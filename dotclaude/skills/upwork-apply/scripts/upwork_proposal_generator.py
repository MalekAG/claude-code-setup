#!/usr/bin/env python3
"""
Upwork Proposal Generator

Generates customized cover letters and project proposals for Upwork jobs.
Uses Opus 4.5 with extended thinking for high-quality personalization.

Usage:
    python execution/upwork_proposal_generator.py --input .tmp/upwork_jobs_batch.json
"""

import os
import json
import re
import time
import argparse
import threading
import anthropic
from concurrent.futures import ThreadPoolExecutor, as_completed
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from dotenv import load_dotenv

load_dotenv()

# Semaphore to serialize Google Doc creation (prevents SSL/rate limit errors)
DOC_CREATION_LOCK = threading.Semaphore(1)


def retry_with_backoff(func, max_retries=5, base_delay=2.0):
    """Execute function with exponential backoff retry."""
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise  # Re-raise on final attempt
            delay = base_delay * (2 ** attempt)  # 2, 4, 8, 16, 32 seconds
            print(f"    Retry {attempt + 1}/{max_retries} after {delay}s: {str(e)[:40]}...")
            time.sleep(delay)
    return None


def extract_job_id(url: str) -> str:
    """Extract job ID from Upwork URL."""
    match = re.search(r'~(\d+)', url)
    return f"~{match.group(1)}" if match else None


def create_apply_link(url: str) -> str:
    """Convert job URL to apply link."""
    job_id = extract_job_id(url)
    if job_id:
        return f"https://www.upwork.com/nx/proposals/job/{job_id}/apply/"
    return url


def generate_cover_letter(job: dict, proposal_doc_url: str, client: anthropic.Anthropic) -> str:
    """Generate customized cover letter using Opus 4.5 with extended thinking."""

    prompt = f"""Generate a short, personalized Upwork cover letter for this job.

JOB DETAILS:
Title: {job['title']}
Skills: {job['skills']}
Budget: {job['budget']}

COVER LETTER FORMAT (follow EXACTLY - must fit above the fold):
"Hi. I work with [2-4 word paraphrase] daily & just built a [2-5 word thing]. Free walkthrough: [LINK]"

EXAMPLES of good paraphrases:
- "n8n automations" not "n8n workflow automation pipelines"
- "AI agents" not "AI-powered autonomous agent systems"
- "Zapier workflows" not "Zapier integration and automation workflows"
- "CRM setups" not "customer relationship management system configurations"

RULES:
- Total must be under 35 words (critical - must stay above the fold)
- [2-4 word paraphrase] = very short description of their need
- [2-5 word thing] = specific relevant thing you built
- End with: Free walkthrough: [LINK]
- No "I'm excited", "I'd love to", or any filler

Return ONLY the cover letter text, nothing else. The [LINK] placeholder will be replaced."""

    response = client.messages.create(
        model="claude-opus-4-5-20251101",
        max_tokens=8000,
        thinking={
            "type": "enabled",
            "budget_tokens": 5000
        },
        messages=[{"role": "user", "content": prompt}]
    )

    # Extract text from response (skip thinking blocks)
    for block in response.content:
        if block.type == "text":
            text = block.text.strip()
            # Replace [LINK] placeholder with actual doc URL
            text = text.replace('[LINK]', proposal_doc_url)
            text = text.replace('[link]', proposal_doc_url)
            return text
    return ""


def generate_cover_letter_simple(job: dict, client: anthropic.Anthropic) -> str:
    """Generate simplified cover letter without doc link."""

    prompt = f"""Generate a short, personalized Upwork cover letter for this job.

JOB DETAILS:
Title: {job['title']}
Skills: {job['skills']}
Budget: {job['budget']}

FORMAT (follow EXACTLY - must fit above the fold):
"Hi. I work with [2-4 word paraphrase] daily & just built a [2-5 word thing]. Happy to walk you through my approach."

RULES:
- Total must be under 35 words
- No "I'm excited", "I'd love to", or any filler
- End with offer to explain approach

Return ONLY the cover letter text."""

    response = client.messages.create(
        model="claude-opus-4-5-20251101",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}]
    )

    for block in response.content:
        if block.type == "text":
            return block.text.strip()
    return ""


