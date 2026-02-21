#!/usr/bin/env python3
"""
Analyze face directions in reference photos using MediaPipe.

This script:
1. Loads photos from .tmp/reference_photos/raw/
2. Analyzes face pose (yaw/pitch) using MediaPipe
3. Renames and moves to .tmp/reference_photos/ with direction in filename

Naming convention: nick_yaw{L/R}{degrees}_pitch{U/D}{degrees}.jpg
Examples:
  - nick_yawL30_pitchU10.jpg  (looking 30° left, 10° up)
  - nick_yawR45_pitch0.jpg    (looking 45° right, level)
  - nick_yaw0_pitch0.jpg      (dead center)

Usage:
    python analyze_face_directions.py              # Process all in raw/
    python analyze_face_directions.py --preview    # Show analysis without renaming
    python analyze_face_directions.py --single photo.jpg  # Analyze single photo
"""

import argparse
import math
import shutil
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from PIL import Image

# Paths
BASE_DIR = Path(__file__).parent.parent / ".tmp" / "reference_photos"
RAW_DIR = BASE_DIR / "raw"
OUTPUT_DIR = BASE_DIR

# MediaPipe Face Mesh
mp_face_mesh = mp.solutions.face_mesh


def get_face_pose(image_path: Path) -> tuple[float, float] | None:
    """
    Extract yaw and pitch angles from a face image using MediaPipe.

    Returns:
        (yaw, pitch) in degrees, or None if no face detected.
        Yaw: negative = looking left, positive = looking right
        Pitch: negative = looking down, positive = looking up
    """
    # Load image
    img = cv2.imread(str(image_path))
    if img is None:
        print(f"  Could not load: {image_path}")
        return None

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
            print(f"  No face detected: {image_path.name}")
            return None

        landmarks = results.multi_face_landmarks[0].landmark

        # Key landmarks for pose estimation
        # Nose tip: 1, Chin: 152, Left eye outer: 33, Right eye outer: 263
        # Left mouth corner: 61, Right mouth corner: 291

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
            print(f"  Pose estimation failed: {image_path.name}")
            return None

        # Convert rotation vector to rotation matrix
        rotation_mat, _ = cv2.Rodrigues(rotation_vec)

        # Get Euler angles
        proj_matrix = np.hstack((rotation_mat, translation_vec))
        _, _, _, _, _, _, euler_angles = cv2.decomposeProjectionMatrix(proj_matrix)

        pitch = euler_angles[0][0]  # Up/down
        yaw = euler_angles[1][0]    # Left/right
        # roll = euler_angles[2][0]  # Tilt (not used)

        # Clamp extreme values (MediaPipe can be noisy at edges)
        yaw = max(-90, min(90, yaw))
        pitch = max(-45, min(45, pitch))

        return (yaw, pitch)


def format_angle(value: float, pos_char: str, neg_char: str) -> str:
    """Format angle for filename: L30, R15, U10, D5, or 0."""
    rounded = round(value / 5) * 5  # Round to nearest 5 degrees
    if abs(rounded) < 3:
        return "0"
    elif rounded > 0:
        return f"{pos_char}{abs(int(rounded))}"
    else:
        return f"{neg_char}{abs(int(rounded))}"


def generate_filename(yaw: float, pitch: float, index: int = 0) -> str:
    """Generate filename from yaw/pitch angles."""
    yaw_str = format_angle(yaw, "R", "L")
    pitch_str = format_angle(pitch, "U", "D")

    base = f"nick_yaw{yaw_str}_pitch{pitch_str}"
    if index > 0:
        base += f"_{index}"
    return base + ".jpg"


def analyze_directory(preview_only: bool = False) -> dict:
    """Analyze all photos in raw directory."""
    if not RAW_DIR.exists():
        RAW_DIR.mkdir(parents=True)
        print(f"Created {RAW_DIR}")
        print("Add reference photos to this directory and run again.")
        return {}

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    extensions = {".jpg", ".jpeg", ".png", ".webp"}
    photos = sorted([
        f for f in RAW_DIR.iterdir()
        if f.suffix.lower() in extensions
    ])

    if not photos:
        print(f"No photos found in {RAW_DIR}")
        return {}

    print(f"Analyzing {len(photos)} photos...\n")

    results = {}
    used_names = set()

    for photo in photos:
        print(f"Processing: {photo.name}")
        pose = get_face_pose(photo)

        if pose is None:
            results[photo.name] = {"error": "No face detected"}
            continue

        yaw, pitch = pose

        # Generate unique filename
        index = 0
        new_name = generate_filename(yaw, pitch, index)
        while new_name in used_names:
            index += 1
            new_name = generate_filename(yaw, pitch, index)
        used_names.add(new_name)

        results[photo.name] = {
            "yaw": round(yaw, 1),
            "pitch": round(pitch, 1),
            "new_name": new_name,
        }

        print(f"  Yaw: {yaw:+.1f}° | Pitch: {pitch:+.1f}° → {new_name}")

        if not preview_only:
            # Copy and rename (preserve original in raw/)
            dest = OUTPUT_DIR / new_name
            shutil.copy2(photo, dest)
            print(f"  Saved: {dest}")

    return results


def analyze_single(image_path: str) -> tuple[float, float] | None:
    """Analyze a single image and return pose."""
    path = Path(image_path)
    if not path.exists():
        print(f"File not found: {path}")
        return None

    pose = get_face_pose(path)
    if pose:
        yaw, pitch = pose
        print(f"Yaw: {yaw:+.1f}° (negative=left, positive=right)")
        print(f"Pitch: {pitch:+.1f}° (negative=down, positive=up)")
        print(f"Suggested name: {generate_filename(yaw, pitch)}")
    return pose


def find_closest_reference(target_yaw: float, target_pitch: float) -> Path | None:
    """
    Find the reference photo with the closest matching pose.

    This is used by the thumbnail recreation script to match
    the target face direction.
    """
    import re

    extensions = {".jpg", ".jpeg", ".png", ".webp"}
    refs = [
        f for f in OUTPUT_DIR.iterdir()
        if f.suffix.lower() in extensions and f.name.startswith("nick_")
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

    if best_match:
        print(f"Best match: {best_match.name} (distance: {best_distance:.1f}°)")

    return best_match


def main():
    parser = argparse.ArgumentParser(
        description="Analyze face directions in reference photos"
    )
    parser.add_argument(
        "--preview", "-p",
        action="store_true",
        help="Preview analysis without renaming files",
    )
    parser.add_argument(
        "--single", "-s",
        type=str,
        help="Analyze a single image file",
    )
    parser.add_argument(
        "--find",
        type=str,
        help="Find closest reference for given yaw,pitch (e.g., '-30,10')",
    )

    args = parser.parse_args()

    if args.single:
        analyze_single(args.single)
    elif args.find:
        try:
            yaw, pitch = map(float, args.find.split(","))
            find_closest_reference(yaw, pitch)
        except ValueError:
            print("Invalid format. Use: --find '-30,10'")
    else:
        analyze_directory(preview_only=args.preview)


if __name__ == "__main__":
    main()
