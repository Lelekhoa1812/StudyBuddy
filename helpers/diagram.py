"""
helpers/diagram.py

Mermaid diagram generation with NVIDIA_LARGE (gpt-oss). Includes a CoT retry
mechanism that feeds back rendering errors to refine the diagram prompt.
"""

from typing import Dict, Any
from utils.logger import get_logger

logger = get_logger("DIAGRAM", __name__)


def should_generate_mermaid(instructions: str, report_text: str) -> bool:
    intent = (instructions or "") + " " + (report_text or "")
    keywords = (
        "architecture", "workflow", "data flow", "sequence", "state machine", "code", "software", "system",
        "er diagram", "dependency", "pipeline", "diagram", "flowchart", "program", 
    )
    return any(k in intent.lower() for k in keywords)


async def generate_mermaid_diagram(
    instructions: str,
    detailed_analysis: Dict[str, Any],
    gemini_rotator,
    nvidia_rotator,
    render_error: str = "",
    retry: int = 0,
    max_retries: int = 2
) -> str:
    from utils.api.router import generate_answer_with_model

    # Build compact overview context
    overview = []
    for title, data in (detailed_analysis or {}).items():
        section_id = data.get("section_id", "")
        syn = data.get("section_synthesis", "")
        if syn:
            overview.append(f"{section_id} {title}: {syn[:180]}...")
    context_overview = "\n".join(overview)

    sys_prompt = (
        "You are an expert technical illustrator. Create a single concise Mermaid diagram that best conveys the core structure\n"
        "(e.g., flowchart, sequence, class, state, or ER) based on the provided CONTEXT.\n"
        "Rules:\n"
        "- Return Mermaid code only (no backticks, no explanations).\n"
        "- Prefer flowchart or sequence if uncertain.\n"
        "- Keep node labels short but meaningful.\n"
        "- Ensure Mermaid syntax is valid.\n"
    )

    feedback = (f"\n\nRENDERING ERROR TO FIX: {render_error}\n" if render_error else "")
    user_prompt = (
        f"INSTRUCTIONS:\n{instructions}\n\nCONTEXT OVERVIEW:\n{context_overview}{feedback}"
    )

    selection = {"provider": "nvidia_large", "model": "openai/gpt-oss-120b"}

    logger.info(f"[DIAGRAM] Generating Mermaid (retry={retry})")
    diagram = await generate_answer_with_model(selection, sys_prompt, user_prompt, gemini_rotator, nvidia_rotator)
    diagram = (diagram or "").strip()

    # Strip accidental code fences
    if diagram.startswith("```"):
        raw = diagram.strip('`')
        if raw.lower().startswith("mermaid"):
            diagram = "\n".join(raw.splitlines()[1:])

    # Naive validation: basic mermaid keywords
    if not any(kw in diagram for kw in ("graph", "sequenceDiagram", "classDiagram", "stateDiagram", "erDiagram")):
        logger.warning("[DIAGRAM] Mermaid validation failed: missing diagram keywords")
        if retry < max_retries:
            return await generate_mermaid_diagram(
                instructions, detailed_analysis, gemini_rotator, nvidia_rotator,
                render_error="Diagram did not include recognizable Mermaid diagram keyword.", retry=retry+1
            )

    return diagram


