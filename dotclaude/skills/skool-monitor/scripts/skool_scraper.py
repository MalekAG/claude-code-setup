#!/usr/bin/env python3
"""
Skool community scraper - extracts posts, members, and activity from Skool communities.
Uses reverse-engineered internal API via browser cookies.
"""

import os
import sys
import json
import re
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

class SkoolScraper:
    def __init__(self, auth_token=None, client_id=None):
        self.base_url = "https://www.skool.com"
        self.auth_token = auth_token or os.getenv("SKOOL_AUTH_TOKEN")
        self.client_id = client_id or os.getenv("SKOOL_CLIENT_ID")

        if not self.auth_token:
            raise ValueError("SKOOL_AUTH_TOKEN not found in environment")

        self.session = requests.Session()
        self.session.headers.update({
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'accept-language': 'en-US,en;q=0.9',
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        })

        # Set cookies
        self.session.cookies.set('auth_token', self.auth_token, domain='.skool.com')
        if self.client_id:
            self.session.cookies.set('client_id', self.client_id, domain='.skool.com')

    def _extract_next_data(self, html):
        """Extract Next.js data from HTML."""
        soup = BeautifulSoup(html, 'html.parser')
        next_data_script = soup.find('script', {'id': '__NEXT_DATA__'})

        if not next_data_script:
            return None

        try:
            return json.loads(next_data_script.string)
        except json.JSONDecodeError:
            return None

    def get_community_posts(self, community_slug, max_posts=50, start_page=1, output_file=None, delay=1.0):
        """
        Get recent posts from a community with pagination support.
        Returns a list of post dictionaries with title, author, content, etc.

        Args:
            community_slug: The community identifier (e.g., 'makerschool')
            max_posts: Maximum number of posts to retrieve (default: 50)
            start_page: Page number to start from (default: 1)
            output_file: Optional file path to write posts incrementally (safer for large scrapes)
            delay: Seconds to wait between requests (default: 1.0) - be respectful to servers
        """
        posts = []
        seen_ids = set()
        current_page = start_page

        # If output_file specified, initialize or load existing data
        if output_file:
            import os
            if os.path.exists(output_file):
                try:
                    with open(output_file, 'r') as f:
                        posts = json.load(f)
                    # Deduplicate existing posts
                    unique_posts = []
                    for p in posts:
                        if p['id'] not in seen_ids:
                            seen_ids.add(p['id'])
                            unique_posts.append(p)
                    posts = unique_posts
                    print(f"Loaded {len(posts)} unique posts from {output_file}", file=sys.stderr)
                except:
                    posts = []

        while len(posts) < max_posts:
            # Build URL with pagination
            url = f"{self.base_url}/{community_slug}"
            if current_page > 1:
                url += f"?p={current_page}"

            print(f"Fetching page {current_page}... ({len(posts)} unique posts so far)", file=sys.stderr)

            try:
                response = self.session.get(url)
                response.raise_for_status()
            except requests.exceptions.HTTPError as e:
                print(f"HTTP error on page {current_page}: {e}", file=sys.stderr)
                # Save progress and exit gracefully
                if output_file and posts:
                    with open(output_file, 'w') as f:
                        json.dump(posts, f, indent=2)
                    print(f"Saved {len(posts)} posts before error", file=sys.stderr)
                raise

            next_data = self._extract_next_data(response.text)
            if not next_data:
                raise Exception("Could not extract Next.js data from page")

            new_posts_this_page = 0
            try:
                page_props = next_data.get('props', {}).get('pageProps', {})

                # Skool uses postTrees structure
                post_trees = page_props.get('postTrees', [])

                # If no posts on this page, we've reached the end
                if not post_trees:
                    print(f"No more posts found at page {current_page}", file=sys.stderr)
                    break

                for tree in post_trees:
                    if len(posts) >= max_posts:
                        break

                    post = tree.get('post', {})
                    post_id = post.get('id')

                    # Skip duplicates
                    if post_id in seen_ids:
                        continue

                    seen_ids.add(post_id)
                    metadata = post.get('metadata', {})
                    user = post.get('user', {})

                    posts.append({
                        'id': post_id,
                        'title': metadata.get('title', 'No title'),
                        'slug': post.get('name'),
                        'content': metadata.get('content', ''),
                        'author': user.get('name', 'Unknown'),
                        'author_id': user.get('id'),
                        'created_at': post.get('createdAt'),
                        'likes': metadata.get('upvotes', 0),
                        'comments': metadata.get('comments', 0),
                        'pinned': metadata.get('pinned', False),
                        'my_vote': metadata.get('myVote'),
                        'url': f"{self.base_url}/{community_slug}/{post.get('name')}",
                        'raw': post
                    })
                    new_posts_this_page += 1

                # Write incrementally to file after each page
                if output_file and new_posts_this_page > 0:
                    with open(output_file, 'w') as f:
                        json.dump(posts, f, indent=2)

            except Exception as e:
                print(f"Error parsing posts: {e}")
                with open('.tmp/skool_debug_data.json', 'w') as f:
                    json.dump(next_data, f, indent=2)
                print("Saved raw data to .tmp/skool_debug_data.json for inspection")
                raise

            current_page += 1

            # Rate limiting - wait between requests
            if len(posts) < max_posts:
                time.sleep(delay)

        return posts

    def _find_posts_in_data(self, data, max_depth=5):
        """Recursively search for post-like data structures."""
        if max_depth == 0:
            return []

        posts = []

        if isinstance(data, dict):
            # Check if this dict looks like a post
            if ('title' in data or 'content' in data or 'body' in data) and ('id' in data or 'slug' in data):
                posts.append(data)

            # Recursively search all dict values
            for value in data.values():
                posts.extend(self._find_posts_in_data(value, max_depth - 1))

        elif isinstance(data, list):
            # Search all list items
            for item in data:
                posts.extend(self._find_posts_in_data(item, max_depth - 1))

        return posts

    def get_new_posts(self, community_slug, since_timestamp=None):
        """
        Get posts created after a specific timestamp.
        If since_timestamp is None, returns all recent posts.
        """
        all_posts = self.get_community_posts(community_slug, max_posts=100)

        if not since_timestamp:
            return all_posts

        # Filter posts by timestamp
        new_posts = []
        for post in all_posts:
            created_at = post.get('created_at')
            if created_at:
                # Parse timestamp (format may vary)
                try:
                    post_time = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    since_time = datetime.fromisoformat(since_timestamp.replace('Z', '+00:00'))
                    if post_time > since_time:
                        new_posts.append(post)
                except:
                    # If parsing fails, include the post
                    new_posts.append(post)

        return new_posts


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Skool community scraper")
    parser.add_argument("command", choices=['posts', 'new'], help="Command to run")
    parser.add_argument("--community", default="makerschool", help="Community slug")
    parser.add_argument("--limit", type=int, default=20, help="Number of posts to fetch")
    parser.add_argument("--start-page", type=int, default=1, help="Page to start from (skip already-fetched pages)")
    parser.add_argument("--delay", type=float, default=1.0, help="Seconds between requests (default: 1.0)")
    parser.add_argument("--since", help="ISO timestamp for filtering new posts")
    parser.add_argument("--output", help="Output JSON file")

    args = parser.parse_args()

    try:
        scraper = SkoolScraper()

        if args.command == 'posts':
            print(f"Fetching posts from {args.community} starting at page {args.start_page}...", file=sys.stderr)
            posts = scraper.get_community_posts(
                args.community,
                max_posts=args.limit,
                start_page=args.start_page,
                output_file=args.output,
                delay=args.delay
            )

            print(f"Found {len(posts)} posts:\n")
            for i, post in enumerate(posts, 1):
                # Format timestamp
                created = post['created_at']
                if created:
                    try:
                        dt = datetime.fromisoformat(created.replace('Z', '+00:00'))
                        created_str = dt.strftime('%Y-%m-%d %H:%M UTC')
                    except:
                        created_str = created
                else:
                    created_str = 'Unknown'

                print(f"{'='*80}")
                print(f"{i}. {post['title']}")
                print(f"By: {post['author']} | {created_str}")
                print(f"Likes: {post['likes']} | Comments: {post['comments']}")
                print(f"URL: {post['url']}")
                print(f"\n{post['content']}")
                print()

            if args.output:
                with open(args.output, 'w') as f:
                    json.dump(posts, f, indent=2)
                print(f"\nSaved {len(posts)} posts to {args.output}")

        elif args.command == 'new':
            print(f"Fetching new posts from {args.community} since {args.since}...")
            posts = scraper.get_new_posts(args.community, since_timestamp=args.since)

            print(f"Found {len(posts)} new posts")

            if args.output:
                with open(args.output, 'w') as f:
                    json.dump(posts, f, indent=2)
                print(f"Saved to {args.output}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
