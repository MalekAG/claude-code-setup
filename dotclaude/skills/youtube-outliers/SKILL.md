---
name: youtube-outliers
description: Find viral YouTube videos in your niche for competitive intelligence. Use when user asks to find YouTube outliers, monitor competitors, or track viral videos.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

# YouTube Outlier Detection

## Goal
Find high-performing videos in your niche for competitive intelligence and content inspiration.

## Scripts
- `./scripts/scrape_youtube_outliers.py` - Scrape and score outliers
- `./scripts/update_transcripts.py` - Fetch transcripts for existing outliers

## Usage

```bash
# Default run
python3 ./scripts/scrape_youtube_outliers.py

# Custom parameters
python3 ./scripts/scrape_youtube_outliers.py \
  --keywords "AI automation,AI agents" \
  --days 30 \
  --min_score 1.5 \
  --limit 50
```

## How It Works
1. Searches YouTube for keywords
2. Calculates outlier score (views / channel average)
3. Applies recency boost
4. Fetches transcripts
5. Generates Claude summaries
6. Saves to Google Sheet

## Output
Google Sheet with:
- Outlier Score, Views, Duration
- Title, Video Link, Channel
- Thumbnail, Summary, Transcript
- Publish Date

## vs Cross-Niche Outliers
- **youtube_outliers**: Your core niche (daily monitoring)
- **cross-niche-outliers**: Adjacent niches (weekly inspiration)

## Environment
```
APIFY_API_TOKEN=your_token
ANTHROPIC_API_KEY=your_key
```
