# ────────────────────────────── utils/chunker.py ──────────────────────────────
import re
from typing import List, Dict, Any
from .summarizer import cheap_summarize
from .common import split_sentences, slugify
from .logger import get_logger

# Heuristic "semantic" chunker:
# - Split by headings / numbered sections if present
# - Ensure each chunk ~ 300-600 words (configurable)
# - Generate a short summary + topic name

MAX_WORDS = 500
MIN_WORDS = 150
logger = get_logger("CHUNKER", __name__)

def _by_headings(text: str):
    # split on markdown-like or outline headings
    pattern = r"(?m)^(#{1,6}\s.*|[0-9]+\.\s+[^\n]+|[A-Z][A-Za-z0-9\s\-]{2,}\n[-=]{3,})\s*$"
    parts = []
    last = 0
    for m in re.finditer(pattern, text):
        start = m.start()
        if start > last:
            parts.append(text[last:start])
        parts.append(text[start:m.end()])
        last = m.end()
    if last < len(text):
        parts.append(text[last:])
    if not parts:
        parts = [text]
    return parts


def build_cards_from_pages(pages: List[Dict[str, Any]], filename: str, user_id: str, project_id: str) -> List[Dict[str, Any]]:
    # Concatenate pages but keep page spans for metadata
    full = ""
    page_markers = []
    for p in pages:
        start = len(full)
        full += f"\n\n[[Page {p['page_num']}]]\n{p.get('text','').strip()}\n"
        page_markers.append((p['page_num'], start, len(full)))

    # First split by headings
    coarse = _by_headings(full)

    # Then pack into 150-500 word chunks
    cards = []
    buf = []
    buf_words = 0
    start_idx = 0
    for block in coarse:
        words = block.split()
        if not words:
            continue
        if buf_words + len(words) > MAX_WORDS and buf_words >= MIN_WORDS:
            cards.append(" ".join(buf))
            buf, buf_words = [], 0
            start_idx = len(" ".join(coarse[:coarse.index(block)]))  # approximate
        buf.extend(words)
        buf_words += len(words)
    if buf_words > 0:
        cards.append(" ".join(buf))

    # Build card dicts
    out = []
    for i, content in enumerate(cards, 1):
        topic = cheap_summarize(content, max_sentences=1)
        if not topic:
            topic = content[:80] + "..."
        summary = cheap_summarize(content, max_sentences=3)
        # Estimate page span
        first_page = pages[0]['page_num'] if pages else 1
        last_page = pages[-1]['page_num'] if pages else 1
        out.append({
            "user_id": user_id,
            "project_id": project_id,
            "filename": filename,
            "topic_name": topic[:120],
            "summary": summary,
            "content": content,
            "page_span": [first_page, last_page],
            "card_id": f"{slugify(filename)}-c{i:04d}"
        })
    logger.info(f"Built {len(out)} cards from {len(pages)} pages for {filename}")
    return out
