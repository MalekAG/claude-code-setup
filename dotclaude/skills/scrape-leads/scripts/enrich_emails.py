#!/usr/bin/env python3
"""
Enrich missing emails using AnyMailFinder API.
"""

import os
import sys
import json
import argparse
import time
from dotenv import load_dotenv
import gspread
from google.oauth2.credentials import Credentials
from google.oauth2.service_account import Credentials as ServiceAccountCredentials
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# Load environment variables
load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

def get_credentials():
    """
    Load Google credentials (reuse logic from update_sheet.py).
    """
    creds = None
    
    # Try OAuth 2.0 Token
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)

    # Refresh if expired
    if creds and creds.expired and creds.refresh_token:
        from google.auth.transport.requests import Request
        try:
            creds.refresh(Request())
        except Exception as e:
            print(f"Error refreshing token: {e}")
            creds = None

    # Try Service Account or new OAuth flow
    if not creds:
        service_account_file = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "service_account.json")
        
        if os.path.exists(service_account_file):
            with open(service_account_file, 'r') as f:
                content = json.load(f)
                
            if "type" in content and content["type"] == "service_account":
                print("Using Service Account credentials...")
                creds = ServiceAccountCredentials.from_service_account_file(service_account_file, scopes=SCOPES)
            elif "installed" in content:
                print("Using OAuth 2.0 Client Credentials...")
                from google_auth_oauthlib.flow import InstalledAppFlow
                flow = InstalledAppFlow.from_client_secrets_file(service_account_file, SCOPES)
                creds = flow.run_local_server(port=0)
                with open('token.json', 'w') as token:
                    token.write(creds.to_json())
            
    return creds

def find_email_with_anymailfinder(first_name, last_name, full_name, company_domain, company_name):
    """
    Query AnyMailFinder API to find an email.
    """
    api_key = os.getenv("ANYMAILFINDER_API_KEY")
    if not api_key:
        print("Error: ANYMAILFINDER_API_KEY not found in .env")
        return None
    
    # Correct endpoint from documentation
    url = "https://api.anymailfinder.com/v5.1/find-email/person"
    headers = {
        "Authorization": api_key,  # Just the API key, not "Bearer {api_key}"
        "Content-Type": "application/json"
    }
    
    # Prepare request body - provide ALL available data for best results
    body = {}
    
    # Provide all name fields if available
    if full_name:
        body["full_name"] = full_name
    if first_name:
        body["first_name"] = first_name
    if last_name:
        body["last_name"] = last_name
    
    # Provide all company fields if available (domain is preferred)
    if company_domain:
        body["domain"] = company_domain
    if company_name:
        body["company_name"] = company_name
    
    # Need at least name and company info
    has_name = full_name or (first_name and last_name)
    has_company = company_domain or company_name
    
    if not has_name or not has_company:
        return None
    
    try:
        response = requests.post(url, headers=headers, json=body, timeout=180)  # 180s timeout per docs
        response.raise_for_status()
        data = response.json()
        
        # Check if email was found
        if data.get("email") and data.get("email_status") in ["valid", "risky"]:
            return data["email"]
        
        return None
        
    except Exception as e:
        print(f"Error querying AnyMailFinder: {e}")
        return None

def create_bulk_search(rows_data):
    """
    Create a bulk search using AnyMailFinder bulk API.
    Returns the search ID if successful.
    """
    api_key = os.getenv("ANYMAILFINDER_API_KEY")
    if not api_key:
        print("Error: ANYMAILFINDER_API_KEY not found in .env")
        return None

    url = "https://api.anymailfinder.com/v5.1/bulk/json"
    headers = {
        "Authorization": api_key,
        "Content-Type": "application/json"
    }

    # Prepare data table: [headers, ...rows]
    table_data = [
        ["first_name", "last_name", "full_name", "domain", "company_name"]
    ]

    for row in rows_data:
        table_data.append([
            row.get('first_name', ''),
            row.get('last_name', ''),
            row.get('full_name', ''),
            row.get('company_domain', ''),
            row.get('company_name', '')
        ])

    body = {
        "data": table_data,
        "first_name_field_index": 0,
        "last_name_field_index": 1,
        "full_name_field_index": 2,
        "domain_field_index": 3,
        "company_name_field_index": 4,
        "file_name": f"sheet_enrichment_{time.strftime('%Y%m%d_%H%M%S')}"
    }

    try:
        response = requests.post(url, headers=headers, json=body, timeout=30)
        response.raise_for_status()
        data = response.json()

        search_id = data.get("id")
        if search_id:
            print(f"✅ Bulk search created: ID {search_id}")
            return search_id
        else:
            print(f"Error: No search ID returned")
            return None

    except Exception as e:
        print(f"Error creating bulk search: {e}")
        return None

