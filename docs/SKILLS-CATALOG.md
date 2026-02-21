# Skills Catalog

Complete reference for all 32 skills included in this setup.

## Quick Reference

| # | Skill | Category | API Keys Needed | Description |
|---|-------|----------|----------------|-------------|
| 1 | `add-webhook` | Automation | Modal CLI | Add Modal webhooks for event-driven execution |
| 2 | `casualize-names` | Lead Gen | None | Convert formal names to casual for cold email |
| 3 | `classify-leads` | Lead Gen | None (uses Claude) | LLM-based lead classification |
| 4 | `create-proposal` | Outreach | `PANDADOC_API_KEY` | Generate PandaDoc proposals from client info |
| 5 | `cross-niche-outliers` | Content | `YOUTUBE_API_KEY` | Find viral videos from adjacent niches |
| 6 | `design-website` | Dev Tools | None | Generate premium website mockups |
| 7 | `generate-report` | Dev Tools | None | Generate PDF reports (uses Open-Meteo) |
| 8 | `gmail-inbox` | Email | Google OAuth | Multi-account Gmail management |
| 9 | `gmail-label` | Email | Google OAuth | Auto-label emails (Action/Waiting/Reference) |
| 10 | `gmaps-leads` | Lead Gen | `APIFY_TOKEN` | Google Maps scraping + contact enrichment |
| 11 | `humanizer` | Content | None | Remove AI writing patterns from text |
| 12 | `instantly-autoreply` | Cold Email | `INSTANTLY_API_KEY` | Auto-generate replies to Instantly threads |
| 13 | `instantly-campaigns` | Cold Email | `INSTANTLY_API_KEY` | Create A/B tested cold email campaigns |
| 14 | `interview` | Dev Tools | None | PRD interview to uncover hidden assumptions |
| 15 | `last30days` | Research | None | Research last 30 days on Reddit/X/Web |
| 16 | `literature-research` | Research | None | Academic literature and PubMed search |
| 17 | `local-server` | Dev Tools | None | Run locally with Cloudflare tunneling |
| 18 | `market-research` | Research | None | Market validation across Web/Reddit/X |
| 19 | `modal-deploy` | Automation | Modal CLI | Deploy scripts to Modal cloud |
| 20 | `onboarding-kickoff` | Cold Email | Multiple* | Full post-kickoff client automation |
| 21 | `pan-3d-transition` | Video | None | 3D pan/swivel transition effects |
| 22 | `recreate-thumbnails` | Content | AI API** | Face-swap YouTube thumbnails |
| 23 | `scrape-leads` | Lead Gen | `APIFY_TOKEN` | Scrape + LLM classify + email enrich leads |
| 24 | `security-review` | Dev Tools | None | OWASP Top 10 scan + secret detection |
| 25 | `skool-monitor` | Community | Skool cookies | Monitor and interact with Skool communities |
| 26 | `skool-rag` | Community | Skool cookies | RAG search over Skool community content |
| 27 | `title-variants` | Content | None | Generate YouTube title variations |
| 28 | `upwork-apply` | Outreach | None | Scrape Upwork jobs + generate proposals |
| 29 | `video-edit` | Video | None | Remove silences + add 3D transitions |
| 30 | `web-research` | Research | None | Structured web research approach |
| 31 | `welcome-email` | Cold Email | Email API*** | Send welcome email sequences |
| 32 | `youtube-outliers` | Content | `YOUTUBE_API_KEY` | Find viral videos in your niche |

\* `onboarding-kickoff` combines multiple skills — needs whatever APIs those skills need
\*\* `recreate-thumbnails` uses AI face-swap services (varies by provider)
\*\*\* `welcome-email` uses whatever email sending service you configure

## By Category

### Lead Generation (4 skills)

#### scrape-leads
Scrape and verify business leads using Apify actors, classify with Claude, enrich with email addresses, and save to Google Sheets.

**API Keys**: `APIFY_TOKEN` (apify.com)
**Trigger**: `/scrape-leads "plumbers in Austin"` or "find leads for..."
**Output**: Google Sheets or CSV with enriched lead data

