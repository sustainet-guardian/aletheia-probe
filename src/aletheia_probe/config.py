"""Configuration management for the journal assessment tool."""

import copy
import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from .backends.base import get_backend_registry
from .constants import (
    DEFAULT_BACKEND_AGREEMENT_BONUS,
    DEFAULT_BACKEND_TIMEOUT,
    DEFAULT_BACKEND_WEIGHT,
    DEFAULT_CACHE_UPDATE_THRESHOLD_DAYS,
    DEFAULT_CONFIDENCE_THRESHOLD,
    DEFAULT_OUTPUT_FORMAT,
    DEFAULT_UNKNOWN_THRESHOLD,
)
from .models import ConfigBackend


class HeuristicConfig(BaseModel):
    """Configuration for heuristic assessment rules."""

    confidence_threshold: float = Field(
        0.6, ge=0.0, le=1.0, description="Minimum confidence for assessment"
    )
    unknown_threshold: float = Field(
        0.3, ge=0.0, le=1.0, description="Threshold for unknown classification"
    )
    backend_agreement_bonus: float = Field(
        0.2, ge=0.0, description="Bonus for multiple backend agreement"
    )


class OutputConfig(BaseModel):
    """Configuration for output formatting."""

    format: str = Field("json", description="Output format: json, yaml, text")
    verbose: bool = Field(False, description="Include verbose output")
    include_raw_data: bool = Field(
        False, description="Include raw backend data in output"
    )


class CacheConfig(BaseModel):
    """Configuration for cache synchronization."""

    auto_sync: bool = Field(
        True, description="Enable automatic cache synchronization with backend config"
    )
    cleanup_disabled: bool = Field(
        True, description="Remove cache data for disabled backends"
    )
    update_threshold_days: int = Field(
        7, ge=1, description="Update cache if data is older than N days"
    )


class DataSourceUrlConfig(BaseModel):
    """Configuration for external data source URLs."""

    algerian_ministry_base_url: str = Field(
        "https://dgrsdt.dz/storage/revus/",
        description="Base URL for Algerian Ministry data",
    )
    algerian_ministry_rar_filename: str = Field(
        "revues.rar", description="RAR filename for Algerian Ministry data"
    )
    retraction_watch_repo_url: str = Field(
        "https://gitlab.com/crossref/retraction-watch-data.git",
        description="Git repository URL for Retraction Watch data",
    )
    retraction_watch_csv_filename: str = Field(
        "retraction_watch.csv", description="CSV filename in Retraction Watch repo"
    )


class AppConfig(BaseModel):
    """Main application configuration."""

    backends: dict[str, ConfigBackend] = Field(
        default_factory=dict, description="Backend configurations"
    )
    heuristics: HeuristicConfig = HeuristicConfig()
    output: OutputConfig = OutputConfig()
    cache: CacheConfig = CacheConfig()
    data_source_urls: DataSourceUrlConfig = DataSourceUrlConfig()


