# routes/search.py
import re, asyncio, time, json
from typing import List, Dict, Any, Tuple
from helpers.setup import logger, embedder, gemini_rotator, nvidia_rotator
from utils.api.router import select_model, generate_answer_with_model, qwen_chat_completion, nvidia_large_chat_completion
from utils.service.summarizer import llama_summarize
from utils.analytics import get_analytics_tracker


async def extract_search_keywords(user_query: str, nvidia_rotator) -> List[str]:
    """Extract intelligent search keywords from user query using NVIDIA Large agent."""
    if not nvidia_rotator:
        # Fallback: simple keyword extraction
        words = re.findall(r'\b\w+\b', user_query.lower())
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'can', 'what', 'how', 'why', 'when', 'where', 'who'}
        keywords = [w for w in words if len(w) > 2 and w not in stop_words]
        return keywords[:5]
    
    try:
        sys_prompt = """You are an expert at extracting search keywords from user queries. 
Extract 3-5 key terms that would be most effective for web search engines.
Focus on:
- Main concepts and technical terms
- Specific entities (names, places, technologies)
- Action words that describe what the user wants to know
- Avoid common words like 'what', 'how', 'the', 'a', etc.

Return only the keywords, separated by spaces, no other text."""
        
        user_prompt = f"User query: {user_query}\n\nExtract search keywords:"
        
        # Track search agent usage
        tracker = get_analytics_tracker()
        if tracker:
            await tracker.track_agent_usage(
                user_id="system",  # Search is system-level
                agent_name="search",
                action="search",
                context="web_search",
                metadata={"query": user_query}
            )
        
        # Use NVIDIA Large for better keyword extraction
        response = await nvidia_large_chat_completion(sys_prompt, user_prompt, nvidia_rotator, user_id, "search_keyword_extraction")
        
        keywords = [kw.strip() for kw in response.split() if kw.strip()]
        return keywords[:5] if keywords else [user_query]
        
    except Exception as e:
        logger.warning(f"[SEARCH] Keyword extraction failed: {e}")
        # Fallback
        words = re.findall(r'\b\w+\b', user_query.lower())
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'can', 'what', 'how', 'why', 'when', 'where', 'who'}
        keywords = [w for w in words if len(w) > 2 and w not in stop_words]
        return keywords[:5]


async def generate_search_strategies(user_query: str, nvidia_rotator) -> List[Dict[str, Any]]:
    """Generate multiple search strategies for comprehensive coverage."""
    if not nvidia_rotator:
        return [{"strategy": "direct", "query": user_query, "priority": 1.0}]
    
    try:
        sys_prompt = """You are an expert search strategist. Given a user query, generate 3-4 different search strategies:
1. Direct search (exact terms)
2. Broad search (general concepts)
3. Technical search (specific terminology)
4. Alternative search (synonyms/related terms)

For each strategy, provide:
- strategy_name: short descriptive name
- query: the search query to use
- priority: importance score 0.0-1.0

Return as JSON array of objects."""
        
        user_prompt = f"User query: {user_query}\n\nGenerate search strategies:"
        
        # Use NVIDIA Large for better strategy generation
        response = await nvidia_large_chat_completion(sys_prompt, user_prompt, nvidia_rotator, user_id, "search_keyword_extraction")
        
        try:
            strategies = json.loads(response)
            if isinstance(strategies, list):
                return strategies[:4]  # Limit to 4 strategies
        except json.JSONDecodeError:
            pass
        
        # Fallback to simple strategies
        return [
            {"strategy": "direct", "query": user_query, "priority": 1.0},
            {"strategy": "broad", "query": " ".join(user_query.split()[:3]), "priority": 0.7},
            {"strategy": "technical", "query": user_query + " technical", "priority": 0.8}
        ]
        
    except Exception as e:
        logger.warning(f"[SEARCH] Strategy generation failed: {e}")
        return [{"strategy": "direct", "query": user_query, "priority": 1.0}]