#### gmaps-leads
Deep Google Maps scraping with website enrichment. Extracts business details, contacts, emails from Google Maps listings and their websites.

**API Keys**: `APIFY_TOKEN` (apify.com)
**Trigger**: `/gmaps-leads "HVAC contractors Dallas"`
**Output**: Enriched lead database

#### classify-leads
Uses Claude to classify leads into categories (e.g., product SaaS vs agencies, B2B vs B2C). Works on existing lead lists.

**API Keys**: None (uses Claude directly)
**Trigger**: `/classify-leads` with a CSV/sheet of leads
**Output**: Classified lead list

#### casualize-names
Converts formal names to casual versions for cold email personalization. "Robert" → "Rob", "Jennifer" → "Jen", company names shortened.

**API Keys**: None
**Trigger**: `/casualize-names` with a lead list
**Output**: Updated list with casual names

### Cold Email & Outreach (6 skills)

#### instantly-campaigns
Create cold email campaigns in Instantly with A/B subject line testing, scheduling, and sender rotation.

**API Keys**: `INSTANTLY_API_KEY` (instantly.ai)
**Trigger**: `/instantly-campaigns`

#### instantly-autoreply
Auto-generate intelligent replies to incoming Instantly email threads using knowledge bases.

**API Keys**: `INSTANTLY_API_KEY` (instantly.ai)
**Trigger**: `/instantly-autoreply`

#### welcome-email
Send welcome email sequences to new clients after signing.

**API Keys**: Email service API (configurable)
**Trigger**: `/welcome-email`

#### onboarding-kickoff
Full post-kickoff automation: generates leads, creates email campaigns, sets up auto-reply. Orchestrates multiple skills.

**API Keys**: Depends on which sub-skills are used
**Trigger**: `/onboarding-kickoff`

#### create-proposal
Generate PandaDoc proposals from client information or sales call transcripts.

**API Keys**: `PANDADOC_API_KEY` (pandadoc.com)
**Trigger**: `/create-proposal`

#### upwork-apply
Scrape Upwork job listings and generate personalized proposals with cover letters.

**API Keys**: None (scrapes public listings)
**Trigger**: `/upwork-apply "web development"` or similar

### Content & YouTube (7 skills)

#### youtube-outliers
Find viral YouTube videos in your niche for competitive intelligence. Identifies outlier videos that performed significantly above channel average.

**API Keys**: `YOUTUBE_API_KEY` (Google Cloud Console)
**Trigger**: `/youtube-outliers`

#### cross-niche-outliers
Find viral videos from adjacent business niches to extract content patterns and hooks that can be adapted.

**API Keys**: `YOUTUBE_API_KEY` (Google Cloud Console)
**Trigger**: `/cross-niche-outliers`

#### title-variants
Generate title variations for YouTube videos based on outlier analysis patterns.

**API Keys**: None
**Trigger**: `/title-variants`

#### recreate-thumbnails
Face-swap YouTube thumbnails to feature your face using AI.

**API Keys**: AI face-swap service API
**Trigger**: `/recreate-thumbnails`

#### humanizer
Remove signs of AI-generated writing from text. Scans for 30 AI writing patterns (inflated symbolism, em dash overuse, promotional language, etc.) and rewrites to sound natural.

**API Keys**: None
**Trigger**: `/humanizer` with text to clean up
**Modes**: scan (diagnose only), rewrite (fix), platform-specific (LinkedIn, blog, website)

#### video-edit
Edit talking-head videos: remove silences with neural VAD, add jump cuts, create 3D swivel teaser transitions.

**API Keys**: None (uses local Python scripts)
**Trigger**: `/video-edit`

#### pan-3d-transition
Create 3D pan/swivel transition effects for videos using Remotion.

**API Keys**: None
**Trigger**: `/pan-3d-transition`

### Email Management (2 skills)

#### gmail-inbox
Manage emails across multiple Gmail accounts. Check inbox, read emails, label, archive.

