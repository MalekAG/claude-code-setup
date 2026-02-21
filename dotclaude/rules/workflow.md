# Workflow Rules

## Self-Anneal Loop

When something breaks, treat it as a learning opportunity:

1. **Read** the error message and stack trace carefully
2. **Fix** the script (if it uses paid tokens/credits, check with user first)
3. **Test** the fix to confirm it works
4. **Update docs** — SKILL.md, DEVLOG, or relevant config with what you learned
5. **System is now stronger** — the same error won't happen again

Example: API returns 429 → investigate → find batch endpoint → rewrite script → test → update SKILL.md with rate limit info.

## Design & Build Workflow

For non-trivial code (scripts, features, refactors):

1. **Write/edit** the code
2. **Code review** — spawn `code-reviewer` subagent with changed files. It reports issues, does NOT fix them.
3. **QA** — spawn `qa` subagent with the code. It generates tests, runs them, reports results. Does NOT fix anything.
4. **Fix** — you (the parent agent) read both reports and apply fixes
5. **Ship** — only after review passes and tests pass

Spawn review + QA in parallel when files are independent (`run_in_background: true`).

## DEVLOG.md

Maintain a `DEVLOG.md` in every project root. Update in real-time, not retroactively.

```markdown
# Project Dev Log

## Working State
**Session:** N | **Date:** YYYY-MM-DD

### Active Task
[Task name + description]
- [x] Step 1: ...
- [ ] Step 2: ... <-- CURRENT
- [ ] Step 3: ...

### Key Files (current shape)
**`path/to/file.ts`** (NEW or MODIFIED, ~N lines)
[2-3 line summary: what it does, key patterns, how it connects to current task]

### Decisions (active)
- [Decision + rationale -- only ones relevant to current work]

### Next Steps
1. [Specific step]
2. [Specific step]

### Blockers
- [Any blockers]

### Watch Out
- [Recent gotchas likely to recur -- max 3]

---
---

## Session Archive

### Session N -- YYYY-MM-DD: [Title]
**What we did:** [1-2 sentences]
**Files:** [comma-separated list]
**Decisions:** [1-2 sentences]

---

## Milestones
- [ ] Milestone 1 - description
- [x] Milestone 2 - completed

## Mistakes & Lessons
### [Date] - [Short title]
**What happened:** ...
**Root cause:** ...
**How we fixed it:** ...
**Lesson:** ...

## Technical Debt & Future Ideas
- ...
```

### DEVLOG Rules

- **Working State**: max 80 lines, overwritten each session (not appended)
- **Key Files**: max 5 entries with inline summaries (not just filenames)
- **Session Archive**: compress to 5-8 lines per session (not 30-80)
- Be specific: "API returned 429 after 100 requests" not "had rate limit issues"
- Capture the why — decisions without context are useless later
- Mistakes are gold — document them honestly

## Project Documentation

See `rules/project-docs.md` for the full documentation standard (CLAUDE.md template, FOR[name].md convention, required docs by project type).