async def search_engine_query(keywords: List[str], max_results: int = 30) -> List[Dict[str, str]]:
    """Search using DuckDuckGo and return structured results with titles and URLs."""
    import httpx
    from urllib.parse import urlparse, parse_qs, unquote
    results = []
    
    if not keywords:
        return results
    
    try:
        # Create search query from keywords
        query = " ".join(keywords)
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
        
        # Try multiple DuckDuckGo endpoints
        search_urls = [
            f"https://html.duckduckgo.com/html/?q={query}",
            f"https://duckduckgo.com/html/?q={query}",
            f"https://duckduckgo.com/?q={query}",
        ]
        
        html = ""
        for search_url in search_urls:
            try:
                async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, headers=headers) as client:
                    r = await client.get(search_url)
                    if r.status_code == 200:
                        html = r.text
                        logger.info(f"[SEARCH] Successfully fetched from: {search_url}")
                        break
            except Exception as e:
                logger.warning(f"[SEARCH] Failed to fetch from {search_url}: {e}")
                continue
        
        if not html:
            logger.error("[SEARCH] Failed to fetch from all DuckDuckGo endpoints")
            return []
        
        # Debug: Log a sample of the HTML to see the structure
        logger.info(f"[SEARCH] HTML sample (first 2000 chars): {html[:2000]}")
        
        # Multiple regex patterns to try for different DuckDuckGo layouts
        patterns = [
            # Pattern 1: Modern DuckDuckGo result structure
            r'<a[^>]+href="([^"]+)"[^>]*class="[^"]*result__a[^"]*"[^>]*>([^<]+)</a>',
            # Pattern 2: Alternative result structure
            r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>([^<]+)</a>',
            # Pattern 3: General result class
            r'<a[^>]+href="([^"]+)"[^>]*class="[^"]*result[^"]*"[^>]*>([^<]+)</a>',
            # Pattern 4: Any link with href containing http (fallback)
            r'<a[^>]+href="(https?://[^"]+)"[^>]*>([^<]+)</a>',
            # Pattern 5: More flexible pattern
            r'<a[^>]+href="([^"]+)"[^>]*>([^<]+)</a>',
        ]
        
        for pattern_idx, pattern in enumerate(patterns):
            logger.info(f"[SEARCH] Trying pattern {pattern_idx + 1}: {pattern}")
            matches = list(re.finditer(pattern, html))
            logger.info(f"[SEARCH] Pattern {pattern_idx + 1} found {len(matches)} matches")
            
            for match in matches:
                href = match.group(1)
                title = match.group(2).strip()
                
                logger.info(f"[SEARCH] Found match - href: {href[:100]}, title: {title[:50]}")
                
                # Skip if title is too short or contains only symbols
                if len(title) < 3 or not re.search(r'[a-zA-Z]', title):
                    logger.info(f"[SEARCH] Skipping due to short/invalid title: {title}")
                    continue
                
                # Handle DuckDuckGo URL unwrapping
                if href.startswith('/l/?'):
                    try:
                        parsed = urlparse(href)
                        uddg = parse_qs(parsed.query).get('uddg', [])
                        if uddg:
                            url = unquote(uddg[0])
                            logger.info(f"[SEARCH] Unwrapped URL: {url[:100]}")
                        else:
                            logger.info(f"[SEARCH] No uddg param found in: {href}")
                            continue
                    except Exception as e:
                        logger.info(f"[SEARCH] URL unwrapping failed: {e}")
                        continue
                else:
                    url = href
                
                # Skip DuckDuckGo internal links and invalid URLs
                if ("duckduckgo.com" in url or 
                    not url.startswith('http') or 
                    not title or
                    any(r["url"] == url for r in results)):
                    logger.info(f"[SEARCH] Skipping URL: {url[:100]} (duckduckgo={('duckduckgo.com' in url)}, http={url.startswith('http')}, duplicate={any(r['url'] == url for r in results)})")
                    continue
                
                logger.info(f"[SEARCH] Adding result: {url[:100]} - {title[:50]}")
                results.append({
                    "url": url,
                    "title": title,
                    "keywords": keywords
                })
                
                # Stop if we have enough results
                if len(results) >= max_results:
                    break
            
            # If we found results with this pattern, stop trying others
            if results:
                break
        
        logger.info(f"[SEARCH] Final results: {len(results)} URLs found")
        for i, result in enumerate(results[:5]):  # Log first 5 results
            logger.info(f"[SEARCH] Result {i+1}: {result['title'][:50]}... -> {result['url']}")
        
        return results[:max_results]
            
    except Exception as e:
        logger.warning(f"[SEARCH] Search engine query failed: {e}")
        return []


