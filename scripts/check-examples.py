#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Check that all example scripts execute successfully."""

import subprocess
import sys
from pathlib import Path


def main() -> int:
    """Execute all example scripts and verify they run without errors."""
    # Find the project root (parent of scripts directory)
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    examples_dir = project_root / "examples"

    # Find all Python example files
    example_files = sorted(examples_dir.glob("*.py"))

    if not example_files:
        print("No example files found in examples/ directory")
        return 1

    print(f"Checking {len(example_files)} example script(s)...\n")

    failed_examples = []

    for example_file in example_files:
        print(f"Running: {example_file.name}")
        try:
            # Run the example with a timeout
            result = subprocess.run(
                [sys.executable, str(example_file)],
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                failed_examples.append(example_file.name)
                print(f"❌ FAILED: {example_file.name}")
                print(f"\nStdout:\n{result.stdout}")
                print(f"\nStderr:\n{result.stderr}")
                print()
            else:
                print(f"✅ PASSED: {example_file.name}\n")

        except subprocess.TimeoutExpired:
            failed_examples.append(example_file.name)
            print(f"❌ TIMEOUT: {example_file.name} (exceeded 30 seconds)\n")
        except Exception as e:
            failed_examples.append(example_file.name)
            print(f"❌ ERROR: {example_file.name}: {e}\n")

    # Print summary
    print("=" * 60)
    if failed_examples:
        print(f"❌ Example Check FAILED: {len(failed_examples)} script(s) failed:")
        for example in failed_examples:
            print(f"  - {example}")
        return 1
    else:
        print(f"✅ All {len(example_files)} example script(s) executed successfully")
        return 0


if __name__ == "__main__":
    sys.exit(main())
