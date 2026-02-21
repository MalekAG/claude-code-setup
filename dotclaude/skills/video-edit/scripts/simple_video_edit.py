#!/usr/bin/env python3
"""
Simple video editing: FFmpeg silence detection/cutting + metadata generation.

No AI-based silence decisions, no filler detection, no voice commands.
Just procedural silence removal, audio normalization, and Claude-generated metadata.

Usage:
    python3 execution/simple_video_edit.py \
        --video .tmp/my_video.mp4 \
        --title "My Video Title"

    # Local only (no upload)
    python3 execution/simple_video_edit.py \
        --video .tmp/my_video.mp4 \
        --title "Test" \
        --no-upload

Output:
    - Edited video: .tmp/{original_name}_edited.mp4
    - Metadata file: .tmp/{original_name}_metadata.txt
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import anthropic
import requests
from dotenv import load_dotenv

load_dotenv()

# API keys
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
AUPHONIC_API_KEY = os.getenv("AUPHONIC_API_KEY")

# Auphonic config
AUPHONIC_PRESET_UUID = "8YdWMdfF2QXpdZ2mDuUugj"
YOUTUBE_SERVICE_UUID = "FxAiTuHCxgeGTZnzYeQLFd"

# Silence detection defaults
SILENCE_THRESHOLD_DB = -35
SILENCE_MIN_DURATION = 3.0
CUT_BUFFER_SECONDS = 0.15


def get_video_duration(video_path: str) -> float:
    """Get video duration in seconds."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json", video_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


def detect_silence(
    video_path: str,
    threshold_db: float = SILENCE_THRESHOLD_DB,
    min_duration: float = SILENCE_MIN_DURATION
) -> list[tuple[float, float]]:
    """
    Use FFmpeg silencedetect to find silent sections.
    Returns list of (start, end) tuples.
    """
    cmd = [
        "ffmpeg", "-i", video_path,
        "-af", f"silencedetect=noise={threshold_db}dB:d={min_duration}",
        "-f", "null", "-"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    stderr = result.stderr

    silence_starts = re.findall(r"silence_start: ([\d.]+)", stderr)
    silence_ends = re.findall(r"silence_end: ([\d.]+)", stderr)

    silences = []
    for i, start in enumerate(silence_starts):
        if i < len(silence_ends):
            silences.append((float(start), float(silence_ends[i])))
        else:
            silences.append((float(start), None))

    return silences


def calculate_keep_segments(
    silences: list[tuple[float, float]],
    duration: float,
    buffer: float = CUT_BUFFER_SECONDS
) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    """
    Given silent sections, calculate segments to keep (inverse).
    Returns (keep_segments, cuts) where cuts is what was removed.
    """
    if not silences:
        return [(0, duration)], []

    keep_segments = []
    cuts = []
    current_pos = 0.0

    for silence_start, silence_end in silences:
        if silence_end is None:
            silence_end = duration

        # Add buffer for smoother transitions
        adjusted_start = silence_start + buffer
        adjusted_end = silence_end - buffer

        # Only cut if meaningful silence remains after buffering
        if adjusted_end <= adjusted_start:
            continue

        if adjusted_start > current_pos:
            keep_segments.append((current_pos, adjusted_start))

        cuts.append((adjusted_start, adjusted_end))
        current_pos = adjusted_end

    if current_pos < duration:
        keep_segments.append((current_pos, duration))

    return keep_segments, cuts


def remove_silence_and_normalize(
    video_path: str,
    keep_segments: list[tuple[float, float]],
    output_path: str,
    normalize: bool = True
) -> None:
    """
    Use FFmpeg to concatenate non-silent segments with audio normalization.
    """
    if not keep_segments:
        raise ValueError("No segments to keep - video is entirely silent")

    # Build filter complex
    filter_parts = []
    concat_inputs = []

    for i, (start, end) in enumerate(keep_segments):
        filter_parts.append(f"[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS[v{i}];")
        if normalize:
            # Apply highpass + loudnorm to each audio segment
            filter_parts.append(
                f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS,"
                f"highpass=f=80,loudnorm=I=-16:TP=-1.5:LRA=11[a{i}];"
            )
        else:
            filter_parts.append(f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS[a{i}];")
        concat_inputs.append(f"[v{i}][a{i}]")

    filter_complex = "".join(filter_parts)
    filter_complex += "".join(concat_inputs) + f"concat=n={len(keep_segments)}:v=1:a=1[outv][outa]"

    # Use hardware encoding on macOS if available
    encoder = "h264_videotoolbox" if sys.platform == "darwin" else "libx264"

    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", encoder,
        "-b:v", "8M",  # Good quality for videotoolbox
        "-c:a", "aac", "-b:a", "320k",
        output_path
    ]

    # Fallback to libx264 if videotoolbox fails
    print("Processing video with FFmpeg...")
    start_time = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0 and encoder == "h264_videotoolbox":
        print("Hardware encoding failed, falling back to software encoding...")
        cmd[cmd.index("h264_videotoolbox")] = "libx264"
        cmd[cmd.index("-b:v")] = "-crf"
        cmd[cmd.index("8M")] = "18"
        result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"FFmpeg error: {result.stderr}")
        raise RuntimeError("Failed to process video")

    elapsed = time.time() - start_time
    print(f"FFmpeg processing took {elapsed:.1f}s")


