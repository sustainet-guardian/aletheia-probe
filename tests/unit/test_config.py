# SPDX-License-Identifier: MIT
"""Tests for the configuration management module."""

import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import yaml
from pydantic import ValidationError

from aletheia_probe.config import AppConfig, ConfigManager
from aletheia_probe.models import ConfigBackend


@pytest.fixture
def temp_config_file():
    """Create a temporary config file for testing."""
    config_data = {
        "backends": {
            "test_backend": {
                "name": "test_backend",
                "enabled": True,
                "weight": 0.8,
                "timeout": 15,
                "config": {"api_key": "test_key"},
            }
        },
        "heuristics": {
            "confidence_threshold": 0.7,
            "unknown_threshold": 0.2,
            "backend_agreement_bonus": 0.15,
        },
        "output": {"format": "yaml", "verbose": True, "include_raw_data": True},
        "cache": {
            "auto_sync": False,
            "cleanup_disabled": False,
            "update_threshold_days": 14,
        },
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(config_data, f)
        yield Path(f.name)

    # Cleanup
    Path(f.name).unlink(missing_ok=True)


class TestConfigManager:
    """Test cases for ConfigManager."""

    def test_load_config_from_file(self, temp_config_file):
        """Test loading configuration from file."""
        manager = ConfigManager(temp_config_file)
        config = manager.load_config()

        assert isinstance(config, AppConfig)
        assert "test_backend" in config.backends
        assert config.backends["test_backend"].enabled
        assert config.backends["test_backend"].weight == 0.8
        assert config.heuristics.confidence_threshold == 0.7
        assert config.output.format == "yaml"
        assert config.cache.auto_sync is False

    def test_load_config_no_file(self, tmp_path):
        """Test loading default configuration when no file exists."""
        manager = ConfigManager(tmp_path / "nonexistent.yaml")
        config = manager.load_config()

        assert isinstance(config, AppConfig)
        # Should have default backends from registry
        assert len(config.backends) > 0
        assert config.heuristics.confidence_threshold == 0.6  # Default
        assert config.output.format == "json"  # Default
        assert config.cache.auto_sync is True  # Default

    def test_load_config_caching(self, temp_config_file):
        """Test that configuration is cached after first load."""
        manager = ConfigManager(temp_config_file)

        config1 = manager.load_config()
        config2 = manager.load_config()

        assert config1 is config2  # Same object reference

    def test_deep_merge_configs(self, temp_config_file):
        """Test deep merging of configuration dictionaries."""
        manager = ConfigManager(temp_config_file)

        default_config = {
            "backends": {
                "backend1": {"enabled": True, "weight": 1.0},
                "backend2": {"enabled": True, "weight": 1.0},
            },
            "heuristics": {"confidence_threshold": 0.6},
        }

        override_config = {
            "backends": {
                "backend1": {"enabled": False},  # Override enabled
                "backend3": {"enabled": True, "weight": 0.5},  # New backend
            },
            "heuristics": {"confidence_threshold": 0.8},  # Override threshold
        }

        result = manager._deep_merge_configs(default_config, override_config)

        assert result["backends"]["backend1"]["enabled"] is False
        assert result["backends"]["backend1"]["weight"] == 1.0  # Preserved
        assert result["backends"]["backend2"]["enabled"] is True  # Preserved
        assert result["backends"]["backend3"]["enabled"] is True  # Added
        assert result["heuristics"]["confidence_threshold"] == 0.8

    def test_apply_env_overrides(self, temp_config_file):
        """Test environment variable overrides."""
        manager = ConfigManager(temp_config_file)

        config_data = {"output": {"format": "json", "verbose": False}}

        env_vars = {
            "ALETHEIA_PROBE_OUTPUT_VERBOSE": "true",
            "ALETHEIA_PROBE_OUTPUT_FORMAT": "yaml",
        }

        with patch.dict(os.environ, env_vars, clear=False):
            result = manager._apply_env_overrides(config_data)

        assert result["output"]["verbose"] is True
        assert result["output"]["format"] == "yaml"

    def test_get_enabled_backends(self, temp_config_file):
        """Test getting list of enabled backend names."""
        manager = ConfigManager(temp_config_file)
        enabled = manager.get_enabled_backends()

        assert "test_backend" in enabled
        assert all(isinstance(name, str) for name in enabled)

    def test_get_backend_config(self, temp_config_file):
        """Test getting configuration for a specific backend."""
        manager = ConfigManager(temp_config_file)
        backend_config = manager.get_backend_config("test_backend")

        assert isinstance(backend_config, ConfigBackend)
        assert backend_config.name == "test_backend"
        assert backend_config.enabled is True
        assert backend_config.weight == 0.8
        assert backend_config.timeout == 15

    def test_get_backend_config_nonexistent(self, temp_config_file):
        """Test getting configuration for non-existent backend."""
        manager = ConfigManager(temp_config_file)
        backend_config = manager.get_backend_config("nonexistent_backend")

        assert backend_config is None

    def test_get_complete_config_dict(self, temp_config_file):
        """Test getting complete configuration as dictionary."""
        manager = ConfigManager(temp_config_file)
        config_dict = manager.get_complete_config_dict()

        assert isinstance(config_dict, dict)
        assert "backends" in config_dict
        assert "heuristics" in config_dict
        assert "output" in config_dict
        assert "cache" in config_dict

    def test_show_config(self, temp_config_file):
        """Test showing configuration in YAML format."""
        manager = ConfigManager(temp_config_file)
        config_yaml = manager.show_config()

        assert isinstance(config_yaml, str)
        # Should be valid YAML
        parsed = yaml.safe_load(config_yaml)
        assert isinstance(parsed, dict)
        assert "backends" in parsed

    def test_find_config_file_priority(self, tmp_path):
        """Test configuration file search priority."""
        # Create config files in different locations
        local_config = tmp_path / ".aletheia-probe" / "config.yaml"
        local_config.parent.mkdir()
        local_config.write_text("backends: {}")

        project_config = tmp_path / "config" / "config.yaml"
        project_config.parent.mkdir()
        project_config.write_text("backends: {}")

        root_config = tmp_path / "config.yaml"
        root_config.write_text("backends: {}")

        with patch("pathlib.Path.cwd", return_value=tmp_path):
            manager = ConfigManager()
            # Should find the highest priority file
            assert manager.config_path == local_config

    def test_get_default_config_with_all_backends(self, temp_config_file):
        """Test getting default configuration with all available backends."""
        with patch("aletheia_probe.config.get_backend_registry") as mock_get_registry:
            mock_registry = Mock()
            mock_registry.get_backend_names.return_value = [
                "backend1",
                "backend2",
                "backend3",
            ]
            # Mock get_supported_params to return empty set (no special params)
            mock_registry.get_supported_params.return_value = set()
            mock_get_registry.return_value = mock_registry

            manager = ConfigManager(temp_config_file)
            default_config = manager.get_default_config_with_all_backends()

            assert isinstance(default_config, dict)
            assert len(default_config["backends"]) == 3
            for backend_name in ["backend1", "backend2", "backend3"]:
                backend_config = default_config["backends"][backend_name]
                assert backend_config["enabled"] is True
                assert backend_config["weight"] == 0.8
                assert backend_config["timeout"] == 10

    def test_create_default_config(self, tmp_path):
        """Test creating a default configuration file."""
        with patch("aletheia_probe.config.get_backend_registry") as mock_get_registry:
            mock_registry = Mock()
            mock_registry.get_backend_names.return_value = ["test_backend"]
            # Mock get_supported_params to return empty set (no special params)
            mock_registry.get_supported_params.return_value = set()
            mock_get_registry.return_value = mock_registry

            manager = ConfigManager()
            output_path = tmp_path / "new_config.yaml"

            manager.create_default_config(output_path)

            assert output_path.exists()
            config_data = yaml.safe_load(output_path.read_text())
            assert "backends" in config_data
            assert "test_backend" in config_data["backends"]

    def test_config_validation_errors(self):
        """Test configuration validation with invalid data."""
        # Test invalid confidence threshold
        with pytest.raises(ValidationError):
            AppConfig(heuristics={"confidence_threshold": 1.5})  # > 1.0

        # Test invalid timeout
        with pytest.raises(ValidationError):
            AppConfig(
                backends={
                    "test": ConfigBackend(
                        name="test",
                        enabled=True,
                        weight=1.0,
                        timeout=0,  # <= 0
                    )
                }
            )

    def test_partial_config_file(self, tmp_path):
        """Test loading configuration with only partial data."""
        partial_config = {"backends": {"test": {"enabled": False}}}
        config_file = tmp_path / "partial.yaml"
        config_file.write_text(yaml.dump(partial_config))

        manager = ConfigManager(config_file)
        config = manager.load_config()

        # Should merge with defaults
        assert isinstance(config, AppConfig)
        assert "test" in config.backends
        # Should have default values for missing fields
        assert config.heuristics.confidence_threshold == 0.6
        assert config.output.format == "json"


class TestConfigModels:
    """Test configuration model validation."""

    def test_config_backend_validation(self):
        """Test ConfigBackend model validation."""
        # Valid configuration
        backend = ConfigBackend(
            name="test",
            enabled=True,
            weight=0.8,
            timeout=15,
            rate_limit=100,
            config={"key": "value"},
        )
        assert backend.name == "test"
        assert backend.weight == 0.8

        # Invalid weight (negative)
        with pytest.raises(ValidationError):
            ConfigBackend(name="test", enabled=True, weight=-0.1, timeout=10)

        # Invalid timeout (zero)
        with pytest.raises(ValidationError):
            ConfigBackend(name="test", enabled=True, weight=1.0, timeout=0)

    def test_app_config_defaults(self):
        """Test AppConfig model with default values."""
        config = AppConfig()

        assert config.backends == {}
        assert config.heuristics.confidence_threshold == 0.6
        assert config.output.format == "json"
        assert config.cache.auto_sync is True
