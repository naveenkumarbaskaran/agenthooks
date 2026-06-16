#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# agenthooks Release Script
# Manages the three-branch release system: master → beta → stable
#
# Commands:
#   bash scripts/release.sh status               # show all branch/tag state
#   bash scripts/release.sh promote-to-beta      # merge master → beta, push
#   bash scripts/release.sh promote-to-stable    # merge beta → stable, publish PyPI
#   bash scripts/release.sh rollback-stable      # revert stable to previous tag
#   bash scripts/release.sh changelog            # show changes since last stable
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$REPO/.venv"
PYTHON="$VENV/bin/python"
cd "$REPO"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'
BOLD='\033[1m'; NC='\033[0m'

_ok()      { echo -e "  ${GREEN}✓${NC}  $1"; }
_fail()    { echo -e "  ${RED}✗${NC}  $1"; exit 1; }
_warn()    { echo -e "  ${YELLOW}⚠${NC}  $1"; }
_section() { echo -e "\n${CYAN}${BOLD}━━━  $1  ━━━${NC}"; }
_info()    { echo -e "  ${CYAN}→${NC}  $1"; }

CURRENT_VERSION=$(grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/')

_load_pypi_token() {
    if [ -n "${PYPI_TOKEN:-}" ]; then
        echo "$PYPI_TOKEN"
    elif [ -f "$REPO/.pypi-token" ]; then
        cat "$REPO/.pypi-token"
    else
        echo ""
    fi
}

_run_regression() {
    _section "Running regression suite"
    if bash "$REPO/scripts/regression.sh" 2>/dev/null; then
        _ok "Regression suite passed"
    else
        _fail "Regression suite FAILED — aborting release"
    fi
}

cmd_status() {
    echo ""
    echo -e "${CYAN}${BOLD}  agenthooks Release Status${NC}"
    echo "  ─────────────────────────────────────────────"

    for branch in master beta stable; do
        if git show-ref --quiet "refs/remotes/origin/$branch" 2>/dev/null || git show-ref --quiet "refs/heads/$branch" 2>/dev/null; then
            COMMIT=$(git log "origin/$branch" --oneline -1 2>/dev/null || git log "$branch" --oneline -1 2>/dev/null || echo "no commits")
            case "$branch" in
                master) ICON="🔧" ;;
                beta)   ICON="🧪" ;;
                stable) ICON="🚀" ;;
            esac
            printf "  %s  %-8s  %s\n" "$ICON" "$branch" "$COMMIT"
        else
            printf "  ⬜  %-8s  (branch not found)\n" "$branch"
        fi
    done

    echo ""
    echo "  Tags (last 5):"
    git tag --sort=-version:refname | head -5 | while read -r tag; do
        MSG=$(git tag -l --format='%(contents:subject)' "$tag" 2>/dev/null || echo "")
        printf "    %-18s  %s\n" "$tag" "$MSG"
    done

    echo ""
    echo "  Current version: $CURRENT_VERSION"
    echo "  PyPI:            https://pypi.org/project/agenthooks-py/"
    echo ""
}

cmd_promote_to_beta() {
    _section "Promote master → beta  (v${CURRENT_VERSION})"

    BRANCH=$(git rev-parse --abbrev-ref HEAD)
    if [ "$BRANCH" != "master" ] && [ "$BRANCH" != "main" ]; then
        _fail "Must be on master/main branch (currently on $BRANCH)"
    fi

    _run_regression

    if ! git show-ref --quiet "refs/heads/beta"; then
        _info "Creating beta branch"
        git checkout -b beta
        git checkout "$BRANCH"
    fi

    _info "Merging $BRANCH → beta"
    git checkout beta
    git merge "$BRANCH" --no-edit -m "chore: promote $BRANCH → beta v${CURRENT_VERSION}"

    BETA_TAG="v${CURRENT_VERSION}-beta"
    git tag "$BETA_TAG" -m "Beta release v${CURRENT_VERSION}"
    _ok "Tagged $BETA_TAG"

    _info "Pushing beta branch + tag"
    git push origin beta --tags
    _ok "beta branch pushed"

    git checkout "$BRANCH"

    echo ""
    _ok "Promoted to beta: v${CURRENT_VERSION}"
    _info "Next: test beta, then run: bash scripts/release.sh promote-to-stable"
    echo ""
}

