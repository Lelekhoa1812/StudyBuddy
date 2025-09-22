# routes/chats.py  
import json, time, re, uuid, asyncio, os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import Form, HTTPException

from helpers.setup import app, rag, logger, embedder, captioner, gemini_rotator, nvidia_rotator
from helpers.models import ChatMessageResponse, ChatHistoryResponse, MessageResponse, ChatAnswerResponse, StatusUpdateResponse
from utils.service.common import trim_text
from .search import build_web_context
# Removed: enhance_question_with_memory - now handled by conversation manager
from utils.api.router import select_model, generate_answer_with_model


@app.post("/chat/save", response_model=MessageResponse)
async def save_chat_message(
    user_id: str = Form(...),
    project_id: str = Form(...),
    role: str = Form(...),
    content: str = Form(...),
    timestamp: Optional[float] = Form(None),
    sources: Optional[str] = Form(None),
    is_report: Optional[int] = Form(0)
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
        **({"sources": parsed_sources} if parsed_sources is not None else {}),
        "is_report": bool(is_report or 0)
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
            sources=message.get("sources"),
            is_report=bool(message.get("is_report", False))
        ))
    
    return ChatHistoryResponse(messages=messages)


@app.delete("/chat/history", response_model=MessageResponse)
async def delete_chat_history(user_id: str, project_id: str):
    try:
        # Clear chat sessions from database
        chat_result = rag.db["chat_sessions"].delete_many({"user_id": user_id, "project_id": project_id})
        logger.info(f"[CHAT] Cleared {chat_result.deleted_count} chat sessions for user {user_id} project {project_id}")
        
        # Clear all memory components using the new comprehensive clear method
        try:
            from memo.core import get_memory_system
            memory = get_memory_system()
            clear_results = memory.clear_all_memory(user_id, project_id)
            
            # Log the results
            if clear_results["errors"]:
                logger.warning(f"[CHAT] Memory clear completed with warnings: {clear_results['errors']}")
            else:
                logger.info(f"[CHAT] Memory clear completed successfully for user {user_id}, project {project_id}")
                
            # Prepare response message
            cleared_components = []
            if clear_results["legacy_cleared"]:
                cleared_components.append("legacy memory")
            if clear_results["enhanced_cleared"]:
                cleared_components.append("enhanced memory")
            if clear_results["session_cleared"]:
                cleared_components.append("conversation sessions")
            if clear_results["planning_reset"]:
                cleared_components.append("planning state")
            
            message = f"Chat history cleared successfully. Cleared: {', '.join(cleared_components)}"
            if clear_results["errors"]:
                message += f" (Warnings: {len(clear_results['errors'])} issues)"
                
        except Exception as me:
            logger.warning(f"[CHAT] Failed to clear memory for user {user_id}: {me}")
            message = "Chat history cleared (memory clear failed)"
        
        return MessageResponse(message=message)
    except Exception as e:
        raise HTTPException(500, detail=f"Failed to clear chat history: {str(e)}")


@app.delete("/chat/history/all", response_model=MessageResponse)
async def delete_all_chat_history(user_id: str):
    """Clear all chat history and memory for a user across all projects"""
    try:
        # Clear all chat sessions from database
        chat_result = rag.db["chat_sessions"].delete_many({"user_id": user_id})
        logger.info(f"[CHAT] Cleared {chat_result.deleted_count} chat sessions for user {user_id} across all projects")
        
        # Clear all memory components using the comprehensive clear method (no project_id = all projects)
        try:
            from memo.core import get_memory_system
            memory = get_memory_system()
            clear_results = memory.clear_all_memory(user_id, None)  # None = all projects
            
            # Log the results
            if clear_results["errors"]:
                logger.warning(f"[CHAT] Global memory clear completed with warnings: {clear_results['errors']}")
            else:
                logger.info(f"[CHAT] Global memory clear completed successfully for user {user_id}")
                
            # Prepare response message
            cleared_components = []
            if clear_results["legacy_cleared"]:
                cleared_components.append("legacy memory")
            if clear_results["enhanced_cleared"]:
                cleared_components.append("enhanced memory")
            if clear_results["session_cleared"]:
                cleared_components.append("conversation sessions")
            if clear_results["planning_reset"]:
                cleared_components.append("planning state")
            
            message = f"All chat history cleared successfully. Cleared: {', '.join(cleared_components)}"
            if clear_results["errors"]:
                message += f" (Warnings: {len(clear_results['errors'])} issues)"
                
        except Exception as me:
            logger.warning(f"[CHAT] Failed to clear global memory for user {user_id}: {me}")
            message = "All chat history cleared (memory clear failed)"
        
        return MessageResponse(message=message)
    except Exception as e:
        raise HTTPException(500, detail=f"Failed to clear all chat history: {str(e)}")


