#!/usr/bin/env python3
"""
Cross-Niche Outlier Detection using TubeLab API.

TubeLab already calculates outlier ratios (averageViewsRatio), so we skip the
expensive yt-dlp scraping and channel average calculations.

Key differences from yt-dlp version:
- Uses TubeLab API (5 credits per query, 10 req/min limit)
- Pre-calculated outlier scores (averageViewsRatio)
- More reliable than yt-dlp (no rate limiting issues)
- Still applies our cross-niche filtering and title variant generation

Usage:
    # Default: 3 queries, ~60 outliers before filtering
    python execution/scrape_cross_niche_tubelab.py

    # Single query test (cheapest, 5 credits)
    python execution/scrape_cross_niche_tubelab.py --queries 1

    # More coverage (15 credits)
    python execution/scrape_cross_niche_tubelab.py --queries 3

    # Custom search terms
    python execution/scrape_cross_niche_tubelab.py --terms "business growth" "entrepreneur" "productivity"
"""

import os
import sys
import json
import time
import datetime
import argparse
import re
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from anthropic import Anthropic
import gspread
from google.oauth2.credentials import Credentials
from google.oauth2.service_account import Credentials as ServiceAccountCredentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

load_dotenv()

# TubeLab API
TUBELAB_BASE_URL = "https://public-api.tubelab.net/v1"
TUBELAB_API_KEY = os.getenv("TUBELAB_API_KEY")

# Default search term (broad to maximize results)
DEFAULT_SEARCH_TERMS = [
    "entrepreneur",
]

# =============================================================================
# EXCLUSION FILTERS (same as yt-dlp version)
# =============================================================================

# OWN NICHE - Hard exclude (we want CROSS-niche, not our niche)
OWN_NICHE_TERMS = [
    # AI/ML Core
    "ai", "a.i.", "a.i", " ai ", "artificial intelligence",
    "gpt", "chatgpt", "chat gpt", "claude", "llm", "gemini",
    "machine learning", "neural network", "deep learning", "openai", "anthropic",
    "midjourney", "stable diffusion", "dall-e", "copilot",
    # Automation Tools
    "automation", "automate", "automated", "n8n", "make.com", "zapier", "workflow",
    "integromat", "power automate", "ifttt", "airtable automation",
    # Agents/Frameworks
    "agent", "agentic", "langchain", "langgraph", "crewai", "autogen", "autogpt",
    "babyagi", "superagi", "agent gpt", "ai agent",
    # Code/Dev
    "code", "coding", "programming", "programmer", "developer", "python", "javascript",
    "typescript", "api", "sdk", "github", "open source", "repository", "deploy",
    "docker", "kubernetes", "aws", "serverless", "backend", "frontend", "full stack",
    # Tech Tools
    "cursor", "replit", "vs code", "vscode", "terminal", "command line", "cli",
    "notion ai", "obsidian", "roam research",
]

