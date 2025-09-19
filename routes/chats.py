import json, time, re, uuid, asyncio, os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import Form, HTTPException

from helpers.setup import app, rag, logger, embedder, captioner, gemini_rotator, nvidia_rotator
from helpers.models import ChatMessageResponse, ChatHistoryResponse, MessageResponse, ChatAnswerResponse
from utils.service.common import trim_text
from utils.api.router import select_model, generate_answer_with_model


@app.post("/chat/save", response_model=MessageResponse)
async def save_chat_message(
    user_id: str = Form(...),
    project_id: str = Form(...),
    role: str = Form(...),
    content: str = Form(...),
    timestamp: Optional[float] = Form(None),
    sources: Optional[str] = Form(None)
):
    """Save a chat message to the session"""
    if role not in ["user", "assistant"]:
        raise HTTPException(400, detail="Invalid role")
    
    # Parse optional sources JSON
    parsed_sources: Optional[List[Dict[str, Any]]] = None
    if sources:
        try:
            parsed = json.loads(sources)
            if isinstance(parsed, list):
                parsed_sources = parsed
        except Exception:
            parsed_sources = None

    message = {
        "user_id": user_id,
        "project_id": project_id,
        "role": role,
        "content": content,
        "timestamp": timestamp or time.time(),
        "created_at": datetime.now(timezone.utc),
        **({"sources": parsed_sources} if parsed_sources is not None else {})
    }
    
    rag.db["chat_sessions"].insert_one(message)
    return MessageResponse(message="Chat message saved")


@app.get("/chat/history", response_model=ChatHistoryResponse)
async def get_chat_history(user_id: str, project_id: str, limit: int = 100):
    """Get chat history for a project"""
    messages_cursor = rag.db["chat_sessions"].find(
        {"user_id": user_id, "project_id": project_id}
    ).sort("timestamp", 1).limit(limit)
    
    messages = []
    for message in messages_cursor:
        messages.append(ChatMessageResponse(
            user_id=message["user_id"],
            project_id=message["project_id"],
            role=message["role"],
            content=message["content"],
            timestamp=message["timestamp"],
            created_at=message["created_at"].isoformat() if isinstance(message["created_at"], datetime) else str(message["created_at"]),
            sources=message.get("sources")
        ))
    
    return ChatHistoryResponse(messages=messages)


@app.delete("/chat/history", response_model=MessageResponse)
async def delete_chat_history(user_id: str, project_id: str):
    try:
        rag.db["chat_sessions"].delete_many({"user_id": user_id, "project_id": project_id})
        logger.info(f"[CHAT] Cleared history for user {user_id} project {project_id}")
        # Also clear in-memory LRU for this user to avoid stale context
        try:
            from memo.core import get_memory_system
            memory = get_memory_system()
            memory.clear(user_id)
            logger.info(f"[CHAT] Cleared memory for user {user_id}")
        except Exception as me:
            logger.warning(f"[CHAT] Failed to clear memory for user {user_id}: {me}")
        return MessageResponse(message="Chat history cleared")
    except Exception as e:
        raise HTTPException(500, detail=f"Failed to clear chat history: {str(e)}")


# ────────────────────────────── RAG Chat and Helpers ──────────────────────────────
async def _generate_query_variations(question: str, nvidia_rotator) -> List[str]:
    """
    Generate multiple query variations using Chain of Thought reasoning
    """
    if not nvidia_rotator:
        return [question]  # Fallback to original question
    
    try:
        # Use NVIDIA to generate query variations
        sys_prompt = """You are an expert at query expansion and reformulation. Given a user question, generate 3-5 different ways to ask the same question that would help retrieve relevant information from a document database.

Focus on:
1. Different terminology and synonyms
2. More specific technical terms
3. Broader conceptual queries
4. Question reformulations

Return only the variations, one per line, no numbering or extra text."""
        
        user_prompt = f"Original question: {question}\n\nGenerate query variations:"
        
        from utils.api.router import generate_answer_with_model
        selection = {"provider": "nvidia", "model": "meta/llama-3.1-8b-instruct"}
        response = await generate_answer_with_model(selection, sys_prompt, user_prompt, None, nvidia_rotator)
        
        # Parse variations
        variations = [line.strip() for line in response.split('\n') if line.strip()]
        variations = [v for v in variations if len(v) > 10]  # Filter out too short variations
        
        # Always include original question
        if question not in variations:
            variations.insert(0, question)
        
        return variations[:5]  # Limit to 5 variations
        
    except Exception as e:
        logger.warning(f"Query variation generation failed: {e}")
        return [question]