def generate_proposal(job: dict, client: anthropic.Anthropic) -> str:
    """Generate project proposal using Opus 4.5 with extended thinking."""

    prompt = f"""Write a personalized project proposal for this Upwork job. Write as Nick - first person, conversational, direct.

JOB DETAILS:
Title: {job['title']}
Description: {job.get('description', '')[:500]}
Skills Required: {job['skills']}
Budget: {job['budget']}

PROPOSAL FORMAT:

Hey [use client name if available in job details, otherwise just "Hey"].

I spent ~15 minutes putting this together for you. In short, it's how I would create your [2-4 word paraphrase of their system/need] end to end.

I've worked with $MM companies like Anthropic (yes—that Anthropic) and I have a lot of experience designing/building similar workflows.

Here's a step-by-step, along with my reasoning at every point:

My proposed approach

[Provide 4-6 detailed numbered steps. For each step:
- Start with what you'd do
- Explain WHY this approach (the reasoning)
- Mention specific tools/tech where relevant (n8n, Claude API, Zapier, Make, GPT, etc.)
- Keep it conversational, like you're explaining to a smart person]

What you'll get

[2-3 concrete deliverables, be specific]

Timeline

[Realistic estimate, conversational tone]

TONE RULES:
- First person ("I would...", "Here's how I'd...")
- Direct and confident, not salesy
- Like you're talking to a peer, not pitching
- Specific technical details, no fluff
- Use plain text with clear section headers (no markdown symbols like ** or #)
- Total ~300 words

Return ONLY the proposal text."""

    response = client.messages.create(
        model="claude-opus-4-5-20251101",
        max_tokens=10000,
        thinking={
            "type": "enabled",
            "budget_tokens": 8000
        },
        messages=[{"role": "user", "content": prompt}]
    )

    for block in response.content:
        if block.type == "text":
            return block.text.strip()
    return ""


def create_formatted_google_doc(title: str, content: str, drive_service, docs_service) -> str:
    """Create a Google Doc with properly formatted proposal content."""

    # Create the document
    doc = docs_service.documents().create(body={
        'title': f"Proposal: {title[:50]}"
    }).execute()

    doc_id = doc.get('documentId')

    # Parse content and build formatting requests
    requests = []
    current_index = 1

    # Split into lines and process
    lines = content.split('\n')

    # Section headers to make bold
    headers = ['My proposed approach', 'What you\'ll get', 'Timeline',
               'Project Understanding', 'Proposed Approach', 'Deliverables',
               'Timeline & Investment', 'Investment', 'Why Me']

    for line in lines:
        if not line.strip():
            # Empty line - add paragraph break
            requests.append({
                'insertText': {
                    'location': {'index': current_index},
                    'text': '\n'
                }
            })
            current_index += 1
            continue

        # Check if this is a header
        is_header = any(line.strip().startswith(h) or line.strip() == h for h in headers)

        # Check if this is a bullet point
        is_bullet = line.strip().startswith('- ') or line.strip().startswith('• ')

        if is_bullet:
            # Remove the bullet marker, we'll format it properly
            clean_line = line.strip()[2:].strip()
            text_to_insert = f"• {clean_line}\n"
        else:
            text_to_insert = f"{line.strip()}\n"

        # Insert the text
        requests.append({
            'insertText': {
                'location': {'index': current_index},
                'text': text_to_insert
            }
        })

        # If header, mark for bold formatting
        if is_header:
            requests.append({
                'updateTextStyle': {
                    'range': {
                        'startIndex': current_index,
                        'endIndex': current_index + len(text_to_insert) - 1
                    },
                    'textStyle': {
                        'bold': True,
                        'fontSize': {'magnitude': 12, 'unit': 'PT'}
                    },
                    'fields': 'bold,fontSize'
                }
            })

        current_index += len(text_to_insert)

    # Execute all requests
    if requests:
        docs_service.documents().batchUpdate(
            documentId=doc_id,
            body={'requests': requests}
        ).execute()

    # Make publicly viewable with link
    drive_service.permissions().create(
        fileId=doc_id,
        body={'type': 'anyone', 'role': 'reader'},
        fields='id'
    ).execute()

    # Enable link sharing
    drive_service.files().update(
        fileId=doc_id,
        body={'copyRequiresWriterPermission': False}
    ).execute()

    return f"https://docs.google.com/document/d/{doc_id}"


