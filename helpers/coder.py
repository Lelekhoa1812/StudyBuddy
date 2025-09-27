"""
helpers/coder.py

Single-agent code generation using NVIDIA Qwen3 Coder model with Chain of Thought reasoning.
Produces files-by-files Markdown with per-file explanations. Designed to be called from 
report generation to attach code outputs to the appropriate subsection.
"""

import os
from typing import Optional
from utils.logger import get_logger
from utils.service.common import trim_text

logger = get_logger("CODER", __name__)

# Get the NVIDIA coder model from environment
NVIDIA_CODER = os.getenv("NVIDIA_CODER", "qwen/qwen3-coder-480b-a35b-instruct")


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
    """Generate code (files-by-files) with explanations using NVIDIA Qwen3 Coder with CoT reasoning.
    
    Enhanced workflow:
    1. Use NVIDIA_LARGE to analyze and enhance the task requirements
    2. Use NVIDIA_CODER to generate the actual code based on enhanced requirements

    Returns a Markdown string containing multiple code blocks. Each block is
    preceded by a heading like `File: path` and followed by a short
    explanation. The content is grounded in provided contexts.
    """
    from utils.api.router import nvidia_large_chat_completion

    logger.info(f"[CODER] Starting enhanced code generation for subsection {subsection_id} (task='{task[:60]}...')")
    
    # Track analytics for the coding agent
    try:
        from utils.analytics import get_analytics_tracker
        tracker = get_analytics_tracker()
        if tracker and user_id:
            await tracker.track_agent_usage(
                user_id=user_id,
                agent_name="coding",
                action="code",
                context="report_coding",
                metadata={"subsection_id": subsection_id, "model": NVIDIA_CODER}
            )
    except Exception:
        pass

    # Step 1: Use NVIDIA_LARGE to analyze and enhance the task requirements
    logger.info(f"[CODER] Step 1: Analyzing task with NVIDIA_LARGE for subsection {subsection_id}")
    
    analysis_system_prompt = (
        "You are a senior software architect and technical lead. Your task is to analyze a coding requirement "
        "and provide a comprehensive, enhanced specification that will be used by a code generation AI.\n\n"
        "ANALYSIS REQUIREMENTS:\n"
        "1. Break down the task into clear, actionable components\n"
        "2. Identify potential technical challenges and solutions\n"
        "3. Suggest appropriate technologies, frameworks, and patterns\n"
        "4. Define clear requirements and constraints\n"
        "5. Identify dependencies and relationships between components\n"
        "6. Consider scalability, maintainability, and best practices\n\n"
        "OUTPUT FORMAT:\n"
        "Provide a structured analysis in the following format:\n"
        "- **Task Analysis**: Clear breakdown of what needs to be implemented\n"
        "- **Technical Requirements**: Specific technical specifications\n"
        "- **Architecture Suggestions**: Recommended structure and patterns\n"
        "- **Dependencies**: Required libraries, frameworks, or external services\n"
        "- **Implementation Notes**: Key considerations for the implementation\n"
        "- **Enhanced Task Description**: A refined, detailed task description for code generation"
    )
    
    analysis_user_prompt = (
        f"ORIGINAL TASK: {task}\n"
        f"ORIGINAL REASONING: {reasoning}\n"
        f"SUBSECTION: {subsection_id}\n\n"
        f"CONTEXT (DOCUMENT):\n{trim_text(context_text or '', 8000)}\n\n"
        f"CONTEXT (WEB):\n{trim_text(web_context or '', 4000)}\n\n"
        "Please analyze this coding task and provide a comprehensive enhancement that will guide the code generation process."
    )
    
    try:
        enhanced_analysis = await nvidia_large_chat_completion(analysis_system_prompt, analysis_user_prompt, nvidia_rotator)
        logger.info(f"[CODER] Task analysis completed for subsection {subsection_id}")
        
        # Track NVIDIA_LARGE usage
        try:
            if tracker and user_id:
                await tracker.track_model_usage(
                    user_id=user_id,
                    model_name="nvidia_large",
                    provider="nvidia_large",
                    context="code_analysis",
                    metadata={"subsection_id": subsection_id}
                )
        except Exception:
            pass
            
    except Exception as e:
        logger.warning(f"[CODER] Task analysis failed for subsection {subsection_id}: {e}")
        enhanced_analysis = f"**Task Analysis**: {task}\n**Technical Requirements**: {reasoning}\n**Enhanced Task Description**: {task}"
    
    # Step 2: Use NVIDIA_CODER to generate code based on enhanced analysis
    logger.info(f"[CODER] Step 2: Generating code with NVIDIA_CODER for subsection {subsection_id}")
    
    # Enhanced system prompt with Chain of Thought reasoning
    system_prompt = (
        "You are a senior software engineer with expertise in code generation and architecture design.\n"
        "Your task is to generate production-quality code based on the ENHANCED ANALYSIS provided below.\n\n"
        "REASONING PROCESS (Chain of Thought):\n"
        "1. First, analyze the enhanced requirements and constraints\n"
        "2. Identify the key components and their relationships\n"
        "3. Consider the context and any existing patterns or frameworks\n"
        "4. Plan the code structure and architecture\n"
        "5. Generate clean, maintainable code with proper error handling\n"
        "6. Ensure code follows best practices and is production-ready\n\n"
        "OUTPUT FORMAT:\n"
        "- Output Markdown with multiple code blocks by file, each preceded by a short heading 'File: path'\n"
        "- Prefer clear, minimal dependencies\n"
        "- After each code block, add a concise explanation of design decisions\n"
        "- Ensure coherent naming and imports across files\n"
        "- If mentioning endpoints/APIs, ensure consistency across files\n"
        "- Do not include meta text like 'Here is the code'. Start with the first file heading\n"
        "- Include proper error handling, documentation, and testing considerations\n"
    )
    
    # Enhanced user prompt with the analysis results
    user_prompt = (
        f"SUBSECTION: {subsection_id}\n"
        f"ENHANCED ANALYSIS:\n{enhanced_analysis}\n\n"
        f"ORIGINAL CONTEXT (DOCUMENT):\n{trim_text(context_text or '', 6000)}\n\n"
        f"ORIGINAL CONTEXT (WEB):\n{trim_text(web_context or '', 3000)}\n\n"
        "Please follow this reasoning process:\n"
        "1. Analyze the enhanced requirements and identify what needs to be implemented\n"
        "2. Consider the provided context and any relevant patterns or frameworks\n"
        "3. Plan the code structure, including file organization and dependencies\n"
        "4. Generate clean, production-ready code with proper error handling\n"
        "5. Ensure code follows best practices and is maintainable\n\n"
        "Produce the code files and explanations as specified."
    )

    # Use the new NVIDIA coder function
    code_md = await nvidia_coder_completion(system_prompt, user_prompt, nvidia_rotator, user_id, "coding")
    code_md = (code_md or "").strip()

    # Track NVIDIA_CODER usage
    try:
        if tracker and user_id:
            await tracker.track_model_usage(
                user_id=user_id,
                model_name=NVIDIA_CODER,
                provider="nvidia_coder",
                context="report_coding",
                metadata={"subsection_id": subsection_id}
            )
    except Exception:
        pass

    if not code_md:
        logger.warning(f"[CODER] Empty code output for subsection {subsection_id}")
        return "Code generation produced no content."

    # Light post-check: ensure at least one fenced code block
    if "```" not in code_md:
        logger.warning(f"[CODER] No code fences detected for subsection {subsection_id}")
    else:
        logger.info(f"[CODER] Code fences detected for subsection {subsection_id}")

    return code_md