def _deduplicate_and_rank_hits(all_hits: List[Dict], original_question: str) -> List[Dict]:
    """
    Deduplicate hits by chunk ID and rank by relevance to original question
    """
    if not all_hits:
        return []
    
    # Deduplicate by chunk ID
    seen_ids = set()
    unique_hits = []
    
    for hit in all_hits:
        chunk_id = str(hit.get("doc", {}).get("_id", ""))
        if chunk_id not in seen_ids:
            seen_ids.add(chunk_id)
            unique_hits.append(hit)
    
    # Simple ranking: boost scores for hits that contain question keywords
    question_words = set(original_question.lower().split())
    
    for hit in unique_hits:
        content = hit.get("doc", {}).get("content", "").lower()
        topic = hit.get("doc", {}).get("topic_name", "").lower()
        
        # Count keyword matches
        content_matches = sum(1 for word in question_words if word in content)
        topic_matches = sum(1 for word in question_words if word in topic)
        
        # Boost score based on keyword matches
        keyword_boost = 1.0 + (content_matches * 0.1) + (topic_matches * 0.2)
        hit["score"] = hit.get("score", 0.0) * keyword_boost
    
    # Sort by boosted score
    unique_hits.sort(key=lambda x: x.get("score", 0.0), reverse=True)
    
    return unique_hits


@app.post("/chat", response_model=ChatAnswerResponse)
async def chat(
    user_id: str = Form(...), 
    project_id: str = Form(...), 
    question: str = Form(...), 
    k: int = Form(6)
):
    import asyncio
    try:
        return await asyncio.wait_for(_chat_impl(user_id, project_id, question, k), timeout=120.0)
    except asyncio.TimeoutError:
        logger.error("[CHAT] Chat request timed out after 120 seconds")
        return ChatAnswerResponse(
            answer="Sorry, the request took too long to process. Please try again with a simpler question.",
            sources=[],
            relevant_files=[]
        )


