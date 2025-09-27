# ────────────────────────────── utils/router.py ──────────────────────────────
import os
from ..logger import get_logger
from typing import Dict, Any
from .rotator import robust_post_json, APIKeyRotator

logger = get_logger("ROUTER", __name__)

# Default model names (can be overridden via env)
GEMINI_SMALL = os.getenv("GEMINI_SMALL", "gemini-2.5-flash-lite")
GEMINI_MED   = os.getenv("GEMINI_MED",   "gemini-2.5-flash")
GEMINI_PRO   = os.getenv("GEMINI_PRO",   "gemini-2.5-pro")

# NVIDIA model hierarchy (can be overridden via env)
NVIDIA_SMALL = os.getenv("NVIDIA_SMALL", "meta/llama-3.1-8b-instruct")         # Llama model for easy complexity tasks
NVIDIA_MEDIUM = os.getenv("NVIDIA_MEDIUM", "qwen/qwen3-next-80b-a3b-thinking") # Qwen model for reasoning tasks
NVIDIA_LARGE = os.getenv("NVIDIA_LARGE", "openai/gpt-oss-120b")                # GPT-OSS model for hard/long context tasks

def select_model(question: str, context: str) -> Dict[str, Any]:
    """
    Enhanced three-tier model selection system:
    - Easy tasks (immediate execution, simple) -> Llama (NVIDIA small)
    - Reasoning tasks (analysis, decision-making, JSON parsing) -> Qwen (NVIDIA medium)
    - Hard/long context tasks (complex synthesis, long-form) -> GPT-OSS (NVIDIA large)
    - Very complex tasks (research, comprehensive analysis) -> Gemini Pro
    """
    qlen = len(question.split())
    clen = len(context.split())
    
    # Very hard task keywords - require Gemini Pro (research, comprehensive analysis)
    very_hard_keywords = ("prove", "derivation", "complexity", "algorithm", "optimize", "theorem", "rigorous", "step-by-step", "policy critique", "ambiguity", "counterfactual", "comprehensive", "detailed analysis", "synthesis", "evaluation", "research", "investigation", "comprehensive study")
    
    # Hard/long context keywords - require NVIDIA Large (GPT-OSS)
    hard_keywords = ("analyze", "explain", "compare", "evaluate", "summarize", "extract", "classify", "identify", "describe", "discuss", "synthesis", "consolidate", "process", "generate", "create", "develop", "build", "construct")
    
    # Reasoning task keywords - require Qwen (thinking/reasoning)
    reasoning_keywords = ("reasoning", "context", "enhance", "select", "decide", "choose", "determine", "assess", "judge", "consider", "think", "reason", "logic", "inference", "deduction", "analysis", "interpretation")
    
    # Simple task keywords - immediate execution
    simple_keywords = ("what", "how", "when", "where", "who", "yes", "no", "count", "list", "find", "search", "lookup")
    
    # Determine complexity level
    is_very_hard = (
        any(k in question.lower() for k in very_hard_keywords) or 
        qlen > 120 or 
        clen > 4000 or
        "comprehensive" in question.lower() or
        "detailed" in question.lower() or
        "research" in question.lower()
    )
    
    is_hard = (
        any(k in question.lower() for k in hard_keywords) or 
        qlen > 50 or 
        clen > 1500 or
        "synthesis" in question.lower() or
        "generate" in question.lower() or
        "create" in question.lower()
    )
    
    is_reasoning = (
        any(k in question.lower() for k in reasoning_keywords) or 
        qlen > 20 or 
        clen > 800 or
        "enhance" in question.lower() or
        "context" in question.lower() or
        "select" in question.lower() or
        "decide" in question.lower()
    )
    
    is_simple = (
        any(k in question.lower() for k in simple_keywords) or
        qlen <= 10 or
        clen <= 200
    )

    if is_very_hard:
        # Use Gemini Pro for very complex tasks requiring advanced reasoning
        return {"provider": "gemini", "model": GEMINI_PRO}
    elif is_hard:
        # Use NVIDIA Large (GPT-OSS) for hard/long context tasks
        return {"provider": "nvidia_large", "model": NVIDIA_LARGE}
    elif is_reasoning:
        # Use Qwen for reasoning tasks requiring thinking
        return {"provider": "qwen", "model": NVIDIA_MEDIUM}
    else:
        # Use NVIDIA small (Llama) for simple tasks requiring immediate execution
        return {"provider": "nvidia", "model": NVIDIA_SMALL}


