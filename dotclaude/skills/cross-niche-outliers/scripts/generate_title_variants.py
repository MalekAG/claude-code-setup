#!/usr/bin/env python3
"""
Generate title variants from YouTube outlier videos.
Supports two modes:
- Mode A: Update existing Google Sheet with variant columns
- Mode B: Create new Google Sheet from JSON input
"""

import os
import sys
import json
import argparse
from datetime import datetime
from dotenv import load_dotenv
from anthropic import Anthropic
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# Load environment variables
load_dotenv()

# Configuration
VARIANTS_PER_TITLE = 3
MODEL = "claude-sonnet-4-5-20250929"
MAX_TOKENS = 500


def get_credentials():
    """
    Get OAuth2 credentials for Google Sheets API.
    Uses token.json if available.

    Returns:
        Credentials object
    """
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]

    creds = None

    if os.path.exists('token.json'):
        try:
            with open('token.json', 'r') as token:
                token_data = json.load(token)
                creds = Credentials.from_authorized_user_info(token_data, scopes)
        except Exception as e:
            print(f"Error loading token: {e}")

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            creds_file = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "credentials.json")
            flow = InstalledAppFlow.from_client_secrets_file(creds_file, scopes)
            creds = flow.run_local_server(port=0)

        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    return creds


def extract_sheet_id(url):
    """Extract spreadsheet ID from Google Sheets URL."""
    if '/d/' in url:
        return url.split('/d/')[1].split('/')[0]
    return url


def read_sheet_data(sheet_url):
    """
    Read outlier data from Google Sheet.

    Args:
        sheet_url: Google Sheet URL

    Returns:
        List of dictionaries with outlier data
    """
    try:
        creds = get_credentials()
        service = build('sheets', 'v4', credentials=creds)
        sheet_id = extract_sheet_id(sheet_url)

        # Read all data
        result = service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range='A:Z'
        ).execute()

        values = result.get('values', [])
        if not values:
            print("No data found in sheet")
            return []

        # Extract headers and data
        headers = values[0]
        data = []

        for row in values[1:]:
            # Pad row to match header length
            row = row + [''] * (len(headers) - len(row))
            row_dict = dict(zip(headers, row))
            data.append(row_dict)

        return data

    except Exception as e:
        print(f"Error reading sheet: {str(e)}", file=sys.stderr)
        return []


def generate_title_variants(original_title, summary=None, variants_count=3):
    """
    Generate title variants using Claude.

    Args:
        original_title: Original outlier video title
        summary: Optional video summary for context
        variants_count: Number of variants to generate

    Returns:
        List of title variant strings
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY not found in .env", file=sys.stderr)
        return []

    client = Anthropic(api_key=api_key)

    context = f"\n\nVideo Summary: {summary}" if summary else ""

    prompt = f"""Analyze this high-performing YouTube video title and generate {variants_count} similar title variants.

Original Title: "{original_title}"{context}

Your task:
1. Identify the hook type (question, shock value, curiosity gap, promise, controversy)
2. Identify the emotional trigger (fear, excitement, curiosity, FOMO, authority)
3. Note structural patterns (format, length, punctuation, capitalization)
4. Extract core keywords and power words

Then generate {variants_count} NEW title variants that:
- Use the SAME hook type and emotional trigger
- Apply SIMILAR structural patterns
- Modify specific wording and angle
- Maintain the "outlier quality" that made the original perform well
- Are meaningfully different from each other
- Stay within YouTube's ~100 character recommendation

