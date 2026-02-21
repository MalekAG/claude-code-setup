import os
import sys
import gspread
import argparse
import anthropic
import json
import concurrent.futures
import time
from dotenv import load_dotenv
from urllib.parse import urlparse

# Load environment variables
load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
BATCH_SIZE = 50  # Sweet spot - balances speed vs reliability
MAX_WORKERS = 5  # Reduced to avoid rate limits
MAX_RETRIES = 3  # Retry failed batches

def get_sheet_id_from_url(url):
    """Extract spreadsheet ID from URL."""
    parsed = urlparse(url)
    if "docs.google.com" in parsed.netloc:
        path_parts = parsed.path.split("/")
        if "d" in path_parts:
            return path_parts[path_parts.index("d") + 1]
    return url

def column_letter(n):
    """Convert column index (0-based) to Excel-style column letter (A, B, ... Z, AA, AB, ...)."""
    result = ""
    while n >= 0:
        result = chr(65 + (n % 26)) + result
        n = n // 26 - 1
    return result

def casualize_batch(records, client, batch_num, total_batches, retry_count=0):
    """Use Claude to casualize first names, company names, and cities in one call."""
    if not records:
        return []

    # Format records as compact JSON (no indent for speed)
    records_list = []
    for i, record in enumerate(records):
        records_list.append({
            "id": i + 1,
            "first_name": record['first_name'],
            "company_name": record['company_name'],
            "city": record['city']
        })

    records_json = json.dumps(records_list)

    prompt = f"""Convert to casual forms for cold emails. Return ONLY valid JSON array.

Rules:
- first_name: Common nicknames (William→Will, Jennifer→Jen), keep if no nickname
- company_name: Remove "The", legal suffixes (LLC/Inc/Corp/Ltd), generic words (Realty/Real Estate/Group/Services). Use "you guys" if too generic
- city: Local nicknames (San Francisco→SF, Philadelphia→Philly), keep if none

Input: {records_json}

Output JSON only (no markdown, no explanations):"""

    try:
        message = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=6000,  # Increased to handle 50 records reliably
            messages=[{"role": "user", "content": prompt}]
        )
        response_text = message.content[0].text.strip()

        # Remove markdown code blocks if present
        if response_text.startswith("```"):
            lines = response_text.split('\n')
            response_text = '\n'.join(lines[1:-1])

        # Parse JSON response
        results = json.loads(response_text)

        # Ensure we have the same number of results as inputs
        if len(results) != len(records):
            print(f"  ⚠️  Batch {batch_num}/{total_batches}: Got {len(results)} results for {len(records)} inputs, padding...")
            while len(results) < len(records):
                idx = len(results)
                results.append({
                    "id": idx + 1,
                    "casual_first_name": records[idx]['first_name'],
                    "casual_company_name": records[idx]['company_name'],
                    "casual_city_name": records[idx]['city']
                })

        print(f"  ✓ Batch {batch_num}/{total_batches} complete ({len(records)} records)")
        return results
    except anthropic.RateLimitError as e:
        if retry_count < MAX_RETRIES:
            wait_time = (2 ** retry_count) * 2  # Exponential backoff: 2s, 4s, 8s
            print(f"  ⏸️  Batch {batch_num}/{total_batches} rate limited, retrying in {wait_time}s...")
            time.sleep(wait_time)
            return casualize_batch(records, client, batch_num, total_batches, retry_count + 1)
        else:
            print(f"  ✗ Batch {batch_num}/{total_batches} failed after {MAX_RETRIES} retries")
            # Return originals
            return [{
                "id": i + 1,
                "casual_first_name": record['first_name'],
                "casual_company_name": record['company_name'],
                "casual_city_name": record['city']
            } for i, record in enumerate(records)]
    except Exception as e:
        print(f"  ✗ Batch {batch_num}/{total_batches} error: {str(e)[:100]}")
        # Return originals if error
        return [{
            "id": i + 1,
            "casual_first_name": record['first_name'],
            "casual_company_name": record['company_name'],
            "casual_city_name": record['city']
        } for i, record in enumerate(records)]

