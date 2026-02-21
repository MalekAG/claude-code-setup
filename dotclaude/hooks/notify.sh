#!/bin/bash
# Unified notification hook - detects SSH vs local and acts accordingly
cat > /dev/null

if [ -n "$SSH_CLIENT" ]; then
    printf '\a'
else
    bash "$HOME/.claude/hooks/play-notification.sh"
fi

exit 0
