# routes/reports.py
import os
from datetime import datetime
from typing import List, Dict, Tuple, Any
from fastapi import Form, HTTPException

from helpers.setup import app, rag, logger, embedder, gemini_rotator, nvidia_rotator
from .search import build_web_context
# Removed: enhance_instructions_with_memory - now handled by conversation manager
from helpers.models import ReportResponse, StatusUpdateResponse
from utils.service.common import trim_text
from utils.api.router import select_model, generate_answer_with_model
from utils.analytics import get_analytics_tracker
from helpers.coder import generate_code_artifacts, extract_structured_code
from helpers.diagram import should_generate_mermaid, generate_mermaid_diagram


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
    
    # Initialize memory system
    from memo.core import get_memory_system
    memory = get_memory_system()
    
    logger.info("[REPORT] User Q/report: %s", trim_text(instructions, 15).replace("\n", " "))
    
    # Update status: Receiving request
    update_report_status(session_id, "receiving", "Receiving request...", 5)
    
    # Get smart context with conversation management
    try:
        recent_context, semantic_context, context_metadata = await memory.get_smart_context(
            user_id, instructions, nvidia_rotator, project_id, "report"
        )
        logger.info(f"[REPORT] Smart context retrieved: recent={len(recent_context)}, semantic={len(semantic_context)}")
        
        # Check for context switch
        context_switch_info = await memory.handle_context_switch(user_id, instructions, nvidia_rotator)
        if context_switch_info.get("is_context_switch", False):
            logger.info(f"[REPORT] Context switch detected (confidence: {context_switch_info.get('confidence', 0):.2f})")
    except Exception as e:
        logger.warning(f"[REPORT] Smart context failed, using fallback: {e}")
        recent_context, semantic_context = "", ""
        context_metadata = {}
    
    # Use enhanced instructions from smart context if available
    enhanced_instructions = context_metadata.get("enhanced_input", instructions)
    memory_context = recent_context + "\n\n" + semantic_context if recent_context or semantic_context else ""
    logger.info(f"[REPORT] Enhanced instructions with memory context: {len(memory_context)} chars")
    
    files_list = rag.list_files(user_id=user_id, project_id=project_id)
    filenames_ci = {f.get("filename", "").lower(): f.get("filename") for f in files_list}
    eff_name = filenames_ci.get(filename.lower(), filename)
    doc_sum = rag.get_file_summary(user_id=user_id, project_id=project_id, filename=eff_name)
    if not doc_sum:
        raise HTTPException(404, detail="No summary found for that file.")

    query_text = f"Comprehensive report for {eff_name}"
    if enhanced_instructions.strip():
        query_text = f"{enhanced_instructions} {eff_name}"
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
        
        # Use enhanced instructions for better web search
        web_context_block, web_sources_meta = await build_web_context(
            enhanced_instructions or query_text, max_web=max_web, top_k=12, status_callback=web_status_callback
        )
    file_summary = doc_sum.get("summary", "")

    # Step 1: Chain of Thought Planning with NVIDIA
    logger.info("[REPORT] Starting CoT planning phase")
    update_report_status(session_id, "planning", "Planning action...", 25)
    
    # Track report agent usage
    tracker = get_analytics_tracker()
    if tracker:
        await tracker.track_agent_usage(
            user_id=user_id,
            agent_name="report",
            action="generate_report",
            context="report_generation",
            metadata={"project_id": project_id, "session_id": session_id, "filename": filename}
        )
    
    # Use enhanced instructions for better CoT planning
    cot_plan = await generate_cot_plan(enhanced_instructions, file_summary, context_text, web_context_block, nvidia_rotator, gemini_rotator, user_id)
    # Track planning agent
    try:
        tracker = get_analytics_tracker()
        if tracker:
            await tracker.track_agent_usage(
                user_id=user_id,
                agent_name="planning",
                action="plan_report",
                context="report_planning",
                metadata={"project_id": project_id, "session_id": session_id}
            )
    except Exception:
        pass
    
    # Step 2: Execute detailed subtasks based on CoT plan
    logger.info("[REPORT] Executing detailed subtasks")
    update_report_status(session_id, "processing", "Processing data...", 40)
    detailed_analysis = await execute_detailed_subtasks(cot_plan, context_text, web_context_block, eff_name, nvidia_rotator, gemini_rotator, user_id)
    
    # Step 3: Synthesize comprehensive report from detailed analysis
    logger.info("[REPORT] Synthesizing comprehensive report")
    update_report_status(session_id, "thinking", "Thinking solution...", 60)
    # Use enhanced instructions for better report synthesis
    comprehensive_report = await synthesize_comprehensive_report(
        enhanced_instructions, cot_plan, detailed_analysis, eff_name, report_words, gemini_rotator, nvidia_rotator, user_id
    )
    # Track synthesis (report agent)
    try:
        tracker = get_analytics_tracker()
        if tracker:
            await tracker.track_agent_usage(
                user_id=user_id,
                agent_name="report",
                action="synthesize_report",
                context="report_synthesis",
                metadata={"project_id": project_id, "session_id": session_id}
            )
    except Exception:
        pass
    
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
async def generate_cot_plan(instructions: str, file_summary: str, context_text: str, web_context: str, nvidia_rotator, gemini_rotator, user_id: str = "") -> Dict[str, Any]:
    """Generate a detailed Chain of Thought plan for report generation using NVIDIA."""
    sys_prompt = """You are an expert report planner. Create a comprehensive plan for generating a detailed, professional report.

Analyze the user's request and create a structured plan with:
1. Key requirements and focus areas
2. Logical report sections with specific subtasks
3. Information extraction needs and reasoning flow
4. Cross-referencing and synthesis strategies

Return a JSON object with this structure:
{
  "analysis": {
    "user_intent": "What the user wants to know",
    "key_requirements": ["requirement1", "requirement2", "requirement3"],
    "complexity_level": "basic|intermediate|advanced|expert",
    "focus_areas": ["area1", "area2", "area3"],
    "target_audience": "academic|business|technical|general",
    "report_scope": "comprehensive|focused|executive_summary"
  },
  "report_structure": {
    "sections": [
      {
        "title": "Section Title",
        "purpose": "Why this section is needed",
        "priority": "critical|important|supporting",
        "subtasks": [
          {
            "task": "Specific task description",
            "reasoning": "Why this task is important",
            "sources_needed": ["local", "web", "both"],
            "depth": "surface|detailed|comprehensive",
            "sub_actions": ["action1", "action2"],
            "expected_output": "What this produces",
            "quality_checks": ["check1", "check2"]
          }
        ]
      }
    ]
  },
  "reasoning_flow": [
    "Step 1: Analyze materials and extract key insights",
    "Step 2: Evaluate evidence and identify patterns",
    "Step 3: Synthesize findings and develop arguments",
    "Step 4: Create comprehensive conclusions"
  ],
  "synthesis_strategy": {
    "cross_referencing": "Connect information across sections",
    "evidence_integration": "Weave together different source types",
    "argument_development": "Build compelling narrative",
    "conclusion_synthesis": "Create powerful conclusion"
  }
}"""

    user_prompt = f"""USER REQUEST: {instructions}

MATERIALS:
FILE SUMMARY: {file_summary[:800]}

DOCUMENT CONTEXT: {context_text[:1500]}

WEB CONTEXT: {web_context[:1000] if web_context else "No web context available"}

Create a detailed plan for this report."""

    try:
        # Use Gemini for CoT planning since it's more reliable for complex JSON generation
        selection = {"provider": "gemini", "model": "gemini-2.5-flash"}
        logger.info(f"[REPORT] Starting CoT API call with model: {selection['model']}")
        logger.info(f"[REPORT] System prompt length: {len(sys_prompt)}")
        logger.info(f"[REPORT] User prompt length: {len(user_prompt)}")
        
        response = await generate_answer_with_model(selection, sys_prompt, user_prompt, gemini_rotator, nvidia_rotator, user_id, "report_planning")
        
        # Parse JSON response
        import json
        json_text = response.strip()
        logger.info(f"[REPORT] Raw CoT response length: {len(json_text)}")
        logger.info(f"[REPORT] Raw CoT response preview: {json_text[:200]}...")
        logger.info(f"[REPORT] Raw CoT response full: {json_text}")
        
        if json_text.startswith('```json'):
            json_text = json_text[7:-3].strip()
        elif json_text.startswith('```'):
            json_text = json_text[3:-3].strip()
        
        if not json_text:
            raise ValueError("Empty response from model")
        
        plan = json.loads(json_text)
        logger.info(f"[REPORT] CoT plan generated with {len(plan.get('report_structure', {}).get('sections', []))} sections")
        return plan
        
    except Exception as e:
        logger.warning(f"[REPORT] CoT planning failed: {e}")
        # Try a simpler fallback approach
        try:
            logger.info("[REPORT] Attempting simplified CoT planning")
            simple_sys_prompt = """You are a report planner. Create a structured plan for a report.

Return a JSON object with this structure:
{
  "analysis": {
    "user_intent": "What the user wants to know",
    "key_requirements": ["requirement1", "requirement2"],
    "complexity_level": "intermediate",
    "focus_areas": ["area1", "area2"],
    "target_audience": "general",
    "report_scope": "focused"
  },
  "report_structure": {
    "sections": [
      {
        "title": "Introduction",
        "purpose": "Provide overview and context",
        "priority": "important",
        "subtasks": [
          {
            "task": "Summarize key points and background",
            "reasoning": "Set foundation for analysis",
            "sources_needed": ["local"],
            "depth": "detailed",
            "sub_actions": ["Extract main themes", "Identify key concepts"],
            "expected_output": "Clear introduction with context",
            "quality_checks": ["completeness", "clarity"]
          }
        ]
      },
      {
        "title": "Main Analysis", 
        "purpose": "Address user's specific request",
        "priority": "critical",
        "subtasks": [
          {
            "task": "Detailed analysis of requested topics",
            "reasoning": "Core content addressing user needs",
            "sources_needed": ["local"],
            "depth": "comprehensive",
            "sub_actions": ["Analyze evidence", "Develop arguments", "Draw conclusions"],
            "expected_output": "Thorough analysis with insights",
            "quality_checks": ["accuracy", "depth", "relevance"]
          }
        ]
      },
      {
        "title": "Conclusion",
        "purpose": "Synthesize findings and provide closure", 
        "priority": "important",
        "subtasks": [
          {
            "task": "Summarize key insights and recommendations",
            "reasoning": "Provide clear closure and next steps",
            "sources_needed": ["local"],
            "depth": "detailed",
            "sub_actions": ["Synthesize findings", "Highlight key takeaways"],
            "expected_output": "Clear conclusion with actionable insights",
            "quality_checks": ["completeness", "actionability"]
          }
        ]
      }
    ]
  },
  "reasoning_flow": [
    "Step 1: Analyze materials and extract key insights",
    "Step 2: Evaluate evidence and develop arguments", 
    "Step 3: Synthesize findings and create conclusions"
  ],
  "synthesis_strategy": {
    "cross_referencing": "Connect related information across sections",
    "evidence_integration": "Weave together different types of evidence",
    "argument_development": "Build logical narrative flow",
    "conclusion_synthesis": "Create compelling final synthesis"
  }
}"""

            simple_user_prompt = f"""USER REQUEST: {instructions}

FILE SUMMARY: {file_summary[:500]}

Create a simple plan for this report."""

            simple_selection = {"provider": "gemini", "model": "gemini-2.5-flash"}
            simple_response = await generate_answer_with_model(simple_selection, simple_sys_prompt, simple_user_prompt, gemini_rotator, nvidia_rotator, user_id, "report_planning_simple")
            simple_json_text = simple_response.strip()
            
            if simple_json_text.startswith('```json'):
                simple_json_text = simple_json_text[7:-3].strip()
            elif simple_json_text.startswith('```'):
                simple_json_text = simple_json_text[3:-3].strip()
            
            if simple_json_text:
                simple_plan = json.loads(simple_json_text)
                logger.info("[REPORT] Simplified CoT plan generated successfully")
                return simple_plan
        except Exception as simple_e:
            logger.warning(f"[REPORT] Simplified CoT planning also failed: {simple_e}")
        
        # Final fallback plan
        logger.info("[REPORT] Using hardcoded fallback plan")
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


