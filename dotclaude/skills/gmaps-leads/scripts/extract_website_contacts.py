#!/usr/bin/env python3
"""
Extract contact information from business websites using Claude.

This script:
1. Fetches the main page of a website
2. Identifies likely contact pages (About, Contact, Team, etc.)
3. Extracts all content as markdown
4. Uses Claude to extract structured contact information

Usage:
    python3 execution/extract_website_contacts.py --url "https://example.com"
    python3 execution/extract_website_contacts.py --urls-file websites.json
"""

import os
import sys
import json
import re
import argparse
from urllib.parse import urljoin, urlparse
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

import httpx
import html2text
import anthropic

load_dotenv()

# Contact page patterns to look for (ordered by priority)
CONTACT_PAGE_PATTERNS = [
    # High priority - most likely to have contact info
    r'/contact',
    r'/about',
    r'/team',
    r'/contact-us',
    r'/about-us',
    r'/our-team',
    # Medium priority - often has owner/staff info
    r'/staff',
    r'/people',
    r'/meet-the-team',
    r'/leadership',
    r'/management',
    r'/founders',
    r'/who-we-are',
    # Lower priority - sometimes has contact details
    r'/company',
    r'/meet-us',
    r'/our-story',
    r'/the-team',
    r'/employees',
    r'/directory',
    r'/locations',
    r'/offices',
]

# Claude model for extraction (cheap and fast)
CLAUDE_MODEL = "claude-3-5-haiku-20241022"

# Maximum content length to send to Claude (in characters)
MAX_CONTENT_LENGTH = 50000