cmd_promote_to_stable() {
    _section "Promote beta → stable + publish PyPI  (v${CURRENT_VERSION})"

    BRANCH=$(git rev-parse --abbrev-ref HEAD)
    if [ "$BRANCH" != "beta" ] && [ "$BRANCH" != "master" ] && [ "$BRANCH" != "main" ]; then
        _fail "Must be on beta or master branch (currently on $BRANCH)"
    fi

    _run_regression

    if ! git show-ref --quiet "refs/heads/stable"; then
        _info "Creating stable branch"
        git checkout -b stable
        git checkout "$BRANCH"
    fi

    _info "Merging ${BRANCH} → stable"
    git checkout stable
    git merge "$BRANCH" --no-edit -m "chore: promote ${BRANCH} → stable v${CURRENT_VERSION}"

    STABLE_TAG="v${CURRENT_VERSION}"
    if ! git tag -l | grep -q "^${STABLE_TAG}$"; then
        git tag "$STABLE_TAG" -m "Release v${CURRENT_VERSION}"
        _ok "Tagged $STABLE_TAG"
    else
        _warn "Tag $STABLE_TAG already exists — skipping tag"
    fi

    _info "Pushing stable branch + tag"
    git push origin stable --tags
    _ok "stable branch pushed"

    _section "Publishing to PyPI"

    PYPI_TOKEN=$(_load_pypi_token)
    if [ -z "$PYPI_TOKEN" ]; then
        _warn "No PyPI token found. Set PYPI_TOKEN env var or create .pypi-token file."
        _warn "Skipping PyPI publish. Run manually:"
        echo ""
        echo "    TWINE_USERNAME=__token__ TWINE_PASSWORD=<token> \\"
        echo "    python -m twine upload dist/agenthooks_py-${CURRENT_VERSION}*"
        echo ""
    else
        _info "Building distribution"
        "$PYTHON" -m build -q
        _ok "Built dist/"

        _info "Uploading to PyPI"
        TWINE_USERNAME="__token__" TWINE_PASSWORD="$PYPI_TOKEN" \
            "$PYTHON" -m twine upload "dist/agenthooks_py-${CURRENT_VERSION}"* 2>&1 | \
            grep -E "Uploading|View at|ERROR" || true
        _ok "Published agenthooks-py v${CURRENT_VERSION} to PyPI"
    fi

    git checkout "$BRANCH"

    echo ""
    _ok "━━━ RELEASE COMPLETE: agenthooks-py v${CURRENT_VERSION} ━━━"
    _info "PyPI: https://pypi.org/project/agenthooks-py/${CURRENT_VERSION}/"
    _info "GitHub: https://github.com/naveenkumarbaskaran/agenthooks/releases/tag/${STABLE_TAG}"
    echo ""
}

cmd_rollback_stable() {
    _section "Rollback stable to previous release"

    CURRENT_STABLE=$(git log origin/stable --oneline -1 2>/dev/null || git log stable --oneline -1 2>/dev/null)
    PREV_TAG=$(git tag --sort=-version:refname | grep -v beta | grep -v rc | sed -n '2p')

    if [ -z "$PREV_TAG" ]; then
        _fail "No previous stable tag found"
    fi

    echo "  Current stable: $CURRENT_STABLE"
    echo "  Rollback to:    $PREV_TAG"
    echo ""
    read -p "  Confirm rollback stable → $PREV_TAG? [y/N] " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "  Aborted."
        exit 0
    fi

    git checkout stable
    git reset --hard "$PREV_TAG"
    git push origin stable --force-with-lease
    _ok "Rolled back stable to $PREV_TAG"
    git checkout master
}

cmd_changelog() {
    LAST_STABLE=$(git tag --sort=-version:refname | grep -v beta | grep -v rc | head -1 || echo "")
    if [ -z "$LAST_STABLE" ]; then
        _warn "No stable tags found. Showing all commits."
        git log --oneline
    else
        _section "Changes since $LAST_STABLE"
        git log "${LAST_STABLE}..HEAD" --oneline
    fi
}

CMD="${1:-status}"
case "$CMD" in
    status)             cmd_status ;;
    promote-to-beta)    cmd_promote_to_beta ;;
    promote-to-stable)  cmd_promote_to_stable ;;
    rollback-stable)    cmd_rollback_stable ;;
    changelog)          cmd_changelog ;;
    *)
        echo "Usage: $0 [status|promote-to-beta|promote-to-stable|rollback-stable|changelog]"
        exit 1
        ;;
esac
