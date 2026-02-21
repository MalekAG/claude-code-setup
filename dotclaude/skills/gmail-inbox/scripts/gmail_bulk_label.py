#!/usr/bin/env python3
"""
Bulk label Gmail emails based on search query.

This script efficiently labels large numbers of emails by:
1. Paginating through ALL matching emails (not just 100)
2. Applying labels in efficient batches
3. Optionally removing from inbox (archiving)

Usage:
    python3 execution/gmail_bulk_label.py --query "subject:invoice" --label "Accounting"
    python3 execution/gmail_bulk_label.py --query "from:noreply@example.com" --label "Automated" --archive
    python3 execution/gmail_bulk_label.py --query "is:unread from:newsletters@" --label "Newsletters" --mark-read

Options:
    --query      Gmail search query (required)
    --label      Label name to apply - will be created if it doesn't exist (required)
    --archive    Remove from inbox after labeling
    --mark-read  Mark emails as read
    --dry-run    Show what would be done without making changes
    --batch-size Number of emails per batch (default: 100)
"""

import os
import sys
import argparse
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Load environment variables
load_dotenv()

# Gmail API scopes - need modify for labeling
SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.labels",
]

CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"
ACCOUNTS_FILE = "gmail_accounts.json"


def load_accounts() -> dict:
    """Load registered accounts from config file."""
    import json
    if os.path.exists(ACCOUNTS_FILE):
        with open(ACCOUNTS_FILE, "r") as f:
            return json.load(f)
    return {}


def get_gmail_service(account: str = None):
    """Authenticate and return Gmail API service."""
    creds = None

    # Determine token file based on account
    if account:
        accounts = load_accounts()
        if account not in accounts:
            print(f"Error: Account '{account}' not found. Available: {list(accounts.keys())}", file=sys.stderr)
            sys.exit(1)
        token_file = accounts[account].get("token_file", TOKEN_FILE)
    else:
        token_file = TOKEN_FILE

    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                with open(token_file, "w") as f:
                    f.write(creds.to_json())
            except Exception:
                creds = None

        if not creds:
            print(f"Error: Valid credentials not found for {account or 'default'}. Run gmail_multi_auth.py first.", file=sys.stderr)
            sys.exit(1)

    return build("gmail", "v1", credentials=creds)


def get_or_create_label(service, label_name: str) -> str:
    """Get label ID by name, creating it if it doesn't exist."""
    try:
        results = service.users().labels().list(userId="me").execute()
        labels = results.get("labels", [])

        for label in labels:
            if label["name"].lower() == label_name.lower():
                print(f"Found existing label: {label_name} (ID: {label['id']})")
                return label["id"]

        # Label doesn't exist, create it
        label_body = {
            "name": label_name,
            "labelListVisibility": "labelShow",
            "messageListVisibility": "show"
        }
        created = service.users().labels().create(userId="me", body=label_body).execute()
        print(f"Created new label: {label_name} (ID: {created['id']})")
        return created["id"]

    except HttpError as e:
        print(f"Error getting/creating label: {e}", file=sys.stderr)
        sys.exit(1)


def search_all_messages(service, query: str) -> list[str]:
    """Search for all messages matching query, handling pagination."""
    message_ids = []
    page_token = None
    page_num = 0

    print(f"Searching for: {query}")

    while True:
        try:
            results = service.users().messages().list(
                userId="me",
                q=query,
                pageToken=page_token,
                maxResults=500  # Max allowed per request
            ).execute()

            messages = results.get("messages", [])
            if messages:
                message_ids.extend([msg["id"] for msg in messages])
                page_num += 1
                print(f"  Page {page_num}: Found {len(messages)} emails (total: {len(message_ids)})")

            page_token = results.get("nextPageToken")
            if not page_token:
                break

        except HttpError as e:
            print(f"Error searching messages: {e}", file=sys.stderr)
            break

    print(f"Total emails found: {len(message_ids)}")
    return message_ids


def batch_modify_messages(
    service,
    message_ids: list[str],
    add_label_ids: list[str] = None,
    remove_label_ids: list[str] = None,
    batch_size: int = 100,
    dry_run: bool = False
) -> tuple[int, int]:
    """Apply label modifications in batches. Returns (success_count, fail_count)."""
    if not message_ids:
        return 0, 0

    add_label_ids = add_label_ids or []
    remove_label_ids = remove_label_ids or []

    success_count = 0
    fail_count = 0

    # Process in batches
    for i in range(0, len(message_ids), batch_size):
        batch = message_ids[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (len(message_ids) + batch_size - 1) // batch_size

        if dry_run:
            print(f"  [DRY RUN] Batch {batch_num}/{total_batches}: Would modify {len(batch)} emails")
            success_count += len(batch)
            continue

        try:
            body = {
                "ids": batch,
                "addLabelIds": add_label_ids,
                "removeLabelIds": remove_label_ids
            }

            service.users().messages().batchModify(userId="me", body=body).execute()
            success_count += len(batch)
            print(f"  Batch {batch_num}/{total_batches}: Modified {len(batch)} emails ✓")

        except HttpError as e:
            fail_count += len(batch)
            print(f"  Batch {batch_num}/{total_batches}: Failed - {e}", file=sys.stderr)

    return success_count, fail_count


def main():
    parser = argparse.ArgumentParser(
        description="Bulk label Gmail emails based on search query",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Label all invoices:
    python3 execution/gmail_bulk_label.py --query "subject:invoice" --label "Accounting"

  Archive newsletters:
    python3 execution/gmail_bulk_label.py --query "from:newsletter@" --label "Newsletters" --archive

  Dry run to see what would be affected:
    python3 execution/gmail_bulk_label.py --query "is:unread" --label "Test" --dry-run
        """
    )

    parser.add_argument("--query", "-q", required=True, help="Gmail search query")
    parser.add_argument("--label", "-l", required=True, help="Label name to apply")
    parser.add_argument("--archive", "-a", action="store_true", help="Remove from inbox")
    parser.add_argument("--mark-read", "-r", action="store_true", help="Mark as read")
    parser.add_argument("--dry-run", "-n", action="store_true", help="Show what would be done")
    parser.add_argument("--batch-size", "-b", type=int, default=100, help="Emails per batch")
    parser.add_argument("--account", help="Account name (from gmail_accounts.json)")

    args = parser.parse_args()

    try:
        # Initialize service
        account_label = f" [{args.account}]" if args.account else ""
        print(f"Connecting to Gmail API{account_label}...")
        service = get_gmail_service(args.account)

        # Get or create the target label
        label_id = get_or_create_label(service, args.label)

        # Build label modification lists
        add_labels = [label_id]
        remove_labels = []

        if args.archive:
            remove_labels.append("INBOX")
        if args.mark_read:
            remove_labels.append("UNREAD")

        # Search for all matching messages
        message_ids = search_all_messages(service, args.query)

        if not message_ids:
            print("No emails found matching the query.")
            return 0

        # Apply modifications
        print(f"\nApplying labels...")
        print(f"  Add: {args.label}" + (" + archive" if args.archive else "") + (" + mark read" if args.mark_read else ""))

        success, failed = batch_modify_messages(
            service,
            message_ids,
            add_label_ids=add_labels,
            remove_label_ids=remove_labels,
            batch_size=args.batch_size,
            dry_run=args.dry_run
        )

        # Summary
        print(f"\n{'[DRY RUN] ' if args.dry_run else ''}Summary:")
        print(f"  Successfully modified: {success}")
        if failed:
            print(f"  Failed: {failed}")

        return 0 if failed == 0 else 1

    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
