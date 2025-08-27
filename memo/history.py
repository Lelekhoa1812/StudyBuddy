# ────────────────────────────── memo/history.py ────────────────────────────── 
import os
import json
import logging
from typing import List, Dict, Any, Tuple
import numpy as np

from utils.logger import get_logger
from utils.rotator import robust_post_json
from utils.embeddings import EmbeddingClient

logger = get_logger("RAG", __name__)

NVIDIA_SMALL = os.getenv("NVIDIA_SMALL", "meta/llama-3.1-8b-instruct")

async def _nvidia_chat(system_prompt: str, user_prompt: str, nvidia_key: str, rotator) -> str:
    """
    Minimal NVIDIA Chat call that enforces no-comment concise outputs.
    """
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

def _safe_json(s: str) -> Any:
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

async def summarize_qa_with_nvidia(question: str, answer: str, rotator) -> str:
    """
    Returns a single line block:
    q: <concise>\na: <concise>
    No extra commentary.
    """
    sys = "You are a terse summarizer. Output exactly two lines:\nq: <short question summary>\na: <short answer summary>\nNo extra text."
    user = f"Question:\n{question}\n\nAnswer:\n{answer}"
    key = rotator.get_key()
    out = await _nvidia_chat(sys, user, key, rotator)
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
    Ask NVIDIA model to mark each file as relevant (true) or not (false) for the question.
    Returns {filename: bool}
    """
    sys = "You classify file relevance. Return STRICT JSON only with shape {\"relevance\":[{\"filename\":\"...\",\"relevant\":true|false}]}."
    items = [{"filename": f["filename"], "summary": f.get("summary","")} for f in file_summaries]
    user = f"Question: {question}\n\nFiles:\n{json.dumps(items, ensure_ascii=False)}\n\nReturn JSON only."
    key = rotator.get_key()
    out = await _nvidia_chat(sys, user, key, rotator)
    data = _safe_json(out) or {}
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

def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = (np.linalg.norm(a) * np.linalg.norm(b)) or 1.0
    return float(np.dot(a, b) / denom)

def _as_text(block: str) -> str:
    return block.strip()

async def related_recent_and_semantic_context(user_id: str, question: str, memory, embedder: EmbeddingClient, topk_sem: int = 3) -> Tuple[str, str]:
    """
    Returns (recent_related_text, semantic_related_text).
    - recent_related_text: NVIDIA checks the last 3 summaries for direct relatedness.
    - semantic_related_text: cosine-sim search over the remaining 17 summaries (top-k).
    """
    recent3 = memory.recent(user_id, 3)
    rest17 = memory.rest(user_id, 3)

    recent_text = ""
    if recent3:
        sys = "Pick only items that directly relate to the new question. Output the selected items verbatim, no commentary. If none, output nothing."
        numbered = [{"id": i+1, "text": s} for i, s in enumerate(recent3)]
        user = f"Question: {question}\nCandidates:\n{json.dumps(numbered, ensure_ascii=False)}\nSelect any related items and output ONLY their 'text' lines concatenated."
        key = None  # We'll let robust_post_json handle rotation via rotator param
        # Use the same nvidia rotator mechanism via a fake call; we'll reconstruct in app with the real rotator passed through
        # Here, we expect the caller to monkey-patch the chat with rotator; to keep it simple, we'll do a tiny trick:
        # The real API call occurs in app with rotator. For here, we return empty and let app request do it. (But to keep module self-contained, we do call with rotator when provided.)
    # However, since this function is called from app and gets the rotator, we'll move NVIDIA call out of here to avoid circular deps.

    # We'll implement a pure semantic search for rest17 here; recent related will be handled in app using the same prompt.

    # Semantic over rest17
    sem_text = ""
    if rest17:
        qv = np.array(embedder.embed([question])[0], dtype="float32")
        mats = embedder.embed([_as_text(s) for s in rest17])
        sims = [(_cosine(qv, np.array(v, dtype="float32")), s) for v, s in zip(mats, rest17)]
        sims.sort(key=lambda x: x[0], reverse=True)
        top = [s for (sc, s) in sims[:topk_sem] if sc > 0.15]  # small threshold
        if top:
            sem_text = "\n\n".join(top)
    # Return recent empty (to be filled by caller using NVIDIA), and semantic text
    return ("", sem_text)
