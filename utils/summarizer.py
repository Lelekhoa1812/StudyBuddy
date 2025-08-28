import os
import asyncio
from typing import List
from .logger import get_logger
from utils.rotator import robust_post_json

logger = get_logger("SUM", __name__)


async def llama_chat(messages, temperature: float = 0.2) -> str:
  model = os.getenv("NVIDIA_SMALL", "meta/llama-3.1-8b-instruct")
  key = os.getenv("NVIDIA_API_1", "") or os.getenv("NVIDIA_API_KEY", "")
  if not key:
    raise RuntimeError("NVIDIA API key not set")
  url = "https://integrate.api.nvidia.com/v1/chat/completions"
  headers = {"Content-Type": "application/json", "Authorization": f"Bearer {key}"}
  payload = {"model": model, "temperature": temperature, "messages": messages}
  data = await robust_post_json(url, headers, payload)
  return data["choices"][0]["message"]["content"].strip()


async def llama_summarize(text: str, max_sentences: int = 3) -> str:
  text = (text or "").strip()
  if not text:
    return ""
  system = (
    "You are a precise summarizer. Produce a clear, faithful summary of the user's text. "
    f"Return ~{max_sentences} sentences, no preface, no markdown."
  )
  user = f"Summarize this text:\n\n{text}"
  try:
    return await llama_chat([
      {"role": "system", "content": system},
      {"role": "user", "content": user},
    ])
  except Exception as e:
    logger.warning(f"LLAMA summarization failed: {e}; using fallback")
    return naive_fallback(text, max_sentences)


def naive_fallback(text: str, max_sentences: int = 3) -> str:
  parts = [p.strip() for p in text.split('. ') if p.strip()]
  return '. '.join(parts[:max_sentences])


async def summarize_text(text: str, max_sentences: int = 6, chunk_size: int = 2500) -> str:
  """Hierarchical summarization for long texts using NVIDIA Llama."""
  if not text:
    return ""
  if len(text) <= chunk_size:
    return await llama_summarize(text, max_sentences=max_sentences)
  # Split into chunks on paragraph boundaries if possible
  paragraphs = text.split('\n\n')
  chunks: List[str] = []
  buf = []
  total = 0
  for p in paragraphs:
    if total + len(p) > chunk_size and buf:
      chunks.append('\n\n'.join(buf))
      buf, total = [], 0
    buf.append(p)
    total += len(p)
  if buf:
    chunks.append('\n\n'.join(buf))

  partials = []
  for ch in chunks:
    partials.append(await llama_summarize(ch, max_sentences=3))
    await asyncio.sleep(0)
  combined = '\n'.join(partials)
  return await llama_summarize(combined, max_sentences=max_sentences)


async def clean_chunk_text(text: str) -> str:
  """Use NVIDIA LLM to remove headers/footers and personally identifying/institution boilerplate.
  Keep the core academic content intact. Do not remove page numbers or section titles.
  """
  content = (text or "").strip()
  if not content:
    return content
  system = (
    "You are a content cleaner. Remove boilerplate headers/footers like institution names, course codes, student IDs, "
    "emails, author IDs, document footers/headers repeated across pages. Keep headings and the main body content. "
    "Preserve meaningful section titles. Keep pagination references in the natural text if present. Return only cleaned text."
  )
  user = f"Clean this content by removing headers/footers and IDs, keep core content:\n\n{content}"
  try:
    return await llama_chat([
      {"role": "system", "content": system},
      {"role": "user", "content": user},
    ], temperature=0.0)
  except Exception as e:
    logger.warning(f"LLAMA cleaning failed: {e}; returning original text")
    return content


# Backward-compatible name used by app.py
async def cheap_summarize(text: str, max_sentences: int = 3) -> str:
  return await llama_summarize(text, max_sentences)