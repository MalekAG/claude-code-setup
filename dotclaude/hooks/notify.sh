#!/bin/bash
# Unified notification hook - detects SSH vs local and acts accordingly
cat > /dev/null

if [ -n "$SSH_CLIENT" ]; then
    printf '\a'
else
    powershell -ExecutionPolicy Bypass -File "$HOME/.claude/hooks/play-notification.ps1"
fi

exit 0