# In-memory status tracking for real-time updates
chat_status_store = {}

@app.get("/chat/status/{session_id}", response_model=StatusUpdateResponse)
async def get_chat_status(session_id: str):
    """Get current status of a chat processing session"""
    status = chat_status_store.get(session_id, {"status": "idle", "message": "Ready", "progress": 0})
    return StatusUpdateResponse(**status)


def update_chat_status(session_id: str, status: str, message: str, progress: int = None):
    """Update chat processing status"""
    chat_status_store[session_id] = {
        "status": status,
        "message": message,
        "progress": progress
    }


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
        
        # Use DeepSeek for better query variation generation reasoning
        from utils.api.router import deepseek_chat_completion
        response = await deepseek_chat_completion(sys_prompt, user_prompt, nvidia_rotator)
        
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
    k: int = Form(6),
    use_web: int = Form(0),
    max_web: int = Form(30),
    session_id: str = Form(None)
):
    import asyncio
    import uuid
    
    # Generate session ID if not provided
    if not session_id:
        session_id = str(uuid.uuid4())
    
    try:
        return await asyncio.wait_for(_chat_impl(user_id, project_id, question, k, use_web=use_web, max_web=max_web, session_id=session_id), timeout=120.0)
    except asyncio.TimeoutError:
        logger.error("[CHAT] Chat request timed out after 120 seconds")
        update_chat_status(session_id, "error", "Request timed out", 0)
        return ChatAnswerResponse(
            answer="Sorry, the request took too long to process. Please try again with a simpler question.",
            sources=[],
            relevant_files=[]
        )


