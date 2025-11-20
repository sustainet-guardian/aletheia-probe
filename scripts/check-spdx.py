#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Script to verify SPDX license identifiers are present in all Python files."""

import sys
from pathlib import Path


def check_spdx_header(file_path: Path) -> tuple[bool, str]:
    """Check if a Python file has a valid SPDX license identifier.

    Returns:
        Tuple of (has_valid_spdx, error_message)
    """
    try:
        with open(file_path, encoding='utf-8') as f:
            lines = f.readlines()
    except Exception as e:
        return False, f"Error reading file: {e}"

    if not lines:
        return False, "File is empty"

    # Check first few lines for SPDX identifier
    for line in lines[:10]:  # Check first 10 lines
        if 'SPDX-License-Identifier:' in line:
            # Verify it's the correct MIT license
            if 'MIT' in line:
                # Check that it's a properly formatted comment
                stripped = line.strip()
                if stripped.startswith('#') and 'SPDX-License-Identifier: MIT' in stripped:
                    return True, ""
                else:
                    return False, f"SPDX header found but incorrectly formatted: '{stripped}'"
            else:
                return False, f"SPDX header found but wrong license: '{line.strip()}'"

    return False, "No SPDX license identifier found"


def main() -> int:
    """Main function to check SPDX headers in all Python files."""
    project_root = Path(__file__).parent.parent

    # Find all Python files
    python_files = list(project_root.glob("**/*.py"))

    # Remove this script itself from the check if it exists
    script_path = Path(__file__).resolve()
    python_files = [f for f in python_files if f.resolve() != script_path]

    missing_spdx: list[tuple[Path, str]] = []
    total_files = len(python_files)

    print(f"Checking SPDX license identifiers in {total_files} Python files...")

    for py_file in python_files:
        has_spdx, error_msg = check_spdx_header(py_file)
        if not has_spdx:
            missing_spdx.append((py_file, error_msg))

    # Report results
    if missing_spdx:
        print(f"\n❌ SPDX Check FAILED: {len(missing_spdx)} file(s) missing or have invalid SPDX headers:")
        for file_path, error in missing_spdx:
            rel_path = file_path.relative_to(project_root)
            print(f"  - {rel_path}: {error}")

        print("\nTo fix these issues, add the following line at the top of each file")
        print("(after any shebang line):")
        print("  # SPDX-License-Identifier: MIT")

        return 1  # Exit with error code
    else:
        print(f"✅ SPDX Check PASSED: All {total_files} Python files have valid SPDX headers")
        return 0


if __name__ == "__main__":
    sys.exit(main())
