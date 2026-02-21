#!/usr/bin/env python3
"""
Scrape YouTube for cross-niche business outliers with transferable content patterns.
IMPROVED VERSION with:
- Better transcript handling (no Apify dependency)
- Integrated title variant generation
- More reasonable outlier detection (like 1of10)
- Better error handling and progress reporting
"""

import os
import sys
import json
import time
import datetime
import subprocess
import argparse
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from anthropic import Anthropic
import gspread
from google.oauth2.credentials import Credentials
from google.oauth2.service_account import Credentials as ServiceAccountCredentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# Load environment variables
load_dotenv()

# Cross-Niche Keywords - Alex Hormozi style (specific enough to avoid noise)
CROSS_NICHE_KEYWORDS = [
    # Business building (Alex Hormozi core topics)
    "how to scale a business",
    "business growth strategies",
    "increase business revenue",
    "gym launch strategy",
    "acquisition.com",

    # Sales & marketing (actionable)
    "how to sell more",
    "closing sales techniques",
    "marketing funnel strategy",
    "lead generation tips",

    # Wealth building (specific)
    "how to make your first million",
    "millionaire business advice",
    "building wealth through business",
    "cash flow strategies",

    # Mindset & systems (business-focused)
    "entrepreneur mindset for success",
    "business systems automation",
    "scaling without burnout",
    "productivity for founders"
]

# =============================================================================
# CHANNEL LIST - Multi-Niche (NOT just business)
# =============================================================================
# Organized by niche for diversity. Goal: Find transferable hooks from
# productivity, academic, storytelling, finance, self-improvement, etc.

