# SPDX-License-Identifier: MIT
"""Tests for version reporting with git suffix (issue 1108)."""

from pathlib import Path
from unittest.mock import patch

import aletheia_probe


class TestGetFullVersion:
    """Test suite for public get_full_version behavior."""

    def test_returns_bare_version_when_no_git_checkout(self) -> None:
        """Test bare version is returned when .git is absent."""
        with patch.object(Path, "exists", return_value=False):
            assert aletheia_probe.get_full_version() == aletheia_probe.__version__

    def test_returns_bare_version_when_git_missing(self) -> None:
        """Test bare version is returned when git binary is unavailable."""
        with patch(
            "aletheia_probe.subprocess.run",
            side_effect=FileNotFoundError("git not found"),
        ):
            assert aletheia_probe.get_full_version() == aletheia_probe.__version__

    def test_appends_git_description_when_available(self) -> None:
        """Test git description is appended for source checkouts."""
        fake_result = type(
            "FakeResult", (), {"returncode": 0, "stdout": "v0.10.0-2-g0dbc628\n"}
        )()
        with (
            patch.object(Path, "exists", return_value=True),
            patch("aletheia_probe.subprocess.run", return_value=fake_result),
        ):
            full_version = aletheia_probe.get_full_version()
            assert full_version == (
                f"{aletheia_probe.__version__} (git v0.10.0-2-g0dbc628)"
            )