async def multi_strategy_search(strategies: List[Dict[str, Any]], max_results_per_strategy: int = 8) -> List[Dict[str, str]]:
    """Execute multiple search strategies and combine results."""
    all_results = []
    seen_urls = set()
    
    # Sort strategies by priority
    strategies.sort(key=lambda x: x.get("priority", 0.5), reverse=True)
    
    for strategy in strategies:
        query = strategy.get("query", "")
        if not query:
            continue
            
        # Extract keywords from the strategy query
        keywords = await extract_search_keywords(query, nvidia_rotator)
        if not keywords:
            keywords = query.split()
            
        results = await search_engine_query(keywords, max_results=max_results_per_strategy)
        
        # Add strategy info to results
        for result in results:
            if result["url"] not in seen_urls:
                result["strategy"] = strategy.get("strategy", "unknown")
                result["priority"] = strategy.get("priority", 0.5)
                all_results.append(result)
                seen_urls.add(result["url"])
    
    # Sort by priority and limit total results
    all_results.sort(key=lambda x: x.get("priority", 0.5), reverse=True)
    return all_results[:max_results_per_strategy * len(strategies)]


async def fetch_and_process_content(url: str, title: str, user_query: str, nvidia_rotator) -> Dict[str, Any]:
    """Fetch content and use NVIDIA agent to extract relevant information."""
    import httpx
    headers = {"User-Agent": "Mozilla/5.0 (compatible; StudyBuddy/1.0)"}
    
    try:
        # Try Jina Reader first for better content extraction
        reader_url = f"https://r.jina.ai/{url}"
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, headers=headers) as client:
            r = await client.get(reader_url)
            if r.status_code == 200 and r.text and len(r.text) > 100:
                content = r.text.strip()
            else:
                # Fallback to direct fetch
                r2 = await client.get(url)
                ctype = r2.headers.get("content-type", "").lower()
                if any(binmt in ctype for binmt in ("image/", "video/", "audio/", "application/zip")):
                    return {"url": url, "title": title, "relevant_content": "", "summary": "", "relevance_score": 0.0}
                content = (r2.text or "").strip()
        
        if not content or len(content) < 200:
            return {"url": url, "title": title, "relevant_content": "", "summary": "", "relevance_score": 0.0}
        
        # Use NVIDIA agent to extract relevant information
        relevant_content = await extract_relevant_content(content, user_query, nvidia_rotator)
        
        if not relevant_content:
            return {"url": url, "title": title, "relevant_content": "", "summary": "", "relevance_score": 0.0}
        
        # Generate summary of the relevant content
        summary = await generate_content_summary(relevant_content, nvidia_rotator)
        
        # Calculate relevance score
        relevance_score = calculate_relevance_score(relevant_content, user_query)
        
        return {
            "url": url,
            "title": title,
            "relevant_content": relevant_content,
            "summary": summary,
            "relevance_score": relevance_score
        }
        
    except Exception as e:
        logger.warning(f"[SEARCH] Content processing failed for {url}: {e}")
        return {"url": url, "title": title, "relevant_content": "", "summary": "", "relevance_score": 0.0}


