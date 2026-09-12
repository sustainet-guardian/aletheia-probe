# SPDX-License-Identifier: MIT
"""Tests for the version bump script state machine (issue 1108)."""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


def load_bump_version_module() -> ModuleType:
    """Load scripts/bump_version.py as a module without touching sys.path."""
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "bump_version.py"
    spec = importlib.util.spec_from_file_location("bump_version", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bump_version_module = load_bump_version_module()


class TestBumpVersionTransitions:
    """Pin every bump path, especially to and from dev markers."""

    @pytest.mark.parametrize(
        ("current", "bump_type", "expected"),
        [
            ("0.10.0", "patch", "0.10.1"),
            ("0.10.0", "minor", "0.11.0"),
            ("0.10.0", "major", "1.0.0"),
            ("0.10.0", "dev", "0.10.1.dev0"),
            ("0.10.1.dev0", "patch", "0.10.1"),
            ("0.10.1.dev0", "minor", "0.11.0"),
            ("0.10.1.dev0", "major", "1.0.0"),
            ("0.10.1.dev0", "dev", "0.10.1.dev0"),
            ("0.10.0", "0.11.0", "0.11.0"),
            ("0.10.0", "0.10.1.dev0", "0.10.1.dev0"),
        ],
    )
    def test_bump_transition(self, current: str, bump_type: str, expected: str) -> None:
        """Test each bump type resolves to the expected version."""
        assert bump_version_module.bump_version(current, bump_type) == expected

    def test_invalid_specific_version_exits(self) -> None:
        """Test an unparsable explicit version aborts instead of writing."""
        with pytest.raises(SystemExit):
            bump_version_module.bump_version("0.10.0", "not-a-version")

    def test_invalid_current_version_exits(self) -> None:
        """Test an unparsable current version aborts instead of guessing."""
        with pytest.raises(SystemExit):
            bump_version_module.bump_version("bad", "patch")

    def test_non_numeric_version_exits(self) -> None:
        """Test non-numeric components abort instead of guessing."""
        with pytest.raises(SystemExit):
            bump_version_module.bump_version("a.b.c", "patch")


class TestVersionPredicates:
    """Test the version classifiers backing the bump logic."""

    @pytest.mark.parametrize(
        ("version", "expected"),
        [
            ("0.10.1.dev0", True),
            ("0.10.1.dev12", True),
            ("0.10.1", False),
            ("0.10.1rc1", False),
        ],
    )
    def test_is_dev_version(self, version: str, expected: bool) -> None:
        """Test dev markers are distinguished from releases."""
        assert bump_version_module.is_dev_version(version) is expected

    @pytest.mark.parametrize(
        ("version", "expected"),
        [
            ("0.10.1", True),
            ("0.10.1.dev0", True),
            ("0.10", False),
            ("abc", False),
        ],
    )
    def test_is_valid_version(self, version: str, expected: bool) -> None:
        """Test only release and dev shapes are accepted."""
        assert bump_version_module.is_valid_version(version) is expected


class TestPyprojectHelpers:
    """Test reading and writing versions including dev markers."""

    def test_get_current_version_reads_dev_marker(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test the dev suffix survives the read from pyproject.toml."""
        tmp_path.joinpath("pyproject.toml").write_text(
            '[project]\nname = "aletheia-probe"\nversion = "0.10.1.dev0"\n'
        )
        monkeypatch.chdir(tmp_path)
        assert bump_version_module.get_current_version() == "0.10.1.dev0"

    def test_get_current_version_missing_file_exits(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test a missing pyproject.toml aborts instead of guessing."""
        monkeypatch.chdir(tmp_path)
        with pytest.raises(SystemExit):
            bump_version_module.get_current_version()

    def test_get_current_version_invalid_content_exits(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test a pyproject.toml without a version aborts instead of guessing."""
        tmp_path.joinpath("pyproject.toml").write_text('[project]\nname = "x"\n')
        monkeypatch.chdir(tmp_path)
        with pytest.raises(SystemExit):
            bump_version_module.get_current_version()

    def test_update_pyproject_writes_dev_version(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test writing a dev version rewrites exactly the version line."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nname = "aletheia-probe"\nversion = "0.10.0"\n')
        monkeypatch.chdir(tmp_path)
        bump_version_module.update_pyproject("0.10.1.dev0")
        assert 'version = "0.10.1.dev0"' in pyproject.read_text()

    def test_update_pyproject_without_version_line_exits(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test a pyproject.toml without a version aborts instead of writing."""
        tmp_path.joinpath("pyproject.toml").write_text('[project]\nname = "x"\n')
        monkeypatch.chdir(tmp_path)
        with pytest.raises(SystemExit):
            bump_version_module.update_pyproject("0.10.1.dev0")