MONITORED_CHANNELS = {
    # -------------------------------------------------------------------------
    # BUSINESS STRATEGY (Core - proven hooks)
    # -------------------------------------------------------------------------
    "UCMrnHNmYzP3LgvKzyq0ILgw": "Alex Hormozi",          # Business scaling, systems
    "UC3yRaQ9qZczN2M5C3kQZlaQ": "Leila Hormozi",         # Operations, hiring, leadership
    "UCwgz-59Z39I8-ZrrHjy6nKw": "My First Million",      # Business ideas, Sam & Shaan
    "UCJustJoeTalks": "Codie Sanchez",                   # Contrarian investing, acquisitions
    "UCIgRClj26EZAKkamv1kzTdA": "Noah Kagan",            # Business experiments, AppSumo
    "UCGy6QE39swWGy-Yb1lMZ_tA": "Greg Isenberg",         # Startup ideas, trend-spotting
    "UC35LCBb7eVc9FXgwDKgBz2Q": "Dan Martell",           # SaaS, Buy Back Your Time
    "UCeqFD1zGwf7_LnrP6ANPlBw": "Patrick Bet-David",     # Business philosophy, Valuetainment

    # -------------------------------------------------------------------------
    # PRODUCTIVITY & SYSTEMS
    # -------------------------------------------------------------------------
    "UCoOae5nYA7VqaXzerajD0lg": "Ali Abdaal",            # Productivity, part-time YouTuber
    "UCG-KntY7aVnIGXYEBQvmBAQ": "Thomas Frank",          # Study/productivity systems
    "UCJ24N4O0bP7LGLBDvye7oCA": "Matt D'Avella",         # Minimalism, habits, documentaries
    "UCIaH-gZIVC432YRjNVvnyCA": "Tiago Forte",           # Second Brain, knowledge management
    "UC4xKdmAXFh4ACyhpiQ_3qBg": "Cal Newport",           # Deep work, digital minimalism
    "UCfbGTpcJyEOMwKP-eYz3_fg": "August Bradley",        # Notion, life design systems

    # -------------------------------------------------------------------------
    # ACADEMIC & SCIENCE (Storytelling/explanation hooks)
    # -------------------------------------------------------------------------
    "UCHnyfMqiRRG1u-2MsSQLbXA": "Veritasium",            # Science storytelling, curiosity
    "UCYO_jab_esuFRV4b17AJtAw": "3Blue1Brown",           # Math visualization, explanations
    "UCsXVk37bltHxD1rDPwtNM8Q": "Kurzgesagt",            # Animated explainers, existential
    "UCBcRF18a7Qf58cCRy5xuWwQ": "ASAP Science",          # Quick science explanations
    "UC9-y-6csu5WGm29I7JiwpnA": "Computerphile",         # CS concepts explained simply
    "UCZYTClx2T1of7BRZ86-8fow": "Scishow",               # Science news, curiosity hooks
    "UCsooa4yRKGN_zEE8iknghZA": "TED-Ed",                # Educational animations

    # -------------------------------------------------------------------------
    # BUSINESS STORYTELLING & DOCUMENTARY
    # -------------------------------------------------------------------------
    "UCqnbDFdCpuN8CMEg0VuEBqA": "Johnny Harris",         # Documentary journalism, maps
    "UCmyxyR7qlShxU0KXJGPE7aw": "Wendover Productions",  # Logistics, business, aviation
    "UCVHFbqXqoYvEWM1Ddxl0QKg": "Polymatter",            # Business/geopolitics analysis
    "UCe0DNp0mKMqrYVaTundyr9w": "Economics Explained",   # Economics made accessible
    "UCy-uo0eOdfnKBSjYwNaPjuw": "ColdFusion",            # Tech/business documentaries
    "UC2C_jShtL725hvbm1arSV9w": "CGP Grey",              # Systems thinking, explanations
    "UCHdos0HAIEhIMqUc9L3Kb1Q": "Half as Interesting",   # Quirky business/logistics

    # -------------------------------------------------------------------------
    # CREATOR ECONOMY & YOUTUBE STRATEGY
    # -------------------------------------------------------------------------
    "UCWsV__V0nANOeXa1bWgN3Xw": "Colin and Samir",       # Creator economy interviews
    "UC1dGTEzZFD0GXe9dEMJSblA": "Paddy Galloway",        # YouTube strategy, analytics
    "UCqtL6ynOaJJ5j7S-4w7c1Fw": "Film Booth",            # Storytelling, video structure
    "UCY1TadMVNLcdoKsDej2FHVA": "Jenny Hoyos",           # Shorts strategy, viral hooks

    # -------------------------------------------------------------------------
    # FINANCE & INVESTING (Money hooks transfer well)
    # -------------------------------------------------------------------------
    "UCV6KDgJskWaEckne5aPA0aQ": "Graham Stephan",        # Real estate, money psychology
    "UCGy7SkBjcIAgTiwkXEtPnYg": "Andrei Jikh",           # Investing, financial freedom
    "UCMtI88Kqc0RwSaLQxDMKCzA": "Mark Tilbury",          # Wealth building, simple advice
    "UCFCEuCsyWP0YkP3CZ3Mr01Q": "The Plain Bagel",       # Finance explained simply
    "UCnMn36GT_H0X-w5_ckLtlgQ": "Minority Mindset",      # Money mindset, financial literacy

    # -------------------------------------------------------------------------
    # SELF-IMPROVEMENT (Universal psychological hooks)
    # -------------------------------------------------------------------------
    "UCGq7ov9-Xk9fkeQjeeXElkQ": "Chris Williamson",      # Modern Wisdom podcast clips
    "UC2D2CMWXMOVWx7giW1n3LIg": "Huberman Lab",          # Science-backed optimization
    "UCvOreA_lxS92xVG-fE7fKtg": "Hamza",                 # Self-improvement for men
    "UC-lHJZR3Gqxm24_Vd_AJ5Yw": "PewDiePie",             # Commentary (massive reach)
    "UCnQC_G5Xsjhp9fEJKuIcrSw": "Ben Shapiro",           # Political commentary (hook style)

    # -------------------------------------------------------------------------
    # WRITING & COMMUNICATION
    # -------------------------------------------------------------------------
    "UC9_p50tH3WmMslWRWKnM7dQ": "Simon Sinek",           # Leadership, communication
    "UCAuUUnT6oDeKwE6v1NGQxug": "TED",                   # Ideas worth spreading
    "UCamLstJyCa-t5gfZegxsFMw": "Chris Do",              # Design, pricing, business

    # -------------------------------------------------------------------------
    # PHILOSOPHY & THINKING
    # -------------------------------------------------------------------------
    "UCfQgsKhHjSyRLOp9mnffqVg": "Pursuit of Wonder",     # Philosophy, existential
    "UCWOA1ZGywLbqmigxE4Qlvuw": "Academy of Ideas",      # Philosophy, psychology
    "UC22BuJwmooPJLsRyDe9-cuw": "Einzelgänger",          # Stoicism, philosophy
}

