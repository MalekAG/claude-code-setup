#!/usr/bin/env bash
# Claude Code Power-User Setup Installer
# Copies dotclaude/ contents to ~/.claude/ and generates settings.json from template

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DOTCLAUDE="$SCRIPT_DIR/dotclaude"
TARGET="$HOME/.claude"

echo "=== Claude Code Setup Installer ==="
echo ""

# Detect OS
case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*) OS="windows" ;;
    Darwin*)               OS="mac" ;;
    Linux*)                OS="linux" ;;
    *)                     OS="unknown" ;;
esac
echo "Detected OS: $OS"

# Check if dotclaude/ exists
if [ ! -d "$DOTCLAUDE" ]; then
    echo "ERROR: dotclaude/ directory not found. Run this script from the repo root."
    exit 1
fi

# Back up existing config
if [ -d "$TARGET" ]; then
    BACKUP="$TARGET.backup.$(date +%Y%m%d_%H%M%S)"
    echo "Backing up existing ~/.claude/ to $BACKUP"
    cp -r "$TARGET" "$BACKUP"
fi

# Create target directories
echo "Creating directory structure..."
mkdir -p "$TARGET"/{rules,agents,hooks,scripts,skills}

# Copy files
echo "Copying agents..."
cp -r "$DOTCLAUDE"/agents/. "$TARGET/agents/"

echo "Copying rules..."
cp -r "$DOTCLAUDE"/rules/. "$TARGET/rules/"

echo "Copying hooks..."
cp -r "$DOTCLAUDE"/hooks/. "$TARGET/hooks/"

echo "Copying scripts..."
cp -r "$DOTCLAUDE"/scripts/. "$TARGET/scripts/"

echo "Copying skills (32 folders)..."
cp -r "$DOTCLAUDE"/skills/. "$TARGET/skills/"

echo "Copying CLAUDE.md..."
cp "$DOTCLAUDE/CLAUDE.md" "$TARGET/CLAUDE.md"

echo "Copying statusline-command.sh..."
cp "$DOTCLAUDE/statusline-command.sh" "$TARGET/statusline-command.sh"

# Make shell scripts executable
chmod +x "$TARGET/hooks/"*.sh 2>/dev/null || true
chmod +x "$TARGET/statusline-command.sh" 2>/dev/null || true

# Generate settings.json from template
echo ""
echo "Generating settings.json..."

TEMPLATE="$DOTCLAUDE/settings.json.template"
SETTINGS="$TARGET/settings.json"

if [ -f "$SETTINGS" ]; then
    echo "  WARNING: settings.json already exists. Saving template as settings.json.new"
    echo "  Review and merge manually."
    SETTINGS="$TARGET/settings.json.new"
fi

# Detect paths based on OS
case "$OS" in
    windows)
        # Detect Git Bash path
        GIT_BASH=""
        for path in "/c/Program Files/Git/usr/bin/bash.exe" "/c/Program Files (x86)/Git/usr/bin/bash.exe"; do
            if [ -f "$path" ]; then
                GIT_BASH="$path"
                break
            fi
        done
        if [ -z "$GIT_BASH" ]; then
            echo "  WARNING: Git Bash not found. Set GIT_BASH_PATH manually in settings.json"
            GIT_BASH="C:\\\\Program Files\\\\Git\\\\usr\\\\bin\\\\bash.exe"
        else
            # Convert to Windows-escaped path
            GIT_BASH=$(echo "$GIT_BASH" | sed 's|/c/|C:\\\\|' | sed 's|/|\\\\|g')
        fi

        CLAUDE_HOME_UNIX=$(echo "$HOME/.claude" | sed 's|^/home/|/c/Users/|')
        WIN_PATH=$(echo "$HOME/.claude" | sed 's|/c/|C:\\\\|' | sed 's|/|\\\\|g')
        NOTIFY_CMD="powershell -ExecutionPolicy Bypass -File \\\"${WIN_PATH}\\\\hooks\\\\notify.ps1\\\""

        # Generate settings
        sed -e "s|{{GIT_BASH_PATH}}|$GIT_BASH|g" \
            -e "s|{{CLAUDE_HOME_UNIX}}|$CLAUDE_HOME_UNIX|g" \
            -e "s|{{NOTIFY_COMMAND}}|$NOTIFY_CMD|g" \
            "$TEMPLATE" > "$SETTINGS"
        ;;

    mac|linux)
        CLAUDE_HOME_UNIX="$HOME/.claude"
        NOTIFY_CMD="bash $HOME/.claude/hooks/notify.sh"

        # Remove Windows-specific env vars and generate settings
        sed -e "s|{{CLAUDE_HOME_UNIX}}|$CLAUDE_HOME_UNIX|g" \
            -e "s|{{NOTIFY_COMMAND}}|$NOTIFY_CMD|g" \
            -e '/GIT_BASH_PATH/d' \
            -e '/CLAUDE_CODE_GIT_BASH_PATH/d' \
            -e '/CLAUDE_CODE_SHELL/d' \
            "$TEMPLATE" > "$SETTINGS"
        ;;

    *)
        echo "  Unknown OS. Copying template as-is — fill in placeholders manually."
        cp "$TEMPLATE" "$SETTINGS"
        ;;
esac

echo "  Settings written to: $SETTINGS"

# Summary
echo ""
echo "=== Installation Complete ==="
echo ""
echo "Installed to: $TARGET"
echo "  - 5 agents"
echo "  - 32 skills"
echo "  - 3 rule files"
echo "  - 4 notification hooks"
echo "  - 1 web search script"
echo "  - 1 status line script"
echo ""

# Optional dependencies check
echo "=== Optional: Install Python Dependencies ==="
if command -v python3 &>/dev/null || command -v python &>/dev/null; then
    echo "Python found. To enable web-search.py:"
    echo "  pip install duckduckgo-search"
else
    echo "Python not found. Some skills require Python 3."
    echo "  Install Python 3 and then: pip install duckduckgo-search"
fi

echo ""
echo "=== API Keys (configure per-project in .env) ==="
echo ""
echo "Some skills need external API keys. These are optional — skills"
echo "without API requirements work out of the box."
echo ""
echo "  APIFY_TOKEN          — scrape-leads, gmaps-leads (apify.com)"
echo "  INSTANTLY_API_KEY    — instantly-campaigns, instantly-autoreply (instantly.ai)"
echo "  PANDADOC_API_KEY     — create-proposal (pandadoc.com)"
echo "  YOUTUBE_API_KEY      — youtube-outliers, cross-niche-outliers (Google Cloud)"
echo "  Google OAuth          — gmail-inbox, gmail-label (Google Cloud Console)"
echo "  Modal CLI auth        — modal-deploy (modal.com)"
echo "  Skool cookies         — skool-monitor, skool-rag (browser dev tools)"
echo ""
echo "=== Next Steps ==="
echo ""
echo "1. Open Claude Code in any project to verify the setup"
echo "2. Run: python ~/.claude/scripts/web-search.py \"test query\""
echo "3. Try: /security-review on a project to test skills"
echo ""
echo "Done!"
