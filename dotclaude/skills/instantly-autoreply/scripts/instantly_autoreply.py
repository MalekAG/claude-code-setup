"""
Instantly Autoreply - Procedural Script (v2)

Webhook → This Script → Claude (only for reply generation) → Instantly API

All logic is deterministic Python. Claude is only invoked for the creative task
of writing the actual reply.
"""

import os
import json
import logging
import requests
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
import anthropic

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("instantly-autoreply")

# Constants
KB_SPREADSHEET_ID = "YOUR_SHEET_ID_HERE"


def get_google_creds(token_data: dict) -> Credentials:
    """Get Google credentials from token data."""
    creds = Credentials(
        token=token_data["token"],
        refresh_token=token_data["refresh_token"],
        token_uri=token_data["token_uri"],
        client_id=token_data["client_id"],
        client_secret=token_data["client_secret"],
        scopes=token_data["scopes"]
    )
    if creds.expired:
        creds.refresh(Request())
    return creds


def lookup_knowledge_base(campaign_id: str, token_data: dict) -> dict | None:
    """
    Look up knowledge base for a campaign ID.
    Returns {"knowledge_base": str, "reply_examples": str} or None if not found.
    """
    creds = get_google_creds(token_data)
    service = build("sheets", "v4", credentials=creds)

    result = service.spreadsheets().values().get(
        spreadsheetId=KB_SPREADSHEET_ID,
        range="Sheet1!A:D"
    ).execute()

    rows = result.get("values", [])
    if len(rows) < 2:
        return None

    # Find header indices
    headers = [h.lower() for h in rows[0]]
    id_idx = headers.index("id") if "id" in headers else 0
    kb_idx = headers.index("knowledge base") if "knowledge base" in headers else 2
    examples_idx = headers.index("reply examples") if "reply examples" in headers else 3

    # Search for matching campaign ID
    for row in rows[1:]:
        if len(row) > id_idx and row[id_idx] == campaign_id:
            kb = row[kb_idx] if len(row) > kb_idx else ""
            examples = row[examples_idx] if len(row) > examples_idx else ""
            if kb:  # Only return if there's actual content
                return {"knowledge_base": kb, "reply_examples": examples}

    return None


def get_conversation_history(lead_email: str, limit: int = 10) -> list:
    """Get email conversation history from Instantly."""
    api_key = os.getenv("INSTANTLY_API_KEY")
    if not api_key:
        logger.warning("INSTANTLY_API_KEY not configured")
        return []

    url = "https://api.instantly.ai/api/v2/emails"
    headers = {"Authorization": f"Bearer {api_key}"}
    params = {"limit": limit, "search": lead_email}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        if response.status_code != 200:
            logger.error(f"Instantly API error: {response.status_code}")
            return []

        data = response.json()
        return data.get("items", [])
    except Exception as e:
        logger.error(f"Failed to get conversation history: {e}")
        return []


