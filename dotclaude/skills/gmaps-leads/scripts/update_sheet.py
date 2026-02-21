#!/usr/bin/env python3
"""
Upload JSON data to a Google Sheet.
"""

import os
import sys
import json
import argparse
import pandas as pd
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

# Load environment variables
load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

def get_credentials():
    """
    Load Google credentials. Supports both Service Account and OAuth 2.0 (Installed App).
    """
    creds = None
    
    # 1. Try OAuth 2.0 Token (token.json)
    if os.path.exists('token.json'):
        from google.oauth2.credentials import Credentials as UserCredentials
        creds = UserCredentials.from_authorized_user_file('token.json', SCOPES)

    # 2. Refresh OAuth 2.0 Token if expired
    if creds and creds.expired and creds.refresh_token:
        from google.auth.transport.requests import Request
        try:
            creds.refresh(Request())
        except Exception as e:
            print(f"Error refreshing token: {e}", file=sys.stderr)
            creds = None

    # 3. If no valid user creds, try Service Account or new OAuth flow
    if not creds:
        # Check for Service Account
        service_account_file = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "service_account.json")
        
        if os.path.exists(service_account_file):
            # Check if it's a service account or client secret
            with open(service_account_file, 'r') as f:
                content = json.load(f)
                
            if "type" in content and content["type"] == "service_account":
                print("Using Service Account credentials...")
                creds = Credentials.from_service_account_file(service_account_file, scopes=SCOPES)
            elif "installed" in content:
                print("Using OAuth 2.0 Client Credentials...")
                from google_auth_oauthlib.flow import InstalledAppFlow
                flow = InstalledAppFlow.from_client_secrets_file(service_account_file, SCOPES)
                creds = flow.run_local_server(port=0)
                # Save the credentials for the next run
                with open('token.json', 'w') as token:
                    token.write(creds.to_json())
            else:
                print("Unknown credential type in JSON.", file=sys.stderr)
        else:
            print(f"Error: Credentials file '{service_account_file}' not found.", file=sys.stderr)
            return None
            
    return creds

def update_sheet(json_file, sheet_name=None):
    """
    Read JSON and upload to Google Sheet.
    """
    # Read JSON data
    try:
        with open(json_file, 'r') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error reading JSON file: {e}", file=sys.stderr)
        return None

    if not data:
        print("No data in JSON file.")
        return None

    # Convert to DataFrame for easier handling
    df = pd.json_normalize(data)
    
    # Authenticate
    creds = get_credentials()
    if not creds:
        return None
        
    client = gspread.authorize(creds)
    
    # Create or open sheet
    try:
        if sheet_name:
            try:
                sh = client.open(sheet_name)
                print(f"Opened existing sheet: {sheet_name}")
            except gspread.SpreadsheetNotFound:
                sh = client.create(sheet_name)
                print(f"Created new sheet: {sheet_name}")
        else:
            # Create a new sheet with a default name based on the file
            default_name = f"Leads Import - {os.path.basename(json_file)}"
            sh = client.create(default_name)
            print(f"Created new sheet: {default_name}")

        worksheet = sh.get_worksheet(0)

        # Clear existing content if it's a new import (optional, but good for cleanliness)
        worksheet.clear()

        # Prepare data for batch update
        all_data = [df.columns.values.tolist()] + df.values.tolist()

        # Resize worksheet if needed (Google Sheets default is 1000 rows × 26 columns)
        required_rows = len(all_data)
        required_cols = len(df.columns)
        current_rows = worksheet.row_count
        current_cols = worksheet.col_count

        if required_rows > current_rows or required_cols > current_cols:
            new_rows = max(required_rows, current_rows)
            new_cols = max(required_cols, current_cols)
            print(f"Resizing worksheet from {current_rows}×{current_cols} to {new_rows}×{new_cols}...")
            worksheet.resize(rows=new_rows, cols=new_cols)

        # Calculate the column range dynamically based on the number of columns
        num_cols = len(df.columns)

        def col_index_to_letter(n):
            """Convert column index (0-based) to Excel-style letter (A, B, ..., Z, AA, AB, etc.)"""
            result = ""
            while n >= 0:
                result = chr(n % 26 + 65) + result
                n = n // 26 - 1
            return result

        end_col = col_index_to_letter(num_cols - 1)

        # Use batch_update for better performance with large datasets
        # This is more efficient than update() for datasets > 1000 rows
        if len(all_data) > 1000:
            print(f"Large dataset detected ({len(all_data)} rows, {num_cols} columns). Using batch update...")

            # Split into chunks of 1000 rows to avoid API limits
            chunk_size = 1000
            for i in range(0, len(all_data), chunk_size):
                chunk = all_data[i:i + chunk_size]
                start_row = i + 1  # gspread is 1-indexed
                end_row = start_row + len(chunk) - 1

                range_name = f"A{start_row}:{end_col}{end_row}"
                worksheet.update(values=chunk, range_name=range_name, value_input_option='RAW')
                print(f"  Updated rows {start_row}-{end_row}")
        else:
            # For smaller datasets, single update is fine
            worksheet.update(values=[df.columns.values.tolist()] + df.values.tolist(), value_input_option='RAW')
        
        # Share with user if email is provided in env (optional enhancement)
        user_email = os.getenv("USER_EMAIL")
        if user_email:
            sh.share(user_email, perm_type='user', role='writer')
            print(f"Shared sheet with {user_email}")

        return sh.url

    except Exception as e:
        print(f"Error updating sheet: {e}", file=sys.stderr)
        return None

def main():
    parser = argparse.ArgumentParser(description="Upload JSON to Google Sheet")
    parser.add_argument("json_file", help="Path to the JSON file containing leads")
    parser.add_argument("--sheet_name", help="Name of the Google Sheet (optional)")

    args = parser.parse_args()

    url = update_sheet(args.json_file, args.sheet_name)
    
    if url:
        print(f"Success! Sheet URL: {url}")
    else:
        print("Failed to update sheet.")
        sys.exit(1)

if __name__ == "__main__":
    main()