async def execute_detailed_subtasks(cot_plan: Dict[str, Any], context_text: str, web_context: str, filename: str, nvidia_rotator, gemini_rotator, user_id: str = "") -> Dict[str, Any]:
    """Execute detailed analysis for each subtask with hierarchical section assignment and CoT references."""
    detailed_analysis = {}
    synthesis_strategy = cot_plan.get("synthesis_strategy", {})
    sections = cot_plan.get("report_structure", {}).get("sections", [])
    
    # Create hierarchical section structure with proper numbering
    section_number = 1
    subsection_number = 1
    agent_context = {}  # Store context from previous agents for CoT references
    
    import asyncio as _asyncio
    semaphore = _asyncio.Semaphore(4)  # limit concurrency to avoid provider rate limits

    async def _process_section(section, section_number_local, agent_context_shared):
        nonlocal subsection_number
        section_title = section.get("title", "Unknown Section")
        section_priority = section.get("priority", "important")
        section_id = f"{section_number_local}"
        section_analysis = {
            "section_id": section_id,
            "title": section_title,
            "purpose": section.get("purpose", ""),
            "priority": section_priority,
            "subtask_results": [],
            "section_synthesis": "",
            "agent_context": agent_context_shared.copy()
        }

        async def _process_subtask(subtask, subtask_index):
            async with semaphore:
                task = subtask.get("task", "")
                reasoning = subtask.get("reasoning", "")
                sources_needed = subtask.get("sources_needed", ["local"])
                depth = subtask.get("depth", "detailed")
                sub_actions = subtask.get("sub_actions", [])
                expected_output = subtask.get("expected_output", "")
                quality_checks = subtask.get("quality_checks", [])
                subsection_id = f"{section_number_local}.{subtask_index}"
                subtask_result = await analyze_subtask_with_cot_references(
                    subsection_id, task, reasoning, sources_needed, depth, sub_actions,
                    expected_output, quality_checks, context_text, web_context, filename,
                    agent_context_shared, nvidia_rotator, gemini_rotator, user_id
                )
                code_blocks = None
                if any(kw in (task.lower() + " " + reasoning.lower()) for kw in ["implement", "code", "function", "class", "api", "script", "module", "endpoint"]):
                    try:
                        logger.info(f"[REPORT] Triggering code generation for {subsection_id}")
                        code_markdown = await generate_code_artifacts(
                            subsection_id=subsection_id,
                            task=task,
                            reasoning=reasoning,
                            context_text=context_text,
                            web_context=web_context,
                            gemini_rotator=gemini_rotator,
                            nvidia_rotator=nvidia_rotator,
                            user_id=user_id
                        )
                        subtask_result = subtask_result + "\n\n" + code_markdown
                        try:
                            code_blocks = extract_structured_code(code_markdown)
                        except Exception as pe:
                            logger.warning(f"[REPORT] Failed to parse structured code for {subsection_id}: {pe}")
                            code_blocks = []
                    except Exception as ce:
                        logger.warning(f"[REPORT] Code generation failed for {subsection_id}: {ce}")
                agent_context_shared[f"{section_id}.{subtask_index}"] = {
                    "subsection_id": subsection_id,
                    "task": task,
                    "key_findings": extract_key_findings(subtask_result),
                    "evidence": extract_evidence(subtask_result),
                    "conclusions": extract_conclusions(subtask_result)
                }
                section_analysis["subtask_results"].append({
                    "subsection_id": subsection_id,
                    "task": task,
                    "reasoning": reasoning,
                    "depth": depth,
                    "sub_actions": sub_actions,
                    "expected_output": expected_output,
                    "quality_checks": quality_checks,
                    "analysis": subtask_result,
                    **({"code_blocks": code_blocks} if code_blocks is not None else {}),
                    "agent_context": agent_context_shared.copy()
                })

        subtask_tasks = []
        subtask_index = 1
        for subtask in section.get("subtasks", []):
            subtask_tasks.append(_process_subtask(subtask, subtask_index))
            subtask_index += 1
        if subtask_tasks:
            await _asyncio.gather(*subtask_tasks)

        section_synthesis = await synthesize_section_with_cot_references(
            section_analysis, synthesis_strategy, agent_context_shared, nvidia_rotator, gemini_rotator, user_id
        )
        section_analysis["section_synthesis"] = section_synthesis
        agent_context_shared[f"section_{section_id}"] = {
            "section_id": section_id,
            "title": section_title,
            "key_insights": extract_key_insights(section_synthesis),
            "cross_references": extract_cross_references(section_synthesis)
        }
        return section_title, section_analysis

    section_tasks = []
    for section in sections:
        section_tasks.append(_process_section(section, section_number, agent_context))
        section_number += 1
    if section_tasks:
        results = await _asyncio.gather(*section_tasks)
        for title, analysis in results:
            detailed_analysis[title] = analysis
    
    
    logger.info(f"[REPORT] Completed hierarchical analysis for {len(detailed_analysis)} sections with CoT references")
    return detailed_analysis


