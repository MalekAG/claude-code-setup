#!/usr/bin/env python3
"""
Skool RAG Query Pipeline

Full retrieval pipeline with:
1. Query embedding via OpenAI
2. Vector search via Pinecone
3. Reranking via Cohere (optional but recommended)
4. Response generation via Claude

Usage:
    # Interactive mode
    python execution/skool_rag_query.py --index skool-makerschool

    # Single query (post reply format - hyperlinks allowed)
    python execution/skool_rag_query.py --index skool-makerschool --query "How do I get my first client?"

    # Message format (plaintext links in brackets)
    python execution/skool_rag_query.py --index skool-makerschool --query "How do I get my first client?" --format message

    # Without reranking (if no Cohere key)
    python execution/skool_rag_query.py --index skool-makerschool --no-rerank

Environment variables:
    OPENAI_API_KEY - For embeddings
    PINECONE_API_KEY - For vector search
    COHERE_API_KEY - For reranking (optional)
    ANTHROPIC_API_KEY - For response generation
"""

import json
import os
import sys
import argparse
from typing import Optional

try:
    from openai import OpenAI
    from pinecone import Pinecone
    import anthropic
except ImportError:
    print("Missing dependencies. Install with:")
    print("  pip install openai pinecone-client anthropic")
    sys.exit(1)

try:
    import cohere
    COHERE_AVAILABLE = True
except ImportError:
    COHERE_AVAILABLE = False

from dotenv import load_dotenv

load_dotenv()

# Configuration
EMBEDDING_MODEL = "text-embedding-3-large"
EMBEDDING_DIMENSIONS = 3072
RERANK_MODEL = "rerank-v3.5"
TOP_K_RETRIEVE = 75  # Initial retrieval (cast wide net)
TOP_K_RERANK = 20    # After reranking (Cohere works best with more candidates)
TOP_K_FINAL = 15     # Passed to LLM (leverage large context windows)


