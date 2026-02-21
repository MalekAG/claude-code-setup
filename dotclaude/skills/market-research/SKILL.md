---
name: market-research
description: This skill should be used when the user asks to "research a market", "validate an idea", "do market research", "analyze competition", "find market size", "validate a business idea", "size a market", "research competitors", or needs comprehensive market analysis across web, Reddit, and X sources.
argument-hint: 'SaaS for plumbers, AI meeting scheduler, indie game marketplace'
allowed-tools: Bash, Read, Write, Edit, AskUserQuestion, WebSearch, WebFetch, mcp__reddit__scrape_subreddit, mcp__reddit__search_reddit, mcp__reddit__get_posts, mcp__reddit__get_comments, mcp__reddit__scrape_post
---

# market-research: Comprehensive Market Research for Any Idea

Research ANY product or business idea across Web, Reddit, and X (Twitter). Validate the problem, size the market, map the competition, profile the customer, and identify distribution channels. Produce a structured markdown report with citations. No API keys required.

## Modes

Parse the user's invocation for depth flags:
- `--quick` → Faster, fewer queries (~15 total). Good for a quick gut check.
- (default) → Balanced (~25 total). Solid coverage across all categories.
- `--deep` → Comprehensive (~35 total). Leave no stone unturned.

Store: `DEPTH_MODE = quick | standard | deep`

---

## PHASE 1: Intake

### Step 1: Gather the idea

If the user provided their idea inline (e.g., `/market-research AI scheduling tool for plumbers`), parse it directly. Otherwise, use AskUserQuestion:

```
Tell me about your business/product idea. Include as much as you can:

- What's the product or service? (one-liner)
- What problem does it solve?
- Who's the target customer?
- What industry/category is it in?
- Any competitors you already know about?
```

### Step 2: Parse into variables

Extract and store:
- `IDEA_NAME` — short name for the product/idea
- `IDEA_ONELINER` — one-sentence description
- `PROBLEM` — the core problem it solves
- `TARGET_AUDIENCE` — who it's for (be specific)
- `INDUSTRY` — industry or market category
- `PRODUCT_CATEGORY` — the type of product (e.g., "scheduling software", "marketplace")
- `KNOWN_COMPETITORS` — list of known competitors (may be empty)
- `IDEA_SLUG` — lowercase, hyphenated, max 40 chars (for filename)

### Step 3: Confirm and start

If all variables are clear, display the parsed intent and proceed:

```
Researching: {IDEA_NAME}

Parsed intent:
- Idea: {IDEA_ONELINER}
- Problem: {PROBLEM}
- Audience: {TARGET_AUDIENCE}
- Industry: {INDUSTRY}
- Known competitors: {KNOWN_COMPETITORS or "none provided"}
- Mode: {DEPTH_MODE}

Starting research across Web, Reddit, and X. This typically takes 3-10 minutes.
```

If PROBLEM or TARGET_AUDIENCE cannot be inferred, ask ONE follow-up AskUserQuestion to fill the gaps. Maximum 2 total questions before research begins.

---

## PHASE 2: Query Generation

Read the query template library:
```
Read file: ~/.claude/skills/market-research/references/search-queries.md
```

Substitute the parsed variables into the templates. Select queries based on DEPTH_MODE per the depth table in the reference file.

Identify 3-6 relevant subreddits using the subreddit discovery table. If the domain is unclear, run one WebSearch: `"{INDUSTRY}" site:reddit.com` to find active communities.

---

## PHASE 3: Parallel Research Execution

Maximize parallelism. Run independent searches in the same tool-call batch.

### Step 0: Check Reddit MCP availability

Before running any Reddit queries, test MCP availability with a single probe call:
```
mcp__reddit__search_reddit(query="test", search_in="posts", limit=1)
```

- **If it succeeds** → set `REDDIT_MODE = mcp` and use MCP tools for all Reddit queries.
- **If it errors** (tool not found, connection refused, timeout) → set `REDDIT_MODE = websearch` and use the WebSearch fallback for all Reddit queries.

**WebSearch fallback mapping** (use when `REDDIT_MODE = websearch`):

| MCP Call | WebSearch Fallback |
|----------|--------------------|
| `mcp__reddit__search_reddit(query=Q)` | `WebSearch("{Q} site:reddit.com")` |
| `mcp__reddit__scrape_subreddit(subreddit=S)` | `WebSearch("{PROBLEM} OR {PRODUCT_CATEGORY} site:reddit.com/r/{S}")` |
| `mcp__reddit__scrape_post(url=U)` | `WebFetch(url=U, prompt="Extract the post title, body, and top comments with upvote counts")` |
| `mcp__reddit__get_posts(target=S, search_query=Q)` | `WebSearch("{Q} site:reddit.com/r/{S}")` |

When using fallback mode, note in the final report: "Reddit data collected via web search (MCP unavailable). Thread-level comment depth may be limited."

### Wave 1: Reddit + Web (parallel)