async def analyze_subtask_with_cot_references(subsection_id: str, task: str, reasoning: str, sources_needed: List[str], 
                                             depth: str, sub_actions: List[str], expected_output: str, quality_checks: List[str],
                                             context_text: str, web_context: str, filename: str, agent_context: Dict[str, Any],
                                             nvidia_rotator, gemini_rotator, user_id: str = "") -> str:
    """Analyze a specific subtask with comprehensive detail, CoT references, and hierarchical context."""
    
    # Select appropriate context based on sources_needed
    selected_context = ""
    if "local" in sources_needed and "web" in sources_needed:
        selected_context = f"DOCUMENT CONTEXT:\n{context_text}\n\nWEB CONTEXT:\n{web_context}"
    elif "local" in sources_needed:
        selected_context = f"DOCUMENT CONTEXT:\n{context_text}"
    elif "web" in sources_needed:
        selected_context = f"WEB CONTEXT:\n{web_context}"
    
    # Build CoT references from previous agents
    cot_references = build_cot_references(agent_context, subsection_id)
    
    # Enhanced depth instructions with hierarchical context
    depth_instructions = {
        "surface": "Provide a brief, high-level analysis with key points and references to previous work",
        "detailed": "Provide a thorough, well-reasoned analysis with specific examples, evidence, clear explanations, and integration with previous findings",
        "comprehensive": "Provide an exhaustive, rigorous analysis with deep insights, multiple perspectives, extensive evidence, and sophisticated integration with all previous work",
        "exhaustive": "Provide the most comprehensive analysis possible with exhaustive detail, multiple angles, critical evaluation, extensive supporting evidence, and advanced synthesis with all previous findings"
    }
    
    sub_actions_text = "\n".join([f"- {action}" for action in sub_actions]) if sub_actions else "No specific sub-actions defined"
    quality_checks_text = "\n".join([f"- {check}" for check in quality_checks]) if quality_checks else "No specific quality checks defined"
    
    sys_prompt = f"""You are an expert analyst performing comprehensive research as part of a hierarchical report generation system.

SUBSECTION ID: {subsection_id}
TASK: {task}

REASONING: {reasoning}

DEPTH REQUIREMENT: {depth_instructions.get(depth, "Provide detailed analysis")}

CHAIN OF THOUGHT CONTEXT:
{cot_references}

SUB-ACTIONS TO PERFORM:
{sub_actions_text}

EXPECTED OUTPUT: {expected_output}

QUALITY CHECKS:
{quality_checks_text}

CRITICAL REQUIREMENTS:
- Build upon and reference previous agents' work where relevant
- Extract specific, relevant information with precision
- Provide clear, detailed explanations and insights
- Support all claims with concrete evidence from the materials
- Maintain the highest analytical rigor and objectivity
- Be comprehensive and thorough while remaining focused
- Follow the sub-actions systematically
- Meet the expected output requirements
- Pass all quality checks
- Integrate findings with previous work through CoT references
- Create detailed, comprehensive content (not just summaries)

WHEN THE TASK IMPLIES IMPLEMENTATION OR CODING:
- Propose concrete code solutions using fenced code blocks with proper language tags
- Organize code by files and paths (e.g., ```python
# File: utils/service/new_module.py
...
```)
- Keep code self-contained and runnable; include imports and minimal scaffolding if needed
- Add brief explanation after each code block (what/why), linking back to requirements

WHEN VISUAL STRUCTURE HELPS (flows/architecture/timelines):
- Include a Mermaid diagram as a fenced ```mermaid block when genuinely helpful (not always)
- Prefer sequence diagrams for flows, class diagrams for structure, graph diagrams for dependencies

Return only the comprehensive analysis, no meta-commentary or introductory phrases."""

    user_prompt = f"""SUBSECTION {subsection_id}: {task}

MATERIALS:
{selected_context}

CHAIN OF THOUGHT REFERENCES:
{cot_references}

Perform the comprehensive analysis as specified, following all sub-actions, meeting quality standards, and building upon previous work through CoT references."""

    try:
        selection = {"provider": "gemini", "model": "gemini-2.5-flash"}
        analysis = await generate_answer_with_model(selection, sys_prompt, user_prompt, gemini_rotator, nvidia_rotator, user_id, "report_analysis")
        return analysis.strip()
        
    except Exception as e:
        logger.warning(f"[REPORT] Comprehensive subtask analysis with CoT failed for '{subsection_id}': {e}")
        return f"Analysis for '{subsection_id}: {task}' could not be completed due to processing error."