async def generate_answer_with_model(selection: Dict[str, Any], system_prompt: str, user_prompt: str,
                                     gemini_rotator: APIKeyRotator, nvidia_rotator: APIKeyRotator, 
                                     user_id: str = None, context: str = "") -> str:
    provider = selection["provider"]
    model = selection["model"]
    
    # Track model usage for analytics
    try:
        from utils.analytics import get_analytics_tracker
        tracker = get_analytics_tracker()
        if tracker and user_id:
            await tracker.track_model_usage(
                user_id=user_id,
                model_name=model,
                provider=provider,
                context=context or "api_call",
                metadata={"system_prompt_length": len(system_prompt), "user_prompt_length": len(user_prompt)}
            )
    except Exception as e:
        logger.debug(f"[ROUTER] Analytics tracking failed: {e}")

    if provider == "gemini":
        # Try Gemini first
        try:
            key = gemini_rotator.get_key() or ""
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
            payload = {
                "contents": [
                    {"role": "user", "parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]}
                ],
                "generationConfig": {"temperature": 0.2}
            }
            headers = {"Content-Type": "application/json"}
            data = await robust_post_json(url, headers, payload, gemini_rotator)
            
            content = data["candidates"][0]["content"]["parts"][0]["text"]
            if not content or content.strip() == "":
                logger.warning(f"Empty content from Gemini model: {data}")
                raise Exception("Empty content from Gemini")
            return content
        except Exception as e:
            logger.warning(f"Gemini model {model} failed: {e}. Attempting fallback...")
            
            # Fallback logic: GEMINI_PRO/MED → NVIDIA_LARGE, GEMINI_SMALL → NVIDIA_SMALL
            if model in [GEMINI_PRO, GEMINI_MED]:
                logger.info(f"Falling back from {model} to NVIDIA_LARGE")
                fallback_selection = {"provider": "nvidia_large", "model": NVIDIA_LARGE}
                return await generate_answer_with_model(fallback_selection, system_prompt, user_prompt, gemini_rotator, nvidia_rotator, user_id, context)
            elif model == GEMINI_SMALL:
                logger.info(f"Falling back from {model} to NVIDIA_SMALL")
                fallback_selection = {"provider": "nvidia", "model": NVIDIA_SMALL}
                return await generate_answer_with_model(fallback_selection, system_prompt, user_prompt, gemini_rotator, nvidia_rotator, user_id, context)
            else:
                logger.error(f"No fallback defined for Gemini model: {model}")
                return "I couldn't parse the model response."

    elif provider == "nvidia":
        # Try NVIDIA small model first
        try:
            key = nvidia_rotator.get_key() or ""
            url = "https://integrate.api.nvidia.com/v1/chat/completions"
            payload = {
                "model": model,
                "temperature": 0.2,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ]
            }
            headers = {"Content-Type": "application/json", "Authorization": f"Bearer {key}"}
            
            logger.info(f"[ROUTER] NVIDIA API call - Model: {model}, Key present: {bool(key)}")
            logger.info(f"[ROUTER] System prompt length: {len(system_prompt)}, User prompt length: {len(user_prompt)}")
            
            data = await robust_post_json(url, headers, payload, nvidia_rotator)
            
            logger.info(f"[ROUTER] NVIDIA API response type: {type(data)}, keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
            content = data["choices"][0]["message"]["content"]
            if not content or content.strip() == "":
                logger.warning(f"Empty content from NVIDIA model: {data}")
                raise Exception("Empty content from NVIDIA")
            return content
        except Exception as e:
            logger.warning(f"NVIDIA model {model} failed: {e}. Attempting fallback...")
            
            # Fallback: NVIDIA_SMALL → Try a different NVIDIA model or basic response
            if model == NVIDIA_SMALL:
                logger.info(f"Falling back from {model} to basic response")
                return "I'm experiencing technical difficulties with the AI model. Please try again later."
            else:
                logger.error(f"No fallback defined for NVIDIA model: {model}")
                return "I couldn't parse the model response."

    elif provider == "qwen":
        # Use Qwen for reasoning tasks with fallback
        try:
            return await qwen_chat_completion(system_prompt, user_prompt, nvidia_rotator)
        except Exception as e:
            logger.warning(f"Qwen model failed: {e}. Attempting fallback...")
            # Fallback: Qwen → NVIDIA_SMALL
            logger.info("Falling back from Qwen to NVIDIA_SMALL")
            fallback_selection = {"provider": "nvidia", "model": NVIDIA_SMALL}
            return await generate_answer_with_model(fallback_selection, system_prompt, user_prompt, gemini_rotator, nvidia_rotator)
    elif provider == "nvidia_large":
        # Use NVIDIA Large (GPT-OSS) for hard/long context tasks with fallback
        try:
            return await nvidia_large_chat_completion(system_prompt, user_prompt, nvidia_rotator)
        except Exception as e:
            logger.warning(f"NVIDIA_LARGE model failed: {e}. Attempting fallback...")
            # Fallback: NVIDIA_LARGE → NVIDIA_SMALL
            logger.info("Falling back from NVIDIA_LARGE to NVIDIA_SMALL")
            fallback_selection = {"provider": "nvidia", "model": NVIDIA_SMALL}
            return await generate_answer_with_model(fallback_selection, system_prompt, user_prompt, gemini_rotator, nvidia_rotator)
    elif provider == "nvidia_coder":
        # Use NVIDIA Coder for code generation tasks with fallback
        try:
            from helpers.coder import nvidia_coder_completion
            return await nvidia_coder_completion(system_prompt, user_prompt, nvidia_rotator)
        except Exception as e:
            logger.warning(f"NVIDIA_CODER model failed: {e}. Attempting fallback...")
            # Fallback: NVIDIA_CODER → NVIDIA_SMALL
            logger.info("Falling back from NVIDIA_CODER to NVIDIA_SMALL")
            fallback_selection = {"provider": "nvidia", "model": NVIDIA_SMALL}
            return await generate_answer_with_model(fallback_selection, system_prompt, user_prompt, gemini_rotator, nvidia_rotator)

    return "Unsupported provider."


async def qwen_chat_completion(system_prompt: str, user_prompt: str, nvidia_rotator: APIKeyRotator) -> str:
    """
    Qwen chat completion with thinking mode enabled.
    Uses the NVIDIA API rotator for key management.
    """
    key = nvidia_rotator.get_key() or ""
    url = "https://integrate.api.nvidia.com/v1/chat/completions"
    
    payload = {
        "model": NVIDIA_MEDIUM,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.6,
        "top_p": 0.7,
        "max_tokens": 8192,
        "stream": True
    }
    
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {key}"}
    
    logger.info(f"[QWEN] API call - Model: {NVIDIA_MEDIUM}, Key present: {bool(key)}")
    logger.info(f"[QWEN] System prompt length: {len(system_prompt)}, User prompt length: {len(user_prompt)}")
    
    try:
        # For streaming, we need to handle the response differently
        import httpx
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(url, headers=headers, json=payload)
            
            if response.status_code in (401, 403, 429) or (500 <= response.status_code < 600):
                logger.warning(f"HTTP {response.status_code} from Qwen provider. Rotating key and retrying")
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
                            
                            # Handle reasoning content (thinking)
                            reasoning = delta.get("reasoning_content")
                            if reasoning:
                                logger.debug(f"[QWEN] Reasoning: {reasoning}")
                            
                            # Handle regular content
                            chunk_content = delta.get("content")
                            if chunk_content:
                                content += chunk_content
                    except json.JSONDecodeError:
                        continue
            
            if not content or content.strip() == "":
                logger.warning(f"Empty content from Qwen model")
                return "I received an empty response from the model."
            
            return content.strip()
            
    except Exception as e:
        logger.warning(f"Qwen API error: {e}")
        return "I couldn't process the request with Qwen model."


async def nvidia_large_chat_completion(system_prompt: str, user_prompt: str, nvidia_rotator: APIKeyRotator) -> str:
    """
    NVIDIA Large (GPT-OSS) chat completion for hard/long context tasks.
    Uses the NVIDIA API rotator for key management.
    """
    key = nvidia_rotator.get_key() or ""
    url = "https://integrate.api.nvidia.com/v1/chat/completions"
    
    payload = {
        "model": NVIDIA_LARGE,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 1.0,
        "top_p": 1.0,
        "max_tokens": 4096,
        "stream": True
    }
    
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {key}"}
    
    logger.info(f"[NVIDIA_LARGE] API call - Model: {NVIDIA_LARGE}, Key present: {bool(key)}")
    logger.info(f"[NVIDIA_LARGE] System prompt length: {len(system_prompt)}, User prompt length: {len(user_prompt)}")
    
    try:
        # For streaming, we need to handle the response differently
        import httpx
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(url, headers=headers, json=payload)
            
            if response.status_code in (401, 403, 429) or (500 <= response.status_code < 600):
                logger.warning(f"HTTP {response.status_code} from NVIDIA Large provider. Rotating key and retrying")
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
                            
                            # Handle reasoning content (thinking)
                            reasoning = delta.get("reasoning_content")
                            if reasoning:
                                logger.debug(f"[NVIDIA_LARGE] Reasoning: {reasoning}")
                            
                            # Handle regular content
                            chunk_content = delta.get("content")
                            if chunk_content:
                                content += chunk_content
                    except json.JSONDecodeError:
                        continue
            
            if not content or content.strip() == "":
                logger.warning(f"Empty content from NVIDIA Large model")
                return "I received an empty response from the model."
            
            return content.strip()
            
    except Exception as e:
        logger.warning(f"NVIDIA Large API error: {e}")
        return "I couldn't process the request with NVIDIA Large model."