class SkoolRAG:
    """RAG pipeline for Skool community Q&A."""

    def __init__(
        self,
        index_name: str,
        use_rerank: bool = True,
        verbose: bool = False
    ):
        self.index_name = index_name
        self.use_rerank = use_rerank and COHERE_AVAILABLE and os.environ.get('COHERE_API_KEY')
        self.verbose = verbose

        # Initialize clients
        self.openai = OpenAI()
        self.pinecone = Pinecone(api_key=os.environ['PINECONE_API_KEY'])
        self.index = self.pinecone.Index(index_name)
        self.anthropic = anthropic.Anthropic()

        if self.use_rerank:
            self.cohere = cohere.Client(os.environ['COHERE_API_KEY'])
        else:
            self.cohere = None
            if use_rerank:
                print("Warning: Cohere reranking disabled (missing key or package)")

    def embed_query(self, query: str) -> list[float]:
        """Generate embedding for query."""
        response = self.openai.embeddings.create(
            model=EMBEDDING_MODEL,
            input=query,
            dimensions=EMBEDDING_DIMENSIONS
        )
        return response.data[0].embedding

    def retrieve(self, query: str, top_k: int = TOP_K_RETRIEVE) -> list[dict]:
        """Retrieve relevant chunks from Pinecone."""
        # Embed query
        query_embedding = self.embed_query(query)

        # Search
        results = self.index.query(
            vector=query_embedding,
            top_k=top_k,
            include_metadata=True
        )

        # Format results
        chunks = []
        for match in results.matches:
            chunks.append({
                'id': match.id,
                'score': match.score,
                'text': match.metadata.get('text', ''),
                'post_title': match.metadata.get('post_title', ''),
                'post_url': match.metadata.get('post_url', ''),
                'post_author': match.metadata.get('post_author', ''),
                'chunk_type': match.metadata.get('chunk_type', ''),
            })

        if self.verbose:
            print(f"Retrieved {len(chunks)} chunks")

        return chunks

    def rerank(self, query: str, chunks: list[dict], top_k: int = TOP_K_RERANK) -> list[dict]:
        """Rerank chunks using Cohere."""
        if not self.cohere or not chunks:
            return chunks[:top_k]

        # Prepare documents for reranking
        documents = [c['text'] for c in chunks]

        # Rerank
        response = self.cohere.rerank(
            model=RERANK_MODEL,
            query=query,
            documents=documents,
            top_n=top_k
        )

        # Reorder chunks by rerank score
        reranked = []
        for result in response.results:
            chunk = chunks[result.index].copy()
            chunk['rerank_score'] = result.relevance_score
            reranked.append(chunk)

        if self.verbose:
            print(f"Reranked to {len(reranked)} chunks")

        return reranked

    def format_context(self, chunks: list[dict]) -> str:
        """Format chunks into context for LLM."""
        context_parts = []

        for i, chunk in enumerate(chunks, 1):
            source = f"[{chunk['post_title']}]({chunk['post_url']})" if chunk['post_url'] else chunk['post_title']
            context_parts.append(
                f"### Source {i}: {source}\n"
                f"Type: {chunk['chunk_type']} | Author: @{chunk['post_author']}\n\n"
                f"{chunk['text']}\n"
            )

        return "\n---\n".join(context_parts)

    def generate_response(self, query: str, context: str, output_format: str = "reply") -> str:
        """Generate response using Claude.

        Args:
            query: The user's question
            context: Formatted context from retrieved chunks
            output_format: Either "reply" (hyperlinks allowed) or "message" (plaintext links in brackets)
        """
        # Link formatting instructions based on output format
        if output_format == "message":
            link_instructions = """- For links: embed plaintext URLs naturally in the sentence with context, like "The one caveat is scope (see https://skool.com/... for more on this, but essentially...)" or "I've talked about this before (https://skool.com/...) and the key insight is..."
- NEVER use markdown hyperlink format [text](url) - always plaintext URLs in round brackets
- Include links inline where they add value, woven into the flow of your answer"""
        else:  # reply format
            link_instructions = """- For links: use markdown hyperlink format [text](url), like "check out [this thread](https://skool.com/...) for more detail"
- Work links in naturally - don't force them if they don't add value"""

        system_prompt = f"""You are Your Name, founder of Maker School. You're replying to a community member's question.

Writing style:
- First person ("I", "I've found", "In my experience")
- Casual, direct, no fluff - like you're texting a friend
- NO markdown formatting (no bold, no headers, no bullet points with dashes)
- When referencing other members, just use their name naturally (e.g., "John mentioned..." or "as Sarah shared in her post...")
- Keep it concise - get to the point fast
- If you reference your own past advice, just say "I've talked about this before" or similar

Link formatting:
{link_instructions}

Content guidelines:
- Answer based ONLY on the provided context
- If context doesn't have the answer, say "I don't have a specific post about this, but..." and give general guidance
- Only include a link when it genuinely adds value (e.g. a detailed thread worth reading). Don't force it - many replies won't need a link
- Be encouraging but real - don't sugarcoat"""

        user_prompt = f"""Community member's question:
{query}

---

Relevant posts and discussions from the community:

{context}

---

Reply as Nick. Keep it natural and conversational. No markdown formatting (except for links as specified)."""

        response = self.anthropic.messages.create(
            model="claude-opus-4-5-20251101",
            max_tokens=2048,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}]
        )

        return response.content[0].text

    def reformat_response(self, text: str) -> str:
        """
        Second pass: reformat into 2-sentence paragraphs, remove trailing periods.
        Uses a fast model. Does NOT change wording, only structure.
        """
        response = self.anthropic.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2048,
            system="""You are a text reformatter. Your ONLY job is to restructure text for readability.

RULES:
1. Break text into short paragraphs (2 sentences each, on average)
2. Add blank lines between paragraphs
3. Remove the period from the final sentence of the entire response
4. DO NOT change any wording, phrasing, or content whatsoever
5. DO NOT add or remove any words
6. DO NOT fix grammar or spelling
7. DO NOT add any commentary

Just restructure and return the text.""",
            messages=[{"role": "user", "content": f"Reformat this:\n\n{text}"}]
        )
        return response.content[0].text

    def query(self, question: str, top_k_final: int = TOP_K_FINAL, output_format: str = "reply") -> dict:
        """Full RAG pipeline: retrieve -> rerank -> generate.

        Args:
            question: The user's question
            top_k_final: Number of chunks to pass to LLM
            output_format: Either "reply" (hyperlinks allowed) or "message" (plaintext links in brackets)
        """

        # Step 1: Retrieve
        chunks = self.retrieve(question, TOP_K_RETRIEVE)

        if not chunks:
            return {
                'answer': "I couldn't find any relevant information in the community discussions.",
                'sources': [],
                'query': question
            }

        # Step 2: Rerank (if enabled)
        if self.use_rerank:
            chunks = self.rerank(question, chunks, TOP_K_RERANK)

        # Step 3: Take top results
        top_chunks = chunks[:top_k_final]

        # Step 4: Generate response
        context = self.format_context(top_chunks)
        raw_answer = self.generate_response(question, context, output_format)

        # Step 5: Reformat for readability (2-sentence paragraphs, no trailing period)
        answer = self.reformat_response(raw_answer)

        # Format sources
        sources = []
        for chunk in top_chunks:
            sources.append({
                'title': chunk['post_title'],
                'url': chunk['post_url'],
                'author': chunk['post_author'],
                'type': chunk['chunk_type'],
                'score': chunk.get('rerank_score', chunk.get('score', 0))
            })

        return {
            'answer': answer,
            'sources': sources,
            'query': question
        }