def transcribe_video(video_path: str) -> list[dict]:
    """
    Transcribe video using faster-whisper.
    Returns list of word dicts with {word, start, end}.
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("Warning: faster-whisper not installed. Skipping transcription.")
        return []

    print("Transcribing video with Whisper...")
    start_time = time.time()

    model = WhisperModel("base", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(video_path, word_timestamps=True)

    words = []
    for segment in segments:
        if segment.words:
            for w in segment.words:
                words.append({
                    "word": w.word.strip(),
                    "start": w.start,
                    "end": w.end
                })

    elapsed = time.time() - start_time
    print(f"Transcription complete: {len(words)} words in {elapsed:.1f}s")
    return words


def generate_metadata(
    words: list[dict],
    cuts: list[tuple[float, float]],
    duration: float,
    title: str
) -> dict:
    """
    Generate YouTube summary and chapters using Claude.
    Returns dict with {title, summary, chapters}.
    """
    if not words:
        return {
            "title": title,
            "summary": "Video content.",
            "chapters": "00:00:00 Introduction"
        }

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Group words into ~30 second chunks
    chunks = []
    current_chunk = []
    chunk_start = 0.0

    for w in words:
        current_chunk.append(w)
        if current_chunk and w["end"] - chunk_start >= 30:
            chunk_text = " ".join(word["word"] for word in current_chunk)
            chunks.append({"start": chunk_start, "end": w["end"], "text": chunk_text})
            chunk_start = w["end"]
            current_chunk = []

    if current_chunk:
        chunk_text = " ".join(word["word"] for word in current_chunk)
        chunks.append({"start": chunk_start, "end": current_chunk[-1]["end"], "text": chunk_text})

    transcript_with_times = "\n".join(
        f"[{c['start']:.0f}s - {c['end']:.0f}s]: {c['text']}"
        for c in chunks
    )

    prompt = f"""Analyze this video transcript and generate:
1. A summary for the YouTube description
2. YouTube chapters with timestamps

TRANSCRIPT (with timestamps in seconds):
{transcript_with_times}

VIDEO DURATION: {duration:.0f} seconds ({duration/60:.1f} minutes)

Respond in this exact JSON format:
{{
    "summary": "<2-4 sentence summary describing what the video covers. Write in third person ('This video covers...'). Be specific about the content.>",
    "chapters": [
        {{"time": "00:00:00", "title": "Introduction"}},
        {{"time": "00:02:30", "title": "Topic Title Here"}}
    ]
}}