async def nvidia_coder_completion(system_prompt: str, user_prompt: str, nvidia_rotator, user_id: str = None, context: str = "") -> str:
    """
    NVIDIA Coder completion using the specified coder model with streaming support.
    Uses the NVIDIA API rotator for key management and supports Chain of Thought reasoning.
    """
    # Track model usage for analytics
    try:
        from utils.analytics import get_analytics_tracker
        tracker = get_analytics_tracker()
        if tracker and user_id:
            await tracker.track_model_usage(
                user_id=user_id,
                model_name="nvidia/coder-8b",
                provider="nvidia_coder",
                context=context or "nvidia_coder_completion",
                metadata={"system_prompt_length": len(system_prompt), "user_prompt_length": len(user_prompt)}
            )
    except Exception as e:
        logger.debug(f"[CODER] Analytics tracking failed: {e}")
    key = nvidia_rotator.get_key() or ""
    url = "https://integrate.api.nvidia.com/v1/chat/completions"
    
    payload = {
        "model": NVIDIA_CODER,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.7,
        "top_p": 0.8,
        "max_tokens": 4096,
        "stream": True
    }
    
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {key}"}
    
    logger.info(f"[NVIDIA_CODER] API call - Model: {NVIDIA_CODER}, Key present: {bool(key)}")
    logger.info(f"[NVIDIA_CODER] System prompt length: {len(system_prompt)}, User prompt length: {len(user_prompt)}")
    
    try:
        # For streaming, we need to handle the response differently
        import httpx
        async with httpx.AsyncClient(timeout=120) as client:  # Longer timeout for code generation
            response = await client.post(url, headers=headers, json=payload)
            
            if response.status_code in (401, 403, 429) or (500 <= response.status_code < 600):
                logger.warning(f"HTTP {response.status_code} from NVIDIA Coder provider. Rotating key and retrying")
                nvidia_rotator.rotate()
                # Retry once with new key
                key = nvidia_rotator.get_key() or ""
                headers = {"Content-Type": "application/json", "Authorization": f"Bearer {key}"}
                response = await client.post(url, headers=headers, json=payload)
            
            response.raise_for_status()
            
            # Handle streaming response
            content = ""
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = line[6:]  # Remove "data: " prefix
                    if data.strip() == "[DONE]":
                        break
                    
                    try:
                        import json
                        chunk_data = json.loads(data)
                        if "choices" in chunk_data and len(chunk_data["choices"]) > 0:
                            delta = chunk_data["choices"][0].get("delta", {})
                            
                            # Handle reasoning content (thinking) for CoT
                            reasoning = delta.get("reasoning_content")
                            if reasoning:
                                logger.debug(f"[NVIDIA_CODER] Reasoning: {reasoning}")
                            
                            # Handle regular content
                            chunk_content = delta.get("content")
                            if chunk_content:
                                content += chunk_content
                    except json.JSONDecodeError:
                        continue
            
            if not content or content.strip() == "":
                logger.warning(f"Empty content from NVIDIA Coder model")
                return "I received an empty response from the model."
            
            return content.strip()
            
    except Exception as e:
        logger.warning(f"NVIDIA Coder API error: {e}")
        return "I couldn't process the request with NVIDIA Coder model."


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


