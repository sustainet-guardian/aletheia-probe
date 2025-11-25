#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Find Python files with imports in the middle of the file (after actual code)."""

import ast
import sys
from pathlib import Path


def has_explanatory_comment(lines: list[str], import_line: int) -> bool:
    """Check if import has an explanatory comment (for circular dependency workarounds).

    Args:
        lines: All lines in the file
        import_line: Line number of the import (1-indexed)

    Returns:
        True if there's a comment on the same line or immediately before
    """
    # Check same line (inline comment)
    import_line_content = lines[import_line - 1]
    if "#" in import_line_content:
        return True

    # Check line immediately before
    if import_line > 1:
        prev_line = lines[import_line - 2].strip()
        if prev_line.startswith("#"):
            return True

    return False


def check_file_for_middle_imports(filepath: Path) -> list[tuple[int, str]]:
    """Check if a file has imports after actual code statements.

    Ignores module docstrings and SPDX headers - only flags imports that
    come after real code like class definitions, function definitions, or
    executable statements.

    Also ignores imports with explanatory comments (for circular import workarounds).

    Returns list of (line_number, import_statement) tuples for middle imports.
    """
    try:
        with open(filepath, encoding="utf-8") as f:
            content = f.read()

        lines = content.split('\n')
        tree = ast.parse(content, filename=str(filepath))

        # Skip the module docstring if present
        body_start_idx = 0
        if (tree.body and
            isinstance(tree.body[0], ast.Expr) and
            isinstance(tree.body[0].value, ast.Constant) and
            isinstance(tree.body[0].value.value, str)):
            body_start_idx = 1

        # Track if we've seen actual code (not imports, not docstrings)
        seen_real_code = False
        middle_imports = []

        for node in tree.body[body_start_idx:]:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                # This is an import
                if seen_real_code:
                    # We've seen real code before this import
                    import_line = node.lineno

                    # Check if this import has an explanatory comment
                    if not has_explanatory_comment(lines, import_line):
                        # No comment - this is problematic
                        import_text = lines[import_line - 1].strip()
                        middle_imports.append((import_line, import_text))
            else:
                # This is actual code (class, function, assignment, etc.)
                # Mark that we've seen real code
                seen_real_code = True

        return middle_imports
    except Exception as e:
        print(f"Error processing {filepath}: {e}", file=sys.stderr)
        return []


def main():
    """Find all Python files with middle imports."""
    root = Path(__file__).parent.parent

    # Find all Python files
    py_files = list(root.glob("src/**/*.py")) + list(root.glob("tests/**/*.py"))

    files_with_middle_imports = {}
    total_middle_imports = 0

    for py_file in py_files:
        middle_imports = check_file_for_middle_imports(py_file)
        if middle_imports:
            rel_path = py_file.relative_to(root)
            files_with_middle_imports[str(rel_path)] = middle_imports
            total_middle_imports += len(middle_imports)

    # Print results
    if files_with_middle_imports:
        print(f"Found {total_middle_imports} imports after code across {len(files_with_middle_imports)} files:\n")

        for filepath, imports in sorted(files_with_middle_imports.items()):
            print(f"{filepath}:")
            for line_num, import_text in imports:
                print(f"  Line {line_num}: {import_text}")
            print()
    else:
        print("No problematic imports found in middle of files.")

    return len(files_with_middle_imports)


if __name__ == "__main__":
    sys.exit(main())
