#!/usr/bin/env python3
"""
Parallelized Google Maps Lead Pipeline - Incremental Save

Enriches businesses and saves to Google Sheet incrementally (every few leads).
"""

import os
import sys
import json
import argparse
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from dotenv import load_dotenv

# Add execution dir to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scrape_google_maps import scrape_google_maps
from extract_website_contacts import scrape_website_contacts
from gmaps_lead_pipeline import (
    flatten_lead, get_or_create_sheet, get_existing_lead_ids,
    LEAD_COLUMNS
)

load_dotenv()

# Global lock for sheet writes
sheet_lock = Lock()


def enrich_single(args: tuple) -> dict:
    """Enrich a single business. Returns flattened lead dict."""
    business, search_query, idx, total = args
    name = business.get("title", "Unknown")
    website = business.get("website")

    print(f"[{idx}/{total}] Enriching: {name}")

    if website:
        try:
            contacts = scrape_website_contacts(website, name)
        except Exception as e:
            contacts = {"error": str(e)}
    else:
        contacts = {"error": "No website available"}

    return flatten_lead(business, contacts, search_query)


def append_single_lead(worksheet, lead: dict, existing_ids: set) -> bool:
    """Append a single lead to the sheet if not duplicate. Thread-safe."""
    if lead["lead_id"] in existing_ids:
        return False

    with sheet_lock:
        row = [lead.get(col, "") for col in LEAD_COLUMNS]
        worksheet.append_row(row, value_input_option='RAW')
        existing_ids.add(lead["lead_id"])
    return True


def run_incremental_pipeline(
    search_query: str,
    max_results: int = 100,
    location: str = None,
    sheet_url: str = None,
    sheet_name: str = None,
    workers: int = 10,
) -> dict:
    """
    Run pipeline with incremental saves after each enrichment.
    """
    results = {
        "search_query": search_query,
        "started_at": datetime.now().isoformat(),
        "businesses_found": 0,
        "leads_added": 0,
        "sheet_url": None,
        "errors": []
    }

    # Step 1: Scrape Google Maps (fast)
    print(f"\n{'='*60}")
    print(f"STEP 1: Scraping Google Maps for '{search_query}'")
    print(f"{'='*60}")

    businesses = scrape_google_maps(
        search_query=search_query,
        max_results=max_results,
        location=location,
    )

    if not businesses:
        results["errors"].append("No businesses found")
        return results

    results["businesses_found"] = len(businesses)
    print(f"Found {len(businesses)} businesses")

    # Save raw data
    os.makedirs(".tmp", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    with open(f".tmp/gmaps_raw_{timestamp}.json", "w") as f:
        json.dump(businesses, f, indent=2)

    # Step 2: Set up Google Sheet
    print(f"\n{'='*60}")
    print(f"STEP 2: Setting up Google Sheet")
    print(f"{'='*60}")

    try:
        spreadsheet, worksheet, is_new = get_or_create_sheet(sheet_url, sheet_name)
        results["sheet_url"] = spreadsheet.url
        print(f"Sheet URL: {spreadsheet.url}")
        existing_ids = get_existing_lead_ids(worksheet)
        print(f"Existing leads in sheet: {len(existing_ids)}")
    except Exception as e:
        results["errors"].append(f"Google Sheets error: {str(e)}")
        print(f"Error: {e}")
        return results

    # Step 3: Enrich in parallel, save incrementally
    print(f"\n{'='*60}")
    print(f"STEP 3: Enriching & saving incrementally ({workers} workers)")
    print(f"{'='*60}")

    total = len(businesses)
    tasks = [(b, search_query, i+1, total) for i, b in enumerate(businesses)]

    added_count = 0
    all_leads = []

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(enrich_single, task): task for task in tasks}

        for future in as_completed(futures):
            try:
                lead = future.result()
                all_leads.append(lead)

                # Save immediately to sheet
                if append_single_lead(worksheet, lead, existing_ids):
                    added_count += 1
                    print(f"  ✓ Saved: {lead['business_name']} ({added_count} added)")
                else:
                    print(f"  - Skipped (duplicate): {lead['business_name']}")

            except Exception as e:
                task = futures[future]
                print(f"  ✗ Error: {task[0].get('title', 'Unknown')} - {e}")
                results["errors"].append(str(e))

    # Save local backup
    with open(f".tmp/leads_enriched_{timestamp}.json", "w") as f:
        json.dump(all_leads, f, indent=2)

    results["leads_added"] = added_count
    results["completed_at"] = datetime.now().isoformat()

    print(f"\n{'='*60}")
    print("PIPELINE COMPLETE")
    print(f"{'='*60}")
    print(f"Businesses found: {results['businesses_found']}")
    print(f"Leads added: {results['leads_added']}")
    print(f"Sheet URL: {results['sheet_url']}")

    return results


def main():
    parser = argparse.ArgumentParser(description="Incremental Google Maps Lead Pipeline")
    parser.add_argument("--search", required=True, help="Search query")
    parser.add_argument("--limit", type=int, default=100, help="Max results (default: 100)")
    parser.add_argument("--location", help="Location filter")
    parser.add_argument("--sheet-url", help="Existing sheet URL")
    parser.add_argument("--sheet-name", help="New sheet name")
    parser.add_argument("--workers", type=int, default=10, help="Parallel workers (default: 10)")

    args = parser.parse_args()

    results = run_incremental_pipeline(
        search_query=args.search,
        max_results=args.limit,
        location=args.location,
        sheet_url=args.sheet_url,
        sheet_name=args.sheet_name,
        workers=args.workers,
    )

    if results["leads_added"] == 0 and results["errors"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
