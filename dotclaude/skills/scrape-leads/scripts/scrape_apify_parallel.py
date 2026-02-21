#!/usr/bin/env python3
"""
Parallel lead scraping using Apify with geographic partitioning.
Splits by location to avoid extra Apify costs while maintaining speed.
"""

import os
import sys
import json
import argparse
from datetime import datetime
from dotenv import load_dotenv
from apify_client import ApifyClient
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import time

# Load environment variables
load_dotenv()

# Geographic partitions (cost-neutral strategy)
# Each region map is mutually exclusive to avoid duplicate charges

# United States (4-way split)
US_REGIONS = {
    "northeast": ["Connecticut", "Maine", "Massachusetts", "New Hampshire", "Rhode Island",
                  "Vermont", "New Jersey", "New York", "Pennsylvania"],
    "southeast": ["Delaware", "Florida", "Georgia", "Maryland", "North Carolina",
                  "South Carolina", "Virginia", "West Virginia", "Alabama", "Kentucky",
                  "Mississippi", "Tennessee", "Arkansas", "Louisiana", "Oklahoma", "Texas"],
    "midwest": ["Illinois", "Indiana", "Michigan", "Ohio", "Wisconsin", "Iowa",
                "Kansas", "Minnesota", "Missouri", "Nebraska", "North Dakota", "South Dakota"],
    "west": ["Arizona", "Colorado", "Idaho", "Montana", "Nevada", "New Mexico", "Utah",
             "Wyoming", "Alaska", "California", "Hawaii", "Oregon", "Washington"]
}

# United States metros (8-way split)
US_METROS = [
    ["New York", "New Jersey", "Philadelphia", "Boston"],
    ["Los Angeles", "San Francisco", "San Diego", "San Jose"],
    ["Chicago", "Detroit", "Minneapolis", "Cleveland"],
    ["Dallas", "Houston", "Austin", "San Antonio"],
    ["Atlanta", "Miami", "Charlotte", "Tampa"],
    ["Phoenix", "Denver", "Las Vegas", "Seattle"],
    ["Washington DC", "Baltimore", "Virginia Beach"],
    ["Portland", "Sacramento", "Salt Lake City"]
]

# European Union (4-way split)
EU_REGIONS = {
    "western": ["Germany", "France", "Netherlands", "Belgium", "Luxembourg", "Austria", "Switzerland"],
    "southern": ["Spain", "Italy", "Portugal", "Greece", "Malta", "Cyprus"],
    "northern": ["Denmark", "Sweden", "Finland", "Norway", "Iceland", "Ireland"],
    "eastern": ["Poland", "Czech Republic", "Hungary", "Romania", "Bulgaria", "Slovakia",
                "Slovenia", "Croatia", "Estonia", "Latvia", "Lithuania"]
}

# United Kingdom (4-way split)
UK_REGIONS = {
    "england_southeast": ["London", "Kent", "Surrey", "Sussex", "Hampshire", "Berkshire", "Essex", "Hertfordshire"],
    "england_north": ["Manchester", "Liverpool", "Leeds", "Sheffield", "Newcastle", "Birmingham", "Nottingham"],
    "scotland_wales": ["Scotland", "Edinburgh", "Glasgow", "Wales", "Cardiff", "Swansea"],
    "england_southwest": ["Bristol", "Cornwall", "Devon", "Somerset", "Gloucestershire", "Dorset"]
}

# Canada (4-way split)
CANADA_REGIONS = {
    "ontario": ["Ontario", "Toronto", "Ottawa", "Mississauga", "Hamilton"],
    "quebec": ["Quebec", "Montreal", "Quebec City", "Laval", "Gatineau"],
    "west": ["British Columbia", "Alberta", "Saskatchewan", "Manitoba", "Vancouver", "Calgary", "Edmonton"],
    "atlantic": ["Nova Scotia", "New Brunswick", "Prince Edward Island", "Newfoundland and Labrador"]
}

# Australia (4-way split)
AUSTRALIA_REGIONS = {
    "nsw": ["New South Wales", "Sydney", "Newcastle", "Wollongong"],
    "victoria_tasmania": ["Victoria", "Melbourne", "Geelong", "Tasmania", "Hobart"],
    "queensland": ["Queensland", "Brisbane", "Gold Coast", "Sunshine Coast", "Cairns"],
    "west_south": ["Western Australia", "Perth", "South Australia", "Adelaide", "Northern Territory"]
}