# NON-TRANSFERABLE FORMATS - Heavy penalty
EXCLUDE_FORMATS = [
    # Gear/Tech Reviews
    "setup", "desk setup", "tour", "room tour", "office tour", "studio tour",
    "carry", "every day carry", "edc", "what's in my bag",
    "buying guide", "review", "unboxing", "hands on", "first look",
    "best laptop", "best phone", "best camera", "best mic", "best keyboard",
    "vs", "comparison", "compared", "which is better", "versus",
    "upgrade", "upgraded my", "new setup",
    # Entertainment/Challenges
    "challenge", "challenged", "survive", "survived", "surviving",
    "win $", "won $", "winning", "prize", "giveaway",
    "battle", "competition", "race", "contest",
    "prank", "pranked", "pranking",
    "react", "reacts", "reacting", "reaction",
    "roast", "roasted", "roasting",
    "exposed", "exposing", "drama", "beef", "cancelled",
    # Personal/Lifestyle
    "day in my life", "day in the life", "a day with",
    "morning routine", "night routine", "evening routine", "my routine",
    "what i eat", "what i ate", "full day of eating", "diet",
    "get ready with me", "grwm", "outfit", "fashion haul", "try on",
    "room makeover", "apartment tour", "house tour", "home tour",
    "travel vlog", "vacation", "trip to", "visiting",
    "wedding", "birthday", "anniversary", "holiday",
    "workout", "gym routine", "fitness routine", "exercise",
    # Low-Value Content
    "q&a", "ama", "ask me anything", "answering your questions",
    "reading comments", "responding to", "replying to",
    "shorts", "short", "#shorts", "tiktok", "reel",
    "clip", "clips", "highlight", "highlights", "compilation", "best of",
    "podcast ep", "full episode", "full interview",
    "live stream", "livestream", "streaming",
    "behind the scenes", "bts", "how we made",
    "bloopers", "outtakes", "deleted scenes",
    # News/Current Events
    "breaking", "just announced", "breaking news",
    "news", "update", "updates", "announcement",
    "what happened", "drama explained",
    "election", "vote", "political", "trump", "biden", "congress",
    "israel", "palestine", "ukraine", "russia", "iran", "china",
    "inflation", "recession", "fed", "federal reserve",
    "crypto", "bitcoin", "ethereum", "cryptocurrency",
    "stock market", "stocks", "economy news",
    "immigration", "border", "deport",
    # Music/Gaming/ASMR
    "music video", "official video", "official audio", "lyric video",
    "gameplay", "playthrough", "walkthrough", "let's play",
    "minecraft", "fortnite", "valorant", "gaming",
    "asmr", "mukbang", "relaxing", "sleep",
]

# Positive scoring hooks
MONEY_HOOKS = [
    "$", "revenue", "income", "profit", "money", "earn", "cash", "wealthy",
    "million", "millionaire", "billionaire", "rich", "wealth", "net worth",
    "salary", "raise", "pricing", "charge more", "high ticket", "premium"
]

TIME_HOOKS = [
    "faster", "save time", "productivity", "efficient", "quick", "speed",
    "in minutes", "in seconds", "instantly", "overnight", "shortcut",
    "hack", "hacks", "cheat code", "fast track", "accelerate"
]

CURIOSITY_HOOKS = [
    "?", "secret", "secrets", "nobody", "no one tells you", "they don't want",
    "this changed", "changed everything", "game changer", "mind blown",
    "shocking", "surprised", "unexpected", "plot twist",
    "never", "always", "stop", "don't", "quit", "avoid",
    "truth about", "real reason", "actually", "really",
    "hidden", "underground", "insider", "exclusive"
]

TRANSFORMATION_HOOKS = [
    "before", "after", "transformed", "transformation",
    "from zero", "from nothing", "started with",
    "how i went", "how i built", "journey",
    "changed my life", "life changing", "breakthrough"
]

CONTRARIAN_HOOKS = [
    "wrong", "mistake", "mistakes", "myth", "myths", "lie", "lies",
    "overrated", "underrated", "unpopular opinion", "controversial",
    "why i stopped", "why i quit", "the problem with",
    "nobody talks about", "uncomfortable truth"
]

URGENCY_HOOKS = [
    "before it's too late", "while you still can", "last chance",
    "now or never", "running out", "limited", "ending soon",
    "don't miss", "must watch", "need to know"
]

# User's channel context
USER_CHANNEL_NICHE = "AI agents, automation, LangGraph, CrewAI, agentic workflows"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]


def get_credentials():
    """Load Google credentials."""
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception:
            creds = None
    if not creds:
        service_account_file = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "credentials.json")
        if os.path.exists(service_account_file):
            with open(service_account_file, 'r') as f:
                content = json.load(f)
            if "type" in content and content["type"] == "service_account":
                creds = ServiceAccountCredentials.from_service_account_file(service_account_file, scopes=SCOPES)
            elif "installed" in content or "web" in content:
                flow = InstalledAppFlow.from_client_secrets_file(service_account_file, SCOPES)
                creds = flow.run_local_server(port=0)
                with open('token.json', 'w') as token:
                    token.write(creds.to_json())
    return creds


