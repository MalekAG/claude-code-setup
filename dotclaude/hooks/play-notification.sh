#!/bin/bash
# Play notification - works over SSH via terminal bell
# The terminal bell (\a) triggers the SSH client's notification
# Configure your terminal app to show alerts on bell (iTerm2, Terminal.app, etc.)

# Consume stdin (hook passes data via stdin)
cat > /dev/null

# Send terminal bell character
printf '\a'

exit 0