async def _chat_impl(
    user_id: str, 
    project_id: str, 
    question: str, 
    k: int,
    use_web: int = 0,
    max_web: int = 30,
    session_id: str = None
):
    import sys
    from memo.core import get_memory_system
    from utils.api.router import NVIDIA_SMALL  # reuse default name
    memory = get_memory_system()
    logger.info("[CHAT] User Q/chat: %s", trim_text(question, 15).replace("\n", " "))
    
    # Update status: Receiving request
    if session_id:
        update_chat_status(session_id, "receiving", "Receiving request...", 5)
    
    # Step 1: Retrieve and enhance prompt with conversation history FIRST with conversation management
    try:
        recent_context, semantic_context, context_metadata = await memory.get_smart_context(
            user_id, question, nvidia_rotator, project_id, "chat"
        )
        logger.info(f"[CHAT] Smart context retrieved: recent={len(recent_context)}, semantic={len(semantic_context)}")
        
        # Check for context switch
        context_switch_info = await memory.handle_context_switch(user_id, question, nvidia_rotator)
        if context_switch_info.get("is_context_switch", False):
            logger.info(f"[CHAT] Context switch detected (confidence: {context_switch_info.get('confidence', 0):.2f})")
    except Exception as e:
        logger.warning(f"[CHAT] Smart context failed, using fallback: {e}")
        recent_context, semantic_context = "", ""
        context_metadata = {}
    
    # Use enhanced question from smart context if available
    enhanced_question = context_metadata.get("enhanced_input", question)
    memory_context = recent_context + "\n\n" + semantic_context if recent_context or semantic_context else ""
    logger.info(f"[CHAT] Enhanced question with memory context: {len(memory_context)} chars")

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
        # Use enhanced question for better file relevance detection
        relevant_map = await history_manager.files_relevance(enhanced_question, files_list, nvidia_rotator)
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

    # Use context from smart context management (already retrieved above)
    recent_related = recent_context
    semantic_related = semantic_context

    logger.info(f"[CHAT] Starting enhanced vector search with relevant_files={relevant_files}")
    
    # Update status: Processing data (LLM generating query variations)
    if session_id:
        update_chat_status(session_id, "processing", "Processing data...", 15)
    
    # Use enhanced question for better query variations
    enhanced_queries = await _generate_query_variations(enhanced_question, nvidia_rotator)
    logger.info(f"[CHAT] Generated {len(enhanced_queries)} query variations")
    
    # Update status: Planning action (planning search strategy)
    if session_id:
        update_chat_status(session_id, "planning", "Planning action...", 25)
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
        # Avoid overly similar local chunks by simple Jaccard on words
        snippet = trim_text(doc.get('content',''), 2000)
        contexts.append(f"[{doc.get('topic_name','Topic')}] {snippet}")
        sources_meta.append({
            "filename": doc.get("filename"),
            "topic_name": doc.get("topic_name"),
            "page_span": doc.get("page_span"),
            "score": float(score),
            "chunk_id": str(doc.get("_id", ""))
        })
    context_text = "\n\n---\n\n".join(contexts)

    # Optionally augment with web search context
    web_context_block = ""
    web_sources_meta: List[Dict[str, Any]] = []
    if use_web:
        # Update status: Searching information (web search)
        if session_id:
            update_chat_status(session_id, "searching", "Searching information...", 40)
        try:
            # Create status callback for web search
            def web_status_callback(status, message, progress):
                if session_id:
                    update_chat_status(session_id, status, message, progress)
            
            # Use enhanced question for better web search
            web_context_block, web_sources_meta = await build_web_context(enhanced_question, max_web=max_web, top_k=10, status_callback=web_status_callback)
        except Exception as e:
            logger.warning(f"[CHAT] Web augmentation failed: {e}")

    file_summary_block = ""
    if relevant_files:
        fsum_map = {f["filename"]: f.get("summary","") for f in files_list}
        lines = [f"[{fn}] {fsum_map.get(fn, '')}" for fn in relevant_files]
        file_summary_block = "\n".join(lines)

    system_prompt = (
        "You are a careful study assistant. Prefer using the provided CONTEXT to answer.\n"
        "If the CONTEXT is insufficient, you may use general knowledge responsibly, avoiding fabricated details.\n"
        "Only say 'I don't know based on the provided materials.' when the question requires specific facts that are absent.\n"
        "Always include citations to provided materials when you use them, formatted as (source: actual_filename, topic).\n"
        "Use the exact filename as provided in the context, not placeholders.\n"
        "Provide direct, substantive answers without meta-commentary like 'Here is...'.\n"
        "Start your response immediately with the actual answer content.\n"
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
    if web_context_block:
        composed_context += "\n\nWEB_CONTEXT:\n" + web_context_block

    # Update status: Thinking solution
    if session_id:
        update_chat_status(session_id, "thinking", "Thinking solution...", 60)
    
    # Use enhanced question for better answer generation
    user_prompt = f"QUESTION:\n{enhanced_question}\n\nCONTEXT:\n{composed_context}"
    selection = select_model(question=question, context=composed_context)
    logger.info(f"Model selection: {selection}")
    logger.info(f"[CHAT] Generating answer with {selection['provider']} {selection['model']}")
    
    # Update status: Generating answer
    if session_id:
        update_chat_status(session_id, "generating", "Generating answer...", 80)
    
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
            
            # Trigger memory consolidation if needed
            try:
                consolidation_result = await memory.consolidate_memories(user_id, nvidia_rotator)
                if consolidation_result.get("consolidated", 0) > 0:
                    logger.info(f"[CHAT] Memory consolidated: {consolidation_result}")
            except Exception as e:
                logger.warning(f"[CHAT] Memory consolidation failed: {e}")
    except Exception as e:
        logger.warning(f"QA summarize/store failed: {e}")
    # Merge web sources if any (normalize to filename=url for frontend display)
    if web_sources_meta:
        for s in web_sources_meta:
            sources_meta.append({
                "filename": s.get("url"),
                "topic_name": s.get("topic_name"),
                "score": float(s.get("score", 0.0)),
                "kind": "web"
            })
    # Update status: Complete
    if session_id:
        update_chat_status(session_id, "complete", "Answer ready", 100)
    
    logger.info("LLM answer (trimmed): %s", trim_text(answer, 200).replace("\n", " "))
    return ChatAnswerResponse(answer=answer, sources=sources_meta, relevant_files=relevant_files)



# ────────────────────────────── Web Search Augmented Chat ─────────────────────
async def _duckduckgo_search(query: str, max_results: int = 30) -> List[str]:
    """Lightweight DuckDuckGo HTML search scraper returning result URLs."""
    import httpx
    urls: List[str] = []
    try:
        q = re.sub(r"\s+", "+", query.strip())
        search_url = f"https://duckduckgo.com/html/?q={q}"
        headers = {"User-Agent": "Mozilla/5.0 (compatible; StudyBuddy/1.0)"}
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, headers=headers) as client:
            r = await client.get(search_url)
            html = r.text
            # Extract result links; tolerate both 'result__a' and generic anchors
            for m in re.finditer(r'<a[^>]+class=\"result__a[^\"]*\"[^>]+href=\"(https?://[^\"]+)\"', html):
                url = m.group(1)
                if "duckduckgo.com" in url:
                    continue
                urls.append(url)
            if len(urls) < max_results:
                for m in re.finditer(r'<a[^>]+href=\"(https?://[^\"]+)\"', html):
                    url = m.group(1)
                    if "duckduckgo.com" in url:
                        continue
                    urls.append(url)
            # Deduplicate while preserving order
            seen = set()
            deduped = []
            for u in urls:
                if u not in seen:
                    seen.add(u)
                    deduped.append(u)
            return deduped[:max_results]
    except Exception as e:
        logger.warning(f"[CHAT] Web search failed: {e}")
        return []


