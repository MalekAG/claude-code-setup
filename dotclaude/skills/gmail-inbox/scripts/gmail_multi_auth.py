#!/usr/bin/env python3
"""
Authorize multiple Gmail accounts for unified management.

Each account gets its own token file (token_<account_name>.json).

Usage:
    python3 execution/gmail_multi_auth.py --account yourcompany
    python3 execution/gmail_multi_auth.py --account youruser
    python3 execution/gmail_multi_auth.py --list
"""

import os
import sys
import argparse
import json
from pathlib import Path
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

load_dotenv()

# Gmail + Sheets + Drive scopes
SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.labels",
    "https://www.googleapis.com/auth/gmail.settings.basic",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

ACCOUNTS_FILE = "gmail_accounts.json"

# Map account names to their credentials files
CREDENTIALS_MAP = {
    "yourcompany": "credentials_yourcompany.json",
    "youruser": "credentials.json",
    "youruser_personal": "credentials_youruser_personal.json",
}
DEFAULT_CREDENTIALS = "credentials.json"


def get_credentials_file(account_name: str) -> str:
    """Get credentials file for an account."""
    return CREDENTIALS_MAP.get(account_name, DEFAULT_CREDENTIALS)


def get_token_file(account_name: str) -> str:
    """Get token filename for an account."""
    return f"token_{account_name}.json"


def load_accounts() -> dict:
    """Load registered accounts from config file."""
    if os.path.exists(ACCOUNTS_FILE):
        with open(ACCOUNTS_FILE, "r") as f:
            return json.load(f)
    return {}


def save_accounts(accounts: dict):
    """Save registered accounts to config file."""
    with open(ACCOUNTS_FILE, "w") as f:
        json.dump(accounts, f, indent=2)


def authorize_account(account_name: str, email_hint: str = None):
    """Authorize a Gmail account and save its token."""
    token_file = get_token_file(account_name)
    creds = None

    # Load existing token if it exists
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)

    # If no valid credentials, do the OAuth flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None

        if not creds:
            credentials_file = get_credentials_file(account_name)
            if not os.path.exists(credentials_file):
                print(f"Error: {credentials_file} not found.", file=sys.stderr)
                sys.exit(1)

            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)

            # Hint which account to use
            if email_hint:
                print(f"\nPlease sign in with: {email_hint}")

            creds = flow.run_local_server(port=0)

        # Save the credentials
        with open(token_file, "w") as token:
            token.write(creds.to_json())

    # Get the email address for this account
    from googleapiclient.discovery import build
    service = build("gmail", "v1", credentials=creds)
    profile = service.users().getProfile(userId="me").execute()
    email = profile.get("emailAddress", "unknown")

    # Save to accounts registry
    accounts = load_accounts()
    accounts[account_name] = {
        "email": email,
        "token_file": token_file
    }
    save_accounts(accounts)

    print(f"\nAuthorized: {account_name}")
    print(f"  Email: {email}")
    print(f"  Token: {token_file}")
    print(f"  Scopes: {creds.scopes}")

    return email


def list_accounts():
    """List all registered accounts."""
    accounts = load_accounts()

    if not accounts:
        print("No accounts registered yet.")
        print("\nTo add an account:")
        print("  python3 execution/gmail_multi_auth.py --account <name>")
        return

    print("Registered Gmail accounts:\n")
    for name, info in accounts.items():
        token_exists = os.path.exists(info.get("token_file", ""))
        status = "OK" if token_exists else "TOKEN MISSING"
        print(f"  {name}:")
        print(f"    Email: {info.get('email', 'unknown')}")
        print(f"    Token: {info.get('token_file', 'unknown')} [{status}]")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Authorize multiple Gmail accounts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Authorize an account:
    python3 execution/gmail_multi_auth.py --account yourcompany
    python3 execution/gmail_multi_auth.py --account youruser --email you@example.com

  List all accounts:
    python3 execution/gmail_multi_auth.py --list
        """
    )

    parser.add_argument("--account", "-a", help="Account name to authorize")
    parser.add_argument("--email", "-e", help="Email hint for OAuth flow")
    parser.add_argument("--list", "-l", action="store_true", help="List registered accounts")

    args = parser.parse_args()

    if args.list:
        list_accounts()
    elif args.account:
        authorize_account(args.account, args.email)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
