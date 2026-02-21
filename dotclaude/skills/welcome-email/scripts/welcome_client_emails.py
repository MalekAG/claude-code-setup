"""
Welcome Client - Send 3-Email Sequence

Procedural script that sends welcome emails from Nick, Peter, and Sam
when a new client signs their agreement.

No Claude needed - just deterministic email sending.
"""

import os
import json
import logging
import time
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from email.mime.text import MIMEText
import base64

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("welcome-client")


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


def send_email(from_name: str, to: str, subject: str, body: str, token_data: dict) -> dict:
    """Send email via Gmail API as HTML."""
    creds = get_google_creds(token_data)
    service = build("gmail", "v1", credentials=creds)

    # Convert plain text to HTML with proper line breaks
    html_body = body.replace('\n', '<br>')

    message = MIMEText(html_body, 'html')
    message["to"] = to
    message["from"] = f"{from_name} <you@yourdomain.com>"  # All from main account
    message["subject"] = subject

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    result = service.users().messages().send(userId="me", body={"raw": raw}).execute()

    logger.info(f"📧 Email sent from {from_name} to {to} | ID: {result['id']}")
    return {"status": "sent", "message_id": result["id"], "from": from_name}


def run(payload: dict, token_data: dict, slack_notify=None) -> dict:
    """
    Send 3-email welcome sequence.

    Args:
        payload: Webhook payload with client info
        token_data: Google OAuth token data
        slack_notify: Optional function to send Slack notifications

    Returns:
        Result dict with email statuses
    """
    def notify(msg: str):
        if slack_notify:
            slack_notify(msg)
        logger.info(msg)

    notify("📬 Starting welcome email sequence...")

    # Extract inputs
    client_first_name = payload.get("client_name", "").split()[0]  # Get first name
    client_email = payload.get("client_email")
    company_name = payload.get("company_name", client_first_name)

    # Validate
    if not client_email:
        notify("❌ Missing client_email")
        return {"status": "error", "error": "Missing client_email"}

    if not client_first_name:
        notify("❌ Missing client_name")
        return {"status": "error", "error": "Missing client_name"}

    notify(f"👤 Client: {client_first_name} ({company_name})")
    notify(f"📧 Sending to: {client_email}")

    emails_sent = []

    # =========================================================================
    # EMAIL 1: Nick's Welcome
    # =========================================================================
    notify("📤 Sending email 1/3 (Nick)...")

    nick_subject = f"Welcome to YourCompany, {client_first_name}!"
    nick_body = f"""Hey {client_first_name},

Just saw the agreement go through and had to rush over and formally welcome you.

I (and the rest of the YourCompany team) are extremely excited to have you/{company_name}. Thanks for filling out your agreement so promptly.

Over the course of the next 30 minutes, you'll receive:
- a couple of welcomes from the people we'll be working with (I sent everyone a message in our Slack),
- a PDF onboarding kit with information about how we work, client comms, etc,
- a link to our onboarding calendar so you can book a call (ideally some time in the next couple of days!)

I want you to know: I'm already getting things up and running for you. By the time we make it onto the call, we'll have produced a variety of assets that will make it easier for us to proceed.

Stay tuned for more on this—once again, appreciate you coming on board.

Thanks,
Nick"""

    try:
        result1 = send_email("Nick", client_email, nick_subject, nick_body, token_data)
        emails_sent.append(result1)
        notify("✅ Email 1/3 sent (Nick)")
    except Exception as e:
        notify(f"❌ Email 1 failed: {e}")
        return {"status": "error", "error": f"Nick's email failed: {e}"}

    # Wait 15 seconds between emails (demo mode)
    notify("⏳ Waiting 15 seconds before next email...")
    time.sleep(15)

    # =========================================================================
    # EMAIL 2: Peter's Welcome
    # =========================================================================
    notify("📤 Sending email 2/3 (Peter)...")

    peter_subject = f"Welcome from Peter"
    peter_body = f"""Hi {client_first_name},

Nick ran me through {company_name} on our last call. So great to formally have you!

Looking forward to connecting.

Thanks,
Peter"""

    try:
        result2 = send_email("Peter", client_email, peter_subject, peter_body, token_data)
        emails_sent.append(result2)
        notify("✅ Email 2/3 sent (Peter)")
    except Exception as e:
        notify(f"❌ Email 2 failed: {e}")
        # Continue anyway - non-critical

    # Wait 15 seconds before final email (demo mode)
    notify("⏳ Waiting 15 seconds before final email...")
    time.sleep(15)

    # =========================================================================
    # EMAIL 3: Sam's Booking Request
    # =========================================================================
    notify("📤 Sending email 3/3 (Sam)...")

    sam_subject = f"Book Your Kickoff Call - {company_name}"
    sam_body = f"""Hi {client_first_name},

I'm Sam—I do bookings at YourCompany.

Would you mind booking in your kickoff call here? I'll coordinate the time with our team and make sure we're all available to formally commence your project.

https://cal.com/YourCompany/Client-Onboarding

Thank you,
Sam"""

    try:
        result3 = send_email("Sam", client_email, sam_subject, sam_body, token_data)
        emails_sent.append(result3)
        notify("✅ Email 3/3 sent (Sam)")
    except Exception as e:
        notify(f"❌ Email 3 failed: {e}")
        # Continue anyway - non-critical

    # =========================================================================
    # Complete
    # =========================================================================
    notify(f"🎉 Welcome sequence complete - {len(emails_sent)}/3 emails sent")

    return {
        "status": "success",
        "emails_sent": len(emails_sent),
        "client_name": client_first_name,
        "client_email": client_email,
        "company_name": company_name,
        "results": emails_sent
    }


# For local testing
if __name__ == "__main__":
    import sys
    from pathlib import Path

    # Test payload
    test_payload = {
        "client_name": "John Smith",
        "client_email": "nickolassaraev@gmail.com",
        "company_name": "Acme Corp"
    }

    # Load token
    token_path = Path(__file__).parent.parent / "token.json"
    if not token_path.exists():
        print("❌ token.json not found")
        sys.exit(1)

    with open(token_path) as f:
        token_data = json.load(f)

    result = run(test_payload, token_data, print)
    print("\n" + "="*80)
    print("RESULT:")
    print(json.dumps(result, indent=2))