async def _fetch_readable(url: str) -> str:
    """Fetch readable text using Jina Reader proxy if possible, fallback to raw HTML text."""
    import httpx
    headers = {"User-Agent": "Mozilla/5.0 (compatible; StudyBuddy/1.0)"}
    reader_url = f"https://r.jina.ai/{url}"
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, headers=headers) as client:
            r = await client.get(reader_url)
            if r.status_code == 200 and r.text and len(r.text) > 100:
                return r.text.strip()
            # Fallback to direct fetch
            r2 = await client.get(url)
            return r2.text.strip()
    except Exception as e:
        logger.warning(f"[CHAT] Fetch failed for {url}: {e}")
        return ""


@app.post("/chat/search", response_model=ChatAnswerResponse)
async def chat_with_search(
    user_id: str = Form(...),
    project_id: str = Form(...),
    question: str = Form(...),
    k: int = Form(6),
    max_web: int = Form(30),
    session_id: str = Form(None)
):
    """Answer using local documents and up to 30 web sources, with URL citations."""
    from memo.core import get_memory_system
    memory = get_memory_system()
    logger.info("[CHAT] User Q/chat.search: %s", trim_text(question, 20).replace("\n", " "))

    # 1) Reuse local RAG retrieval
    local_resp = await _chat_impl(user_id, project_id, question, k, use_web=1, max_web=max_web, session_id=session_id)

    # 2) Get enhanced question for web search
    memory = get_memory_system()
    enhanced_question, memory_context = await enhance_question_with_memory(
        user_id, question, memory, nvidia_rotator, embedder
    )

    # 3) Web search and fetching via shared utilities
    # Use enhanced question for better web search
    web_context, web_sources_meta = await build_web_context(enhanced_question, max_web=max_web, top_k=10)
    if not web_context:
        return local_resp

    # 5) Ask the model with merged context and explicit URL citation rule
    composed_context = ""
    if local_resp.sources:
        # Reconstruct local context text roughly from sources is non-trivial; instead, inform the model
        # to consider both local materials and web snippets; we pass the summaries/snippets we have
        pass

    doc_context = web_context
    system_prompt = (
        "You are a careful study assistant. Prefer using the provided CONTEXT to answer.\n"
        "Cite sources for any claims you make.\n"
        "For local documents, cite as (source: filename, topic). For web sources, cite as (web: URL).\n"
        "Use general knowledge if needed but avoid fabrications.\n"
    )
    user_prompt = f"QUESTION:\n{question}\n\nCONTEXT (WEB SNIPPETS + LOCAL MATERIALS):\n{doc_context}"

    selection = select_model(question=question, context=doc_context)
    logger.info(f"[CHAT] Generating web-augmented answer with {selection['provider']} {selection['model']}")
    try:
        answer = await generate_answer_with_model(
            selection=selection,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            gemini_rotator=gemini_rotator,
            nvidia_rotator=nvidia_rotator
        )
    except Exception as e:
        logger.warning(f"[CHAT] Web-augmented LLM error: {e}")
        # Fallback to local-only answer
        return local_resp

    # Merge sources: local + web
    merged_sources = list(local_resp.sources or []) + web_sources_meta
    merged_files = local_resp.relevant_files or []

    logger.info("[CHAT] Web-augmented answer len=%d, web_used=%d", len(answer or ""), len(web_sources_meta))
    return ChatAnswerResponse(answer=answer, sources=merged_sources, relevant_files=merged_files)
