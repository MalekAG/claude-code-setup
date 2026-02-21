#!/usr/bin/env python3
"""Web search via DuckDuckGo - drop-in replacement for Claude Code's WebSearch.

Usage:
    python web-search.py "your search query"
    python web-search.py "your search query" --max 10
    python web-search.py "your search query" --region us-en
    python web-search.py "your search query" --json
"""

import argparse
import json
import sys
import warnings

warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from ddgs import DDGS


def search(query: str, max_results: int = 5, region: str = "us-en", as_json: bool = False):
    results = DDGS().text(query, region=region, max_results=max_results)

    if as_json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return

    if not results:
        print("No results found.")
        return

    for i, r in enumerate(results, 1):
        print(f"{i}. {r['title']}")
        print(f"   {r['href']}")
        print(f"   {r['body'][:200]}")
        print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Web search via DuckDuckGo")
    parser.add_argument("query", help="Search query")
    parser.add_argument("--max", type=int, default=5, help="Max results (default: 5)")
    parser.add_argument("--region", default="us-en", help="Region (default: us-en)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    search(args.query, max_results=args.max, region=args.region, as_json=args.json)
