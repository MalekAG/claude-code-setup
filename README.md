# Claude Code Power-User Setup

A battle-tested Claude Code configuration with 5 custom agents, 32 skills, notification hooks, and workflow rules. Built over months of daily use for software engineering, lead generation, content creation, and business automation.

## What's Inside

| Category | Count | Description |
|----------|-------|-------------|
| **Agents** | 5 | code-reviewer, qa, research, project-init, market-research |
| **Skills** | 32 | Lead gen, cold email, content, video editing, security, dev tools |
| **Rules** | 3 | Code style, workflow (self-anneal + build loop), project docs standard |
| **Hooks** | 4 | Desktop/SSH notifications on Stop and AskUserQuestion events |
| **Scripts** | 1 | DuckDuckGo web search (bypasses Claude Code's geo-restriction) |
| **Status Line** | 1 | Shows model, folder name, and context usage with color-coded progress bar |

## Quick Start

### Option A: Let Claude Install It

```bash
git clone https://github.com/MalekAG/claude-code-setup.git
cd claude-code-setup
# Open Claude Code here — it reads CLAUDE.md and knows how to install everything
```

### Option B: Run the Installer

```bash
git clone https://github.com/MalekAG/claude-code-setup.git
cd claude-code-setup
bash install.sh
```

### Option C: Manual Installation

See [docs/SETUP-GUIDE.md](docs/SETUP-GUIDE.md) for step-by-step instructions.

## Prerequisites

- **Claude Code CLI** (installed and authenticated)
- **Git Bash** (Windows only — install via [Git for Windows](https://gitforwindows.org/))
- **Python 3** (optional — only needed for `web-search.py` and some skill scripts)
- **jq** (for the status line script — usually pre-installed on Mac/Linux)

## The Build Loop

The core workflow this setup enforces:

```
Write code → code-reviewer (reports issues) → qa (runs tests) → Fix → Ship
```

Both agents run in parallel. You only ship after both pass. This catches bugs before they reach production without slowing you down.

## Agents

| Agent | Model | Purpose |
|-------|-------|---------|
| `code-reviewer` | Sonnet | Zero-context code review. Evaluates correctness, readability, performance, security. |
| `qa` | Sonnet | Generates tests, runs them, reports pass/fail. Covers happy path, edge cases, errors. |
| `research` | Sonnet | Deep research with web + file access. Synthesizes findings with citations. |
| `project-init` | Sonnet | Scaffolds missing docs (CLAUDE.md, DEVLOG.md, .env.example) for any project. |
| `market-research` | Sonnet | Runs 15-35 search queries across Web, Reddit, X. Produces structured market reports. |

## Skills by Category

### Development Tools
| Skill | Description |
|-------|-------------|
| `security-review` | OWASP Top 10 scan, secret detection, auth audit |
| `design-website` | Generate premium website mockups |
| `modal-deploy` | Deploy scripts to Modal cloud |
| `local-server` | Run locally with Cloudflare tunneling |
| `generate-report` | PDF report generation |
| `interview` | PRD interview — uncovers hidden assumptions |

### Lead Generation
| Skill | Description |
|-------|-------------|
| `scrape-leads` | Apify-powered lead scraping + LLM classification |
| `gmaps-leads` | Google Maps scraping with contact enrichment |
| `classify-leads` | LLM-based lead classification |
| `casualize-names` | Formal → casual name conversion for cold email |

### Cold Email & Outreach
| Skill | Description |
|-------|-------------|
| `instantly-campaigns` | Create A/B tested cold email campaigns |
| `instantly-autoreply` | Auto-generate replies using knowledge bases |
| `welcome-email` | Welcome email sequences for new clients |
| `onboarding-kickoff` | Full post-kickoff automation pipeline |
| `create-proposal` | PandaDoc proposal generation |
| `upwork-apply` | Scrape Upwork jobs + generate proposals |

### Content & YouTube
| Skill | Description |
|-------|-------------|
| `youtube-outliers` | Find viral videos in your niche |
| `cross-niche-outliers` | Find viral videos from adjacent niches |
| `title-variants` | Generate YouTube title variations |
| `recreate-thumbnails` | Face-swap thumbnails using AI |
| `video-edit` | Remove silences + add 3D transitions |
| `pan-3d-transition` | 3D pan/swivel video transitions |
| `humanizer` | Remove AI writing patterns from text |

### Email & Communication
| Skill | Description |
|-------|-------------|
| `gmail-inbox` | Multi-account Gmail management |
| `gmail-label` | Auto-label emails (Action/Waiting/Reference) |

### Community & Social
| Skill | Description |
|-------|-------------|
| `skool-monitor` | Monitor and interact with Skool communities |
| `skool-rag` | RAG search over Skool community content |

### Research
| Skill | Description |
|-------|-------------|
| `market-research` | Comprehensive market validation across Web/Reddit/X |
| `web-research` | Structured web research approach |
| `literature-research` | Academic literature and PubMed search |
| `last30days` | Research last 30 days on Reddit/X/Web for any topic |

### Automation
| Skill | Description |
|-------|-------------|
| `add-webhook` | Add Modal webhooks for event triggers |

## Customization

### Change the Notification Sound

Place any `.mp3` file at `~/.claude/notification.mp3`. Falls back to Windows chimes if not found. On Mac/Linux, notifications use terminal bell (`\a`).

### Adjust Permissions

Edit `~/.claude/settings.json`:
- `"defaultMode": "default"` — asks before each tool use (recommended)
- `"defaultMode": "bypassPermissions"` — no permission prompts (power user — only if you trust all installed skills/agents)
- `"allow": [...]` — pre-approve specific tools even in default mode

### Enable/Disable Plugins

The `enabledPlugins` section controls Claude Code plugins (installed separately via the plugin system). Toggle `true`/`false` as needed.

### Model Overrides

```json
"ANTHROPIC_DEFAULT_HAIKU_MODEL": "claude-sonnet-4-6",
"ANTHROPIC_DEFAULT_SONNET_MODEL": "claude-sonnet-4-6"
```

This routes all "haiku" and "sonnet" subagent requests to Sonnet 4.6. Change these to use different models for different agent tiers.

## Documentation

- [CLAUDE.md](CLAUDE.md) — AI-readable installation guide (Claude reads this automatically)
- [docs/SETUP-GUIDE.md](docs/SETUP-GUIDE.md) — Manual installation steps
- [docs/SKILLS-CATALOG.md](docs/SKILLS-CATALOG.md) — Full skill catalog with API key requirements
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — How agents, rules, hooks, and skills connect

## License

MIT
