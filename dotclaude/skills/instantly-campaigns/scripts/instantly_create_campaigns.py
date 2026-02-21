"""
Instantly Campaign Creator

Creates 3 email campaigns in Instantly based on client description and offers.
Each campaign:
- Targets a different offer
- Has 2-3 email steps
- First step has 2 variants (A/B split test)

Usage:
    python3 execution/instantly_create_campaigns.py \
        --client_name "ClientName" \
        --client_description "Description..." \
        --offers "Offer1|Offer2|Offer3" \
        --target_audience "Who we're targeting" \
        --social_proof "Credentials to mention"
"""

import os
import sys
import json
import argparse
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests
import anthropic
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("instantly-campaigns")

# Constants
INSTANTLY_API_BASE = "https://api.instantly.ai/api/v2"
EXAMPLES_PATH = Path(__file__).parent.parent / ".tmp" / "instantly_campaign_examples" / "campaigns.md"


def load_examples() -> str:
    """Load campaign examples for inspiration."""
    if EXAMPLES_PATH.exists():
        return EXAMPLES_PATH.read_text()
    logger.warning(f"Examples file not found at {EXAMPLES_PATH}")
    return ""


def generate_campaigns_with_claude(
    client_name: str,
    client_description: str,
    offers: list[str],
    target_audience: str,
    social_proof: str,
    examples: str
) -> list[dict]:
    """
    Use Claude to generate 3 campaigns with email sequences.
    Returns list of campaign structures ready for Instantly API.
    """
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    offers_text = "\n".join(f"{i+1}. {offer}" for i, offer in enumerate(offers))

    prompt = f"""Generate 3 email campaigns for cold outreach. Each campaign targets a DIFFERENT offer.

CLIENT INFO:
- Name: {client_name}
- Description: {client_description}
- Target Audience: {target_audience}
- Social Proof: {social_proof}

OFFERS (one per campaign):
{offers_text}

EXAMPLE EMAILS FOR INSPIRATION (study the tone, structure, and personalization):
{examples[:8000]}

REQUIREMENTS:
1. Each campaign has 3 email steps
2. Step 1 has TWO variants (A/B test) - both should be meaningfully different in approach
3. Steps 2-3 have one variant each (follow-ups)
4. Use these variables: {{{{firstName}}}}, {{{{icebreaker}}}}, {{{{sendingAccountFirstName}}}}, {{{{companyName}}}}
5. Structure: personalization hook → social proof → offer → soft CTA
6. Tone: conversational, confident, zero fluff, no em dashes
7. Subject lines: short, lowercase preferred, personal feel
8. Body: 5-10 sentences max, line breaks between paragraphs

OUTPUT FORMAT (valid JSON array):
[
  {{
    "campaign_name": "ClientName | Offer 1 - Brief Description",
    "sequences": [
      {{
        "steps": [
          {{
            "type": "email",
            "delay": 0,
            "variants": [
              {{"subject": "subject line A", "body": "Email body A..."}},
              {{"subject": "subject line B", "body": "Email body B..."}}
            ]
          }},
          {{
            "type": "email",
            "delay": 3,
            "variants": [
              {{"subject": "Re: quick follow up", "body": "Follow up body..."}}
            ]
          }},
          {{
            "type": "email",
            "delay": 4,
            "variants": [
              {{"subject": "Re: closing the loop", "body": "Breakup email..."}}
            ]
          }}
        ]
      }}
    ]
  }},
  ... (2 more campaigns)
]

Generate the 3 campaigns now. Output ONLY the JSON array, no other text."""

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

        # Extract text content
        result_text = ""
        for block in response.content:
            if hasattr(block, "text"):
                result_text = block.text
                break

        # Parse JSON from response
        # Handle case where Claude might wrap in ```json
        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split("```")[0]
        elif "```" in result_text:
            result_text = result_text.split("```")[1].split("```")[0]

        campaigns = json.loads(result_text.strip())

        # Convert plain text to HTML paragraphs (Instantly strips text outside HTML tags)
        for campaign in campaigns:
            for sequence in campaign.get("sequences", []):
                for step in sequence.get("steps", []):
                    for variant in step.get("variants", []):
                        if "body" in variant:
                            body = variant["body"]
                            # Split by double newlines (paragraphs) and single newlines
                            paragraphs = body.split("\n\n")
                            html_parts = []
                            for p in paragraphs:
                                # Replace single newlines with <br> within paragraphs
                                p = p.replace("\n", "<br>")
                                if p.strip():
                                    html_parts.append(f"<p>{p}</p>")
                            variant["body"] = "".join(html_parts)

        logger.info(f"Generated {len(campaigns)} campaigns")
        return campaigns

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Claude response as JSON: {e}")
        logger.error(f"Response was: {result_text[:1000]}")
        raise
    except Exception as e:
        logger.error(f"Claude API error: {e}")
        raise


