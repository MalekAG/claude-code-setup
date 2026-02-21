#!/usr/bin/env python3
"""
Split a fetched emails JSON file into N chunks for parallel classification.

Usage:
    python3 .claude/skills/gmail-label/scripts/gmail_label_split.py \
        --input .tmp/emails.json --chunks 10 --output-dir .tmp/chunks
"""

import os
import sys
import json
import argparse
import math


def main():
    parser = argparse.ArgumentParser(description="Split emails into chunks")
    parser.add_argument("--input", "-i", required=True, help="Input emails JSON file")
    parser.add_argument("--chunks", "-n", type=int, default=10, help="Number of chunks (default: 10)")
    parser.add_argument("--output-dir", "-o", required=True, help="Output directory for chunk files")
    args = parser.parse_args()

    with open(args.input, "r") as f:
        emails = json.load(f)

    total = len(emails)
    chunk_size = math.ceil(total / args.chunks)

    os.makedirs(args.output_dir, exist_ok=True)

    actual_chunks = 0
    for i in range(args.chunks):
        start = i * chunk_size
        end = min(start + chunk_size, total)
        if start >= total:
            break
        chunk = emails[start:end]
        chunk_path = os.path.join(args.output_dir, f"chunk_{i}.json")
        with open(chunk_path, "w") as f:
            json.dump(chunk, f, indent=2)
        actual_chunks += 1

    print(f"Split {total} emails into {actual_chunks} chunks of ~{chunk_size} each")
    print(f"Output: {args.output_dir}/chunk_0.json .. chunk_{actual_chunks - 1}.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
