#!/usr/bin/env python3
"""
Skool unread posts fetcher - retrieves posts with new activity you haven't seen.

Uses Skool's native ?filter=unread parameter to fetch posts where:
- You've never viewed the post (myView is None)
- There are new comments since you last viewed (lastComment > myView)
"""

import os
import sys
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()


class SkoolUnreads:
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

    def get_unreads(self, community_slug, max_posts=100, since_hours=None):
        """
        Get all unread posts from a community.

        Returns posts where you either:
        - Have never viewed the post
        - Have new comments since your last view

        Args:
            community_slug: The community identifier (e.g., 'makerschool')
            max_posts: Maximum posts to return (default: 100)
            since_hours: Only return posts created within this many hours (default: None = all)

        Returns:
            List of post dicts with unread metadata
        """
        posts = []
        current_page = 1
        seen_ids = set()
        label_map = {}  # Cache label ID -> display name

        # Calculate cutoff time if since_hours specified
        cutoff = None
        if since_hours:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
            print(f"Filtering to posts since: {cutoff.strftime('%Y-%m-%d %H:%M UTC')}", file=sys.stderr)

        while len(posts) < max_posts:
            # Use fl=unr (the correct Skool unread filter)
            url = f"{self.base_url}/{community_slug}?c=&s=newest&fl=unr"
            if current_page > 1:
                url += f"&p={current_page}"

            print(f"Fetching unread page {current_page}...", file=sys.stderr)

            try:
                response = self.session.get(url)
                response.raise_for_status()
            except requests.exceptions.HTTPError as e:
                print(f"HTTP error: {e}", file=sys.stderr)
                break

            next_data = self._extract_next_data(response.text)
            if not next_data:
                print("Could not extract Next.js data", file=sys.stderr)
                break

            page_props = next_data.get('props', {}).get('pageProps', {})
            post_trees = page_props.get('postTrees', [])

            # Build label map from group data (only on first page)
            if not label_map:
                current_group = page_props.get('currentGroup', {})
                for label in current_group.get('labels', []):
                    label_id = label.get('id')
                    display_name = label.get('metadata', {}).get('displayName', 'Unknown')
                    label_map[label_id] = display_name

            if not post_trees:
                break

            new_this_page = 0
            stop_pagination = False

            for tree in post_trees:
                if len(posts) >= max_posts:
                    break

                post = tree.get('post', {})
                post_id = post.get('id')

                if post_id in seen_ids:
                    continue
                seen_ids.add(post_id)

                # Check time filter
                created_at = post.get('createdAt')
                if cutoff and created_at:
                    try:
                        post_time = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                        if post_time < cutoff:
                            stop_pagination = True
                            continue  # Skip this post but check remaining on page
                    except:
                        pass

                metadata = post.get('metadata', {})
                user = post.get('user', {})

                # Determine unread reason
                my_view = metadata.get('myView')
                last_comment = metadata.get('lastComment')

                if my_view is None:
                    unread_reason = "never_viewed"
                elif last_comment and last_comment > my_view:
                    unread_reason = "new_comments"
                else:
                    unread_reason = "unknown"

                # Get category/label
                label_id = post.get('labelId')
                category = label_map.get(label_id, 'Uncategorized') if label_id else 'Uncategorized'

                posts.append({
                    'id': post_id,
                    'title': metadata.get('title', 'No title'),
                    'slug': post.get('name'),
                    'content': metadata.get('content', ''),
                    'author': user.get('name', 'Unknown'),
                    'author_id': user.get('id'),
                    'created_at': created_at,
                    'category': category,
                    'category_id': label_id,
                    'likes': metadata.get('upvotes', 0),
                    'comments': metadata.get('comments', 0),
                    'pinned': metadata.get('pinned', False),
                    'my_vote': metadata.get('myVote'),
                    'my_view': my_view,
                    'last_comment': last_comment,
                    'unread_reason': unread_reason,
                    'url': f"{self.base_url}/{community_slug}/{post.get('name')}",
                })
                new_this_page += 1

            if new_this_page == 0 or stop_pagination:
                break

            current_page += 1

        return posts

    def get_unread_count(self, community_slug):
        """Get total unread count without fetching all posts."""
        url = f"{self.base_url}/{community_slug}?c=&s=newest&fl=unr"
        response = self.session.get(url)
        response.raise_for_status()
        next_data = self._extract_next_data(response.text)
        if next_data:
            page_props = next_data.get('props', {}).get('pageProps', {})
            return page_props.get('total', 0)
        return 0

    def get_unread_summary(self, community_slug, since_hours=None, max_posts=500):
        """
        Get a categorized summary of unread posts.

        Args:
            community_slug: The community identifier
            since_hours: Only include posts from last N hours
            max_posts: Maximum posts to fetch (default: 500)

        Returns:
            Dict with 'total_all_time', 'never_viewed' and 'new_comments' lists
        """
        total_all_time = self.get_unread_count(community_slug)
        unreads = self.get_unreads(community_slug, max_posts=max_posts, since_hours=since_hours)

        summary = {
            'total_all_time': total_all_time,
            'total_filtered': len(unreads),
            'never_viewed': [],
            'new_comments': [],
        }

        for post in unreads:
            if post['unread_reason'] == 'never_viewed':
                summary['never_viewed'].append(post)
            else:
                summary['new_comments'].append(post)

        return summary