Chapter guidelines:
- Generate 5-15 chapters marking major topic transitions
- First chapter MUST be at 00:00:00
- Chapters should be 1-2+ minutes apart (except intro/outro)
- Concise titles (2-6 words)

Return ONLY the JSON, no other text."""

    print("Generating metadata with Claude...")
    response = client.messages.create(
        model="claude-opus-4-5-20251101",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )

    response_text = response.content[0].text.strip()

    # Parse JSON response
    json_match = re.search(r'\{[\s\S]*\}', response_text)
    if not json_match:
        return {"title": title, "summary": "Video content.", "chapters": "00:00:00 Introduction"}

    try:
        data = json.loads(json_match.group())
        summary = data.get("summary", "Video content.")
        chapters_list = data.get("chapters", [{"time": "00:00:00", "title": "Introduction"}])
    except json.JSONDecodeError:
        return {"title": title, "summary": "Video content.", "chapters": "00:00:00 Introduction"}

    # Adjust timestamps for cuts
    adjusted_chapters = []
    sorted_cuts = sorted(cuts, key=lambda x: x[0]) if cuts else []

    for chapter in chapters_list:
        time_str = chapter.get("time", "00:00:00")
        chapter_title = chapter.get("title", "Chapter")

        # Parse timestamp
        match = re.match(r'^(\d{1,2}):(\d{2}):(\d{2})$', time_str)
        if not match:
            match = re.match(r'^(\d{1,2}):(\d{2})$', time_str)
            if match:
                minutes, seconds = match.groups()
                original_time = int(minutes) * 60 + int(seconds)
            else:
                adjusted_chapters.append(f"{time_str} {chapter_title}")
                continue
        else:
            hours, minutes, seconds = match.groups()
            original_time = int(hours) * 3600 + int(minutes) * 60 + int(seconds)

        # Calculate time removed before this timestamp
        time_removed = 0
        for cut_start, cut_end in sorted_cuts:
            if cut_end <= original_time:
                time_removed += cut_end - cut_start
            elif cut_start < original_time:
                time_removed += original_time - cut_start

        adjusted_time = max(0, original_time - time_removed)

        hours = int(adjusted_time // 3600)
        minutes = int((adjusted_time % 3600) // 60)
        seconds = int(adjusted_time % 60)

        adjusted_chapters.append(f"{hours:02d}:{minutes:02d}:{seconds:02d} {chapter_title}")

    chapters_text = "\n".join(adjusted_chapters) if adjusted_chapters else "00:00:00 Introduction"

    return {
        "title": title,
        "summary": summary,
        "chapters": chapters_text
    }


def save_metadata(metadata: dict, output_path: str) -> None:
    """Save metadata to a text file."""
    content = f"""TITLE:
{metadata['title']}

SUMMARY:
{metadata['summary']}

CHAPTERS:
{metadata['chapters']}
"""
    with open(output_path, "w") as f:
        f.write(content)
    print(f"Metadata saved to: {output_path}")


def build_youtube_description(summary: str, chapters: str) -> str:
    """Build full YouTube description from template with dynamic summary and chapters."""
    return f"""Join Maker School & get automation customer #1 + all my templates ⤵️
https://www.skool.com/makerschool/about?ref=e525fc95e7c346999dcec8e0e870e55d

Summary ⤵️
{summary}

My software, tools, & deals (some give me kickbacks—thank you!)
🚀 Instantly: https://link.youruser.com/instantly-short
📧 Anymailfinder: https://link.youruser.com/amf-short
🤖 Apify: https://console.apify.com/sign-up (30% off with code 30NICKSARAEV)
🧑🏽‍💻 n8n: https://n8n.partnerlinks.io/h372ujv8cw80
📈 Rize: https://link.youruser.com/rize-short (25% off with promo code NICK)