**API Keys**: Google OAuth credentials (Google Cloud Console)
**Trigger**: `/gmail-inbox`

#### gmail-label
Auto-label Gmail emails into three categories: Action Required, Waiting On, Reference.

**API Keys**: Google OAuth credentials (Google Cloud Console)
**Trigger**: `/gmail-label`

### Community (2 skills)

#### skool-monitor
Monitor and interact with Skool communities. Read posts, create posts, reply to comments, like content, search.

**API Keys**: Skool session cookies (extract from browser dev tools)
**Trigger**: `/skool-monitor`

#### skool-rag
Query Skool community content using RAG pipeline with vector search. Search community knowledge base.

**API Keys**: Skool session cookies
**Trigger**: `/skool-rag "how to do X"`

### Research (4 skills)

#### market-research
Comprehensive market validation. Runs 15-35 search queries across Web, Reddit, X. Produces structured report with verdicts on problem validation, market size, competition.

**API Keys**: None (uses web search)
**Trigger**: `/market-research "SaaS for plumbers"`
**Output**: Structured report in `.tmp/market-research/`

#### web-research
Structured web research approach for any topic.

**API Keys**: None
**Trigger**: `/web-research`

#### literature-research
Search academic literature via PubMed and perform deep research reviews.

**API Keys**: None (PubMed is free)
**Trigger**: `/literature-research`

#### last30days
Research a topic from the last 30 days across Reddit, X, and Web. Become an expert and write copy-paste-ready prompts for your target tool.

**API Keys**: None
**Trigger**: `/last30days "AI code review" for "LinkedIn post"`

### Development Tools (6 skills)

#### security-review
Run OWASP Top 10 vulnerability scan, secret detection, auth audit, injection risk analysis, dependency check, and infrastructure misconfiguration scan.

**API Keys**: None
**Trigger**: `/security-review` or `/security-review ./my-project`

#### design-website
Generate premium website mockups using the buildinamsterdam.com template style.

**API Keys**: None
**Trigger**: `/design-website`

#### modal-deploy
Deploy execution scripts to Modal cloud. Create Modal functions, build API endpoints.

**API Keys**: Modal CLI authentication (modal.com)
**Trigger**: `/modal-deploy`

#### local-server
Run Claude orchestrator locally with Cloudflare tunneling for webhook testing.

**API Keys**: None (Cloudflare tunnel is free)
**Trigger**: `/local-server`

#### generate-report
Generate PDF reports. Default template uses Open-Meteo weather API (free, no key).

**API Keys**: None
**Trigger**: `/generate-report`

#### interview
Conducts in-depth PRD interviews using interactive questions to uncover hidden assumptions, edge cases, technical implications, and UI/UX concerns.

**API Keys**: None
**Trigger**: `/interview`

### Automation (1 skill)

#### add-webhook
Add new Modal webhooks for event-driven execution.

**API Keys**: Modal CLI authentication
**Trigger**: `/add-webhook`

## API Key Setup Summary

| API Key | Where to Get | Skills That Need It |
|---------|-------------|---------------------|
| `APIFY_TOKEN` | [apify.com](https://apify.com) | scrape-leads, gmaps-leads |
| `INSTANTLY_API_KEY` | [instantly.ai](https://instantly.ai) | instantly-campaigns, instantly-autoreply |
| `PANDADOC_API_KEY` | [pandadoc.com](https://pandadoc.com) | create-proposal |
| `YOUTUBE_API_KEY` | [Google Cloud Console](https://console.cloud.google.com) | youtube-outliers, cross-niche-outliers |
| Google OAuth | [Google Cloud Console](https://console.cloud.google.com) | gmail-inbox, gmail-label |
| Modal CLI | [modal.com](https://modal.com) | modal-deploy, add-webhook |
| Skool cookies | Browser dev tools | skool-monitor, skool-rag |

Store API keys in your project's `.env` file (not in `~/.claude/`). Each skill's `SKILL.md` documents exactly which env vars it expects.
