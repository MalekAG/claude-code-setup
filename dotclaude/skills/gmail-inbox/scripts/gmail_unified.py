#!/usr/bin/env python3
"""
Unified Gmail management across multiple accounts.

Search, label, and modify emails across all registered Gmail accounts.

Usage:
    python3 execution/gmail_unified.py --query "is:unread"
    python3 execution/gmail_unified.py --query "subject:invoice" --label "Accounting" --archive
    python3 execution/gmail_unified.py --query "from:hello@cal.com" --mark-read
    python3 execution/gmail_unified.py --accounts  # list accounts

Options:
    --query      Gmail search query (required for operations)
    --label      Label name to apply (created if doesn't exist)
    --archive    Remove from inbox after labeling
    --mark-read  Mark emails as read
    --dry-run    Show what would be done without making changes
    --account    Only operate on specific account(s), comma-separated
"""

import os
import sys
import argparse
import json
from datetime import datetime
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.labels",
    "https://www.googleapis.com/auth/gmail.send",
]

ACCOUNTS_FILE = "gmail_accounts.json"


def load_accounts() -> dict:
    """Load registered accounts from config file."""
    if os.path.exists(ACCOUNTS_FILE):
        with open(ACCOUNTS_FILE, "r") as f:
            return json.load(f)
    return {}


def get_service(account_name: str, account_info: dict):
    """Get Gmail API service for an account."""
    token_file = account_info.get("token_file")

    if not token_file or not os.path.exists(token_file):
        print(f"  Warning: Token file not found for {account_name}", file=sys.stderr)
        return None

    try:
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                with open(token_file, "w") as f:
                    f.write(creds.to_json())
            else:
                print(f"  Warning: Invalid credentials for {account_name}. Re-run gmail_multi_auth.py", file=sys.stderr)
                return None

        return build("gmail", "v1", credentials=creds)
    except Exception as e:
        print(f"  Warning: Failed to authenticate {account_name}: {e}", file=sys.stderr)
        return None


def get_or_create_label(service, label_name: str) -> str:
    """Get label ID by name, creating it if it doesn't exist."""
    try:
        results = service.users().labels().list(userId="me").execute()
        labels = results.get("labels", [])

        for label in labels:
            if label["name"].lower() == label_name.lower():
                return label["id"]

        # Label doesn't exist, create it
        label_body = {
            "name": label_name,
            "labelListVisibility": "labelShow",
            "messageListVisibility": "show"
        }
        created = service.users().labels().create(userId="me", body=label_body).execute()
        return created["id"]

    except HttpError as e:
        print(f"  Error getting/creating label: {e}", file=sys.stderr)
        return None


def search_messages(service, query: str, max_results: int = None) -> list[dict]:
    """Search for messages matching query, with metadata via batch API.

    Args:
        max_results: If None, returns ALL matching messages. Otherwise caps at this number.
    """
    from googleapiclient.http import BatchHttpRequest

    message_ids = []
    page_token = None

    # First, get all message IDs (fast)
    while True:
        try:
            # Calculate how many more we need
            if max_results:
                remaining = max_results - len(message_ids)
                if remaining <= 0:
                    break
                fetch_count = min(500, remaining)
            else:
                fetch_count = 500

            results = service.users().messages().list(
                userId="me",
                q=query,
                pageToken=page_token,
                maxResults=fetch_count
            ).execute()

            batch = results.get("messages", [])
            if batch:
                message_ids.extend([msg["id"] for msg in batch])

            if max_results and len(message_ids) >= max_results:
                message_ids = message_ids[:max_results]
                break

            page_token = results.get("nextPageToken")
            if not page_token:
                break
        except HttpError as e:
            print(f"  Error searching: {e}", file=sys.stderr)
            break

    if not message_ids:
        return []

    # Now batch fetch metadata (fast - up to 100 per batch request)
    messages = {}

    def callback(request_id, response, exception):
        if exception:
            messages[request_id] = {"id": request_id, "subject": "(error)", "from": "", "date": ""}
        else:
            headers = {h["name"]: h["value"] for h in response.get("payload", {}).get("headers", [])}
            messages[request_id] = {
                "id": response["id"],
                "subject": headers.get("Subject", "(no subject)"),
                "from": headers.get("From", "(unknown)"),
                "date": headers.get("Date", ""),
                "snippet": response.get("snippet", "")[:80]
            }

    # Process in batches of 100 (Gmail API limit)
    for i in range(0, len(message_ids), 100):
        batch = service.new_batch_http_request(callback=callback)
        for msg_id in message_ids[i:i+100]:
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