def create_campaign_in_instantly(campaign_data: dict) -> dict:
    """
    Create a single campaign in Instantly via API.
    Returns the created campaign data or error.
    """
    api_key = os.getenv("INSTANTLY_API_KEY")
    if not api_key:
        return {"error": "INSTANTLY_API_KEY not configured in .env"}

    url = f"{INSTANTLY_API_BASE}/campaigns"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # Set default campaign settings
    start_date = datetime.now().strftime("%Y-%m-%d")
    end_date = (datetime.now() + timedelta(days=365)).strftime("%Y-%m-%d")

    payload = {
        "name": campaign_data["campaign_name"],
        "sequences": campaign_data["sequences"],
        "campaign_schedule": {
            "start_date": start_date,
            "end_date": end_date,
            "schedules": [
                {
                    "name": "Weekday Schedule",
                    "days": {"1": True, "2": True, "3": True, "4": True, "5": True},
                    "timing": {"from": "09:00", "to": "17:00"},
                    "timezone": "America/Chicago"
                }
            ]
        },
        "email_gap": 10,
        "daily_limit": 50,
        "stop_on_reply": True,
        "stop_on_auto_reply": True,
        "link_tracking": True,
        "open_tracking": True,
        "text_only": False
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)

        if response.status_code == 429:
            # Rate limited - wait and retry once
            logger.warning("Rate limited, waiting 30 seconds...")
            time.sleep(30)
            response = requests.post(url, headers=headers, json=payload, timeout=60)

        if response.status_code not in [200, 201]:
            logger.error(f"Instantly API error: {response.status_code} - {response.text}")
            return {"error": f"API error {response.status_code}", "details": response.text}

        result = response.json()
        logger.info(f"Created campaign: {campaign_data['campaign_name']} (ID: {result.get('id', 'unknown')})")
        return result

    except requests.exceptions.Timeout:
        return {"error": "Request timeout"}
    except Exception as e:
        logger.error(f"Failed to create campaign: {e}")
        return {"error": str(e)}


def generate_offers_if_missing(client_name: str, client_description: str) -> list[str]:
    """Generate 3 offers if none provided."""
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    prompt = f"""Generate 3 distinct cold email offers for this business:

Business: {client_name}
Description: {client_description}

Each offer should be:
1. Low barrier to entry (free audit, demo, quick call)
2. High perceived value
3. Different from the others (variety of angles)

Output format (one offer per line, no numbering):
Free workflow audit to find automation opportunities
Live demo of our AI system
Revenue share partnership pilot

Generate 3 offers now:"""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )

        text = response.content[0].text.strip()
        offers = [line.strip() for line in text.split("\n") if line.strip()]
        return offers[:3]

    except Exception as e:
        logger.error(f"Failed to generate offers: {e}")
        # Return generic fallback offers
        return [
            "Free strategy call to discuss your goals",
            "Custom demo of our solution",
            "Pilot program with performance guarantee"
        ]


def main():
    parser = argparse.ArgumentParser(description="Create Instantly email campaigns")
    parser.add_argument("--client_name", required=True, help="Client/company name")
    parser.add_argument("--client_description", required=True, help="Description of the client and their offering")
    parser.add_argument("--offers", help="Pipe-separated offers (e.g., 'Offer 1|Offer 2|Offer 3')")
    parser.add_argument("--target_audience", default="Business owners and decision makers", help="Target audience description")
    parser.add_argument("--social_proof", default="", help="Credentials and social proof to include")
    parser.add_argument("--dry_run", action="store_true", help="Generate campaigns without creating in Instantly")

    args = parser.parse_args()

    # Check for API key early (unless dry run)
    api_key = os.getenv("INSTANTLY_API_KEY", "")
    if not args.dry_run and (not api_key or api_key.startswith("your_")):
        print(json.dumps({
            "status": "error",
            "error": "INSTANTLY_API_KEY not configured in .env",
            "help": "Add your Instantly API v2 key to .env file. Get it from https://app.instantly.ai/app/settings/integrations"
        }, indent=2))
        sys.exit(1)

    # Parse or generate offers
    if args.offers:
        offers = [o.strip() for o in args.offers.split("|")]
    else:
        logger.info("No offers provided, generating...")
        offers = generate_offers_if_missing(args.client_name, args.client_description)

    # Ensure we have exactly 3 offers
    while len(offers) < 3:
        offers.append(f"Custom solution discussion {len(offers) + 1}")
    offers = offers[:3]

    logger.info(f"Using offers: {offers}")

    # Load examples
    examples = load_examples()
    if examples:
        logger.info(f"Loaded {len(examples)} chars of example content")

    # Generate campaigns
    logger.info("Generating campaigns with Claude...")
    campaigns = generate_campaigns_with_claude(
        client_name=args.client_name,
        client_description=args.client_description,
        offers=offers,
        target_audience=args.target_audience,
        social_proof=args.social_proof,
        examples=examples
    )

    if args.dry_run:
        print(json.dumps({
            "status": "dry_run",
            "campaigns_generated": len(campaigns),
            "campaigns": campaigns
        }, indent=2))
        return

    # Create campaigns in Instantly
    results = []
    campaign_ids = []
    campaign_names = []
    errors = []

    for campaign in campaigns:
        result = create_campaign_in_instantly(campaign)
        results.append(result)

        if "error" in result:
            errors.append(result)
        else:
            campaign_ids.append(result.get("id", "unknown"))
            campaign_names.append(campaign["campaign_name"])

        # Small delay between API calls
        time.sleep(2)

    # Output results
    output = {
        "status": "success" if not errors else "partial_success" if campaign_ids else "failed",
        "campaigns_created": len(campaign_ids),
        "campaign_ids": campaign_ids,
        "campaign_names": campaign_names
    }

    if errors:
        output["errors"] = errors

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
