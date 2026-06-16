#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# agenthooks Version Bump Script
#
# Usage:
#   bash scripts/bump-version.sh patch      # 0.1.0 → 0.1.1
#   bash scripts/bump-version.sh minor      # 0.1.0 → 0.2.0
#   bash scripts/bump-version.sh major      # 0.1.0 → 1.0.0
#   bash scripts/bump-version.sh beta       # 0.1.0 → 0.1.0b1  (or b2, b3...)
#   bash scripts/bump-version.sh rc         # 0.1.0 → 0.1.0rc1
#   bash scripts/bump-version.sh 0.2.0      # explicit version
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYPROJECT="$REPO/pyproject.toml"
INIT="$REPO/src/agenthooks/__init__.py"

CURRENT=$(grep '^version = ' "$PYPROJECT" | sed 's/version = "\(.*\)"/\1/')
echo "Current version: $CURRENT"

BASE=$(echo "$CURRENT" | sed 's/[ab][0-9]*$//' | sed 's/rc[0-9]*$//')
MAJOR=$(echo "$BASE" | cut -d. -f1)
MINOR=$(echo "$BASE" | cut -d. -f2)
PATCH=$(echo "$BASE" | cut -d. -f3)

BUMP="${1:-patch}"

case "$BUMP" in
  major)
    NEW="$((MAJOR + 1)).0.0"
    ;;
  minor)
    NEW="${MAJOR}.$((MINOR + 1)).0"
    ;;
  patch)
    NEW="${MAJOR}.${MINOR}.$((PATCH + 1))"
    ;;
  beta)
    BETA_BASE="${MAJOR}.${MINOR}.${PATCH}"
    CURRENT_BETA=$(echo "$CURRENT" | grep -oE 'b[0-9]+$' | grep -oE '[0-9]+' || echo "0")
    NEXT_BETA=$((CURRENT_BETA + 1))
    NEW="${BETA_BASE}b${NEXT_BETA}"
    ;;
  rc)
    RC_BASE="${MAJOR}.${MINOR}.${PATCH}"
    CURRENT_RC=$(echo "$CURRENT" | grep -oE 'rc[0-9]+$' | grep -oE '[0-9]+' || echo "0")
    NEXT_RC=$((CURRENT_RC + 1))
    NEW="${RC_BASE}rc${NEXT_RC}"
    ;;
  [0-9]*)
    NEW="$BUMP"
    ;;
  *)
    echo "Usage: $0 [major|minor|patch|beta|rc|X.Y.Z]"
    exit 1
    ;;
esac

echo "New version:     $NEW"
echo ""

read -p "Bump $CURRENT → $NEW? [y/N] " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
fi

sed -i '' "s/^version = \"${CURRENT}\"/version = \"${NEW}\"/" "$PYPROJECT"
echo "✓  pyproject.toml → $NEW"

sed -i '' "s/__version__ = \"${CURRENT}\"/__version__ = \"${NEW}\"/" "$INIT"
echo "✓  src/agenthooks/__init__.py → $NEW"

BRANCH=$(git -C "$REPO" rev-parse --abbrev-ref HEAD)
git -C "$REPO" add "$PYPROJECT" "$INIT"
git -C "$REPO" commit -m "chore: bump version $CURRENT → $NEW"
git -C "$REPO" tag "v${NEW}"
echo "✓  git commit + tag v${NEW}"
echo ""
echo "  Next steps:"
echo "    git push origin $BRANCH --tags"
echo "    bash scripts/release.sh promote-to-beta    # master → beta"
echo "    bash scripts/release.sh promote-to-stable  # beta → stable + PyPI"
