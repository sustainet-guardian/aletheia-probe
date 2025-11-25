#!/bin/bash
# Pre-commit quality checks script
# This script runs all code quality checks that are executed in CI/CD
# Run this before committing to catch issues early

set -e  # Exit on first error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Running Code Quality Checks${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Function to run a check and track status
# Only shows output if the check fails
run_check() {
    local check_name="$1"
    shift

    # Capture output in a temporary file
    local tmp_output=$(mktemp)

    if "$@" > "$tmp_output" 2>&1; then
        # Check passed - just show success message
        echo -e "${GREEN}✓ ${check_name}${NC}"
        rm -f "$tmp_output"
        return 0
    else
        # Check failed - show the output
        echo -e "${RED}✗ ${check_name} failed${NC}"
        echo ""
        cat "$tmp_output"
        echo ""
        rm -f "$tmp_output"
        exit 1
    fi
}

# Run checks in order from fastest to slowest
# Fast checks first for quick feedback

# 1. Ruff linting (very fast)
run_check "Ruff linting" ruff check src/ tests/

# 2. Ruff formatting check (very fast)
run_check "Ruff format check" ruff format --check src/ tests/

# 3. Logging consistency check (fast)
run_check "Logging consistency" python scripts/check-logging.py

# 4. SPDX license identifier check (fast)
run_check "SPDX license identifiers" python scripts/check-spdx.py

# 5. Import organization check (fast)
run_check "Import organization" python scripts/find_middle_imports.py

# 6. Markdown link check (medium)
run_check "Markdown link check" python scripts/check-markdown-links.py

# 7. Example execution check (medium)
run_check "Example execution" python scripts/check-examples.py

# 8. Mypy type checking (slower)
run_check "Mypy type checking" mypy src/ --strict

# 9. Pytest with coverage (slowest)
run_check "Pytest with coverage" pytest --cov=src --cov-report=term-missing tests/

# Final summary
echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}✓ All quality checks passed!${NC}"
echo -e "${BLUE}========================================${NC}"
