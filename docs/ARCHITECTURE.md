# Architecture — How Everything Connects

## Overview

This setup has four layers that work together:

```
Rules (always loaded)
  ↓ inform
Agents (spawned on demand)
  ↓ use
Skills (invoked via / commands)
  ↓ run
Hooks + Scripts (event-driven automation)
```

## Layer 1: Rules

Three rule files in `~/.claude/rules/` are loaded into every Claude Code session automatically.

### style.md
Governs how Claude writes code: concise, no over-engineering, minimal comments, only validate at system boundaries. Prevents the common AI tendency to add unnecessary abstractions.

### workflow.md
Defines two key patterns:

**Self-Anneal Loop**: When something breaks → fix it → update docs → system gets stronger. Treats errors as learning opportunities that improve the setup permanently.

**Design & Build Loop**: Write code → code-reviewer (parallel) → qa (parallel) → fix issues → ship. Non-trivial code doesn't ship without both review and test passing.

### project-docs.md
Every project gets standard documentation: CLAUDE.md (context for Claude), DEVLOG.md (session journal), PRD.md (requirements), .env.example. The `project-init` agent can scaffold these automatically.

## Layer 2: Agents

Five custom agents defined in `~/.claude/agents/`. These are spawned as subagents by Claude Code using the Task tool.

### code-reviewer (Sonnet)
**Tools**: Read, Write

Reviews code with zero prior context — intentionally. This forces evaluation on the code's own merits without bias. Checks correctness, readability, performance, security, and error handling at system boundaries. Outputs a structured review with PASS/PASS WITH NOTES/NEEDS CHANGES verdict.

### qa (Sonnet)
**Tools**: Read, Write, Bash

Generates tests, runs them, and reports results. Covers happy path, edge cases, and error cases. Does not modify original code — only creates test files. Supports Python (pytest), JavaScript (vitest/node test), and bash scripts.

### research (Sonnet)
**Tools**: Read, Glob, Grep, WebSearch, WebFetch

Deep research agent for investigations that need many searches. Breaks questions into sub-questions, searches web and files, synthesizes with citations. Returns concise findings — the parent agent doesn't want a novel.

### project-init (Sonnet)
**Tools**: Read, Write, Glob

Scaffolds missing documentation for projects. Scans the project structure, reads package.json/requirements.txt, discovers the stack, and generates CLAUDE.md + DEVLOG.md + .env.example from templates. Never overwrites existing files.

### market-research (Sonnet)
**Tools**: WebSearch, WebFetch, Read, Write, Bash

The heaviest agent. Runs 15-35 search queries across Web, Reddit (site:reddit.com), and X (site:x.com) to validate a business idea. Produces a structured report with verdicts on problem validation, market size, and competition. Spawned via the market-research skill's intake flow.

## Layer 3: Skills

32 skill folders in `~/.claude/skills/`. Each has a `SKILL.md` defining the skill's trigger, instructions, and often a `scripts/` subfolder with Python/bash automation.

Skills are invoked via `/skill-name` in Claude Code. They expand into full prompts that guide Claude through the skill's workflow.

### How Skills Work

```
User types: /scrape-leads "plumbers in Austin"
    ↓
Claude reads: ~/.claude/skills/scrape-leads/SKILL.md
    ↓
SKILL.md contains: instructions, API endpoints, script paths
    ↓
Claude runs: scripts/scrape.py with parameters
    ↓
Output: structured lead data in Google Sheets or CSV
```

### Skill Categories

| Category | Skills | Common Pattern |
|----------|--------|---------------|
| **Lead Gen** | scrape-leads, gmaps-leads, classify-leads, casualize-names | Apify scraping → LLM enrichment → Sheets output |
| **Cold Email** | instantly-campaigns, instantly-autoreply, welcome-email, onboarding-kickoff | API calls to Instantly/email service |
| **Content** | youtube-outliers, cross-niche-outliers, title-variants, humanizer | YouTube API → analysis → output |
| **Video** | video-edit, pan-3d-transition, recreate-thumbnails | Python scripts with ffmpeg/Remotion |
| **Dev Tools** | security-review, design-website, modal-deploy, local-server | Direct Claude analysis or CLI tools |
| **Research** | market-research, web-research, literature-research, last30days | Web search → synthesis → structured report |
| **Email Mgmt** | gmail-inbox, gmail-label | Google API via Python scripts |
| **Community** | skool-monitor, skool-rag | Browser automation / vector search |
| **Automation** | add-webhook, create-proposal, upwork-apply | API integrations |

## Layer 4: Hooks + Scripts

### Notification Hooks

Configured in `settings.json` under `hooks`:

```
Stop event         → notify.ps1 / notify.sh
AskUserQuestion    → notify.ps1 / notify.sh
```

When Claude finishes a task or asks a question, a notification fires. On Windows this plays an audio file (custom MP3 or Windows chimes). On Mac/Linux it sends terminal bell. Over SSH, it sends a UDP ping to the SSH client IP.

### Status Line

`statusline-command.sh` receives JSON from Claude Code via stdin and renders:

```
Sonnet 4.6  my-project  ████████░░ 82%
```

Color-coded: green (<60%), yellow (60-80%), red (>80%).

### Web Search Script

`scripts/web-search.py` uses DuckDuckGo's API via the `ddgs` Python package. This exists because Claude Code's built-in WebSearch tool is geo-restricted to the US. The script works from anywhere.

```bash
python ~/.claude/scripts/web-search.py "query" --max 10 --region us-en --json
```

## How the Build Loop Flows

Here's a concrete example of the full system working together:

```
1. You ask Claude to "add pagination to the users table"

2. Claude reads the rules:
   - style.md: keep it simple, no over-engineering
   - workflow.md: use the build loop for non-trivial code

3. Claude writes the pagination code

4. Claude spawns two agents in parallel:
   - code-reviewer: reads the new code, checks for issues
   - qa: generates pagination tests, runs them

5. Both agents report back:
   - code-reviewer: "PASS WITH NOTES — consider edge case for empty results"
   - qa: "5/5 tests passed"

6. Claude fixes the edge case, re-runs the review

7. Code ships
```

## Data Flow Diagram

```
~/.claude/
├── CLAUDE.md          ← loaded every session (global instructions)
├── settings.json      ← hooks config, permissions, env vars, plugins
├── statusline-command.sh ← renders status bar (receives JSON via stdin)
│
├── rules/
│   ├── style.md       ← loaded every session (code style)
│   ├── workflow.md    ← loaded every session (build loop, devlog)
│   └── project-docs.md ← loaded every session (doc standards)
│
├── agents/
│   ├── code-reviewer.md ← spawned by Task tool when reviewing code
│   ├── qa.md            ← spawned by Task tool when testing code
│   ├── research.md      ← spawned for deep investigations
│   ├── project-init.md  ← spawned to scaffold project docs
│   └── market-research.md ← spawned for market validation
│
├── hooks/
│   ├── notify.ps1       ← triggered on Stop/AskUserQuestion (Windows)
│   ├── notify.sh        ← triggered on Stop/AskUserQuestion (Mac/Linux)
│   ├── play-notification.ps1 ← audio player (Windows)
│   └── play-notification.sh  ← terminal bell (Mac/Linux)
│
├── scripts/
│   └── web-search.py    ← called by Claude when WebSearch is geo-blocked
│
└── skills/
    └── [32 folders]     ← invoked via /skill-name, each has SKILL.md + scripts/
```
