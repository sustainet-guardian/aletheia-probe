#!/bin/bash
# SPDX-License-Identifier: MIT
# Comprehensive benchmark script
# This script runs all performance benchmarks including comprehensive scaling tests
# Run this manually or let it run weekly in CI/CD for detailed performance analysis

set -e  # Exit on first error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Running Comprehensive Performance Benchmarks${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${YELLOW}Note: This includes comprehensive scaling tests${NC}"
echo -e "${YELLOW}and may take several minutes to complete.${NC}"
echo ""

# Function to run a check and track status
run_check() {
    local check_name="$1"
    shift

    echo -e "${BLUE}--- Running: ${check_name} ---${NC}"
    if "$@"; then
        echo -e "${GREEN}✓ ${check_name} passed${NC}"
        echo ""
        return 0
    else
        echo -e "${RED}✗ ${check_name} failed${NC}"
        echo ""
        exit 1
    fi
}

# Run all performance benchmarks including comprehensive ones
# Benchmark tests should run sequentially for accurate timing
run_check "All performance benchmarks" pytest tests/performance/ --benchmark-only --benchmark-json=benchmark-comprehensive.json

# Final summary
echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}✓ All comprehensive benchmarks completed!${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${YELLOW}Benchmark results saved to: benchmark-comprehensive.json${NC}"