def search_tubelab_outliers(query, size=40, min_views=10000, video_type="video", published_after=None):
    """
    Search TubeLab for outliers.

    Args:
        query: Search term
        size: Number of results (default 40, API max per docs)
        min_views: Minimum view count
        video_type: "video" for long-form only
        published_after: ISO 8601 date string for server-side filtering

    Returns:
        List of video dicts or empty list on error
    """
    if not TUBELAB_API_KEY:
        print("ERROR: TUBELAB_API_KEY not set in .env")
        return []

    headers = {
        "Authorization": f"Api-Key {TUBELAB_API_KEY}",
        "Accept": "application/json"
    }

    params = {
        "query": query,
        "size": size,
        "type": video_type,
        "viewCountFrom": min_views,
        "language": "en",  # English only
    }

    # Server-side date filtering
    if published_after:
        params["publishedAtFrom"] = published_after

    try:
        response = requests.get(
            f"{TUBELAB_BASE_URL}/search/outliers",
            headers=headers,
            params=params,
            timeout=30
        )
        response.raise_for_status()
        data = response.json()

        videos = []
        for hit in data.get("hits", []):
            # Skip shorts
            if hit.get("kind") == "short":
                continue

            snippet = hit.get("snippet", {})
            stats = hit.get("statistics", {})

            # Get best thumbnail
            thumbnails = snippet.get("thumbnails", {})
            thumb_url = (
                thumbnails.get("high", {}).get("url") or
                thumbnails.get("medium", {}).get("url") or
                thumbnails.get("default", {}).get("url") or
                f"https://i.ytimg.com/vi/{hit['id']}/maxresdefault.jpg"
            )

            # Parse publish date
            published_at = snippet.get("publishedAt", "")
            if published_at:
                try:
                    pub_date = datetime.datetime.fromisoformat(published_at.replace("Z", "+00:00"))
                    date_str = pub_date.strftime("%Y%m%d")
                    days_old = (datetime.datetime.now(datetime.timezone.utc) - pub_date).days
                except:
                    date_str = ""
                    days_old = 999
            else:
                date_str = ""
                days_old = 999

            # Get classification data
            classification = hit.get("classification") or {}
            sentiment = snippet.get("sentiment") or {}

            video = {
                "video_id": hit.get("id"),
                "title": snippet.get("title", ""),
                "url": f"https://www.youtube.com/watch?v={hit['id']}",
                "view_count": stats.get("viewCount", 0),
                "like_count": stats.get("likeCount", 0),
                "comment_count": stats.get("commentCount", 0),
                "duration": snippet.get("duration", 0),
                "channel_name": snippet.get("channelTitle", ""),
                "channel_handle": snippet.get("channelHandle", ""),
                "channel_id": snippet.get("channelId", ""),
                "channel_subscribers": snippet.get("channelSubscribers", 0),
                "thumbnail_url": thumb_url,
                "date": date_str,
                "days_old": days_old,
                "language": snippet.get("language", ""),
                "sentiment": sentiment.get("sentiment", ""),
                "sub_sentiment": sentiment.get("subSentiment", ""),
                "is_faceless": classification.get("isFaceless", None),
                "quality": classification.get("quality", ""),
                # TubeLab already calculates this!
                "outlier_score": round(stats.get("averageViewsRatio", 1.0), 2),
                "z_score": round(stats.get("zScore", 0), 2),
                "source": f"tubelab: {query}",
            }
            videos.append(video)

        return videos

    except requests.exceptions.RequestException as e:
        print(f"  TubeLab API error: {str(e)[:100]}")
        return []