# Asia-Pacific (8-way split)
APAC_REGIONS = [
    ["Japan", "Tokyo", "Osaka", "Kyoto"],
    ["South Korea", "Seoul", "Busan", "Incheon"],
    ["Singapore"],
    ["Hong Kong"],
    ["India", "Mumbai", "Delhi", "Bangalore", "Hyderabad"],
    ["China", "Beijing", "Shanghai", "Guangzhou", "Shenzhen"],
    ["Southeast Asia", "Thailand", "Vietnam", "Malaysia", "Indonesia", "Philippines"],
    ["Australia", "New Zealand"]
]

# Global/Worldwide (8-way continental split)
GLOBAL_REGIONS = [
    ["United States", "Canada", "Mexico"],
    ["United Kingdom", "Ireland", "France", "Germany", "Netherlands", "Belgium"],
    ["Spain", "Italy", "Portugal", "Greece", "Switzerland", "Austria"],
    ["Poland", "Czech Republic", "Hungary", "Romania", "Scandinavia"],
    ["Australia", "New Zealand", "Singapore", "Hong Kong"],
    ["India", "Pakistan", "Bangladesh"],
    ["China", "Japan", "South Korea", "Taiwan"],
    ["Brazil", "Argentina", "Chile", "Colombia", "Peru"]
]

# Region map lookup
REGION_MAPS = {
    "united states": US_REGIONS,
    "us": US_REGIONS,
    "usa": US_REGIONS,
    "european union": EU_REGIONS,
    "eu": EU_REGIONS,
    "europe": EU_REGIONS,
    "united kingdom": UK_REGIONS,
    "uk": UK_REGIONS,
    "great britain": UK_REGIONS,
    "canada": CANADA_REGIONS,
    "australia": AUSTRALIA_REGIONS,
}

def scrape_partition(partition_id, query, locations, max_items, company_keywords=None, require_email=False):
    """
    Run a single Apify scrape for specific locations.
    Returns (partition_id, results, elapsed_time).
    """
    start_time = time.time()

    api_token = os.getenv("APIFY_API_TOKEN")
    if not api_token:
        print(f"[Partition {partition_id}] Error: APIFY_API_TOKEN not found in .env", file=sys.stderr)
        return (partition_id, None, 0)

    client = ApifyClient(api_token)

    # Prepare the actor input
    # Convert locations to Apify's required format (e.g., "illinois, us" instead of "Illinois")
    formatted_locations = []
    for loc in locations:
        loc_lower = loc.lower()
        # Check if it's a US state (not already formatted as "state, us")
        if ", us" not in loc_lower and loc_lower not in ["united states", "canada", "australia", "uk", "united kingdom"]:
            # Assume it's a US state and format it
            loc_lower = f"{loc_lower}, us"
        formatted_locations.append(loc_lower)

    run_input = {
        "fetch_count": int(max_items),
        "contact_job_title": [query],
        "company_keywords": company_keywords if company_keywords else [query],
        "contact_location": formatted_locations,  # Multiple locations
        "language": "en",
    }

    if require_email:
        run_input["email_status"] = ["validated"]

    location_str = ", ".join(locations[:3]) + ("..." if len(locations) > 3 else "")
    print(f"[Partition {partition_id}] Starting scrape for '{query}' in [{location_str}] (Limit: {max_items})...")

    try:
        # Run the actor and wait for it to finish
        run = client.actor("code_crafter/leads-finder").call(run_input=run_input)
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"[Partition {partition_id}] Error running actor: {e}")
        return (partition_id, None, elapsed)

    if not run:
        elapsed = time.time() - start_time
        print(f"[Partition {partition_id}] Error: Actor run failed to start", file=sys.stderr)
        return (partition_id, None, elapsed)

    print(f"[Partition {partition_id}] Scrape finished. Fetching results from dataset {run['defaultDatasetId']}...")

    # Fetch results from the actor's default dataset
    results = []
    for item in client.dataset(run["defaultDatasetId"]).iterate_items():
        results.append(item)

    elapsed = time.time() - start_time
    print(f"[Partition {partition_id}] Retrieved {len(results)} leads in {elapsed:.1f}s")
    return (partition_id, results, elapsed)

