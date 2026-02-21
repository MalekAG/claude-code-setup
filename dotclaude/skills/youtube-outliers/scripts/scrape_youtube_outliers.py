#!/usr/bin/env python3
"""
Scrape YouTube for outlier videos using yt-dlp (FAST), calculate scores, and summarize.
"""

import os
import sys
import json
import time
import datetime
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from apify_client import ApifyClient
from anthropic import Anthropic
import gspread
from google.oauth2.credentials import Credentials
from google.oauth2.service_account import Credentials as ServiceAccountCredentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# Load environment variables
load_dotenv()

# Configuration
KEYWORDS = [
    "agentic workflows",
    "AI agents",
    "agent framework",
    "multi-agent systems",
    "AI automation agents",
    "LangGraph",
    "CrewAI",
    "AutoGPT"
]
MAX_VIDEOS_PER_KEYWORD = 30  # Balanced depth
DAYS_BACK = 7  # Last week

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
        result = subprocess.run(
            command, 
            capture_output=True, 
            text=True, 
            check=True
        )
        # yt-dlp outputs one JSON object per line
        items = []
        for line in result.stdout.strip().split('\n'):
            if line:
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return items
    except subprocess.CalledProcessError as e:
        # print(f"yt-dlp error: {e.stderr}")
        return []

def scrape_keyword(keyword):
    """Scrape a single keyword using yt-dlp."""
    print(f"  - Searching for: {keyword}")
    # Remove --flat-playlist to ensure we get upload_date and view_count
    # Use --get-id and --get-url to get proper video IDs
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
        # Filter by date (upload_date is YYYYMMDD)
        upload_date = item.get("upload_date")
        
        # Debug print if date is missing
        if not upload_date:
             # print(f"    Skipping video {item.get('id')} - No upload_date")
             continue
             
        if upload_date < cutoff_date:
            continue
        
        # Get the video ID - this is the actual YouTube video ID
        video_id = item.get("id")
        
        # Construct proper YouTube URL
        youtube_url = f"https://www.youtube.com/watch?v={video_id}" if video_id else item.get("webpage_url")
        
        video_data = {
            "title": item.get("title"),
            "url": youtube_url,  # Use proper YouTube URL
            "view_count": item.get("view_count"),
            "channel_name": item.get("uploader") or item.get("channel"),
            "channel_url": item.get("uploader_url") or item.get("channel_url"),
            "thumbnail_url": item.get("thumbnail"), 
            "date": upload_date,
            "video_id": video_id  # Use the actual YouTube video ID
        }
        
        videos.append(video_data)
        
    return videos

def get_channel_average(channel_url):
    """Get average view count for a channel using yt-dlp."""
    if not channel_url:
        return 0
        
    # Get last 5 videos
    cmd = [
        "yt-dlp", 
        channel_url, 
        "--dump-json", 
        "--playlist-end", "5", 
        "--flat-playlist",
        "--skip-download"
    ]
    
    items = run_ytdlp(cmd)
    views = [int(item.get("view_count")) for item in items if item.get("view_count") is not None]
    
    if not views:
        return 0
        
    return sum(views) / len(views)

def fetch_transcript(video_id, apify_client):
    """Fetch transcript using Apify transcript scraper (karamelo/youtube-transcripts)."""
    if not video_id:
        return None

    try:
        # Build YouTube URL from video ID
        video_url = f"https://www.youtube.com/watch?v={video_id}"

        # Use karamelo/youtube-transcripts actor
        run_input = {
            "urls": [video_url]
        }

        run = apify_client.actor("karamelo/youtube-transcripts").call(run_input=run_input, timeout_secs=120)

        # Get the transcript from dataset
        dataset_items = list(apify_client.dataset(run["defaultDatasetId"]).iterate_items())

        if dataset_items and len(dataset_items) > 0:
            # Transcript is in the captions field as an array
            transcript_data = dataset_items[0]
            captions = transcript_data.get("captions", [])

            if captions and isinstance(captions, list):
                # Join all caption lines into a single text
                return " ".join(captions)

        return None
    except Exception as e:
        print(f"      Apify transcript error for {video_id}: {str(e)[:100]}")
        return None