async def extract_relevant_content(content: str, user_query: str, nvidia_rotator) -> str:
    """Use NVIDIA Large agent to extract only the content relevant to the user query."""
    if not nvidia_rotator:
        # Fallback: return first 2000 chars
        return content[:2000]
    
    try:
        # If content is too large, chunk it first
        if len(content) > 8000:
            chunks = chunk_content_intelligently(content, max_chunk_size=4000)
            relevant_chunks = []
            
            for chunk in chunks:
                if is_chunk_relevant(chunk, user_query):
                    relevant_chunks.append(chunk)
                    if len(relevant_chunks) >= 3:  # Limit to top 3 relevant chunks
                        break
            
            content = "\n\n".join(relevant_chunks)
        
        if len(content) > 4000:
            content = content[:4000]  # Truncate if still too long
        
        sys_prompt = """You are an expert at extracting relevant information from web content.
Given a user query and web content, extract ONLY the parts that directly answer or relate to the query.
- Keep the original text as much as possible
- Focus on facts, explanations, and specific details
- Remove irrelevant sections, ads, navigation, etc.
- Preserve important context and structure
- If nothing is relevant, return empty string

Return only the relevant content, no additional commentary."""
        
        user_prompt = f"User Query: {user_query}\n\nWeb Content:\n{content}\n\nExtract relevant information:"
        
        # Use NVIDIA Large for better content extraction
        response = await nvidia_large_chat_completion(sys_prompt, user_prompt, nvidia_rotator, user_id, "search_keyword_extraction")
        
        return response.strip() if response.strip() else ""
        
    except Exception as e:
        logger.warning(f"[SEARCH] Content extraction failed: {e}")
        return content[:2000]  # Fallback


async def assess_content_quality(content: str, nvidia_rotator) -> Dict[str, Any]:
    """Assess content quality using NVIDIA Large agent."""
    if not nvidia_rotator or not content:
        return {"quality_score": 0.5, "issues": [], "strengths": []}
    
    try:
        sys_prompt = """You are an expert content quality assessor. Analyze web content and provide:
1. quality_score: 0.0-1.0 (1.0 = excellent)
2. issues: list of quality problems (empty if none)
3. strengths: list of quality strengths

Consider: accuracy, completeness, clarity, authority, recency, bias, factual claims."""
        
        user_prompt = f"Assess this content quality:\n\n{content[:2000]}"
        
        # Use NVIDIA Large for better quality assessment
        response = await nvidia_large_chat_completion(sys_prompt, user_prompt, nvidia_rotator, user_id, "search_keyword_extraction")
        
        try:
            # Try to parse JSON response
            assessment = json.loads(response)
            if isinstance(assessment, dict):
                return {
                    "quality_score": float(assessment.get("quality_score", 0.5)),
                    "issues": assessment.get("issues", []),
                    "strengths": assessment.get("strengths", [])
                }
        except json.JSONDecodeError:
            pass
        
        # Fallback: simple heuristic assessment
        quality_score = 0.5
        issues = []
        strengths = []
        
        if len(content) < 100:
            issues.append("Very short content")
            quality_score -= 0.3
        elif len(content) > 2000:
            strengths.append("Comprehensive content")
            quality_score += 0.2
        
        if any(word in content.lower() for word in ['according to', 'research shows', 'studies indicate']):
            strengths.append("References sources")
            quality_score += 0.2
        
        if any(word in content.lower() for word in ['opinion', 'believe', 'think', 'feel']):
            issues.append("Contains subjective language")
            quality_score -= 0.1
        
        return {
            "quality_score": max(0.0, min(1.0, quality_score)),
            "issues": issues,
            "strengths": strengths
        }
        
    except Exception as e:
        logger.warning(f"[SEARCH] Quality assessment failed: {e}")
        return {"quality_score": 0.5, "issues": [], "strengths": []}


