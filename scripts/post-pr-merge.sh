#!/bin/bash
# Post-PR merge cleanup script
# Run this after successfully merging a PR to clean up local branches and update main
# Usage: ./scripts/post-pr-merge.sh [branch-name]
#   If branch-name is not provided, will use the current branch

set -e  # Exit on first error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Post-PR Merge Cleanup${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Get the branch name to delete
BRANCH_TO_DELETE=""
if [ -n "$1" ]; then
    BRANCH_TO_DELETE="$1"
else
    # Get current branch name
    BRANCH_TO_DELETE=$(git branch --show-current)
fi

# Safety check: don't delete main or develop branches
if [ "$BRANCH_TO_DELETE" = "main" ] || [ "$BRANCH_TO_DELETE" = "develop" ]; then
    echo -e "${RED}✗ Error: Cannot delete main or develop branch${NC}"
    echo -e "${YELLOW}  Please checkout a feature branch first${NC}"
    exit 1
fi

echo -e "${YELLOW}Branch to delete: ${BRANCH_TO_DELETE}${NC}"
echo ""

# Check if we're on the branch to be deleted
CURRENT_BRANCH=$(git branch --show-current)
if [ "$CURRENT_BRANCH" = "$BRANCH_TO_DELETE" ]; then
    # Switch to main branch
    echo -e "${YELLOW}▶ Checking out main branch...${NC}"
    git checkout main
    echo -e "${GREEN}✓ Switched to main${NC}"
    echo ""
fi

# Pull latest changes from remote
echo -e "${YELLOW}▶ Pulling latest changes from remote...${NC}"
git pull origin main
echo -e "${GREEN}✓ Main branch updated${NC}"
echo ""

# Delete local branch
echo -e "${YELLOW}▶ Deleting local branch: ${BRANCH_TO_DELETE}${NC}"
if git branch -d "$BRANCH_TO_DELETE" 2>/dev/null; then
    echo -e "${GREEN}✓ Local branch deleted${NC}"
else
    # If -d fails, try -D (force delete)
    echo -e "${YELLOW}  Branch has unmerged changes, using force delete...${NC}"
    git branch -D "$BRANCH_TO_DELETE"
    echo -e "${GREEN}✓ Local branch force deleted${NC}"
fi
echo ""

# Delete remote branch if it exists
echo -e "${YELLOW}▶ Checking for remote branch...${NC}"
if git ls-remote --exit-code --heads origin "$BRANCH_TO_DELETE" >/dev/null 2>&1; then
    echo -e "${YELLOW}  Deleting remote branch: ${BRANCH_TO_DELETE}${NC}"
    git push origin --delete "$BRANCH_TO_DELETE"
    echo -e "${GREEN}✓ Remote branch deleted${NC}"
else
    echo -e "${BLUE}  Remote branch already deleted${NC}"
fi
echo ""

# Prune remote tracking branches
echo -e "${YELLOW}▶ Pruning stale remote tracking branches...${NC}"
git fetch --prune
echo -e "${GREEN}✓ Remote tracking branches pruned${NC}"
echo ""

# Show current status
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Cleanup Complete${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${GREEN}✓ Current branch: $(git branch --show-current)${NC}"
echo -e "${GREEN}✓ Latest commit: $(git log -1 --oneline)${NC}"
echo ""

# Show remaining local branches (excluding main and develop)
echo -e "${BLUE}Remaining local branches:${NC}"
git branch | grep -v "^\*" | grep -v "main" | grep -v "develop" || echo -e "${BLUE}  (none)${NC}"
echo ""

echo -e "${GREEN}✨ All done! Ready for the next feature.${NC}"
