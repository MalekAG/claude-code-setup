#!/usr/bin/env bash
# Claude Code status line
# Receives JSON via stdin

input=$(cat)

cwd=$(echo "$input" | jq -r '.workspace.current_dir // .cwd // empty')
model=$(echo "$input" | jq -r '.model.display_name // empty')
used=$(echo "$input" | jq -r '.context_window.used_percentage // empty')
vim_mode=$(echo "$input" | jq -r '.vim.mode // empty')

# Show just the folder name
if [ -n "$cwd" ]; then
  short_cwd=$(basename "$cwd")
else
  short_cwd="?"
fi

# Build context indicator with progress bar
if [ -n "$used" ]; then
  used_int=${used%.*}
  if [ "$used_int" -ge 80 ]; then
    ctx_color="\033[31m"  # red
  elif [ "$used_int" -ge 60 ]; then
    ctx_color="\033[33m"  # yellow
  else
    ctx_color="\033[32m"  # green
  fi
  # Build 10-char progress bar
  bar_width=10
  filled=$((used_int * bar_width / 100))
  empty=$((bar_width - filled))
  bar=""
  for ((i=0; i<filled; i++)); do bar+="█"; done
  for ((i=0; i<empty; i++)); do bar+="░"; done
  ctx_part="${ctx_color}${bar}\033[0m ${used_int}%"
else
  ctx_part=""
fi

# Build vim mode indicator
if [ -n "$vim_mode" ]; then
  vim_part=" [${vim_mode}]"
else
  vim_part=""
fi

# Build model short name (e.g. "Sonnet 4.6" -> "Sonnet 4.6")
if [ -n "$model" ]; then
  model_part="\033[2m${model}\033[0m"
else
  model_part=""
fi

# Assemble: dir | model | ctx%
parts=""

if [ -n "$model_part" ]; then
  parts="${model_part}"
fi

if [ -n "$short_cwd" ]; then
  parts="${parts}  \033[1m${short_cwd}\033[0m"
fi

if [ -n "$ctx_part" ]; then
  parts="${parts}  ${ctx_part}"
fi

if [ -n "$vim_part" ]; then
  parts="${parts}${vim_part}"
fi

echo -e "${parts}"
