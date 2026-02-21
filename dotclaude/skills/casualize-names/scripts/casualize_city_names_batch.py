import os
import sys
import gspread
import argparse
import anthropic
from dotenv import load_dotenv
from urllib.parse import urlparse

# Load environment variables
load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
BATCH_SIZE = 30  # Process 30 cities per API call

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

def casualize_city_names_batch(city_names, client):
    """Use Claude to convert multiple city names at once."""
    if not city_names:
        return []

    # Format city names as numbered list
    city_list = "\n".join([f"{i+1}. {name}" for i, name in enumerate(city_names)])

    prompt = f"""Convert these formal city names to their casual forms for cold emails. Make them AS CASUAL AS POSSIBLE - like how locals actually refer to their city.

Rules:
- Use common nicknames and abbreviations that locals use
- If a city has multiple well-known casual names, pick the most common one
- For cities without common nicknames, use the shortest recognizable form
- Remove unnecessary words like "City of", "Greater", etc.
- Keep it natural and friendly

Examples:
- "San Francisco" → "SF"
- "Los Angeles" → "LA"
- "New York" → "NYC"
- "Philadelphia" → "Philly"
- "Indianapolis" → "Indy"
- "Minneapolis" → "Minneapolis" (no common nickname)
- "Saint Louis" → "St. Louis"
- "Fort Worth" → "Fort Worth"
- "Boston" → "Boston" (already casual)
- "Washington" → "DC"
- "Las Vegas" → "Vegas"
- "New Orleans" → "NOLA"
- "San Antonio" → "San Antonio"
- "Pittsburgh" → "Pittsburgh"

City names to convert:
{city_list}

Output format: Return ONLY a numbered list with the casual name for each city, one per line. No explanations.
Example output:
1. SF
2. LA
3. NYC
4. Boston"""

    try:
        message = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        response_text = message.content[0].text.strip()

        # Parse the numbered list response
        casual_names = []
        for line in response_text.split('\n'):
            line = line.strip()
            if not line:
                continue
            # Remove number prefix (e.g., "1. " or "1) ")
            if '. ' in line:
                casual_name = line.split('. ', 1)[1]
            elif ') ' in line:
                casual_name = line.split(') ', 1)[1]
            else:
                casual_name = line
            # Remove quotes if present
            casual_name = casual_name.strip('"').strip("'")
            casual_names.append(casual_name)

        # Ensure we have the same number of results as inputs
        if len(casual_names) != len(city_names):
            print(f"  ! Warning: Got {len(casual_names)} results for {len(city_names)} inputs")
            # Pad with original names if needed
            while len(casual_names) < len(city_names):
                casual_names.append(city_names[len(casual_names)])

        return casual_names
    except Exception as e:
        print(f"  ! API Error: {e}")
        return city_names  # Return originals if error

def main():
    parser = argparse.ArgumentParser(description="Casualize city names for cold email (batched)")
    parser.add_argument("sheet_url", help="URL of the Google Sheet")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing casual names")
    args = parser.parse_args()

    if not ANTHROPIC_API_KEY:
        print("Error: ANTHROPIC_API_KEY not set in .env")
        sys.exit(1)

    print(f"Connecting to Google Sheet...")
    try:
        gc = gspread.oauth()
        sheet_id = get_sheet_id_from_url(args.sheet_url)
        spreadsheet = gc.open_by_key(sheet_id)
        worksheet = spreadsheet.sheet1
    except Exception as e:
        print(f"Error connecting to sheet: {e}")
        sys.exit(1)

    # Get all values
    print("Reading sheet data...")
    rows = worksheet.get_all_values()
    if not rows:
        print("Sheet is empty")
        sys.exit(0)

    headers = rows[0]

    # Find column indices
    try:
        email_idx = headers.index("email")
        city_idx = headers.index("city")
    except ValueError as e:
        print(f"Error: Missing required column: {e}")
        print(f"Available columns: {headers}")
        sys.exit(1)

    # Check if casual_city_name column exists
    if "casual_city_name" in headers:
        casual_idx = headers.index("casual_city_name")
        print(f"Using existing 'casual_city_name' column at index {casual_idx}")
    else:
        # Add new column
        print("Adding new 'casual_city_name' column...")
        casual_idx = len(headers)

        # Resize sheet to add new column if needed
        current_cols = worksheet.col_count
        if casual_idx >= current_cols:
            worksheet.resize(cols=casual_idx + 1)
            print(f"Resized sheet to {casual_idx + 1} columns")

        worksheet.update_cell(1, casual_idx + 1, "casual_city_name")
        headers.append("casual_city_name")
        print(f"Created column at index {casual_idx}")

    # Initialize Claude client
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Collect rows to process
    print(f"\nScanning {len(rows)-1} rows for records with emails...")
    rows_to_process = []

    for i in range(1, len(rows)):
        row = rows[i]

        # Skip if no email
        if len(row) <= email_idx or not row[email_idx].strip():
            continue

        # Get city name
        city_name = row[city_idx].strip() if len(row) > city_idx else ""
        if not city_name:
            continue

        # Check if already casualized (skip if not overwriting)
        if not args.overwrite and len(row) > casual_idx and row[casual_idx].strip():
            continue

        rows_to_process.append({
            'row_num': i,
            'city_name': city_name
        })

    total_to_process = len(rows_to_process)
    print(f"Found {total_to_process} cities to casualize")

    if total_to_process == 0:
        print("Nothing to process!")
        sys.exit(0)

    # Process in batches
    print(f"\nProcessing in batches of {BATCH_SIZE}...")
    updates = []
    processed = 0

    for batch_start in range(0, total_to_process, BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE, total_to_process)
        batch = rows_to_process[batch_start:batch_end]

        batch_names = [item['city_name'] for item in batch]

        print(f"[{batch_start+1}-{batch_end}/{total_to_process}] Processing batch of {len(batch_names)} cities...")

        casual_names = casualize_city_names_batch(batch_names, client)

        # Prepare updates for this batch
        for i, item in enumerate(batch):
            casual_name = casual_names[i] if i < len(casual_names) else item['city_name']
            print(f"  {item['city_name']} → {casual_name}")

            # Sheet rows are 1-indexed, +1 for header
            updates.append({
                'range': f'{column_letter(casual_idx)}{item["row_num"] + 1}',
                'values': [[casual_name]]
            })

        processed += len(batch)

    # Batch update all cells at once
    print(f"\nUpdating {len(updates)} cells in Google Sheet...")
    if updates:
        worksheet.batch_update(updates)
        print(f"✅ Updated {len(updates)} casual city names")

    print(f"\n✅ Done! Casualized {processed} city names.")

if __name__ == "__main__":
    main()
