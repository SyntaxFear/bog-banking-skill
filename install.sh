#!/usr/bin/env bash
# Install this skill into Claude Code and Codex (run: bash install.sh).
# Re-run any time to update.
set -e
SRC="$(cd "$(dirname "$0")" && pwd)"
rm -rf "$SRC/scripts/__pycache__" 2>/dev/null || true

install_to () {
  local dest="$1" tool="$2"
  mkdir -p "$(dirname "$dest")"
  rm -rf "$dest"
  cp -R "$SRC" "$dest"
  echo "  installed -> $tool: $dest"
}

echo "Installing the bog-banking skill..."
install_to "$HOME/.claude/skills/bog-banking" "Claude Code"
install_to "$HOME/.agents/skills/bog-banking" "Codex"
echo
echo "Done. In Claude Code or Codex, just ask: \"what's my BOG balance?\""
echo "On first use the agent will ask for your BOG credentials and store them."