Follow me on other platforms 😈
📸 Instagram: https://www.instagram.com/nick_saraev
🕊️ Twitter/X: https://twitter.com/youruser
🤙 Blog: https://youruser.com

Why watch?
If this is your first view—hi, I'm Nick! TLDR: I spent six years building automated businesses with Make.com (most notably 1SecondCopy, a content company that hit 7 figures). Today a lot of people talk about automation, but I've noticed that very few have practical, real world success making money with it. So this channel is me chiming in and showing you what *real* systems that make *real* revenue look like.

Hopefully I can help you improve your business, and in doing so, the rest of your life 🙏

Like, subscribe, and leave me a comment if you have a specific request! Thanks.

Chapters
{chapters}
"""


def upload_to_auphonic(
    video_path: str,
    title: str,
    description: str | None = None,
    thumbnail_path: str | None = None
) -> dict:
    """Upload video to Auphonic for processing and YouTube upload."""
    headers = {"Authorization": f"Bearer {AUPHONIC_API_KEY}"}

    # Build metadata with description if provided
    metadata = {"title": title}
    if description:
        metadata["summary"] = description  # Auphonic uses 'summary' for YouTube description

    print("Creating Auphonic production...")
    create_resp = requests.post(
        "https://auphonic.com/api/productions.json",
        headers=headers,
        json={
            "preset": AUPHONIC_PRESET_UUID,
            "metadata": metadata,
            "outgoing_services": [{"uuid": YOUTUBE_SERVICE_UUID, "privacy": "private"}],
            "output_files": [{
                "format": "video",
                "outgoing_services": [YOUTUBE_SERVICE_UUID]
            }]
        }
    )
    create_resp.raise_for_status()
    production = create_resp.json()["data"]
    production_uuid = production["uuid"]

    print("Uploading video to Auphonic...")
    with open(video_path, "rb") as f:
        upload_resp = requests.post(
            f"https://auphonic.com/api/production/{production_uuid}/upload.json",
            headers=headers,
            files={"input_file": f}
        )
    upload_resp.raise_for_status()

    if thumbnail_path and os.path.exists(thumbnail_path):
        print("Uploading thumbnail...")
        with open(thumbnail_path, "rb") as f:
            requests.post(
                f"https://auphonic.com/api/production/{production_uuid}/upload.json",
                headers=headers,
                files={"image": f}
            )

    print("Starting Auphonic processing...")
    start_resp = requests.post(
        f"https://auphonic.com/api/production/{production_uuid}/start.json",
        headers=headers
    )
    start_resp.raise_for_status()

    print(f"\nProduction started!")
    print(f"Monitor at: https://auphonic.com/engine/status/{production_uuid}")

    return start_resp.json()["data"]


def main():
    parser = argparse.ArgumentParser(description="Simple video editing with metadata generation")
    parser.add_argument("--video", required=True, help="Path to input video")
    parser.add_argument("--title", required=True, help="YouTube video title")
    parser.add_argument("--thumbnail", help="Path to thumbnail image")
    parser.add_argument("--no-upload", action="store_true", help="Skip Auphonic upload")
    parser.add_argument("--no-normalize", action="store_true", help="Skip audio normalization")
    parser.add_argument("--keep-temp", action="store_true", help="Keep edited video after upload")
    parser.add_argument("--silence-threshold", type=float, default=SILENCE_THRESHOLD_DB,
                        help=f"Silence threshold in dB (default: {SILENCE_THRESHOLD_DB})")
    parser.add_argument("--silence-duration", type=float, default=SILENCE_MIN_DURATION,
                        help=f"Min silence duration in seconds (default: {SILENCE_MIN_DURATION})")
    parser.add_argument("--upload-only", action="store_true",
                        help="Skip editing, just upload the specified video to Auphonic")

    args = parser.parse_args()

    # Validate
    if not os.path.exists(args.video):
        print(f"Error: Video not found: {args.video}")
        sys.exit(1)

    if not args.no_upload and not AUPHONIC_API_KEY:
        print("Error: AUPHONIC_API_KEY not set in .env")
        sys.exit(1)

    if not ANTHROPIC_API_KEY:
        print("Error: ANTHROPIC_API_KEY not set in .env")
        sys.exit(1)

    # Setup paths
    video_path = args.video
    video_name = Path(video_path).stem
    script_dir = Path(__file__).parent.parent
    tmp_dir = script_dir / ".tmp"
    tmp_dir.mkdir(exist_ok=True)

    output_path = str(tmp_dir / f"{video_name}_edited.mp4")
    metadata_path = str(tmp_dir / f"{video_name}_metadata.txt")

    # Upload-only mode: skip editing, just upload
    if args.upload_only:
        print(f"\nUpload-only mode: uploading {video_path} to Auphonic...")
        # Try to load existing metadata if available
        base_name = video_name.replace("_edited", "")
        possible_metadata = str(tmp_dir / f"{base_name}_metadata.txt")
        description = ""
        if os.path.exists(possible_metadata):
            print(f"Loading metadata from: {possible_metadata}")
            with open(possible_metadata, "r") as f:
                content = f.read()
                # Extract summary and chapters for description
                if "SUMMARY:" in content and "CHAPTERS:" in content:
                    summary_start = content.index("SUMMARY:") + len("SUMMARY:")
                    chapters_start = content.index("CHAPTERS:")
                    summary = content[summary_start:chapters_start].strip()
                    chapters = content[chapters_start + len("CHAPTERS:"):].strip()
                    description = f"{summary}\n\n{chapters}"

        upload_to_auphonic(
            video_path,
            args.title,
            description=description,
            thumbnail_path=args.thumbnail
        )
        print("\nDone! Video will upload to YouTube as private draft.")
        return

    # Get video info
    print(f"\nAnalyzing: {video_path}")
    duration = get_video_duration(video_path)
    print(f"Duration: {duration:.1f}s ({duration/60:.1f} min)")

    # Detect silence
    print(f"\nDetecting silence (threshold: {args.silence_threshold}dB, min: {args.silence_duration}s)...")
    silences = detect_silence(video_path, args.silence_threshold, args.silence_duration)

    if silences:
        total_silence = sum((end or duration) - start for start, end in silences)
        print(f"Found {len(silences)} silent sections ({total_silence:.1f}s total)")
    else:
        print("No significant silence detected")

    # Calculate segments
    keep_segments, cuts = calculate_keep_segments(silences, duration)
    kept_duration = sum(end - start for start, end in keep_segments)
    removed = duration - kept_duration
    print(f"Keeping {kept_duration:.1f}s, removing {removed:.1f}s ({removed/duration*100:.1f}%)")

    # Process video
    print(f"\nProcessing video...")
    remove_silence_and_normalize(
        video_path, keep_segments, output_path,
        normalize=not args.no_normalize
    )
    print(f"Edited video: {output_path}")

    # Transcribe for metadata
    print(f"\nGenerating metadata...")
    words = transcribe_video(video_path)

    # Generate and save metadata
    metadata = generate_metadata(words, cuts, kept_duration, args.title)
    save_metadata(metadata, metadata_path)

    # Build YouTube description from template
    youtube_description = build_youtube_description(metadata['summary'], metadata['chapters'])

    # Upload if requested
    if not args.no_upload:
        print(f"\nUploading to Auphonic...")
        try:
            upload_to_auphonic(
                output_path,
                args.title,
                description=youtube_description,
                thumbnail_path=args.thumbnail
            )
            print("\nDone! Video will upload to YouTube as private draft.")
        finally:
            if not args.keep_temp and os.path.exists(output_path):
                os.remove(output_path)
                print("Cleaned up edited video")
    else:
        print(f"\nDone! Edited video at: {output_path}")

    print(f"Metadata at: {metadata_path}")


if __name__ == "__main__":
    main()