Return ONLY a JSON array of {variants_count} strings (the variant titles), nothing else.
Example format: ["Variant 1 title here", "Variant 2 title here", "Variant 3 title here"]"""

    try:
        message = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            messages=[{
                "role": "user",
                "content": prompt
            }]
        )

        response_text = message.content[0].text.strip()

        # Try to extract JSON if there's extra text
        if response_text.startswith('```'):
            response_text = response_text.split('```')[1]
            if response_text.startswith('json'):
                response_text = response_text[4:]
            response_text = response_text.strip()

        variants = json.loads(response_text)

        if isinstance(variants, list) and len(variants) == variants_count:
            return variants
        else:
            print(f"Warning: Unexpected response format for '{original_title}'")
            return []

    except Exception as e:
        print(f"Error generating variants for '{original_title}': {str(e)}", file=sys.stderr)
        return []


def update_sheet_with_variants(sheet_url, variants_data):
    """
    Update existing Google Sheet with variant columns.

    Args:
        sheet_url: Google Sheet URL
        variants_data: List of dicts with 'row_index' and 'variants'

    Returns:
        Boolean success status
    """
    try:
        creds = get_credentials()
        service = build('sheets', 'v4', credentials=creds)
        sheet_id = extract_sheet_id(sheet_url)

        # Get current sheet structure
        result = service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range='A1:Z1'
        ).execute()
        headers = result.get('values', [[]])[0]

        # Determine where to add variant columns
        next_col_index = len(headers)
        variant_cols = ['Title Variant 1', 'Title Variant 2', 'Title Variant 3']

        # Check if variant columns already exist
        variant_col_indices = []
        for col_name in variant_cols:
            if col_name in headers:
                variant_col_indices.append(headers.index(col_name))
            else:
                variant_col_indices.append(next_col_index)
                next_col_index += 1

        # Add headers if needed
        if len(headers) < next_col_index:
            new_headers = headers + variant_cols[len(headers) - variant_col_indices[0]:]
            service.spreadsheets().values().update(
                spreadsheetId=sheet_id,
                range='A1:Z1',
                valueInputOption='RAW',
                body={'values': [new_headers]}
            ).execute()

        # Prepare batch update
        updates = []
        for item in variants_data:
            row_num = item['row_index'] + 2  # +1 for header, +1 for 0-index
            variants = item['variants']

            for i, variant in enumerate(variants):
                col_letter = chr(ord('A') + variant_col_indices[i])
                updates.append({
                    'range': f'{col_letter}{row_num}',
                    'values': [[variant]]
                })

        # Batch update
        if updates:
            service.spreadsheets().values().batchUpdate(
                spreadsheetId=sheet_id,
                body={'data': updates, 'valueInputOption': 'RAW'}
            ).execute()

            print(f"✓ Updated {len(updates)} cells in sheet")
            return True

        return False

    except Exception as e:
        print(f"Error updating sheet: {str(e)}", file=sys.stderr)
        return False


def create_new_sheet_with_variants(outliers, variants_data):
    """
    Create a new Google Sheet with outliers and variants.

    Args:
        outliers: List of outlier dictionaries
        variants_data: List of dicts with variants

    Returns:
        Sheet URL
    """
    try:
        creds = get_credentials()
        service = build('sheets', 'v4', credentials=creds)

        # Create new spreadsheet
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        title = f"Title Variants - {timestamp}"

        spreadsheet = service.spreadsheets().create(body={
            'properties': {'title': title}
        }).execute()

        sheet_id = spreadsheet['spreadsheetId']
        sheet_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}"

        print(f"Created new sheet: {sheet_url}")

        # Prepare data
        headers = ['Original Title', 'Video Link', 'Title Variant 1', 'Title Variant 2', 'Title Variant 3', 'Source Summary']
        rows = [headers]

        for i, outlier in enumerate(outliers):
            original_title = outlier.get('title') or outlier.get('Title', '')
            video_link = outlier.get('video_link') or outlier.get('Video Link', '')
            summary = outlier.get('summary') or outlier.get('Summary', '')

            variants = variants_data[i]['variants'] if i < len(variants_data) else ['', '', '']
            # Pad variants to ensure we have 3
            variants = (variants + ['', '', ''])[:3]

            rows.append([original_title, video_link] + variants + [summary])

        # Write data
        service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range='A1:F',
            valueInputOption='RAW',
            body={'values': rows}
        ).execute()

        print(f"✓ Wrote {len(rows)-1} rows to new sheet")
        return sheet_url

    except Exception as e:
        print(f"Error creating new sheet: {str(e)}", file=sys.stderr)
        return None


def main():
    parser = argparse.ArgumentParser(description="Generate title variants from YouTube outliers")
    parser.add_argument("--sheet_url", help="Google Sheet URL with outliers (Mode A)")
    parser.add_argument("--input", help="JSON file with outliers (Mode B)")
    parser.add_argument("--limit", type=int, help="Limit number of outliers to process")
    parser.add_argument("--variants", type=int, default=3, help="Number of variants per title")

    args = parser.parse_args()

    if not args.sheet_url and not args.input:
        print("Error: Specify either --sheet_url or --input", file=sys.stderr)
        return 1

    global VARIANTS_PER_TITLE
    VARIANTS_PER_TITLE = args.variants

    # Load outlier data
    outliers = []
    mode = None

    if args.sheet_url:
        mode = 'A'
        print("Mode A: Updating existing Google Sheet")
        outliers = read_sheet_data(args.sheet_url)
    elif args.input:
        mode = 'B'
        print("Mode B: Creating new Google Sheet from JSON")
        try:
            with open(args.input, 'r') as f:
                outliers = json.load(f)
        except Exception as e:
            print(f"Error loading input file: {str(e)}", file=sys.stderr)
            return 1

    if not outliers:
        print("No outliers found to process")
        return 1

    # Apply limit if specified
    if args.limit:
        outliers = outliers[:args.limit]

    print(f"Processing {len(outliers)} outliers...")

    # Generate variants
    variants_data = []
    for i, outlier in enumerate(outliers, 1):
        title = outlier.get('title') or outlier.get('Title', '')
        summary = outlier.get('summary') or outlier.get('Summary', '')

        if not title:
            print(f"  [{i}/{len(outliers)}] Skipping row with no title")
            variants_data.append({'row_index': i-1, 'variants': ['', '', '']})
            continue

        print(f"  [{i}/{len(outliers)}] Generating variants for: {title[:60]}...")

        variants = generate_title_variants(title, summary, VARIANTS_PER_TITLE)

        if not variants or len(variants) != VARIANTS_PER_TITLE:
            # Pad with empty strings if generation failed
            variants = (variants + [''] * VARIANTS_PER_TITLE)[:VARIANTS_PER_TITLE]

        variants_data.append({
            'row_index': i - 1,
            'variants': variants
        })

    # Output based on mode
    if mode == 'A':
        success = update_sheet_with_variants(args.sheet_url, variants_data)
        if success:
            print(f"\n✓ Successfully updated sheet with {VARIANTS_PER_TITLE} variant columns")
            print(f"  Sheet URL: {args.sheet_url}")
        else:
            print("\n✗ Failed to update sheet")
            return 1
    else:  # Mode B
        sheet_url = create_new_sheet_with_variants(outliers, variants_data)
        if sheet_url:
            print(f"\n✓ Successfully created new sheet with variants")
            print(f"  Sheet URL: {sheet_url}")
        else:
            print("\n✗ Failed to create new sheet")
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
