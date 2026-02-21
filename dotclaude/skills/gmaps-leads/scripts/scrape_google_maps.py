#!/usr/bin/env python3
"""
Scrape Google Maps business listings using Apify's compass/crawler-google-places actor.

Usage:
    python3 execution/scrape_google_maps.py --search "plumbers in Austin TX" --limit 10
    python3 execution/scrape_google_maps.py --search "dentists near me" --location "New York, NY" --limit 25
"""

import os
import sys
import json
import argparse
from datetime import datetime
from dotenv import load_dotenv
from apify_client import ApifyClient

load_dotenv()

ACTOR_ID = "compass/crawler-google-places"


def scrape_google_maps(
    search_query: str,
    max_results: int = 10,
    location: str = None,
    language: str = "en",
) -> list[dict]:
    """
    Run the Apify Google Maps scraper actor.

    Args:
        search_query: Search term (e.g., "plumbers in Austin TX")
        max_results: Maximum number of places to scrape
        location: Optional location to focus the search
        language: Language code (default: en)

    Returns:
        List of business dictionaries with scraped data
    """
    api_token = os.getenv("APIFY_API_TOKEN")
    if not api_token:
        print("Error: APIFY_API_TOKEN not found in .env", file=sys.stderr)
        return []

    client = ApifyClient(api_token)

    # Build search string with location if provided
    full_search = search_query
    if location and location.lower() not in search_query.lower():
        full_search = f"{search_query} in {location}"

    run_input = {
        "searchStringsArray": [full_search],
        "maxCrawledPlacesPerSearch": max_results,
        "language": language,
        "deeperCityScrape": False,
        "oneReviewPerRow": False,
    }

    print(f"Starting Google Maps scrape: '{full_search}' (limit: {max_results})...")

    try:
        run = client.actor(ACTOR_ID).call(run_input=run_input)
    except Exception as e:
        print(f"Error running Apify actor: {e}", file=sys.stderr)
        return []

    if not run:
        print("Error: Actor run failed to start", file=sys.stderr)
        return []

    print(f"Scrape finished. Fetching results from dataset {run['defaultDatasetId']}...")

    results = []
    for item in client.dataset(run["defaultDatasetId"]).iterate_items():
        results.append(item)

    print(f"Retrieved {len(results)} businesses from Google Maps")
    return results


def save_results(results: list[dict], prefix: str = "gmaps") -> str:
    """Save results to a JSON file in .tmp directory."""
    if not results:
        print("No results to save.")
        return None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = ".tmp"
    os.makedirs(output_dir, exist_ok=True)

    filename = f"{output_dir}/{prefix}_{timestamp}.json"

    with open(filename, "w") as f:
        json.dump(results, f, indent=2)

    print(f"Results saved to {filename}")
    return filename


def main():
    parser = argparse.ArgumentParser(description="Scrape Google Maps businesses using Apify")
    parser.add_argument("--search", required=True, help="Search query (e.g., 'plumbers in Austin TX')")
    parser.add_argument("--limit", type=int, default=10, help="Maximum number of results (default: 10)")
    parser.add_argument("--location", help="Optional location to focus search")
    parser.add_argument("--language", default="en", help="Language code (default: en)")
    parser.add_argument("--output", default="gmaps", help="Output file prefix (default: gmaps)")
    parser.add_argument("--json", action="store_true", help="Output results as JSON to stdout")

    args = parser.parse_args()

    results = scrape_google_maps(
        search_query=args.search,
        max_results=args.limit,
        location=args.location,
        language=args.language,
    )

    if not results:
        print("No results found or error occurred.")
        sys.exit(1)

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        filename = save_results(results, prefix=args.output)
        if filename:
            print(f"\nSample result:")
            sample = results[0]
            for key in ["title", "address", "phone", "website", "categoryName"]:
                if key in sample:
                    print(f"  {key}: {sample.get(key)}")


if __name__ == "__main__":
    main()
