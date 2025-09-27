# ────────────────────────────── memo/nvidia.py ──────────────────────────────
"""
NVIDIA Integration

Functions for interacting with NVIDIA's API for summarization and analysis.
"""

import os
import json
from typing import List, Dict, Any

from utils.logger import get_logger
from utils.api.rotator import robust_post_json
from utils.api.router import qwen_chat_completion

logger = get_logger("NVIDIA_INTEGRATION", __name__)

NVIDIA_SMALL = os.getenv("NVIDIA_SMALL", "meta/llama-3.1-8b-instruct")
NVIDIA_MEDIUM = os.getenv("NVIDIA_MEDIUM", "qwen/qwen3-next-80b-a3b-thinking")

async def nvidia_chat(system_prompt: str, user_prompt: str, nvidia_key: str, rotator, user_id: str = "system", context: str = "nvidia_chat") -> str:
    """
    Minimal NVIDIA Chat call that enforces no-comment concise outputs.
    """
    # Track model usage for analytics
    try:
        from utils.analytics import get_analytics_tracker
        tracker = get_analytics_tracker()
        if tracker:
            await tracker.track_model_usage(
                user_id=user_id,
                model_name=os.getenv("NVIDIA_SMALL", "meta/llama-3.1-8b-instruct"),
                provider="nvidia",
                context=context,
                metadata={"system_prompt_length": len(system_prompt), "user_prompt_length": len(user_prompt)}
            )
    except Exception:
        pass
    
    url = "https://integrate.api.nvidia.com/v1/chat/completions"
    payload = {
        "model": NVIDIA_SMALL,
        "temperature": 0.0,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
    }
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {nvidia_key or ''}"}
    data = None
    try:
        data = await robust_post_json(url, headers, payload, rotator)
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning(f"NVIDIA chat error: {e} • response: {data}")
        return ""

async def qwen_chat(system_prompt: str, user_prompt: str, rotator, user_id: str = "") -> str:
    """
    Qwen chat call for medium complexity tasks with thinking mode.
    """
    # Track memo agent usage
    try:
        from utils.analytics import get_analytics_tracker
        tracker = get_analytics_tracker()
        if tracker:
            await tracker.track_agent_usage(
                user_id=user_id,
                agent_name="memo",
                action="chat",
                context="memo_qwen_chat",
                metadata={"query": user_prompt[:100]}
            )
    except Exception:
        pass
    
    try:
        return await qwen_chat_completion(system_prompt, user_prompt, rotator, user_id, "memo_qwen_chat")
    except Exception as e:
        logger.warning(f"Qwen chat error: {e}")
        return ""

def safe_json(s: str) -> Any:
    """Safely parse JSON string"""
    try:
        return json.loads(s)
    except Exception:
        # Try to extract a JSON object from text
        start = s.find("{")
        end = s.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(s[start:end+1])
            except Exception:
                return {}
        return {}

async def summarize_qa(question: str, answer: str, rotator) -> str:
    """
    Returns a single line block:
    q: <concise>\na: <concise>
    No extra commentary.
    """
    sys = "You are a terse summarizer. Output exactly two lines:\nq: <short question summary>\na: <short answer summary>\nNo extra text."
    user = f"Question:\n{question}\n\nAnswer:\n{answer}"
    key = rotator.get_key()
    out = await nvidia_chat(sys, user, key, rotator, user_id="system", context="memo_nvidia_chat")
    
    # Basic guard if the model returns extra prose
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    ql = next((l for l in lines if l.lower().startswith('q:')), None)
    al = next((l for l in lines if l.lower().startswith('a:')), None)
    
    if not ql or not al:
        # Fallback truncate
        ql = "q: " + (question.strip()[:160] + ("…" if len(question.strip()) > 160 else ""))
        al = "a: " + (answer.strip()[:220] + ("…" if len(answer.strip()) > 220 else ""))
    
    return f"{ql}\n{al}"

async def files_relevance(question: str, file_summaries: List[Dict[str, str]], rotator) -> Dict[str, bool]:
    """
    Ask Qwen model to mark each file as relevant (true) or not (false) for the question.
    Returns {filename: bool}
    """
    sys = "You classify file relevance. Return STRICT JSON only with shape {\"relevance\":[{\"filename\":\"...\",\"relevant\":true|false}]}."
    items = [{"filename": f["filename"], "summary": f.get("summary","")} for f in file_summaries]
    user = f"Question: {question}\n\nFiles:\n{json.dumps(items, ensure_ascii=False)}\n\nReturn JSON only."
    
    # Use Qwen for better JSON parsing and reasoning
    out = await qwen_chat(sys, user, rotator)
    
    data = safe_json(out) or {}
    rels = {}
    for row in data.get("relevance", []):
        fn = row.get("filename")
        rv = row.get("relevant")
        if isinstance(fn, str) and isinstance(rv, bool):
            rels[fn] = rv
    
    # If parsing failed, default to considering all files possibly relevant
    if not rels and file_summaries:
        rels = {f["filename"]: True for f in file_summaries}
    
    return rels

async def related_recent_context(question: str, recent_memories: List[str], rotator) -> str:
    """
    Use Qwen to select related items from recent memories.
    Enhanced function for better context memory ability.
    """
    if not recent_memories:
        return ""
    
    sys = "Pick only items that directly relate to the new question. Output the selected items verbatim, no commentary. If none, output nothing."
    numbered = [{"id": i+1, "text": s} for i, s in enumerate(recent_memories)]
    user = f"Question: {question}\nCandidates:\n{json.dumps(numbered, ensure_ascii=False)}\nSelect any related items and output ONLY their 'text' lines concatenated."
    
    try:
        # Use Qwen for better reasoning and context selection
        out = await qwen_chat(sys, user, rotator)
        return out.strip()
    except Exception as e:
        logger.warning(f"Recent-related Qwen error: {e}")
        return ""