def main():
    parser = argparse.ArgumentParser(description="Casualize first names, company names, and cities in one pass")
    parser.add_argument("sheet_url", help="URL of the Google Sheet")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing casual names")
    parser.add_argument("--workers", type=int, default=MAX_WORKERS, help=f"Number of parallel workers (default: {MAX_WORKERS})")
    args = parser.parse_args()

    if not ANTHROPIC_API_KEY:
        print("Error: ANTHROPIC_API_KEY not set in .env")
        sys.exit(1)

    start_time = time.time()

    print(f"Connecting to Google Sheet...")
    try:
        gc = gspread.oauth()
        sheet_id = get_sheet_id_from_url(args.sheet_url)
        spreadsheet = gc.open_by_key(sheet_id)
        worksheet = spreadsheet.sheet1
    except Exception as e:
        print(f"Error connecting to sheet: {e}")
        sys.exit(1)

    # Get all values at once
    print("Reading sheet data...")
    rows = worksheet.get_all_values()
    if not rows:
        print("Sheet is empty")
        sys.exit(0)

    headers = rows[0]

    # Find column indices
    try:
        email_idx = headers.index("email")
        first_name_idx = headers.index("first_name")
        company_name_idx = headers.index("company_name")
        city_idx = headers.index("city")
    except ValueError as e:
        print(f"Error: Missing required column: {e}")
        print(f"Available columns: {headers}")
        sys.exit(1)

    # Find or create casual columns (batch create all at once)
    casual_columns = {}
    columns_to_create = []

    for field in ['casual_first_name', 'casual_company_name', 'casual_city_name']:
        if field in headers:
            casual_columns[field] = headers.index(field)
        else:
            columns_to_create.append(field)
            casual_idx = len(headers)
            casual_columns[field] = casual_idx
            headers.append(field)

    if columns_to_create:
        print(f"Creating {len(columns_to_create)} new columns...")
        current_cols = worksheet.col_count
        needed_cols = len(headers)
        if needed_cols > current_cols:
            worksheet.resize(cols=needed_cols)

        # Batch create all headers at once
        header_updates = [{'range': f'{column_letter(casual_columns[field])}1', 'values': [[field]]}
                          for field in columns_to_create]
        if header_updates:
            worksheet.batch_update(header_updates)

    # Collect rows to process
    print(f"\nScanning {len(rows)-1} rows...")
    rows_to_process = []

    for i in range(1, len(rows)):
        row = rows[i]

        if len(row) <= email_idx or not row[email_idx].strip():
            continue

        first_name = row[first_name_idx].strip() if len(row) > first_name_idx else ""
        company_name = row[company_name_idx].strip() if len(row) > company_name_idx else ""
        city = row[city_idx].strip() if len(row) > city_idx else ""

        if not first_name or not company_name or not city:
            continue

        # Check if already casualized
        if not args.overwrite:
            already_done = True
            for field in ['casual_first_name', 'casual_company_name', 'casual_city_name']:
                idx = casual_columns[field]
                if len(row) <= idx or not row[idx].strip():
                    already_done = False
                    break
            if already_done:
                continue

        rows_to_process.append({
            'row_num': i,
            'first_name': first_name,
            'company_name': company_name,
            'city': city
        })

    total_to_process = len(rows_to_process)
    print(f"Found {total_to_process} records to casualize")

    if total_to_process == 0:
        print("Nothing to process!")
        sys.exit(0)

    # Split into batches
    batches = []
    for batch_start in range(0, total_to_process, BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE, total_to_process)
        batches.append(rows_to_process[batch_start:batch_end])

    total_batches = len(batches)
    print(f"\nProcessing {total_batches} batches of up to {BATCH_SIZE} records using {args.workers} parallel workers...")

    # Process batches in parallel
    all_results = []
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_to_batch = {
            executor.submit(casualize_batch, batch, client, i+1, total_batches): (i, batch)
            for i, batch in enumerate(batches)
        }

        for future in concurrent.futures.as_completed(future_to_batch):
            batch_idx, batch = future_to_batch[future]
            try:
                results = future.result()
                all_results.append((batch_idx, batch, results))
            except Exception as e:
                print(f"  ✗ Batch {batch_idx+1} failed: {e}")
                # Add fallback results
                results = [{
                    "id": i + 1,
                    "casual_first_name": record['first_name'],
                    "casual_company_name": record['company_name'],
                    "casual_city_name": record['city']
                } for i, record in enumerate(batch)]
                all_results.append((batch_idx, batch, results))

    # Sort results by original batch order
    all_results.sort(key=lambda x: x[0])

    # Prepare all updates
    print(f"\nPreparing updates...")
    updates = []
    processed = 0

    for batch_idx, batch, results in all_results:
        for i, item in enumerate(batch):
            result = results[i] if i < len(results) else {
                "casual_first_name": item['first_name'],
                "casual_company_name": item['company_name'],
                "casual_city_name": item['city']
            }

            casual_first = result.get('casual_first_name', item['first_name'])
            casual_company = result.get('casual_company_name', item['company_name'])
            casual_city = result.get('casual_city_name', item['city'])

            row_num = item['row_num'] + 1
            updates.append({
                'range': f'{column_letter(casual_columns["casual_first_name"])}{row_num}',
                'values': [[casual_first]]
            })
            updates.append({
                'range': f'{column_letter(casual_columns["casual_company_name"])}{row_num}',
                'values': [[casual_company]]
            })
            updates.append({
                'range': f'{column_letter(casual_columns["casual_city_name"])}{row_num}',
                'values': [[casual_city]]
            })

        processed += len(batch)

    # Batch update all cells at once
    print(f"Updating {len(updates)} cells in Google Sheet...")
    if updates:
        # Google Sheets API has a limit of ~1000 updates per batch
        # Split into chunks if needed
        chunk_size = 1000
        for i in range(0, len(updates), chunk_size):
            chunk = updates[i:i+chunk_size]
            worksheet.batch_update(chunk)
            if len(updates) > chunk_size:
                print(f"  Updated {min(i+chunk_size, len(updates))}/{len(updates)} cells...")

    elapsed = time.time() - start_time
    print(f"\n✅ Done! Casualized {processed} records in {elapsed:.1f}s ({processed/elapsed:.1f} records/sec)")

if __name__ == "__main__":
    main()