async def analyze_subtask_comprehensive(task: str, reasoning: str, sources_needed: List[str], depth: str,
                                      sub_actions: List[str], expected_output: str, quality_checks: List[str],
                                      context_text: str, web_context: str, filename: str, nvidia_rotator, gemini_rotator, user_id: str = "") -> str:
    """Legacy function for backward compatibility."""
    return await analyze_subtask_with_cot_references(
        "1.1", task, reasoning, sources_needed, depth, sub_actions, expected_output, 
        quality_checks, context_text, web_context, filename, {}, nvidia_rotator, gemini_rotator, user_id
    )


async def synthesize_section_with_cot_references(section_analysis: Dict[str, Any], synthesis_strategy: Dict[str, str], 
                                               agent_context: Dict[str, Any], nvidia_rotator, gemini_rotator, user_id: str = "") -> str:
    """Synthesize all subtask results within a section with CoT references and hierarchical context."""
    
    section_title = section_analysis.get("title", "Unknown Section")
    section_id = section_analysis.get("section_id", "1")
    section_purpose = section_analysis.get("purpose", "")
    subtask_results = section_analysis.get("subtask_results", [])
    
    # Build comprehensive CoT context for synthesis
    cot_context = build_synthesis_cot_context(agent_context, section_id)
    
    # Prepare detailed subtask summaries with hierarchical structure
    subtask_summaries = ""
    for result in subtask_results:
        subsection_id = result.get("subsection_id", "")
        task = result.get("task", "")
        analysis = result.get("analysis", "")
        subtask_summaries += f"\n### {subsection_id}: {task}\n{analysis}\n"
    
    sys_prompt = f"""You are an expert synthesis analyst creating comprehensive, hierarchical section synthesis.

SECTION {section_id}: {section_title}
PURPOSE: {section_purpose}

CHAIN OF THOUGHT CONTEXT:
{cot_context}

SYNTHESIS STRATEGY:
- Cross-referencing: {synthesis_strategy.get('cross_referencing', 'Connect related information across subtasks')}
- Evidence integration: {synthesis_strategy.get('evidence_integration', 'Weave together different types of evidence')}
- Argument development: {synthesis_strategy.get('argument_development', 'Build a compelling narrative flow')}

CRITICAL REQUIREMENTS:
- Create logical flow between subtask results with hierarchical structure
- Identify key themes and patterns across all subsections
- Highlight important insights and findings with cross-references
- Ensure comprehensive coverage of the section purpose
- Maintain analytical rigor and coherence throughout
- Build toward a strong section conclusion
- Reference and build upon previous work through CoT
- Create detailed, comprehensive content (not summaries)
- Use proper hierarchical numbering and structure

CODING ARTIFACTS:
- If subsections include code, consolidate into a coherent file-by-file set
- Ensure consistent naming, imports, and integration across files
- Provide short rationale per file and note relationships (e.g., section 2.1 uses helper from 1.2)

DIAGRAMS:
- If helpful, include a single Mermaid diagram summarizing relationships across subsections

Return only the synthesized analysis with proper hierarchical structure, no meta-commentary."""

    user_prompt = f"""SECTION {section_id}: {section_title}

CHAIN OF THOUGHT CONTEXT:
{cot_context}

DETAILED SUBTASK ANALYSES:
{subtask_summaries}

Synthesize these analyses into a comprehensive, coherent section with proper hierarchical structure that fulfills the section purpose and builds upon previous work."""

    try:
        selection = {"provider": "gemini", "model": "gemini-2.5-flash"}
        synthesis = await generate_answer_with_model(selection, sys_prompt, user_prompt, gemini_rotator, nvidia_rotator, user_id, "report_synthesis")
        return synthesis.strip()
        
    except Exception as e:
        logger.warning(f"[REPORT] Section synthesis with CoT failed for '{section_title}': {e}")
        return f"Synthesis for '{section_title}' could not be completed due to processing error."


