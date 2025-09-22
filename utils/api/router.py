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
NVIDIA_SMALL = os.getenv("NVIDIA_SMALL", "meta/llama-3.1-8b-instruct")  # example; adjust to your NIM catalog

def select_model(question: str, context: str) -> Dict[str, Any]:
    """
    Very lightweight complexity heuristic:
    - If long question or lots of context -> MED/PRO
    - If code/math keywords -> PRO
    - Else SMALL
    Prefers NVIDIA small when question is short/simple (cost-awareness).
    """
    qlen = len(question.split())
    clen = len(context.split())
    hard_keywords = ("prove", "derivation", "complexity", "algorithm", "optimize", "theorem", "rigorous", "step-by-step", "policy critique", "ambiguity", "counterfactual")
    is_hard = any(k in question.lower() for k in hard_keywords) or qlen > 60 or clen > 1600

    if is_hard:
        # Use Gemini Pro (larger context)
        return {"provider": "gemini", "model": GEMINI_PRO}
    elif qlen > 25 or clen > 900:
        return {"provider": "gemini", "model": GEMINI_MED}
    else:
        # Prefer NVIDIA small for cheap/light
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

    return "Unsupported provider."