def batch_modify(service, message_ids: list[str], add_labels: list[str] = None,
                 remove_labels: list[str] = None, batch_size: int = 100) -> tuple[int, int]:
    """Batch modify messages. Returns (success, failed) counts."""
    if not message_ids:
        return 0, 0

    add_labels = add_labels or []
    remove_labels = remove_labels or []
    success = 0
    failed = 0

    for i in range(0, len(message_ids), batch_size):
        batch = message_ids[i:i + batch_size]
        try:
            service.users().messages().batchModify(
                userId="me",
                body={
                    "ids": batch,
                    "addLabelIds": add_labels,
                    "removeLabelIds": remove_labels
                }
            ).execute()
            success += len(batch)
        except HttpError as e:
            failed += len(batch)
            print(f"    Batch failed: {e}", file=sys.stderr)

    return success, failed


def create_message(to: str, subject: str, body: str, from_email: str = None,
                   reply_to_message_id: str = None, thread_id: str = None) -> dict:
    """Create a message for sending."""
    message = MIMEText(body)
    message["to"] = to
    message["subject"] = subject
    if from_email:
        message["from"] = from_email
    if reply_to_message_id:
        message["In-Reply-To"] = reply_to_message_id
        message["References"] = reply_to_message_id

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    msg_body = {"raw": raw}
    if thread_id:
        msg_body["threadId"] = thread_id
    return msg_body


def send_message(service, to: str, subject: str, body: str, from_email: str = None) -> dict:
    """Send a new email."""
    try:
        message = create_message(to, subject, body, from_email)
        result = service.users().messages().send(userId="me", body=message).execute()
        return {"success": True, "id": result.get("id"), "threadId": result.get("threadId")}
    except HttpError as e:
        return {"success": False, "error": str(e)}


def reply_to_message(service, message_id: str, body: str) -> dict:
    """Reply to an existing email, preserving thread."""
    try:
        # Get original message details
        original = service.users().messages().get(
            userId="me", id=message_id, format="metadata",
            metadataHeaders=["Subject", "From", "To", "Message-ID"]
        ).execute()

        headers = {h["name"]: h["value"] for h in original.get("payload", {}).get("headers", [])}
        thread_id = original.get("threadId")
        original_message_id = headers.get("Message-ID", "")
        original_subject = headers.get("Subject", "")
        original_from = headers.get("From", "")

        # Reply subject
        if not original_subject.lower().startswith("re:"):
            subject = f"Re: {original_subject}"
        else:
            subject = original_subject

        # Reply to the sender
        to = original_from

        message = create_message(
            to=to,
            subject=subject,
            body=body,
            reply_to_message_id=original_message_id,
            thread_id=thread_id
        )

        result = service.users().messages().send(userId="me", body=message).execute()

        # Mark original message as read after successful reply
        service.users().messages().modify(
            userId="me",
            id=message_id,
            body={"removeLabelIds": ["UNREAD"]}
        ).execute()

        return {"success": True, "id": result.get("id"), "threadId": result.get("threadId"), "to": to}
    except HttpError as e:
        return {"success": False, "error": str(e)}


def get_message_detail(service, message_id: str) -> dict:
    """Get full message details including body."""
    try:
        msg = service.users().messages().get(userId="me", id=message_id, format="full").execute()
        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}

        # Extract body
        body = ""
        payload = msg.get("payload", {})

        def extract_body(part):
            if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
            for sub in part.get("parts", []):
                result = extract_body(sub)
                if result:
                    return result
            return ""

        body = extract_body(payload)
        if not body and payload.get("body", {}).get("data"):
            body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")

        return {
            "id": message_id,
            "threadId": msg.get("threadId"),
            "subject": headers.get("Subject", "(no subject)"),
            "from": headers.get("From", ""),
            "to": headers.get("To", ""),
            "date": headers.get("Date", ""),
            "body": body,
            "snippet": msg.get("snippet", "")
        }
    except HttpError as e:
        return {"error": str(e)}


def list_accounts_cmd():
    """List all registered accounts."""
    accounts = load_accounts()

    if not accounts:
        print("No accounts registered.")
        print("\nTo add accounts:")
        print("  python3 execution/gmail_multi_auth.py --account yourcompany")
        print("  python3 execution/gmail_multi_auth.py --account youruser")
        return

    print("Registered Gmail accounts:\n")
    for name, info in accounts.items():
        token_exists = os.path.exists(info.get("token_file", ""))
        status = "OK" if token_exists else "TOKEN MISSING"
        print(f"  {name}: {info.get('email', 'unknown')} [{status}]")


