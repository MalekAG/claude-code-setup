#!/usr/bin/env python3
"""
Merge classified chunk files into a single labels.json for bulk label application.

Usage:
    python3 .claude/skills/gmail-label/scripts/gmail_label_merge.py \
        --input-dir .tmp/chunks --output .tmp/labels.json
"""

import os
import sys
import json
import argparse
import glob


def main():
    parser = argparse.ArgumentParser(description="Merge classified chunks into labels.json")
    parser.add_argument("--input-dir", "-i", required=True, help="Directory with classified_*.json files")
    parser.add_argument("--output", "-o", required=True, help="Output merged labels JSON file")
    args = parser.parse_args()

    merged = {
        "Action Required": [],
        "Waiting On": [],
        "Reference": []
    }

    pattern = os.path.join(args.input_dir, "classified_*.json")
    files = sorted(glob.glob(pattern))

    if not files:
        print(f"Error: No classified_*.json files found in {args.input_dir}", file=sys.stderr)
        return 1

    for filepath in files:
        try:
            with open(filepath, "r") as f:
                chunk = json.load(f)
            for label in merged:
                merged[label].extend(chunk.get(label, []))
            print(f"  Merged {filepath}: {sum(len(v) for v in chunk.values())} emails")
        except (json.JSONDecodeError, KeyError) as e:
            print(f"  Warning: Failed to parse {filepath}: {e}", file=sys.stderr)

    total = sum(len(ids) for ids in merged.values())
    print(f"\nMerged total: {total} emails")
    for label, ids in merged.items():
        if ids:
            print(f"  {label}: {len(ids)}")

    with open(args.output, "w") as f:
        json.dump(merged, f, indent=2)

    print(f"\nWritten to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
