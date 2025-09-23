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

# NVIDIA small default (can be override)
NVIDIA_SMALL = os.getenv("NVIDIA_SMALL", "meta/llama-3.1-8b-instruct")         # Llama model for easy complexity tasks
NVIDIA_MEDIUM = os.getenv("NVIDIA_MEDIUM", "qwen/qwen3-next-80b-a3b-thinking") # Qwen model for medium complexity tasks

def select_model(question: str, context: str) -> Dict[str, Any]:
    """
    Enhanced complexity heuristic with proper model hierarchy:
    - Easy tasks (immediate execution, simple) -> Llama (NVIDIA small)
    - Medium tasks (accurate, reasoning, not too time-consuming) -> Qwen
    - Hard tasks (complex analysis, synthesis, long-form) -> Gemini Pro
    """
    qlen = len(question.split())
    clen = len(context.split())
    
    # Hard task keywords - require complex reasoning and analysis
    hard_keywords = ("prove", "derivation", "complexity", "algorithm", "optimize", "theorem", "rigorous", "step-by-step", "policy critique", "ambiguity", "counterfactual", "comprehensive", "detailed analysis", "synthesis", "evaluation")
    
    # Medium task keywords - require reasoning but not too complex
    medium_keywords = ("analyze", "explain", "compare", "evaluate", "summarize", "extract", "classify", "identify", "describe", "discuss", "reasoning", "context", "enhance", "select", "consolidate")
    
    # Simple task keywords - immediate execution
    simple_keywords = ("what", "how", "when", "where", "who", "yes", "no", "count", "list", "find")
    
    # Determine complexity level
    is_very_hard = (
        any(k in question.lower() for k in hard_keywords) or 
        qlen > 100 or 
        clen > 3000 or
        "comprehensive" in question.lower() or
        "detailed" in question.lower()
    )
    
    is_medium = (
        any(k in question.lower() for k in medium_keywords) or 
        (qlen > 10 and qlen <= 100) or 
        (clen > 200 and clen <= 3000) or
        "reasoning" in question.lower() or
        "context" in question.lower()
    )
    
    is_simple = (
        any(k in question.lower() for k in simple_keywords) or
        qlen <= 10 or
        clen <= 200
    )

    if is_very_hard:
        # Use Gemini Pro for very complex tasks requiring advanced reasoning
        return {"provider": "gemini", "model": GEMINI_PRO}
    elif is_medium:
        # Use Qwen for medium complexity tasks requiring reasoning but not too time-consuming
        return {"provider": "qwen", "model": NVIDIA_MEDIUM}
    else:
        # Use NVIDIA small (Llama) for simple tasks requiring immediate execution
        return {"provider": "nvidia", "model": NVIDIA_SMALL}


async def generate_answer_with_model(selection: Dict[str, Any], system_prompt: str, user_prompt: str,
                                     gemini_rotator: APIKeyRotator, nvidia_rotator: APIKeyRotator) -> str:
    provider = selection["provider"]
    model = selection["model"]

    if provider == "gemini":
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
        try:
            content = data["candidates"][0]["content"]["parts"][0]["text"]
            if not content or content.strip() == "":
                logger.warning(f"Empty content from Gemini model: {data}")
                return "I received an empty response from the model."
            return content
        except Exception as e:
            logger.warning(f"Unexpected Gemini response: {data}, error: {e}")
            return "I couldn't parse the model response."

    elif provider == "nvidia":
        # Many NVIDIA endpoints are OpenAI-compatible. Adjust if using a different path.
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
        try:
            content = data["choices"][0]["message"]["content"]
            if not content or content.strip() == "":
                logger.warning(f"Empty content from NVIDIA model: {data}")
                return "I received an empty response from the model."
            return content
        except Exception as e:
            logger.warning(f"Unexpected NVIDIA response: {data}, error: {e}")
            return "I couldn't parse the model response."

    elif provider == "qwen":
        # Use Qwen for medium complexity tasks
        return await qwen_chat_completion(system_prompt, user_prompt, nvidia_rotator)

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