def fetch_page(url: str, timeout: float = 15.0) -> tuple[str, str]:
    """
    Fetch a web page and return its HTML content.

    Args:
        url: URL to fetch
        timeout: Request timeout in seconds

    Returns:
        Tuple of (html_content, final_url) or (None, None) on error
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    try:
        with httpx.Client(follow_redirects=True, timeout=timeout) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()
            return response.text, str(response.url)
    except Exception as e:
        print(f"  Error fetching {url}: {e}")
        return None, None


def html_to_markdown(html: str) -> str:
    """Convert HTML to clean markdown."""
    h = html2text.HTML2Text()
    h.ignore_links = False
    h.ignore_images = True
    h.ignore_tables = False
    h.body_width = 0  # Don't wrap lines
    h.skip_internal_links = False

    markdown = h.handle(html)

    # Clean up excessive whitespace
    markdown = re.sub(r'\n{3,}', '\n\n', markdown)

    return markdown.strip()


def extract_links(html: str, base_url: str) -> list[str]:
    """Extract all links from HTML that match contact page patterns, ordered by priority."""
    # Simple regex to find href attributes
    href_pattern = r'href=["\']([^"\']+)["\']'
    matches = re.findall(href_pattern, html, re.IGNORECASE)

    # Store links with their priority (index in CONTACT_PAGE_PATTERNS)
    contact_links = {}  # url -> priority
    base_domain = urlparse(base_url).netloc

    for href in matches:
        # Skip anchors, javascript, mailto, tel
        if href.startswith(('#', 'javascript:', 'mailto:', 'tel:')):
            continue

        # Build absolute URL
        full_url = urljoin(base_url, href)
        parsed = urlparse(full_url)

        # Skip external links
        if parsed.netloc and parsed.netloc != base_domain:
            continue

        # Check if path matches contact patterns, track priority
        path = parsed.path.lower()
        for priority, pattern in enumerate(CONTACT_PAGE_PATTERNS):
            if re.search(pattern, path):
                # Keep the highest priority (lowest index) for each URL
                if full_url not in contact_links or priority < contact_links[full_url]:
                    contact_links[full_url] = priority
                break

    # Sort by priority and return top 5
    sorted_links = sorted(contact_links.items(), key=lambda x: x[1])
    return [url for url, _ in sorted_links[:5]]


def search_for_contacts(business_name: str, location: str = None) -> str:
    """
    Search the web for additional contact information about a business.
    Uses DuckDuckGo HTML (no API key needed, doesn't block).

    Returns markdown content from search results.
    """
    if not business_name:
        return ""

    # Build search query
    query_parts = [f'"{business_name}"', "owner", "email", "contact"]
    if location:
        query_parts.append(location)
    query = " ".join(query_parts)

    search_url = f"https://html.duckduckgo.com/html/?q={query}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    }

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(search_url, headers=headers)
            response.raise_for_status()

            # Extract result snippets from DuckDuckGo HTML
            html = response.text

            # Find result snippets (they're in <a class="result__snippet"> tags)
            snippet_pattern = r'class="result__snippet"[^>]*>([^<]+)<'
            snippets = re.findall(snippet_pattern, html)

            # Find result titles and URLs
            title_pattern = r'class="result__a"[^>]*href="([^"]+)"[^>]*>([^<]+)<'
            titles = re.findall(title_pattern, html)

            if not snippets and not titles:
                return ""

            # Build content from search results
            content_parts = [f"=== WEB SEARCH RESULTS for '{business_name}' ==="]

            for i, (url, title) in enumerate(titles[:5]):
                content_parts.append(f"\n## {title}")
                if i < len(snippets):
                    content_parts.append(snippets[i])

            # Also try to fetch the first non-social-media result page
            for url, title in titles[:3]:
                # Skip social media and common non-useful sites
                if any(x in url.lower() for x in ['facebook.com', 'twitter.com', 'linkedin.com',
                                                   'yelp.com', 'yellowpages', 'bbb.org']):
                    continue

                # DuckDuckGo redirects through their URL - extract actual URL
                if 'uddg=' in url:
                    actual_url = re.search(r'uddg=([^&]+)', url)
                    if actual_url:
                        from urllib.parse import unquote
                        url = unquote(actual_url.group(1))

                page_html, _ = fetch_page(url)
                if page_html:
                    page_md = html_to_markdown(page_html)
                    # Only take first 5000 chars to avoid bloat
                    content_parts.append(f"\n=== {url} ===\n{page_md[:5000]}")
                    break  # Only fetch one extra page

            return "\n".join(content_parts)

    except Exception as e:
        print(f"    Search fallback failed: {e}")
        return ""


def extract_contacts_with_claude(content: str, business_name: str = None) -> dict:
    """
    Use Claude to extract structured contact information from website content.

    Args:
        content: Markdown content from the website
        business_name: Optional business name for context

    Returns:
        Dictionary with extracted contact information
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY not found in .env", file=sys.stderr)
        return {}

    client = anthropic.Anthropic(api_key=api_key)

    # Truncate content if too long
    if len(content) > MAX_CONTENT_LENGTH:
        content = content[:MAX_CONTENT_LENGTH] + "\n\n[Content truncated...]"

    business_context = f" for {business_name}" if business_name else ""

    prompt = f"""Analyze this website content{business_context} and extract ALL contact information you can find.

Return a JSON object with these fields (use null for missing values):

{{
  "emails": ["array of all email addresses found"],
  "phone_numbers": ["array of all phone numbers found"],
  "addresses": ["array of all physical addresses found"],
  "social_media": {{
    "facebook": "url or null",
    "twitter": "url or null",
    "linkedin": "url or null",
    "instagram": "url or null",
    "youtube": "url or null",
    "tiktok": "url or null"
  }},
  "owner_info": {{
    "name": "owner/founder name if found",
    "title": "their title/position",
    "email": "their direct email if different from general",
    "phone": "their direct phone if found",
    "linkedin": "their personal linkedin if found"
  }},
  "team_members": [
    {{
      "name": "person name",
      "title": "their position",
      "email": "email if found",
      "phone": "phone if found",
      "linkedin": "linkedin if found"
    }}
  ],
  "business_hours": "operating hours if found",
  "additional_contacts": ["any other contact methods found (e.g., WhatsApp, Calendly, booking links)"]
}}

Only include fields where you found actual data. Be thorough - extract every email, phone number, and social link you can find.

WEBSITE CONTENT:
{content}

Respond with ONLY the JSON object, no other text."""

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )

        result_text = response.content[0].text.strip()

        # Clean up response if it has markdown code blocks
        if result_text.startswith("```"):
            result_text = re.sub(r'^```json?\s*', '', result_text)
            result_text = re.sub(r'\s*```$', '', result_text)

        return json.loads(result_text)

    except json.JSONDecodeError as e:
        print(f"  Error parsing Claude response: {e}")
        return {}
    except Exception as e:
        print(f"  Error calling Claude API: {e}")
        return {}