async def synthesize_section_analysis(section_analysis: Dict[str, Any], synthesis_strategy: Dict[str, str], nvidia_rotator, gemini_rotator, user_id: str = "") -> str:
    """Legacy function for backward compatibility."""
    return await synthesize_section_with_cot_references(
        section_analysis, synthesis_strategy, {}, nvidia_rotator, gemini_rotator, user_id
    )


async def synthesize_comprehensive_report(instructions: str, cot_plan: Dict[str, Any], 
                                        detailed_analysis: Dict[str, Any], filename: str, 
                                        report_words: int, gemini_rotator, nvidia_rotator, user_id: str = "") -> str:
    """Synthesize the detailed analysis into a comprehensive, hierarchical report with CoT integration."""
    
    # Prepare hierarchical synthesis materials with proper section numbering
    analysis_summary = ""
    synthesis_strategy = cot_plan.get("synthesis_strategy", {})
    
    # Build comprehensive CoT context from all sections
    all_agent_context = {}
    for section_title, section_data in detailed_analysis.items():
        section_id = section_data.get("section_id", "1")
        all_agent_context[f"section_{section_id}"] = {
            "section_id": section_id,
            "title": section_title,
            "key_insights": extract_key_insights(section_data.get("section_synthesis", "")),
            "cross_references": extract_cross_references(section_data.get("section_synthesis", ""))
        }
    
    # Create hierarchical structure with proper numbering
    section_number = 1
    for section_title, section_data in detailed_analysis.items():
        section_id = section_data.get("section_id", str(section_number))
        analysis_summary += f"\n## {section_number}. {section_title}\n"
        analysis_summary += f"Purpose: {section_data.get('purpose', '')}\n"
        analysis_summary += f"Priority: {section_data.get('priority', 'important')}\n\n"
        
        # Include section synthesis with hierarchical structure
        section_synthesis = section_data.get("section_synthesis", "")
        if section_synthesis:
            analysis_summary += f"### Section {section_number} Synthesis:\n{section_synthesis}\n\n"
        
        # Include detailed subtask results with proper subsection numbering
        subtask_number = 1
        for subtask_result in section_data.get("subtask_results", []):
            subsection_id = subtask_result.get("subsection_id", f"{section_number}.{subtask_number}")
            task = subtask_result.get("task", "")
            analysis = subtask_result.get("analysis", "")
            
            analysis_summary += f"### {subsection_id} {task}\n"
            analysis_summary += f"Depth: {subtask_result.get('depth', 'detailed')}\n"
            analysis_summary += f"Analysis: {analysis}\n\n"
            subtask_number += 1
        
        section_number += 1
    
    # Build comprehensive CoT context for final synthesis
    final_cot_context = build_final_synthesis_cot_context(all_agent_context)
    
    reasoning_flow = cot_plan.get("reasoning_flow", [])
    flow_text = "\n".join([f"{i+1}. {step}" for i, step in enumerate(reasoning_flow)])
    
    # Enhanced synthesis strategy
    cross_referencing = synthesis_strategy.get("cross_referencing", "Connect related information across sections")
    evidence_integration = synthesis_strategy.get("evidence_integration", "Weave together different source types")
    argument_development = synthesis_strategy.get("argument_development", "Build a compelling narrative")
    conclusion_synthesis = synthesis_strategy.get("conclusion_synthesis", "Create a powerful conclusion")
    
    sys_prompt = f"""You are an expert report writer creating a comprehensive, hierarchical report with advanced Chain of Thought integration.

Your task is to create a well-structured, authoritative report that:
1. Follows the planned reasoning flow: {flow_text}
2. Integrates all detailed analyses seamlessly with sophisticated synthesis
3. Maintains logical flow and coherence throughout with proper hierarchical structure
4. Provides clear, actionable insights and recommendations
5. Uses proper academic/professional formatting with section/subsection numbering
6. Targets approximately {report_words} words with comprehensive coverage
7. Demonstrates analytical rigor and depth
8. Integrates Chain of Thought references throughout

SYNTHESIS REQUIREMENTS:
- Cross-referencing: {cross_referencing}
- Evidence integration: {evidence_integration}
- Argument development: {argument_development}
- Conclusion synthesis: {conclusion_synthesis}

HIERARCHICAL STRUCTURE REQUIREMENTS:
- Proper section numbering (1, 2, 3, etc.)
- Proper subsection numbering (1.1, 1.2, 2.1, 2.2, etc.)
- Executive summary with key findings
- Clear section headings with logical progression
- Smooth transitions between sections with cross-references
- Proper citations and references throughout
- Data-driven insights and evidence-based conclusions
- Actionable recommendations where appropriate
- Professional, analytical tone
- Chain of Thought integration showing how sections build upon each other

CODING GENERATION (WHEN REQUESTED/IMPLIED):
- Produce file-by-file code blocks with file path headers
- Ensure code compiles and integrates across files (imports, shared types)
- For each file, include a short explanation and why this design
- Link code back to the report sections/subsections where it originates

DIAGRAMS (WHEN HELPFUL):
- Include concise Mermaid diagrams to visualize flows/architecture
- Use fenced ```mermaid blocks so the UI can render them

CRITICAL: Start the report immediately with substantive content. Do NOT include meta-commentary like "Here is a comprehensive report..." or "Of course, here is...". Begin directly with the report title and content."""

    user_prompt = f"""USER REQUEST: {instructions}

CHAIN OF THOUGHT CONTEXT:
{final_cot_context}

COMPREHENSIVE HIERARCHICAL ANALYSIS TO SYNTHESIZE:
{analysis_summary}

REASONING FLOW TO FOLLOW:
{flow_text}

SYNTHESIS STRATEGY:
- Cross-referencing: {cross_referencing}
- Evidence integration: {evidence_integration}
- Argument development: {argument_development}
- Conclusion synthesis: {conclusion_synthesis}

Create a comprehensive, authoritative report with proper hierarchical structure that addresses the user's request by synthesizing all the detailed analysis above. Use proper section/subsection numbering and integrate Chain of Thought references throughout. Begin immediately with the report title and substantive content."""

    try:
        # Use Gemini Pro for final synthesis (better for long-form content)
        selection = {"provider": "gemini", "model": "gemini-2.5-pro"}
        report = await generate_answer_with_model(selection, sys_prompt, user_prompt, gemini_rotator, nvidia_rotator, user_id, "report_final")
        
        # Post-process to remove any remaining meta-commentary and ensure proper formatting
        report = remove_meta_commentary(report)
        report = ensure_hierarchical_structure(report)
        
        # Fix heading numbering using AI
        report = await fix_heading_numbering(report, nvidia_rotator)

        # Optionally enrich with Mermaid diagrams when useful
        try:
            if should_generate_mermaid(instructions, report):
                logger.info("[REPORT] Considering Mermaid diagram generation")
                diagram = await generate_mermaid_diagram(instructions, detailed_analysis, gemini_rotator, nvidia_rotator, user_id=user_id)
                if diagram:
                    report = ("## Diagrams\n\n" + "```mermaid\n" + diagram.strip() + "\n```\n\n" + report)
                else:
                    logger.info("[REPORT] Mermaid generation returned empty diagram")
        except Exception as me:
            logger.warning(f"[REPORT] Mermaid generation skipped: {me}")
        
        logger.info(f"[REPORT] Comprehensive hierarchical report synthesized, length: {len(report)} characters")
        return report
        
    except Exception as e:
        logger.error(f"[REPORT] Report synthesis failed: {e}")
        # Fallback: simple concatenation with hierarchical structure
        fallback_report = f"# {instructions}\n\n"
        fallback_report += analysis_summary
        fallback_report += f"\n\n## Conclusion\n\n{instructions}"
        return fallback_report

