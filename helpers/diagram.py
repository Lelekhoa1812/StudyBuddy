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
    max_retries: int = 5,
    user_id: str = ""
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

    # Enhanced system prompt with better error handling guidance
    sys_prompt = (
        "You are an expert technical illustrator and Mermaid syntax specialist. Create a single concise Mermaid diagram that best conveys the core structure\n"
        "(e.g., flowchart, sequence, class, state, or ER) based on the provided CONTEXT.\n"
        "Rules:\n"
        "- Return Mermaid code only (no backticks, no explanations).\n"
        "- Prefer flowchart or sequence if uncertain.\n"
        "- Keep node labels short but meaningful.\n"
        "- Ensure Mermaid syntax is valid and follows these guidelines:\n"
        "  * Use proper node IDs (alphanumeric, no spaces)\n"
        "  * Use proper arrow syntax (--> for flowcharts, ->> for sequence)\n"
        "  * Quote labels with special characters\n"
        "  * Use proper diagram type declarations\n"
        "- If there was a previous error, fix the specific syntax issues mentioned.\n"
    )

    # Enhanced error feedback
    if render_error:
        feedback = f"\n\nPREVIOUS RENDERING ERROR TO FIX:\n{render_error}\n\nPlease analyze this error and generate a corrected Mermaid diagram that addresses the specific syntax or logical issues mentioned above."
    else:
        feedback = ""

    user_prompt = (
        f"INSTRUCTIONS:\n{instructions}\n\nCONTEXT OVERVIEW:\n{context_overview}{feedback}"
    )

    # Use NVIDIA_LARGE for better diagram generation
    selection = {"provider": "nvidia_large", "model": "openai/gpt-oss-120b"}

    logger.info(f"[DIAGRAM] Generating Mermaid (retry={retry}/{max_retries})")
    # Track analytics
    try:
        from utils.analytics import get_analytics_tracker
        tracker = get_analytics_tracker()
        if tracker and user_id:
            await tracker.track_agent_usage(
                user_id=user_id,
                agent_name="diagram",
                action="diagram",
                context="report_diagram",
                metadata={"retry": retry}
            )
            await tracker.track_model_usage(
                user_id=user_id,
                model_name=selection["model"],
                provider=selection["provider"],
                context="report_diagram",
                metadata={"retry": retry}
            )
    except Exception:
        pass
    diagram = await generate_answer_with_model(selection, sys_prompt, user_prompt, gemini_rotator, nvidia_rotator, user_id, "diagram")
    diagram = (diagram or "").strip()

    # Strip accidental code fences
    if diagram.startswith("```"):
        raw = diagram.strip('`')
        if raw.lower().startswith("mermaid"):
            diagram = "\n".join(raw.splitlines()[1:])

    # Enhanced validation: check for common Mermaid syntax issues
    if not any(kw in diagram for kw in ("graph", "sequenceDiagram", "classDiagram", "stateDiagram", "erDiagram")):
        logger.warning("[DIAGRAM] Mermaid validation failed: missing diagram keywords")
        if retry < max_retries:
            return await generate_mermaid_diagram(
                instructions, detailed_analysis, gemini_rotator, nvidia_rotator,
                render_error="Diagram did not include recognizable Mermaid diagram keyword.", retry=retry+1, user_id=user_id
            )

    return diagram


async def _render_mermaid_with_retry(mermaid_text: str, max_retries: int = 3, user_id: str = "") -> bytes:
    """
    Render mermaid code to PNG with retry logic and AI-powered error correction.
    """
    last_error = ""
    
    for attempt in range(max_retries):
        try:
            # Try to render the current mermaid code
            img_bytes = _render_mermaid_png(mermaid_text)
            
            if img_bytes and len(img_bytes) > 0:
                logger.info(f"[DIAGRAM] Mermaid rendered successfully on attempt {attempt + 1}")
                return img_bytes
            else:
                logger.warning(f"[DIAGRAM] Mermaid render returned empty on attempt {attempt + 1}")
                
        except Exception as e:
            last_error = str(e)
            logger.warning(f"[DIAGRAM] Mermaid render attempt {attempt + 1} failed: {e}")
        
        # If this isn't the last attempt, try to fix the mermaid code using AI
        if attempt < max_retries - 1:
            try:
                logger.info(f"[DIAGRAM] Attempting to fix Mermaid syntax using AI (attempt {attempt + 1})")
                fixed_mermaid = await _fix_mermaid_with_ai(mermaid_text, last_error, user_id)
                if fixed_mermaid and fixed_mermaid != mermaid_text:
                    mermaid_text = fixed_mermaid
                    logger.info(f"[DIAGRAM] AI provided fixed Mermaid code for retry {attempt + 2}")
                else:
                    logger.warning(f"[DIAGRAM] AI could not provide fixed Mermaid code")
                    break
            except Exception as ai_error:
                logger.warning(f"[DIAGRAM] AI Mermaid fix failed: {ai_error}")
                break
    
    logger.warning(f"[DIAGRAM] All Mermaid render attempts failed, last error: {last_error}")
    return b""


