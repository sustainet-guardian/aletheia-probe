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

# Track overall status
FAILED=0

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Running Code Quality Checks${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Function to run a check and track status
run_check() {
    local check_name="$1"
    shift
    echo -e "${YELLOW}▶ Running: ${check_name}${NC}"
    if "$@"; then
        echo -e "${GREEN}✓ ${check_name} passed${NC}"
        echo ""
        return 0
    else
        echo -e "${RED}✗ ${check_name} failed${NC}"
        echo ""
        FAILED=1
        return 1
    fi
}

# 1. Ruff linting
run_check "Ruff linting" ruff check src/ tests/ || true

# 2. Ruff formatting check
run_check "Ruff format check" ruff format --check src/ tests/ || true

# 3. Mypy type checking
run_check "Mypy type checking" mypy src/ --strict || true

# 4. Pytest with coverage
run_check "Pytest with coverage" pytest --cov=src --cov-report=term-missing tests/ || true

# 5. Logging consistency check
run_check "Logging consistency" python scripts/check-logging.py || true

# 6. SPDX license identifier check
run_check "SPDX license identifiers" python scripts/check-spdx.py || true

# 7. Example execution check
run_check "Example execution" python scripts/check-examples.py || true

# 8. Markdown link check
run_check "Markdown link check" python scripts/check-markdown-links.py || true

# 9. Import organization check
run_check "Import organization" python scripts/find_middle_imports.py

# Final summary
echo -e "${BLUE}========================================${NC}"
if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ All quality checks passed!${NC}"
    echo -e "${BLUE}========================================${NC}"
    exit 0
else
    echo -e "${RED}✗ Some quality checks failed!${NC}"
    echo -e "${YELLOW}Please fix the issues above before committing.${NC}"
    echo -e "${BLUE}========================================${NC}"
    exit 1
fi
