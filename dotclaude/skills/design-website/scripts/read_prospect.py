#!/usr/bin/env python3
"""
Read a single prospect row from a Google Sheet and output as JSON.
"""

import os
import sys
import json
import argparse
from dotenv import load_dotenv
import gspread
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

load_dotenv()

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets.readonly',
    'https://www.googleapis.com/auth/drive.readonly'
]


def get_credentials():
    creds = None
    if os.path.exists('token.json'):
        try:
            with open('token.json', 'r') as f:
                token_data = json.load(f)
                creds = Credentials.from_authorized_user_info(token_data, SCOPES)
        except Exception:
            pass

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            creds_file = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "credentials.json")
            flow = InstalledAppFlow.from_client_secrets_file(creds_file, SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as f:
            f.write(creds.to_json())

    return creds


def extract_sheet_id(url):
    if '/d/' in url:
        return url.split('/d/')[1].split('/')[0]
    return url


def normalize_key(key):
    """Normalize column header to a standard key."""
    k = key.strip().lower().replace(' ', '_').replace('-', '_')
    mapping = {
        'company': 'company_name',
        'company_name': 'company_name',
        'organization_name': 'company_name',
        'about': 'description',
        'description': 'description',
        'company_description': 'description',
        'keywords': 'keywords',
        'services': 'keywords',
        'company_keywords': 'keywords',
        'phone': 'phone',
        'phone_number': 'phone',
        'company_phone': 'phone',
        'email': 'email',
        'contact_email': 'email',
        'address': 'address',
        'full_address': 'address',
        'company_address': 'address',
        'city': 'city',
        'state': 'state',
        'country': 'country',
        'industry': 'industry',
        'category': 'industry',
        'first_name': 'first_name',
        'last_name': 'last_name',
        'title': 'title',
        'role': 'title',
        'website': 'website',
        'company_website': 'website',
    }
    return mapping.get(k, k)


def read_prospect(sheet_url, row_number, worksheet_name=None):
    creds = get_credentials()
    client = gspread.authorize(creds)

    sheet_id = extract_sheet_id(sheet_url)
    spreadsheet = client.open_by_key(sheet_id)

    if worksheet_name:
        worksheet = spreadsheet.worksheet(worksheet_name)
    else:
        worksheet = spreadsheet.sheet1

    records = worksheet.get_all_records()

    if row_number < 1 or row_number > len(records):
        print(f"Error: Row {row_number} out of range (1-{len(records)})", file=sys.stderr)
        sys.exit(1)

    raw = records[row_number - 1]

    # Normalize keys
    prospect = {}
    for key, value in raw.items():
        normalized = normalize_key(key)
        if value:  # Skip empty values
            prospect[normalized] = str(value)

    return prospect


def main():
    parser = argparse.ArgumentParser(description="Read a prospect from Google Sheets")
    parser.add_argument("--url", required=True, help="Google Sheets URL or ID")
    parser.add_argument("--row", required=True, type=int, help="Row number (1-indexed, excluding header)")
    parser.add_argument("--worksheet", help="Worksheet name (default: first sheet)")

    args = parser.parse_args()
    prospect = read_prospect(args.url, args.row, args.worksheet)
    print(json.dumps(prospect, indent=2))


if __name__ == "__main__":
    main()
