"""DuckDuckGo web search for last30days skill.

Provides built-in web search that works anywhere (no geo-restriction).
Uses the ddgs package (formerly duckduckgo_search).
"""

import sys
from typing import Any, Dict, List

try:
    from ddgs import DDGS
    HAS_DDGS = True
except ImportError:
    try:
        from duckduckgo_search import DDGS
        HAS_DDGS = True
    except ImportError:
        HAS_DDGS = False


def _log(msg: str):
    sys.stderr.write(f"[WEB] {msg}\n")
    sys.stderr.flush()


def is_available() -> bool:
    """Check if DuckDuckGo search is available."""
    return HAS_DDGS


def search_web(
    topic: str,
    max_results: int = 15,
) -> List[Dict[str, Any]]:
    """Search the web using DuckDuckGo.

    Args:
        topic: Search query
        max_results: Maximum number of results

    Returns:
        List of result dicts with title, url, snippet keys
    """
    if not HAS_DDGS:
        _log("ddgs package not installed, skipping web search")
        return []

    results = []
    try:
        with DDGS() as ddgs:
            for r in ddgs.text(
                topic,
                region="wt-wt",
                max_results=max_results,
            ):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", r.get("link", "")),
                    "snippet": r.get("body", r.get("snippet", "")),
                })
    except Exception as e:
        _log(f"DuckDuckGo search error: {e}")

    return results


def search_web_multi(
    topic: str,
    max_results: int = 15,
) -> List[Dict[str, Any]]:
    """Search the web with multiple query variations for better coverage.

    Runs 2 queries and deduplicates results.

    Args:
        topic: Base search topic
        max_results: Max results per query

    Returns:
        Deduplicated list of result dicts
    """
    queries = [
        topic,
        f"{topic} 2026",
    ]

    all_results = []
    seen_urls = set()

    for query in queries:
        results = search_web(query, max_results=max_results)
        for r in results:
            url = r.get("url", "").lower().rstrip("/")
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_results.append(r)

    return all_results
