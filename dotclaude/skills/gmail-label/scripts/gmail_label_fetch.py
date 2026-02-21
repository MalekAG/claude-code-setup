#!/usr/bin/env python3
"""
Fetch Gmail emails and output compact JSON summaries for LLM classification.

Usage:
    python3 .claude/skills/gmail-label/scripts/gmail_label_fetch.py \
        --account youruser_personal --query "in:inbox" --limit 100 --output .tmp/emails.json
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


def fetch_emails(service, query: str, limit: int) -> list[dict]:
    """Fetch emails matching query with metadata via batch API."""
    # Step 1: Get message IDs (paginated)
    message_ids = []
    page_token = None

    while len(message_ids) < limit:
        remaining = limit - len(message_ids)
        try:
            results = service.users().messages().list(
                userId="me",
                q=query,
                pageToken=page_token,
                maxResults=min(500, remaining)
            ).execute()

            batch = results.get("messages", [])
            if batch:
                message_ids.extend([msg["id"] for msg in batch])

            page_token = results.get("nextPageToken")
            if not page_token:
                break
        except HttpError as e:
            print(f"Error searching: {e}", file=sys.stderr)
            break

    message_ids = message_ids[:limit]

    if not message_ids:
        return []

    # Step 2: Batch fetch metadata (100 per batch request)
    messages = {}

    def callback(request_id, response, exception):
        if exception:
            messages[request_id] = {
                "id": request_id,
                "subject": "(error)",
                "from": "",
                "date": "",
                "snippet": ""
            }
        else:
            headers = {h["name"]: h["value"] for h in response.get("payload", {}).get("headers", [])}
            messages[request_id] = {
                "id": response["id"],
                "subject": headers.get("Subject", "(no subject)"),
                "from": headers.get("From", "(unknown)"),
                "date": headers.get("Date", ""),
                "snippet": response.get("snippet", "")[:120]
            }

    for i in range(0, len(message_ids), 100):
        batch = service.new_batch_http_request(callback=callback)
        for msg_id in message_ids[i:i + 100]:
            batch.add(
                service.users().messages().get(
                    userId="me",
                    id=msg_id,
                    format="metadata",
                    metadataHeaders=["Subject", "From", "Date"]
                ),
                request_id=msg_id
            )
        batch.execute()

    # Return in original order
    return [messages[mid] for mid in message_ids if mid in messages]


def main():
    parser = argparse.ArgumentParser(description="Fetch Gmail emails for classification")
    parser.add_argument("--account", "-a", required=True, help="Account name from gmail_accounts.json")
    parser.add_argument("--query", "-q", default="in:inbox", help="Gmail search query (default: in:inbox)")
    parser.add_argument("--limit", "-l", type=int, default=100, help="Max emails to fetch (default: 100)")
    parser.add_argument("--output", "-o", required=True, help="Output JSON file path")
    args = parser.parse_args()

    # Ensure output directory exists
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)

    print(f"Connecting to Gmail API [{args.account}]...")
    service = get_service(args.account)

    print(f"Fetching emails: {args.query} (limit: {args.limit})")
    emails = fetch_emails(service, args.query, args.limit)
    print(f"Fetched {len(emails)} emails")

    with open(args.output, "w") as f:
        json.dump(emails, f, indent=2)

    print(f"Written to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
