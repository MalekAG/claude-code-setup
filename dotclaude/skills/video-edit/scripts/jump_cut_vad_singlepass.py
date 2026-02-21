#!/usr/bin/env python3
"""
Jump Cut Editor - Single Pass Version

Uses FFmpeg trim+concat filter for single-pass extraction.
Reads the input file once, applies trim filters to extract segments,
then concatenates them in a single pipeline.

Much faster than segment-by-segment approach for large files since
it avoids repeated file seeking overhead.
"""

import subprocess
import tempfile
import os
import argparse
import time
from pathlib import Path

# Video encoding settings - H.265/HEVC at 17Mbps, 30fps
HARDWARE_ENCODER = "hevc_videotoolbox"
SOFTWARE_ENCODER = "libx265"
HARDWARE_BITRATE = "17M"
SOFTWARE_CRF = "18"
TARGET_FPS = 30

# Cache for hardware encoder availability
_hardware_encoder_available = None


def check_hardware_encoder_available() -> bool:
    """Check if hevc_videotoolbox hardware encoder is available."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=5
        )
        return "hevc_videotoolbox" in result.stdout
    except Exception:
        return False


def get_cached_encoder_args() -> list[str]:
    """Get encoder args with cached hardware availability check."""
    global _hardware_encoder_available
    if _hardware_encoder_available is None:
        _hardware_encoder_available = check_hardware_encoder_available()
        if _hardware_encoder_available:
            print(f"🚀 Hardware encoding enabled (hevc_videotoolbox)")
        else:
            print(f"💻 Using software encoding (libx265)")

    if _hardware_encoder_available:
        return ["-c:v", HARDWARE_ENCODER, "-b:v", HARDWARE_BITRATE, "-r", str(TARGET_FPS), "-tag:v", "hvc1"]
    else:
        return ["-c:v", SOFTWARE_ENCODER, "-preset", "fast", "-crf", SOFTWARE_CRF, "-r", str(TARGET_FPS), "-tag:v", "hvc1"]


def extract_audio(input_path: str, output_path: str, sample_rate: int = 16000):
    """Extract audio from video as WAV for VAD processing."""
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-vn", "-ar", str(sample_rate), "-ac", "1",
        "-acodec", "pcm_s16le",
        "-loglevel", "error", output_path
    ]
    subprocess.run(cmd, capture_output=True, check=True)


def get_speech_timestamps_silero(audio_path: str, min_speech_duration: float = 0.25, min_silence_duration: float = 0.5):
    """Use Silero VAD to detect speech segments."""
    import torch

    model, utils = torch.hub.load(
        repo_or_dir='snakers4/silero-vad',
        model='silero_vad',
        force_reload=False,
        trust_repo=True
    )

    (get_speech_timestamps, save_audio, read_audio, VADIterator, collect_chunks) = utils

    SAMPLE_RATE = 16000
    wav = read_audio(audio_path, sampling_rate=SAMPLE_RATE)

    speech_timestamps = get_speech_timestamps(
        wav,
        model,
        sampling_rate=SAMPLE_RATE,
        threshold=0.5,
        min_speech_duration_ms=int(min_speech_duration * 1000),
        min_silence_duration_ms=int(min_silence_duration * 1000),
        speech_pad_ms=100,
    )

    segments = []
    for ts in speech_timestamps:
        start_sec = ts['start'] / SAMPLE_RATE
        end_sec = ts['end'] / SAMPLE_RATE
        segments.append((start_sec, end_sec))

    return segments


def merge_close_segments(segments: list, max_gap: float) -> list:
    """Merge segments that are very close together."""
    if not segments:
        return []

    merged = [segments[0]]
    for start, end in segments[1:]:
        prev_start, prev_end = merged[-1]
        if start - prev_end <= max_gap:
            merged[-1] = (prev_start, end)
        else:
            merged.append((start, end))

    return merged


def add_padding(segments: list, padding_s: float, duration: float) -> list:
    """Add padding around segments and merge overlaps."""
    if not segments:
        return []

    padded = []
    for start, end in segments:
        new_start = max(0, start - padding_s)
        new_end = min(duration, end + padding_s)
        padded.append((new_start, new_end))

    merged = [padded[0]]
    for start, end in padded[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))

    return merged


def get_duration(input_path: str) -> float:
    """Get video duration in seconds."""
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", input_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return float(result.stdout.strip())


def build_trim_concat_filter(segments: list) -> str:
    """
    Build FFmpeg trim+concat filter for multiple segments.

    This approach is more reliable than select filter for many segments.
    Each segment is trimmed independently, then all are concatenated.

    Args:
        segments: List of (start, end) tuples

    Returns:
        FFmpeg filter_complex string
    """
    n = len(segments)
    filter_parts = []

    # Video trim filters
    for i, (start, end) in enumerate(segments):
        filter_parts.append(
            f"[0:v]trim=start={start:.6f}:end={end:.6f},setpts=PTS-STARTPTS[v{i}]"
        )

    # Audio trim filters
    for i, (start, end) in enumerate(segments):
        filter_parts.append(
            f"[0:a]atrim=start={start:.6f}:end={end:.6f},asetpts=PTS-STARTPTS[a{i}]"
        )

    # Build concat input list: [v0][a0][v1][a1]...
    concat_inputs = "".join(f"[v{i}][a{i}]" for i in range(n))

    # Concat filter
    filter_parts.append(f"{concat_inputs}concat=n={n}:v=1:a=1[outv][outa]")

    return ";".join(filter_parts)


def concatenate_singlepass(input_path: str, segments: list, output_path: str):
    """
    Single-pass concatenation using FFmpeg trim+concat filter.

    Reads the input once, applies trim filters to extract each segment,
    then concatenates them in a single encoding pass.

    This is more reliable than the select filter approach and works
    correctly with any number of segments.
    """
    print(f"⚡ Single-pass processing {len(segments)} segments...")
    start_time = time.time()

    # Get encoder settings
    encoder_args = get_cached_encoder_args()

    # Build the trim+concat filter
    filter_complex = build_trim_concat_filter(segments)

    # For very long filter expressions, use a filter script file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(filter_complex)
        filter_script_path = f.name

    try:
        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-filter_complex_script", filter_script_path,
            "-map", "[outv]", "-map", "[outa]",
        ]
        cmd.extend(encoder_args)
        cmd.extend([
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            "-loglevel", "error",
            output_path
        ])

        print(f"   Running FFmpeg trim+concat...")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            print(f"   FFmpeg error: {result.stderr[:1000]}")
            return False

        elapsed = time.time() - start_time
        print(f"   Done in {elapsed:.1f}s!")
        return True
    finally:
        # Clean up filter script
        if os.path.exists(filter_script_path):
            os.remove(filter_script_path)


def main():
    parser = argparse.ArgumentParser(description="Jump cut editor - single pass version (trim+concat)")
    parser.add_argument("input", help="Input video file")
    parser.add_argument("output", help="Output video file")
    parser.add_argument("--min-silence", type=float, default=0.5,
                        help="Minimum silence duration to cut (default: 0.5s)")
    parser.add_argument("--min-speech", type=float, default=0.25,
                        help="Minimum speech duration to keep (default: 0.25s)")
    parser.add_argument("--padding", type=int, default=100,
                        help="Padding around speech in ms (default: 100)")
    parser.add_argument("--merge-gap", type=float, default=0.3,
                        help="Merge segments closer than this (default: 0.3s)")
    parser.add_argument("--keep-start", action="store_true", default=True,
                        help="Always start from 0:00 (default: True)")
    parser.add_argument("--no-keep-start", action="store_false", dest="keep_start")

    args = parser.parse_args()

    input_path = args.input
    output_path = args.output

    print(f"🎬 Jump Cut Editor (Single-Pass, trim+concat)")
    print(f"   Input: {input_path}")
    print(f"   Output: {output_path}")
    print()

    overall_start = time.time()

    duration = get_duration(input_path)
    print(f"📏 Video duration: {duration:.2f}s ({duration/60:.1f} min)")

    # Extract audio for VAD
    print(f"🎵 Extracting audio...")
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        audio_path = tmp.name

    try:
        extract_audio(input_path, audio_path)

        print(f"🎯 Running Silero VAD...")
        speech_segments = get_speech_timestamps_silero(
            audio_path,
            min_speech_duration=args.min_speech,
            min_silence_duration=args.min_silence
        )
        print(f"   Found {len(speech_segments)} speech segments")

        # Debug: show first few segments
        for i, (start, end) in enumerate(speech_segments[:5]):
            print(f"     {i+1}. {start:.2f}s - {end:.2f}s ({end-start:.2f}s)")
        if len(speech_segments) > 5:
            print(f"     ... and {len(speech_segments) - 5} more")

    finally:
        if os.path.exists(audio_path):
            os.remove(audio_path)

    if not speech_segments:
        print("⚠️  No speech detected!")
        return

    # Merge close segments
    speech_segments = merge_close_segments(speech_segments, args.merge_gap)
    print(f"📎 After merging: {len(speech_segments)} segments")

    # Add padding
    padding_s = args.padding / 1000
    speech_segments = add_padding(speech_segments, padding_s, duration)
    print(f"🔲 After padding: {len(speech_segments)} segments")

    # Keep start
    if args.keep_start and speech_segments and speech_segments[0][0] > 0:
        first_start, first_end = speech_segments[0]
        speech_segments[0] = (0.0, first_end)
        print(f"📌 Extended first segment to start at 0:00")

    # Calculate expected output duration
    total_speech = sum(end - start for start, end in speech_segments)
    print(f"📊 Expected output: {total_speech:.1f}s ({total_speech/60:.1f} min)")
    print()

    # Single-pass concatenation using trim+concat
    success = concatenate_singlepass(input_path, speech_segments, output_path)

    if success:
        new_duration = get_duration(output_path)
        removed = duration - new_duration
        overall_time = time.time() - overall_start

        print()
        print(f"📊 Stats:")
        print(f"   Original: {duration:.2f}s ({duration/60:.1f} min)")
        print(f"   New: {new_duration:.2f}s ({new_duration/60:.1f} min)")
        print(f"   Removed: {removed:.2f}s ({100*removed/duration:.1f}%)")
        print(f"   ⚡ Total processing time: {overall_time:.1f}s")


if __name__ == "__main__":
    main()
