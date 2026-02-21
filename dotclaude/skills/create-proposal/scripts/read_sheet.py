#!/usr/bin/env python3
"""
Read leads from a Google Sheet and export to JSON.
"""

import os
import sys
import json
import argparse
from datetime import datetime
from dotenv import load_dotenv
import gspread
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import pickle

# Load environment variables
load_dotenv()


def extract_sheet_id(url):
    """
    Extract the Google Sheet ID from a URL.

    Args:
        url: Google Sheets URL

    Returns:
        Sheet ID string
    """
    if '/d/' in url:
        return url.split('/d/')[1].split('/')[0]
    return url  # Assume it's already just the ID


def get_credentials():
    """
    Get OAuth2 credentials for Google Sheets API.
    Uses token.json if available, otherwise prompts for authorization.

    Returns:
        Credentials object
    """
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]

    creds = None

    # Check if token.json exists
    if os.path.exists('token.json'):
        try:
            with open('token.json', 'r') as token:
                token_data = json.load(token)
                creds = Credentials.from_authorized_user_info(token_data, scopes)
        except Exception as e:
            print(f"Error loading token: {e}")

    # If credentials are invalid or don't exist, get new ones
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            creds_file = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "credentials.json")
            flow = InstalledAppFlow.from_client_secrets_file(creds_file, scopes)
            creds = flow.run_local_server(port=0)

        # Save credentials for next run
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    return creds


def read_google_sheet(sheet_url, worksheet_name=None):
    """
    Read data from a Google Sheet.

    Args:
        sheet_url: Google Sheets URL or ID
        worksheet_name: Name of the specific worksheet (default: first sheet)

    Returns:
        List of dictionaries containing lead data
    """
    try:
        creds = get_credentials()
        client = gspread.authorize(creds)

        # Open the spreadsheet
        sheet_id = extract_sheet_id(sheet_url)
        spreadsheet = client.open_by_key(sheet_id)

        # Get the worksheet
        if worksheet_name:
            worksheet = spreadsheet.worksheet(worksheet_name)
        else:
            worksheet = spreadsheet.sheet1  # First sheet by default

        # Get all records as dictionaries
        records = worksheet.get_all_records()

        print(f"Successfully read {len(records)} leads from Google Sheet")
        return records

    except Exception as e:
        print(f"Error reading Google Sheet: {str(e)}", file=sys.stderr)
        return None


def save_leads(leads, prefix="leads_input"):
    """
    Save leads to a JSON file.

    Args:
        leads: List of lead dictionaries
        prefix: Prefix for the output filename

    Returns:
        Path to the saved file
    """
    if not leads:
        print("No leads to save.")
        return None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = ".tmp"
    os.makedirs(output_dir, exist_ok=True)

    filename = f"{output_dir}/{prefix}_{timestamp}.json"

    with open(filename, "w") as f:
        json.dump(leads, f, indent=2)

    print(f"Leads saved to {filename}")
    return filename


def main():
    parser = argparse.ArgumentParser(description="Read leads from Google Sheets")
    parser.add_argument("--url", required=True, help="Google Sheets URL or ID")
    parser.add_argument("--worksheet", help="Name of the worksheet (default: first sheet)")
    parser.add_argument("--output_prefix", default="leads_input", help="Prefix for output file")

    args = parser.parse_args()

    leads = read_google_sheet(args.url, args.worksheet)

    if leads:
        filename = save_leads(leads, prefix=args.output_prefix)
        if filename:
            # Print summary
            print(f"\nSummary:")
            print(f"  Total leads: {len(leads)}")
            if leads:
                print(f"  Fields: {', '.join(leads[0].keys())}")
            return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
