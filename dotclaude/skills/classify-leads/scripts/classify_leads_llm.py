#!/usr/bin/env python3
"""
Use LLM to accurately classify leads based on custom criteria.
Uses Anthropic Message Batches API for fast parallel processing.
Generalized version that works for any classification task.
"""

import os
import sys
import json
import argparse
import anthropic
import time
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

def create_classification_request(company, custom_id, classification_prompt):
    """Create a single classification request for the batch API."""
    name = company.get('company_name', 'Unknown')
    desc = (company.get('company_description') or 'No description')[:500]
    keywords = (company.get('keywords') or 'No keywords')[:300]
    industry = company.get('industry', 'No industry')

    # Build the full prompt with company data
    full_prompt = classification_prompt.format(
        name=name,
        industry=industry,
        keywords=keywords,
        desc=desc
    )

    return {
        "custom_id": custom_id,
        "params": {
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 20,
            "messages": [{"role": "user", "content": full_prompt}]
        }
    }

# Pre-defined classification prompts
CLASSIFICATION_PROMPTS = {
    "product_saas": """Classify this company as either PRODUCT_SAAS, SERVICE, or UNCLEAR.

PRODUCT_SAAS = Companies that sell software products/platforms (subscription SaaS, licenses, apps)
SERVICE = Agencies, consultancies, custom dev shops, IT services that do work for clients
UNCLEAR = Not enough information to determine

Key indicators:
- Product SaaS: "our platform", "subscription", "sign up", "dashboard", "API access", "pricing plans", "software product"
- Service: "we help companies", "consulting", "agency", "custom development", "professional services", "we work with clients"

Company: {name}
Industry: {industry}
Keywords: {keywords}
Description: {desc}

Respond with ONLY one word: PRODUCT_SAAS, SERVICE, or UNCLEAR""",
}

