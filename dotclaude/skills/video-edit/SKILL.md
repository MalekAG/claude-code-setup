---
name: video-edit
description: Edit talking-head videos by removing silences with neural VAD and adding 3D swivel teaser transitions. Use when user asks to edit video, remove silences, add jump cuts, or create video teasers.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

# Video Editing

## Goal
Automatically edit talking-head videos: remove silences via neural VAD, add swivel teaser preview.

## Scripts
- `./scripts/jump_cut_vad_singlepass.py` - VAD silence removal
- `./scripts/insert_3d_transition.py` - Swivel teaser insertion
- `./scripts/simple_video_edit.py` - Basic FFmpeg editing

## Quick Start

```bash
# Step 1: Remove silences
python3 ./scripts/jump_cut_vad_singlepass.py input.mp4 .tmp/edited.mp4

# Step 2: Add swivel teaser
python3 ./scripts/insert_3d_transition.py .tmp/edited.mp4 output.mp4 --bg-image .tmp/bg.png

# One-liner
python3 ./scripts/jump_cut_vad_singlepass.py input.mp4 .tmp/edited.mp4 && \
python3 ./scripts/insert_3d_transition.py .tmp/edited.mp4 output.mp4 --bg-image .tmp/bg.png
```

## Step 1: VAD Silence Removal

### How It Works
1. Extracts audio as WAV (16kHz mono)
2. Runs Silero VAD to detect speech segments
3. Merges close segments, adds padding
4. Uses FFmpeg trim+concat to join segments in single pass
5. Hardware encodes with hevc_videotoolbox (H.265, 17Mbps, 30fps)

### CLI Arguments
| Argument | Default | Description |
|----------|---------|-------------|
| `--min-silence` | 0.5 | Min silence duration to cut (seconds) |
| `--min-speech` | 0.25 | Min speech duration to keep (seconds) |
| `--padding` | 100 | Padding around speech (ms) |
| `--merge-gap` | 0.3 | Merge segments closer than this (seconds) |
| `--keep-start` | true | Always start from 0:00 |

## Step 2: Swivel Teaser

### How It Works
1. Extracts frames from later in video (default: 60s onwards)
2. Creates 3D rotating "swivel" animation
3. Splits video: intro, transition, main content
4. Re-encodes and concatenates with audio preserved

### CLI Arguments
| Argument | Default | Description |
|----------|---------|-------------|
| `--insert-at` | 3 | Where to insert teaser (seconds) |
| `--duration` | 5 | Teaser duration (seconds) |
| `--teaser-start` | 60 | Where to sample content from (seconds) |
| `--bg-image` | none | Background image for 3D effect |

## Final Timeline
```
[0-3s intro] [3-8s swivel teaser @ 100x] [8s onwards: edited content]
Audio: Original audio plays continuously
```

## Processing Time (49-min 4K video)
- Step 1 (VAD + encode): ~8 minutes
- Step 2 (swivel teaser): ~3 minutes
- Total: ~11 minutes

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Cuts feel abrupt | `--padding 200` |
| Too much cut | `--min-silence 1.0` |
| Too little cut | `--min-speech 0.1` |
| Won't play in QuickTime | Ensure hvc1 codec tag |
| Swivel has blank frames | Extract 300 frames for 5s teaser |

## Dependencies
```bash
pip install torch  # For Silero VAD
brew install ffmpeg node  # macOS
cd video_effects && npm install  # For 3D rendering
```

## Technical Details
- macOS: Hardware encoding (hevc_videotoolbox) H.265 at 17Mbps
- Fallback: libx265 CRF 18
- Audio: AAC 192kbps
- Uses `hvc1` codec tag for QuickTime compatibility