async def generate_code_artifacts(subsection_id: str, task: str, reasoning: str, context_text: str, web_context: str, gemini_rotator, nvidia_rotator, user_id: str = "") -> str:
    """Generate code (files-by-files) with explanations using Gemini Pro, grounded in context."""
    system_prompt = (
        "You are a senior software engineer. Generate production-quality code that fulfills the TASK,\n"
        "grounded strictly in the provided CONTEXT.\n"
        "Rules:\n"
        "- Output Markdown with multiple code blocks by file, each preceded by a short heading 'File: path'.\n"
        "- Prefer clear, minimal dependencies.\n"
        "- After each code block, add a concise explanation of design decisions.\n"
        "- If APIs/endpoints are referenced, ensure coherent naming across files.\n"
        "- Do not include meta text like 'Here is the code'. Start with the first file heading."
    )
    user_prompt = (
        f"SUBSECTION {subsection_id}\nTASK: {task}\nREASONING: {reasoning}\n\n"
        f"CONTEXT (DOCUMENT):\n{trim_text(context_text, 6000)}\n\n"
        f"CONTEXT (WEB):\n{trim_text(web_context, 3000)}\n\n"
        "Produce the code files and explanations as specified."
    )
    selection = {"provider": "gemini", "model": "gemini-2.5-pro"}
    code_md = await generate_answer_with_model(selection, system_prompt, user_prompt, gemini_rotator, nvidia_rotator, user_id, "report_coding")
    return code_md.strip()

def should_generate_mermaid(instructions: str, report_text: str) -> bool:
    """Heuristic to decide whether to include a Mermaid diagram."""
    intent = (instructions or "") + " " + (report_text or "")
    keywords = ("architecture", "workflow", "data flow", "sequence", "state machine", "er diagram", "dependency", "pipeline", "diagram")
    if any(k in intent.lower() for k in keywords):
        return True
    return False

async def generate_mermaid_diagram(instructions: str, detailed_analysis: Dict[str, Any], gemini_rotator, nvidia_rotator, user_id: str = "") -> str:
    """Use NVIDIA_LARGE (GPT-OSS) to synthesize a concise Mermaid diagram when helpful."""
    try:
        # Build a compact overview context from section titles and key insights
        overview = []
        for title, data in detailed_analysis.items():
            section_id = data.get("section_id", "")
            insights = extract_key_insights(data.get("section_synthesis", ""))
            overview.append(f"{section_id} {title}: " + "; ".join(insights))
        context_overview = "\n".join(overview)

        sys_prompt = (
            "You are an expert technical illustrator. Create a single concise Mermaid diagram that best conveys the core structure\n"
            "(e.g., flowchart, sequence, class, state, or ER) based on the provided CONTEXT.\n"
            "Rules:\n"
            "- Return Mermaid code only (no backticks, no explanations).\n"
            "- Prefer flowchart or sequence if uncertain.\n"
            "- Keep node labels short but meaningful.\n"
            "- Ensure Mermaid syntax is valid."
        )
        user_prompt = f"INSTRUCTIONS:\n{instructions}\n\nCONTEXT OVERVIEW:\n{context_overview}"

        # Use NVIDIA_LARGE for diagram synthesis
        selection = {"provider": "nvidia_large", "model": os.getenv("NVIDIA_LARGE", "openai/gpt-oss-120b")}
        diagram = await generate_answer_with_model(selection, sys_prompt, user_prompt, gemini_rotator, nvidia_rotator, user_id, "report_diagram")
        # Strip accidental code fences
        diagram = diagram.strip()
        if diagram.startswith("```"):
            diagram = diagram.strip('`')
            # Attempt to remove language header if present
            if diagram.lower().startswith("mermaid"):
                diagram = "\n".join(diagram.splitlines()[1:])
        return diagram
    except Exception as e:
        logger.warning(f"[REPORT] Mermaid generation error: {e}")
        return ""