# =============================================================================
# EXCLUSION FILTERS
# =============================================================================

# OWN NICHE - Hard exclude (we want CROSS-niche, not our niche)
OWN_NICHE_TERMS = [
    # AI/ML Core (include variants with periods/spaces)
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

# NON-TRANSFERABLE FORMATS - Heavy penalty (these don't translate to thumbnails/hooks)
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

    # News/Current Events (not evergreen)
    "breaking", "just announced", "breaking news",
    "news", "update", "updates", "announcement",
    "what happened", "drama explained",
    "election", "vote", "political", "trump", "biden", "congress",
    "israel", "palestine", "ukraine", "russia", "iran", "china",
    "inflation", "recession", "fed", "federal reserve",
    "crypto", "bitcoin", "ethereum", "cryptocurrency",
    "stock market", "stocks", "economy news",
    "immigration", "border", "deport",

    # Platform-Specific (not transferable)
    "youtube algorithm", "youtube update", "monetization",
    "subscriber", "subscribers", "sub count", "hitting",
    "play button", "silver play", "gold play",
    "channel update", "channel news",

    # Tutorials Too Specific
    "tutorial", "how to edit", "editing tutorial",
    "photoshop", "premiere", "final cut", "davinci",
    "canva tutorial", "figma tutorial",

    # Music/Audio
    "music video", "official video", "official audio", "lyric video",
    "cover", "remix", "mashup", "acoustic",
    "ft.", "feat.", "featuring",
    "album", "ep release", "single",

    # Gaming
    "gameplay", "playthrough", "walkthrough", "let's play",
    "minecraft", "fortnite", "valorant", "league", "apex",
    "gaming", "gamer", "twitch", "esports",

    # Food/Cooking Specific
    "recipe", "cooking", "baking", "how to cook", "how to make",
    "mukbang", "eating", "food review", "restaurant",

    # ASMR/Relaxation
    "asmr", "relaxing", "sleep", "meditation", "ambient",
    "white noise", "rain sounds", "study music",

    # Relationship/Dating
    "dating", "relationship", "boyfriend", "girlfriend", "marriage",
    "breakup", "ex", "crush", "love life",

    # Misc Non-Transferable
    "storytime", "story time", "confession",
    "haul", "shopping haul", "favorites",
    "empties", "monthly favorites",
    "tier list", "ranking every",
]

# Technical terms that reduce cross-niche score (softer penalty than hard exclude)
TECHNICAL_TERMS = [
    "API", "Python", "code", "SDK", "framework", "JavaScript",
    "LangGraph", "CrewAI", "n8n", "Zapier", "Make.com", "GitHub",
    "programming", "developer", "coding", "script", "database",
    "server", "cloud", "saas", "software"
]

# =============================================================================
# POSITIVE SCORING HOOKS
# =============================================================================

# Power words that boost cross-niche score
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

MAX_VIDEOS_PER_KEYWORD = 50  # UPDATED: Increased from 30 to get more results
MAX_VIDEOS_PER_CHANNEL = 15  # UPDATED: Increased from 10 to get more results
DAYS_BACK = 90  # UPDATED: Changed to 90 for more outliers (3 months of data)
MIN_OUTLIER_SCORE = 1.1  # UPDATED: Lowered to 1.1 (10% above average) to find ~20 outliers
MIN_VIDEO_DURATION_SECONDS = 180  # 3 minutes - filter out shorts and clips
MIN_VIEW_COUNT = 1000  # Minimum views to be considered

# User's channel context (for title variant generation)
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