def scrape_website_contacts(url: str, business_name: str = None, fast_mode: bool = True) -> dict:
    """
    Scrape contact information from a business website.

    Args:
        url: Website URL to scrape
        business_name: Optional business name for context
        fast_mode: If True, skip web search and limit to 2 contact pages (default: True)

    Returns:
        Dictionary with extracted contact information
    """
    if not url:
        return {"error": "No URL provided"}

    # Normalize URL
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    # Fetch main page
    main_html, final_url = fetch_page(url, timeout=10.0)
    if not main_html:
        return {"error": f"Could not fetch {url}", "website": url}

    all_content = []

    # Convert main page to markdown
    main_markdown = html_to_markdown(main_html)
    all_content.append(f"=== MAIN PAGE ({final_url}) ===\n{main_markdown}")

    # Find and fetch contact-related pages (limit to 2 in fast mode)
    contact_links = extract_links(main_html, final_url)
    max_pages = 2 if fast_mode else 5
    contact_links = contact_links[:max_pages]

    for link in contact_links:
        page_html, page_url = fetch_page(link, timeout=8.0)
        if page_html:
            page_markdown = html_to_markdown(page_html)
            all_content.append(f"\n\n=== {page_url} ===\n{page_markdown}")

    # Combine all content
    combined_content = "\n".join(all_content)

    # Skip web search in fast mode (DDG often blocks anyway)
    search_content = ""
    if not fast_mode:
        search_content = search_for_contacts(business_name)
        if search_content:
            combined_content += f"\n\n{search_content}"

    # Extract contacts using Claude
    contacts = extract_contacts_with_claude(combined_content, business_name)

    # Add metadata
    contacts["_source_url"] = url
    contacts["_pages_scraped"] = 1 + len(contact_links)
    contacts["_search_enriched"] = bool(search_content)

    return contacts


def process_multiple_websites(websites: list[dict], max_workers: int = 5) -> list[dict]:
    """
    Process multiple websites in parallel.

    Args:
        websites: List of dicts with 'url' and optionally 'name' keys
        max_workers: Maximum parallel threads

    Returns:
        List of contact dictionaries
    """
    results = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_site = {
            executor.submit(
                scrape_website_contacts,
                site.get('website') or site.get('url'),
                site.get('title') or site.get('name')
            ): site
            for site in websites
            if site.get('website') or site.get('url')
        }

        for future in as_completed(future_to_site):
            site = future_to_site[future]
            try:
                contacts = future.result()
                # Merge with original site data
                merged = {**site, **contacts}
                results.append(merged)
            except Exception as e:
                print(f"Error processing {site}: {e}")
                results.append({**site, "error": str(e)})

    return results


def save_results(results: list[dict], prefix: str = "contacts") -> str:
    """Save results to a JSON file."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = ".tmp"
    os.makedirs(output_dir, exist_ok=True)

    filename = f"{output_dir}/{prefix}_{timestamp}.json"

    with open(filename, "w") as f:
        json.dump(results, f, indent=2)

    print(f"Results saved to {filename}")
    return filename


def main():
    parser = argparse.ArgumentParser(description="Extract contact info from websites using Claude")
    parser.add_argument("--url", help="Single URL to scrape")
    parser.add_argument("--name", help="Business name (for single URL)")
    parser.add_argument("--urls-file", help="JSON file with list of URLs to scrape")
    parser.add_argument("--workers", type=int, default=5, help="Parallel workers (default: 5)")
    parser.add_argument("--output", default="contacts", help="Output file prefix")
    parser.add_argument("--json", action="store_true", help="Output results as JSON to stdout")

    args = parser.parse_args()

    if args.url:
        # Single URL mode
        result = scrape_website_contacts(args.url, args.name)
        results = [result]
    elif args.urls_file:
        # Batch mode
        with open(args.urls_file, 'r') as f:
            websites = json.load(f)
        results = process_multiple_websites(websites, args.workers)
    else:
        parser.print_help()
        sys.exit(1)

    if not results:
        print("No results generated.")
        sys.exit(1)

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        filename = save_results(results, prefix=args.output)
        print(f"\nExtracted contacts from {len(results)} website(s)")


if __name__ == "__main__":
    main()
