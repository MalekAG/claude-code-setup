#!/usr/bin/env python3
"""
Skool RAG Data Preparation Script

Transforms scraped Skool posts and comments into RAG-ready chunks with:
1. Thread reconstruction (parent + replies as single units)
2. Contextual prefixes for better retrieval
3. Metadata for filtering

Usage:
    python execution/skool_rag_prepare.py \
        --posts .tmp/all_skool_posts.json \
        --comments .tmp/skool_comments.json \
        --output .tmp/rag_chunks.json
"""

import json
import argparse
import hashlib
from datetime import datetime
from pathlib import Path


def load_data(posts_file: str, comments_file: str) -> tuple[list, dict]:
    """Load posts and comments data."""
    with open(posts_file) as f:
        posts = json.load(f)

    with open(comments_file) as f:
        comments_data = json.load(f)

    return posts, comments_data


def reconstruct_threads(comments: list) -> list[dict]:
    """
    Reconstruct comment threads from flat list with parent_id.
    Returns list of thread dicts with top-level comment and all replies.
    """
    if not comments:
        return []

    # Index comments by ID
    by_id = {c['id']: c for c in comments}

    # Find top-level comments (no parent)
    top_level = [c for c in comments if not c.get('parent_id')]

    # Build threads
    threads = []
    for parent in top_level:
        thread = {
            'root': parent,
            'replies': []
        }

        # Find all replies to this parent (can be nested)
        def find_replies(parent_id):
            replies = []
            for c in comments:
                if c.get('parent_id') == parent_id:
                    replies.append(c)
                    # Recursively find nested replies
                    replies.extend(find_replies(c['id']))
            return replies

        thread['replies'] = find_replies(parent['id'])
        threads.append(thread)

    return threads


def thread_to_text(thread: dict) -> str:
    """Convert a thread to readable text format."""
    root = thread['root']
    text = f"@{root['author']}: {root['content']}"

    for reply in thread['replies']:
        # Indent replies
        text += f"\n  └─ @{reply['author']}: {reply['content']}"

    return text


def estimate_tokens(text: str) -> int:
    """Rough token estimate (4 chars per token)."""
    return len(text) // 4


def create_chunk_id(content: str, post_id: str) -> str:
    """Create deterministic chunk ID."""
    hash_input = f"{post_id}:{content[:100]}"
    return hashlib.md5(hash_input.encode()).hexdigest()[:16]


def generate_contextual_prefix(post: dict, chunk_type: str) -> str:
    """
    Generate contextual prefix for better retrieval.
    Based on Anthropic's Contextual Retrieval approach.
    """
    title = post.get('title', 'Untitled')
    author = post.get('author', 'Unknown')

    if chunk_type == 'post':
        return f"This is a post titled \"{title}\" from the Maker School community by @{author}. "
    elif chunk_type == 'thread':
        return f"This is a comment thread on the post \"{title}\" in the Maker School community. "
    elif chunk_type == 'post_with_discussion':
        return f"This is the post \"{title}\" by @{author} along with community discussion from Maker School. "

    return ""