async def cross_validate_information(content: str, other_contents: List[str], nvidia_rotator) -> Dict[str, Any]:
    """Cross-validate information across multiple sources."""
    if not nvidia_rotator or not other_contents:
        return {"consistency_score": 0.5, "conflicts": [], "agreements": []}
    
    try:
        # Combine other contents for comparison
        comparison_text = "\n\n---\n\n".join(other_contents[:3])  # Limit to 3 sources
        
        sys_prompt = """You are an expert fact-checker. Compare information across sources and identify:
1. consistency_score: 0.0-1.0 (1.0 = fully consistent)
2. conflicts: list of contradictory information
3. agreements: list of consistent information

Focus on factual claims, statistics, and verifiable information."""
        
        user_prompt = f"Main content:\n{content[:1000]}\n\nOther sources:\n{comparison_text[:2000]}\n\nAnalyze consistency:"
        
        # Use NVIDIA Large for better cross-validation
        response = await nvidia_large_chat_completion(sys_prompt, user_prompt, nvidia_rotator, user_id, "search_keyword_extraction")
        
        try:
            validation = json.loads(response)
            if isinstance(validation, dict):
                return {
                    "consistency_score": float(validation.get("consistency_score", 0.5)),
                    "conflicts": validation.get("conflicts", []),
                    "agreements": validation.get("agreements", [])
                }
        except json.JSONDecodeError:
            pass
        
        # Fallback: simple consistency check
        return {"consistency_score": 0.7, "conflicts": [], "agreements": ["Basic information present"]}
        
    except Exception as e:
        logger.warning(f"[SEARCH] Cross-validation failed: {e}")
        return {"consistency_score": 0.5, "conflicts": [], "agreements": []}


def chunk_content_intelligently(content: str, max_chunk_size: int = 4000) -> List[str]:
    """Intelligently chunk content by paragraphs and sentences."""
    # Split by double newlines (paragraphs)
    paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
    
    chunks = []
    current_chunk = ""
    
    for paragraph in paragraphs:
        if len(current_chunk) + len(paragraph) <= max_chunk_size:
            current_chunk += paragraph + "\n\n"
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = paragraph + "\n\n"
    
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    return chunks


def is_chunk_relevant(chunk: str, user_query: str) -> bool:
    """Simple relevance check based on keyword overlap."""
    query_words = set(user_query.lower().split())
    chunk_words = set(chunk.lower().split())
    
    # Check for significant word overlap
    overlap = len(query_words.intersection(chunk_words))
    return overlap >= 2 or len(query_words.intersection(chunk_words)) / len(query_words) > 0.3


async def generate_content_summary(content: str, nvidia_rotator) -> str:
    """Generate a concise summary of the relevant content."""
    if not nvidia_rotator or not content:
        return content[:200] + "..." if len(content) > 200 else content
    
    try:
        sys_prompt = """You are an expert at creating concise summaries.
Create a brief, informative summary (2-3 sentences) that captures the key points.
Focus on the most important facts and insights.
Be clear and direct."""
        
        user_prompt = f"Summarize this content:\n\n{content}"
        
        # Use NVIDIA Large for better summarization
        response = await nvidia_large_chat_completion(sys_prompt, user_prompt, nvidia_rotator, user_id, "search_keyword_extraction")
        
        return response.strip() if response.strip() else content[:200] + "..."
        
    except Exception as e:
        logger.warning(f"[SEARCH] Summary generation failed: {e}")
        return content[:200] + "..." if len(content) > 200 else content


def calculate_relevance_score(content: str, user_query: str) -> float:
    """Calculate relevance score based on keyword overlap and content quality."""
    if not content:
        return 0.0
    
    query_words = set(user_query.lower().split())
    content_words = set(content.lower().split())
    
    # Basic keyword overlap
    overlap = len(query_words.intersection(content_words))
    overlap_score = min(overlap / len(query_words), 1.0) if query_words else 0.0
    
    # Content quality indicators
    quality_score = 0.0
    if len(content) > 100:  # Substantial content
        quality_score += 0.2
    if any(word in content.lower() for word in ['because', 'therefore', 'however', 'specifically', 'example']):  # Explanatory content
        quality_score += 0.3
    if any(char.isdigit() for char in content):  # Contains numbers/data
        quality_score += 0.2
    
    return min(overlap_score + quality_score, 1.0)


