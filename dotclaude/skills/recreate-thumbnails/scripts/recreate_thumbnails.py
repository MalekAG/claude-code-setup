#!/usr/bin/env python3
"""
Recreate YouTube thumbnails with Your Name's face using Nano Banana Pro.

This script:
1. Takes a YouTube URL or thumbnail image
2. Analyzes face direction in the source thumbnail
3. Finds the best-matching reference photo by face pose
4. Recreates it with Nick's face swapped in
5. Generates 3 variations by default
6. Supports edit passes for refinements

Usage:
    # Basic recreation (analyzes face direction, finds best reference)
    python recreate_thumbnails.py --youtube "https://youtube.com/watch?v=VIDEO_ID"
    python recreate_thumbnails.py --source "path/to/thumbnail.jpg"

    # Edit pass (refine a generated thumbnail)
    python recreate_thumbnails.py --edit "path/to/generated.png" --prompt "change graph to show upward trend"
"""

import argparse
import base64
import io
import math
import os
import re
import sys
import tempfile
from pathlib import Path
from datetime import datetime

import cv2
import mediapipe as mp
import numpy as np
import requests
from dotenv import load_dotenv
from PIL import Image
from google import genai
from google.genai import types

load_dotenv()

# MediaPipe Face Mesh for pose estimation
mp_face_mesh = mp.solutions.face_mesh

# Constants
REFERENCE_PHOTOS_DIR = Path(__file__).parent.parent / ".tmp" / "reference_photos"
OUTPUT_DIR = Path(__file__).parent.parent / ".tmp" / "thumbnails"
API_KEY = os.getenv("NANO_BANANA_API_KEY")

# Nano Banana Pro model for face-consistent image generation
MODEL = "gemini-3-pro-image-preview"

# Image sizes
THUMB_SIZE = (1280, 720)  # Native YouTube thumbnail resolution (16:9)
REF_SIZE = (400, 400)     # Square reference photos


def get_face_pose(image: Image.Image) -> tuple[float, float] | None:
    """
    Extract yaw and pitch angles from a face in a PIL Image using MediaPipe.

    Returns:
        (yaw, pitch) in degrees, or None if no face detected.
        Yaw: negative = looking left, positive = looking right
        Pitch: negative = looking down, positive = looking up
    """
    # Convert PIL to OpenCV format
    img = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    h, w = img.shape[:2]

    with mp_face_mesh.FaceMesh(
        static_image_mode=True,
        max_num_faces=1,
        refine_landmarks=True,
        min_detection_confidence=0.5,
    ) as face_mesh:
        results = face_mesh.process(rgb)

        if not results.multi_face_landmarks:
            return None

        landmarks = results.multi_face_landmarks[0].landmark

        # 3D model points (generic face model)
        model_points = np.array([
            (0.0, 0.0, 0.0),          # Nose tip
            (0.0, -330.0, -65.0),     # Chin
            (-225.0, 170.0, -135.0),  # Left eye outer
            (225.0, 170.0, -135.0),   # Right eye outer
            (-150.0, -150.0, -125.0), # Left mouth corner
            (150.0, -150.0, -125.0),  # Right mouth corner
        ], dtype=np.float64)

        # 2D image points from landmarks
        landmark_indices = [1, 152, 33, 263, 61, 291]
        image_points = np.array([
            (landmarks[i].x * w, landmarks[i].y * h)
            for i in landmark_indices
        ], dtype=np.float64)

        # Camera matrix (approximate)
        focal_length = w
        center = (w / 2, h / 2)
        camera_matrix = np.array([
            [focal_length, 0, center[0]],
            [0, focal_length, center[1]],
            [0, 0, 1],
        ], dtype=np.float64)

        dist_coeffs = np.zeros((4, 1))

        # Solve PnP
        success, rotation_vec, translation_vec = cv2.solvePnP(
            model_points, image_points, camera_matrix, dist_coeffs,
            flags=cv2.SOLVEPNP_ITERATIVE
        )

        if not success:
            return None

        # Convert rotation vector to rotation matrix
        rotation_mat, _ = cv2.Rodrigues(rotation_vec)

        # Get Euler angles
        proj_matrix = np.hstack((rotation_mat, translation_vec))
        _, _, _, _, _, _, euler_angles = cv2.decomposeProjectionMatrix(proj_matrix)

        pitch = float(euler_angles[0][0])
        yaw = float(euler_angles[1][0])

        # Clamp extreme values
        yaw = max(-90, min(90, yaw))
        pitch = max(-45, min(45, pitch))

        return (yaw, pitch)


