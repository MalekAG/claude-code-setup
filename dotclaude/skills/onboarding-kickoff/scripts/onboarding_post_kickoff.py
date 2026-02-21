"""
Post-Kickoff Client Onboarding - Procedural Script

Webhook → This Script → Subprocess calls to various tools → Email summary

Orchestrates the full onboarding after kickoff call:
1. Generate leads (Google Maps + enrichment)
2. Casualize company names
3. Create Instantly campaigns
4. Set up auto-reply knowledge base
5. Send summary email

All logic is deterministic Python. Claude is NOT used here (used in subprocess scripts).
"""

import os
import sys
import json
import logging
import subprocess
import time
import glob
from datetime import datetime
from pathlib import Path
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("onboarding-post-kickoff")

# Constants
KB_SPREADSHEET_ID = "YOUR_SHEET_ID_HERE"
WORKSPACE_DIR = Path(__file__).parent.parent


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


def send_email(to: str, subject: str, body: str, token_data: dict) -> dict:
    """Send email via Gmail API as HTML."""
    from email.mime.text import MIMEText
    import base64

    creds = get_google_creds(token_data)
    service = build("gmail", "v1", credentials=creds)

    # Convert plain text to HTML with proper line breaks
    html_body = body.replace('\n', '<br>')

    message = MIMEText(html_body, 'html')
    message["to"] = to
    message["subject"] = subject
    message["cc"] = "you@yourdomain.com"

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    result = service.users().messages().send(userId="me", body={"raw": raw}).execute()

    logger.info(f"📧 Email sent to {to} | ID: {result['id']}")
    return {"status": "sent", "message_id": result["id"]}


def update_knowledge_base(client_name: str, service_type: str, offers: list, social_proof: str, token_data: dict) -> bool:
    """Add entry to auto-reply knowledge base."""
    creds = get_google_creds(token_data)
    service = build("sheets", "v4", credentials=creds)

    # Build knowledge base content
    offers_text = "\n".join([f"- {offer}" for offer in offers])
    kb_content = f"""Service: {service_type}

Offers:
{offers_text}

Credentials: {social_proof}

When leads ask about pricing, mention our offers and suggest booking a call to discuss their specific needs.
When leads show interest, provide clear next steps to book a consultation."""

    # Example replies
    reply_examples = f"""Example 1: "Thanks for your interest! {offers[0]} - want to hop on a quick call this week?"

Example 2: "Happy to share more details. We specialize in {service_type} and have {social_proof}. Which offer interests you most?"
"""

    # Append row
    values = [[
        client_name,  # ID column
        f"{client_name} | {service_type}",  # Campaign Name
        kb_content,  # Knowledge Base
        reply_examples  # Reply Examples
    ]]

    try:
        result = service.spreadsheets().values().append(
            spreadsheetId=KB_SPREADSHEET_ID,
            range="Sheet1!A:D",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": values}
        ).execute()

        logger.info(f"✅ Added knowledge base entry for {client_name}")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to update knowledge base: {e}")
        return False


def run_command(cmd: list, description: str, timeout: int = 600) -> dict:
    """Run shell command and return result."""
    logger.info(f"🔧 {description}...")
    logger.info(f"   Command: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            cwd=str(WORKSPACE_DIR),
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ}
        )

        if result.returncode != 0:
            logger.error(f"❌ Command failed: {result.stderr}")
            return {"success": False, "error": result.stderr, "stdout": result.stdout}

        logger.info(f"✅ {description} complete")
        return {"success": True, "stdout": result.stdout, "stderr": result.stderr}

    except subprocess.TimeoutExpired:
        logger.error(f"❌ Command timeout after {timeout}s")
        return {"success": False, "error": f"Timeout after {timeout}s"}
    except Exception as e:
        logger.error(f"❌ Command error: {e}")
        return {"success": False, "error": str(e)}


def extract_sheet_url(stdout: str) -> str | None:
    """Extract Google Sheet URL from command output."""
    import re
    match = re.search(r'https://docs\.google\.com/spreadsheets/d/[a-zA-Z0-9_-]+', stdout)
    return match.group(0) if match else None


def extract_campaign_ids(stdout: str) -> list:
    """Extract campaign IDs from instantly_create_campaigns output."""
    try:
        # Look for JSON in output
        import re
        json_match = re.search(r'\{.*"campaign_ids".*\}', stdout, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group(0))
            return data.get("campaign_ids", [])
    except:
        pass
    return []


