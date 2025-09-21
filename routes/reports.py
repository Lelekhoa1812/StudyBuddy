# routes/reports.py
import os
from datetime import datetime
from typing import List, Dict, Tuple, Any
from fastapi import Form, HTTPException

from helpers.setup import app, rag, logger, embedder, gemini_rotator, nvidia_rotator
from .search import build_web_context
from memo.context import enhance_instructions_with_memory
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
    
    # Step 1: Retrieve and enhance prompt with conversation history FIRST
    from memo.core import get_memory_system
    memory = get_memory_system()
    enhanced_instructions, memory_context = await enhance_instructions_with_memory(
        user_id, instructions, memory, nvidia_rotator, embedder
    )
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
    # Use enhanced instructions for better CoT planning
    cot_plan = await generate_cot_plan(enhanced_instructions, file_summary, context_text, web_context_block, nvidia_rotator)
    
    # Step 2: Execute detailed subtasks based on CoT plan
    logger.info("[REPORT] Executing detailed subtasks")
    update_report_status(session_id, "processing", "Processing data...", 40)
    detailed_analysis = await execute_detailed_subtasks(cot_plan, context_text, web_context_block, eff_name, nvidia_rotator)
    
    # Step 3: Synthesize comprehensive report from detailed analysis
    logger.info("[REPORT] Synthesizing comprehensive report")
    update_report_status(session_id, "thinking", "Thinking solution...", 60)
    # Use enhanced instructions for better report synthesis
    comprehensive_report = await synthesize_comprehensive_report(
        enhanced_instructions, cot_plan, detailed_analysis, eff_name, report_words, gemini_rotator, nvidia_rotator
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
    sys_prompt = """You are an expert research analyst and report planner. Given a user's request and available materials, create a comprehensive plan for generating a detailed, professional report.

Your task is to:
1. Deeply analyze the user's request and identify ALL key requirements and sub-requirements
2. Break down the report into logical sections with detailed subtasks
3. Identify specific information extraction needs from each source type
4. Plan comprehensive reasoning flow and argument structure
5. Determine appropriate depth and rigor for each section
6. Create detailed sub-action plans for each major section
7. Plan cross-referencing and synthesis strategies
8. Identify potential gaps and additional research needs

Return a JSON object with this structure:
{
  "analysis": {
    "user_intent": "Detailed analysis of what the user really wants to know",
    "key_requirements": ["primary_requirement1", "secondary_requirement2", "implicit_requirement3"],
    "complexity_level": "basic|intermediate|advanced|expert",
    "focus_areas": ["primary_area1", "secondary_area2", "supporting_area3"],
    "target_audience": "academic|business|technical|general",
    "report_scope": "comprehensive|focused|executive_summary",
    "quality_standards": ["academic_rigor", "practical_applicability", "completeness"]
  },
  "report_structure": {
    "sections": [
      {
        "title": "Section Title",
        "purpose": "Detailed explanation of why this section is needed",
        "priority": "critical|important|supporting",
        "estimated_length": "short|medium|long",
        "subtasks": [
          {
            "task": "Specific, detailed task description",
            "reasoning": "Detailed explanation of why this task is important",
            "sources_needed": ["local", "web", "both"],
            "depth": "surface|detailed|comprehensive|exhaustive",
            "sub_actions": [
              "Specific action 1",
              "Specific action 2",
              "Specific action 3"
            ],
            "expected_output": "What this subtask should produce",
            "quality_checks": ["check1", "check2"]
          }
        ]
      }
    ]
  },
  "reasoning_flow": [
    "Step 1: Comprehensive analysis of...",
    "Step 2: Deep examination of...",
    "Step 3: Critical evaluation of...",
    "Step 4: Synthesis and integration of...",
    "Step 5: Final comprehensive conclusion..."
  ],
  "synthesis_strategy": {
    "cross_referencing": "How to connect information across sections",
    "evidence_integration": "How to weave together different source types",
    "argument_development": "How to build a compelling narrative",
    "conclusion_synthesis": "How to create a powerful conclusion"
  }
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
    synthesis_strategy = cot_plan.get("synthesis_strategy", {})
    
    for section in cot_plan.get("report_structure", {}).get("sections", []):
        section_title = section.get("title", "Unknown Section")
        section_priority = section.get("priority", "important")
        section_analysis = {
            "title": section_title,
            "purpose": section.get("purpose", ""),
            "priority": section_priority,
            "subtask_results": [],
            "section_synthesis": ""
        }
        
        # Process each subtask with enhanced detail
        for subtask in section.get("subtasks", []):
            task = subtask.get("task", "")
            reasoning = subtask.get("reasoning", "")
            sources_needed = subtask.get("sources_needed", ["local"])
            depth = subtask.get("depth", "detailed")
            sub_actions = subtask.get("sub_actions", [])
            expected_output = subtask.get("expected_output", "")
            quality_checks = subtask.get("quality_checks", [])
            
            # Generate comprehensive analysis for this subtask
            subtask_result = await analyze_subtask_comprehensive(
                task, reasoning, sources_needed, depth, sub_actions, expected_output, 
                quality_checks, context_text, web_context, filename, nvidia_rotator
            )
            
            section_analysis["subtask_results"].append({
                "task": task,
                "reasoning": reasoning,
                "depth": depth,
                "sub_actions": sub_actions,
                "expected_output": expected_output,
                "quality_checks": quality_checks,
                "analysis": subtask_result
            })
        
        # Generate section-level synthesis
        section_synthesis = await synthesize_section_analysis(
            section_analysis, synthesis_strategy, nvidia_rotator
        )
        section_analysis["section_synthesis"] = section_synthesis
        
        detailed_analysis[section_title] = section_analysis
    
    logger.info(f"[REPORT] Completed detailed analysis for {len(detailed_analysis)} sections")
    return detailed_analysis


async def analyze_subtask_comprehensive(task: str, reasoning: str, sources_needed: List[str], depth: str,
                                      sub_actions: List[str], expected_output: str, quality_checks: List[str],
                                      context_text: str, web_context: str, filename: str, nvidia_rotator) -> str:
    """Analyze a specific subtask with comprehensive detail and sub-actions."""
    
    # Select appropriate context based on sources_needed
    selected_context = ""
    if "local" in sources_needed and "web" in sources_needed:
        selected_context = f"DOCUMENT CONTEXT:\n{context_text}\n\nWEB CONTEXT:\n{web_context}"
    elif "local" in sources_needed:
        selected_context = f"DOCUMENT CONTEXT:\n{context_text}"
    elif "web" in sources_needed:
        selected_context = f"WEB CONTEXT:\n{web_context}"
    
    # Enhanced depth instructions
    depth_instructions = {
        "surface": "Provide a brief, high-level analysis with key points",
        "detailed": "Provide a thorough, well-reasoned analysis with specific examples, evidence, and clear explanations",
        "comprehensive": "Provide an exhaustive, rigorous analysis with deep insights, multiple perspectives, and extensive evidence",
        "exhaustive": "Provide the most comprehensive analysis possible with exhaustive detail, multiple angles, critical evaluation, and extensive supporting evidence"
    }
    
    sub_actions_text = "\n".join([f"- {action}" for action in sub_actions]) if sub_actions else "No specific sub-actions defined"
    quality_checks_text = "\n".join([f"- {check}" for check in quality_checks]) if quality_checks else "No specific quality checks defined"
    
    sys_prompt = f"""You are an expert analyst performing comprehensive research. Your task is to {task}.

REASONING: {reasoning}

DEPTH REQUIREMENT: {depth_instructions.get(depth, "Provide detailed analysis")}

SUB-ACTIONS TO PERFORM:
{sub_actions_text}

EXPECTED OUTPUT: {expected_output}

QUALITY CHECKS:
{quality_checks_text}

Focus on:
- Extracting specific, relevant information with precision
- Providing clear, detailed explanations and insights
- Supporting all claims with concrete evidence from the materials
- Maintaining the highest analytical rigor and objectivity
- Being comprehensive and thorough while remaining focused
- Following the sub-actions systematically
- Meeting the expected output requirements
- Passing all quality checks

Return only the analysis, no meta-commentary or introductory phrases."""

    user_prompt = f"""TASK: {task}

MATERIALS:
{selected_context}

Perform the comprehensive analysis as specified, following all sub-actions and meeting quality standards."""

    try:
        selection = {"provider": "nvidia", "model": "meta/llama-3.1-8b-instruct"}
        analysis = await generate_answer_with_model(selection, sys_prompt, user_prompt, None, nvidia_rotator)
        return analysis.strip()
        
    except Exception as e:
        logger.warning(f"[REPORT] Comprehensive subtask analysis failed for '{task}': {e}")
        return f"Analysis for '{task}' could not be completed due to processing error."


async def synthesize_section_analysis(section_analysis: Dict[str, Any], synthesis_strategy: Dict[str, str], nvidia_rotator) -> str:
    """Synthesize all subtask results within a section into a coherent analysis."""
    
    section_title = section_analysis.get("title", "Unknown Section")
    section_purpose = section_analysis.get("purpose", "")
    subtask_results = section_analysis.get("subtask_results", [])
    
    # Prepare subtask summaries
    subtask_summaries = ""
    for i, result in enumerate(subtask_results, 1):
        task = result.get("task", "")
        analysis = result.get("analysis", "")
        subtask_summaries += f"\n### Subtask {i}: {task}\n{analysis}\n"
    
    sys_prompt = f"""You are an expert synthesis analyst. Your task is to synthesize multiple detailed analyses into a coherent, comprehensive section.

SECTION: {section_title}
PURPOSE: {section_purpose}

SYNTHESIS STRATEGY:
- Cross-referencing: {synthesis_strategy.get('cross_referencing', 'Connect related information across subtasks')}
- Evidence integration: {synthesis_strategy.get('evidence_integration', 'Weave together different types of evidence')}
- Argument development: {synthesis_strategy.get('argument_development', 'Build a compelling narrative flow')}

Focus on:
- Creating logical flow between subtask results
- Identifying key themes and patterns
- Highlighting important insights and findings
- Ensuring comprehensive coverage of the section purpose
- Maintaining analytical rigor and coherence
- Building toward a strong section conclusion

Return only the synthesized analysis, no meta-commentary."""

    user_prompt = f"""SECTION: {section_title}

DETAILED SUBTASK ANALYSES:
{subtask_summaries}

Synthesize these analyses into a comprehensive, coherent section that fulfills the section purpose."""

    try:
        selection = {"provider": "nvidia", "model": "meta/llama-3.1-8b-instruct"}
        synthesis = await generate_answer_with_model(selection, sys_prompt, user_prompt, None, nvidia_rotator)
        return synthesis.strip()
        
    except Exception as e:
        logger.warning(f"[REPORT] Section synthesis failed for '{section_title}': {e}")
        return f"Synthesis for '{section_title}' could not be completed due to processing error."


async def synthesize_comprehensive_report(instructions: str, cot_plan: Dict[str, Any], 
                                        detailed_analysis: Dict[str, Any], filename: str, 
                                        report_words: int, gemini_rotator, nvidia_rotator) -> str:
    """Synthesize the detailed analysis into a comprehensive, well-structured report."""
    
    # Prepare comprehensive synthesis materials
    analysis_summary = ""
    synthesis_strategy = cot_plan.get("synthesis_strategy", {})
    
    for section_title, section_data in detailed_analysis.items():
        analysis_summary += f"\n## {section_title}\n"
        analysis_summary += f"Purpose: {section_data.get('purpose', '')}\n"
        analysis_summary += f"Priority: {section_data.get('priority', 'important')}\n\n"
        
        # Include section synthesis if available
        section_synthesis = section_data.get("section_synthesis", "")
        if section_synthesis:
            analysis_summary += f"### Section Synthesis:\n{section_synthesis}\n\n"
        
        # Include detailed subtask results
        for subtask_result in section_data.get("subtask_results", []):
            analysis_summary += f"### {subtask_result.get('task', '')}\n"
            analysis_summary += f"Depth: {subtask_result.get('depth', 'detailed')}\n"
            analysis_summary += f"Analysis: {subtask_result.get('analysis', '')}\n\n"
    
    reasoning_flow = cot_plan.get("reasoning_flow", [])
    flow_text = "\n".join([f"{i+1}. {step}" for i, step in enumerate(reasoning_flow)])
    
    # Enhanced synthesis strategy
    cross_referencing = synthesis_strategy.get("cross_referencing", "Connect related information across sections")
    evidence_integration = synthesis_strategy.get("evidence_integration", "Weave together different source types")
    argument_development = synthesis_strategy.get("argument_development", "Build a compelling narrative")
    conclusion_synthesis = synthesis_strategy.get("conclusion_synthesis", "Create a powerful conclusion")
    
    sys_prompt = f"""You are an expert report writer synthesizing detailed analysis into a comprehensive, professional report.

Your task is to create a well-structured, authoritative report that:
1. Follows the planned reasoning flow: {flow_text}
2. Integrates all detailed analyses seamlessly with sophisticated synthesis
3. Maintains logical flow and coherence throughout
4. Provides clear, actionable insights and recommendations
5. Uses proper academic/professional formatting and structure
6. Targets approximately {report_words} words with comprehensive coverage
7. Demonstrates analytical rigor and depth

SYNTHESIS REQUIREMENTS:
- Cross-referencing: {cross_referencing}
- Evidence integration: {evidence_integration}
- Argument development: {argument_development}
- Conclusion synthesis: {conclusion_synthesis}

STRUCTURE REQUIREMENTS:
- Executive summary with key findings
- Clear section headings with logical progression
- Smooth transitions between sections
- Proper citations and references throughout
- Data-driven insights and evidence-based conclusions
- Actionable recommendations where appropriate
- Professional, analytical tone

CRITICAL: Start the report immediately with substantive content. Do NOT include meta-commentary like "Here is a comprehensive report..." or "Of course, here is...". Begin directly with the report title and content."""

    user_prompt = f"""USER REQUEST: {instructions}

COMPREHENSIVE ANALYSIS TO SYNTHESIZE:
{analysis_summary}

REASONING FLOW TO FOLLOW:
{flow_text}

SYNTHESIS STRATEGY:
- Cross-referencing: {cross_referencing}
- Evidence integration: {evidence_integration}
- Argument development: {argument_development}
- Conclusion synthesis: {conclusion_synthesis}

Create a comprehensive, authoritative report that addresses the user's request by synthesizing all the detailed analysis above. Begin immediately with the report title and substantive content."""

    try:
        # Use Gemini Pro for final synthesis (better for long-form content)
        selection = {"provider": "gemini", "model": "gemini-2.5-pro"}
        report = await generate_answer_with_model(selection, sys_prompt, user_prompt, gemini_rotator, nvidia_rotator)
        
        # Post-process to remove any remaining meta-commentary
        report = remove_meta_commentary(report)
        
        logger.info(f"[REPORT] Comprehensive report synthesized, length: {len(report)} characters")
        return report
        
    except Exception as e:
        logger.error(f"[REPORT] Report synthesis failed: {e}")
        # Fallback: simple concatenation
        fallback_report = f"# {instructions}\n\n"
        fallback_report += analysis_summary
        fallback_report += f"\n\n## Conclusion\n\n{instructions}"
        return fallback_report


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


