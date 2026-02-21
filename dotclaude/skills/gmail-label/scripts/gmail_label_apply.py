#!/usr/bin/env python3
"""
Apply label classifications to Gmail emails in bulk.

Reads a JSON file mapping label names to lists of message IDs,
creates labels if needed, and applies them via batch API.

Usage:
    python3 .claude/skills/gmail-label/scripts/gmail_label_apply.py \
        --account youruser_personal --input .tmp/labels.json

Input format (.tmp/labels.json):
{
  "Action Required": ["msg_id_1", "msg_id_2"],
  "Waiting On": ["msg_id_3"],
  "Reference": ["msg_id_4", "msg_id_5"]
}
"""

import os
import sys
import json
import argparse
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.labels",
]
ACCOUNTS_FILE = "gmail_accounts.json"


def load_accounts() -> dict:
    if os.path.exists(ACCOUNTS_FILE):
        with open(ACCOUNTS_FILE, "r") as f:
            return json.load(f)
    return {}


def get_service(account: str):
    accounts = load_accounts()
    if account not in accounts:
        print(f"Error: Account '{account}' not found. Available: {list(accounts.keys())}", file=sys.stderr)
        sys.exit(1)

    token_file = accounts[account].get("token_file")
    if not token_file or not os.path.exists(token_file):
        print(f"Error: Token file '{token_file}' not found for {account}. Run gmail_multi_auth.py first.", file=sys.stderr)
        sys.exit(1)

    creds = Credentials.from_authorized_user_file(token_file, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(token_file, "w") as f:
                f.write(creds.to_json())
        else:
            print(f"Error: Invalid credentials for {account}. Re-run gmail_multi_auth.py.", file=sys.stderr)
            sys.exit(1)

    return build("gmail", "v1", credentials=creds)


def get_or_create_label(service, label_name: str) -> str:
    """Get label ID by name, creating it if it doesn't exist."""
    try:
        results = service.users().labels().list(userId="me").execute()
        labels = results.get("labels", [])

        for label in labels:
            if label["name"].lower() == label_name.lower():
                print(f"  Found label: {label_name} (ID: {label['id']})")
                return label["id"]

        # Create it
        label_body = {
            "name": label_name,
            "labelListVisibility": "labelShow",
            "messageListVisibility": "show"
        }
        created = service.users().labels().create(userId="me", body=label_body).execute()
        print(f"  Created label: {label_name} (ID: {created['id']})")
        return created["id"]

    except HttpError as e:
        print(f"  Error with label '{label_name}': {e}", file=sys.stderr)
        return None


def validate_ids(message_ids: list[str]) -> tuple[list[str], list[str]]:
    """Filter out malformed message IDs. Valid Gmail IDs are variable-length hex strings."""
    valid = []
    invalid = []
    for mid in message_ids:
        if mid and all(c in '0123456789abcdefABCDEF' for c in mid):
            valid.append(mid)
        else:
            invalid.append(mid)
    return valid, invalid


def batch_apply_label(service, message_ids: list[str], label_id: str, batch_size: int = 100) -> tuple[int, int]:
    """Apply a label to messages in batches. Returns (success, failed)."""
    message_ids, invalid = validate_ids(message_ids)
    if invalid:
        print(f"    Skipped {len(invalid)} malformed IDs: {invalid[:5]}")

    success = 0
    failed = 0

    for i in range(0, len(message_ids), batch_size):
        batch = message_ids[i:i + batch_size]
        try:
            service.users().messages().batchModify(
                userId="me",
                body={
                    "ids": batch,
                    "addLabelIds": [label_id],
                }
            ).execute()
            success += len(batch)
        except HttpError as e:
            failed += len(batch)
            print(f"    Batch failed: {e}", file=sys.stderr)

    return success, failed


def main():
    parser = argparse.ArgumentParser(description="Apply label classifications to Gmail emails")
    parser.add_argument("--account", "-a", required=True, help="Account name from gmail_accounts.json")
    parser.add_argument("--input", "-i", required=True, help="Input JSON file with label -> message_ids mapping")
    parser.add_argument("--dry-run", "-n", action="store_true", help="Show what would be done")
    args = parser.parse_args()

    # Load classification
    with open(args.input, "r") as f:
        classifications = json.load(f)

    total_emails = sum(len(ids) for ids in classifications.values())
    print(f"Classification summary:")
    for label_name, ids in classifications.items():
        print(f"  {label_name}: {len(ids)} emails")
    print(f"  Total: {total_emails} emails")

    if args.dry_run:
        print("\n[DRY RUN] No changes made.")
        return 0

    print(f"\nConnecting to Gmail API [{args.account}]...")
    service = get_service(args.account)

    total_success = 0
    total_failed = 0

    for label_name, message_ids in classifications.items():
        if not message_ids:
            continue

        print(f"\nApplying '{label_name}' to {len(message_ids)} emails...")
        label_id = get_or_create_label(service, label_name)

        if not label_id:
            total_failed += len(message_ids)
            continue

        success, failed = batch_apply_label(service, message_ids, label_id)
        total_success += success
        total_failed += failed
        print(f"  Done: {success} labeled" + (f", {failed} failed" if failed else ""))

    print(f"\nSummary: {total_success} labeled, {total_failed} failed")
    return 0 if total_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