def generate_reply(
    payload: dict,
    knowledge_base: dict,
    conversation_history: list
) -> str | None:
    """
    Use Claude to generate the reply. This is the ONLY place Claude is invoked.
    Returns HTML reply string, or None if no reply should be sent.
    """
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    # Build context for Claude
    kb_text = knowledge_base.get("knowledge_base", "")
    examples = knowledge_base.get("reply_examples", "")

    incoming_email = payload.get("reply_text") or payload.get("reply_html", "")
    sender_email = payload.get("lead_email", "")
    email_account = payload.get("email_account", "")

    # Format conversation history
    history_text = ""
    if conversation_history:
        for email in conversation_history[:5]:  # Last 5 emails
            from_addr = email.get("from_address_email", "")
            body = email.get("body", {}).get("text", "")[:500]
            history_text += f"\n---\nFrom: {from_addr}\n{body}\n"

    prompt = f"""Write a sales email reply.

FROM: {sender_email}
MESSAGE: {incoming_email}

CONTEXT (your company/offering):
{kb_text}

TONE EXAMPLES:
{examples}

RULES:
- Reply as {email_account} (use first name to sign off)
- Be concise (3-8 sentences), confident, friendly
- No em dashes, no hype, no filler
- Answer their questions directly using the context above
- If they asked about pricing, ROI, process - give specifics from the context

OUTPUT: Just the email body in HTML (<br> for line breaks). No tags like <html> or <body>.

ONLY return the single word SKIP if:
- They said "unsubscribe" or "remove me"
- The conversation is clearly finished (call booked, deal closed)

Otherwise, write the reply now:"""

    try:
        response = client.messages.create(
            model="claude-opus-4-5-20251101",
            max_tokens=16000,
            thinking={
                "type": "enabled",
                "budget_tokens": 10000
            },
            messages=[{"role": "user", "content": prompt}]
        )

        # Extract text from response
        reply_text = ""
        for block in response.content:
            if hasattr(block, "text"):
                reply_text = block.text
                break

        logger.info(f"Claude raw response: {reply_text[:500] if reply_text else 'EMPTY'}")

        # Check if we should skip - be more lenient with matching
        cleaned = reply_text.strip()
        if cleaned.upper() == "SKIP" or cleaned.upper().startswith("SKIP"):
            logger.info("Claude decided to SKIP")
            return None

        # Also skip if empty
        if not cleaned:
            logger.info("Claude returned empty response")
            return None

        return cleaned

    except Exception as e:
        logger.error(f"Claude API error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        # Return error message instead of None so we can debug
        return f"ERROR: {str(e)}"


def send_reply(payload: dict, html_body: str) -> dict:
    """Send the reply via Instantly API."""
    api_key = os.getenv("INSTANTLY_API_KEY")
    if not api_key:
        return {"error": "INSTANTLY_API_KEY not configured"}

    url = "https://api.instantly.ai/api/v2/emails/reply"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    request_payload = {
        "eaccount": payload.get("email_account"),
        "reply_to_uuid": payload.get("email_id"),
        "subject": payload.get("reply_subject"),
        "body": {"html": html_body}
    }

    try:
        response = requests.post(url, headers=headers, json=request_payload, timeout=30)

        if response.status_code not in [200, 201]:
            logger.error(f"Instantly reply error: {response.status_code} - {response.text}")
            return {"error": f"Instantly API error: {response.status_code}", "details": response.text}

        logger.info(f"Reply sent to {payload.get('lead_email')}")
        return {"status": "sent", "reply_to_uuid": payload.get("email_id")}

    except Exception as e:
        logger.error(f"Failed to send reply: {e}")
        return {"error": str(e)}


def run(payload: dict, token_data: dict, slack_notify=None) -> dict:
    """
    Main entry point. Executes the full procedural flow.

    Args:
        payload: Webhook payload from Instantly
        token_data: Google OAuth token data
        slack_notify: Optional function to send Slack notifications

    Returns:
        Result dict with status, skipped, reply_sent, etc.
    """
    def notify(msg: str):
        if slack_notify:
            slack_notify(msg)
        logger.info(msg)

    # Debug: verify setup
    notify(f"📦 API key present: {bool(os.getenv('ANTHROPIC_API_KEY'))}")

    # Step 1: Extract campaign ID
    campaign_id = payload.get("campaign_id")
    if not campaign_id:
        # Try parsing from campaign_name
        campaign_name = payload.get("campaign_name", "")
        if "|" in campaign_name:
            campaign_id = campaign_name.split("|")[0].strip()
        else:
            campaign_id = campaign_name.strip()

    if not campaign_id:
        notify("⚠️ No campaign ID found, skipping")
        return {"status": "success", "skipped": True, "reason": "no_campaign_id"}

    notify(f"📧 Processing reply from {payload.get('lead_email')} (campaign: {campaign_id})")

    # Step 2: Lookup knowledge base
    kb = lookup_knowledge_base(campaign_id, token_data)
    if not kb:
        notify(f"⚠️ No knowledge base for campaign {campaign_id}, skipping")
        return {"status": "success", "skipped": True, "reason": "no_knowledge_base"}

    notify(f"📚 Found knowledge base ({len(kb.get('knowledge_base', ''))} chars)")

    # Step 3: Get conversation history (optional, for context)
    history = get_conversation_history(payload.get("lead_email", ""))
    notify(f"💬 Retrieved {len(history)} prior emails")

    # Step 4: Generate reply (THIS IS WHERE CLAUDE IS CALLED)
    notify("🤖 Generating reply with Claude...")
    reply = generate_reply(payload, kb, history)

    if not reply:
        notify("⏭️ Claude decided to skip (no reply needed)")
        return {"status": "success", "skipped": True, "reason": "claude_skip", "debug": "reply was None or empty"}

    notify(f"✍️ Generated reply ({len(reply)} chars): {reply[:200]}...")

    # Check for test/dry-run mode
    email_id = payload.get("email_id", "")
    is_test = payload.get("dry_run") or email_id.startswith("test-")
    notify(f"📋 email_id={email_id}, is_test={is_test}")

    if is_test:
        notify("🧪 DRY RUN - not sending reply")
        return {
            "status": "success",
            "skipped": False,
            "reply_sent": False,
            "dry_run": True,
            "reply_preview": reply[:500] if len(reply) > 500 else reply,
            "reply_length": len(reply)
        }

    # Step 5: Send reply
    result = send_reply(payload, reply)

    if "error" in result:
        notify(f"❌ Failed to send: {result['error']}")
        return {"status": "error", "error": result["error"]}

    notify(f"✅ Reply sent successfully")
    return {
        "status": "success",
        "skipped": False,
        "reply_sent": True,
        "reply_length": len(reply)
    }


# For local testing
if __name__ == "__main__":
    import sys

    # Test with sample payload
    test_payload = {
        "campaign_id": "YourCompany",
        "lead_email": "test@example.com",
        "email_account": "outreach@yourdomain.com",
        "email_id": "test-uuid",
        "reply_subject": "Re: Test",
        "reply_text": "This sounds interesting, tell me more about pricing."
    }

    # Load token from file
    with open("../token.json") as f:
        token_data = json.load(f)

    result = run(test_payload, token_data, print)
    print(json.dumps(result, indent=2))