def find_best_reference(target_yaw: float, target_pitch: float) -> Path | None:
    """
    Find the reference photo with the closest matching face pose.

    Looks for files named like: nick_yawL30_pitchU10.jpg
    """
    extensions = {".jpg", ".jpeg", ".png", ".webp"}
    refs = [
        f for f in REFERENCE_PHOTOS_DIR.iterdir()
        if f.suffix.lower() in extensions and f.name.startswith("nick_yaw")
    ]

    if not refs:
        return None

    # Parse yaw/pitch from filename
    pattern = r"nick_yaw(L|R)?(\d+|0)_pitch(U|D)?(\d+|0)"

    best_match = None
    best_distance = float("inf")

    for ref in refs:
        match = re.match(pattern, ref.stem)
        if not match:
            continue

        yaw_dir, yaw_val, pitch_dir, pitch_val = match.groups()

        # Parse yaw
        yaw = int(yaw_val) if yaw_val != "0" else 0
        if yaw_dir == "L":
            yaw = -yaw

        # Parse pitch
        pitch = int(pitch_val) if pitch_val != "0" else 0
        if pitch_dir == "D":
            pitch = -pitch

        # Euclidean distance in pose space
        distance = math.sqrt((target_yaw - yaw) ** 2 + (target_pitch - pitch) ** 2)

        if distance < best_distance:
            best_distance = distance
            best_match = ref

    return best_match


def extract_video_id(url: str) -> str | None:
    """Extract YouTube video ID from various URL formats."""
    patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})',
        r'youtube\.com/shorts/([a-zA-Z0-9_-]{11})',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def get_youtube_thumbnail(video_id: str) -> Image.Image | None:
    """Download YouTube thumbnail in best available quality."""
    qualities = ['maxresdefault', 'sddefault', 'hqdefault', 'mqdefault']

    for quality in qualities:
        url = f"https://img.youtube.com/vi/{video_id}/{quality}.jpg"
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                img = Image.open(io.BytesIO(response.content))
                # maxresdefault returns a placeholder if not available
                if img.size[0] > 200:
                    print(f"Downloaded thumbnail: {quality} ({img.size})")
                    return img
        except Exception:
            continue

    return None


def download_image(url: str) -> Image.Image:
    """Download image from URL."""
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return Image.open(io.BytesIO(response.content))


def load_reference_photo(path: Path) -> Image.Image | None:
    """Load and resize a single reference photo."""
    try:
        img = Image.open(path)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        img = img.resize(REF_SIZE)
        print(f"Loaded reference: {path.name}")
        return img
    except Exception as e:
        print(f"Warning: Could not load {path}: {e}")
        return None


def load_reference_photos(max_photos: int = 3, specific_path: Path | None = None) -> list[Image.Image]:
    """
    Load Nick's reference photos for face consistency.

    If specific_path is provided, uses that as the primary reference.
    Otherwise loads the first max_photos from the directory.
    """
    photos = []

    if not REFERENCE_PHOTOS_DIR.exists():
        print(f"Warning: Reference photos not found at {REFERENCE_PHOTOS_DIR}")
        return photos

    # If a specific reference was found via direction matching, use it first
    if specific_path and specific_path.exists():
        ref = load_reference_photo(specific_path)
        if ref:
            photos.append(ref)
            # If we only need one, we're done
            if max_photos == 1:
                return photos

    extensions = {".jpg", ".jpeg", ".png", ".webp"}
    photo_files = sorted([
        f for f in REFERENCE_PHOTOS_DIR.iterdir()
        if f.suffix.lower() in extensions and f != specific_path
    ])

    for photo_file in photo_files[:max_photos - len(photos)]:
        ref = load_reference_photo(photo_file)
        if ref:
            photos.append(ref)

    return photos