def main():
    parser = argparse.ArgumentParser(
        description="Unified Gmail management across multiple accounts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  List unread across all accounts:
    python3 execution/gmail_unified.py --query "is:unread"

  Label invoices in all accounts:
    python3 execution/gmail_unified.py --query "subject:invoice" --label "Accounting" --archive

  Mark calendar notifications as read:
    python3 execution/gmail_unified.py --query "from:hello@cal.com" --mark-read

  Only search one account:
    python3 execution/gmail_unified.py --query "is:unread" --account yourcompany
        """
    )

    parser.add_argument("--query", "-q", help="Gmail search query")
    parser.add_argument("--label", "-l", help="Label name to apply")
    parser.add_argument("--archive", "-a", action="store_true", help="Remove from inbox")
    parser.add_argument("--mark-read", "-r", action="store_true", help="Mark as read")
    parser.add_argument("--dry-run", "-n", action="store_true", help="Show what would be done")
    parser.add_argument("--account", help="Only operate on specific account(s), comma-separated")
    parser.add_argument("--accounts", action="store_true", help="List registered accounts")
    parser.add_argument("--limit", type=int, default=50, help="Max results to display per account")

    args = parser.parse_args()

    if args.accounts:
        list_accounts_cmd()
        return 0

    if not args.query:
        parser.print_help()
        return 1

    # Load accounts
    accounts = load_accounts()
    if not accounts:
        print("No accounts registered. Run gmail_multi_auth.py first.")
        return 1

    # Filter to specific accounts if requested
    if args.account:
        filter_names = [n.strip() for n in args.account.split(",")]
        accounts = {k: v for k, v in accounts.items() if k in filter_names}
        if not accounts:
            print(f"No matching accounts found for: {args.account}")
            return 1

    # Determine if we're just searching or also modifying
    is_modify = args.label or args.archive or args.mark_read

    all_results = []
    total_success = 0
    total_failed = 0

    for account_name, account_info in accounts.items():
        email = account_info.get("email", account_name)
        print(f"\n[{email}]")

        service = get_service(account_name, account_info)
        if not service:
            continue

        # Search - get all for modify operations, limit for display-only
        print(f"  Searching: {args.query}")
        max_fetch = None if is_modify else args.limit
        messages = search_messages(service, args.query, max_results=max_fetch)
        print(f"  Found: {len(messages)} emails")

        if not messages:
            continue

        # Store results with account info
        for msg in messages:
            msg["account"] = account_name
            msg["email"] = email
        all_results.extend(messages)

        # Modify if requested
        if is_modify:
            add_labels = []
            remove_labels = []

            if args.label:
                label_id = get_or_create_label(service, args.label)
                if label_id:
                    add_labels.append(label_id)

            if args.archive:
                remove_labels.append("INBOX")

            if args.mark_read:
                remove_labels.append("UNREAD")

            if args.dry_run:
                print(f"  [DRY RUN] Would modify {len(messages)} emails")
                total_success += len(messages)
            else:
                message_ids = [m["id"] for m in messages]
                success, failed = batch_modify(service, message_ids, add_labels, remove_labels)
                total_success += success
                total_failed += failed
                print(f"  Modified: {success}" + (f" (failed: {failed})" if failed else ""))

    # Summary
    print(f"\n{'='*60}")
    print(f"Total emails found: {len(all_results)}")

    if is_modify:
        prefix = "[DRY RUN] " if args.dry_run else ""
        print(f"{prefix}Successfully modified: {total_success}")
        if total_failed:
            print(f"Failed: {total_failed}")
    else:
        # Display results
        print(f"\nShowing up to {args.limit} most recent:\n")
        # Sort by date (most recent first) - rough sort by string
        all_results.sort(key=lambda x: x.get("date", ""), reverse=True)

        for msg in all_results[:args.limit]:
            account_tag = f"[{msg.get('email', '?')}]"
            from_addr = msg.get("from", "")
            # Truncate from address
            if len(from_addr) > 40:
                from_addr = from_addr[:37] + "..."
            subject = msg.get("subject", "(no subject)")
            if len(subject) > 50:
                subject = subject[:47] + "..."

            print(f"  {account_tag}")
            print(f"    From: {from_addr}")
            print(f"    Subject: {subject}")
            print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