def poll_bulk_search_status(search_id):
    """
    Poll the status of a bulk search until it completes.
    Returns True if completed successfully.
    """
    api_key = os.getenv("ANYMAILFINDER_API_KEY")
    if not api_key:
        return False

    url = f"https://api.anymailfinder.com/v5.1/bulk/{search_id}"
    headers = {
        "Authorization": api_key
    }
    
    print("\nPolling bulk search status...")
    
    while True:
        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            status = data.get("status")
            progress = data.get("progress", {})
            total = progress.get("total", 0)
            processed = progress.get("processed", 0)
            
            if status == "completed":
                print(f"✅ Bulk search completed! ({processed}/{total} rows)")
                return True
            elif status == "failed":
                print(f"❌ Bulk search failed")
                return False
            elif status in ["queued", "running"]:
                print(f"⏳ Status: {status} - {processed}/{total} rows processed...")
                time.sleep(10)  # Poll every 10 seconds
            else:
                print(f"Status: {status}")
                time.sleep(10)
                
        except Exception as e:
            print(f"Error polling status: {e}")
            return False

def download_bulk_results(search_id):
    """
    Download the results of a completed bulk search.
    Returns a list of results with emails.
    """
    api_key = os.getenv("ANYMAILFINDER_API_KEY")
    if not api_key:
        return None
    
    url = f"https://api.anymailfinder.com/v5.1/bulk/{search_id}/download"
    headers = {
        "Authorization": api_key
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=60)
        response.raise_for_status()
        data = response.json()
        
        results = data.get("data", [])
        print(f"📥 Downloaded {len(results)} results")
        return results
        
    except Exception as e:
        print(f"Error downloading results: {e}")
        return None

def enrich_sheet(sheet_url):
    """
    Enrich a Google Sheet by finding missing emails.
    """
    # Authenticate
    creds = get_credentials()
    if not creds:
        print("Error: Could not authenticate with Google")
        return None
        
    client = gspread.authorize(creds)
    
    # Open the sheet
    try:
        sheet = client.open_by_url(sheet_url)
        worksheet = sheet.get_worksheet(0)
    except Exception as e:
        print(f"Error opening sheet: {e}")
        return None
    
    # Get all records
    records = worksheet.get_all_records()
    
    if not records:
        print("No records found in sheet")
        return sheet_url
    
    # Find email column index once
    email_col = None
    headers = worksheet.row_values(1)
    for col_idx, header in enumerate(headers):
        if header.lower() == "email":
            email_col = col_idx + 1  # gspread is 1-indexed
            break
    
    if not email_col:
        print("Error: Could not find 'email' column in sheet")
        return None
    
    # Collect rows that need enrichment
    rows_to_enrich = []
    for idx, record in enumerate(records):
        row_num = idx + 2  # +2 because header is row 1 and idx is 0-based
        
        # Check if email is missing
        email = record.get("email", "").strip()
        if email:
            continue  # Email already exists
        
        # Extract required fields
        first_name = record.get("first_name", "").strip()
        last_name = record.get("last_name", "").strip()
        full_name = record.get("full_name", "").strip()
        company_domain = record.get("company_domain", "").strip()
        company_name = record.get("company_name", "").strip()
        
        rows_to_enrich.append({
            'row_num': row_num,
            'first_name': first_name,
            'last_name': last_name,
            'full_name': full_name,
            'company_domain': company_domain,
            'company_name': company_name
        })
    
    if not rows_to_enrich:
        print("No rows need email enrichment")
        return sheet_url
    
    print(f"Processing {len(rows_to_enrich)} rows with missing emails...\n")
    
    # Auto-detect: Use bulk API for 200+ rows, concurrent for smaller datasets
    if len(rows_to_enrich) >= 200:
        print(f"🚀 Using BULK API for {len(rows_to_enrich)} rows (faster for large datasets)")
        result = enrich_with_bulk_api(worksheet, email_col, rows_to_enrich, sheet_url)

        # Fallback to concurrent API if bulk API fails
        if result is None:
            print(f"\n⚠️  Bulk API failed. Falling back to CONCURRENT API...")
            return enrich_with_concurrent_api(worksheet, email_col, rows_to_enrich, sheet_url)
        return result
    else:
        print(f"⚡ Using CONCURRENT API for {len(rows_to_enrich)} rows")
        return enrich_with_concurrent_api(worksheet, email_col, rows_to_enrich, sheet_url)

