#!/usr/bin/env bash
# Install git hooks for agenthooks development.
# Run once after cloning: bash scripts/install-hooks.sh
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOOKS_DIR="$REPO/.git/hooks"

cp "$REPO/scripts/pre-push.hook" "$HOOKS_DIR/pre-push"
chmod +x "$HOOKS_DIR/pre-push"

echo "✓  pre-push hook installed → .git/hooks/pre-push"
echo "   The regression suite will run automatically before every git push."