def create_chunks(posts: list, comments_data: dict, max_tokens: int = 500) -> list[dict]:
    """
    Create RAG chunks from posts and comments.

    Strategy:
    - Small posts (<max_tokens) with few comments: combine as single chunk
    - Large posts: split post, then separate thread chunks
    - Each thread is a chunk (preserves conversational context)
    """
    chunks = []

    # Index posts by ID for quick lookup
    posts_by_id = {p['id']: p for p in posts}

    for post in posts:
        post_id = post['id']
        post_content = post.get('content', '')
        post_title = post.get('title', 'Untitled')
        post_url = post.get('url', '')
        post_author = post.get('author', 'Unknown')
        post_date = post.get('created_at', '')
        post_likes = post.get('likes', 0)

        # Get comments for this post
        post_comments_data = comments_data.get(post_id, {})
        comments = post_comments_data.get('comments', [])

        # Reconstruct threads
        threads = reconstruct_threads(comments)

        # Calculate sizes
        post_tokens = estimate_tokens(post_content)
        total_comment_tokens = sum(
            estimate_tokens(thread_to_text(t)) for t in threads
        )

        # Base metadata for all chunks from this post
        base_metadata = {
            'post_id': post_id,
            'post_title': post_title,
            'post_url': post_url,
            'post_author': post_author,
            'post_date': post_date,
            'post_likes': post_likes,
            'source': 'skool_makerschool',
        }

        # Strategy 1: Small post + small discussion = single chunk
        if post_tokens + total_comment_tokens < max_tokens and len(threads) <= 5:
            combined_text = f"# {post_title}\n\n{post_content}"

            if threads:
                combined_text += "\n\n## Discussion\n"
                for thread in threads:
                    combined_text += f"\n{thread_to_text(thread)}\n"

            prefix = generate_contextual_prefix(post, 'post_with_discussion')

            chunks.append({
                'id': create_chunk_id(combined_text, post_id),
                'text': prefix + combined_text,
                'text_without_prefix': combined_text,
                'chunk_type': 'post_with_discussion',
                'metadata': {
                    **base_metadata,
                    'comment_count': len(comments),
                    'thread_count': len(threads),
                }
            })

        else:
            # Strategy 2: Separate post chunk
            prefix = generate_contextual_prefix(post, 'post')
            post_text = f"# {post_title}\n\n{post_content}"

            chunks.append({
                'id': create_chunk_id(post_text, post_id),
                'text': prefix + post_text,
                'text_without_prefix': post_text,
                'chunk_type': 'post',
                'metadata': {
                    **base_metadata,
                    'comment_count': len(comments),
                }
            })

            # Strategy 3: Each thread as separate chunk
            for i, thread in enumerate(threads):
                thread_text = thread_to_text(thread)

                # Skip very short threads (< 20 chars)
                if len(thread_text) < 20:
                    continue

                prefix = generate_contextual_prefix(post, 'thread')

                chunks.append({
                    'id': create_chunk_id(thread_text, f"{post_id}_thread_{i}"),
                    'text': prefix + thread_text,
                    'text_without_prefix': thread_text,
                    'chunk_type': 'thread',
                    'metadata': {
                        **base_metadata,
                        'thread_index': i,
                        'reply_count': len(thread['replies']),
                        'thread_author': thread['root']['author'],
                    }
                })

    return chunks


def main():
    parser = argparse.ArgumentParser(description='Prepare Skool data for RAG')
    parser.add_argument('--posts', required=True, help='Path to posts JSON')
    parser.add_argument('--comments', required=True, help='Path to comments JSON')
    parser.add_argument('--output', required=True, help='Output path for chunks')
    parser.add_argument('--max-tokens', type=int, default=500, help='Max tokens per chunk')

    args = parser.parse_args()

    print(f"Loading data...")
    posts, comments_data = load_data(args.posts, args.comments)
    print(f"  Posts: {len(posts)}")
    print(f"  Posts with comments: {len(comments_data)}")

    print(f"\nCreating chunks (max {args.max_tokens} tokens)...")
    chunks = create_chunks(posts, comments_data, args.max_tokens)

    # Stats
    post_chunks = [c for c in chunks if c['chunk_type'] == 'post']
    thread_chunks = [c for c in chunks if c['chunk_type'] == 'thread']
    combined_chunks = [c for c in chunks if c['chunk_type'] == 'post_with_discussion']

    print(f"\nChunk statistics:")
    print(f"  Total chunks: {len(chunks)}")
    print(f"  Post-only chunks: {len(post_chunks)}")
    print(f"  Thread chunks: {len(thread_chunks)}")
    print(f"  Combined (post+discussion): {len(combined_chunks)}")

    avg_tokens = sum(estimate_tokens(c['text']) for c in chunks) / len(chunks) if chunks else 0
    print(f"  Average tokens per chunk: {avg_tokens:.0f}")

    # Save
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w') as f:
        json.dump(chunks, f, indent=2)

    print(f"\nSaved {len(chunks)} chunks to {args.output}")


if __name__ == '__main__':
    main()
