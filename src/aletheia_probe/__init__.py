# SPDX-License-Identifier: MIT
"""Journal Assessment Tool - Automated predatory journal detection."""

import subprocess
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

# Import main components to ensure they're available
from . import backends as backends
from . import dispatcher as dispatcher


__all__: list[str] = ["backends", "dispatcher", "__version__", "get_full_version"]

# Get version from installed package metadata
__version__: str
try:
    __version__ = version("aletheia-probe")
except PackageNotFoundError:
    # Package is not installed, use development fallback
    __version__ = "development"


def _get_git_description() -> str | None:
    """Return `git describe` output for a source checkout.

    Returns:
        Git description like `v0.10.0-2-g0dbc628`, or None when not
        running from a git checkout or when git is unavailable.
    """
    try:
        repo_root = Path(__file__).resolve().parents[2]
        if not (repo_root / ".git").exists():
            return None
        result = subprocess.run(
            ["git", "describe", "--tags", "--always", "--dirty"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode != 0:
            return None
        description = result.stdout.strip()
        return description if description else None
    except (OSError, subprocess.SubprocessError):
        return None


def get_full_version() -> str:
    """Return version with git suffix when running from a source checkout.

    Returns:
        Bare `__version__` for installed artifacts without git metadata,
        otherwise `"{__version__} (git {description})"`.
    """
    git_description = _get_git_description()
    if git_description and git_description not in __version__:
        return f"{__version__} (git {git_description})"
    return __version__