class ConfigManager:
    """Manages application configuration from files and environment."""

    def __init__(self, config_path: Path | None = None):
        self.config_path = config_path or self._find_config_file()
        self._config: AppConfig | None = None

    def _find_config_file(self) -> Path | None:
        """Find configuration file in standard locations."""
        search_paths = [
            Path.cwd()
            / ".aletheia-probe"
            / "config.yaml",  # Local project config (highest priority)
            Path.cwd() / "config" / "config.yaml",
            Path.cwd() / "config.yaml",
            Path.home() / ".config" / "aletheia-probe" / "config.yaml",
            Path("/etc/aletheia-probe/config.yaml"),
        ]

        for path in search_paths:
            if path.exists():
                return path

        return None

    def load_config(self) -> AppConfig:
        """Load configuration from file or create default."""
        if self._config is not None:
            return self._config

        # Start with default configuration
        default_config = self.get_default_config_with_all_backends()

        if self.config_path and self.config_path.exists():
            with open(self.config_path, encoding="utf-8") as f:
                file_config = yaml.safe_load(f) or {}

            # Deep merge file config with defaults
            config_data = self._deep_merge_configs(default_config, file_config)
        else:
            config_data = default_config

        # Override with environment variables
        config_data = self._apply_env_overrides(config_data)

        self._config = AppConfig(**config_data)
        return self._config

    def _deep_merge_configs(
        self, default_config: dict[str, Any], override_config: dict[str, Any]
    ) -> dict[str, Any]:
        """Deep merge override config into default config.

        This method performs a recursive merge of configuration dictionaries,
        with special handling for the 'backends' configuration section.

        Args:
            default_config: Base configuration with all defaults
            override_config: User-provided overrides

        Returns:
            Merged configuration

        Backend Special Handling:
            The 'backends' section requires special treatment due to its nested
            structure and merging requirements:

            1. Nested Structure: Backends are stored as a two-level dictionary:
               backends: {
                 "backend_name": {"enabled": True, "weight": 0.8, ...}
               }

            2. Per-Backend Merging: Instead of replacing entire backend configs,
               this method merges individual backend settings. This allows users
               to override specific settings (e.g., "enabled": false) while
               preserving other default settings (e.g., timeout, weight).

            3. Dynamic Addition: New backends not in the default config can be
               added. The method automatically ensures each backend has a 'name'
               field matching its dictionary key.

            4. Partial Overrides: Users can provide minimal overrides like:
               backends:
                 doaj:
                   enabled: false
               And the method preserves all other default settings for that backend.

            Without this special handling, users would need to specify complete
            backend configurations even for single setting changes.

        Example:
            Default: {"backends": {"doaj": {"name": "doaj", "enabled": True, "weight": 0.8}}}
            Override: {"backends": {"doaj": {"enabled": False}}}
            Result: {"backends": {"doaj": {"name": "doaj", "enabled": False, "weight": 0.8}}}
        """
        result = copy.deepcopy(default_config)

        for key, value in override_config.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                # For nested dicts, merge recursively
                if key == "backends":
                    # Special handling for backends - merge each backend config
                    for backend_name, backend_config in value.items():
                        if backend_name in result[key]:
                            # Merge backend-specific config
                            result[key][backend_name].update(backend_config)
                        else:
                            # New backend config - ensure 'name' field is present
                            if "name" not in backend_config:
                                backend_config = {
                                    "name": backend_name,
                                    **backend_config,
                                }
                            result[key][backend_name] = backend_config
                else:
                    # Regular dict merge
                    result[key].update(value)
            else:
                # Direct override for non-dict values
                result[key] = value

        return result

    def _apply_env_overrides(self, config_data: dict[str, Any]) -> dict[str, Any]:
        """Apply environment variable overrides to config."""
        # Example: JOURNAL_ASSESSMENT_OUTPUT_VERBOSE=true
        for key, value in os.environ.items():
            if key.startswith("JOURNAL_ASSESSMENT_"):
                config_key = key.replace("JOURNAL_ASSESSMENT_", "").lower()
                parts = config_key.split("_")

                if len(parts) >= 2:
                    if parts[0] == "output":
                        if "output" not in config_data:
                            config_data["output"] = {}
                        if parts[1] == "verbose":
                            config_data["output"]["verbose"] = value.lower() == "true"
                        elif parts[1] == "format":
                            config_data["output"]["format"] = value

        return config_data

    def get_enabled_backends(self) -> list[str]:
        """Get list of enabled backend names."""
        config = self.load_config()
        return [
            name
            for name, backend_config in config.backends.items()
            if backend_config.enabled
        ]

    def get_backend_config(self, backend_name: str) -> ConfigBackend | None:
        """Get configuration for a specific backend."""
        config = self.load_config()
        return config.backends.get(backend_name)

    def get_complete_config_dict(self) -> dict[str, Any]:
        """Get the complete configuration as a dictionary for display."""
        config = self.load_config()
        return config.model_dump()

    def show_config(self) -> str:
        """Show the complete configuration in YAML format.

        Returns:
            YAML formatted configuration string
        """
        config_dict = self.get_complete_config_dict()
        return yaml.dump(config_dict, default_flow_style=False, sort_keys=False)

    def get_default_config_with_all_backends(self) -> dict[str, Any]:
        """Get default configuration with all available backends enabled."""
        # Get all available backend names
        backend_registry = get_backend_registry()
        backend_names = backend_registry.get_backend_names()

        backends_config = {}
        for backend_name in backend_names:
            backends_config[backend_name] = {
                "name": backend_name,
                "enabled": True,
                "weight": DEFAULT_BACKEND_WEIGHT,
                "timeout": DEFAULT_BACKEND_TIMEOUT,
                "config": {},
            }

        return {
            "backends": backends_config,
            "heuristics": {
                "confidence_threshold": DEFAULT_CONFIDENCE_THRESHOLD,
                "unknown_threshold": DEFAULT_UNKNOWN_THRESHOLD,
                "backend_agreement_bonus": DEFAULT_BACKEND_AGREEMENT_BONUS,
            },
            "output": {
                "format": DEFAULT_OUTPUT_FORMAT,
                "verbose": False,
                "include_raw_data": False,
            },
            "cache": {
                "auto_sync": True,
                "cleanup_disabled": True,
                "update_threshold_days": DEFAULT_CACHE_UPDATE_THRESHOLD_DAYS,
            },
        }

    def create_default_config(self, output_path: Path) -> None:
        """Create a default configuration file with all backends enabled."""
        default_config = self.get_default_config_with_all_backends()

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            yaml.dump(default_config, f, default_flow_style=False, sort_keys=False)


# Global config manager instance with factory pattern
_config_manager_instance: ConfigManager | None = None


def get_config_manager(config_path: Path | None = None) -> ConfigManager:
    """Get or create the global config manager instance.

    Args:
        config_path: Optional path to config file (only used on first call)

    Returns:
        The global ConfigManager instance
    """
    global _config_manager_instance
    if _config_manager_instance is None:
        _config_manager_instance = ConfigManager(config_path)
    return _config_manager_instance


def set_config_manager(manager: ConfigManager) -> None:
    """Set the config manager instance (primarily for testing).

    Args:
        manager: ConfigManager instance to use globally
    """
    global _config_manager_instance
    _config_manager_instance = manager


def reset_config_manager() -> None:
    """Reset the config manager instance (primarily for testing)."""
    global _config_manager_instance
    _config_manager_instance = None
