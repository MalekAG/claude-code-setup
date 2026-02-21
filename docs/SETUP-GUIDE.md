# Setup Guide — Manual Installation

Step-by-step guide for manually installing the Claude Code power-user setup.

## Prerequisites

- Claude Code CLI installed and authenticated
- Git Bash (Windows only)
- Python 3 + pip (optional, for web search and some skills)
- jq (for status line — pre-installed on most Mac/Linux systems)

## Step 1: Back Up Your Current Config

If you already have a `~/.claude/` directory:

```bash
cp -r ~/.claude ~/.claude.backup.$(date +%Y%m%d)
```

## Step 2: Create Directory Structure

```bash
mkdir -p ~/.claude/{rules,agents,hooks,scripts,skills}
```

## Step 3: Copy Files

From the repo root:

```bash
# Core files
cp dotclaude/CLAUDE.md ~/.claude/
cp dotclaude/statusline-command.sh ~/.claude/
chmod +x ~/.claude/statusline-command.sh

# Rules
cp dotclaude/rules/*.md ~/.claude/rules/

# Agents
cp dotclaude/agents/*.md ~/.claude/agents/

# Hooks
cp dotclaude/hooks/* ~/.claude/hooks/
chmod +x ~/.claude/hooks/*.sh

# Scripts
cp dotclaude/scripts/* ~/.claude/scripts/
chmod +x ~/.claude/scripts/*.py

# Skills (all 32 folders)
cp -r dotclaude/skills/* ~/.claude/skills/
```

## Step 4: Configure settings.json

Copy the template and edit it:

```bash
cp dotclaude/settings.json.template ~/.claude/settings.json
```

Open `~/.claude/settings.json` in your editor and replace the placeholders:

### Windows

| Placeholder | Replace With |
|-------------|-------------|
| `{{GIT_BASH_PATH}}` | `C:\\Program Files\\Git\\usr\\bin\\bash.exe` |
| `{{CLAUDE_HOME_UNIX}}` | `/c/Users/YOURUSERNAME/.claude` |
| `{{NOTIFY_COMMAND}}` | `powershell -ExecutionPolicy Bypass -File \"C:\\Users\\YOURUSERNAME\\.claude\\hooks\\notify.ps1\"` |

### Mac

| Placeholder | Replace With |
|-------------|-------------|
| `{{CLAUDE_HOME_UNIX}}` | `/Users/YOURUSERNAME/.claude` |
| `{{NOTIFY_COMMAND}}` | `bash ~/.claude/hooks/notify.sh` |

Also remove these lines from the `env` section (Windows-only):
```json
"CLAUDE_CODE_GIT_BASH_PATH": "...",
"CLAUDE_CODE_SHELL": "...",
```

### Linux

| Placeholder | Replace With |
|-------------|-------------|
| `{{CLAUDE_HOME_UNIX}}` | `/home/YOURUSERNAME/.claude` |
| `{{NOTIFY_COMMAND}}` | `bash ~/.claude/hooks/notify.sh` |

Also remove `CLAUDE_CODE_GIT_BASH_PATH` and `CLAUDE_CODE_SHELL` from env.

## Step 5: Customize Settings (Optional)

### Permission Mode

The default is `"defaultMode": "bypassPermissions"` which skips all tool approval prompts. If you prefer safer operation:

```json
"defaultMode": "default"
```

### Model Overrides

The setup routes "haiku" and "sonnet" model requests to Sonnet 4.6:

```json
"ANTHROPIC_DEFAULT_HAIKU_MODEL": "claude-sonnet-4-6",
"ANTHROPIC_DEFAULT_SONNET_MODEL": "claude-sonnet-4-6"
```

Change these to any model you prefer. Remove these lines entirely to use Claude Code's default model routing.

### Agent Teams

```json
"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
```

This enables the experimental teams feature (multiple agents collaborating). Remove if you don't need it.

### Plugins

The `enabledPlugins` section lists official Claude Code plugins. These are installed via Claude Code's plugin system, not from this repo. Enable the ones relevant to your workflow:

- `frontend-design` — UI generation
- `github` — GitHub integration
- `context7` — Library docs lookup
- `playwright` — Browser automation
- `supabase` — Supabase integration
- `ralph-loop` — Iterative improvement loop

## Step 6: Install Python Dependencies

For the web search script:

```bash
pip install duckduckgo-search
```

Verify:

```bash
python ~/.claude/scripts/web-search.py "test query"
```

## Step 7: Custom Notification Sound (Optional)

### Windows

Place any MP3 at `~/.claude/notification.mp3`. The hooks check for this file first, then fall back to `C:\Windows\Media\chimes.wav`.

### Mac/Linux

Notifications use terminal bell (`\a`). Configure your terminal app to show alerts on bell:
- **iTerm2**: Preferences → Profiles → Terminal → "Notification center alerts"
- **Terminal.app**: Preferences → Profiles → Advanced → "Bell" settings
- **Kitty/Alacritty**: Check your terminal's bell configuration

## Step 8: Verify

1. **Status line**: Open Claude Code in any project. You should see model name, folder, and context % bar.
2. **Skills**: Type `/` in Claude Code — you should see the 32 skills in autocomplete.
3. **Agents**: Ask Claude to "review this file" — it should spawn the `code-reviewer` subagent.
4. **Web search**: Run `python ~/.claude/scripts/web-search.py "hello world"`.
5. **Notifications**: Complete a task — you should hear a sound (Windows) or see a terminal bell (Mac/Linux).

## Troubleshooting

### Status line shows nothing
- Check that `jq` is installed: `jq --version`
- Check that `statusline-command.sh` is executable: `chmod +x ~/.claude/statusline-command.sh`
- Verify the path in settings.json matches your actual `~/.claude/` location

### Skills don't appear
- Verify skills were copied: `ls ~/.claude/skills/` should show 32 folders
- Each folder must have a `SKILL.md` file
- Restart Claude Code after copying

### Notifications don't work (Windows)
- Check PowerShell execution policy: `Get-ExecutionPolicy` should not be `Restricted`
- The hooks use `presentationCore` assembly which is built into Windows
- Test directly: `powershell -ExecutionPolicy Bypass -File ~/.claude/hooks/notify.ps1`

### web-search.py fails
- Install dependency: `pip install duckduckgo-search`
- Check Python version: `python --version` (needs 3.8+)
- On Windows, try `python` instead of `python3`
