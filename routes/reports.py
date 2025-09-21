# routes/reports.py
import os
from datetime import datetime
from typing import List, Dict
from fastapi import Form, HTTPException

from helpers.setup import app, rag, logger, embedder, gemini_rotator, nvidia_rotator
from .search import build_web_context
from helpers.models import ReportResponse, StatusUpdateResponse
from utils.service.common import trim_text
from utils.api.router import select_model, generate_answer_with_model


# In-memory status tracking for report generation
report_status_store = {}

@app.get("/report/status/{session_id}", response_model=StatusUpdateResponse)
async def get_report_status(session_id: str):
    """Get current status of a report generation session"""
    status = report_status_store.get(session_id, {"status": "idle", "message": "Ready", "progress": 0})
    return StatusUpdateResponse(**status)

def update_report_status(session_id: str, status: str, message: str, progress: int = None):
    """Update report generation status"""
    report_status_store[session_id] = {
        "status": status,
        "message": message,
        "progress": progress
    }

@app.post("/report", response_model=ReportResponse)
async def generate_report(
    user_id: str = Form(...),
    project_id: str = Form(...),
    filename: str = Form(...),
    outline_words: int = Form(200),
    report_words: int = Form(1200),
    instructions: str = Form(""),
    use_web: int = Form(0),
    max_web: int = Form(20),
    session_id: str = Form(None)
):
    import uuid
    if not session_id:
        session_id = str(uuid.uuid4())
    
    logger.info("[REPORT] User Q/report: %s", trim_text(instructions, 15).replace("\n", " "))
    
    # Update status: Receiving request
    update_report_status(session_id, "receiving", "Receiving request...", 5)
    
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
        # Create status callback for web search
        def web_status_callback(status, message, progress):
            update_report_status(session_id, status, message, progress)
        
        web_context_block, web_sources_meta = await build_web_context(
            instructions or query_text, max_web=max_web, top_k=12, status_callback=web_status_callback
        )
    file_summary = doc_sum.get("summary", "")

    # Step 1: Chain of Thought Planning with NVIDIA
    logger.info("[REPORT] Starting CoT planning phase")
    update_report_status(session_id, "planning", "Planning action...", 25)
    cot_plan = await generate_cot_plan(instructions, file_summary, context_text, web_context_block, nvidia_rotator)
    
    # Step 2: Execute detailed subtasks based on CoT plan
    logger.info("[REPORT] Executing detailed subtasks")
    update_report_status(session_id, "processing", "Processing data...", 40)
    detailed_analysis = await execute_detailed_subtasks(cot_plan, context_text, web_context_block, eff_name, nvidia_rotator)
    
    # Step 3: Synthesize comprehensive report from detailed analysis
    logger.info("[REPORT] Synthesizing comprehensive report")
    update_report_status(session_id, "thinking", "Thinking solution...", 60)
    comprehensive_report = await synthesize_comprehensive_report(
        instructions, cot_plan, detailed_analysis, eff_name, report_words, gemini_rotator, nvidia_rotator
    )
    
    # Update status: Generating answer (final report generation)
    update_report_status(session_id, "generating", "Generating answer...", 80)
    
    # Update status: Complete
    update_report_status(session_id, "complete", "Report ready", 100)

    # Use the comprehensive report from CoT approach
    report_md = comprehensive_report
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
    report_content: str = Form(...),
    sources: str = Form("[]")
):
    from utils.service.pdf import generate_report_pdf as generate_pdf
    from fastapi.responses import Response
    import json
    try:
        # Parse sources JSON
        sources_list = []
        if sources and sources != "[]":
            try:
                sources_list = json.loads(sources)
            except json.JSONDecodeError:
                logger.warning(f"[REPORT] Failed to parse sources JSON: {sources}")
        
        pdf_content = await generate_pdf(report_content, user_id, project_id, sources_list)
        return Response(
            content=pdf_content,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=report-{datetime.now().strftime('%Y-%m-%d')}.pdf"}
        )
    except HTTPException:
        raise


# ────────────────────────────── Chain of Thought Report Generation ──────────────────

