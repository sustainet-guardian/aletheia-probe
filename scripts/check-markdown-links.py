#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Script to check for broken links in markdown documentation files.

This script validates all internal file links in markdown files to ensure
they point to existing files. External URLs are optionally checked but may
fail due to CAPTCHA or other restrictions.

Usage:
    python scripts/check-markdown-links.py [--check-external]

Exit code:
    0: All checks pass
    1: Broken links found
"""

import re
import sys
import urllib.request
from pathlib import Path
from typing import NamedTuple
from urllib.error import HTTPError, URLError


class Link(NamedTuple):
    """Represents a link found in a markdown file."""

    file_path: Path
    line_number: int
    link_text: str
    link_target: str
    is_external: bool


class LinkCheckResult(NamedTuple):
    """Result of checking a link."""

    link: Link
    exists: bool
    error_message: str | None = None


def find_markdown_files(root_dir: Path) -> list[Path]:
    """Find all markdown files in the repository.

    Args:
        root_dir: Root directory to search from

    Returns:
        List of markdown file paths
    """
    # Exclude certain directories
    exclude_dirs = {".pytest_cache", "__pycache__", ".git", "node_modules", ".venv"}

    markdown_files = []
    for md_file in root_dir.rglob("*.md"):
        # Skip if any parent directory is in exclude list
        if any(part in exclude_dirs for part in md_file.parts):
            continue
        markdown_files.append(md_file)

    return sorted(markdown_files)


def extract_links(file_path: Path) -> list[Link]:
    """Extract all markdown links from a file.

    Args:
        file_path: Path to markdown file

    Returns:
        List of Link objects found in the file
    """
    links = []

    # Match markdown links: [text](url) or [text](path)
    link_pattern = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

    try:
        content = file_path.read_text(encoding="utf-8")
        for line_num, line in enumerate(content.split("\n"), start=1):
            for match in link_pattern.finditer(line):
                link_text = match.group(1)
                link_target = match.group(2)

                # Skip anchor-only links (#section)
                if link_target.startswith("#"):
                    continue

                # Determine if external (http/https) or internal (file path)
                is_external = link_target.startswith(("http://", "https://"))

                links.append(
                    Link(
                        file_path=file_path,
                        line_number=line_num,
                        link_text=link_text,
                        link_target=link_target,
                        is_external=is_external,
                    )
                )

    except Exception as e:
        print(f"Warning: Could not read {file_path}: {e}")

    return links


def check_internal_link(link: Link, root_dir: Path) -> LinkCheckResult:
    """Check if an internal file link points to an existing file.

    Args:
        link: Link to check
        root_dir: Repository root directory

    Returns:
        LinkCheckResult indicating if the link is valid
    """
    # Remove fragment identifier (#section) if present
    target_path = link.link_target.split("#")[0]

    # Handle relative paths
    if target_path.startswith("/"):
        # Absolute path from repo root
        full_path = root_dir / target_path.lstrip("/")
    else:
        # Relative to the markdown file's directory
        full_path = (link.file_path.parent / target_path).resolve()

    if full_path.exists():
        return LinkCheckResult(link=link, exists=True)
    else:
        error_msg = f"File not found: {target_path}"
        return LinkCheckResult(link=link, exists=False, error_message=error_msg)


def check_external_link(link: Link) -> LinkCheckResult:
    """Check if an external URL is accessible.

    Note: This may fail for sites with CAPTCHA or bot protection.

    Args:
        link: Link to check

    Returns:
        LinkCheckResult indicating if the URL is accessible
    """
    try:
        # Set a reasonable timeout and user agent
        req = urllib.request.Request(
            link.link_target,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; LinkChecker/1.0)",
            },
        )

        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                return LinkCheckResult(link=link, exists=True)
            else:
                error_msg = f"HTTP {response.status}"
                return LinkCheckResult(link=link, exists=False, error_message=error_msg)

    except HTTPError as e:
        # Some sites may block automated requests or require CAPTCHA
        if e.code in (403, 429):
            # Treat as warning, not error (might be CAPTCHA or rate limiting)
            return LinkCheckResult(
                link=link,
                exists=True,
                error_message=f"⚠️ HTTP {e.code} (may require CAPTCHA)",
            )
        error_msg = f"HTTP {e.code}: {e.reason}"
        return LinkCheckResult(link=link, exists=False, error_message=error_msg)

    except URLError as e:
        error_msg = f"URL error: {e.reason}"
        return LinkCheckResult(link=link, exists=False, error_message=error_msg)

    except Exception as e:
        error_msg = f"Unexpected error: {e!s}"
        return LinkCheckResult(link=link, exists=False, error_message=error_msg)


def main() -> int:
    """Run markdown link checks."""
    check_external = "--check-external" in sys.argv

    print("Checking markdown links...")
    print()

    # Find repository root (assuming script is in scripts/ directory)
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent

    if not repo_root.exists():
        print("ERROR: Could not find repository root.")
        return 1

    # Find all markdown files
    markdown_files = find_markdown_files(repo_root)
    print(f"Found {len(markdown_files)} markdown files to check")
    print()

    # Extract all links
    all_links = []
    for md_file in markdown_files:
        links = extract_links(md_file)
        all_links.extend(links)

    internal_links = [link for link in all_links if not link.is_external]
    external_links = [link for link in all_links if link.is_external]

    print(
        f"Found {len(internal_links)} internal links and {len(external_links)} external links"
    )
    print()

    # Check internal links
    print("Checking internal file links...")
    broken_internal = []
    for link in internal_links:
        result = check_internal_link(link, repo_root)
        if not result.exists:
            broken_internal.append(result)

    if broken_internal:
        print(f"❌ Found {len(broken_internal)} broken internal links:")
        print()
        for result in broken_internal:
            rel_path = result.link.file_path.relative_to(repo_root)
            print(f"  {rel_path}:{result.link.line_number}")
            print(f"    Link: [{result.link.link_text}]({result.link.link_target})")
            print(f"    Error: {result.error_message}")
            print()
    else:
        print("✅ All internal links are valid!")
        print()

    # Check external links if requested
    warnings = []
    if check_external:
        print("Checking external URLs...")
        broken_external = []
        for link in external_links:
            result = check_external_link(link)
            if not result.exists:
                broken_external.append(result)
            elif result.error_message and "⚠️" in result.error_message:
                warnings.append(result)

        if broken_external:
            print(f"❌ Found {len(broken_external)} broken external links:")
            print()
            for result in broken_external:
                rel_path = result.link.file_path.relative_to(repo_root)
                print(f"  {rel_path}:{result.link.line_number}")
                print(f"    Link: [{result.link.link_text}]({result.link.link_target})")
                print(f"    Error: {result.error_message}")
                print()
        else:
            print("✅ All external links are accessible!")
            print()

        if warnings:
            print(f"⚠️ {len(warnings)} external link(s) with warnings:")
            for result in warnings:
                rel_path = result.link.file_path.relative_to(repo_root)
                print(f"  {rel_path}:{result.link.line_number}")
                print(f"    Link: {result.link.link_target}")
                print(f"    Warning: {result.error_message}")
            print()
    else:
        print("ℹ️ Skipping external link checks (use --check-external to enable)")
        print()

    # Return exit code based on broken links
    if broken_internal:
        print("❌ Broken internal links found. Please fix them before committing.")
        return 1
    elif check_external and broken_external:
        print("❌ Broken external links found.")
        return 1
    else:
        print("✅ All markdown link checks passed!")
        return 0


if __name__ == "__main__":
    sys.exit(main())