def run_ytdlp(command):
    """Run yt-dlp command and return JSON output."""
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=60)
        items = []
        for line in result.stdout.strip().split('\n'):
            if line:
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return items
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        print(f"    yt-dlp error: {str(e)[:100]}")
        return []


def calculate_cross_niche_score(title, base_outlier_score):
    """
    Calculate cross-niche potential score with comprehensive filtering.

    Hard Exclude (return 0):
    - Own niche terms (AI, automation, code, etc.)

    Heavy Penalty (-70%):
    - Non-transferable formats (gear, challenges, vlogs, etc.)

    Soft Penalty (-20% per term):
    - Technical terms

    Bonuses:
    - Money hooks: +40%
    - Curiosity hooks: +30%
    - Transformation hooks: +25%
    - Contrarian hooks: +25%
    - Time hooks: +20%
    - Urgency hooks: +15%
    - Numbers (listicles): +10%

    Args:
        title: Video title
        base_outlier_score: Original outlier score

    Returns:
        Cross-niche score (float), or 0 if hard excluded
    """
    title_lower = title.lower()
    score = base_outlier_score

    # ==========================================================================
    # HARD EXCLUSIONS (return 0)
    # ==========================================================================

    # Own niche - we want CROSS-niche content, not our own niche
    if any(term in title_lower for term in OWN_NICHE_TERMS):
        return 0

    # ==========================================================================
    # HEAVY PENALTIES
    # ==========================================================================

    # Non-transferable formats (gear reviews, challenges, vlogs, etc.)
    if any(fmt in title_lower for fmt in EXCLUDE_FORMATS):
        score *= 0.3  # -70% penalty

    # ==========================================================================
    # SOFT PENALTIES
    # ==========================================================================

    # Technical terms (softer penalty)
    tech_count = sum(1 for term in TECHNICAL_TERMS if term.lower() in title_lower)
    score *= max(0.2, 1.0 - (tech_count * 0.2))  # Cap at -80%

    # ==========================================================================
    # BONUSES
    # ==========================================================================

    # Money hooks (highest value - proven CTR)
    if any(hook in title_lower for hook in MONEY_HOOKS):
        score *= 1.4

    # Curiosity hooks (high value - drives clicks)
    if any(hook in title_lower for hook in CURIOSITY_HOOKS):
        score *= 1.3

    # Transformation hooks (emotional resonance)
    if any(hook in title_lower for hook in TRANSFORMATION_HOOKS):
        score *= 1.25

    # Contrarian hooks (pattern interrupt)
    if any(hook in title_lower for hook in CONTRARIAN_HOOKS):
        score *= 1.25

    # Time hooks (practical value)
    if any(hook in title_lower for hook in TIME_HOOKS):
        score *= 1.2

    # Urgency hooks (FOMO)
    if any(hook in title_lower for hook in URGENCY_HOOKS):
        score *= 1.15

    # Numbers (listicles - proven format)
    if re.search(r'\b\d+\b', title):
        score *= 1.1

    return round(score, 2)


def scrape_keyword(keyword):
    """Scrape a single keyword using yt-dlp."""
    print(f"  - Searching: {keyword}")
    cmd = [
        "yt-dlp",
        f"ytsearch{MAX_VIDEOS_PER_KEYWORD}:{keyword}",
        "--dump-json",
        "--no-playlist",
        "--skip-download",
        "--no-warnings"
    ]

    items = run_ytdlp(cmd)
    videos = []
    cutoff_date = (datetime.datetime.now() - datetime.timedelta(days=DAYS_BACK)).strftime("%Y%m%d")

    for item in items:
        upload_date = item.get("upload_date")
        if not upload_date or upload_date < cutoff_date:
            continue

        video_id = item.get("id")
        youtube_url = f"https://www.youtube.com/watch?v={video_id}" if video_id else item.get("webpage_url")

        # Filter by duration and views
        duration = item.get("duration", 0)
        view_count = item.get("view_count", 0)

        if duration < MIN_VIDEO_DURATION_SECONDS or view_count < MIN_VIEW_COUNT:
            continue

        video_data = {
            "title": item.get("title"),
            "url": youtube_url,
            "view_count": view_count,
            "duration": duration,
            "channel_name": item.get("uploader") or item.get("channel"),
            "channel_url": item.get("uploader_url") or item.get("channel_url"),
            "thumbnail_url": item.get("thumbnail"),
            "date": upload_date,
            "video_id": video_id,
            "source": f"keyword: {keyword}"
        }
        videos.append(video_data)

    return videos


