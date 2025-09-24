"""
helpers/coder.py

Single-agent code generation using Gemini Pro. Produces files-by-files Markdown
with per-file explanations. Designed to be called from report generation to
attach code outputs to the appropriate subsection.
"""

from typing import Optional
from utils.logger import get_logger
from utils.service.common import trim_text

logger = get_logger("CODER", __name__)


async def generate_code_artifacts(
    subsection_id: str,
    task: str,
    reasoning: str,
    context_text: str,
    web_context: str,
    gemini_rotator,
    nvidia_rotator
) -> str:
    """Generate code (files-by-files) with explanations using Gemini Pro.

    Returns a Markdown string containing multiple code blocks. Each block is
    preceded by a heading like `File: path` and followed by a short
    explanation. The content is grounded in provided contexts.
    """
    from utils.api.router import generate_answer_with_model

    system_prompt = (
        "You are a senior software engineer. Generate production-quality code that fulfills the TASK,\n"
        "grounded strictly in the provided CONTEXT.\n"
        "Rules:\n"
        "- Output Markdown with multiple code blocks by file, each preceded by a short heading 'File: path'.\n"
        "- Prefer clear, minimal dependencies.\n"
        "- After each code block, add a concise explanation of design decisions.\n"
        "- Ensure coherent naming and imports across files.\n"
        "- If mentioning endpoints/APIs, ensure consistency across files.\n"
        "- Do not include meta text like 'Here is the code'. Start with the first file heading.\n"
    )
    user_prompt = (
        f"SUBSECTION {subsection_id}\nTASK: {task}\nREASONING: {reasoning}\n\n"
        f"CONTEXT (DOCUMENT):\n{trim_text(context_text or '', 6000)}\n\n"
        f"CONTEXT (WEB):\n{trim_text(web_context or '', 3000)}\n\n"
        "Produce the code files and explanations as specified."
    )

    selection = {"provider": "gemini", "model": "gemini-2.5-pro"}

    logger.info(f"[CODER] Generating code for subsection {subsection_id} (task='{task[:60]}...')")
    code_md = await generate_answer_with_model(selection, system_prompt, user_prompt, gemini_rotator, nvidia_rotator)
    code_md = (code_md or "").strip()

    if not code_md:
        logger.warning(f"[CODER] Empty code output for subsection {subsection_id}")
        return "Code generation produced no content."

    # Light post-check: ensure at least one fenced code block
    if "```" not in code_md:
        logger.warning(f"[CODER] No code fences detected for subsection {subsection_id}")
    else:
        logger.info(f"[CODER] Code fences detected for subsection {subsection_id}")

    return code_md