def recreate_thumbnail(
    source_image: Image.Image,
    reference_photos: list[Image.Image],
    style_variation: str = "purple/teal gradient",
    additional_prompt: str = "",
) -> Image.Image | None:
    """
    Recreate a thumbnail with Nick's face and style variations.

    Args:
        source_image: Original thumbnail to recreate
        reference_photos: Reference photos of Nick for face consistency
        style_variation: Color/style changes to apply
        additional_prompt: Extra instructions

    Returns:
        Generated thumbnail or None if failed
    """
    client = genai.Client(api_key=API_KEY)

    # Resize source for optimal API performance
    thumb = source_image.copy()
    thumb.thumbnail(THUMB_SIZE, Image.Resampling.LANCZOS)

    # Build prompt - direct face swap only
    num_refs = len(reference_photos)
    prompt = f"""IMAGE 1{' and 2' if num_refs > 1 else ''}: Reference photo(s) of Your Name's face.
IMAGE {num_refs + 1}: The thumbnail to edit.

TASK: Replace ONLY the face in the thumbnail with Your Name's exact face from the reference(s).

The output must be a 100% exact duplicate of the thumbnail, except the face is swapped with Nick's face. Keep every single pixel identical outside the face region.

Output in 16:9 format.

{additional_prompt}"""

    # Build content: references first, then source, then prompt
    contents = reference_photos + [thumb, prompt]

    print(f"\nGenerating with {len(reference_photos)} reference photos...")
    print(f"Style variation: {style_variation}")

    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"],
            ),
        )

        # Extract generated image
        if response.candidates and response.candidates[0].content:
            for part in response.candidates[0].content.parts:
                if hasattr(part, 'inline_data') and part.inline_data:
                    data = part.inline_data.data
                    if data:
                        img_bytes = base64.b64decode(data) if isinstance(data, str) else data
                        return Image.open(io.BytesIO(img_bytes))
                elif hasattr(part, 'text') and part.text:
                    print(f"Model note: {part.text[:200]}")

        print("No image in response")
        return None

    except Exception as e:
        print(f"Error: {e}")
        return None