def enrich_with_bulk_api(worksheet, email_col, rows_to_enrich, sheet_url):
    """Enrich using bulk API (for 200+ rows)."""
    
    # Create bulk search
    search_id = create_bulk_search(rows_to_enrich)
    if not search_id:
        print("Failed to create bulk search")
        return None
    
    # Poll until complete
    if not poll_bulk_search_status(search_id):
        print("Bulk search did not complete successfully")
        return None
    
    # Download results
    results = download_bulk_results(search_id)
    if not results:
        print("Failed to download results")
        return None
    
    # Map results back to rows (excluding header row)
    enriched_count = 0
    failed_count = 0
    updates_to_apply = []
    
    # Results start from index 1 (skip header at index 0)
    for idx, result_row in enumerate(results[1:], start=0):
        if idx >= len(rows_to_enrich):
            break
        
        row_data = rows_to_enrich[idx]
        row_num = row_data['row_num']
        
        # Result row format: [first_name, last_name, full_name, domain, company_name, email, email_status]
        email = result_row[5] if len(result_row) > 5 else None
        email_status = result_row[6] if len(result_row) > 6 else None
        
        if email and email_status in ['valid', 'risky']:
            updates_to_apply.append({
                'row': row_num,
                'col': email_col,
                'value': email
            })
            print(f"  ✅ Row {row_num}: Found: {email}")
            enriched_count += 1
        else:
            display_name = row_data['full_name'] or f"{row_data['first_name']} {row_data['last_name']}"
            print(f"  ⚠️  Row {row_num}: Email not found for {display_name}")
            failed_count += 1
    
    # Batch update sheet
    if updates_to_apply:
        print(f"\nBatch updating {len(updates_to_apply)} cells in sheet...")
        cell_list = []
        for update in updates_to_apply:
            cell = worksheet.cell(update['row'], update['col'])
            cell.value = update['value']
            cell_list.append(cell)
        worksheet.update_cells(cell_list, value_input_option='RAW')
        print(f"✅ Batch update complete!")
    
    print(f"\nEnrichment complete:")
    print(f"  - Emails found: {enriched_count}")
    print(f"  - Not found: {failed_count}")
    
    return sheet_url

def enrich_with_concurrent_api(worksheet, email_col, rows_to_enrich, sheet_url):
    """Enrich using concurrent API calls (for <200 rows)."""

    enriched_count = 0
    failed_count = 0

    def enrich_row(row_data):
        """Helper function to enrich a single row."""
        row_num = row_data['row_num']
        display_name = row_data['full_name'] or f"{row_data['first_name']} {row_data['last_name']}"
        display_company = row_data['company_domain'] or row_data['company_name']

        print(f"Row {row_num}: Querying for {display_name} at {display_company}")

        found_email = find_email_with_anymailfinder(
            row_data['first_name'],
            row_data['last_name'],
            row_data['full_name'],
            row_data['company_domain'],
            row_data['company_name']
        )

        return {
            'row_num': row_num,
            'email': found_email,
            'display_name': display_name
        }

    # Use ThreadPoolExecutor to process up to 20 emails concurrently
    with ThreadPoolExecutor(max_workers=20) as executor:
        future_to_row = {executor.submit(enrich_row, row): row for row in rows_to_enrich}

        # Collect updates for batch processing
        updates_to_apply = []

        for future in as_completed(future_to_row):
            result = future.result()

            if result['email']:
                # Stage the update for batch processing
                updates_to_apply.append({
                    'row': result['row_num'],
                    'col': email_col,
                    'value': result['email']
                })
                print(f"  ✅ Row {result['row_num']}: Found: {result['email']}")
                enriched_count += 1
            else:
                print(f"  ⚠️  Row {result['row_num']}: Email not found for {result['display_name']}")
                failed_count += 1

    # Batch update all cells at once using range update (avoids per-cell API calls)
    if updates_to_apply:
        print(f"\nBatch updating {len(updates_to_apply)} cells in sheet...")

        # Prepare data for batch update using values_update (more efficient)
        # Group updates by row for batch processing
        try:
            # Use update() with cell list but avoid individual cell() calls
            # Instead, build the range notation directly
            batch_data = []
            for update in updates_to_apply:
                # Convert column number to letter
                col_letter = chr(64 + update['col'])  # A=65, B=66, etc.
                range_notation = f"{col_letter}{update['row']}"
                batch_data.append({
                    'range': range_notation,
                    'values': [[update['value']]]
                })

            # Use batch_update to update multiple ranges at once
            worksheet.spreadsheet.values_batch_update(
                body={
                    'value_input_option': 'RAW',
                    'data': batch_data
                }
            )
            print(f"✅ Batch update complete!")
        except Exception as e:
            print(f"Error during batch update: {e}")
            print("Attempting alternative update method...")
            # Fallback: use single range update with sorted data
            updates_to_apply.sort(key=lambda x: x['row'])
            for update in updates_to_apply:
                col_letter = chr(64 + update['col'])
                range_notation = f"{col_letter}{update['row']}"
                worksheet.update(range_notation, [[update['value']]], value_input_option='RAW')
                time.sleep(0.1)  # Small delay to avoid rate limits

    print(f"\nEnrichment complete:")
    print(f"  - Emails found: {enriched_count}")
    print(f"  - Not found: {failed_count}")

    return sheet_url

def main():
    parser = argparse.ArgumentParser(description="Enrich missing emails using AnyMailFinder")
    parser.add_argument("sheet_url", help="Google Sheet URL to enrich")

    args = parser.parse_args()

    result_url = enrich_sheet(args.sheet_url)
    
    if result_url:
        print(f"\nSuccess! Updated sheet: {result_url}")
    else:
        print("Enrichment failed.")
        sys.exit(1)

if __name__ == "__main__":
    main()