async def _fix_mermaid_with_ai(mermaid_text: str, error_message: str, user_id: str = "") -> str:
    """
    Use AI to fix Mermaid syntax errors.
    """
    try:
        from utils.api.router import generate_answer_with_model
        
        sys_prompt = """You are a Mermaid syntax expert. Your task is to fix Mermaid diagram syntax errors.

Rules:
1. Return ONLY the corrected Mermaid code (no backticks, no explanations)
2. Ensure proper syntax for the diagram type
3. Fix common issues like:
   - Invalid node IDs (use alphanumeric, no spaces)
   - Incorrect arrow syntax
   - Missing quotes around labels with special characters
   - Wrong diagram type declarations
4. Maintain the original intent and structure of the diagram"""

        user_prompt = f"""Fix this Mermaid diagram that has rendering errors:

ORIGINAL MERMAID CODE:
```mermaid
{mermaid_text}
```

ERROR MESSAGE:
{error_message}

Please provide the corrected Mermaid code that will render successfully."""

        # Use NVIDIA_LARGE for better error correction
        selection = {"provider": "nvidia_large", "model": "openai/gpt-oss-120b"}
        response = await generate_answer_with_model(selection, sys_prompt, user_prompt, None, None, user_id, "diagram_fix")
        
        if response:
            # Clean up the response
            fixed_code = response.strip()
            if fixed_code.startswith("```"):
                fixed_code = fixed_code.strip('`')
                if fixed_code.lower().startswith("mermaid"):
                    fixed_code = "\n".join(fixed_code.splitlines()[1:])
            
            return fixed_code.strip()
        
    except Exception as e:
        logger.warning(f"[DIAGRAM] AI Mermaid fix failed: {e}")
    
    return ""


def _render_mermaid_png(mermaid_text: str) -> bytes:
    """
    Render mermaid code to PNG via Kroki service (no local mermaid-cli dependency).
    Falls back to returning empty bytes on failure.
    """
    try:
        import base64
        import json
        import urllib.request
        import urllib.error
        
        # Validate and clean mermaid content
        if not mermaid_text or not mermaid_text.strip():
            logger.warning("[DIAGRAM] Empty mermaid content")
            return b""
        
        # Clean the mermaid text - remove any potential issues
        cleaned_text = mermaid_text.strip()
        
        # Basic mermaid syntax validation
        if not cleaned_text.startswith(('graph', 'flowchart', 'sequenceDiagram', 'classDiagram', 'stateDiagram', 'erDiagram', 'journey', 'gantt', 'pie', 'gitgraph')):
            logger.warning(f"[DIAGRAM] Invalid mermaid diagram type: {cleaned_text[:50]}...")
            return b""
        
        # Kroki POST API for mermaid -> png
        data = json.dumps({"diagram_source": cleaned_text}).encode("utf-8")
        req = urllib.request.Request(
            url="https://kroki.io/mermaid/png",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status == 200:
                return resp.read()
            else:
                logger.warning(f"[DIAGRAM] Kroki returned status {resp.status}")
                return b""
                
    except urllib.error.HTTPError as e:
        if e.code == 400:
            logger.warning(f"[DIAGRAM] Kroki mermaid syntax error (400): {e.reason}")
        else:
            logger.warning(f"[DIAGRAM] Kroki HTTP error {e.code}: {e.reason}")
    except urllib.error.URLError as e:
        logger.warning(f"[DIAGRAM] Kroki connection error: {e.reason}")
    except Exception as e:
        logger.warning(f"[DIAGRAM] Kroki mermaid render error: {e}")
    
    return b""


async def fix_mermaid_syntax_for_ui(mermaid_text: str, error_message: str = "", user_id: str = "") -> str:
    """
    Fix Mermaid syntax for UI rendering using AI.
    Returns the corrected Mermaid code that can be used in the browser.
    """
    try:
        # If no error message provided, try to validate the mermaid syntax first
        if not error_message:
            # Basic validation - check for common issues
            if not mermaid_text.strip():
                error_message = "Empty Mermaid diagram"
            elif not any(kw in mermaid_text for kw in ("graph", "sequenceDiagram", "classDiagram", "stateDiagram", "erDiagram")):
                error_message = "Missing valid Mermaid diagram type declaration"
        
        # Use AI to fix the mermaid code
        fixed_code = await _fix_mermaid_with_ai(mermaid_text, error_message, user_id)
        
        if fixed_code and fixed_code != mermaid_text:
            logger.info(f"[DIAGRAM] AI provided fixed Mermaid code for UI")
            return fixed_code
        else:
            logger.warning(f"[DIAGRAM] AI could not fix Mermaid code for UI")
            return mermaid_text  # Return original if AI couldn't fix it
            
    except Exception as e:
        logger.warning(f"[DIAGRAM] Mermaid UI fix failed: {e}")
        return mermaid_text  # Return original on error


