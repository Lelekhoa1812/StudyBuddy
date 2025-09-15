# ────────────────────────────── utils/chunker.py ──────────────────────────────
import re
from typing import List, Dict, Any
from utils.service.summarizer import cheap_summarize, clean_chunk_text
from utils.service.common import split_sentences, slugify
from ..logger import get_logger

# Enhanced semantic chunker with overlap and better structure:
# - Split by headings / numbered sections if present
# - Ensure each chunk ~ 300-600 words (configurable)
# - Add overlap between chunks for better context preservation
# - Generate a short summary + topic name
# - Better handling of semantic boundaries

MAX_WORDS = 500
MIN_WORDS = 150
OVERLAP_WORDS = 50  # Overlap between chunks for better context
logger = get_logger("CHUNKER", __name__)


def _by_headings(text: str):
    # Enhanced split on markdown-like or outline headings with better patterns
    patterns = [
        r"(?m)^(#{1,6}\s.*)\s*$",  # Markdown headers
        r"(?m)^([0-9]+\.\s+[^\n]+)\s*$",  # Numbered sections
        r"(?m)^([A-Z][A-Za-z0-9\s\-]{2,}\n[-=]{3,})\s*$",  # Underlined headers
        r"(?m)^(Chapter\s+\d+.*|Section\s+\d+.*)\s*$",  # Chapter/Section headers
        r"(?m)^(Abstract|Introduction|Conclusion|References|Bibliography)\s*$",  # Common academic sections
    ]
    
    parts = []
    last = 0
    all_matches = []
    
    # Find all matches from all patterns
    for pattern in patterns:
        for m in re.finditer(pattern, text):
            all_matches.append((m.start(), m.end(), m.group(1).strip()))
    
    # Sort matches by position
    all_matches.sort(key=lambda x: x[0])
    
    # Split text based on matches
    for start, end, header in all_matches:
        if start > last:
            parts.append(text[last:start])
        parts.append(text[start:end])
        last = end
    
    if last < len(text):
        parts.append(text[last:])
    
    if not parts:
        parts = [text]
    
    return parts


def _create_overlapping_chunks(text_blocks: List[str]) -> List[str]:
    """Create overlapping chunks from text blocks for better context preservation"""
    chunks = []
    
    for i, block in enumerate(text_blocks):
        words = block.split()
        if not words:
            continue
            
        # If block is small enough, use as-is
        if len(words) <= MAX_WORDS:
            chunks.append(block)
            continue
        
        # Split large blocks with overlap
        start = 0
        while start < len(words):
            end = min(start + MAX_WORDS, len(words))
            chunk_words = words[start:end]
            
            # Add overlap from previous chunk if available
            if start > 0 and len(chunks) > 0:
                prev_words = chunks[-1].split()
                overlap_start = max(0, len(prev_words) - OVERLAP_WORDS)
                overlap_words = prev_words[overlap_start:]
                chunk_words = overlap_words + chunk_words
            
            chunks.append(" ".join(chunk_words))
            start = end - OVERLAP_WORDS  # Overlap with next chunk
    
    return chunks


async def build_cards_from_pages(pages: List[Dict[str, Any]], filename: str, user_id: str, project_id: str) -> List[Dict[str, Any]]:
    # Concatenate pages but keep page spans for metadata
    full = ""
    page_markers = []
    for p in pages:
        start = len(full)
        full += f"\n\n[[Page {p['page_num']}]]\n{p.get('text','').strip()}\n"
        page_markers.append((p['page_num'], start, len(full)))

    # First split by headings
    coarse = _by_headings(full)

    # Create overlapping chunks for better context preservation
    cards = _create_overlapping_chunks(coarse)

    # Build card dicts
    out = []
    for i, raw_content in enumerate(cards, 1):
        # Clean with LLM to remove headers/footers and IDs
        cleaned = await clean_chunk_text(raw_content)
        topic = await cheap_summarize(cleaned, max_sentences=1)
        if not topic:
            topic = cleaned[:80] + "..."
        summary = await cheap_summarize(cleaned, max_sentences=3)
        # Estimate page span
        first_page = pages[0]['page_num'] if pages else 1
        last_page = pages[-1]['page_num'] if pages else 1
        out.append({
            "user_id": user_id,
            "project_id": project_id,
            "filename": filename,
            "topic_name": topic[:120],
            "summary": summary,
            "content": cleaned,
            "page_span": [first_page, last_page],
            "card_id": f"{slugify(filename)}-c{i:04d}"
        })
    logger.info(f"Built {len(out)} cards from {len(pages)} pages for {filename}")
    return out
