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
    nvidia_rotator,
    user_id: str = ""
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
    # Track analytics
    try:
        from utils.analytics import get_analytics_tracker
        tracker = get_analytics_tracker()
        if tracker and user_id:
            await tracker.track_agent_usage(
                user_id=user_id,
                agent_name="coding",
                action="generate_code",
                context="report_coding",
                metadata={"subsection_id": subsection_id}
            )
            await tracker.track_model_usage(
                user_id=user_id,
                model_name=selection["model"],
                provider=selection["provider"],
                context="report_coding",
                metadata={"subsection_id": subsection_id}
            )
    except Exception:
        pass
    code_md = await generate_answer_with_model(selection, system_prompt, user_prompt, gemini_rotator, nvidia_rotator, user_id, "coding")
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


def extract_structured_code(markdown: str):
    """Extract structured code blocks from the Gemini output.

    Expects sections like:
    'File: path/to/file.py' followed by a fenced code block and then an explanation paragraph.

    Returns list of {path, language, code, explanation}.
    """
    import re
    blocks = []
    if not markdown:
        return blocks

    # Split on 'File:' headings to locate file sections
    parts = re.split(r"\n(?=File:\s*)", markdown)
    for part in parts:
        part = part.strip()
        if not part.lower().startswith("file:"):
            # The first chunk may be prelude; skip if no code block
            continue
        # Extract path
        m_path = re.match(r"File:\s*(.+)", part)
        file_path = m_path.group(1).strip() if m_path else "unknown"

        # Extract fenced code block with optional language
        m_code = re.search(r"```([a-zA-Z0-9_+-]*)\n([\s\S]*?)\n```", part)
        language = (m_code.group(1) or '').strip() if m_code else ''
        code = m_code.group(2) if m_code else ''

        # Remove the matched code from part to find explanation remainder
        explanation = ''
        if m_code:
            start, end = m_code.span()
            # Text after code block is considered explanation
            explanation = part[end:].strip()

        blocks.append({
            "path": file_path,
            "language": language or detect_language_from_path(file_path),
            "code": code.strip(),
            "explanation": explanation
        })
    return blocks


def detect_language_from_path(path: str) -> str:
    ext = (path.split('.')[-1].lower() if '.' in path else '')
    return {
        'py': 'python',
        'js': 'javascript',
        'ts': 'typescript',
        'json': 'json',
        'md': 'markdown',
        'html': 'html',
        'css': 'css',
        'sh': 'bash',
        'yml': 'yaml',
        'yaml': 'yaml'
    }.get(ext, '')