def build_cot_references(agent_context: Dict[str, Any], current_subsection_id: str) -> str:
    """Build Chain of Thought references from previous agents' work."""
    if not agent_context:
        return "No previous agent context available."
    
    references = []
    for key, context in agent_context.items():
        if key.startswith("section_"):
            section_id = context.get("section_id", "")
            title = context.get("title", "")
            key_insights = context.get("key_insights", [])
            cross_refs = context.get("cross_references", [])
            
            if key_insights or cross_refs:
                ref_text = f"Section {section_id} ({title}):"
                if key_insights:
                    ref_text += f"\n  Key Insights: {', '.join(key_insights[:3])}"
                if cross_refs:
                    ref_text += f"\n  Cross-references: {', '.join(cross_refs[:2])}"
                references.append(ref_text)
        else:
            # Individual subsection context
            subsection_id = context.get("subsection_id", "")
            task = context.get("task", "")
            key_findings = context.get("key_findings", [])
            evidence = context.get("evidence", [])
            
            if key_findings or evidence:
                ref_text = f"{subsection_id} ({task}):"
                if key_findings:
                    ref_text += f"\n  Key Findings: {', '.join(key_findings[:2])}"
                if evidence:
                    ref_text += f"\n  Evidence: {', '.join(evidence[:2])}"
                references.append(ref_text)
    
    if references:
        return "PREVIOUS AGENT WORK TO BUILD UPON:\n" + "\n".join(references)
    else:
        return "No relevant previous agent work to reference."


def build_synthesis_cot_context(agent_context: Dict[str, Any], current_section_id: str) -> str:
    """Build comprehensive CoT context for section synthesis."""
    if not agent_context:
        return "No previous context available for synthesis."
    
    context_parts = []
    
    # Include previous section insights
    for key, context in agent_context.items():
        if key.startswith("section_"):
            section_id = context.get("section_id", "")
            if section_id != current_section_id:  # Don't include current section
                title = context.get("title", "")
                key_insights = context.get("key_insights", [])
                cross_refs = context.get("cross_references", [])
                
                if key_insights or cross_refs:
                    context_parts.append(f"Section {section_id} ({title}): {', '.join(key_insights[:3])}")
    
    # Include subsection context within current section
    current_subsections = []
    for key, context in agent_context.items():
        if not key.startswith("section_") and context.get("subsection_id", "").startswith(current_section_id):
            subsection_id = context.get("subsection_id", "")
            task = context.get("task", "")
            key_findings = context.get("key_findings", [])
            current_subsections.append(f"{subsection_id} ({task}): {', '.join(key_findings[:2])}")
    
    if current_subsections:
        context_parts.append(f"Current Section Subsections: {'; '.join(current_subsections)}")
    
    if context_parts:
        return "SYNTHESIS CONTEXT:\n" + "\n".join(context_parts)
    else:
        return "No relevant context available for synthesis."


def extract_key_findings(analysis_text: str) -> List[str]:
    """Extract key findings from analysis text."""
    # Simple extraction - could be enhanced with NLP
    sentences = analysis_text.split('.')
    findings = []
    for sentence in sentences[:5]:  # First 5 sentences
        sentence = sentence.strip()
        if len(sentence) > 20 and any(word in sentence.lower() for word in ['find', 'reveal', 'show', 'indicate', 'demonstrate', 'suggest']):
            findings.append(sentence[:100] + "..." if len(sentence) > 100 else sentence)
    return findings[:3]


def extract_evidence(analysis_text: str) -> List[str]:
    """Extract evidence from analysis text."""
    sentences = analysis_text.split('.')
    evidence = []
    for sentence in sentences[:5]:
        sentence = sentence.strip()
        if len(sentence) > 20 and any(word in sentence.lower() for word in ['data', 'evidence', 'research', 'study', 'analysis', 'results']):
            evidence.append(sentence[:100] + "..." if len(sentence) > 100 else sentence)
    return evidence[:3]


def extract_conclusions(analysis_text: str) -> List[str]:
    """Extract conclusions from analysis text."""
    sentences = analysis_text.split('.')
    conclusions = []
    for sentence in sentences[-3:]:  # Last 3 sentences
        sentence = sentence.strip()
        if len(sentence) > 20 and any(word in sentence.lower() for word in ['conclude', 'therefore', 'thus', 'consequently', 'indicates', 'suggests']):
            conclusions.append(sentence[:100] + "..." if len(sentence) > 100 else sentence)
    return conclusions[:2]


def extract_key_insights(synthesis_text: str) -> List[str]:
    """Extract key insights from section synthesis."""
    sentences = synthesis_text.split('.')
    insights = []
    for sentence in sentences[:5]:
        sentence = sentence.strip()
        if len(sentence) > 30:
            insights.append(sentence[:80] + "..." if len(sentence) > 80 else sentence)
    return insights[:3]


def extract_cross_references(synthesis_text: str) -> List[str]:
    """Extract cross-references from section synthesis."""
    sentences = synthesis_text.split('.')
    references = []
    for sentence in sentences:
        sentence = sentence.strip()
        if any(word in sentence.lower() for word in ['section', 'subsection', 'previous', 'earlier', 'above', 'below']):
            references.append(sentence[:60] + "..." if len(sentence) > 60 else sentence)
    return references[:2]


def build_final_synthesis_cot_context(all_agent_context: Dict[str, Any]) -> str:
    """Build comprehensive CoT context for final report synthesis."""
    if not all_agent_context:
        return "No previous context available for final synthesis."
    
    context_parts = []
    for key, context in all_agent_context.items():
        section_id = context.get("section_id", "")
        title = context.get("title", "")
        key_insights = context.get("key_insights", [])
        cross_refs = context.get("cross_references", [])
        
        if key_insights or cross_refs:
            context_parts.append(f"Section {section_id} ({title}): {', '.join(key_insights[:3])}")
    
    if context_parts:
        return "FINAL SYNTHESIS CONTEXT:\n" + "\n".join(context_parts)
    else:
        return "No relevant context available for final synthesis."