def scrape_channel(channel_id, channel_name):
    """Scrape recent videos from a specific channel."""
    print(f"  - Monitoring channel: {channel_name}")
    channel_url = f"https://www.youtube.com/channel/{channel_id}/videos"

    cmd = [
        "yt-dlp",
        channel_url,
        "--dump-json",
        "--playlist-end", str(MAX_VIDEOS_PER_CHANNEL),
        "--skip-download",
        "--no-warnings"
    ]

    items = run_ytdlp(cmd)
    videos = []
    cutoff_date = (datetime.datetime.now() - datetime.timedelta(days=DAYS_BACK)).strftime("%Y%m%d")

    for item in items:
        upload_date = item.get("upload_date")
        if not upload_date or upload_date < cutoff_date:
            continue

        video_id = item.get("id")
        youtube_url = f"https://www.youtube.com/watch?v={video_id}" if video_id else item.get("webpage_url")

        # Filter by duration and views
        duration = item.get("duration", 0)
        view_count = item.get("view_count", 0)

        if duration < MIN_VIDEO_DURATION_SECONDS or view_count < MIN_VIEW_COUNT:
            continue

        video_data = {
            "title": item.get("title"),
            "url": youtube_url,
            "view_count": view_count,
            "duration": duration,
            "channel_name": channel_name,
            "channel_url": f"https://www.youtube.com/channel/{channel_id}",
            "thumbnail_url": item.get("thumbnail"),
            "date": upload_date,
            "video_id": video_id,
            "source": f"channel: {channel_name}"
        }
        videos.append(video_data)

    return videos


def get_channel_average(channel_url):
    """Get average view count for a channel."""
    if not channel_url:
        return 0

    cmd = [
        "yt-dlp",
        channel_url,
        "--dump-json",
        "--playlist-end", "10",  # Increased from 5 to 10 for better average
        "--flat-playlist",
        "--skip-download"
    ]

    items = run_ytdlp(cmd)
    views = [int(item.get("view_count")) for item in items if item.get("view_count") is not None]

    return sum(views) / len(views) if views else 0


def fetch_transcript(video_id):
    """Fetch transcript using youtube-transcript-api with Apify fallback."""
    if not video_id:
        return None

    # Try youtube-transcript-api first (free, fast)
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        import time as time_module

        # Add small delay to avoid rate limiting
        time_module.sleep(1)

        transcript = YouTubeTranscriptApi.get_transcript(video_id)
        text = ' '.join([entry['text'] for entry in transcript])
        return text
    except Exception as e:
        # Silently fail - try Apify fallback
        error_str = str(e).lower()
        if '429' in error_str or 'too many requests' in error_str:
            # Rate limited - wait longer and retry once
            time_module.sleep(5)
            try:
                transcript = YouTubeTranscriptApi.get_transcript(video_id)
                text = ' '.join([entry['text'] for entry in transcript])
                return text
            except:
                pass  # Fall through to Apify

    # Fallback to Apify karamelo/youtube-transcripts (free tier available)
    apify_token = os.getenv("APIFY_API_TOKEN")
    if not apify_token:
        return None

    try:
        from apify_client import ApifyClient
        apify_client = ApifyClient(apify_token)

        video_url = f"https://www.youtube.com/watch?v={video_id}"
        run_input = {"urls": [video_url]}

        # Use karamelo/youtube-transcripts (free and reliable)
        run = apify_client.actor("karamelo/youtube-transcripts").call(
            run_input=run_input,
            timeout_secs=120
        )

        dataset_items = list(apify_client.dataset(run["defaultDatasetId"]).iterate_items())

        if dataset_items and len(dataset_items) > 0:
            item = dataset_items[0]
            # karamelo returns captions as a list of strings
            if "captions" in item and isinstance(item["captions"], list):
                return " ".join(item["captions"])

        return None
    except Exception as e:
        # Silently fail - some videos genuinely don't have transcripts
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
            max_tokens=500,  # Reduced from 1000
            temperature=0.7,
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text
    except Exception as e:
        return f"Summarization error: {str(e)}"


