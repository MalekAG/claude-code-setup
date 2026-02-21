#!/usr/bin/env python3
"""
Create Gmail filters programmatically for any registered account.

Usage:
    python3 execution/gmail_create_filters.py --account youruser --setup-all
    python3 execution/gmail_create_filters.py --account yourcompany --list
"""

import os
import sys
import argparse
import json
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.labels",
    "https://www.googleapis.com/auth/gmail.settings.basic",
]

ACCOUNTS_FILE = "gmail_accounts.json"

# Standard filter configurations
ACCOUNTING_SENDERS = [
    "stripe.com",
    "anthropic.com",
    "aws.amazon.com",
    "mercury.com",
    "klaviyo.com",
    "infocusllp.ca",
    "infocusllp.com",
    "jamesbakercpa.com",
    "interac.ca",
]

META_SENDERS = [
    "facebookmail.com",
    "noreply@business-updates.facebook.com",
    "noreply@business.fb.com",
]

CALENDAR_SENDERS = [
    "hello@cal.com",
    "calendar-notification@google.com",
    "notifications@calendly.com",
]

CALENDAR_SUBJECTS = [
    "Accepted:",
    "Invitation:",
]


def load_accounts() -> dict:
    if os.path.exists(ACCOUNTS_FILE):
        with open(ACCOUNTS_FILE, "r") as f:
            return json.load(f)
    return {}


def get_gmail_service(account: str):
    accounts = load_accounts()
    if account not in accounts:
        print(f"Error: Account '{account}' not found. Available: {list(accounts.keys())}", file=sys.stderr)
        sys.exit(1)

    token_file = accounts[account].get("token_file")
    if not token_file or not os.path.exists(token_file):
        print(f"Error: Token file not found for {account}. Run gmail_multi_auth.py first.", file=sys.stderr)
        sys.exit(1)

    creds = Credentials.from_authorized_user_file(token_file, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(token_file, "w") as f:
                f.write(creds.to_json())
        else:
            print(f"Error: Invalid credentials for {account}. Re-run gmail_multi_auth.py", file=sys.stderr)
            sys.exit(1)

    return build("gmail", "v1", credentials=creds)


def get_or_create_label(service, label_name: str) -> str:
    """Get label ID by name, creating if needed."""
    try:
        results = service.users().labels().list(userId="me").execute()
        for label in results.get("labels", []):
            if label["name"].lower() == label_name.lower():
                return label["id"]

        # Create it
        created = service.users().labels().create(
            userId="me",
            body={
                "name": label_name,
                "labelListVisibility": "labelShow",
                "messageListVisibility": "show"
            }
        ).execute()
        print(f"  Created label: {label_name}")
        return created["id"]
    except HttpError as e:
        print(f"  Error with label {label_name}: {e}", file=sys.stderr)
        return None


def create_filter(service, criteria: dict, action: dict) -> bool:
    """Create a single filter."""
    try:
        service.users().settings().filters().create(
            userId="me",
            body={"criteria": criteria, "action": action}
        ).execute()
        return True
    except HttpError as e:
        if "Filter already exists" in str(e):
            return True  # Already exists is fine
        print(f"    Error: {e}", file=sys.stderr)
        return False


def list_filters(service):
    """List all existing filters."""
    try:
        results = service.users().settings().filters().list(userId="me").execute()
        filters = results.get("filter", [])

        if not filters:
            print("No filters configured.")
            return

        print(f"Found {len(filters)} filters:\n")
        for f in filters:
            criteria = f.get("criteria", {})
            action = f.get("action", {})

            crit_parts = []
            if criteria.get("from"):
                crit_parts.append(f"from:{criteria['from']}")
            if criteria.get("to"):
                crit_parts.append(f"to:{criteria['to']}")
            if criteria.get("subject"):
                crit_parts.append(f"subject:{criteria['subject']}")
            if criteria.get("query"):
                crit_parts.append(f"query:{criteria['query']}")

            act_parts = []
            if action.get("addLabelIds"):
                act_parts.append(f"+labels:{action['addLabelIds']}")
            if action.get("removeLabelIds"):
                act_parts.append(f"-labels:{action['removeLabelIds']}")

            print(f"  {' '.join(crit_parts) or '(no criteria)'}")
            print(f"    → {' '.join(act_parts) or '(no action)'}")
            print()

    except HttpError as e:
        print(f"Error listing filters: {e}", file=sys.stderr)


def setup_all_filters(service, dry_run: bool = False):
    """Set up all standard filters."""

    # Get/create Accounting label
    print("Setting up Accounting filters...")
    accounting_label_id = get_or_create_label(service, "Accounting")

    if accounting_label_id:
        for sender in ACCOUNTING_SENDERS:
            desc = f"  from:{sender} → Accounting + archive"
            if dry_run:
                print(f"  [DRY RUN] {desc}")
            else:
                success = create_filter(
                    service,
                    {"from": sender},
                    {"addLabelIds": [accounting_label_id], "removeLabelIds": ["INBOX"]}
                )
                print(f"  {'✓' if success else '✗'} {desc}")

    print("\nSetting up Meta/Facebook filters (auto-archive + read)...")
    for sender in META_SENDERS:
        desc = f"  from:{sender} → archive + mark read"
        if dry_run:
            print(f"  [DRY RUN] {desc}")
        else:
            success = create_filter(
                service,
                {"from": sender},
                {"removeLabelIds": ["INBOX", "UNREAD"]}
            )
            print(f"  {'✓' if success else '✗'} {desc}")

    print("\nSetting up Calendar filters (auto-read)...")
    for sender in CALENDAR_SENDERS:
        desc = f"  from:{sender} → mark read"
        if dry_run:
            print(f"  [DRY RUN] {desc}")
        else:
            success = create_filter(
                service,
                {"from": sender},
                {"removeLabelIds": ["UNREAD"]}
            )
            print(f"  {'✓' if success else '✗'} {desc}")

    for subject in CALENDAR_SUBJECTS:
        desc = f"  subject:{subject} → mark read"
        if dry_run:
            print(f"  [DRY RUN] {desc}")
        else:
            success = create_filter(
                service,
                {"subject": subject},
                {"removeLabelIds": ["UNREAD"]}
            )
            print(f"  {'✓' if success else '✗'} {desc}")

    print("\nDone!")


def main():
    parser = argparse.ArgumentParser(description="Create Gmail filters for any account")
    parser.add_argument("--account", "-a", required=True, help="Account name")
    parser.add_argument("--list", "-l", action="store_true", help="List existing filters")
    parser.add_argument("--setup-all", action="store_true", help="Set up all standard filters")
    parser.add_argument("--dry-run", "-n", action="store_true", help="Show what would be done")

    args = parser.parse_args()

    print(f"Connecting to Gmail API [{args.account}]...")
    service = get_gmail_service(args.account)

    if args.list:
        list_filters(service)
    elif args.setup_all:
        setup_all_filters(service, args.dry_run)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
