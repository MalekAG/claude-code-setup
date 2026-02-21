"""
One-time script to authorize Gmail API access.
Run this locally to generate a token with Gmail send scope.

Usage: python3 execution/gmail_auth.py
"""

import os
import json
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# Gmail + Sheets + Drive scopes
SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",  # Read, send, modify emails
    "https://www.googleapis.com/auth/gmail.labels",  # Manage labels
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"


def main():
    creds = None

    # Load existing token if it exists
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    # If no valid credentials, do the OAuth flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                # If refresh fails, re-auth
                creds = None

        if not creds:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        # Save the credentials
        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())

        print(f"Token saved to {TOKEN_FILE}")
        print(f"Scopes: {creds.scopes}")
    else:
        print("Credentials already valid!")
        print(f"Scopes: {creds.scopes}")


if __name__ == "__main__":
    main()