def generate_title_variants(original_title, summary=None):
    """
    Generate 3 title variants adapted for AI/automation niche.

    Args:
        original_title: Original outlier video title
        summary: Optional video summary for context

    Returns:
        List of 3 title variant strings
    """
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

        # Try to extract JSON if there's extra text
        if response_text.startswith('```'):
            response_text = response_text.split('```')[1]
            if response_text.startswith('json'):
                response_text = response_text[4:]
            response_text = response_text.strip()

        variants = json.loads(response_text)

        if isinstance(variants, list) and len(variants) == 3:
            return variants
        else:
            return ["", "", ""]

    except Exception as e:
        print(f"      Title variant error: {str(e)[:100]}")
        return ["", "", ""]


def process_outlier_content(outlier, index, total):
    """
    Process a single outlier: fetch transcript, summarize, generate variants.
    Thread-safe wrapper for parallel processing.
    """
    title_short = outlier['title'][:50] + "..." if len(outlier['title']) > 50 else outlier['title']
    print(f"\n  [{index}/{total}] {title_short}")

    # Fetch transcript
    print(f"    📄 Fetching transcript...")
    transcript = fetch_transcript(outlier["video_id"])

    if transcript:
        print(f"    ✓ Got transcript ({len(transcript)} chars)")
        summary = summarize_transcript(transcript, outlier["title"])
        outlier["summary"] = summary
        outlier["transcript"] = transcript
    else:
        print(f"    ⚠ No transcript available")
        summary = None
        outlier["summary"] = "No transcript available"
        outlier["transcript"] = ""

    # Categorize
    outlier["category"] = categorize_content(outlier["title"], outlier.get("summary", ""))

    # Generate title variants
    print(f"    🎯 Generating title variants...")
    variants = generate_title_variants(outlier["title"], summary)
    outlier["title_variant_1"] = variants[0] if len(variants) > 0 else ""
    outlier["title_variant_2"] = variants[1] if len(variants) > 1 else ""
    outlier["title_variant_3"] = variants[2] if len(variants) > 2 else ""

    if variants[0]:
        print(f"    ✓ [{index}/{total}] Completed: {title_short}")

    return outlier


def is_noise_content(title):
    """
    Filter out content that should never appear in results.
    This is a first-pass filter before scoring.
    """
    title_lower = title.lower()

    # Hard exclude - these should never appear
    hard_exclude = [
        # Music
        "official music video", "official video", "lyric video", "music video",
        "ft.", "feat.", "(official audio)", "official audio",
        "album", "ep release", "remix", "cover song",

        # Gaming
        "minecraft", "fortnite", "valorant", "call of duty", "gta",
        "gameplay", "gaming", "let's play", "walkthrough", "playthrough",
        "speedrun", "esports", "twitch",

        # Low-effort formats
        "asmr", "mukbang", "eating show",
        "#shorts", "tiktok compilation",

        # Foreign language (unless you want non-English)
        # Uncomment if needed:
        # "en español", "auf deutsch", "en français",
    ]

    # Check if title contains own niche (shouldn't be in cross-niche results)
    if any(term in title_lower for term in OWN_NICHE_TERMS):
        return True

    return any(pattern in title_lower for pattern in hard_exclude)


def categorize_content(title, summary):
    """Auto-categorize content type based on title and summary."""
    title_lower = title.lower()
    summary_lower = summary.lower() if summary else ""

    combined = title_lower + " " + summary_lower

    # Check for keywords in combined text
    if any(word in combined for word in ["money", "revenue", "income", "profit", "$", "million", "millionaire", "cash", "earn"]):
        return "Money"
    elif any(word in combined for word in ["productivity", "time", "efficient", "faster", "save time", "productive", "hack"]):
        return "Productivity"
    elif any(word in combined for word in ["youtube", "content", "creator", "channel", "subscriber", "video", "views"]):
        return "Creator"
    elif any(word in combined for word in ["business", "startup", "founder", "entrepreneur", "company", "scale", "grow"]):
        return "Business"
    elif any(word in combined for word in ["ai", "automation", "tool", "chatgpt", "agent", "code"]):
        return "AI/Tech"
    else:
        return "General"


