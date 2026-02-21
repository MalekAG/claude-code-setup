#!/usr/bin/env python3
"""
Skool API client for interacting with Skool communities via their internal API.
Uses browser cookies for authentication.
Supports read and write operations: create posts, reply, like, search.
"""

import os
import sys
import json
import requests
import re
from datetime import datetime
from dotenv import load_dotenv
from bs4 import BeautifulSoup

load_dotenv()

class SkoolClient:
    def __init__(self, auth_token=None, client_id=None, aws_waf_token=None):
        self.base_url = "https://www.skool.com"
        self.api_base_url = "https://api2.skool.com"

        self.auth_token = auth_token or os.getenv("SKOOL_AUTH_TOKEN")
        self.client_id = client_id or os.getenv("SKOOL_CLIENT_ID")
        self.aws_waf_token = aws_waf_token or os.getenv("SKOOL_AWS_WAF_TOKEN")

        if not self.auth_token:
            raise ValueError("SKOOL_AUTH_TOKEN not found in environment")

        self.session = requests.Session()
        self._update_headers()

        # Set cookies
        self.session.cookies.set('auth_token', self.auth_token, domain='.skool.com')
        if self.client_id:
            self.session.cookies.set('client_id', self.client_id, domain='.skool.com')
        if self.aws_waf_token:
            self.session.cookies.set('aws-waf-token', self.aws_waf_token, domain='.skool.com')

    def _update_headers(self):
        """Update session headers for API requests."""
        self.session.headers.update({
            'accept': '*/*',
            'accept-language': 'en-US,en;q=0.9',
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36',
            'origin': 'https://www.skool.com',
            'referer': 'https://www.skool.com/',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
        })

        # Add AWS WAF token to headers if available
        if self.aws_waf_token:
            self.session.headers.update({
                'x-aws-waf-token': self.aws_waf_token
            })

    def get_community_info(self, community_slug):
        """Get basic info about a community."""
        url = f"{self.base_url}/{community_slug}"
        response = self.session.get(url)
        response.raise_for_status()
        return response.text

    def get_group_id(self, community_slug):
        """
        Extract group_id from a community page.
        This is required for creating posts.
        """
        html = self.get_community_info(community_slug)
        soup = BeautifulSoup(html, 'html.parser')
        next_data_script = soup.find('script', {'id': '__NEXT_DATA__'})

        if not next_data_script:
            raise Exception("Could not find __NEXT_DATA__ in page")

        try:
            data = json.loads(next_data_script.string)
            group = data.get('props', {}).get('pageProps', {}).get('currentGroup', {})
            group_id = group.get('id')

            if not group_id:
                raise Exception("Could not extract group_id from page data")

            return group_id
        except json.JSONDecodeError:
            raise Exception("Could not parse __NEXT_DATA__ JSON")

    def create_post(self, group_id, title, content, labels=None, follow=True):
        """
        Create a new post in a community.

        Args:
            group_id: Community group ID (get via get_group_id())
            title: Post title
            content: Post content (markdown supported)
            labels: Optional label ID (category/tag)
            follow: Whether to follow the post (default True)

        Returns:
            dict: API response with post data
        """
        url = f"{self.api_base_url}/posts"
        params = {'follow': 'true' if follow else 'false'}

        payload = {
            "post_type": "generic",
            "group_id": group_id,
            "metadata": {
                "title": title,
                "content": content,
                "attachments": "",
                "labels": labels or "",
                "action": 0,
                "video_ids": ""
            }
        }

        headers = {'content-type': 'application/json'}
        response = self.session.post(url, params=params, json=payload, headers=headers)
        response.raise_for_status()

        return response.json()

    def reply_to_post(self, group_id, post_id, content, follow=False):
        """
        Reply to an existing post (create a comment).

        Args:
            group_id: Community group ID
            post_id: ID of post to reply to (root_id and parent_id)
            content: Comment content
            follow: Whether to follow the post (default False)

        Returns:
            dict: API response with comment data
        """
        url = f"{self.api_base_url}/posts"
        params = {'follow': 'true' if follow else 'false'}

        payload = {
            "post_type": "comment",
            "group_id": group_id,
            "root_id": post_id,
            "parent_id": post_id,
            "metadata": {
                "title": "",
                "content": content,
                "attachments": "",
                "action": 0,
                "video_ids": ""
            }
        }

        headers = {'content-type': 'application/json'}
        response = self.session.post(url, params=params, json=payload, headers=headers)
        response.raise_for_status()

        return response.json()

    def like_post(self, post_id):
        """
        Like a post or comment.

        Args:
            post_id: ID of post to like

        Returns:
            dict: API response
        """
        url = f"{self.api_base_url}/posts/{post_id}/vote"
        payload = {"old": "", "new": "up"}

        headers = {'content-type': 'application/json'}
        response = self.session.put(url, json=payload, headers=headers)
        response.raise_for_status()

        return response.json()

    def unlike_post(self, post_id):
        """
        Remove like from a post or comment.

        Args:
            post_id: ID of post to unlike

        Returns:
            dict: API response
        """
        url = f"{self.api_base_url}/posts/{post_id}/vote"
        payload = {"old": "up", "new": ""}

        headers = {'content-type': 'application/json'}
        response = self.session.put(url, json=payload, headers=headers)
        response.raise_for_status()

        return response.json()

    def search_posts(self, community_slug, query, build_id="1763672899107"):
        """
        Search for posts in a community.

        Args:
            community_slug: Community slug (e.g., "makerschool")
            query: Search query string
            build_id: Next.js build ID (can usually stay static)

        Returns:
            dict: Search results
        """
        url = f"{self.base_url}/_next/data/{build_id}/{community_slug}/-/search.json"
        params = {
            'q': query,
            'group': community_slug
        }

        headers = {'x-nextjs-data': '1'}
        response = self.session.get(url, params=params, headers=headers)
        response.raise_for_status()

        return response.json()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Skool API client with write operations")
    parser.add_argument("command",
                       choices=['test', 'create', 'reply', 'like', 'unlike', 'search', 'group-id'],
                       help="Command to run")
    parser.add_argument("--community", default="makerschool", help="Community slug")
    parser.add_argument("--title", help="Post title (for create)")
    parser.add_argument("--content", help="Post/comment content")
    parser.add_argument("--post-id", help="Post ID (for reply/like/unlike)")
    parser.add_argument("--group-id", help="Group ID (for create/reply)")
    parser.add_argument("--query", help="Search query")
    parser.add_argument("--labels", help="Label ID for post category")

    args = parser.parse_args()

    try:
        client = SkoolClient()

        if args.command == 'test':
            print("Testing connection to Skool...")
            html = client.get_community_info(args.community)
            print(f"✓ Successfully connected to {args.community}")
            print(f"Response length: {len(html)} characters")

        elif args.command == 'group-id':
            print(f"Getting group_id for {args.community}...")
            group_id = client.get_group_id(args.community)
            print(f"Group ID: {group_id}")

        elif args.command == 'create':
            if not args.title or not args.content:
                print("Error: --title and --content are required for create")
                sys.exit(1)

            if not args.group_id:
                print(f"Group ID not provided, fetching from {args.community}...")
                group_id = client.get_group_id(args.community)
            else:
                group_id = args.group_id

            print(f"Creating post in {args.community}...")
            result = client.create_post(group_id, args.title, args.content, labels=args.labels)
            print("✓ Post created successfully!")
            print(json.dumps(result, indent=2))

        elif args.command == 'reply':
            if not args.content or not args.post_id:
                print("Error: --content and --post-id are required for reply")
                sys.exit(1)

            if not args.group_id:
                print(f"Group ID not provided, fetching from {args.community}...")
                group_id = client.get_group_id(args.community)
            else:
                group_id = args.group_id

            print(f"Replying to post {args.post_id}...")
            result = client.reply_to_post(group_id, args.post_id, args.content)
            print("✓ Reply posted successfully!")
            print(json.dumps(result, indent=2))

        elif args.command == 'like':
            if not args.post_id:
                print("Error: --post-id is required for like")
                sys.exit(1)

            print(f"Liking post {args.post_id}...")
            result = client.like_post(args.post_id)
            print("✓ Post liked successfully!")
            print(json.dumps(result, indent=2))

        elif args.command == 'unlike':
            if not args.post_id:
                print("Error: --post-id is required for unlike")
                sys.exit(1)

            print(f"Unliking post {args.post_id}...")
            result = client.unlike_post(args.post_id)
            print("✓ Post unliked successfully!")
            print(json.dumps(result, indent=2))

        elif args.command == 'search':
            if not args.query:
                print("Error: --query is required for search")
                sys.exit(1)

            print(f"Searching for '{args.query}' in {args.community}...")
            result = client.search_posts(args.community, args.query)
            print(json.dumps(result, indent=2))

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