def calculate_authority_score(url: str, title: str) -> float:
    """Calculate authority score based on domain and title characteristics."""
    authority_score = 0.5  # Base score
    
    # Domain-based scoring
    domain = url.lower()
    if any(edu in domain for edu in ['.edu', '.ac.', '.university']):
        authority_score += 0.3  # Academic sources
    elif any(gov in domain for gov in ['.gov', '.govt', '.government']):
        authority_score += 0.3  # Government sources
    elif any(org in domain for org in ['.org', '.ngo', '.foundation']):
        authority_score += 0.2  # Non-profit sources
    elif any(com in domain for com in ['.com', '.net', '.co']):
        authority_score += 0.1  # Commercial sources
    
    # Title-based scoring
    title_lower = title.lower()
    if any(word in title_lower for word in ['research', 'study', 'analysis', 'report']):
        authority_score += 0.2
    if any(word in title_lower for word in ['official', 'government', 'university', 'institute']):
        authority_score += 0.2
    if any(word in title_lower for word in ['news', 'blog', 'opinion', 'personal']):
        authority_score -= 0.1
    
    return max(0.0, min(1.0, authority_score))


def calculate_freshness_score(content: str, url: str) -> float:
    """Calculate content freshness score based on temporal indicators."""
    freshness_score = 0.5  # Base score
    
    content_lower = content.lower()
    
    # Look for date indicators
    current_year = 2024
    for year in range(current_year - 5, current_year + 1):
        if str(year) in content_lower:
            if year >= current_year - 1:
                freshness_score += 0.3
            elif year >= current_year - 3:
                freshness_score += 0.1
            else:
                freshness_score -= 0.1
    
    # Look for recency indicators
    if any(word in content_lower for word in ['recent', 'latest', 'new', 'updated', 'current']):
        freshness_score += 0.2
    if any(word in content_lower for word in ['outdated', 'old', 'previous', 'former']):
        freshness_score -= 0.2
    
    return max(0.0, min(1.0, freshness_score))


async def calculate_comprehensive_score(content: str, user_query: str, url: str, title: str, 
                                      quality_assessment: Dict[str, Any], 
                                      consistency_assessment: Dict[str, Any]) -> float:
    """Calculate comprehensive relevance score combining multiple factors."""
    # Base relevance score
    relevance_score = calculate_relevance_score(content, user_query)
    
    # Quality score
    quality_score = quality_assessment.get("quality_score", 0.5)
    
    # Authority score
    authority_score = calculate_authority_score(url, title)
    
    # Freshness score
    freshness_score = calculate_freshness_score(content, url)
    
    # Consistency score
    consistency_score = consistency_assessment.get("consistency_score", 0.5)
    
    # Weighted combination
    comprehensive_score = (
        relevance_score * 0.4 +      # Most important: relevance to query
        quality_score * 0.25 +       # Content quality
        authority_score * 0.15 +     # Source authority
        freshness_score * 0.1 +      # Content freshness
        consistency_score * 0.1      # Cross-source consistency
    )
    
    return max(0.0, min(1.0, comprehensive_score))


