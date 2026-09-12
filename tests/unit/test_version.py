# SPDX-License-Identifier: MIT
"""Tests for version reporting with git suffix (issue 1108)."""

import importlib
from importlib.metadata import PackageNotFoundError
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

    def test_returns_bare_version_when_git_command_fails(self) -> None:
        """Test bare version is returned when git exits non-zero."""
        fake_result = type("FakeResult", (), {"returncode": 128, "stdout": ""})()
        with (
            patch.object(Path, "exists", return_value=True),
            patch("aletheia_probe.subprocess.run", return_value=fake_result),
        ):
            assert aletheia_probe.get_full_version() == aletheia_probe.__version__

    def test_falls_back_to_development_when_not_installed(self) -> None:
        """Test version is development when package metadata is absent."""
        with patch("importlib.metadata.version", side_effect=PackageNotFoundError()):
            reloaded = importlib.reload(aletheia_probe)
            try:
                assert reloaded.__version__ == "development"
                assert reloaded.get_full_version() != ""
            finally:
                importlib.reload(aletheia_probe)