**Reddit** (use MCP tools or WebSearch fallback per `REDDIT_MODE`):
- Scrape top subreddits: `mcp__reddit__scrape_subreddit(subreddit, limit=50, scrape_comments=true)`
- Search for problem/industry: `mcp__reddit__search_reddit(query, search_in="both", limit=30)`

**Web + X (WebSearch — parallel with Reddit):**
- Run Problem Validation web queries
- Run Market Size web queries
- Run Competition web queries (including site:g2.com, site:producthunt.com)
- Run X queries using `site:x.com` scoping

Group all independent WebSearch calls into a single parallel batch.

### Wave 2: Remaining categories

- Run Customer web + X queries
- Run Distribution web + X queries
- Run competitor-specific Reddit searches if KNOWN_COMPETITORS provided

### Wave 3: Targeted follow-ups (if needed)

Review coverage. If any category is thin (< 3 data points):
- Scrape specific promising Reddit posts: `mcp__reddit__scrape_post(url, scrape_comments=true)` (or WebFetch fallback)
- Run broader web queries (use adjacent industry terms)
- Fetch high-value URLs with WebFetch

Track throughout:
- `REDDIT_THREADS` — count of Reddit threads/posts found
- `X_POSTS` — count of X results from site:x.com searches
- `WEB_PAGES` — count of web search queries run
- `SUBREDDITS` — list of subreddit names explored

---

## PHASE 4: Synthesis & Report

### Step 1: Synthesize per category

For each of the 5 categories, synthesize findings with source weighting:
- **Reddit/X**: HIGH weight. Real people, engagement signals (upvotes, likes, comments).
- **Web articles**: MEDIUM weight. Good for factual data (market size, pricing).
- **Company websites**: LOW weight for opinions (biased), HIGH for feature/pricing data.

Ground every finding in actual research data. Do not inject pre-existing knowledge as findings. If general knowledge adds useful context, label it: "[Note: based on general knowledge, not from this research]".

### Step 2: Generate the report

Read the report template:
```
Read file: ~/.claude/skills/market-research/references/report-template.md
```

Fill in the template. Every claim needs a citation:
- Reddit: `(r/{subreddit}, {N} upvotes)`
- X: `(@{handle} on X)` or `(X search: {N} posts mentioning this)`
- Web: `({source name})`

### Step 3: Assign verdicts

**Problem Validation verdict:**
- **Strong Signal**: 10+ organic mentions, people actively seeking solutions, workarounds described
- **Moderate Signal**: 3-10 mentions, some discussion but not urgent
- **Weak Signal**: Under 3 mentions, or only in marketing contexts (not organic)

**Competition verdict:**
- **Crowded**: 5+ direct competitors with funding/traction
- **Moderate**: 2-4 direct competitors
- **Blue Ocean**: 0-1 direct competitors

**Market verdict:**
- **Growing**: CAGR > 10% or strong trend signals
- **Stable**: CAGR 2-10%
- **Shrinking**: CAGR < 2% or declining signals

### Step 4: Save the report

Create output directory and save:
```bash
mkdir -p .tmp/market-research
```
Write to: `.tmp/market-research/{IDEA_SLUG}-{YYYY-MM-DD}.md`

### Step 5: Display summary

After saving, display to the user:

```
---
Market research complete for {IDEA_NAME}.

## Key Findings
- [Top 3-5 findings as bullet points]

## Verdicts
- Problem Validation: {Strong/Moderate/Weak Signal}
- Market: {Growing/Stable/Shrinking} — {size if found}
- Competition: {Crowded/Moderate/Blue Ocean}
- Distribution: {Clear channels / Needs creative approach}

## Research Stats
├─ 🟠 Reddit: {N} threads across r/{sub1}, r/{sub2}, ...
├─ 🔵 X: {N} posts analyzed
├─ 🌐 Web: {N} pages searched
└─ 📄 Report: .tmp/market-research/{IDEA_SLUG}-{date}.md

Want me to dive deeper into any section, or help plan next steps?
---
```

---

## PHASE 5: Follow-up

After the report, handle follow-up requests:

- **"Go deeper on [section]"** → Run targeted searches for that category, update report
- **"Help me plan next steps"** → Generate tactical action plan based on findings
- **"Compare [competitor A] vs [competitor B]"** → Deep-dive comparison
- **"What subreddits should I monitor?"** → List relevant subreddits with engagement levels

For follow-ups, do NOT re-run the entire pipeline. Use targeted searches only.

---

## Error Handling

- **Reddit MCP unavailable**: Detected automatically in Phase 3, Step 0. Uses WebSearch fallback mapping. Noted in report Methodology section.
- **Thin data in a category**: Broaden to adjacent industry terms. Report honestly rather than fabricating.
- **Very niche topic**: Try broader industry terms and adjacent audiences. Note the pivot in the report.

## Additional Resources

### Reference Files
- **`references/search-queries.md`** — Full query template library organized by category and depth mode
- **`references/report-template.md`** — Structured markdown template for the output report
