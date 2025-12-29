#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Dead code detection using runtime tracing.

This script:
1. Discovers all functions/methods in src/aletheia_probe/
2. Runs representative CLI commands in real environment
3. Tracks which functions are actually called
4. Reports functions that were never executed
"""

import ast
import sys
from pathlib import Path
from types import FrameType
from typing import Any


class FunctionTracer:
    """Trace function calls during execution."""

    def __init__(self, src_root: Path) -> None:
        """Initialize tracer.

        Args:
            src_root: Root directory to trace (src/aletheia_probe/)
        """
        self.src_root = src_root
        self.called_functions: set[tuple[str, str]] = set()

    def trace_function(
        self, frame: FrameType, event: str, arg: Any
    ) -> Any:
        """Trace callback for sys.settrace().

        Args:
            frame: Current stack frame
            event: Trace event type
            arg: Event argument

        Returns:
            Trace function to continue tracing, or None
        """
        if event != "call":
            return self.trace_function

        code = frame.f_code
        filename = code.co_filename

        # Only track calls in src/aletheia_probe/
        if not filename.startswith(str(self.src_root)):
            return self.trace_function

        # Get function name
        func_name = code.co_name

        # Try to get class name from frame locals
        class_name = None
        if "self" in frame.f_locals:
            class_name = frame.f_locals["self"].__class__.__name__
        elif "cls" in frame.f_locals:
            class_name = frame.f_locals["cls"].__name__

        # Build qualified name
        if class_name:
            qualified_name = f"{class_name}.{func_name}"
        else:
            qualified_name = func_name

        # Get module path relative to src
        try:
            module_path = Path(filename).relative_to(self.src_root.parent)
            module_str = str(module_path).replace("/", ".").replace(".py", "")
        except ValueError:
            # Not in src tree, ignore
            return self.trace_function

        self.called_functions.add((module_str, qualified_name))

        return self.trace_function

    def start(self) -> None:
        """Start tracing."""
        sys.settrace(self.trace_function)

    def stop(self) -> None:
        """Stop tracing."""
        sys.settrace(None)


class FunctionDiscoverer:
    """Discover all functions/methods in source code using AST."""

    def __init__(self, src_root: Path) -> None:
        """Initialize discoverer.

        Args:
            src_root: Root directory to analyze (src/aletheia_probe/)
        """
        self.src_root = src_root
        self.all_functions: set[tuple[str, str, int]] = set()

    def discover(self) -> None:
        """Discover all functions in src directory."""
        for py_file in self.src_root.rglob("*.py"):
            if "__pycache__" in py_file.parts:
                continue

            self._analyze_file(py_file)

    def _analyze_file(self, file_path: Path) -> None:
        """Analyze a Python file for functions.

        Args:
            file_path: Path to Python file
        """
        try:
            source = file_path.read_text()
            tree = ast.parse(source, filename=str(file_path))

            # Get module path
            module_path = file_path.relative_to(self.src_root.parent)
            module_str = str(module_path).replace("/", ".").replace(".py", "")

            # Walk AST and find all function definitions
            self._walk_ast(tree, module_str, None)

        except SyntaxError as e:
            print(f"Warning: Could not parse {file_path}: {e}")

    def _walk_ast(
        self, node: ast.AST, module_str: str, parent_class: str | None
    ) -> None:
        """Recursively walk AST to find functions.

        Args:
            node: AST node to walk
            module_str: Module name
            parent_class: Parent class name if inside a class
        """
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                # Recurse into class with class name as parent
                self._walk_ast(child, module_str, child.name)

            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Found a function/method
                if parent_class:
                    qualified_name = f"{parent_class}.{child.name}"
                else:
                    qualified_name = child.name

                self.all_functions.add((module_str, qualified_name, child.lineno))

                # Don't recurse into nested functions to keep it function-level
                # (user wants function-level, not nested functions)

            else:
                # Continue walking for classes
                if isinstance(node, ast.ClassDef):
                    self._walk_ast(child, module_str, parent_class)


class CLIRunner:
    """Run CLI commands programmatically."""

    def __init__(self) -> None:
        """Initialize CLI runner."""
        # Import here to ensure imports are traced
        from click.testing import CliRunner

        from aletheia_probe.cli import main

        self.cli_main = main
        self.runner = CliRunner()

    def run_representative_commands(self) -> None:
        """Run representative commands to exercise code paths."""
        import tempfile
        from pathlib import Path

        # Create temporary bibtex file with complex entries to trigger parsing
        bibtex_content = """@article{nature2023,
  author = {Smith, John and Doe, Jane and M\\"{u}ller, Anna},
  title = {Test Article with {LaTeX} and $\\alpha$ symbols},
  journal = {{Nature}},
  year = {2023},
  volume = {1},
  pages = {1--10},
  doi = {10.1038/s41586-023-00001-1},
  issn = {0028-0836}
}

@article{jmlr2022,
  author = {Brown, Alice},
  title = {Machine Learning Paper},
  journal = {Journal of Machine Learning Research},
  year = {2022},
  volume = {23},
  pages = {1-50},
  issn = {1532-4435}
}

@inproceedings{icml2023,
  author = {Doe, Jane and O'Brien, Patrick},
  title = {{{Deep Learning}}},
  booktitle = {International Conference on Machine Learning},
  year = {2023},
  pages = {100--110}
}

@inproceedings{neurips2023,
  author = {Kumar, Raj},
  title = {Neural Networks},
  booktitle = {NeurIPS},
  year = {2023}
}

@article{preprint2024,
  author = {Zhang, Wei},
  title = {Preprint Article},
  journal = {arXiv},
  year = {2024},
  eprint = {2401.12345}
}

@article{plos2023,
  author = {Garcia, Maria},
  title = {Biology Paper},
  journal = {PLOS ONE},
  year = {2023},
  doi = {10.1371/journal.pone.0123456},
  issn = {1932-6203}
}

@article{wakefield1998,
  author = {Wakefield, Andrew J and others},
  title = {Ileal-lymphoid-nodular hyperplasia},
  journal = {The Lancet},
  year = {1998},
  doi = {10.1016/S0140-6736(97)11096-0},
  note = {This is a famous retracted article}
}
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".bib", delete=False
        ) as tmp:
            tmp.write(bibtex_content)
            bibtex_file = tmp.name

        # Create temporary CSV file for custom list testing
        csv_content = """journal_name,issn,publisher
Test Journal,1234-5678,Test Publisher
Another Journal,9876-5432,Another Publisher
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False
        ) as tmp_csv:
            tmp_csv.write(csv_content)
            csv_file = tmp_csv.name

        # Create temporary JSON file for custom list testing
        json_content = """[
  {
    "journal_name": "JSON Test Journal",
    "issn": "1111-2222",
    "publisher": "JSON Publisher"
  },
  {
    "journal_name": "Second JSON Journal",
    "issn": "3333-4444"
  }
]
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as tmp_json:
            tmp_json.write(json_content)
            json_file = tmp_json.name

        try:
            # List of commands to run
            commands = [
                # Sync FIRST - all other commands rely on cached data
                ["sync"],
                # Sync specific backends
                ["sync", "doaj"],
                ["sync", "bealls"],
                # Config operations
                ["config"],
                # Cache operations
                ["status"],
                # Journal assessment - legitimate journals
                ["journal", "Nature"],
                ["journal", "Nature", "--verbose"],
                ["journal", "Science", "--format", "json"],
                ["journal", "PLOS ONE", "--verbose", "--format", "json"],
                ["journal", "Cell"],
                # Journal assessment - open access journals
                ["journal", "JMLR"],
                ["journal", "Journal of Machine Learning Research", "--format", "json"],
                # Journal assessment - potentially predatory (if in lists)
                ["journal", "International Journal of Advanced Research"],
                ["journal", "World Journal of Science"],
                # Journal assessment - edge cases and diverse queries
                ["journal", "BMC Medicine"],  # Open access
                ["journal", "Frontiers in Psychology"],  # Large publisher
                ["journal", "IEEE Transactions on Pattern Analysis"],  # IEEE
                ["journal", "Lancet"],  # Well-known medical journal
                ["journal", "Test Journal That Does Not Exist"],  # Non-existent
                # Conference assessment - legitimate
                ["conference", "ICML"],
                ["conference", "ICML", "--verbose"],
                ["conference", "NeurIPS", "--format", "json"],
                ["conference", "International Conference on Machine Learning"],
                # Conference assessment - various formats
                ["conference", "CVPR"],
                ["conference", "ACL", "--verbose"],
                ["conference", "Conference on Computer Vision"],  # Full name
                ["conference", "AAAI"],  # AI conference
                ["conference", "Some Unknown Conference"],  # Non-existent
                # BibTeX batch processing (various options)
                ["bibtex", bibtex_file],
                ["bibtex", bibtex_file, "--format", "json"],
                ["bibtex", bibtex_file, "--verbose"],
                ["bibtex", bibtex_file, "--relax-bibtex"],
                ["bibtex", bibtex_file, "--verbose", "--format", "json"],
                # Custom list operations - CSV
                ["add-list", csv_file, "--list-type", "PREDATORY", "--list-name", "test-csv"],
                # Custom list operations - JSON
                ["add-list", json_file, "--list-type", "SUSPICIOUS", "--list-name", "test-json"],
                # Status after adding custom lists
                ["status"],
                # Acronym operations
                ["acronym", "status"],
                ["acronym", "stats"],
                ["acronym", "list", "--limit", "5"],
                ["acronym", "add", "ICML", "International Conference on Machine Learning"],
                ["acronym", "add", "NeurIPS", "Neural Information Processing Systems", "--entity-type", "conference"],
                ["acronym", "list", "--limit", "10"],
                ["acronym", "list", "--offset", "5", "--limit", "5"],
                # Clear operations (at the end)
                ["clear-cache", "--confirm"],
                ["acronym", "clear", "--confirm"],
            ]

            for cmd in commands:
                print(f"Running: aletheia-probe {' '.join(cmd)}")
                try:
                    result = self.runner.invoke(
                        self.cli_main, cmd, catch_exceptions=False
                    )
                    if result.exit_code != 0 and result.exit_code != 1:
                        # Exit code 1 is expected for bibtex with predatory journals
                        print(f"  Warning: Exit code {result.exit_code}")
                except Exception as e:
                    print(f"  Error: {e}")

        finally:
            # Cleanup temp files
            Path(bibtex_file).unlink(missing_ok=True)
            Path(csv_file).unlink(missing_ok=True)
            Path(json_file).unlink(missing_ok=True)


def _should_ignore(module: str, qualified_name: str) -> bool:
    """Filter known false positives.

    Args:
        module: Module name
        qualified_name: Qualified function name

    Returns:
        True if should be ignored
    """
    # Ignore magic methods
    if qualified_name.startswith("__") and qualified_name.endswith("__"):
        return True

    # Ignore test files (shouldn't be in src but just in case)
    if "test" in module.lower():
        return True

    # Ignore module-level code
    if qualified_name == "<module>":
        return True

    return False


def main() -> None:
    """Main entry point."""
    # Setup paths
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent
    src_root = repo_root / "src" / "aletheia_probe"

    print("=" * 80)
    print("Dead Code Detection - Runtime Tracing")
    print("=" * 80)

    # Step 1: Discover all functions
    print("\n[1/4] Discovering functions in src/aletheia_probe/...")
    discoverer = FunctionDiscoverer(src_root)
    discoverer.discover()
    print(f"Found {len(discoverer.all_functions)} functions/methods")

    # Step 2: Start tracing
    print("\n[2/4] Installing runtime tracer...")
    tracer = FunctionTracer(src_root)
    tracer.start()

    # Step 3: Run commands
    print("\n[3/4] Running representative CLI commands...")
    print("(This will run sync and may take a few minutes)\n")
    try:
        runner = CLIRunner()
        runner.run_representative_commands()
    finally:
        tracer.stop()

    print(f"\nTracked {len(tracer.called_functions)} unique function calls")

    # Step 4: Compare
    print("\n[4/4] Analyzing dead code...")

    # Build lookup of called functions (module, name)
    called_lookup = {(mod, name) for mod, name in tracer.called_functions}

    # Find dead code
    dead_functions = []
    for module, qualified_name, line in discoverer.all_functions:
        if (module, qualified_name) not in called_lookup:
            # Filter out common false positives
            if not _should_ignore(module, qualified_name):
                dead_functions.append((module, qualified_name, line))

    # Sort and report
    dead_functions.sort()

    print("\n" + "=" * 80)
    print(f"DEAD CODE REPORT: {len(dead_functions)} potentially unused functions")
    print("=" * 80)

    if not dead_functions:
        print("\n✅ No dead code detected!")
        return

    # Group by module
    by_module: dict[str, list[tuple[str, int]]] = {}
    for module, name, line in dead_functions:
        if module not in by_module:
            by_module[module] = []
        by_module[module].append((name, line))

    for module in sorted(by_module.keys()):
        print(f"\n{module}:")
        for name, line in sorted(by_module[module]):
            print(f"  Line {line:4d}: {name}")

    # Summary statistics
    print("\n" + "=" * 80)
    print("Summary:")
    print(f"  Total functions discovered: {len(discoverer.all_functions)}")
    print(f"  Functions called: {len(tracer.called_functions)}")
    print(f"  Dead code candidates: {len(dead_functions)}")
    coverage = len(tracer.called_functions) / len(discoverer.all_functions) * 100
    print(f"  Coverage: {coverage:.1f}%")


if __name__ == "__main__":
    main()
