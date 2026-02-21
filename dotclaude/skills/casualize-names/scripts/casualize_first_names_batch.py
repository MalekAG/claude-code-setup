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
BATCH_SIZE = 30  # Process 30 names per API call

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

def casualize_first_names_batch(first_names, client):
    """Use Claude to convert multiple first names to casual nicknames."""
    if not first_names:
        return []

    # Format first names as numbered list
    name_list = "\n".join([f"{i+1}. {name}" for i, name in enumerate(first_names)])

    prompt = f"""Convert these formal first names to their most common casual nicknames for cold emails. Use what feels natural and friendly.

Rules:
- Use the most common, widely-accepted nickname (e.g., "William" → "Will", not "Bill" or "Billy")
- If there's no common nickname, keep the original name
- Keep it professional - avoid overly casual or childish nicknames
- When in doubt, keep the original

Common examples:
- "William" → "Will"
- "Robert" → "Rob"
- "Jennifer" → "Jen"
- "Michael" → "Mike"
- "Christopher" → "Chris"
- "Elizabeth" → "Liz"
- "Matthew" → "Matt"
- "Daniel" → "Dan"
- "Richard" → "Rick"
- "Katherine" → "Kate"
- "Nicholas" → "Nick"
- "Benjamin" → "Ben"
- "Alexander" → "Alex"
- "Rebecca" → "Becca"
- "Jonathan" → "Jon"
- "Anthony" → "Tony"
- "Timothy" → "Tim"
- "Andrew" → "Andy"
- "Joseph" → "Joe"
- "Thomas" → "Tom"

Names that typically stay the same:
- "John" → "John"
- "Sarah" → "Sarah"
- "David" → "David" (though "Dave" is also common)
- "Mark" → "Mark"
- "Paul" → "Paul"
- "Lisa" → "Lisa"
- "Amy" → "Amy"
- "Eric" → "Eric"
- "Ryan" → "Ryan"

First names to convert:
{name_list}

Output format: Return ONLY a numbered list with the casual name for each person, one per line. No explanations.
Example output:
1. Will
2. Rob
3. Jen
4. John"""

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
        if len(casual_names) != len(first_names):
            print(f"  ! Warning: Got {len(casual_names)} results for {len(first_names)} inputs")
            # Pad with original names if needed
            while len(casual_names) < len(first_names):
                casual_names.append(first_names[len(casual_names)])

        return casual_names
    except Exception as e:
        print(f"  ! API Error: {e}")
        return first_names  # Return originals if error

def main():
    parser = argparse.ArgumentParser(description="Casualize first names to nicknames for cold email (batched)")
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
        first_name_idx = headers.index("first_name")
    except ValueError as e:
        print(f"Error: Missing required column: {e}")
        print(f"Available columns: {headers}")
        sys.exit(1)

    # Check if casual_first_name column exists
    if "casual_first_name" in headers:
        casual_idx = headers.index("casual_first_name")
        print(f"Using existing 'casual_first_name' column at index {casual_idx}")
    else:
        # Add new column
        print("Adding new 'casual_first_name' column...")
        casual_idx = len(headers)

        # Resize sheet to add new column if needed
        current_cols = worksheet.col_count
        if casual_idx >= current_cols:
            worksheet.resize(cols=casual_idx + 1)
            print(f"Resized sheet to {casual_idx + 1} columns")

        worksheet.update_cell(1, casual_idx + 1, "casual_first_name")
        headers.append("casual_first_name")
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

        # Get first name
        first_name = row[first_name_idx].strip() if len(row) > first_name_idx else ""
        if not first_name:
            continue

        # Check if already casualized (skip if not overwriting)
        if not args.overwrite and len(row) > casual_idx and row[casual_idx].strip():
            continue

        rows_to_process.append({
            'row_num': i,
            'first_name': first_name
        })

    total_to_process = len(rows_to_process)
    print(f"Found {total_to_process} first names to casualize")

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

        batch_names = [item['first_name'] for item in batch]

        print(f"[{batch_start+1}-{batch_end}/{total_to_process}] Processing batch of {len(batch_names)} names...")

        casual_names = casualize_first_names_batch(batch_names, client)

        # Prepare updates for this batch
        for i, item in enumerate(batch):
            casual_name = casual_names[i] if i < len(casual_names) else item['first_name']
            print(f"  {item['first_name']} → {casual_name}")

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
        print(f"✅ Updated {len(updates)} casual first names")

    print(f"\n✅ Done! Casualized {processed} first names.")

if __name__ == "__main__":
    main()
