# Claude Code Power-User Setup — Installation Guide

This file is for Claude/AI agents. When someone clones this repo and opens it in Claude Code, read this file to understand how to help them install the setup.

## What This Repo Is

A complete Claude Code configuration: 5 custom agents, 32 skills, notification hooks, 3 rule files, a status line, and a web search workaround script. Everything lives in `dotclaude/` and gets copied to `~/.claude/`.

## File Structure

```
dotclaude/           → Copy contents to ~/.claude/
  CLAUDE.md          → Global instructions (loaded every session)
  settings.json.template → Settings with {{PLACEHOLDERS}} to fill
  statusline-command.sh  → Context % bar + model + cwd in status line
  rules/             → 3 rule files (style, workflow, project-docs)
  agents/            → 5 custom agents (code-reviewer, qa, research, project-init, market-research)
  hooks/             → Notification hooks (PS1 for Windows, sh for Mac/Linux)
  scripts/           → web-search.py (DuckDuckGo, bypasses geo-restrictions)
  skills/            → 32 skill folders (lead gen, content, automation, dev tools, research)
```

## Installation Steps

Follow these steps to install for the user:

### 1. Back Up Existing Config

```bash
if [ -d ~/.claude ]; then
    cp -r ~/.claude ~/.claude.backup.$(date +%Y%m%d)
fi
```

### 2. Copy Files

```bash
cp -r dotclaude/* ~/.claude/
```

If `~/.claude/` doesn't exist, create it first: `mkdir -p ~/.claude/{rules,agents,hooks,scripts,skills}`

### 3. Generate settings.json

The template at `dotclaude/settings.json.template` has these placeholders:

| Placeholder | Description | Example |
|-------------|-------------|---------|
| `{{GIT_BASH_PATH}}` | Path to Git Bash (Windows only) | `C:\\Program Files\\Git\\usr\\bin\\bash.exe` |
| `{{CLAUDE_HOME_UNIX}}` | Unix-style path to `~/.claude` | `/c/Users/John/.claude` or `/home/john/.claude` |
| `{{NOTIFY_COMMAND}}` | Notification hook command | See OS-specific values below |

**Windows:**
```
GIT_BASH_PATH = C:\\Program Files\\Git\\usr\\bin\\bash.exe
CLAUDE_HOME_UNIX = /c/Users/USERNAME/.claude
NOTIFY_COMMAND = powershell -ExecutionPolicy Bypass -File "C:\\Users\\USERNAME\\.claude\\hooks\\notify.ps1"
```

**Mac/Linux:**
```
GIT_BASH_PATH = (remove these two env vars entirely — not needed)
CLAUDE_HOME_UNIX = /home/USERNAME/.claude (or /Users/USERNAME/.claude on Mac)
NOTIFY_COMMAND = bash ~/.claude/hooks/notify.sh
```

After replacing placeholders, save as `~/.claude/settings.json`.

### 4. OS-Specific Adjustments

**Mac/Linux users:**
- Remove `CLAUDE_CODE_GIT_BASH_PATH` and `CLAUDE_CODE_SHELL` from `env` in settings.json (these are Windows-only)
- The `.ps1` hooks are Windows PowerShell scripts — the `.sh` equivalents are already included and work on Mac/Linux
- Change the `NOTIFY_COMMAND` to use the `.sh` hook

**Windows users:**
- Git Bash is required — install Git for Windows if not already installed
- The PowerShell notification hooks use `presentationCore` for audio (built into Windows)
- Optionally place a custom `notification.mp3` at `~/.claude/notification.mp3`

### 5. Install Python Dependencies (Optional)

For the web search script:
```bash
pip install duckduckgo-search
```

Test it: `python ~/.claude/scripts/web-search.py "test query"`

### 6. Settings Explained

**permissions.defaultMode: "default"** — Asks before executing tools. Change to `"bypassPermissions"` to skip all permission prompts (power-user setting — only do this if you trust all installed skills and agents, as any skill can execute arbitrary shell commands without confirmation).

**permissions.allow** — List of tools that are pre-approved even in `"default"` mode. `Bash` is intentionally excluded from the default allow list — add it only if you want unattended shell execution.

**env.ANTHROPIC_DEFAULT_HAIKU_MODEL / ANTHROPIC_DEFAULT_SONNET_MODEL** — Override which models are used when agents request "haiku" or "sonnet". Set to `claude-sonnet-4-6` to use Sonnet 4.6 for both (cost-effective for subagents).

**enabledPlugins** — Which Claude Code plugins are active. These are installed via the plugin system, not from this repo. Enable/disable as needed.

### 7. Verify Installation

After installation, test these:
1. Open Claude Code in any project — status line should show model + folder + context %
2. Run `/security-review` — should trigger the security review skill
3. Ask Claude to review a file — should spawn `code-reviewer` subagent
4. Run `python ~/.claude/scripts/web-search.py "hello world"` — should return results

## Skills That Need API Keys

Most skills work with just Claude Code, but some need external API keys configured in your project's `.env`:

| Skill | API Key Needed | Where to Get It |
|-------|---------------|-----------------|
| scrape-leads | `APIFY_TOKEN` | apify.com |
| gmail-inbox / gmail-label | Google OAuth credentials | Google Cloud Console |
| instantly-campaigns / instantly-autoreply | `INSTANTLY_API_KEY` | instantly.ai |
| create-proposal | `PANDADOC_API_KEY` | pandadoc.com |
| gmaps-leads | `APIFY_TOKEN` | apify.com |
| modal-deploy | Modal CLI auth | modal.com |
| skool-monitor / skool-rag | Skool session cookies | skool.com (browser dev tools) |
| youtube-outliers / cross-niche-outliers | `YOUTUBE_API_KEY` | Google Cloud Console |
| recreate-thumbnails | AI face-swap API | Varies |

Skills without API key requirements work out of the box with just Claude Code.

## What's NOT Included

- Session continuity system (orchestrator, handoff hooks) — a separate advanced feature
- npx-installed skills (find-skills, supabase-postgres-best-practices, vercel-deploy) — install these via Claude Code's plugin system
- Per-project memory (`~/.claude/projects/`) — this is auto-generated per machine
- Credentials, history, cache, telemetry — machine-specific runtime data