def ensure_hierarchical_structure(text: str) -> str:
    """Ensure the report has proper hierarchical structure with section/subsection numbering."""
    lines = text.split('\n')
    processed_lines = []
    section_counter = 1
    subsection_counter = 1
    current_section = None
    
    for line in lines:
        line = line.strip()
        if not line:
            processed_lines.append(line)
            continue
            
        # Check for main sections (## or #)
        if line.startswith('## ') or line.startswith('# '):
            # Reset subsection counter for new section
            subsection_counter = 1
            current_section = section_counter
            
            # Ensure proper section numbering
            if not line.startswith(f'# {section_counter}.') and not line.startswith(f'## {section_counter}.'):
                # Add section number if missing
                if line.startswith('# '):
                    line = f'# {section_counter}. {line[2:]}'
                elif line.startswith('## '):
                    line = f'## {section_counter}. {line[3:]}'
            
            processed_lines.append(line)
            section_counter += 1
            
        # Check for subsections (###)
        elif line.startswith('### '):
            if current_section is not None:
                # Ensure proper subsection numbering
                if not line.startswith(f'### {current_section}.{subsection_counter}'):
                    line = f'### {current_section}.{subsection_counter} {line[4:]}'
                subsection_counter += 1
            else:
                # If no main section yet, treat as section
                line = f'## {section_counter}. {line[4:]}'
                section_counter += 1
            
            processed_lines.append(line)
        else:
            processed_lines.append(line)
    
    return '\n'.join(processed_lines)


def remove_meta_commentary(text: str) -> str:
    """Remove common meta-commentary phrases from the beginning of reports."""
    meta_phrases = [
        "Of course. Here is a comprehensive report",
        "Here is a comprehensive report",
        "Of course, here is",
        "Here is",
        "I'll provide you with",
        "I will now provide",
        "Let me provide you with",
        "I can provide you with",
        "I'll create a comprehensive report",
        "I will create a comprehensive report",
        "Let me create a comprehensive report",
        "I can create a comprehensive report"
    ]
    
    text = text.strip()
    for phrase in meta_phrases:
        if text.startswith(phrase):
            text = text[len(phrase):].strip()
            # Remove any trailing periods and clean up
            if text.startswith("."):
                text = text[1:].strip()
            break
    
    return text


async def fix_heading_numbering(report: str, nvidia_rotator) -> str:
    """
    Extract headings from the report, use AI to re-number them properly, then apply the fixes.
    """
    try:
        import re
        from utils.api.router import generate_answer_with_model
        
        # Extract all headings from the report
        heading_pattern = r'^(#{1,6})\s*(.*)$'
        headings = []
        lines = report.split('\n')
        
        for i, line in enumerate(lines):
            match = re.match(heading_pattern, line.strip())
            if match:
                level = len(match.group(1))  # Number of # characters
                text = match.group(2).strip()
                # Remove existing numbering if present
                text = re.sub(r'^\d+\.?\s*', '', text)
                headings.append({
                    'line_number': i,
                    'level': level,
                    'text': text,
                    'original_line': line
                })
        
        if not headings:
            logger.info("[REPORT] No headings found for re-numbering")
            return report
        
        # Prepare headings for AI analysis
        headings_text = "\n".join([f"{h['level']}. {h['text']}" for h in headings])
        
        # Use AI to re-number headings properly
        sys_prompt = """You are an expert at structuring academic and technical documents. 
Your task is to analyze the headings from a report and provide proper hierarchical numbering.

Rules:
1. Main sections (level 1) should be numbered 1, 2, 3, etc.
2. Subsections (level 2) should be numbered 1.1, 1.2, 2.1, 2.2, etc.
3. Sub-subsections (level 3) should be numbered 1.1.1, 1.1.2, 2.1.1, etc.
4. Maintain logical hierarchy and proper nesting
5. Return ONLY the renumbered headings in the exact format: "level: new_number: heading_text"
6. One heading per line, no additional text or explanations"""

        user_prompt = f"""Analyze these headings and provide proper hierarchical numbering:

{headings_text}

Return the renumbered headings in the format: "level: new_number: heading_text" (one per line)"""
        
        # Use NVIDIA model for heading re-numbering
        selection = {"provider": "nvidia", "model": "meta/llama-3.1-8b-instruct"}
        response = await generate_answer_with_model(selection, sys_prompt, user_prompt, None, nvidia_rotator, user_id, "report_heading_fix")
        
        # Parse the AI response
        renumbered_headings = []
        for line in response.strip().split('\n'):
            line = line.strip()
            if ':' in line and line.count(':') >= 2:
                try:
                    parts = line.split(':', 2)
                    level = int(parts[0].strip())
                    new_number = parts[1].strip()
                    heading_text = parts[2].strip()
                    renumbered_headings.append({
                        'level': level,
                        'new_number': new_number,
                        'text': heading_text
                    })
                except (ValueError, IndexError):
                    logger.warning(f"[REPORT] Could not parse heading line: {line}")
                    continue
        
        if not renumbered_headings:
            logger.warning("[REPORT] AI heading re-numbering failed, using original headings")
            return report
        
        # Apply the re-numbered headings to the report
        updated_lines = lines.copy()
        heading_index = 0
        
        for i, line in enumerate(lines):
            match = re.match(heading_pattern, line.strip())
            if match and heading_index < len(renumbered_headings):
                level = len(match.group(1))
                new_heading = renumbered_headings[heading_index]
                
                # Create the new heading line
                hash_symbols = '#' * level
                new_line = f"{hash_symbols} {new_heading['new_number']}. {new_heading['text']}"
                updated_lines[i] = new_line
                heading_index += 1
        
        # Reconstruct the report
        fixed_report = '\n'.join(updated_lines)
        logger.info(f"[REPORT] Successfully re-numbered {len(renumbered_headings)} headings")
        return fixed_report
        
    except Exception as e:
        logger.warning(f"[REPORT] Heading re-numbering failed: {e}")
        return report


@app.post("/mermaid/fix")
async def fix_mermaid_syntax(
    mermaid_code: str = Form(...),
    error_message: str = Form(""),
    user_id: str = Form("system")
):
    """
    Fix Mermaid diagram syntax using AI for UI rendering.
    """
    try:
        from helpers.diagram import fix_mermaid_syntax_for_ui
        
        logger.info(f"[MERMAID] Fixing Mermaid syntax for UI")
        fixed_code = await fix_mermaid_syntax_for_ui(mermaid_code, error_message, user_id)
        
        return {
            "success": True,
            "fixed_code": fixed_code,
            "was_fixed": fixed_code != mermaid_code
        }
        
    except Exception as e:
        logger.error(f"[MERMAID] Failed to fix Mermaid syntax: {e}")
        return {
            "success": False,
            "error": str(e),
            "fixed_code": mermaid_code
        }