def calculate_cross_niche_score(title, base_outlier_score):
    """
    Calculate cross-niche potential score with comprehensive filtering.
    Returns 0 for hard-excluded content.
    """
    title_lower = title.lower()
    score = base_outlier_score

    # Hard exclude own niche
    if any(term in title_lower for term in OWN_NICHE_TERMS):
        return 0

    # Heavy penalty for non-transferable formats
    if any(fmt in title_lower for fmt in EXCLUDE_FORMATS):
        score *= 0.3

    # Bonuses for proven hooks
    if any(hook in title_lower for hook in MONEY_HOOKS):
        score *= 1.4
    if any(hook in title_lower for hook in CURIOSITY_HOOKS):
        score *= 1.3
    if any(hook in title_lower for hook in TRANSFORMATION_HOOKS):
        score *= 1.25
    if any(hook in title_lower for hook in CONTRARIAN_HOOKS):
        score *= 1.25
    if any(hook in title_lower for hook in TIME_HOOKS):
        score *= 1.2
    if any(hook in title_lower for hook in URGENCY_HOOKS):
        score *= 1.15
    if re.search(r'\b\d+\b', title):
        score *= 1.1

    return round(score, 2)


def categorize_content(title):
    """Auto-categorize content type."""
    title_lower = title.lower()

    if any(word in title_lower for word in ["money", "revenue", "income", "profit", "$", "million"]):
        return "Money"
    elif any(word in title_lower for word in ["productivity", "time", "efficient", "faster"]):
        return "Productivity"
    elif any(word in title_lower for word in ["youtube", "content", "creator", "channel"]):
        return "Creator"
    elif any(word in title_lower for word in ["business", "startup", "founder", "entrepreneur"]):
        return "Business"
    else:
        return "General"


def fetch_transcript(video_id):
    """Fetch transcript using youtube-transcript-api with Apify fallback."""
    if not video_id:
        return None

    # Try youtube-transcript-api first
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        time.sleep(1)  # Rate limit
        transcript = YouTubeTranscriptApi.get_transcript(video_id)
        text = ' '.join([entry['text'] for entry in transcript])
        return text
    except Exception as e:
        pass

    # Fallback to Apify
    apify_token = os.getenv("APIFY_API_TOKEN")
    if not apify_token:
        return None

    try:
        from apify_client import ApifyClient
        client = ApifyClient(apify_token)
        run = client.actor("karamelo/youtube-transcripts").call(
            run_input={"urls": [f"https://www.youtube.com/watch?v={video_id}"]},
            timeout_secs=120
        )
        items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
        if items and "captions" in items[0]:
            return " ".join(items[0]["captions"])
    except:
        pass

    return None


def summarize_transcript(text, title):
    """Summarize transcript with focus on transferable patterns."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return "Error: ANTHROPIC_API_KEY not set"

    client = Anthropic(api_key=api_key)

    prompt = f"""Analyze this YouTube video for transferable content patterns.

Title: {title}

Transcript (first 8000 chars):
{text[:8000]}

Provide BRIEF analysis (3-4 sentences total) covering:
1. Core hook/angle and why it works
2. Key content structure or pattern
3. How to adapt this for AI/automation content

Keep it concise and actionable."""

    try:
        message = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=500,
            temperature=0.7,
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text
    except Exception as e:
        return f"Summarization error: {str(e)}"


def generate_title_variants(original_title, summary=None):
    """Generate 3 title variants adapted for AI/automation niche."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return ["", "", ""]

    client = Anthropic(api_key=api_key)
    context = f"\n\nContext from original video: {summary}" if summary else ""

    prompt = f"""You're a YouTube strategist for a channel about {USER_CHANNEL_NICHE}.

Analyze this high-performing title from a different niche and generate 3 adapted variants for my channel.

Original Title: "{original_title}"{context}

Generate 3 NEW title variants that:
- Adapt the hook/structure to AI agents and automation
- Use the same emotional trigger and curiosity gap as original
- Are specific to {USER_CHANNEL_NICHE}
- Are meaningfully different from each other
- Stay under 100 characters

Return ONLY a JSON array of 3 strings (the variant titles), nothing else.
Example format: ["Variant 1", "Variant 2", "Variant 3"]"""

    try:
        message = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = message.content[0].text.strip()
        if response_text.startswith('```'):
            response_text = response_text.split('```')[1]
            if response_text.startswith('json'):
                response_text = response_text[4:]
            response_text = response_text.strip()

        variants = json.loads(response_text)
        if isinstance(variants, list) and len(variants) == 3:
            return variants
    except Exception as e:
        print(f"      Title variant error: {str(e)[:100]}")

    return ["", "", ""]


