#!/usr/bin/env python3
"""
Skool comment scraper - fetches comments for posts using browser-based WAF token generation.
Designed for large-scale scraping with rate limiting and incremental saves.
"""

import os
import sys
import json
import time
import argparse
from datetime import datetime
from playwright.sync_api import sync_playwright
import requests

# Load environment variables
def load_env():
    env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if '=' in line and not line.startswith('#'):
                    k, v = line.strip().split('=', 1)
                    os.environ[k] = v


class SkoolCommentScraper:
    """
    Scrapes comments from Skool posts using Playwright for WAF token generation.
    """

    def __init__(self, auth_token=None, client_id=None, headless=True):
        self.base_url = "https://www.skool.com"
        self.api_url = "https://api2.skool.com"
        self.group_id = "e256cd9ef1ac4dbe9197634db46e9e3b"  # makerschool

        self.auth_token = auth_token or os.getenv("SKOOL_AUTH_TOKEN")
        self.client_id = client_id or os.getenv("SKOOL_CLIENT_ID")

        if not self.auth_token:
            raise ValueError("SKOOL_AUTH_TOKEN not found")

        self.headless = headless
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.session = requests.Session()

        self._waf_token = None
        self._waf_token_uses = 0
        self._max_waf_uses = 50  # Refresh WAF token every N requests

    def start(self):
        """Start the browser session."""
        print("Starting browser session...", file=sys.stderr)

        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=self.headless)
        self.context = self.browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )

        self.context.add_cookies([
            {'name': 'auth_token', 'value': self.auth_token, 'domain': '.skool.com', 'path': '/'},
            {'name': 'client_id', 'value': self.client_id, 'domain': '.skool.com', 'path': '/'}
        ])

        self.page = self.context.new_page()

        # Navigate to establish session
        print("Loading Skool to generate WAF token...", file=sys.stderr)
        self.page.goto(f"{self.base_url}/makerschool", wait_until="domcontentloaded", timeout=60000)
        time.sleep(3)

        self._refresh_waf_token()
        print("Browser session ready", file=sys.stderr)

    def stop(self):
        """Stop the browser session."""
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()

    def _refresh_waf_token(self):
        """Get a fresh WAF token from browser cookies."""
        cookies = self.context.cookies()
        for cookie in cookies:
            if cookie['name'] == 'aws-waf-token':
                self._waf_token = cookie['value']
                self._waf_token_uses = 0
                return

        # Trigger token generation by reloading
        print("Refreshing WAF token...", file=sys.stderr)
        self.page.reload(wait_until="domcontentloaded")
        time.sleep(2)

        cookies = self.context.cookies()
        for cookie in cookies:
            if cookie['name'] == 'aws-waf-token':
                self._waf_token = cookie['value']
                self._waf_token_uses = 0
                return

        raise Exception("Could not obtain WAF token")

    def _get_waf_token(self):
        """Get WAF token, refreshing if needed."""
        if self._waf_token_uses >= self._max_waf_uses:
            self._refresh_waf_token()
        self._waf_token_uses += 1
        return self._waf_token

    def fetch_comments(self, post_id, limit=20):
        """
        Fetch all comments for a post using browser-based request with pagination.

        Args:
            post_id: The post ID
            limit: Max comments per request (API max is 20)

        Returns:
            List of comment dictionaries
        """
        all_comments = []
        cursor = None
        page_num = 0

        while True:
            # Build URL with pagination cursor if we have one
            url = f"{self.api_url}/posts/{post_id}/comments?group-id={self.group_id}&limit={limit}"
            if cursor:
                url += f"&last={cursor}"

            try:
                # Use Playwright to make the request (inherits browser's WAF token)
                response = self.page.evaluate(f'''
                    async () => {{
                        const response = await fetch("{url}", {{
                            method: "GET",
                            headers: {{
                                "accept": "application/json",
                            }},
                            credentials: "include"
                        }});
                        if (!response.ok) {{
                            return {{ error: response.status, text: await response.text() }};
                        }}
                        return await response.json();
                    }}
                ''')

                if isinstance(response, dict) and 'error' in response:
                    print(f"  API error {response['error']}", file=sys.stderr)
                    break

                # Parse comments from post_tree.children structure
                post_tree = response.get('post_tree', {})
                children = post_tree.get('children', [])

                if not children:
                    break

                parsed = self._parse_comments(children, post_id)
                all_comments.extend(parsed)
                page_num += 1

                # Check for pagination cursor
                next_cursor = response.get('last')
                if not next_cursor or next_cursor == cursor:
                    break  # No more pages

                cursor = next_cursor

                # Small delay between pagination requests
                if cursor:
                    time.sleep(0.5)

            except Exception as e:
                print(f"  Error fetching comments for {post_id}: {e}", file=sys.stderr)
                break

        return all_comments

    def _parse_comments(self, raw_comments, post_id, parent_id=None):
        """Parse raw comment data into clean format with proper parent tracking."""
        parsed = []

        for c in raw_comments:
            # Handle nested structure
            if 'post' in c:
                comment_data = c['post']
            else:
                comment_data = c

            meta = comment_data.get('metadata', {})
            user = comment_data.get('user', {})
            comment_id = comment_data.get('id')

            parsed.append({
                'id': comment_id,
                'post_id': post_id,
                'parent_id': parent_id,  # Use passed-in parent, not API field
                'content': meta.get('content', ''),
                'author': user.get('name', 'Unknown'),
                'author_id': user.get('id'),
                'author_name': f"{user.get('firstName', '')} {user.get('lastName', '')}".strip(),
                'created_at': comment_data.get('createdAt'),
                'likes': meta.get('upvotes', 0),
            })

            # Process nested replies - pass current comment's ID as parent
            nested = c.get('children', [])
            if nested:
                parsed.extend(self._parse_comments(nested, post_id, parent_id=comment_id))

        return parsed

    def scrape_comments_for_posts(self, posts, output_file, delay=3.0, skip_existing=True):
        """
        Scrape comments for multiple posts with incremental saves.

        Args:
            posts: List of post dicts (must have 'id' and 'comments' count)
            output_file: Path to save results (JSON)
            delay: Seconds between requests
            skip_existing: Skip posts that already have comments in output
        """
        # Load existing data
        existing_data = {}
        if os.path.exists(output_file) and skip_existing:
            try:
                with open(output_file, 'r') as f:
                    existing_data = json.load(f)
                print(f"Loaded {len(existing_data)} existing posts with comments", file=sys.stderr)
            except:
                existing_data = {}

        # Filter posts with comments
        posts_with_comments = [p for p in posts if p.get('comments', 0) > 0]
        print(f"Posts with comments: {len(posts_with_comments)}", file=sys.stderr)

        # Skip already scraped
        if skip_existing:
            posts_to_scrape = [p for p in posts_with_comments if p['id'] not in existing_data]
        else:
            posts_to_scrape = posts_with_comments

        print(f"Posts to scrape: {len(posts_to_scrape)}", file=sys.stderr)

        total_comments = 0

        for i, post in enumerate(posts_to_scrape, 1):
            post_id = post['id']
            expected_comments = post.get('comments', 0)

            print(f"[{i}/{len(posts_to_scrape)}] Fetching {expected_comments} comments for: {post.get('title', '')[:50]}...", file=sys.stderr)

            comments = self.fetch_comments(post_id)

            if comments:
                existing_data[post_id] = {
                    'post_id': post_id,
                    'post_title': post.get('title', ''),
                    'post_url': post.get('url', ''),
                    'expected_comments': expected_comments,
                    'fetched_comments': len(comments),
                    'comments': comments,
                    'scraped_at': datetime.utcnow().isoformat() + 'Z'
                }
                total_comments += len(comments)
                print(f"  Got {len(comments)} comments", file=sys.stderr)
            else:
                print(f"  No comments returned", file=sys.stderr)

            # Save incrementally every 10 posts
            if i % 10 == 0:
                with open(output_file, 'w') as f:
                    json.dump(existing_data, f, indent=2)
                print(f"  [Saved checkpoint: {len(existing_data)} posts, {total_comments} comments]", file=sys.stderr)

            # Rate limiting
            if i < len(posts_to_scrape):
                time.sleep(delay)

        # Final save
        with open(output_file, 'w') as f:
            json.dump(existing_data, f, indent=2)

        print(f"\nComplete! Scraped {total_comments} comments from {len(posts_to_scrape)} posts", file=sys.stderr)
        print(f"Total posts with comments: {len(existing_data)}", file=sys.stderr)
        print(f"Saved to: {output_file}", file=sys.stderr)

        return existing_data


def main():
    load_env()

    parser = argparse.ArgumentParser(description="Scrape comments from Skool posts")
    parser.add_argument("--posts-file", required=True, help="JSON file with posts to scrape")
    parser.add_argument("--output", required=True, help="Output JSON file for comments")
    parser.add_argument("--delay", type=float, default=3.0, help="Seconds between requests (default: 3.0)")
    parser.add_argument("--limit", type=int, help="Max posts to process")
    parser.add_argument("--no-skip", action="store_true", help="Don't skip already scraped posts")
    parser.add_argument("--visible", action="store_true", help="Show browser window")

    args = parser.parse_args()

    # Load posts
    with open(args.posts_file, 'r') as f:
        posts = json.load(f)

    if args.limit:
        posts = posts[:args.limit]

    print(f"Loaded {len(posts)} posts from {args.posts_file}", file=sys.stderr)

    # Initialize scraper
    scraper = SkoolCommentScraper(headless=not args.visible)

    try:
        scraper.start()
        scraper.scrape_comments_for_posts(
            posts,
            args.output,
            delay=args.delay,
            skip_existing=not args.no_skip
        )
    finally:
        scraper.stop()


if __name__ == "__main__":
    main()