def generate_lead_hash(lead):
    """
    Generate a unique hash for a lead based on key identifiers.
    Used for deduplication.
    """
    # Use email as primary key, fallback to name+company+location
    email = lead.get("email") or ""
    email = email.strip().lower() if email else ""
    if email:
        return hashlib.md5(email.encode()).hexdigest()

    # Fallback: combine available identifiers
    identifiers = [
        (lead.get("first_name") or "").strip().lower(),
        (lead.get("last_name") or "").strip().lower(),
        (lead.get("full_name") or "").strip().lower(),
        (lead.get("company_name") or "").strip().lower(),
        (lead.get("company_domain") or "").strip().lower(),
        (lead.get("city") or "").strip().lower(),
        (lead.get("state") or "").strip().lower()
    ]

    combined = "|".join(filter(None, identifiers))
    return hashlib.md5(combined.encode()).hexdigest()

def deduplicate_leads(all_results):
    """
    Deduplicate leads across all partitions.
    Returns unique leads only.
    """
    seen_hashes = set()
    unique_leads = []
    duplicate_count = 0

    for lead in all_results:
        lead_hash = generate_lead_hash(lead)

        if lead_hash not in seen_hashes:
            seen_hashes.add(lead_hash)
            unique_leads.append(lead)
        else:
            duplicate_count += 1

    print(f"\nDeduplication complete:")
    print(f"  - Total leads collected: {len(all_results)}")
    print(f"  - Duplicates removed: {duplicate_count}")
    print(f"  - Unique leads: {len(unique_leads)}")

    return unique_leads