def process_outlier_content(outlier, index, total, skip_transcripts=False):
    """Process a single outlier: fetch transcript, summarize, generate variants."""
    title_short = outlier['title'][:50] + "..." if len(outlier['title']) > 50 else outlier['title']
    print(f"\n  [{index}/{total}] {title_short}")

    if skip_transcripts:
        outlier["summary"] = "Skipped"
        outlier["transcript"] = ""
    else:
        print(f"    Fetching transcript...")
        transcript = fetch_transcript(outlier["video_id"])

        if transcript:
            print(f"    Got transcript ({len(transcript)} chars)")
            summary = summarize_transcript(transcript, outlier["title"])
            outlier["summary"] = summary
            outlier["transcript"] = transcript
        else:
            print(f"    No transcript available")
            outlier["summary"] = "No transcript available"
            outlier["transcript"] = ""

    outlier["category"] = categorize_content(outlier["title"])

    print(f"    Generating title variants...")
    variants = generate_title_variants(
        outlier["title"],
        outlier.get("summary") if not skip_transcripts else None
    )
    outlier["title_variant_1"] = variants[0] if len(variants) > 0 else ""
    outlier["title_variant_2"] = variants[1] if len(variants) > 1 else ""
    outlier["title_variant_3"] = variants[2] if len(variants) > 2 else ""

    print(f"    Done")
    return outlier


