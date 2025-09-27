import os
import asyncio
from typing import List
from utils.logger import get_logger
from utils.api.rotator import robust_post_json, APIKeyRotator
from utils.api.router import qwen_chat_completion, nvidia_large_chat_completion
from helpers.setup import nvidia_rotator

logger = get_logger("SUM", __name__)

# Use the shared NVIDIA API key rotator from helpers.setup
ROTATOR = nvidia_rotator


async def llama_chat(messages, temperature: float = 0.2, user_id: str = "system", context: str = "llama_chat") -> str:
  model = os.getenv("NVIDIA_SMALL", "meta/llama-3.1-8b-instruct")
  
  # Track model usage for analytics
  try:
    from utils.analytics import get_analytics_tracker
    tracker = get_analytics_tracker()
    if tracker:
      await tracker.track_model_usage(
        user_id=user_id,
        model_name=model,
        provider="nvidia",
        context=context,
        metadata={"temperature": temperature, "message_count": len(messages)}
      )
  except Exception:
    pass
  
  # Get key via rotator (supports rotation/retries in robust_post_json)
  key = ROTATOR.get_key()
  if not key:
    raise RuntimeError("NVIDIA API key not set (NVIDIA_API_*)")
  url = "https://integrate.api.nvidia.com/v1/chat/completions"
  headers = {"Content-Type": "application/json", "Authorization": f"Bearer {key}"}
  payload = {"model": model, "temperature": temperature, "messages": messages}
  data = await robust_post_json(url, headers, payload, ROTATOR)
  return data["choices"][0]["message"]["content"].strip()


async def llama_summarize(text: str, max_sentences: int = 3) -> str:
  """Flexible summarization using NVIDIA Small (Llama) for short text, NVIDIA Large for long context."""
  text = (text or "").strip()
  if not text:
    return ""
  
  # Use NVIDIA Large for long context (>1500 chars), NVIDIA Small for short context
  if len(text) > 1500:
    logger.info(f"[SUMMARIZER] Using NVIDIA Large for long context ({len(text)} chars)")
    return await nvidia_large_summarize(text, max_sentences)
  else:
    logger.info(f"[SUMMARIZER] Using NVIDIA Small for short context ({len(text)} chars)")
    return await nvidia_small_summarize(text, max_sentences)

async def nvidia_small_summarize(text: str, max_sentences: int = 3) -> str:
  """Summarization using NVIDIA Small (Llama) for short text."""
  system = (
    "You are a precise summarizer. Produce a clear, faithful summary of the user's text. "
    f"Return ~{max_sentences} sentences, no comments, no preface, no markdown."
  )
  user = f"Summarize this text:\n\n{text}"
  try:
    return await llama_chat([
      {"role": "system", "content": system},
      {"role": "user", "content": user},
    ], user_id="system", context="llama_summarize")
  except Exception as e:
    logger.warning(f"NVIDIA Small summarization failed: {e}; using fallback")
    return naive_fallback(text, max_sentences)

async def nvidia_large_summarize(text: str, max_sentences: int = 3) -> str:
  """Summarization using NVIDIA Large (GPT-OSS) for long context."""
  system = (
    "You are a precise summarizer. Produce a clear, faithful summary of the user's text. "
    f"Return ~{max_sentences} sentences, no comments, no preface, no markdown."
  )
  user = f"Summarize this text:\n\n{text}"
  try:
    # Track model usage for analytics
    try:
        from utils.analytics import get_analytics_tracker
        tracker = get_analytics_tracker()
        if tracker:
            await tracker.track_model_usage(
                user_id="system",
                model_name=os.getenv("NVIDIA_LARGE", "openai/gpt-oss-120b"),
                provider="nvidia_large",
                context="summarization",
                metadata={"text_length": len(text)}
            )
    except Exception:
        pass
    return await nvidia_large_chat_completion(system, user, ROTATOR, user_id="system", context="summarization")
  except Exception as e:
    logger.warning(f"NVIDIA Large summarization failed: {e}; using fallback")
    return naive_fallback(text, max_sentences)


def naive_fallback(text: str, max_sentences: int = 3) -> str:
  parts = [p.strip() for p in text.split('. ') if p.strip()]
  return '. '.join(parts[:max_sentences])


async def summarize_text(text: str, max_sentences: int = 6, chunk_size: int = 2500) -> str:
  """Hierarchical summarization for long texts using flexible model selection."""
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

  # Process chunks with flexible model selection
  partials = []
  for ch in chunks:
    partials.append(await llama_summarize(ch, max_sentences=3))
    await asyncio.sleep(0)
  
  # Combine and summarize with flexible model selection
  combined = '\n'.join(partials)
  return await llama_summarize(combined, max_sentences=max_sentences)


async def clean_chunk_text(text: str) -> str:
  """Use Qwen LLM to remove headers/footers and personally identifying/institution boilerplate.
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
    # Track model usage for analytics
    try:
        from utils.analytics import get_analytics_tracker
        tracker = get_analytics_tracker()
        if tracker:
            await tracker.track_model_usage(
                user_id="system",
                model_name=os.getenv("NVIDIA_SMALL", "meta/llama-3.1-8b-instruct"),
                provider="nvidia",
                context="content_cleaning",
                metadata={"text_length": len(text)}
            )
    except Exception:
        pass
    # Use Qwen for better content cleaning
    return await qwen_chat_completion(system, user, ROTATOR, user_id="system", context="content_cleaning")
  except Exception as e:
    logger.warning(f"Qwen cleaning failed: {e}; returning original text")
    return content

async def qwen_summarize(text: str, max_sentences: int = 3) -> str:
  """Use Qwen for better summarization with thinking mode."""
  text = (text or "").strip()
  if not text:
    return ""
  system = (
    "You are a precise summarizer. Produce a clear, faithful summary of the user's text. "
    f"Return ~{max_sentences} sentences, no comments, no preface, no markdown."
  )
  user = f"Summarize this text:\n\n{text}"
  try:
    # Track model usage for analytics
    try:
        from utils.analytics import get_analytics_tracker
        tracker = get_analytics_tracker()
        if tracker:
            await tracker.track_model_usage(
                user_id="system",
                model_name=os.getenv("NVIDIA_SMALL", "meta/llama-3.1-8b-instruct"),
                provider="nvidia",
                context="qwen_summarization",
                metadata={"text_length": len(text)}
            )
    except Exception:
        pass
    return await qwen_chat_completion(system, user, ROTATOR, user_id="system", context="qwen_summarization")
  except Exception as e:
    logger.warning(f"Qwen summarization failed: {e}; using fallback")
    return naive_fallback(text, max_sentences)


# Backward-compatible name used by app.py
async def cheap_summarize(text: str, max_sentences: int = 3) -> str:
  """Backward-compatible summarization with flexible model selection."""
  return await llama_summarize(text, max_sentences)