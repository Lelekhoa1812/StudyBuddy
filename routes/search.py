# routes/search.py
import re, asyncio, time
from typing import List, Dict, Any, Tuple
from helpers.setup import logger, embedder, gemini_rotator, nvidia_rotator


async def duckduckgo_search(query: str, max_results: int = 30) -> List[str]:
    """Lightweight DuckDuckGo HTML search scraper returning result URLs."""
    import httpx
    urls: List[str] = []
    try:
        t0 = time.perf_counter()
        q = re.sub(r"\s+", "+", (query or "").strip())
        if not q:
            return []
        search_url = f"https://duckduckgo.com/html/?q={q}"
        headers = {"User-Agent": "Mozilla/5.0 (compatible; StudyBuddy/1.0)"}
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, headers=headers) as client:
            r = await client.get(search_url)
            html = r.text
            for m in re.finditer(r'<a[^>]+class=\"result__a[^\"]*\"[^>]+href=\"(https?://[^\"]+)\"', html):
                url = m.group(1)
                if "duckduckgo.com" in url:
                    continue
                urls.append(url)
            if len(urls) < max_results:
                for m in re.finditer(r'<a[^>]+href=\"(https?://[^\"]+)\"', html):
                    url = m.group(1)
                    if "duckduckgo.com" in url:
                        continue
                    urls.append(url)
            seen = set()
            deduped = []
            for u in urls:
                if u not in seen:
                    seen.add(u)
                    deduped.append(u)
            out = deduped[:max_results]
            logger.info(f"[SEARCH] DDG results: requested={max_results}, got={len(out)} in {time.perf_counter() - t0:.2f}s")
            return out
    except Exception as e:
        logger.warning(f"[SEARCH] Web search failed: {e}")
        return []


async def fetch_readable(url: str) -> str:
    """Fetch readable text using Jina Reader proxy if possible, fallback to raw HTML text."""
    import httpx
    headers = {"User-Agent": "Mozilla/5.0 (compatible; StudyBuddy/1.0)"}
    reader_url = f"https://r.jina.ai/{url}"
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, headers=headers) as client:
            r = await client.get(reader_url)
            if r.status_code == 200 and r.text and len(r.text) > 100:
                logger.info(f"[SEARCH] Reader fetched: {url}")
                return r.text.strip()
            r2 = await client.get(url)
            logger.info(f"[SEARCH] Direct fetched: {url} (reader not usable)")
            return (r2.text or "").strip()
    except Exception as e:
        logger.warning(f"[SEARCH] Fetch failed for {url}: {e}")
        return ""


async def build_web_context(question: str, max_web: int = 30, top_k: int = 10) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Perform search, fetch pages, rank by similarity to the question, and
    return a composed context string plus sources metadata with URLs.
    """
    t0 = time.perf_counter()
    urls = await duckduckgo_search(question, max_results=max_web)
    if not urls:
        return "", []

    async def _fetch(u: str):
        txt = await fetch_readable(u)
        return u, txt

    tasks = [asyncio.create_task(_fetch(u)) for u in urls]
    fetched = await asyncio.gather(*tasks)
    web_docs = [(u, t) for (u, t) in fetched if t and len(t) > 200]
    logger.info(f"[SEARCH] Fetched pages: total_urls={len(urls)}, usable={len(web_docs)}")
    if not web_docs:
        return "", []

    import numpy as np
    q_vec = embedder.embed([question])[0]
    qv = np.array(q_vec, dtype="float32")
    scored: List[Dict[str, Any]] = []
    for url, text in web_docs:
        snippet = text[:4000]
        v = np.array(embedder.embed([snippet])[0], dtype="float32")
        denom = (np.linalg.norm(qv) * np.linalg.norm(v)) or 1.0
        sim = float(np.dot(qv, v) / denom)
        scored.append({"url": url, "text": snippet, "score": sim})
    scored.sort(key=lambda x: x["score"], reverse=True)
    top_web = scored[:min(top_k, len(scored))]
    logger.info(f"[SEARCH] Ranked web docs: kept_top={len(top_web)} (top_k={top_k}) in {time.perf_counter() - t0:.2f}s")

    # Compose context and sources meta
    from utils.service.common import trim_text
    web_contexts: List[str] = []
    web_sources_meta: List[Dict[str, Any]] = []
    for w in top_web:
        title_line = (w["text"].splitlines()[0][:120] if w["text"] else "Web").strip()
        web_contexts.append(f"[WEB: {title_line}] {trim_text(w['text'], 2000)}")
        web_sources_meta.append({
            "url": w["url"],
            "topic_name": title_line,
            "score": float(w["score"]),
            "kind": "web"
        })
    composed = "\n\n---\n\n".join(web_contexts)
    return composed, web_sources_meta