def main():
    parser = argparse.ArgumentParser(description="Classify leads using LLM batches")
    parser.add_argument("input_file", help="Input JSON file with companies")
    parser.add_argument("--output", default=".tmp/classified_leads.json", help="Output file for classified companies")
    parser.add_argument("--classification_type", choices=['product_saas', 'custom'], default='product_saas',
                        help="Type of classification to perform")
    parser.add_argument("--custom_prompt", help="Custom classification prompt (use {name}, {industry}, {keywords}, {desc} as placeholders)")
    parser.add_argument("--min_confidence", choices=['high', 'medium', 'low'], default='medium',
                        help="Confidence level: high=only primary class, medium=include unclear (default), low=exclude only clear mismatches")
    parser.add_argument("--primary_class", default="product_saas", help="Primary classification value to filter for (e.g., 'product_saas')")
    parser.add_argument("--exclude_class", default="service", help="Classification value to exclude (e.g., 'service')")

    args = parser.parse_args()

    if not ANTHROPIC_API_KEY:
        print("Error: ANTHROPIC_API_KEY not set in .env")
        sys.exit(1)

    # Get classification prompt
    if args.classification_type == 'custom':
        if not args.custom_prompt:
            print("Error: --custom_prompt required when using --classification_type custom")
            sys.exit(1)
        classification_prompt = args.custom_prompt
    else:
        classification_prompt = CLASSIFICATION_PROMPTS.get(args.classification_type)
        if not classification_prompt:
            print(f"Error: Unknown classification type: {args.classification_type}")
            sys.exit(1)

    # Load companies
    print(f"Loading companies from {args.input_file}...")
    try:
        with open(args.input_file, 'r') as f:
            companies = json.load(f)
    except Exception as e:
        print(f"Error loading file: {e}")
        sys.exit(1)

    print(f"Loaded {len(companies)} companies")
    print(f"Creating batch classification requests...")

    # Initialize Claude client
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Create batch requests (max 10,000 per batch)
    requests = []
    for i, company in enumerate(companies):
        request = create_classification_request(company, f"company_{i}", classification_prompt)
        requests.append(request)

    print(f"Created {len(requests)} classification requests")
    print(f"Submitting batch to Anthropic API...")

    # Create the batch
    try:
        message_batch = client.messages.batches.create(requests=requests)
        batch_id = message_batch.id
        print(f"✓ Batch created: {batch_id}")
        print(f"Status: {message_batch.processing_status}")
    except Exception as e:
        print(f"Error creating batch: {e}")
        sys.exit(1)

    # Poll for completion
    print(f"Waiting for batch to complete (this may take a few minutes)...")
    print(f"Processing {len(companies)} companies in parallel...")

    last_counts = None
    while True:
        try:
            batch = client.messages.batches.retrieve(batch_id)

            # Show progress if counts changed
            current_counts = (batch.request_counts.processing,
                            batch.request_counts.succeeded,
                            batch.request_counts.errored)

            if current_counts != last_counts:
                print(f"  Progress: {batch.request_counts.succeeded}/{len(companies)} completed, "
                      f"{batch.request_counts.processing} processing, "
                      f"{batch.request_counts.errored} errors")
                last_counts = current_counts

            if batch.processing_status == "ended":
                print(f"✓ Batch completed!")
                break

            time.sleep(2)  # Poll every 2 seconds

        except Exception as e:
            print(f"Error checking batch status: {e}")
            time.sleep(5)

    # Retrieve results
    print(f"Retrieving results...")
    try:
        results = []
        for result in client.messages.batches.results(batch_id):
            results.append(result)

        print(f"Retrieved {len(results)} results")
    except Exception as e:
        print(f"Error retrieving results: {e}")
        sys.exit(1)

    # Parse results and add to companies
    print(f"Processing classifications...")
    classifications_map = {}

    for result in results:
        custom_id = result.custom_id
        company_idx = int(custom_id.split('_')[1])

        if result.result.type == "succeeded":
            response_text = result.result.message.content[0].text.strip().upper()
            # Clean up the response - normalize to lowercase with underscores
            if 'PRODUCT_SAAS' in response_text or 'PRODUCT-SAAS' in response_text:
                classification = 'product_saas'
            elif 'SERVICE' in response_text:
                classification = 'service'
            elif 'UNCLEAR' in response_text:
                classification = 'unclear'
            else:
                classification = 'unclear'
            classifications_map[company_idx] = classification
        else:
            # Error case
            classifications_map[company_idx] = 'unclear'

    # Add classifications to companies
    for i, company in enumerate(companies):
        company['_classification'] = classifications_map.get(i, 'unclear')

    # Summary statistics
    print()
    print("="*80)
    print("CLASSIFICATION SUMMARY")
    print("="*80)

    # Count each classification
    classification_counts = {}
    for company in companies:
        cls = company.get('_classification', 'unclear')
        classification_counts[cls] = classification_counts.get(cls, 0) + 1

    print(f"Total companies: {len(companies)}")
    for cls, count in sorted(classification_counts.items()):
        percentage = count/len(companies)*100
        print(f"{cls.replace('_', ' ').title()}: {count} ({percentage:.1f}%)")
    print()

    # Filter based on confidence level
    primary = args.primary_class.lower()
    exclude = args.exclude_class.lower()

    if args.min_confidence == 'high':
        filtered = [c for c in companies if c.get('_classification') == primary]
        print(f"Filtering: HIGH confidence ({primary} only)")
    elif args.min_confidence == 'medium':
        filtered = [c for c in companies if c.get('_classification') in [primary, 'unclear']]
        print(f"Filtering: MEDIUM confidence ({primary} + unclear)")
    else:  # low
        filtered = [c for c in companies if c.get('_classification') != exclude]
        print(f"Filtering: LOW confidence (everything except {exclude})")

    print(f"Final count: {len(filtered)} companies")
    print()

    # Ensure output directory exists
    os.makedirs(os.path.dirname(args.output) if os.path.dirname(args.output) else '.', exist_ok=True)

    # Save filtered results
    with open(args.output, 'w') as f:
        json.dump(filtered, f, indent=2)

    print(f"✅ Saved {len(filtered)} companies to {args.output}")

    # Show examples of primary class
    primary_companies = [c for c in companies if c.get('_classification') == primary]
    if primary_companies:
        print()
        print(f"Sample {primary.replace('_', ' ').title()} companies:")
        for i, comp in enumerate(primary_companies[:15], 1):
            print(f"{i}. {comp['company_name']}")

if __name__ == "__main__":
    main()
