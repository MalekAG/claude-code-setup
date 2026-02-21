#!/usr/bin/env python3
"""
Fetch transcripts for existing YouTube outliers and update the Google Sheet.
"""

import os
import sys
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from apify_client import ApifyClient
from anthropic import Anthropic
import gspread
from google.oauth2.credentials import Credentials
from google.oauth2.service_account import Credentials as ServiceAccountCredentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

load_dotenv()

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
    elif "youtube.com/v/" in url:
        return url.split("/v/")[1].split("?")[0]
    else:
        # If URL contains googlevideo or manifest, try to extract from query params
        if "youtube.com" in url or "googlevideo.com" in url:
            # Try to find id in path
            parts = url.split("/")
            for i, part in enumerate(parts):
                if part == "id" and i + 1 < len(parts):
                    return parts[i + 1]
        # Otherwise assume it's already an ID
        return url.split("?")[0].split("&")[0]

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

def process_video(row_index, video_data, apify_client):
    """Process a single video to get transcript and summary."""
    title = video_data.get("Title", "")
    video_link = video_data.get("Video Link", "")

    print(f"  {row_index}. Processing: {title[:40]}...")

    video_id = extract_video_id(video_link)
    print(f"     Extracted ID: {video_id}")

    transcript = fetch_transcript(video_id, apify_client)
    if transcript:
        summary = summarize_transcript(transcript)
        return (row_index, summary)
    else:
        return (row_index, "No transcript available.")

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 update_transcripts.py <sheet_id>")
        print("Example: python3 update_transcripts.py 1na3np_ofa1aSuYJ0mXaX280ydTqVJXZKaNS2qgGvB6I")
        sys.exit(1)

    sheet_id = sys.argv[1]

    # 1. Setup Apify
    apify_token = os.getenv("APIFY_API_TOKEN")
    if not apify_token:
        print("Error: APIFY_API_TOKEN not found.")
        sys.exit(1)

    apify_client = ApifyClient(apify_token)

    # 2. Connect to sheet
    print("Connecting to Google Sheet...")
    creds = get_credentials()
    if not creds:
        print("Error: Could not authenticate with Google.")
        sys.exit(1)

    gc = gspread.authorize(creds)
    sh = gc.open_by_key(sheet_id)
    ws = sh.get_worksheet(0)
    
    # 2. Read all data
    print("Reading sheet data...")
    all_values = ws.get_all_values()
    headers = all_values[0]
    
    # Find column indices
    try:
        summary_col_idx = headers.index("Summary") + 1  # +1 for 1-indexed
        title_col_idx = headers.index("Title") + 1
        video_link_col_idx = headers.index("Video Link") + 1
    except ValueError as e:
        print(f"Error: Required column not found: {e}")
        sys.exit(1)
    
    # 3. Process videos in parallel
    print(f"\nProcessing {len(all_values) - 1} videos...")
    updates = []

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = []
        for i, row in enumerate(all_values[1:], start=2):  # Skip header, start at row 2
            video_data = {
                "Title": row[title_col_idx - 1] if len(row) > title_col_idx - 1 else "",
                "Video Link": row[video_link_col_idx - 1] if len(row) > video_link_col_idx - 1 else ""
            }
            futures.append(executor.submit(process_video, i, video_data, apify_client))

        for future in as_completed(futures):
            row_idx, summary = future.result()
            updates.append((row_idx, summary))
    
    # 4. Update sheet in batch
    print(f"\nUpdating {len(updates)} summaries...")
    batch_data = []
    for row_idx, summary in sorted(updates):
        cell_range = f"{chr(64 + summary_col_idx)}{row_idx}"
        batch_data.append({
            'range': cell_range,
            'values': [[summary]]
        })
    
    if batch_data:
        ws.batch_update(batch_data, value_input_option='USER_ENTERED')
        print(f"✅ Successfully updated {len(batch_data)} summaries!")
        print(f"   Sheet: https://docs.google.com/spreadsheets/d/{sheet_id}")
    else:
        print("No updates to make.")

if __name__ == "__main__":
    main()
