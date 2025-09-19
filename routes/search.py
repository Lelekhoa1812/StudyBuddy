# routes/search.py
import re, asyncio, time, json
from typing import List, Dict, Any, Tuple
from helpers.setup import logger, embedder, gemini_rotator, nvidia_rotator
from utils.api.router import select_model, generate_answer_with_model
from utils.service.summarizer import llama_summarize


async def duckduckgo_search(query: str, max_results: int = 30) -> List[str]:
    """Lightweight DuckDuckGo HTML search scraper returning result URLs."""
    import httpx
    from urllib.parse import urlparse, parse_qs, unquote
    urls: List[str] = []
    try:
        t0 = time.perf_counter()
        q = re.sub(r"\s+", "+", (query or "").strip())
        if not q:
            return []
        # Use lite HTML endpoint directly to avoid 302 and heavier markup
        search_url = f"https://html.duckduckgo.com/html/?q={q}"
        headers = {"User-Agent": "Mozilla/5.0 (compatible; StudyBuddy/1.0)"}
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, headers=headers) as client:
            r = await client.get(search_url)
            html = r.text
            # First, capture anchors with DDG result classes
            for m in re.finditer(r'<a[^>]+class="([^"]*result__a[^"]*)"[^>]+href="([^"]+)"', html):
                href = m.group(2)
                # DDG often wraps URLs like /l/?kh=1&uddg=<encoded>
                if href.startswith('/l/?'):
                    try:
                        parsed = urlparse(href)
                        uddg = parse_qs(parsed.query).get('uddg', [])
                        if uddg:
                            url = unquote(uddg[0])
                        else:
                            continue
                    except Exception:
                        continue
                else:
                    url = href
                if "duckduckgo.com" in url:
                    continue
                if url.startswith('http'):
                    urls.append(url)
            # Fallback: capture any anchor with href and try to unwrap uddg
            if len(urls) < max_results:
                for m in re.finditer(r'<a[^>]+href="([^"]+)"', html):
                    href = m.group(1)
                    if href.startswith('/l/?'):
                        try:
                            parsed = urlparse(href)
                            uddg = parse_qs(parsed.query).get('uddg', [])
                            if uddg:
                                url = unquote(uddg[0])
                            else:
                                continue
                        except Exception:
                            continue
                    else:
                        url = href
                    if "duckduckgo.com" in url:
                        continue
                    if url.startswith('http'):
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
            ctype = r2.headers.get("content-type", "").lower()
            if any(binmt in ctype for binmt in ("image/", "video/", "audio/", "application/zip")):
                logger.info(f"[SEARCH] Skipping non-text content: {url} ({ctype})")
                return ""
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



# ────────────────────────────── LLM-Enhanced Search Planning ──────────────────
async def generate_query_variations_llm(question: str, max_variations: int = 5) -> List[str]:
    """Use NVIDIA small model to expand queries for better recall."""
    system = (
        "You are an expert at query expansion and reformulation. Given a user question, "
        "produce 3-5 alternative ways to phrase it for web search.\n"
        "Focus on synonyms, technical terms, broader/narrower scopes.\n"
        "Return one variation per line, no numbering."
    )
    user = f"Original question: {question}\n\nVariations:"
    try:
        selection = {"provider": "nvidia", "model": "meta/llama-3.1-8b-instruct"}
        text = await generate_answer_with_model(selection, system, user, gemini_rotator, nvidia_rotator)
        # Remove meta lines like "Here are ..." or numbering
        raw_lines = [v.strip() for v in text.split('\n') if v.strip()]
        variations = []
        for v in raw_lines:
            if re.match(r"^(here (are|is)|i suggest|variations|alternative|possible queries)\b", v.strip().lower()):
                continue
            v = re.sub(r"^[-*\d\.\)\s]+", "", v).strip()
            if len(v) >= 8:
                variations.append(v)
        uniq = []
        seen = set()
        for v in variations:
            k = v.lower()
            if k not in seen:
                seen.add(k)
                uniq.append(v)
        if question not in uniq:
            uniq.insert(0, question)
        return uniq[:max_variations]
    except Exception as e:
        logger.warning(f"[SEARCH] LLM variations failed: {e}")
        return [question]