def edit_thumbnail(
    source_image: Image.Image,
    edit_instructions: str,
) -> Image.Image | None:
    """
    Edit an existing thumbnail with high-level instructions.

    This is the "edit pass" - takes a generated thumbnail and refines it
    based on user instructions (e.g., "change the graph to show upward trend").

    Args:
        source_image: The thumbnail to edit
        edit_instructions: What changes to make

    Returns:
        Edited thumbnail or None if failed
    """
    client = genai.Client(api_key=API_KEY)

    # Resize for API
    thumb = source_image.copy()
    thumb.thumbnail(THUMB_SIZE, Image.Resampling.LANCZOS)

    prompt = f"""IMAGE 1: A thumbnail that needs editing.

TASK: Make the following changes to this thumbnail:
{edit_instructions}

Keep everything else exactly the same. Only modify what is explicitly requested.

Output in 16:9 format."""

    print(f"\nEditing with instructions: {edit_instructions[:100]}...")

    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=[thumb, prompt],
            config=types.GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"],
            ),
        )

        # Extract generated image
        if response.candidates and response.candidates[0].content:
            for part in response.candidates[0].content.parts:
                if hasattr(part, 'inline_data') and part.inline_data:
                    data = part.inline_data.data
                    if data:
                        img_bytes = base64.b64decode(data) if isinstance(data, str) else data
                        return Image.open(io.BytesIO(img_bytes))
                elif hasattr(part, 'text') and part.text:
                    print(f"Model note: {part.text[:200]}")

        print("No image in response")
        return None

    except Exception as e:
        print(f"Error: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Recreate YouTube thumbnails with Your Name"
    )
    parser.add_argument(
        "--youtube", "-y",
        type=str,
        help="YouTube video URL to recreate thumbnail from",
    )
    parser.add_argument(
        "--source", "-s",
        type=str,
        help="Source thumbnail URL or file path",
    )
    parser.add_argument(
        "--edit", "-e",
        type=str,
        help="Edit an existing thumbnail (path to image)",
    )
    parser.add_argument(
        "--style",
        type=str,
        default="purple/teal gradient with modern aesthetic",
        help="Style variation to apply (colors, vibe)",
    )
    parser.add_argument(
        "--prompt", "-p",
        type=str,
        default="",
        help="Additional instructions (for recreation or edit)",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        help="Output filename",
    )
    parser.add_argument(
        "--refs",
        type=int,
        default=2,
        help="Number of reference photos to use (1-5)",
    )
    parser.add_argument(
        "--variations", "-n",
        type=int,
        default=3,
        help="Number of variations to generate (default: 3)",
    )
    parser.add_argument(
        "--no-match",
        action="store_true",
        help="Skip face direction matching (use default references)",
    )

    args = parser.parse_args()

    if not API_KEY:
        print("Error: NANO_BANANA_API_KEY not set in .env")
        sys.exit(1)

    # Create date-based output folder (YYYYMMDD)
    date_folder = OUTPUT_DIR / datetime.now().strftime("%Y%m%d")
    date_folder.mkdir(parents=True, exist_ok=True)
    time_stamp = datetime.now().strftime("%H%M%S")

    # === EDIT MODE ===
    if args.edit:
        if not args.prompt:
            print("Error: --edit requires --prompt with edit instructions")
            sys.exit(1)

        print(f"Loading image to edit: {args.edit}")
        edit_image = Image.open(args.edit)
        print(f"Size: {edit_image.size}")

        result = edit_thumbnail(edit_image, args.prompt)

        if result is None:
            print("Edit failed")
            sys.exit(1)

        if args.output:
            output_path = date_folder / args.output
        else:
            output_path = date_folder / f"{time_stamp}_edited.png"

        result.save(output_path)
        print(f"\nSaved: {output_path}")
        print(f"Size: {result.size}")
        return [str(output_path)]

    # === RECREATION MODE ===
    if not args.youtube and not args.source:
        print("Error: Provide --youtube URL, --source image, or --edit image")
        sys.exit(1)

    # Load source thumbnail
    source_image = None

    if args.youtube:
        video_id = extract_video_id(args.youtube)
        if not video_id:
            print(f"Error: Could not extract video ID from {args.youtube}")
            sys.exit(1)
        print(f"Video ID: {video_id}")
        source_image = get_youtube_thumbnail(video_id)
        if not source_image:
            print("Error: Could not download YouTube thumbnail")
            sys.exit(1)
    elif args.source:
        print(f"Loading source: {args.source}")
        if args.source.startswith(("http://", "https://")):
            source_image = download_image(args.source)
        else:
            source_image = Image.open(args.source)

    print(f"Source size: {source_image.size}")

    # Analyze face direction in source thumbnail
    best_reference = None
    if not args.no_match:
        print("\nAnalyzing face direction in source thumbnail...")
        pose = get_face_pose(source_image)
        if pose:
            yaw, pitch = pose
            print(f"Detected pose: yaw={yaw:+.1f}°, pitch={pitch:+.1f}°")

            # Find best matching reference
            best_reference = find_best_reference(yaw, pitch)
            if best_reference:
                print(f"Best matching reference: {best_reference.name}")
            else:
                print("No direction-labeled references found, using defaults")
        else:
            print("No face detected in source, using default references")

    # Load reference photos (prioritizing best match if found)
    reference_photos = load_reference_photos(
        max_photos=args.refs,
        specific_path=best_reference
    )
    if not reference_photos:
        print("Warning: No reference photos found. Results may vary.")

    # Generate multiple variations
    output_paths = []

    for i in range(args.variations):
        print(f"\n--- Variation {i + 1}/{args.variations} ---")

        result = recreate_thumbnail(
            source_image=source_image,
            reference_photos=reference_photos,
            style_variation=args.style,
            additional_prompt=args.prompt,
        )

        if result is None:
            print(f"Failed to generate variation {i + 1}")
            continue

        # Save output
        if args.output and args.variations == 1:
            output_path = date_folder / args.output
        else:
            output_path = date_folder / f"{time_stamp}_{i + 1}.png"

        result.save(output_path)
        output_paths.append(str(output_path))
        print(f"Saved: {output_path}")
        print(f"Size: {result.size}")

    print(f"\n=== Generated {len(output_paths)}/{args.variations} variations ===")
    for path in output_paths:
        print(f"  - {path}")

    return output_paths


if __name__ == "__main__":
    main()
