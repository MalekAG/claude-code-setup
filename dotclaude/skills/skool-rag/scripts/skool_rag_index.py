#!/usr/bin/env python3
"""
Skool RAG Pinecone Indexing Script

Generates embeddings and indexes chunks into Pinecone with:
1. OpenAI text-embedding-3-large (3072 dimensions, best quality)
2. Batch processing with progress saving
3. Metadata for hybrid search filtering

Usage:
    python execution/skool_rag_index.py \
        --chunks .tmp/rag_chunks.json \
        --index skool-makerschool \
        --batch-size 100

Environment variables required:
    OPENAI_API_KEY - For embeddings
    PINECONE_API_KEY - For vector storage
"""

import json
import os
import sys
import time
import argparse
from pathlib import Path
from typing import Generator

try:
    from openai import OpenAI
    from pinecone import Pinecone, ServerlessSpec
except ImportError:
    print("Missing dependencies. Install with:")
    print("  pip install openai pinecone-client")
    sys.exit(1)

from dotenv import load_dotenv

load_dotenv()

# Configuration
EMBEDDING_MODEL = "text-embedding-3-large"
EMBEDDING_DIMENSIONS = 3072
PINECONE_CLOUD = "aws"
PINECONE_REGION = "us-east-1"


def load_chunks(chunks_file: str) -> list[dict]:
    """Load prepared chunks."""
    with open(chunks_file) as f:
        return json.load(f)


def load_progress(progress_file: str) -> set:
    """Load set of already-indexed chunk IDs."""
    if os.path.exists(progress_file):
        with open(progress_file) as f:
            return set(json.load(f))
    return set()


def save_progress(progress_file: str, indexed_ids: set):
    """Save progress to file."""
    with open(progress_file, 'w') as f:
        json.dump(list(indexed_ids), f)


def batch_chunks(chunks: list, batch_size: int) -> Generator[list, None, None]:
    """Yield batches of chunks."""
    for i in range(0, len(chunks), batch_size):
        yield chunks[i:i + batch_size]


def truncate_text(text: str, max_chars: int = 6000) -> str:
    """Truncate text to fit within embedding token limit."""
    if len(text) > max_chars:
        return text[:max_chars]
    return text


def generate_embeddings(client: OpenAI, texts: list[str]) -> list[list[float]]:
    """Generate embeddings for a batch of texts."""
    # Truncate any texts that might exceed token limit
    truncated_texts = [truncate_text(t) for t in texts]
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=truncated_texts,
        dimensions=EMBEDDING_DIMENSIONS
    )
    return [item.embedding for item in response.data]


def create_pinecone_index(pc: Pinecone, index_name: str) -> None:
    """Create Pinecone index if it doesn't exist."""
    existing_indexes = [idx.name for idx in pc.list_indexes()]

    if index_name not in existing_indexes:
        print(f"Creating index '{index_name}'...")
        pc.create_index(
            name=index_name,
            dimension=EMBEDDING_DIMENSIONS,
            metric="cosine",
            spec=ServerlessSpec(
                cloud=PINECONE_CLOUD,
                region=PINECONE_REGION
            )
        )
        # Wait for index to be ready
        print("Waiting for index to be ready...")
        time.sleep(10)
    else:
        print(f"Index '{index_name}' already exists")


def prepare_metadata(chunk: dict) -> dict:
    """
    Prepare metadata for Pinecone.
    Pinecone has limits on metadata size and types.
    """
    meta = chunk.get('metadata', {})

    # Keep only essential, indexable fields
    return {
        'post_id': meta.get('post_id', ''),
        'post_title': meta.get('post_title', '')[:200],  # Truncate long titles
        'post_author': meta.get('post_author', ''),
        'post_url': meta.get('post_url', ''),
        'chunk_type': chunk.get('chunk_type', 'unknown'),
        'source': meta.get('source', 'skool'),
        # Store text for retrieval (Pinecone allows up to 40KB metadata)
        'text': chunk.get('text_without_prefix', '')[:8000],
    }


def index_chunks(
    chunks: list[dict],
    index_name: str,
    batch_size: int = 100,
    progress_file: str = '.tmp/rag_index_progress.json'
) -> None:
    """Main indexing function."""

    # Initialize clients
    openai_client = OpenAI()
    pc = Pinecone(api_key=os.environ['PINECONE_API_KEY'])

    # Create index
    create_pinecone_index(pc, index_name)
    index = pc.Index(index_name)

    # Load progress
    indexed_ids = load_progress(progress_file)
    print(f"Already indexed: {len(indexed_ids)} chunks")

    # Filter out already indexed
    remaining = [c for c in chunks if c['id'] not in indexed_ids]
    print(f"Remaining to index: {len(remaining)} chunks")

    if not remaining:
        print("All chunks already indexed!")
        return

    # Process in batches
    total_batches = (len(remaining) + batch_size - 1) // batch_size
    indexed_count = 0

    for batch_num, batch in enumerate(batch_chunks(remaining, batch_size), 1):
        try:
            # Generate embeddings
            texts = [c['text'] for c in batch]
            embeddings = generate_embeddings(openai_client, texts)

            # Prepare vectors for Pinecone
            vectors = []
            for chunk, embedding in zip(batch, embeddings):
                vectors.append({
                    'id': chunk['id'],
                    'values': embedding,
                    'metadata': prepare_metadata(chunk)
                })

            # Upsert to Pinecone
            index.upsert(vectors=vectors)

            # Update progress
            for chunk in batch:
                indexed_ids.add(chunk['id'])
            indexed_count += len(batch)

            # Save progress every batch
            save_progress(progress_file, indexed_ids)

            print(f"[{batch_num}/{total_batches}] Indexed {indexed_count}/{len(remaining)} chunks")

            # Rate limiting (OpenAI has 3000 RPM for embeddings)
            time.sleep(0.5)

        except Exception as e:
            print(f"Error on batch {batch_num}: {e}")
            save_progress(progress_file, indexed_ids)
            raise

    print(f"\nComplete! Total indexed: {len(indexed_ids)} chunks")

    # Print index stats
    stats = index.describe_index_stats()
    print(f"Index stats: {stats}")


def main():
    parser = argparse.ArgumentParser(description='Index Skool chunks to Pinecone')
    parser.add_argument('--chunks', required=True, help='Path to chunks JSON')
    parser.add_argument('--index', default='skool-makerschool', help='Pinecone index name')
    parser.add_argument('--batch-size', type=int, default=100, help='Batch size')
    parser.add_argument('--progress', default='.tmp/rag_index_progress.json', help='Progress file')

    args = parser.parse_args()

    # Check environment
    if not os.environ.get('OPENAI_API_KEY'):
        print("Error: OPENAI_API_KEY not set")
        sys.exit(1)
    if not os.environ.get('PINECONE_API_KEY'):
        print("Error: PINECONE_API_KEY not set")
        sys.exit(1)

    print(f"Loading chunks from {args.chunks}...")
    chunks = load_chunks(args.chunks)
    print(f"Loaded {len(chunks)} chunks")

    index_chunks(
        chunks,
        args.index,
        args.batch_size,
        args.progress
    )


if __name__ == '__main__':
    main()
