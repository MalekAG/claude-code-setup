# Project Documentation Standard

Every project in the workspace must have baseline documentation. What's required depends on the project type.

## Required Docs by Project Type

| Doc | Web App | Python Tool | Ops/Business |
|-----|---------|-------------|--------------|
| CLAUDE.md | Required | Required | Required |
| DEVLOG.md | Required | Required | Optional |
| PRD.md | Required | Required | No |
| .env.example | Required | If uses APIs | If uses APIs |

## CLAUDE.md Template

Every project gets a CLAUDE.md in its root. This is the primary context file that Claude reads on every session. Keep it under 80 lines — link to other docs for details.

```markdown
# [Project Name]

[One-line description of what this project does]

## Stack

- [Framework] [version]
- [Language] [version]
- [Database/Services]

## Commands

```
npm run dev      # Start dev server
npm run build    # Production build
npm run test     # Run tests
npm run lint     # Lint check
```

## Structure

```
src/
  app/           # Next.js routes (App Router)
  components/    # React components
  lib/           # Shared utilities
  types/         # TypeScript types
```

## Architecture

[2-4 sentences: how data flows, key patterns, what talks to what]

## Conventions

- [Naming conventions]
- [State management approach]
- [Auth pattern]
- [Any project-specific rules]

## Key Context

- [Important decisions and why they were made]
- [Known gotchas or workarounds]
- [Links to PRD.md, DEVLOG.md for deeper context]

## Environment

Requires `.env.local` with:
- `VARIABLE_NAME` — what it's for
```

Adapt sections to the project — Python tools won't have npm commands, ops projects won't have a src/ structure. Remove sections that don't apply rather than leaving them empty.

## FOR[name].md Convention

Optional deep-dive documentation that explains the project in plain language. Write one when a project reaches maturity or when onboarding someone new.

Include:
1. Technical architecture — how the system is designed
2. Codebase structure — where things live and why
3. Technology choices — what we picked and why
4. How things connect — trace data flow end to end
5. Lessons learned — bugs, pitfalls, discoveries, patterns

Write it like you're explaining to a smart friend, not a spec sheet. The DEVLOG feeds into the FOR file's lessons section.

## DEVLOG Working State

The DEVLOG uses a **Working State** section (replaces old "Current Status") that is overwritten each session. See `rules/workflow.md` for the full template and rules. Key points:

- Working State: max 80 lines, overwritten each session
- Key Files: max 5 entries with **inline summaries** (not just filenames)
- Session Archive: compressed to 5-8 lines per session

## Scaffolding

Use the `project-init` agent to generate missing docs for new or existing projects:
```
Run project-init agent with: project path, project name, project type
```
