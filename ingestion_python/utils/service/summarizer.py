import re
from typing import List
from utils.logger import get_logger

logger = get_logger("SUM", __name__)


async def clean_chunk_text(text: str) -> str:
  """Clean and normalize text for processing."""
  if not text:
    return ""
  
  # Remove extra whitespace and normalize
  text = " ".join(text.split())
  
  # Remove common artifacts
  text = text.replace("\\n", " ").replace("\\t", " ")
  
  return text.strip()


async def cheap_summarize(text: str, max_sentences: int = 3) -> str:
  """Simple text-based summarization without external APIs."""
  if not text or len(text.strip()) < 50:
    return text.strip()
  
  try:
    # Simple extractive summarization: take first few sentences
    sentences = re.split(r'[.!?]+', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    
    if len(sentences) <= max_sentences:
      return text.strip()
    
    # Take first max_sentences sentences
    summary_sentences = sentences[:max_sentences]
    summary = '. '.join(summary_sentences)
    
    # Add period if it doesn't end with punctuation
    if not summary.endswith(('.', '!', '?')):
      summary += '.'
    
    return summary
    
  except Exception as e:
    logger.warning(f"[SUM] Summarization failed: {e}")
    # Fallback: return first part of text
    return text[:200] + "..." if len(text) > 200 else text