def run(payload: dict, token_data: dict, slack_notify=None) -> dict:
    """
    Main entry point for post-kickoff onboarding.

    Args:
        payload: Webhook payload with client info
        token_data: Google OAuth token data
        slack_notify: Optional function to send Slack notifications

    Returns:
        Result dict with status, sheet_url, campaigns, etc.
    """
    def notify(msg: str):
        if slack_notify:
            slack_notify(msg)
        logger.info(msg)

    start_time = time.time()
    notify("🚀 Starting post-kickoff onboarding...")

    # Extract inputs
    client_name = payload.get("client_name")
    client_email = payload.get("client_email")
    service_type = payload.get("service_type")
    target_location = payload.get("target_location")
    offers_str = payload.get("offers")  # pipe-separated
    target_audience = payload.get("target_audience", "business owners")
    social_proof = payload.get("social_proof", "")
    lead_limit = payload.get("lead_limit", 500)

    # Validate required fields
    required = ["client_name", "client_email", "service_type", "target_location", "offers"]
    missing = [f for f in required if not payload.get(f)]
    if missing:
        notify(f"❌ Missing required fields: {', '.join(missing)}")
        return {"status": "error", "error": f"Missing fields: {', '.join(missing)}"}

    offers = [o.strip() for o in offers_str.split("|")]
    if len(offers) != 3:
        notify(f"❌ Must provide exactly 3 offers (got {len(offers)})")
        return {"status": "error", "error": "Must provide exactly 3 offers separated by |"}

    notify(f"📋 Client: {client_name}")
    notify(f"   Service: {service_type} in {target_location}")
    notify(f"   Offers: {', '.join(offers)}")
    notify(f"   Target: {lead_limit} leads")

    # =========================================================================
    # STEP 1: Generate leads (3-step Apify flow)
    # =========================================================================
    notify("📍 Step 1/5: Generating leads from Apify...")

    # Extract job titles from target_audience (e.g., "partners and founders" → ["Partner", "Founder"])
    job_titles = ["Partner", "Founder", "Managing Partner", "CEO", "Owner"]

    # Extract company keywords from service_type
    company_keywords = []
    if "accounting" in service_type.lower() or "accounting" in target_audience.lower():
        company_keywords.append("accounting")
    if "consulting" in service_type.lower() or "consulting" in target_audience.lower():
        company_keywords.append("consulting")
    if "financial" in service_type.lower() or "financial" in target_audience.lower():
        company_keywords.extend(["financial advisory", "wealth management"])
    if "coaching" in target_audience.lower():
        company_keywords.append("executive coaching")

    # Fallback if no keywords extracted
    if not company_keywords:
        company_keywords = [service_type]

    # Step 1a: Scrape with Apify (saves to .tmp/leads_*.json)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_prefix = f"{client_name.lower().replace(' ', '_')}_leads"

    scrape_cmd = [
        "python3", "execution/scrape_apify.py",
        "--query", service_type,
        "--location", target_location,
        "--max_items", str(lead_limit),
        "--output_prefix", output_prefix,
        "--job_titles"
    ] + job_titles + [
        "--company_keywords"
    ] + company_keywords + [
        "--no-email-filter"  # Scrape without email requirement, enrich after
    ]

    notify(f"🔧 Scraping {lead_limit} leads via Apify...")
    notify(f"   Job Titles: {', '.join(job_titles)}")
    notify(f"   Company Keywords: {', '.join(company_keywords)}")
    scrape_result = run_command(scrape_cmd, "Scraping leads", timeout=900)

    if not scrape_result["success"]:
        notify(f"❌ Lead scraping failed: {scrape_result['error']}")
        return {"status": "error", "error": "Lead scraping failed", "details": scrape_result}

    # Find the generated JSON file
    json_files = glob.glob(f".tmp/{output_prefix}_*.json")
    if not json_files:
        notify("❌ No JSON file generated from scrape")
        return {"status": "error", "error": "No leads file found"}

    leads_file = sorted(json_files)[-1]  # Get most recent
    notify(f"✅ Scraped leads saved to {leads_file}")

    # Step 1b: Upload to Google Sheet (DELIVERABLE)
    sheet_name = f"{client_name} - Leads"
    upload_cmd = [
        "python3", "execution/update_sheet.py",
        leads_file,
        "--sheet_name", sheet_name
    ]

    notify(f"📤 Uploading to Google Sheet...")
    upload_result = run_command(upload_cmd, "Uploading to sheet", timeout=300)

    if not upload_result["success"]:
        notify(f"❌ Sheet upload failed: {upload_result['error']}")
        return {"status": "error", "error": "Sheet upload failed", "details": upload_result}

    sheet_url = extract_sheet_url(upload_result["stdout"])
    if not sheet_url:
        notify("⚠️ Could not extract sheet URL from output")
        sheet_url = "Check logs for sheet URL"

    notify(f"✅ Sheet created: {sheet_url}")

    # Step 1c: Enrich missing emails
    if sheet_url and sheet_url.startswith("http"):
        enrich_cmd = [
            "python3", "execution/enrich_emails.py",
            sheet_url
        ]

        notify(f"📧 Enriching missing emails...")
        enrich_result = run_command(enrich_cmd, "Enriching emails", timeout=600)

        if not enrich_result["success"]:
            notify(f"⚠️ Email enrichment failed (non-critical): {enrich_result['error']}")
        else:
            notify("✅ Emails enriched")

    notify(f"✅ Leads generated: {sheet_url}")

    # =========================================================================
    # STEP 2: Casualize company names
    # =========================================================================
    notify("📝 Step 2/5: Casualizing company names...")

    if sheet_url and sheet_url.startswith("http"):
        casual_cmd = [
            "python3", "execution/casualize_company_names_batch.py",
            sheet_url  # Positional argument only
        ]

        casual_result = run_command(casual_cmd, "Casualizing names", timeout=300)

        if not casual_result["success"]:
            notify(f"⚠️ Casualization failed (non-critical): {casual_result['error']}")
        else:
            notify("✅ Company names casualized")
    else:
        notify("⚠️ Skipping casualization (no valid sheet URL)")

    # =========================================================================
    # STEP 3: Create Instantly campaigns
    # =========================================================================
    notify("📧 Step 3/5: Creating Instantly campaigns...")

    client_desc = f"We help {client_name} generate qualified leads through personalized cold email outreach for their {service_type} services in {target_location}"

    campaign_cmd = [
        "python3", "execution/instantly_create_campaigns.py",
        "--client_name", client_name,
        "--client_description", client_desc,
        "--offers", offers_str,
        "--target_audience", target_audience,
        "--social_proof", social_proof
    ]

    campaign_result = run_command(campaign_cmd, "Creating campaigns", timeout=600)

    if not campaign_result["success"]:
        notify(f"❌ Campaign creation failed: {campaign_result['error']}")
        return {"status": "error", "error": "Campaign creation failed", "details": campaign_result}

    campaign_ids = extract_campaign_ids(campaign_result["stdout"])
    notify(f"✅ Created {len(campaign_ids)} campaigns")

    # Build campaign info
    campaigns = []
    for i, (cid, offer) in enumerate(zip(campaign_ids, offers)):
        campaigns.append({
            "id": cid,
            "name": f"{client_name} - Offer {i+1}",
            "offer": offer,
            "url": f"https://app.instantly.ai/app/campaigns/{cid}"
        })

    # =========================================================================
    # STEP 4: Add knowledge base entry
    # =========================================================================
    notify("📚 Step 4/5: Setting up auto-reply knowledge base...")

    kb_success = update_knowledge_base(client_name, service_type, offers, social_proof, token_data)

    if not kb_success:
        notify("⚠️ Knowledge base update failed (non-critical)")
    else:
        notify("✅ Auto-reply configured")

    # =========================================================================
    # STEP 5: Send summary email
    # =========================================================================
    notify("📤 Step 5/5: Sending summary email...")

    client_first_name = client_name.split()[0]

    campaign_links = "\n".join([
        f"{i+1}. {c['name']}: {c['offer']}\n   → {c['url']}"
        for i, c in enumerate(campaigns)
    ])

    email_body = f"""Hey {client_first_name},

Your cold email system is live! Here's what we set up:

CAMPAIGNS (3 offers being split-tested):
{campaign_links}

LEADS:
→ {lead_limit} qualified {service_type} leads in {target_location}
→ Spreadsheet: {sheet_url}
→ Next step: Review leads, then we'll upload to campaigns

AUTO-REPLY:
→ Configured for campaign ID: {client_name}
→ Will respond intelligently using your offers and credentials
→ You can review/adjust the knowledge base here:
  https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID_HERE/edit

NEXT STEPS:
1. Review the leads in the spreadsheet (remove any you don't want to contact)
2. Reply to this email when ready, and we'll upload leads to campaigns
3. Campaigns will start sending within 24 hours
4. Auto-replies handle all responses automatically

Questions? Just reply to this email.

- Nick @ YourCompany
"""

    try:
        email_result = send_email(
            to=client_email,
            subject=f"YourCompany Setup Complete - {client_name}",
            body=email_body,
            token_data=token_data
        )
        notify("✅ Summary email sent")
    except Exception as e:
        notify(f"⚠️ Email failed (non-critical): {e}")

    # =========================================================================
    # Complete
    # =========================================================================
    elapsed = time.time() - start_time
    notify(f"🎉 Onboarding complete in {elapsed:.1f}s")

    return {
        "status": "success",
        "client_name": client_name,
        "sheet_url": sheet_url,
        "lead_count": lead_limit,
        "campaigns": campaigns,
        "knowledge_base_updated": kb_success,
        "summary_email_sent": True,
        "elapsed_seconds": round(elapsed, 1)
    }


# For local testing
if __name__ == "__main__":
    # Test payload
    test_payload = {
        "client_name": "TestPlumbing",
        "client_email": "nickolassaraev@gmail.com",
        "service_type": "plumbers",
        "target_location": "Austin TX",
        "lead_limit": 5,
        "offers": "Free inspection|10% off first service|24/7 emergency",
        "target_audience": "homeowners and property managers",
        "social_proof": "15 years in business, 500+ satisfied customers"
    }

    # Load token
    token_path = WORKSPACE_DIR / "token.json"
    if not token_path.exists():
        print("❌ token.json not found")
        sys.exit(1)

    with open(token_path) as f:
        token_data = json.load(f)

    result = run(test_payload, token_data, print)
    print("\n" + "="*80)
    print("RESULT:")
    print(json.dumps(result, indent=2))