async def generate_cot_plan(instructions: str, file_summary: str, context_text: str, web_context: str, nvidia_rotator) -> Dict[str, Any]:
    """Generate a detailed Chain of Thought plan for report generation using NVIDIA."""
    sys_prompt = """You are an expert research analyst and report planner. Given a user's request and available materials, create a comprehensive plan for generating a detailed report.

Your task is to:
1. Analyze the user's request and identify key requirements
2. Break down the report into logical sections and subtasks
3. Identify what specific information needs to be extracted from each source
4. Plan the reasoning flow and argument structure
5. Determine the depth and rigor needed for each section

Return a JSON object with this structure:
{
  "analysis": {
    "user_intent": "What the user really wants to know",
    "key_requirements": ["requirement1", "requirement2"],
    "complexity_level": "basic|intermediate|advanced",
    "focus_areas": ["area1", "area2", "area3"]
  },
  "report_structure": {
    "sections": [
      {
        "title": "Section Title",
        "purpose": "Why this section is needed",
        "subtasks": [
          {
            "task": "Specific task description",
            "reasoning": "Why this task is important",
            "sources_needed": ["local", "web", "both"],
            "depth": "surface|detailed|comprehensive"
          }
        ]
      }
    ]
  },
  "reasoning_flow": [
    "Step 1: Start with...",
    "Step 2: Then analyze...",
    "Step 3: Finally synthesize..."
  ]
}"""

    user_prompt = f"""USER REQUEST: {instructions}

AVAILABLE MATERIALS:
FILE SUMMARY: {file_summary}

DOCUMENT CONTEXT: {context_text[:2000]}...

WEB CONTEXT: {web_context[:2000]}...

Create a detailed plan for generating a comprehensive report that addresses the user's request."""

    try:
        selection = {"provider": "nvidia", "model": "meta/llama-3.1-8b-instruct"}
        response = await generate_answer_with_model(selection, sys_prompt, user_prompt, None, nvidia_rotator)
        
        # Parse JSON response
        import json
        json_text = response.strip()
        if json_text.startswith('```json'):
            json_text = json_text[7:-3].strip()
        elif json_text.startswith('```'):
            json_text = json_text[3:-3].strip()
        
        plan = json.loads(json_text)
        logger.info(f"[REPORT] CoT plan generated with {len(plan.get('report_structure', {}).get('sections', []))} sections")
        return plan
        
    except Exception as e:
        logger.warning(f"[REPORT] CoT planning failed: {e}")
        # Fallback plan
        return {
            "analysis": {
                "user_intent": instructions,
                "key_requirements": ["comprehensive analysis"],
                "complexity_level": "intermediate",
                "focus_areas": ["main topics"]
            },
            "report_structure": {
                "sections": [
                    {
                        "title": "Introduction",
                        "purpose": "Provide overview and context",
                        "subtasks": [{"task": "Summarize key points", "reasoning": "Set foundation", "sources_needed": ["local"], "depth": "detailed"}]
                    },
                    {
                        "title": "Main Analysis",
                        "purpose": "Address user's specific request",
                        "subtasks": [{"task": "Detailed analysis", "reasoning": "Core content", "sources_needed": ["both"], "depth": "comprehensive"}]
                    },
                    {
                        "title": "Conclusion",
                        "purpose": "Synthesize findings",
                        "subtasks": [{"task": "Summarize key insights", "reasoning": "Provide closure", "sources_needed": ["local"], "depth": "detailed"}]
                    }
                ]
            },
            "reasoning_flow": ["Analyze materials", "Extract key insights", "Synthesize findings"]
        }


async def execute_detailed_subtasks(cot_plan: Dict[str, Any], context_text: str, web_context: str, filename: str, nvidia_rotator) -> Dict[str, Any]:
    """Execute detailed analysis for each subtask identified in the CoT plan."""
    detailed_analysis = {}
    
    for section in cot_plan.get("report_structure", {}).get("sections", []):
        section_title = section.get("title", "Unknown Section")
        section_analysis = {
            "title": section_title,
            "purpose": section.get("purpose", ""),
            "subtask_results": []
        }
        
        for subtask in section.get("subtasks", []):
            task = subtask.get("task", "")
            reasoning = subtask.get("reasoning", "")
            sources_needed = subtask.get("sources_needed", ["local"])
            depth = subtask.get("depth", "detailed")
            
            # Generate detailed analysis for this subtask
            subtask_result = await analyze_subtask(
                task, reasoning, sources_needed, depth, context_text, web_context, filename, nvidia_rotator
            )
            
            section_analysis["subtask_results"].append({
                "task": task,
                "reasoning": reasoning,
                "depth": depth,
                "analysis": subtask_result
            })
        
        detailed_analysis[section_title] = section_analysis
    
    logger.info(f"[REPORT] Completed detailed analysis for {len(detailed_analysis)} sections")
    return detailed_analysis