async def plan_subqueries(question: str) -> List[str]:
    """Plan sub-queries using NVIDIA for simple, Gemini for complex questions."""
    selection = select_model(question=question, context=question)
    system = (
        "You are a planning agent. Break the user's question into 3-6 focused sub-queries "
        "that, when searched separately, will comprehensively answer the question.\n"
        "Return a JSON array of strings only."
    )
    user = f"Question: {question}\nReturn JSON array only."
    try:
        text = await generate_answer_with_model(selection, system, user, gemini_rotator, nvidia_rotator)
        try:
            arr = json.loads(text)
            if isinstance(arr, list) and all(isinstance(x, str) for x in arr):
                out = []
                seen = set()
                for q in arr:
                    k = q.strip().lower()
                    if k and k not in seen:
                        seen.add(k)
                        out.append(q.strip())
                if out:
                    return out[:6]
        except json.JSONDecodeError:
            pass
        return await generate_query_variations_llm(question, max_variations=5)
    except Exception as e:
        logger.warning(f"[SEARCH] Planning failed, using variations: {e}")
        return await generate_query_variations_llm(question, max_variations=5)


def _cosine_similarity(a, b):
    import numpy as np
    denom = (np.linalg.norm(a) * np.linalg.norm(b)) or 1.0
    return float(np.dot(a, b) / denom)


async def plan_and_build_web_context(question: str, max_web: int = 30, per_query: int = 6, top_k: int = 12,
                                     dedup_threshold: float = 0.90) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Plan sub-queries with LLM, search/fetch per sub-query, summarize and deduplicate
    semantically similar snippets, and return fused context + sources.
    - max_web: total budget across all sub-queries
    - per_query: max URLs per sub-query
    - top_k: final number of fused snippets to keep
    - dedup_threshold: cosine similarity threshold to drop near-duplicates
    """
    import numpy as np
    subqueries = await plan_subqueries(question)
    if not subqueries:
        subqueries = [question]

    per_q = max(3, min(per_query, max_web // max(1, len(subqueries))))

    snippets: List[Tuple[float, str, Dict[str, Any]]] = []  # (score, text, meta)
    q_vec = np.array(embedder.embed([question])[0], dtype="float32")

    # Concurrency limiter to avoid hammering
    sem = asyncio.Semaphore(8)

    async def process_url(url: str) -> Tuple[float, str, Dict[str, Any]]:
        async with sem:
            txt = await fetch_readable(url)
            if not txt or len(txt) < 200:
                return 0.0, "", {}
            try:
                summary = await llama_summarize(txt[:6000], max_sentences=4)
            except Exception:
                summary = txt[:1000]
            v = np.array(embedder.embed([summary])[0], dtype="float32")
            sim = _cosine_similarity(q_vec, v)
            meta = {"url": url, "topic_name": summary.split('\n')[0][:120], "score": float(sim), "kind": "web"}
            return sim, summary, meta

    for sq in subqueries:
        urls = await duckduckgo_search(sq, max_results=per_q)
        if not urls:
            continue
        tasks = [asyncio.create_task(process_url(u)) for u in urls]
        results = await asyncio.gather(*tasks)
        for sim, summary, meta in results:
            if meta and summary:
                snippets.append((sim, summary, meta))

    if not snippets:
        return "", []

    # Deduplicate by URL and semantic similarity
    snippets.sort(key=lambda x: x[0], reverse=True)
    kept_texts: List[str] = []
    kept_vecs: List[List[float]] = []
    kept_meta: List[Dict[str, Any]] = []
    seen_urls = set()
    for score, text, meta in snippets:
        url = meta.get("url")
        if url in seen_urls:
            continue
        v = embedder.embed([text])[0]
        is_dup = False
        for kv in kept_vecs:
            if _cosine_similarity(np.array(v, dtype="float32"), np.array(kv, dtype="float32")) >= dedup_threshold:
                is_dup = True
                break
        if is_dup:
            continue
        seen_urls.add(url)
        kept_texts.append(text)
        kept_vecs.append(v)
        kept_meta.append(meta)
        if len(kept_texts) >= top_k:
            break

    # Fused intro summary
    try:
        fused_intro = await llama_summarize("\n\n".join(kept_texts)[:10000], max_sentences=5)
    except Exception:
        fused_intro = ""

    from utils.service.common import trim_text
    blocks = []
    if fused_intro:
        blocks.append(f"[WEB_FUSED_SUMMARY] {trim_text(fused_intro, 1800)}")
    for text, meta in zip(kept_texts, kept_meta):
        title_line = (text.splitlines()[0][:120] if text else meta.get("topic_name", "Web")).strip()
        blocks.append(f"[WEB: {title_line}] {trim_text(text, 2000)}")
    composed = "\n\n---\n\n".join(blocks)
    return composed, kept_meta