def main():
    parser = argparse.ArgumentParser(description="Cross-niche outlier detection via TubeLab API")
    parser.add_argument("--queries", type=int, default=1, help="Number of TubeLab queries (5 credits each)")
    parser.add_argument("--terms", nargs="+", help="Custom search terms (overrides defaults)")
    parser.add_argument("--size", type=int, default=100, help="Results per query (default: 100)")
    parser.add_argument("--min_views", type=int, default=10000, help="Minimum view count")
    parser.add_argument("--max_days", type=int, default=30, help="Max age in days (default: 30 = last month)")
    parser.add_argument("--min_score", type=float, default=1.5, help="Minimum outlier score after filtering")
    parser.add_argument("--limit", type=int, help="Max outliers to process")
    parser.add_argument("--skip_transcripts", action="store_true", help="Skip transcript fetching")
    parser.add_argument("--workers", type=int, default=3, help="Parallel workers for content processing")

    args = parser.parse_args()

    if not TUBELAB_API_KEY:
        print("ERROR: TUBELAB_API_KEY not set in .env")
        return 1

    # Determine search terms
    search_terms = args.terms if args.terms else DEFAULT_SEARCH_TERMS[:args.queries]

    print(f"Cross-Niche Outlier Detection (TubeLab API)")
    print(f"  Search terms: {search_terms}")
    print(f"  Results per query: {args.size}")
    print(f"  Min views: {args.min_views:,}")
    print(f"  Max age: {args.max_days} days")
    print(f"  Min cross-niche score: {args.min_score}")
    print(f"  Estimated credits: {len(search_terms) * 5}")
    print()

    # Calculate published_after date for server-side filtering
    published_after = (
        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=args.max_days)
    ).strftime("%Y-%m-%dT00:00:00Z")
    print(f"  Date filter: {published_after}")
    print()

    # Step 1: Fetch outliers from TubeLab
    print("Fetching outliers from TubeLab...")
    all_videos = []

    for term in search_terms:
        print(f"  Searching: {term}")
        videos = search_tubelab_outliers(
            query=term,
            size=args.size,
            min_views=args.min_views,
            video_type="video",
            published_after=published_after
        )
        print(f"    Found {len(videos)} videos")
        all_videos.extend(videos)
        time.sleep(0.5)  # Rate limit (10 req/min)

    # Deduplicate
    seen = set()
    unique_videos = []
    for v in all_videos:
        if v["video_id"] not in seen:
            seen.add(v["video_id"])
            unique_videos.append(v)

    print(f"\nFound {len(unique_videos)} unique videos")

    # Step 2: Apply cross-niche scoring and filtering
    print("\nApplying cross-niche filters...")
    outliers = []
    filtered_own_niche = 0
    filtered_low_score = 0

    for video in unique_videos:
        # Date filtering now done server-side via publishedAtFrom

        cross_score = calculate_cross_niche_score(video["title"], video["outlier_score"])

        if cross_score == 0:
            filtered_own_niche += 1
            continue

        if cross_score < args.min_score:
            filtered_low_score += 1
            continue

        video["cross_niche_score"] = cross_score
        outliers.append(video)

    print(f"  Filtered {filtered_own_niche} own-niche videos")
    print(f"  Filtered {filtered_low_score} low cross-niche score videos")
    print(f"  Remaining: {len(outliers)} outliers")

    # Sort by date (most recent first)
    outliers.sort(key=lambda x: x.get("date", ""), reverse=True)

    if args.limit:
        outliers = outliers[:args.limit]

    if not outliers:
        print("\nNo outliers found with current criteria. Try lowering --min_score.")
        return 0

    # Step 3: Process content (transcripts, summaries, variants)
    print(f"\nProcessing {len(outliers)} outliers...")

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                process_outlier_content,
                outlier, i, len(outliers),
                args.skip_transcripts
            ): outlier
            for i, outlier in enumerate(outliers, 1)
        }
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print(f"    Error: {str(e)}")

    # Step 4: Create Google Sheet
    print("\nCreating Google Sheet...")
    creds = get_credentials()
    gc = gspread.authorize(creds)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    sheet_title = f"Cross-Niche Outliers (TubeLab) - {timestamp}"
    spreadsheet = gc.create(sheet_title)
    worksheet = spreadsheet.sheet1

    headers = [
        # Scores
        "Cross-Niche Score", "Outlier Score", "Z-Score",
        # Video info
        "Title", "Video Link", "Thumbnail URL", "Thumbnail Preview",
        # Stats
        "Views", "Likes", "Comments", "Duration (min)", "Days Old",
        # Channel info
        "Channel", "Channel Handle", "Channel Subs",
        # Classification
        "Category", "Sentiment", "Is Faceless", "Quality",
        # Generated content
        "Summary", "Title Variant 1", "Title Variant 2", "Title Variant 3",
        # Raw data
        "Raw Transcript", "Publish Date", "Language", "Source"
    ]

    rows = [headers]
    for o in outliers:
        rows.append([
            # Scores
            o["cross_niche_score"],
            o["outlier_score"],
            o.get("z_score", 0),
            # Video info
            o["title"],
            o["url"],
            o["thumbnail_url"],  # Raw URL for downstream use
            f'=IMAGE("{o["thumbnail_url"]}")',  # Preview
            # Stats
            o["view_count"],
            o.get("like_count", 0),
            o.get("comment_count", 0),
            round(o.get("duration", 0) / 60, 1),
            o.get("days_old", "N/A"),
            # Channel info
            o["channel_name"],
            o.get("channel_handle", ""),
            o.get("channel_subscribers", 0),
            # Classification
            o.get("category", "Unknown"),
            o.get("sentiment", ""),
            o.get("is_faceless", ""),
            o.get("quality", ""),
            # Generated content
            o.get("summary", ""),
            o.get("title_variant_1", ""),
            o.get("title_variant_2", ""),
            o.get("title_variant_3", ""),
            # Raw data
            o.get("transcript", "")[:50000],  # Sheet cell limit
            o["date"],
            o.get("language", ""),
            o.get("source", "")
        ])

    worksheet.update(range_name='A1', values=rows, value_input_option='USER_ENTERED')

    print(f"\nDone! Created sheet with {len(outliers)} cross-niche outliers")
    print(f"Sheet URL: {spreadsheet.url}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