def interactive_mode(rag: SkoolRAG, output_format: str = "reply"):
    """Run interactive Q&A session."""
    print("\n" + "="*60)
    print(f"Skool Community Q&A (format: {output_format}, type 'quit' to exit)")
    print("="*60 + "\n")

    while True:
        try:
            question = input("Your question: ").strip()

            if not question:
                continue
            if question.lower() in ('quit', 'exit', 'q'):
                print("Goodbye!")
                break

            print("\nSearching community knowledge...\n")
            result = rag.query(question, output_format=output_format)

            print("-" * 40)
            print(result['answer'])
            print("-" * 40)

            if result['sources']:
                print("\nSources:")
                for src in result['sources']:
                    print(f"  - {src['title']} (@{src['author']})")
                    if src['url']:
                        print(f"    {src['url']}")

            print()

        except KeyboardInterrupt:
            print("\nGoodbye!")
            break


def main():
    parser = argparse.ArgumentParser(description='Query Skool RAG')
    parser.add_argument('--index', default='skool-makerschool', help='Pinecone index name')
    parser.add_argument('--query', '-q', help='Single query (interactive mode if not provided)')
    parser.add_argument('--format', '-f', choices=['reply', 'message'], default='reply',
                        help='Output format: "reply" for hyperlinks, "message" for plaintext links in brackets')
    parser.add_argument('--no-rerank', action='store_true', help='Disable Cohere reranking')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    parser.add_argument('--json', action='store_true', help='Output as JSON')

    args = parser.parse_args()

    # Check environment
    required_vars = ['OPENAI_API_KEY', 'PINECONE_API_KEY', 'ANTHROPIC_API_KEY']
    missing = [v for v in required_vars if not os.environ.get(v)]
    if missing:
        print(f"Error: Missing environment variables: {', '.join(missing)}")
        sys.exit(1)

    # Initialize RAG
    rag = SkoolRAG(
        index_name=args.index,
        use_rerank=not args.no_rerank,
        verbose=args.verbose
    )

    if args.query:
        # Single query mode
        result = rag.query(args.query, output_format=args.format)

        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"\nQuestion: {result['query']}\n")
            print(result['answer'])
            print("\nSources:")
            for src in result['sources']:
                print(f"  - {src['title']} ({src['url']})")
    else:
        # Interactive mode
        interactive_mode(rag, output_format=args.format)


if __name__ == '__main__':
    main()
