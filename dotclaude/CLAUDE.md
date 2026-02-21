# Personal Preferences

- Primary stack: Next.js (App Router), React, Tailwind CSS, Supabase, Python
- Style: Concise, no emojis, explain the "why" not just the "what"
- Model preference: Use Opus for building and coding subagents, Sonnet for review/research/exploration subagents
- Language: English for code and docs

# Workflow

- **Self-anneal**: fix → update script → test → update docs → system stronger
  - Errors are learning opportunities, not dead ends
  - If a fix uses paid tokens/credits, check with user first
- **DEVLOG.md** in every project root — real-time session journal, not retroactive
- **Project docs standard**: every project needs CLAUDE.md + DEVLOG.md (see `rules/project-docs.md`)
- **Skills first**: check installed skills before writing custom scripts
- **Subagents before shipping**: use `code-reviewer` and `qa` for non-trivial code changes
- **Parallelize with subagents**: use Task tool to spawn subagents for independent work items — faster than doing everything sequentially

# Coding Rules

- Read existing code before modifying it
- Don't add features, refactoring, or "improvements" beyond what was asked
- Don't create files unnecessarily — prefer editing existing ones
- Only comment where logic isn't self-evident
- Only validate at system boundaries (user input, external APIs)
- Three similar lines > premature abstraction
- No backwards-compatibility hacks (unused vars, re-exports, removal comments)

# Design & Build Loop

For non-trivial code:
1. Write/edit the code
2. Spawn `code-reviewer` subagent — reports issues, does NOT fix them
3. Spawn `qa` subagent — generates tests, runs them, reports results
4. Fix issues from both reports
5. Ship only after review passes and tests pass

Spawn review + QA in parallel when files are independent.

# File Organization

- `.tmp/` for intermediate/temp files (never commit)
- Deliverables go to cloud services (Sheets, Slides, etc.) where user can access them
- `.env` for environment variables and API keys

# Cloud & Deployment

- Supabase for backend/auth/database
- Vercel for frontend deployment
- Modal for webhooks/serverless (when needed)