def main():
    parser = argparse.ArgumentParser(description="Scrape cross-niche business outliers")
    parser.add_argument("--limit", type=int, help="Limit outliers to process")
    parser.add_argument("--days", type=int, default=90, help="Days to look back (default: 90)")
    parser.add_argument("--min_score", type=float, default=1.1, help="Min outlier score (default: 1.1)")
    parser.add_argument("--keywords_only", action="store_true", help="Skip channel monitoring")
    parser.add_argument("--channels_only", action="store_true", help="Skip keyword searches")
    parser.add_argument("--skip_transcripts", action="store_true", help="Skip transcript fetching (faster)")
    parser.add_argument("--content_workers", type=int, default=5, help="Parallel workers for transcript/summary (default: 5)")

    args = parser.parse_args()

    global DAYS_BACK, MIN_OUTLIER_SCORE
    DAYS_BACK = args.days
    MIN_OUTLIER_SCORE = args.min_score

    print(f"🔍 Cross-Niche Outlier Detection v2 (IMPROVED)")
    print(f"   Days back: {DAYS_BACK}")
    print(f"   Min score: {MIN_OUTLIER_SCORE} (1.2 = 20% above avg, 1.3 = 30%, 1.5 = 50%)")
    print(f"   Will generate 3 title variants per outlier")
    print(f"   Target: ~20 outliers per run")
    print()

    # Step 1: Scrape videos
    all_videos = []

    if not args.channels_only:
        print("📺 Scraping keywords...")
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(scrape_keyword, kw) for kw in CROSS_NICHE_KEYWORDS]
            for future in as_completed(futures):
                all_videos.extend(future.result())

    if not args.keywords_only:
        print("\n🎬 Monitoring channels...")
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(scrape_channel, cid, cname)
                      for cid, cname in MONITORED_CHANNELS.items()]
            for future in as_completed(futures):
                all_videos.extend(future.result())

    # Deduplicate and filter noise
    seen = set()
    unique_videos = []
    filtered_count = 0
    for v in all_videos:
        if v["video_id"] not in seen:
            seen.add(v["video_id"])
            # Filter out noise content
            if is_noise_content(v["title"]):
                filtered_count += 1
                continue
            unique_videos.append(v)

    print(f"\n✓ Found {len(unique_videos)} unique videos (filtered {filtered_count} noise videos)")

    if not unique_videos:
        print("No videos found. Exiting.")
        return 0

    # Step 2: Calculate outlier scores
    print("\n📊 Calculating outlier scores...")
    with ThreadPoolExecutor(max_workers=20) as executor:
        channel_futures = {v["channel_url"]: executor.submit(get_channel_average, v["channel_url"])
                          for v in unique_videos if v.get("channel_url")}

        channel_avgs = {url: future.result() for url, future in channel_futures.items()}

    outliers = []
    for video in unique_videos:
        channel_avg = channel_avgs.get(video.get("channel_url"), 0)
        if channel_avg > 0:
            # Calculate base outlier score
            raw_outlier_score = video["view_count"] / channel_avg

            # Apply recency boost: newer videos get a boost since they've had less time to accumulate views
            upload_date = datetime.datetime.strptime(video["date"], "%Y%m%d")
            days_old = (datetime.datetime.now() - upload_date).days
            if days_old <= 1:
                recency_multiplier = 2.0  # 100% boost for videos < 1 day old
            elif days_old <= 3:
                recency_multiplier = 1.5  # 50% boost for videos < 3 days old
            elif days_old <= 7:
                recency_multiplier = 1.2  # 20% boost for videos < 7 days old
            else:
                recency_multiplier = 1.0

            outlier_score = raw_outlier_score * recency_multiplier

            if outlier_score >= MIN_OUTLIER_SCORE:
                cross_niche_score = calculate_cross_niche_score(video["title"], outlier_score)

                # Skip if hard-excluded (score = 0)
                if cross_niche_score == 0:
                    continue

                video["outlier_score"] = round(outlier_score, 2)
                video["raw_outlier_score"] = round(raw_outlier_score, 2)
                video["channel_avg_views"] = int(channel_avg)
                video["cross_niche_score"] = cross_niche_score
                video["days_old"] = days_old
                outliers.append(video)

    # Sort by cross-niche score (highest transferability first)
    outliers.sort(key=lambda x: x["cross_niche_score"], reverse=True)

    if args.limit:
        outliers = outliers[:args.limit]

    print(f"✓ Found {len(outliers)} outliers (sorted by cross-niche score)")

    if not outliers:
        print("No outliers found with current criteria. Try lowering --min_score.")
        return 0

    # Step 3: Fetch transcripts, summarize, and generate title variants (PARALLEL)
    if not args.skip_transcripts:
        print(f"\n📝 Fetching transcripts & generating content for {len(outliers)} outliers...")
        print(f"   Using {args.content_workers} parallel workers")
        start_content_time = time.time()

        # Process outliers in parallel
        with ThreadPoolExecutor(max_workers=args.content_workers) as executor:
            futures = {
                executor.submit(process_outlier_content, outlier, i, len(outliers)): outlier
                for i, outlier in enumerate(outliers, 1)
            }

            # Collect results (outliers are modified in place, but we wait for completion)
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    print(f"    ❌ Error processing outlier: {str(e)}")

        content_elapsed = time.time() - start_content_time
        print(f"\n   ✓ Content processing complete in {content_elapsed:.1f}s")
    else:
        print("\n⏭ Skipping transcripts and summaries (--skip_transcripts flag)")
        for outlier in outliers:
            outlier["summary"] = "Skipped"
            outlier["transcript"] = ""
            outlier["category"] = "Unknown"
            outlier["title_variant_1"] = ""
            outlier["title_variant_2"] = ""
            outlier["title_variant_3"] = ""

    # Step 4: Create Google Sheet
    print("\n📄 Creating Google Sheet...")
    creds = get_credentials()
    gc = gspread.authorize(creds)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    sheet_title = f"Cross-Niche Outliers v2 - {timestamp}"
    spreadsheet = gc.create(sheet_title)
    worksheet = spreadsheet.sheet1

    # Headers (with title variant columns and transcript)
    headers = [
        "Cross-Niche Score", "Outlier Score (w/ Recency)", "Raw Outlier Score", "Days Old",
        "Category", "Title", "Video Link", "View Count", "Duration (min)",
        "Channel Name", "Channel Avg Views", "Thumbnail", "Summary",
        "Title Variant 1", "Title Variant 2", "Title Variant 3",
        "Raw Transcript", "Publish Date", "Source"
    ]

    # Prepare rows
    rows = [headers]
    for o in outliers:
        rows.append([
            o["cross_niche_score"],
            o["outlier_score"],
            o.get("raw_outlier_score", o["outlier_score"]),
            o.get("days_old", "N/A"),
            o.get("category", "Unknown"),
            o["title"],
            o["url"],
            o["view_count"],
            round(o.get("duration", 0) / 60, 1),  # Convert to minutes
            o["channel_name"],
            o["channel_avg_views"],
            f'=IMAGE("{o["thumbnail_url"]}")',
            o.get("summary", ""),
            o.get("title_variant_1", ""),
            o.get("title_variant_2", ""),
            o.get("title_variant_3", ""),
            o.get("transcript", ""),  # Raw transcript
            o["date"],
            o.get("source", "")
        ])

    worksheet.update(range_name='A1', values=rows, value_input_option='USER_ENTERED')

    print(f"\n✅ Done! Created sheet with {len(outliers)} cross-niche outliers")
    print(f"   Each outlier has 3 title variants adapted for {USER_CHANNEL_NICHE}")
    print(f"   📊 Sheet URL: {spreadsheet.url}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
