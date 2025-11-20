#!/usr/bin/env python3
"""Script to enforce consistent logging practices in the codebase.

This script checks that no files use direct logging.getLogger() and instead
use the project's centralized detail_logger and status_logger.

Usage:
    python scripts/check-logging.py

Exit code:
    0: All checks pass
    1: Violations found
"""

import subprocess
import sys
from pathlib import Path


def check_direct_logger_usage():
    """Check for direct logging.getLogger() usage."""
    violations = []

    # Find all Python files in src directory
    src_dir = Path("src")
    if not src_dir.exists():
        print("ERROR: src directory not found. Run this script from the project root.")
        return False

    # Search for logging.getLogger(__name__) pattern
    try:
        result = subprocess.run(
            ["grep", "-r", "-n", "logging\\.getLogger(__name__)", str(src_dir)],
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            violations = result.stdout.strip().split("\n")

    except FileNotFoundError:
        print("ERROR: grep command not found. Install grep to run this check.")
        return False

    if violations:
        print("❌ LOGGING VIOLATIONS FOUND:")
        print()
        print(
            "The following files use direct logging.getLogger() instead of project loggers:"
        )
        print()

        for violation in violations:
            print(f"  {violation}")

        print()
        print("Fix these by:")
        print("1. Remove 'import logging' and 'logger = logging.getLogger(__name__)'")
        print(
            "2. Add: from .logging_config import get_detail_logger, get_status_logger"
        )
        print(
            "3. Add: detail_logger = get_detail_logger(); status_logger = get_status_logger()"
        )
        print(
            "4. Use detail_logger for technical details, status_logger for user messages"
        )
        print()
        return False

    print("✅ All logging checks pass!")
    return True


def check_logger_imports():
    """Check that files using loggers import from logging_config."""
    try:
        # Find files that use detail_logger or status_logger but don't import them
        result = subprocess.run(
            [
                "grep",
                "-r",
                "-l",
                "--include=*.py",
                "detail_logger\\|status_logger",
                "src",
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            return True  # No files use loggers, that's fine

        files_using_loggers = result.stdout.strip().split("\n")
        violations = []

        for file_path in files_using_loggers:
            # Skip the logging_config.py file itself and __pycache__ files
            if "logging_config.py" in file_path or "__pycache__" in file_path:
                continue

            # Check if file imports from logging_config
            import_result = subprocess.run(
                ["grep", "-q", "from.*logging_config import", file_path],
                capture_output=True,
            )

            if import_result.returncode != 0:
                violations.append(file_path)

        if violations:
            print("❌ LOGGING IMPORT VIOLATIONS:")
            print()
            print("Files use loggers but don't import from logging_config:")
            for violation in violations:
                print(f"  {violation}")
            print()
            return False

    except FileNotFoundError:
        print("WARNING: Could not run logger import check (grep not available)")

    return True


def main():
    """Run all logging checks."""
    print("Checking logging consistency...")
    print()

    checks_pass = True

    # Check for direct logger usage
    if not check_direct_logger_usage():
        checks_pass = False

    print()

    # Check for proper imports
    if not check_logger_imports():
        checks_pass = False

    if checks_pass:
        print("✅ All logging checks passed!")
        return 0
    else:
        print("❌ Logging violations found. Please fix them before committing.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
