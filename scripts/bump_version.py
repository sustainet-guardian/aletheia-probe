#!/usr/bin/env python3
"""
Version bumping utility for aletheia-probe.

This script helps manage semantic versioning by automatically updating
the version in pyproject.toml and optionally creating a git tag.

Usage:
    python scripts/bump_version.py patch    # 0.1.0 -> 0.1.1
    python scripts/bump_version.py minor    # 0.1.0 -> 0.2.0
    python scripts/bump_version.py major    # 0.1.0 -> 1.0.0
    python scripts/bump_version.py 0.2.0    # Set specific version
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path


def get_current_version() -> str:
    """Read current version from pyproject.toml."""
    pyproject_path = Path("pyproject.toml")
    if not pyproject_path.exists():
        print("ERROR: pyproject.toml not found. Run this script from the repository root.")
        sys.exit(1)

    content = pyproject_path.read_text()
    match = re.search(r'version = "(\d+\.\d+\.\d+)"', content)
    if not match:
        print("ERROR: Could not find version in pyproject.toml")
        sys.exit(1)

    return match.group(1)


def parse_version(version: str) -> tuple[int, int, int]:
    """Parse version string into components."""
    parts = version.split(".")
    if len(parts) != 3:
        print(f"ERROR: Invalid version format: {version}")
        sys.exit(1)

    try:
        return int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        print(f"ERROR: Invalid version format: {version}")
        sys.exit(1)


def bump_version(current: str, bump_type: str) -> str:
    """Bump version based on type (major, minor, patch)."""
    major, minor, patch = parse_version(current)

    if bump_type == "major":
        return f"{major + 1}.0.0"
    elif bump_type == "minor":
        return f"{major}.{minor + 1}.0"
    elif bump_type == "patch":
        return f"{major}.{minor}.{patch + 1}"
    else:
        # Assume it's a specific version
        parse_version(bump_type)  # Validate format
        return bump_type


def update_pyproject(new_version: str) -> None:
    """Update version in pyproject.toml."""
    pyproject_path = Path("pyproject.toml")
    content = pyproject_path.read_text()

    new_content = re.sub(
        r'version = "\d+\.\d+\.\d+"', f'version = "{new_version}"', content
    )

    if content == new_content:
        print("ERROR: Failed to update version in pyproject.toml")
        sys.exit(1)

    pyproject_path.write_text(new_content)
    print(f"✓ Updated pyproject.toml to version {new_version}")


def check_git_clean() -> bool:
    """Check if git working directory is clean."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True, check=True
        )
        return len(result.stdout.strip()) == 0
    except subprocess.CalledProcessError:
        return False


def create_git_commit(version: str, tag: bool = False) -> None:
    """Create git commit and optionally tag."""
    try:
        # Add pyproject.toml
        subprocess.run(["git", "add", "pyproject.toml"], check=True)

        # Commit
        subprocess.run(
            ["git", "commit", "-m", f"Bump version to {version}"], check=True
        )
        print(f"✓ Created commit for version {version}")

        if tag:
            # Create tag
            subprocess.run(
                ["git", "tag", "-a", f"v{version}", "-m", f"Release version {version}"],
                check=True,
            )
            print(f"✓ Created git tag v{version}")
            print("\nTo push the changes:")
            print(f"  git push origin main")
            print(f"  git push origin v{version}")

    except subprocess.CalledProcessError as e:
        print(f"ERROR: Git operation failed: {e}")
        sys.exit(1)


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Bump version for aletheia-probe",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s patch           # Bump patch version (0.1.0 -> 0.1.1)
  %(prog)s minor           # Bump minor version (0.1.0 -> 0.2.0)
  %(prog)s major           # Bump major version (0.1.0 -> 1.0.0)
  %(prog)s 0.2.0           # Set specific version
  %(prog)s minor --tag     # Bump minor and create git tag
  %(prog)s 1.0.0 --no-git  # Only update file, don't commit
        """,
    )
    parser.add_argument(
        "bump_type",
        help="Version bump type (major, minor, patch) or specific version (e.g., 1.2.3)",
    )
    parser.add_argument(
        "--tag",
        action="store_true",
        help="Create a git tag for the new version",
    )
    parser.add_argument(
        "--no-git",
        action="store_true",
        help="Only update pyproject.toml, don't create git commit",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force version bump even if git working directory is not clean",
    )

    args = parser.parse_args()

    # Get current version
    current_version = get_current_version()
    print(f"Current version: {current_version}")

    # Calculate new version
    new_version = bump_version(current_version, args.bump_type)
    print(f"New version: {new_version}")

    # Check if versions are the same
    if current_version == new_version:
        print("ERROR: New version is the same as current version")
        sys.exit(1)

    # Check git status if we're going to commit
    if not args.no_git and not args.force and not check_git_clean():
        print(
            "\nWARNING: Git working directory is not clean."
        )
        print("Please commit or stash your changes before bumping version.")
        print("Or use --force to proceed anyway, or --no-git to skip git operations.")
        sys.exit(1)

    # Update pyproject.toml
    update_pyproject(new_version)

    # Git operations
    if not args.no_git:
        create_git_commit(new_version, tag=args.tag)
    else:
        print("\nTo commit this change manually:")
        print(f"  git add pyproject.toml")
        print(f"  git commit -m 'Bump version to {new_version}'")
        if args.tag:
            print(f"  git tag -a v{new_version} -m 'Release version {new_version}'")

    print(f"\n✓ Successfully bumped version from {current_version} to {new_version}")


if __name__ == "__main__":
    main()