def summarize_transcript(text):
    """Summarize transcript using Anthropic (Claude)."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return "Error: No Anthropic API Key"
    client = Anthropic(api_key=api_key)
    prompt = f"""
    Analyze this YouTube video transcript and provide a summary for a content creator.

    Transcript: {text[:100000]}

    Output Format (plain text, no markdown):

    1. High-Level Overview: Write 2-3 sentences summarizing what the video is about and why it's resonating with viewers.

    2. Section-by-Section Summary: Break down the video's content into distinct sections with clear transitions. For each section, describe what was covered.

    Do not use any markdown formatting (no asterisks, no bullet points, no headers with #). Just plain text with numbered sections.
    """
    try:
        message = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=1000,
            temperature=0.7,
            system="You are an expert YouTube strategist.",
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text
    except Exception as e:
        return f"Error summarizing: {e}"

def extract_video_id(url):
    """Extract YouTube video ID from various URL formats."""
    if not url:
        return None
    
    # Handle different YouTube URL formats
    if "youtu.be/" in url:
        return url.split("youtu.be/")[1].split("?")[0].split("&")[0]
    elif "watch?v=" in url:
        return url.split("v=")[1].split("&")[0]
    elif "/embed/" in url:
        return url.split("/embed/")[1].split("?")[0]
    else:
        # If it's already just an ID
        return url

def process_outlier_content(video, apify_client):
    """Fetch transcript and summarize."""
    print(f"    🚀 Processing outlier: {video['title'][:30]}...")
    
    # Try to extract video ID from URL if video_id isn't already set properly
    video_id = video.get("video_id")
    if not video_id:
        video_id = extract_video_id(video.get("url"))
    
    print(f"       Video ID: {video_id}")
    transcript = fetch_transcript(video_id, apify_client)
    if transcript:
        video["summary"] = summarize_transcript(transcript)
    else:
        video["summary"] = "No transcript available."
    return video

def main():
    # 1. Setup
    apify_token = os.getenv("APIFY_API_TOKEN")
    if not apify_token:
        print("Error: APIFY_API_TOKEN not found.")
        sys.exit(1)
    
    apify_client = ApifyClient(apify_token)
    
    # 2. Scrape Videos (Parallel)
    print(f"Searching for videos (last {DAYS_BACK} days)...")
    all_videos = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(scrape_keyword, k) for k in KEYWORDS]
        for future in as_completed(futures):
            all_videos.extend(future.result())
            
    unique_videos = {v['video_id']: v for v in all_videos if v.get('video_id')}.values()
    videos = list(unique_videos)
    print(f"Found {len(videos)} unique videos.")
    
    if not videos:
        return

    # 2. Get Channel Stats (Parallel)
    unique_channels = list(set(v.get("channel_url") for v in videos if v.get("channel_url")))
    print(f"Fetching stats for {len(unique_channels)} channels...")
    
    channel_avgs = {}
    with ThreadPoolExecutor(max_workers=20) as executor:
        future_to_url = {executor.submit(get_channel_average, url): url for url in unique_channels}
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            channel_avgs[url] = future.result()

    # 3. Calculate Scores
    outliers = []
    for video in videos:
        c_url = video.get("channel_url")
        v_count = video.get("view_count")
        
        if not v_count or not c_url or c_url not in channel_avgs:
            continue
            
        avg = channel_avgs[c_url]
        if avg == 0:
            score = 0
        else:
            score = v_count / avg
            
        video["outlier_score"] = round(score, 2)
        video["channel_avg"] = int(avg)

        # Collect all videos with scores (we'll take top 10)
        outliers.append(video)

    # 4. Process Top 10 Outliers
    if outliers:
        # Sort by score and take top 10
        outliers.sort(key=lambda x: x["outlier_score"], reverse=True)
        top_outliers = outliers[:10]

        print(f"Summarizing top {len(top_outliers)} outliers...")
        final_results = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(process_outlier_content, v, apify_client) for v in top_outliers]
            for future in as_completed(futures):
                final_results.append(future.result())
    else:
        final_results = []
        print("No outliers found.")

    if not final_results:
        return

    final_results.sort(key=lambda x: x["outlier_score"], reverse=True)

    # 5. Save to Sheet
    print(f"Saving {len(final_results)} outliers to Sheet...")
    creds = get_credentials()
    if not creds:
        print("Error: Google Auth failed.")
        return
    gc = gspread.authorize(creds)
    title = f"YouTube Outliers {datetime.datetime.now().strftime('%Y-%m-%d')}"
    try:
        sh = gc.create(title)
        ws = sh.get_worksheet(0)
        ws.append_row(["Outlier Score", "Title", "Video Link", "View Count", "Channel Name", "Channel Avg", "Thumbnail", "Summary", "Publish Date"])
        rows = []
        for v in final_results:
            thumb = f'=IMAGE("{v.get("thumbnail_url")}")'
            rows.append([v.get("outlier_score"), v.get("title"), v.get("url"), v.get("view_count"), v.get("channel_name"), v.get("channel_avg"), thumb, v.get("summary"), v.get("date")])
        ws.append_rows(rows, value_input_option='USER_ENTERED')
        print(f"Success! {sh.url}")
    except Exception as e:
        print(f"Sheet error: {e}")

if __name__ == "__main__":
    main()
