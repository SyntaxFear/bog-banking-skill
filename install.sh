#!/usr/bin/env bash
# Install the bog-banking skill into Claude Code and Codex.
#
# One-line install (no clone needed):
#   curl -fsSL https://raw.githubusercontent.com/SyntaxFear/claude-bog-banking/main/install.sh | bash
#
# Pin to a specific version:
#   curl -fsSL https://raw.githubusercontent.com/SyntaxFear/claude-bog-banking/main/install.sh | BOG_SKILL_REF=v1.0.0 bash
#
# Or, from a local clone:
#   bash install.sh
#
# Re-run any time to update.
set -euo pipefail

REPO="SyntaxFear/claude-bog-banking"
SKILL_NAME="bog-banking"
CLAUDE_DIR="$HOME/.claude/skills/$SKILL_NAME"
CODEX_DIR="$HOME/.agents/skills/$SKILL_NAME"

# --- locate the source: local clone, or download the tarball (curl | bash) ---
SELF_DIR=""
src_candidate="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)"
if [ -n "$src_candidate" ] && [ -f "$src_candidate/SKILL.md" ]; then
  SELF_DIR="$src_candidate"
fi

CLEANUP=""
trap '[ -n "${CLEANUP:-}" ] && rm -rf "$CLEANUP"' EXIT   # always remove temp dir
if [ -n "$SELF_DIR" ]; then
  SRC="$SELF_DIR"
else
  command -v curl >/dev/null 2>&1 || { echo "Error: 'curl' is required for one-line install."; exit 1; }
  command -v tar  >/dev/null 2>&1 || { echo "Error: 'tar' is required for one-line install."; exit 1; }
  REF="${BOG_SKILL_REF:-main}"
  echo "Downloading $SKILL_NAME ($REF) from github.com/$REPO ..."
  TMP="$(mktemp -d)"; CLEANUP="$TMP"
  curl -fsSL "https://github.com/$REPO/archive/$REF.tar.gz" | tar xz -C "$TMP"
  SRC="$(find "$TMP" -mindepth 1 -maxdepth 1 -type d | head -1)"
  [ -n "$SRC" ] && [ -f "$SRC/SKILL.md" ] || { echo "Error: download did not contain the skill."; exit 1; }
fi

install_to () {
  local dest="$1" tool="$2"
  mkdir -p "$(dirname "$dest")"
  rm -rf "$dest"
  cp -R "$SRC" "$dest"
  rm -rf "$dest/.git" "$dest/scripts/__pycache__"   # don't ship repo/cache cruft
  echo "  installed -> $tool: $dest"
}

echo "Installing the $SKILL_NAME skill..."
install_to "$CLAUDE_DIR" "Claude Code"
install_to "$CODEX_DIR"  "Codex"
[ -n "$CLEANUP" ] && rm -rf "$CLEANUP"

echo
echo "Done. In Claude Code or Codex, just ask: \"what's my BOG balance?\""
echo "On first use the agent will ask for your BOG credentials and store them"
echo "securely in your OS keychain (never in a file)."