def scrape_parallel(query, location, total_count, strategy="regions", num_partitions=4, company_keywords=None, require_email=False):
    """
    Run parallel scrapes with geographic partitioning.

    Strategy Options:
    - "regions": Split by US regions (Northeast, Southeast, Midwest, West) - 4 partitions
    - "metros": Split by major metro areas - 8 partitions
    - "states": Provide your own list of states - custom partitions

    Args:
        query: Base search query
        location: Target location (must be "United States" for region/metro strategies)
        total_count: Total number of leads desired
        strategy: Partitioning strategy ("regions", "metros", "states")
        num_partitions: Number of parallel partitions (default 4)
        company_keywords: Company keywords to filter
        require_email: Whether to require validated emails

    Returns:
        (unique_leads, total_time, partition_times)
    """
    workflow_start = time.time()

    # Determine partition strategy
    if strategy == "regions":
        # Auto-detect region map based on location
        location_lower = location.lower() if isinstance(location, str) else None

        if location_lower in REGION_MAPS:
            # Use predefined region map
            region_map = REGION_MAPS[location_lower]
            location_groups = list(region_map.values())
            num_partitions = len(location_groups)
            print(f"  - Detected region: {location_lower.upper()} ({num_partitions}-way split)")
        else:
            # Default to US regions if ambiguous
            location_groups = list(US_REGIONS.values())
            num_partitions = 4
            print(f"  - No region map found for '{location}', defaulting to US regions")

    elif strategy == "metros":
        # Use US metros by default (could expand to other metros)
        location_groups = US_METROS[:num_partitions] if num_partitions else US_METROS
        num_partitions = len(location_groups)

    elif strategy == "apac":
        location_groups = APAC_REGIONS[:num_partitions] if num_partitions else APAC_REGIONS
        num_partitions = len(location_groups)

    elif strategy == "global":
        location_groups = GLOBAL_REGIONS[:num_partitions] if num_partitions else GLOBAL_REGIONS
        num_partitions = len(location_groups)

    elif isinstance(location, list):
        # Custom: user provided list of locations
        # Split into N groups
        if not num_partitions:
            num_partitions = 4
        chunk_size = max(1, len(location) // num_partitions)
        location_groups = [location[i:i + chunk_size] for i in range(0, len(location), chunk_size)]
    else:
        print(f"Error: For parallel scraping, use strategy='regions', or provide location as a list of states/cities")
        print(f"Supported locations for auto-regions: {', '.join(REGION_MAPS.keys())}")
        return None, 0, []

    items_per_partition = total_count // num_partitions

    print(f"Starting parallel scrape:")
    print(f"  - Total target: {total_count} leads")
    print(f"  - Partitions: {num_partitions}")
    print(f"  - Items per partition: {items_per_partition}")
    print(f"  - Strategy: {strategy.upper()} (geographic split)")
    print(f"  - Cost: SAME as sequential ({total_count} total leads)")
    print()

    # Execute partitions in parallel
    all_results = []
    partition_times = []

    with ThreadPoolExecutor(max_workers=num_partitions) as executor:
        # Submit all partition scrapes
        futures = []
        for i, locations in enumerate(location_groups[:num_partitions]):
            future = executor.submit(
                scrape_partition,
                partition_id=i + 1,
                query=query,
                locations=locations,
                max_items=items_per_partition,
                company_keywords=company_keywords,
                require_email=require_email
            )
            futures.append((future, i + 1, locations))

        # Collect results as they complete
        for future, partition_id, locations in futures:
            pid, results, elapsed = future.result()
            partition_times.append(elapsed)

            if results:
                location_str = ", ".join(locations[:2]) + ("..." if len(locations) > 2 else "")
                print(f"[Partition {pid}] ✅ Completed: {len(results)} leads from [{location_str}]")
                all_results.extend(results)
            else:
                print(f"[Partition {pid}] ❌ Failed or returned no results")

    if not all_results:
        print("\nNo results collected from any partition")
        return None, 0, partition_times

    # Deduplicate (in case leads appear in multiple geographic regions)
    unique_leads = deduplicate_leads(all_results)

    total_time = time.time() - workflow_start

    # Note: No trimming needed - we requested exactly what we wanted

    return unique_leads, total_time, partition_times

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

    print(f"\nResults saved to {filename}")
    return filename

def main():
    parser = argparse.ArgumentParser(
        description="Parallel lead scraping with geographic partitioning",
        epilog=f"Supported regions for auto-detection: {', '.join(REGION_MAPS.keys())}"
    )
    parser.add_argument("--query", required=True, help="Search query (e.g., 'Dentist', 'Plumber')")
    parser.add_argument("--location", required=True,
                        help="Location: 'United States', 'EU', 'UK', 'Canada', 'Australia', or comma-separated cities/states")
    parser.add_argument("--total_count", type=int, required=True, help="Total number of leads desired")
    parser.add_argument("--strategy", default="regions",
                        choices=["regions", "metros", "apac", "global"],
                        help="Partition strategy: regions (auto-detect by location), metros (8-way US), apac (8-way Asia-Pacific), global (8-way worldwide)")
    parser.add_argument("--partitions", type=int, default=None, help="Number of partitions (auto-set based on strategy)")
    parser.add_argument("--output", default=None, help="Full output file path (e.g., .tmp/leads.json)")
    parser.add_argument("--output_prefix", default="leads", help="Prefix for auto-generated output file (ignored if --output is set)")
    parser.add_argument("--company_keywords", nargs='+', help="Company keywords to filter")
    parser.add_argument("--no-email-filter", action="store_true", help="Don't filter by validated emails")

    args = parser.parse_args()

    require_email = not args.no_email_filter

    # Handle custom state list
    location = args.location
    if "," in location:
        # User provided comma-separated list
        location = [loc.strip() for loc in location.split(",")]
        strategy = "custom"
        num_partitions = args.partitions or 4
    else:
        strategy = args.strategy
        num_partitions = args.partitions

    results, total_time, partition_times = scrape_parallel(
        query=args.query,
        location=location,
        total_count=args.total_count,
        strategy=strategy,
        num_partitions=num_partitions,
        company_keywords=args.company_keywords,
        require_email=require_email
    )

    if results:
        print(f"\n✅ Total unique leads collected: {len(results)}")
        print(f"⏱️  Total time: {total_time:.1f}s ({total_time/60:.1f} minutes)")
        print(f"📊 Partition times: {[f'{t:.1f}s' for t in partition_times]}")
        print(f"🚀 Avg partition time: {sum(partition_times)/len(partition_times):.1f}s")
        print(f"💰 Cost: SAME as sequential ({args.total_count} total leads)")

        save_results(results, output=args.output, prefix=args.output_prefix)
    else:
        print("\n❌ No leads found or error occurred.")
        sys.exit(1)

if __name__ == "__main__":
    main()