def process_job(job: dict, anthropic_client, drive_service, docs_service) -> dict:
    """Process a single job: generate proposal first, then cover letter with doc link."""

    print(f"  Processing: {job['title'][:50]}...")

    # Generate apply link
    apply_link = create_apply_link(job['url'])

    # Generate proposal FIRST
    proposal = generate_proposal(job, anthropic_client)

    # Create Google Doc with semaphore (serialized) and exponential retry
    # Skip if docs_service is not available (missing scope)
    doc_url = ""
    if docs_service is not None:
        with DOC_CREATION_LOCK:  # Only one Doc creation at a time
            try:
                doc_url = retry_with_backoff(
                    lambda: create_formatted_google_doc(job['title'], proposal, drive_service, docs_service),
                    max_retries=4,
                    base_delay=1.5
                )
                print(f"    Doc created: {doc_url[:60]}...")
            except Exception as e:
                print(f"    Doc failed after retries: {str(e)[:40]}")

    # Generate cover letter - with doc URL if available, otherwise without
    if doc_url:
        cover_letter = generate_cover_letter(job, doc_url, anthropic_client)
    else:
        # Simplified cover letter without doc link
        cover_letter = generate_cover_letter_simple(job, anthropic_client)

    return {
        **job,
        'apply_link': apply_link,
        'cover_letter': cover_letter,
        'proposal_doc': doc_url if doc_url else proposal[:500]  # First 500 chars of proposal as fallback
    }


def create_new_spreadsheet(title: str, sheets_service) -> str:
    """Create a new Google Sheet and return its ID."""
    spreadsheet = sheets_service.spreadsheets().create(body={
        'properties': {'title': title},
        'sheets': [{'properties': {'title': 'Jobs'}}]
    }).execute()
    return spreadsheet.get('spreadsheetId')


def write_fresh_sheet(sheet_id: str, jobs: list[dict], sheets_service):
    """Write all data to a fresh sheet with all columns."""
    headers = ['Title', 'URL', 'Budget', 'Experience', 'Skills', 'Category',
               'Client Country', 'Client Spent', 'Client Hires', 'Connects',
               'Apply Link', 'Cover Letter', 'Proposal Doc']

    rows = [headers]
    for job in jobs:
        skills = job.get('skills', [])
        if isinstance(skills, list):
            skills = ', '.join(skills[:5])

        client = job.get('client', {})

        rows.append([
            job.get('title', ''),
            job.get('url', ''),
            job.get('budget', ''),
            job.get('experience_level', ''),
            skills,
            job.get('category', ''),
            client.get('country', '') if isinstance(client, dict) else '',
            f"${client.get('total_spent', 0):,.0f}" if isinstance(client, dict) else '',
            client.get('total_hires', 0) if isinstance(client, dict) else '',
            job.get('connects_cost', ''),
            job.get('apply_link', ''),
            job.get('cover_letter', ''),
            job.get('proposal_doc', ''),
        ])

    sheets_service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=f'Jobs!A1:M{len(rows)}',
        valueInputOption='RAW',
        body={'values': rows}
    ).execute()

    print(f"Wrote {len(jobs)} jobs to sheet")


def update_spreadsheet(sheet_id: str, jobs: list[dict], sheets_service):
    """Update the spreadsheet with new columns."""

    # Get current data to find last column
    result = sheets_service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range='Jobs!A1:Z1'
    ).execute()

    current_headers = result.get('values', [[]])[0]

    # Check if columns already exist
    if 'Apply Link' in current_headers:
        # Find the column index and overwrite
        col_idx = current_headers.index('Apply Link')
        col_letter = chr(ord('A') + col_idx)
        end_col_letter = chr(ord('A') + col_idx + 2)
    else:
        # Add new columns
        next_col = len(current_headers)
        col_letter = chr(ord('A') + next_col)
        end_col_letter = chr(ord('A') + next_col + 2)

        # Add headers
        new_headers = ['Apply Link', 'Cover Letter', 'Proposal Doc']
        sheets_service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range=f'Jobs!{col_letter}1:{end_col_letter}1',
            valueInputOption='RAW',
            body={'values': [new_headers]}
        ).execute()

    # Add data rows
    rows = []
    for job in jobs:
        rows.append([
            job.get('apply_link', ''),
            job.get('cover_letter', ''),
            job.get('proposal_doc', '')
        ])

    sheets_service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=f'Jobs!{col_letter}2:{end_col_letter}{len(rows)+1}',
        valueInputOption='RAW',
        body={'values': rows}
    ).execute()

    print(f"Updated spreadsheet with columns at {col_letter}-{end_col_letter}")