async def build_web_context(question: str, max_web: int = 30, top_k: int = 10, status_callback=None) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Intelligent web search and content processing:
    1. Extract intelligent search keywords
    2. Search for multiple results
    3. Process each source with NVIDIA agent
    4. Structure knowledge for final prompt
    """
    t0 = time.perf_counter()
    
    # Step 1: Extract intelligent search keywords
    if status_callback:
        status_callback("searching", "Searching information...", 45)
    keywords = await extract_search_keywords(question, nvidia_rotator)
    logger.info(f"[SEARCH] Extracted keywords: {keywords}")
    
    if not keywords:
        return "", []
    
    # Step 2: Search for multiple results
    search_results = await search_engine_query(keywords, max_results=max_web)
    logger.info(f"[SEARCH] Found {len(search_results)} search results")
    
    if not search_results:
        return "", []
    
    # Step 3: Process each source with NVIDIA agent
    if status_callback:
        status_callback("processing", "Processing data...", 50)
    processing_tasks = []
    for result in search_results:
        task = fetch_and_process_content(result["url"], result["title"], question, nvidia_rotator)
        processing_tasks.append(task)
    
    processed_results = await asyncio.gather(*processing_tasks)
    
    # Step 4: Filter and rank by relevance
    relevant_results = [r for r in processed_results if r["relevance_score"] > 0.1 and r["relevant_content"]]
    relevant_results.sort(key=lambda x: x["relevance_score"], reverse=True)
    top_results = relevant_results[:top_k]
    
    logger.info(f"[SEARCH] Processed {len(relevant_results)} relevant results, using top {len(top_results)} in {time.perf_counter() - t0:.2f}s")
    
    # Step 5: Structure knowledge for final prompt
    web_contexts = []
    web_sources_meta = []
    
    for result in top_results:
        # Create structured context entry
        context_entry = f"[WEB SOURCE: {result['title']}]\n"
        context_entry += f"URL: {result['url']}\n"
        context_entry += f"Summary: {result['summary']}\n"
        context_entry += f"Relevant Content: {result['relevant_content'][:1500]}..."
        
        web_contexts.append(context_entry)
        
        # Create source metadata
        web_sources_meta.append({
            "url": result["url"],
            "topic_name": result["title"],
            "score": float(result["relevance_score"]),
            "kind": "web",
            "summary": result["summary"]
        })
    
    composed_context = "\n\n---\n\n".join(web_contexts)
    return composed_context, web_sources_meta


async def fetch_and_process_content_enhanced(url: str, title: str, user_query: str, nvidia_rotator) -> Dict[str, Any]:
    """Enhanced content processing with quality assessment and authority scoring."""
    import httpx
    headers = {"User-Agent": "Mozilla/5.0 (compatible; StudyBuddy/1.0)"}
    
    try:
        # Try Jina Reader first for better content extraction
        reader_url = f"https://r.jina.ai/{url}"
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, headers=headers) as client:
            r = await client.get(reader_url)
            if r.status_code == 200 and r.text and len(r.text) > 100:
                content = r.text.strip()
            else:
                # Fallback to direct fetch
                r2 = await client.get(url)
                ctype = r2.headers.get("content-type", "").lower()
                if any(binmt in ctype for binmt in ("image/", "video/", "audio/", "application/zip")):
                    return {"url": url, "title": title, "relevant_content": "", "summary": "", "comprehensive_score": 0.0}
                content = (r2.text or "").strip()
        
        if not content or len(content) < 200:
            return {"url": url, "title": title, "relevant_content": "", "summary": "", "comprehensive_score": 0.0}
        
        # Extract relevant content
        relevant_content = await extract_relevant_content(content, user_query, nvidia_rotator)
        
        if not relevant_content:
            return {"url": url, "title": title, "relevant_content": "", "summary": "", "comprehensive_score": 0.0}
        
        # Assess content quality
        quality_assessment = await assess_content_quality(relevant_content, nvidia_rotator)
        
        # Calculate authority and freshness scores
        authority_score = calculate_authority_score(url, title)
        freshness_score = calculate_freshness_score(relevant_content, url)
        
        # Generate summary
        summary = await generate_content_summary(relevant_content, nvidia_rotator)
        
        # Calculate base relevance score
        relevance_score = calculate_relevance_score(relevant_content, user_query)
        
        return {
            "url": url,
            "title": title,
            "relevant_content": relevant_content,
            "summary": summary,
            "relevance_score": relevance_score,
            "authority_score": authority_score,
            "freshness_score": freshness_score,
            "quality_assessment": quality_assessment
        }
        
    except Exception as e:
        logger.warning(f"[SEARCH] Enhanced content processing failed for {url}: {e}")
        return {"url": url, "title": title, "relevant_content": "", "summary": "", "comprehensive_score": 0.0}