def format_post(post, index):
    """Format a single post for display."""
    created = post['created_at']
    if created:
        try:
            dt = datetime.fromisoformat(created.replace('Z', '+00:00'))
            created_str = dt.strftime('%Y-%m-%d %H:%M UTC')
        except:
            created_str = created
    else:
        created_str = 'Unknown'

    reason_emoji = "🆕" if post['unread_reason'] == 'never_viewed' else "💬"
    category = post.get('category', 'Uncategorized')

    lines = [
        f"{index}. {reason_emoji} {post['title']}",
        f"   By: {post['author']} | {created_str}",
        f"   Category: {category}",
        f"   Likes: {post['likes']} | Comments: {post['comments']}",
        f"   URL: {post['url']}",
    ]
    return '\n'.join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Fetch unread Skool posts")
    parser.add_argument("--community", default="makerschool", help="Community slug")
    parser.add_argument("--limit", type=int, default=500, help="Max posts to fetch")
    parser.add_argument("--since", type=int, help="Only posts from last N hours (e.g., --since 48)")
    parser.add_argument("--output", help="Output JSON file")
    parser.add_argument("--summary", action="store_true", help="Show categorized summary")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--count-only", action="store_true", help="Just show total unread count")

    args = parser.parse_args()

    try:
        fetcher = SkoolUnreads()

        if args.count_only:
            count = fetcher.get_unread_count(args.community)
            if args.json:
                print(json.dumps({'total_unread': count}))
            else:
                print(f"📬 Total unread: {count}")
            return

        if args.summary:
            summary = fetcher.get_unread_summary(args.community, since_hours=args.since, max_posts=args.limit)

            if args.json:
                print(json.dumps(summary, indent=2))
            else:
                print(f"\n📬 Unread Posts Summary for {args.community}")
                print(f"{'='*60}")
                print(f"Total unread (all time): {summary['total_all_time']}")
                if args.since:
                    print(f"Unread in last {args.since}h: {summary['total_filtered']}")
                print(f"  🆕 Never viewed: {len(summary['never_viewed'])}")
                print(f"  💬 New comments: {len(summary['new_comments'])}")

                if summary['never_viewed']:
                    print(f"\n🆕 NEVER VIEWED ({len(summary['never_viewed'])})")
                    print("-" * 40)
                    for i, post in enumerate(summary['never_viewed'][:20], 1):
                        print(format_post(post, i))
                        print()

                if summary['new_comments']:
                    print(f"\n💬 NEW COMMENTS ({len(summary['new_comments'])})")
                    print("-" * 40)
                    for i, post in enumerate(summary['new_comments'][:20], 1):
                        print(format_post(post, i))
                        print()
        else:
            posts = fetcher.get_unreads(args.community, max_posts=args.limit, since_hours=args.since)

            if args.json:
                print(json.dumps(posts, indent=2))
            else:
                time_label = f" (last {args.since}h)" if args.since else ""
                print(f"\n📬 {len(posts)} Unread Posts in {args.community}{time_label}")
                print("=" * 60)

                for i, post in enumerate(posts, 1):
                    print(format_post(post, i))
                    print()

        if args.output:
            if args.summary:
                data = fetcher.get_unread_summary(args.community, since_hours=args.since, max_posts=args.limit)
            else:
                data = fetcher.get_unreads(args.community, max_posts=args.limit, since_hours=args.since)
            with open(args.output, 'w') as f:
                json.dump(data, f, indent=2)
            print(f"\nSaved to {args.output}", file=sys.stderr)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