async def analyze_subtask(task: str, reasoning: str, sources_needed: List[str], depth: str, 
                         context_text: str, web_context: str, filename: str, nvidia_rotator) -> str:
    """Analyze a specific subtask with appropriate depth and source selection."""
    
    # Select appropriate context based on sources_needed
    selected_context = ""
    if "local" in sources_needed and "web" in sources_needed:
        selected_context = f"DOCUMENT CONTEXT:\n{context_text}\n\nWEB CONTEXT:\n{web_context}"
    elif "local" in sources_needed:
        selected_context = f"DOCUMENT CONTEXT:\n{context_text}"
    elif "web" in sources_needed:
        selected_context = f"WEB CONTEXT:\n{web_context}"
    
    # Adjust prompt based on depth requirement
    depth_instructions = {
        "surface": "Provide a brief, high-level analysis",
        "detailed": "Provide a thorough, well-reasoned analysis with specific examples",
        "comprehensive": "Provide an exhaustive, rigorous analysis with deep insights and multiple perspectives"
    }
    
    sys_prompt = f"""You are an expert analyst performing detailed research. Your task is to {task}.

REASONING: {reasoning}

DEPTH REQUIREMENT: {depth_instructions.get(depth, "Provide detailed analysis")}

Focus on:
- Extracting specific, relevant information
- Providing clear explanations and insights
- Supporting claims with evidence from the materials
- Maintaining analytical rigor and objectivity
- Being comprehensive yet concise

Return only the analysis, no meta-commentary."""

    user_prompt = f"""TASK: {task}

MATERIALS:
{selected_context}

Perform the analysis as specified."""

    try:
        selection = {"provider": "nvidia", "model": "meta/llama-3.1-8b-instruct"}
        analysis = await generate_answer_with_model(selection, sys_prompt, user_prompt, None, nvidia_rotator)
        return analysis.strip()
        
    except Exception as e:
        logger.warning(f"[REPORT] Subtask analysis failed for '{task}': {e}")
        return f"Analysis for '{task}' could not be completed due to processing error."


async def synthesize_comprehensive_report(instructions: str, cot_plan: Dict[str, Any], 
                                        detailed_analysis: Dict[str, Any], filename: str, 
                                        report_words: int, gemini_rotator, nvidia_rotator) -> str:
    """Synthesize the detailed analysis into a comprehensive, well-structured report."""
    
    # Prepare synthesis materials
    analysis_summary = ""
    for section_title, section_data in detailed_analysis.items():
        analysis_summary += f"\n## {section_title}\n"
        analysis_summary += f"Purpose: {section_data.get('purpose', '')}\n\n"
        
        for subtask_result in section_data.get("subtask_results", []):
            analysis_summary += f"### {subtask_result.get('task', '')}\n"
            analysis_summary += f"{subtask_result.get('analysis', '')}\n\n"
    
    reasoning_flow = cot_plan.get("reasoning_flow", [])
    flow_text = "\n".join([f"{i+1}. {step}" for i, step in enumerate(reasoning_flow)])
    
    sys_prompt = f"""You are an expert report writer synthesizing detailed analysis into a comprehensive report.

Your task is to create a well-structured, professional report that:
1. Follows the planned reasoning flow: {flow_text}
2. Integrates all detailed analyses seamlessly
3. Maintains logical flow and coherence
4. Provides clear, actionable insights
5. Uses proper academic/professional formatting
6. Targets approximately {report_words} words

Structure the report with:
- Clear section headings
- Logical progression of ideas
- Smooth transitions between sections
- Proper citations and references
- Executive summary or key takeaways
- Conclusion with actionable insights

Write in a professional, analytical tone suitable for business or academic contexts."""

    user_prompt = f"""USER REQUEST: {instructions}

DETAILED ANALYSIS TO SYNTHESIZE:
{analysis_summary}

REASONING FLOW TO FOLLOW:
{flow_text}

Create a comprehensive report that addresses the user's request by synthesizing all the detailed analysis above."""

    try:
        # Use Gemini Pro for final synthesis (better for long-form content)
        selection = {"provider": "gemini", "model": "gemini-2.5-pro"}
        report = await generate_answer_with_model(selection, sys_prompt, user_prompt, gemini_rotator, nvidia_rotator)
        
        logger.info(f"[REPORT] Comprehensive report synthesized, length: {len(report)} characters")
        return report
        
    except Exception as e:
        logger.error(f"[REPORT] Report synthesis failed: {e}")
        # Fallback: simple concatenation
        fallback_report = f"# Report: {instructions}\n\n"
        fallback_report += analysis_summary
        fallback_report += f"\n\n## Conclusion\n\nThis report addresses: {instructions}"
        return fallback_report