def main():
    parser = argparse.ArgumentParser(description="Generate Upwork proposals")
    parser.add_argument("--input", "-i", required=True, help="Input JSON file with jobs")
    parser.add_argument("--sheet-id", "-s", help="Google Sheet ID (creates new if not provided)")
    parser.add_argument("--output", "-o", help="Output JSON file")
    parser.add_argument("--filter-keywords", "-f", help="Only process jobs with these keywords (comma-separated)")
    parser.add_argument("--workers", "-w", type=int, default=5, help="Number of parallel workers (default: 5)")

    args = parser.parse_args()

    # Load jobs
    with open(args.input) as f:
        jobs = json.load(f)

    # Filter if specified
    if args.filter_keywords:
        keywords = [k.strip().lower() for k in args.filter_keywords.split(',')]
        jobs = [j for j in jobs if j.get('keyword', '').lower() in keywords]

    print(f"Processing {len(jobs)} jobs...", flush=True)

    # Initialize Anthropic client
    anthropic_client = anthropic.Anthropic()

    # Initialize Google services - read scopes from token.json
    with open('token.json', 'r') as f:
        token_data = json.load(f)
    available_scopes = token_data.get('scopes', [])

    # Only request scopes that are in the token
    creds = Credentials.from_authorized_user_file('token.json', available_scopes)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    sheets_service = build('sheets', 'v4', credentials=creds)
    drive_service = build('drive', 'v3', credentials=creds)

    # Only initialize docs service if documents scope is available
    has_docs_scope = 'https://www.googleapis.com/auth/documents' in available_scopes
    docs_service = build('docs', 'v1', credentials=creds) if has_docs_scope else None
    if not has_docs_scope:
        print("Note: documents scope not available - will skip Google Doc creation")

    # Create or use existing sheet
    if args.sheet_id:
        sheet_id = args.sheet_id
    else:
        from datetime import datetime
        sheet_title = f"Upwork Proposals - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        sheet_id = create_new_spreadsheet(sheet_title, sheets_service)
        print(f"Created new sheet: https://docs.google.com/spreadsheets/d/{sheet_id}")

    # Process jobs in parallel
    print(f"Processing {len(jobs)} jobs with {args.workers} parallel workers...", flush=True)

    processed_jobs = [None] * len(jobs)  # Preserve order
    completed = 0

    def process_with_index(idx_job):
        idx, job = idx_job
        try:
            return idx, process_job(job, anthropic_client, drive_service, docs_service), None
        except Exception as e:
            return idx, {**job, 'apply_link': create_apply_link(job['url']), 'cover_letter': '', 'proposal_doc': ''}, str(e)

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(process_with_index, (i, job)): i for i, job in enumerate(jobs)}

        for future in as_completed(futures):
            idx, result, error = future.result()
            processed_jobs[idx] = result
            completed += 1

            if error:
                print(f"[{completed}/{len(jobs)}] ✗ {jobs[idx]['title'][:40]}... Error: {error[:50]}", flush=True)
            else:
                print(f"[{completed}/{len(jobs)}] ✓ {result['title'][:50]}...", flush=True)

    # Write all data to sheet (fresh sheet = all columns)
    write_fresh_sheet(sheet_id, processed_jobs, sheets_service)

    # Save output
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(processed_jobs, f, indent=2)
        print(f"Saved to {args.output}")

    print(f"\nDone! Processed {len(processed_jobs)} jobs")
    print(f"Sheet: https://docs.google.com/spreadsheets/d/{sheet_id}")

    return processed_jobs


if __name__ == "__main__":
    main()