async def _chat_impl(
    user_id: str, 
    project_id: str, 
    question: str, 
    k: int
):
    import sys
    from memo.core import get_memory_system
    from utils.api.router import NVIDIA_SMALL  # reuse default name
    memory = get_memory_system()
    logger.info("[CHAT] User Q/chat: %s", trim_text(question, 15).replace("\n", " "))

    mentioned = set([m.group(0).strip() for m in re.finditer(r"\b[^\s/\\]+?\.(?:pdf|docx|doc)\b", question, re.IGNORECASE)])
    if mentioned:
        logger.info(f"[CHAT] Detected mentioned filenames in question: {list(mentioned)}")

    if mentioned and (re.search(r"\b(summary|summarize|about|overview)\b", question, re.IGNORECASE)):
        if len(mentioned) == 1:
            fn = next(iter(mentioned))
            doc = rag.get_file_summary(user_id=user_id, project_id=project_id, filename=fn)
            if doc:
                return ChatAnswerResponse(
                    answer=doc.get("summary", ""),
                    sources=[{"filename": fn, "file_summary": True}]
                )
            files_ci = rag.list_files(user_id=user_id, project_id=project_id)
            match = next((f["filename"] for f in files_ci if f.get("filename", "").lower() == fn.lower()), None)
            if match:
                doc = rag.get_file_summary(user_id=user_id, project_id=project_id, filename=match)
                if doc:
                    return ChatAnswerResponse(
                        answer=doc.get("summary", ""),
                        sources=[{"filename": match, "file_summary": True}]
                    )

    files_list = rag.list_files(user_id=user_id, project_id=project_id)

    filenames_ci_map = {f.get("filename", "").lower(): f.get("filename") for f in files_list if f.get("filename")}
    mentioned_normalized = []
    for mfn in mentioned:
        key = mfn.lower()
        if key in filenames_ci_map:
            mentioned_normalized.append(filenames_ci_map[key])
    if mentioned and not mentioned_normalized and files_list:
        norm = {f.get("filename", "").lower().replace(" ", ""): f.get("filename") for f in files_list if f.get("filename")}
        for mfn in mentioned:
            key2 = mfn.lower().replace(" ", "")
            if key2 in norm:
                mentioned_normalized.append(norm[key2])
    if mentioned_normalized:
        logger.info(f"[CHAT] Normalized mentions to stored filenames: {mentioned_normalized}")

    try:
        from memo.history import get_history_manager
        history_manager = get_history_manager(memory)
        relevant_map = await history_manager.files_relevance(question, files_list, nvidia_rotator)
        relevant_files = [fn for fn, ok in relevant_map.items() if ok]
        logger.info(f"[CHAT] NVIDIA relevant files: {relevant_files}")
    except Exception as e:
        logger.warning(f"[CHAT] NVIDIA relevance failed, defaulting to all files: {e}")
        relevant_files = [f.get("filename") for f in files_list if f.get("filename")]

    if mentioned_normalized:
        extra = [fn for fn in mentioned_normalized if fn not in relevant_files]
        relevant_files.extend(extra)
        if extra:
            logger.info(f"[CHAT] Forced-include mentioned files into relevance: {extra}")

    try:
        from memo.history import get_history_manager
        history_manager = get_history_manager(memory)
        recent_related, semantic_related = await history_manager.related_recent_and_semantic_context(
            user_id, question, embedder
        )
    except Exception as e:
        logger.warning(f"[CHAT] Enhanced context retrieval failed, using fallback: {e}")
        recent3 = memory.recent(user_id, 3)
        if recent3:
            sys = "Pick only items that directly relate to the new question. Output the selected items verbatim, no commentary. If none, output nothing."
            numbered = [{"id": i+1, "text": s} for i, s in enumerate(recent3)]
            user = f"Question: {question}\nCandidates:\n{json.dumps(numbered, ensure_ascii=False)}\nSelect any related items and output ONLY their 'text' values concatenated."
            try:
                from utils.api.rotator import robust_post_json
                key = nvidia_rotator.get_key()
                url = "https://integrate.api.nvidia.com/v1/chat/completions"
                payload = {
                    "model": os.getenv("NVIDIA_SMALL", "meta/llama-3.1-8b-instruct"),
                    "temperature": 0.0,
                    "messages": [
                        {"role": "system", "content": sys},
                        {"role": "user", "content": user},
                    ]
                }
                headers = {"Content-Type": "application/json", "Authorization": f"Bearer {key or ''}"}
                data = await robust_post_json(url, headers, payload, nvidia_rotator)
                recent_related = data["choices"][0]["message"]["content"].strip()
            except Exception as e:
                logger.warning(f"Recent-related NVIDIA error: {e}")
                recent_related = ""
        else:
            recent_related = ""
        rest17 = memory.rest(user_id, 3)
        if rest17:
            import numpy as np
            def _cosine(a: np.ndarray, b: np.ndarray) -> float:
                denom = (np.linalg.norm(a) * np.linalg.norm(b)) or 1.0
                return float(np.dot(a, b) / denom)
            qv = np.array(embedder.embed([question])[0], dtype="float32")
            mats = embedder.embed([s.strip() for s in rest17])
            sims = [(_cosine(qv, np.array(v, dtype="float32")), s) for v, s in zip(mats, rest17)]
            sims.sort(key=lambda x: x[0], reverse=True)
            top = [s for (sc, s) in sims[:3] if sc > 0.15]
            semantic_related = "\n\n".join(top) if top else ""

    logger.info(f"[CHAT] Starting enhanced vector search with relevant_files={relevant_files}")
    enhanced_queries = await _generate_query_variations(question, nvidia_rotator)
    logger.info(f"[CHAT] Generated {len(enhanced_queries)} query variations")
    all_hits = []
    search_strategies = ["flat", "hybrid", "local"]
    for strategy in search_strategies:
        for query_variant in enhanced_queries:
            q_vec = embedder.embed([query_variant])[0]
            hits = rag.vector_search(
                user_id=user_id,
                project_id=project_id,
                query_vector=q_vec,
                k=k,
                filenames=relevant_files if relevant_files else None,
                search_type=strategy
            )
            if hits:
                all_hits.extend(hits)
                logger.info(f"[CHAT] {strategy} search with '{query_variant[:50]}...' returned {len(hits)} hits")
                break
        if all_hits:
            break
    hits = _deduplicate_and_rank_hits(all_hits, question)
    logger.info(f"[CHAT] Final vector search returned {len(hits) if hits else 0} hits")
    if not hits:
        logger.info(f"[CHAT] No hits with relevance filter. relevant_files={relevant_files}")
        q_vec_original = embedder.embed([question])[0]
        hits = rag.vector_search(
            user_id=user_id,
            project_id=project_id,
            query_vector=q_vec_original,
            k=k,
            filenames=relevant_files if relevant_files else None,
            search_type="flat"
        )
        logger.info(f"[CHAT] Fallback flat search → hits={len(hits) if hits else 0}")
        if not hits and mentioned_normalized:
            hits = rag.vector_search(
                user_id=user_id,
                project_id=project_id,
                query_vector=q_vec_original,
                k=k,
                filenames=mentioned_normalized,
                search_type="flat"
            )
            logger.info(f"[CHAT] Fallback with mentioned files only → hits={len(hits) if hits else 0}")
        if not hits:
            hits = rag.vector_search(
                user_id=user_id,
                project_id=project_id,
                query_vector=q_vec_original,
                k=k,
                filenames=None,
                search_type="flat"
            )
            logger.info(f"[CHAT] Fallback with all files → hits={len(hits) if hits else 0}")
        if not hits and mentioned_normalized:
            fsum_map = {f["filename"]: f.get("summary", "") for f in files_list}
            summaries = [fsum_map.get(fn, "") for fn in mentioned_normalized]
            summaries = [s for s in summaries if s]
            if summaries:
                answer = ("\n\n---\n\n").join(summaries)
                return ChatAnswerResponse(
                    answer=answer,
                    sources=[{"filename": fn, "file_summary": True} for fn in mentioned_normalized],
                    relevant_files=mentioned_normalized
                )
        if not hits:
            candidates = mentioned_normalized or relevant_files or []
            if candidates:
                fsum_map = {f["filename"]: f.get("summary", "") for f in files_list}
                summaries = [fsum_map.get(fn, "") for fn in candidates]
                summaries = [s for s in summaries if s]
                if summaries:
                    answer = ("\n\n---\n\n").join(summaries)
                    logger.info(f"[CHAT] Falling back to file-level summaries for: {candidates}")
                    return ChatAnswerResponse(
                        answer=answer,
                        sources=[{"filename": fn, "file_summary": True} for fn in candidates],
                        relevant_files=candidates
                    )
            return ChatAnswerResponse(
                answer="I don't know based on your uploaded materials. Try uploading more sources or rephrasing the question.",
                sources=[],
                relevant_files=relevant_files or mentioned_normalized
            )
    contexts = []
    sources_meta = []
    for h in hits:
        doc = h["doc"]
        score = h["score"]
        contexts.append(f"[{doc.get('topic_name','Topic')}] {trim_text(doc.get('content',''), 2000)}")
        sources_meta.append({
            "filename": doc.get("filename"),
            "topic_name": doc.get("topic_name"),
            "page_span": doc.get("page_span"),
            "score": float(score),
            "chunk_id": str(doc.get("_id", ""))
        })
    context_text = "\n\n---\n\n".join(contexts)

    file_summary_block = ""
    if relevant_files:
        fsum_map = {f["filename"]: f.get("summary","") for f in files_list}
        lines = [f"[{fn}] {fsum_map.get(fn, '')}" for fn in relevant_files]
        file_summary_block = "\n".join(lines)

    system_prompt = (
        "You are a careful study assistant. Answer strictly using the given CONTEXT.\n"
        "If the answer isn't in the context, say 'I don't know based on the provided materials.'\n"
        "Write concise, clear explanations with citations like (source: actual_filename, topic).\n"
        "Use the exact filename as provided in the context, not placeholders.\n"
    )

    history_block = ""
    if recent_related or semantic_related:
        history_block = "RECENT_CHAT_CONTEXT:\n" + (recent_related or "") + ("\n\nHISTORICAL_SIMILARITY_CONTEXT:\n" + semantic_related if semantic_related else "")
    composed_context = ""
    if history_block:
        composed_context += history_block + "\n\n"
    if file_summary_block:
        composed_context += "FILE_SUMMARIES:\n" + file_summary_block + "\n\n"
    composed_context += "DOC_CONTEXT:\n" + context_text

    user_prompt = f"QUESTION:\n{question}\n\nCONTEXT:\n{composed_context}"
    selection = select_model(question=question, context=composed_context)
    logger.info(f"Model selection: {selection}")
    logger.info(f"[CHAT] Generating answer with {selection['provider']} {selection['model']}")
    try:
        answer = await generate_answer_with_model(
            selection=selection,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            gemini_rotator=gemini_rotator,
            nvidia_rotator=nvidia_rotator
        )
        logger.info(f"[CHAT] Answer generated successfully, length: {len(answer)}")
    except Exception as e:
        logger.error(f"LLM error: {e}")
        answer = "I had trouble contacting the language model provider just now. Please try again."
    try:
        from memo.history import get_history_manager
        history_manager = get_history_manager(memory)
        qa_sum = await history_manager.summarize_qa_with_nvidia(question, answer, nvidia_rotator)
        memory.add(user_id, qa_sum)
        if memory.is_enhanced_available():
            await memory.add_conversation_memory(
                user_id=user_id,
                question=question,
                answer=answer,
                project_id=project_id,
                context={
                    "relevant_files": relevant_files,
                    "sources_count": len(sources_meta),
                    "timestamp": time.time()
                }
            )
    except Exception as e:
        logger.warning(f"QA summarize/store failed: {e}")
    logger.info("LLM answer (trimmed): %s", trim_text(answer, 200).replace("\n", " "))
    return ChatAnswerResponse(answer=answer, sources=sources_meta, relevant_files=relevant_files)


