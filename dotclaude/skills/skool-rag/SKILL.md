---
name: skool-rag
description: Query Skool community content using RAG pipeline with vector search. Use when user asks to search Skool knowledge, find community answers, or query Skool content.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

# Skool RAG Pipeline

## Goal
Query Skool community content using a RAG (Retrieval-Augmented Generation) pipeline with vector search and reranking.

## Scripts
- `./scripts/skool_rag_prepare.py` - Prepare content for indexing
- `./scripts/skool_rag_index.py` - Index content in Pinecone
- `./scripts/skool_rag_query.py` - Query the knowledge base

## Pipeline

### 1. Prepare Content
```bash
python3 ./scripts/skool_rag_prepare.py --community makerschool
```
Scrapes and chunks community content.

### 2. Index in Pinecone
```bash
python3 ./scripts/skool_rag_index.py --input .tmp/skool_chunks.json
```
Creates OpenAI embeddings and stores in Pinecone.

### 3. Query
```bash
python3 ./scripts/skool_rag_query.py --query "How do I get my first client?"
```

**Pipeline:**
1. OpenAI embeddings for query
2. Pinecone vector search
3. Cohere reranking
4. Claude response generation

## Environment
```
PINECONE_API_KEY=your_key
OPENAI_API_KEY=your_key
COHERE_API_KEY=your_key
ANTHROPIC_API_KEY=your_key
```
