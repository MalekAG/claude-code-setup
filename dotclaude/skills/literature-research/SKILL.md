---
name: literature-research
description: Search academic literature and perform deep research reviews. Use when user asks to search PubMed, find academic papers, or do literature reviews.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

# Literature Research

## Goal
Search academic databases and perform comprehensive literature reviews.

## Scripts
- `./scripts/pubmed_literature_search.py` - Search PubMed
- `./scripts/literature_deep_review.py` - Deep review with Claude

## Usage

### Search PubMed
```bash
python3 ./scripts/pubmed_literature_search.py \
  --query "machine learning cancer diagnosis" \
  --limit 50 \
  --output .tmp/papers.json
```

### Deep Review
```bash
python3 ./scripts/literature_deep_review.py \
  --input .tmp/papers.json \
  --output .tmp/review.md
```

## Output
- JSON file with paper metadata
- Markdown review with key findings, themes, gaps
