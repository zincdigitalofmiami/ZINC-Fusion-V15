#!/usr/bin/env bash
# ============================================================================
# WORKTREE HYGIENE — cleans up stale agent worktrees, branches, stashes
#
# Usage: scripts/cleanup_worktrees.sh          (interactive)
#        scripts/cleanup_worktrees.sh --auto    (non-interactive, stale > 7 days)
#        scripts/cleanup_worktrees.sh --dry-run (show what would be cleaned)
# ============================================================================
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

MODE="${1:-interactive}"
STALE_DAYS=7

prompt_yes_no() {
    local prompt="$1"
    local reply=""

    # Read prompts from the terminal, not loop stdin.
    if [ ! -t 1 ] || [ ! -r /dev/tty ]; then
        return 1
    fi

    read -r -n 1 -p "$prompt" reply </dev/tty || true
    echo
    [[ "$reply" =~ ^[Yy]$ ]]
}

echo "============================================"
echo "  Worktree & Branch Hygiene"
echo "============================================"
echo ""

# --------------------------------------------------------------------------
# 1. Stale worktrees
# --------------------------------------------------------------------------
echo "[1/4] Checking worktrees..."
WORKTREE_COUNT=0

while IFS= read -r wt; do
    # Skip the main worktree
    if [ "$wt" = "$REPO_ROOT" ]; then
        continue
    fi

    WORKTREE_COUNT=$((WORKTREE_COUNT + 1))

    if [ ! -d "$wt" ]; then
        echo -e "  ${RED}ORPHANED: $wt (directory missing)${NC}"
        if [ "$MODE" = "--auto" ]; then
            git worktree remove --force "$wt" 2>/dev/null || git worktree prune
            echo "    Removed."
        elif [ "$MODE" = "--dry-run" ]; then
            echo "    (would remove)"
        else
            if prompt_yes_no "    Remove? [y/N] "; then
                git worktree remove --force "$wt" 2>/dev/null || git worktree prune
                echo "    Removed."
            fi
        fi
        continue
    fi

    LAST_COMMIT_AGE=$(git -C "$wt" log -1 --format="%cr" 2>/dev/null || echo "unknown")
    echo -e "  ${YELLOW}WORKTREE: $wt${NC}"
    echo "    Last commit: $LAST_COMMIT_AGE"

    if [ "$MODE" = "--dry-run" ]; then
        echo "    (would prompt for removal)"
    elif [ "$MODE" = "--auto" ]; then
        EPOCH_NOW=$(date +%s)
        EPOCH_LAST=$(git -C "$wt" log -1 --format="%ct" 2>/dev/null || echo "$EPOCH_NOW")
        AGE_DAYS=$(( (EPOCH_NOW - EPOCH_LAST) / 86400 ))
        if [ "$AGE_DAYS" -gt "$STALE_DAYS" ]; then
            echo "    Stale (${AGE_DAYS} days). Removing..."
            git worktree remove --force "$wt" 2>/dev/null || true
        else
            echo "    Recent (${AGE_DAYS} days). Keeping."
        fi
    else
        if prompt_yes_no "    Remove this worktree? [y/N] "; then
            git worktree remove --force "$wt" 2>/dev/null || true
            echo "    Removed."
        fi
    fi
done < <(git worktree list --porcelain | grep "^worktree " | sed 's/^worktree //')

# Always prune dangling references
git worktree prune 2>/dev/null || true

# --------------------------------------------------------------------------
# 2. Agent branches (local only)
# --------------------------------------------------------------------------
echo ""
echo "[2/4] Checking local agent branches..."

# Patterns that match agent-created branch names
CURRENT_BRANCH=$(git branch --show-current)
AGENT_BRANCHES=$(git branch --list | sed 's/^[* ]*//' | grep -E '^(claude/|copilot/|codex/|agent-|set-up-|inngest-bugwork|frontend-endpoints-)' || true)

if [ -n "$AGENT_BRANCHES" ]; then
    while IFS= read -r branch; do
        # Never touch the current branch
        if [ "$branch" = "$CURRENT_BRANCH" ]; then
            echo -e "  ${YELLOW}SKIP: $branch (current branch)${NC}"
            continue
        fi

        MERGED=$(git branch --merged main | sed 's/^[* ]*//' | grep -Fx "$branch" || true)
        if [ -n "$MERGED" ]; then
            STATUS="merged into main"
        else
            STATUS="NOT merged"
        fi

        echo -e "  ${YELLOW}${branch}${NC} ($STATUS)"

        if [ "$MODE" = "--dry-run" ]; then
            echo "    (would prompt for deletion)"
        elif [ "$MODE" = "--auto" ] && [ -n "$MERGED" ]; then
            git branch -d "$branch" 2>/dev/null || true
            echo "    Deleted."
        elif [ "$MODE" != "--auto" ]; then
            if prompt_yes_no "    Delete? [y/N] "; then
                git branch -D "$branch" 2>/dev/null || true
                echo "    Deleted."
            fi
        fi
    done <<< "$AGENT_BRANCHES"
else
    echo -e "  ${GREEN}No agent branches found${NC}"
fi

# --------------------------------------------------------------------------
# 3. Remote prune
# --------------------------------------------------------------------------
echo ""
echo "[3/4] Pruning stale remote tracking branches..."
if [ "$MODE" != "--dry-run" ]; then
    PRUNED=$(git remote prune origin 2>&1 || true)
    if echo "$PRUNED" | grep -q "pruning"; then
        echo "$PRUNED"
    else
        echo -e "  ${GREEN}Nothing to prune${NC}"
    fi
else
    git remote prune origin --dry-run 2>/dev/null || true
fi

# --------------------------------------------------------------------------
# 4. Stashes
# --------------------------------------------------------------------------
echo ""
echo "[4/4] Checking stashes..."
STASH_COUNT=$(git stash list 2>/dev/null | wc -l | tr -d ' ')
if [ "$STASH_COUNT" -gt 0 ]; then
    echo -e "  ${YELLOW}${STASH_COUNT} stash(es) found:${NC}"
    git stash list | head -10
    if [ "$MODE" = "--dry-run" ]; then
        echo "    (would prompt for cleanup)"
    elif [ "$MODE" != "--auto" ]; then
        if prompt_yes_no "  Drop all stashes? [y/N] "; then
            git stash clear
            echo -e "  ${GREEN}Stashes cleared${NC}"
        fi
    fi
else
    echo -e "  ${GREEN}No stashes${NC}"
fi

echo ""
echo -e "${GREEN}Hygiene check complete.${NC}"
echo "============================================"
