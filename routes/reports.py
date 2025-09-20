# routes/reports.py
import os
from datetime import datetime
from typing import List, Dict
from fastapi import Form, HTTPException

from helpers.setup import app, rag, logger, embedder, gemini_rotator, nvidia_rotator
from .search import build_web_context
from helpers.models import ReportResponse
from utils.service.common import trim_text
from utils.api.router import select_model, generate_answer_with_model


@app.post("/report", response_model=ReportResponse)
async def generate_report(
    user_id: str = Form(...),
    project_id: str = Form(...),
    filename: str = Form(...),
    outline_words: int = Form(200),
    report_words: int = Form(1200),
    instructions: str = Form(""),
    use_web: int = Form(0),
    max_web: int = Form(20)
):
    logger.info("[REPORT] User Q/report: %s", trim_text(instructions, 15).replace("\n", " "))
    files_list = rag.list_files(user_id=user_id, project_id=project_id)
    filenames_ci = {f.get("filename", "").lower(): f.get("filename") for f in files_list}
    eff_name = filenames_ci.get(filename.lower(), filename)
    doc_sum = rag.get_file_summary(user_id=user_id, project_id=project_id, filename=eff_name)
    if not doc_sum:
        raise HTTPException(404, detail="No summary found for that file.")

    query_text = f"Comprehensive report for {eff_name}"
    if instructions.strip():
        query_text = f"{instructions} {eff_name}"
    q_vec = embedder.embed([query_text])[0]
    hits = rag.vector_search(user_id=user_id, project_id=project_id, query_vector=q_vec, k=8, filenames=[eff_name], search_type="flat")
    if not hits:
        hits = []

    contexts: List[str] = []
    sources_meta: List[Dict] = []
    for h in hits:
        doc = h["doc"]
        chunk_id = str(doc.get("_id", ""))
        contexts.append(f"[CHUNK_ID: {chunk_id}] [{doc.get('topic_name','Topic')}] {trim_text(doc.get('content',''), 2000)}")
        sources_meta.append({
            "filename": doc.get("filename"),
            "topic_name": doc.get("topic_name"),
            "page_span": doc.get("page_span"),
            "score": float(h.get("score", 0.0)),
            "chunk_id": chunk_id
        })
    context_text = "\n\n---\n\n".join(contexts) if contexts else ""
    web_context_block = ""
    web_sources_meta: List[Dict] = []
    if use_web:
        web_context_block, web_sources_meta = await build_web_context(
            instructions or query_text, max_web=max_web, top_k=12
        )
    file_summary = doc_sum.get("summary", "")

    from utils.api.router import GEMINI_MED, GEMINI_PRO
    if instructions.strip():
        filter_sys = (
            "You are an expert content analyst. Given the user's specific instructions and the document content, "
            "identify which sections/chunks are MOST relevant to their request. "
            "Each chunk is prefixed with [CHUNK_ID: <id>] - use these exact IDs in your response. "
            "Return a JSON object with this structure: {\"relevant_chunks\": [\"<chunk_id_1>\", \"<chunk_id_2>\"], \"focus_areas\": [\"key topic 1\", \"key topic 2\"]}"
        )
        filter_user = f"USER_INSTRUCTIONS: {instructions}\n\nDOCUMENT_SUMMARY: {file_summary}\n\nAVAILABLE_CHUNKS:\n{context_text}\n\nIdentify only the chunks that directly address the user's specific request."
        try:
            selection_filter = {"provider": "gemini", "model": os.getenv("GEMINI_MED", "gemini-2.5-flash")}
            filter_response = await generate_answer_with_model(selection_filter, filter_sys, filter_user, gemini_rotator, nvidia_rotator)
            logger.info(f"[REPORT] Raw filter response: {filter_response}")
            import json as _json
            try:
                # Extract JSON from markdown code blocks if present
                json_text = filter_response.strip()
                if json_text.startswith('```json'):
                    # Remove markdown code block formatting
                    json_text = json_text[7:]  # Remove ```json
                    if json_text.endswith('```'):
                        json_text = json_text[:-3]  # Remove ```
                    json_text = json_text.strip()
                elif json_text.startswith('```'):
                    # Remove generic code block formatting
                    json_text = json_text[3:]  # Remove ```
                    if json_text.endswith('```'):
                        json_text = json_text[:-3]  # Remove ```
                    json_text = json_text.strip()
                
                filter_data = _json.loads(json_text)
                relevant_chunk_ids = filter_data.get("relevant_chunks", [])
                focus_areas = filter_data.get("focus_areas", [])
                logger.info(f"[REPORT] Content filtering identified {len(relevant_chunk_ids)} relevant chunks: {relevant_chunk_ids} and focus areas: {focus_areas}")
                if relevant_chunk_ids and hits:
                    filtered_hits = [h for h in hits if str(h["doc"].get("_id", "")) in relevant_chunk_ids]
                    if filtered_hits:
                        hits = filtered_hits
                        logger.info(f"[REPORT] Filtered context from {len(hits)} chunks to {len(filtered_hits)} relevant chunks")
                    else:
                        logger.warning(f"[REPORT] No matching chunks found for IDs: {relevant_chunk_ids}")
                else:
                    logger.warning(f"[REPORT] No relevant chunk IDs returned or no hits available")
            except _json.JSONDecodeError as e:
                logger.warning(f"[REPORT] Could not parse filter response, using all chunks. JSON error: {e}. Response: {filter_response}")
        except Exception as e:
            logger.warning(f"[REPORT] Content filtering failed: {e}")

    sys_outline = (
        "You are an expert technical writer. Create a focused, hierarchical outline for a report based on the user's specific instructions and the MATERIALS. "
        "The outline should directly address what the user asked for. Output as Markdown bullet list only. Keep it within about {} words."
    ).format(max(100, outline_words))
    instruction_context = f"USER_REQUEST: {instructions}\n\n" if instructions.strip() else ""
    user_outline = f"{instruction_context}MATERIALS:\n\n[FILE_SUMMARY from {eff_name}]\n{file_summary}\n\n[DOC_CONTEXT]\n{context_text}\n\n[WEB_CONTEXT]\n{web_context_block}"
    try:
        selection_outline = {"provider": "gemini", "model": os.getenv("GEMINI_MED", "gemini-2.5-flash")}
        outline_md = await generate_answer_with_model(selection_outline, sys_outline, user_outline, gemini_rotator, nvidia_rotator)
    except Exception as e:
        logger.warning(f"Report outline failed: {e}")
        outline_md = "# Report Outline\n\n- Introduction\n- Key Topics\n- Conclusion"

    instruction_focus = f"FOCUS ON: {instructions}\n\n" if instructions.strip() else ""
    sys_report = (
        "You are an expert report writer. Write a focused, comprehensive Markdown report that directly addresses the user's specific request. "
        "Using the OUTLINE and MATERIALS:\n"
        "- Structure the report to answer exactly what the user asked for\n"
        "- Use clear section headings\n"
        "- Keep content factual and grounded in the provided materials\n"
        f"- Include brief citations like (source: {eff_name}, topic) - use the actual filename provided\n"
        "- If the user asked for a specific section/topic, focus heavily on that\n"
        f"- Target length ~{max(600, report_words)} words\n"
        "- Ensure the report directly fulfills the user's request"
    )
    user_report = f"{instruction_focus}OUTLINE:\n{outline_md}\n\nMATERIALS:\n[FILE_SUMMARY from {eff_name}]\n{file_summary}\n\n[DOC_CONTEXT]\n{context_text}\n\n[WEB_CONTEXT]\n{web_context_block}"
    try:
        selection_report = {"provider": "gemini", "model": os.getenv("GEMINI_PRO", "gemini-2.5-pro")}
        report_md = await generate_answer_with_model(selection_report, sys_report, user_report, gemini_rotator, nvidia_rotator)
    except Exception as e:
        logger.error(f"Report generation failed: {e}")
        report_md = outline_md + "\n\n" + file_summary
    # Merge local and web sources
    merged_sources = list(sources_meta) + [
        {"filename": s.get("url"), "topic_name": s.get("topic_name"), "score": s.get("score"), "kind": "web"}
        for s in web_sources_meta
    ]
    return ReportResponse(filename=eff_name, report_markdown=report_md, sources=merged_sources)


@app.post("/report/pdf")
async def generate_report_pdf(
    user_id: str = Form(...),
    project_id: str = Form(...),
    report_content: str = Form(...)
):
    from utils.service.pdf import generate_report_pdf as generate_pdf
    from fastapi.responses import Response
    try:
        pdf_content = await generate_pdf(report_content, user_id, project_id)
        return Response(
            content=pdf_content,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=report-{datetime.now().strftime('%Y-%m-%d')}.pdf"}
        )
    except HTTPException:
        raise


