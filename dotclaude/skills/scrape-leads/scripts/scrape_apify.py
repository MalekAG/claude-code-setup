#!/usr/bin/env python3
"""
Scrape leads using Apify's code_crafter/leads-finder actor.
"""

import os
import sys
import json
import argparse
from datetime import datetime
from dotenv import load_dotenv
from apify_client import ApifyClient

# Load environment variables
load_dotenv()

# US states for auto-formatting "Texas" -> "texas, us"
US_STATES = {
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
    "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana",
    "maine", "maryland", "massachusetts", "michigan", "minnesota",
    "mississippi", "missouri", "montana", "nebraska", "nevada",
    "new hampshire", "new jersey", "new mexico", "new york",
    "north carolina", "north dakota", "ohio", "oklahoma", "oregon",
    "pennsylvania", "rhode island", "south carolina", "south dakota",
    "tennessee", "texas", "utah", "vermont", "virginia", "washington",
    "west virginia", "wisconsin", "wyoming"
}

# Countries that are valid as-is (no suffix needed)
COUNTRY_LOCATIONS = {
    "united states", "united kingdom", "canada", "australia", "germany",
    "france", "india", "china", "japan", "brazil", "mexico", "spain",
    "italy", "netherlands", "sweden", "switzerland", "ireland", "singapore",
    "south korea", "new zealand", "israel", "portugal", "belgium",
    "austria", "norway", "denmark", "finland", "poland", "south africa",
    "united arab emirates"
}

def format_location(location):
    """
    Auto-format location to Apify's required format.
    - US states: "Texas" -> "texas, us"
    - Countries: "United States" -> "united states" (as-is)
    - Already formatted: "texas, us" -> "texas, us" (no change)
    """
    loc = location.strip().lower()

    # Already formatted with country suffix
    if ", " in loc:
        return loc

    # Known country - use as-is
    if loc in COUNTRY_LOCATIONS:
        return loc

    # US state - append ", us"
    if loc in US_STATES:
        return f"{loc}, us"

    # Unknown - return as-is and let the API error if invalid
    return loc

def scrape_leads(query, location, max_items, job_titles=None, company_keywords=None, require_email=True):
    """
    Run the Apify actor to scrape leads.
    """
    api_token = os.getenv("APIFY_API_TOKEN")
    if not api_token:
        print("Error: APIFY_API_TOKEN not found in .env", file=sys.stderr)
        return None

    client = ApifyClient(api_token)

    formatted_location = format_location(location)
    if formatted_location != location.strip().lower():
        print(f"Location auto-formatted: '{location}' -> '{formatted_location}'")

    run_input = {
        "fetch_count": int(max_items),
        "contact_job_title": job_titles if job_titles else [query],
        "company_keywords": company_keywords if company_keywords else [query],
        "contact_location": [formatted_location],
        "language": "en",
    }

    # Only add email filter if required
    if require_email:
        run_input["email_status"] = ["validated"]

    print(f"Starting scrape for '{query}' in '{location}' (Limit: {max_items})...")
    print(f"Debug: run_input = {json.dumps(run_input, indent=2)}")
    
    try:
        # Run the actor and wait for it to finish
        run = client.actor("code_crafter/leads-finder").call(run_input=run_input)
    except Exception as e:
        print(f"Error running actor: {e}") # Print to stdout
        return None

    if not run:
        print("Error: Actor run failed to start", file=sys.stderr)
        return None

    print(f"Scrape finished. Fetching results from dataset {run['defaultDatasetId']}...")

    # Fetch results from the actor's default dataset
    results = []
    for item in client.dataset(run["defaultDatasetId"]).iterate_items():
        results.append(item)
            
    return results

def save_results(results, output=None, prefix="leads"):
    """
    Save results to a JSON file.
    If output is provided, use it as the full file path.
    Otherwise, generate a timestamped file in .tmp/.
    """
    if not results:
        print("No results to save.")
        return None

    if output:
        filename = output
        output_dir = os.path.dirname(filename)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = ".tmp"
        os.makedirs(output_dir, exist_ok=True)
        filename = f"{output_dir}/{prefix}_{timestamp}.json"

    with open(filename, "w") as f:
        json.dump(results, f, indent=2)

    print(f"Results saved to {filename}")
    return filename

def main():
    parser = argparse.ArgumentParser(description="Scrape leads using Apify")
    parser.add_argument("--query", required=True, help="Search query (e.g., 'Plumbers')")
    parser.add_argument("--location", required=True, help="Location (e.g., 'New York')")
    parser.add_argument("--max_items", type=int, default=25, help="Maximum number of items to scrape")
    parser.add_argument("--output", default=None, help="Full output file path (e.g., .tmp/leads.json)")
    parser.add_argument("--output_prefix", default="leads", help="Prefix for auto-generated output file (ignored if --output is set)")
    parser.add_argument("--job_titles", nargs='+', help="Specific job titles to target (e.g., CEO Founder)")
    parser.add_argument("--company_keywords", nargs='+', help="Company keywords to filter (e.g., 'software' 'SaaS')")
    parser.add_argument("--no-email-filter", action="store_true", help="Don't filter by validated emails (faster, larger results)")

    args = parser.parse_args()

    require_email = not args.no_email_filter
    results = scrape_leads(args.query, args.location, args.max_items, args.job_titles, args.company_keywords, require_email)
    
    if results:
        print(f"Found {len(results)} leads.")
        save_results(results, output=args.output, prefix=args.output_prefix)
    else:
        print("No leads found or error occurred.")
        sys.exit(1)

if __name__ == "__main__":
    main()
