from typing import List
import os
import asyncio
from .logger import get_logger
from utils.rotator import robust_post_json

logger = get_logger("SUM", __name__)


async def llama_summarize(text: str, max_sentences: int = 3) -> str:
  """Summarize text using NVIDIA Llama via /v1/chat/completions. Returns plain text."""
  text = (text or "").strip()
  if not text:
    return ""
  model = os.getenv("NVIDIA_SMALL", "meta/llama-3.1-8b-instruct")
  key = os.getenv("NVIDIA_API_1", "") or os.getenv("NVIDIA_API_KEY", "")
  if not key:
    logger.warning("NVIDIA API key not set; returning naive fallback summary")
    return naive_fallback(text, max_sentences)

  system_prompt = (
    "You are a precise summarizer. Produce a concise summary of the user's text. "
    f"Return about {max_sentences} sentences, no preface, no markdown."
  )
  user_prompt = f"Summarize this:\n\n{text}"

  try:
    url = "https://integrate.api.nvidia.com/v1/chat/completions"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {key}"}
    payload = {
      "model": model,
      "temperature": 0.2,
      "messages": [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
      ]
    }
    # Using rotator helper for retries; if not available, simple fetch could be used
    data = await robust_post_json(url, headers, payload)
    content = data["choices"][0]["message"]["content"].strip()
    return content
  except Exception as e:
    logger.warning(f"LLAMA summarization failed: {e}; using fallback")
    return naive_fallback(text, max_sentences)


def naive_fallback(text: str, max_sentences: int = 3) -> str:
  parts = [p.strip() for p in text.split('. ') if p.strip()]
  return '. '.join(parts[:max_sentences])


# Backward-compatible name used by app.py
async def cheap_summarize(text: str, max_sentences: int = 3) -> str:
  return await llama_summarize(text, max_sentences)