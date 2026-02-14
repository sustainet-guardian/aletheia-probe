# SPDX-License-Identifier: MIT
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
    DEFAULT_CACHE_AUTO_SYNC,
    DEFAULT_CACHE_DB_PATH,
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

    db_path: str = Field(
        DEFAULT_CACHE_DB_PATH, description="Path to the SQLite cache database file"
    )
    auto_sync: bool = Field(
        DEFAULT_CACHE_AUTO_SYNC,
        description="Enable automatic cache synchronization with backend config",
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
    retraction_watch_repo_url: str = Field(
        "https://gitlab.com/crossref/retraction-watch-data.git",
        description="Git repository URL for Retraction Watch data",
    )
    retraction_watch_csv_filename: str = Field(
        "retraction_watch.csv", description="CSV filename in Retraction Watch repo"
    )
    bealls_publishers_url: str = Field(
        "https://beallslist.net/",
        description="URL for Beall's List publishers page",
    )
    bealls_standalone_url: str = Field(
        "https://beallslist.net/standalone-journals/",
        description="URL for Beall's List standalone journals page",
    )
    predatory_journals_fallback_url: str = Field(
        "https://www.predatoryjournals.org/the-list/journals",
        description="Fallback URL for predatory journals list",
    )
    predatory_publishers_fallback_url: str = Field(
        "https://www.predatoryjournals.org/the-list/publishers",
        description="Fallback URL for predatory publishers list",
    )
    ugc_care_cloned_url: str = Field(
        "https://ugccare.unipune.ac.in/Apps1/User/Web/CloneJournalsNew",
        description="URL for UGC-CARE Group-I cloned journals page",
    )
    ugc_care_cloned_group2_url: str = Field(
        "https://ugccare.unipune.ac.in/Apps1/User/Web/CloneJournalsGroupIINew",
        description="URL for UGC-CARE Group-II cloned journals page",
    )
    ugc_care_delisted_group2_url: str = Field(
        "https://ugccare.unipune.ac.in/Apps1/User/Web/ScopusDelisted",
        description="URL for UGC-CARE Group-II delisted journals page",
    )
    dblp_xml_dump_url: str = Field(
        "https://dblp.org/xml/dblp.xml.gz",
        description="URL for DBLP full XML dump",
    )
    core_conference_rankings_url: str = Field(
        "https://portal.core.edu.au/conf-ranks/",
        description="URL for CORE/ICORE conference rankings portal",
    )
    core_journal_rankings_url: str = Field(
        "https://portal.core.edu.au/jnl-ranks/",
        description="URL for CORE journal rankings portal",
    )
    core_conference_default_source: str = Field(
        "ICORE2026",
        description="Default source filter for CORE conference rankings",
    )
    core_journal_default_source: str = Field(
        "CORE2020",
        description="Default source filter for CORE journal rankings",
    )


class DataSourceProcessingConfig(BaseModel):
    """Configuration for data source processing parameters."""

    download_chunk_size: int = Field(
        8192, ge=1024, description="Chunk size in bytes for file downloads"
    )
    url_extraction_pattern: str = Field(
        r"https?://[^\s]+",
        description="Regex pattern for extracting URLs from text",
    )
    scopus_column_mappings: dict[str, list[str]] = Field(
        default_factory=lambda: {
            "title": ["source title", "title"],
            "issn": ["issn"],
            "eissn": ["eissn", "e-issn"],
            "publisher": ["publisher"],
            "status": ["active or inactive"],
            "quality_flag": ["discontinued", "quality"],
            "source_type": ["source type"],
            "coverage": ["coverage"],
            "open_access": ["open access"],
        },
        description="Column header mappings for Scopus Excel files",
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
    data_source_processing: DataSourceProcessingConfig = DataSourceProcessingConfig()


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

        # Ensure backend configs have required 'name' field
        # (handles new backends added via config that weren't in defaults)
        if "backends" in config_data and isinstance(config_data["backends"], dict):
            for backend_name, backend_config in config_data["backends"].items():
                if isinstance(backend_config, dict) and "name" not in backend_config:
                    backend_config["name"] = backend_name

        # Override with environment variables
        config_data = self._apply_env_overrides(config_data)

        self._config = AppConfig(**config_data)
        return self._config

    def _deep_merge_configs(
        self, default_config: dict[str, Any], override_config: dict[str, Any]
    ) -> dict[str, Any]:
        """Deep merge override config into default config recursively.

        Nested dictionaries are merged recursively rather than replaced,
        allowing partial overrides at any nesting level.

        Args:
            default_config: Base configuration with all defaults
            override_config: User-provided overrides

        Returns:
            Merged configuration
        """
        result = copy.deepcopy(default_config)

        for key, value in override_config.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                # Recursively merge ANY nested dict
                result[key] = self._deep_merge_configs(result[key], value)
            else:
                # Direct override for non-dict values or new keys
                result[key] = value

        return result

    def _apply_env_overrides(self, config_data: dict[str, Any]) -> dict[str, Any]:
        """Apply environment variable overrides to config.

        Supports any config section and handles nested paths with automatic
        type conversion. This is a general parser that works for all config
        sections without hardcoded special cases.

        Examples:
            ALETHEIA_PROBE_OUTPUT_VERBOSE=true
            ALETHEIA_PROBE_BACKENDS_DOAJ_ENABLED=false
            ALETHEIA_PROBE_HEURISTICS_CONFIDENCE_THRESHOLD=0.8
            ALETHEIA_PROBE_CACHE_UPDATE_THRESHOLD_DAYS=14

        Args:
            config_data: Configuration dictionary to apply overrides to

        Returns:
            Configuration dictionary with environment variable overrides applied
        """
        for key, value in os.environ.items():
            if key.startswith("ALETHEIA_PROBE_"):
                # Parse: ALETHEIA_PROBE_SECTION_SUBSECTION_FIELD
                config_path = key.replace("ALETHEIA_PROBE_", "").lower().split("_")

                if len(config_path) >= 2:
                    # Navigate/create nested structure
                    current = config_data
                    for part in config_path[:-1]:
                        if part not in current:
                            current[part] = {}
                        current = current[part]

                    # Set the value with type conversion
                    field = config_path[-1]
                    current[field] = self._parse_env_value(value)

        return config_data

    def _parse_env_value(self, value: str) -> str | bool | int | float:
        """Parse environment variable string to appropriate type.

        Automatically converts string values to the most appropriate type:
        - "true"/"false" (case-insensitive) → bool
        - Numeric strings with decimal point → float
        - Numeric strings without decimal → int
        - Everything else → str (unchanged)

        Args:
            value: Raw string value from environment variable

        Returns:
            Parsed value with appropriate type (bool, int, float, or str)

        Examples:
            >>> self._parse_env_value("true")
            True
            >>> self._parse_env_value("0.8")
            0.8
            >>> self._parse_env_value("14")
            14
            >>> self._parse_env_value("json")
            'json'
        """
        # Boolean
        if value.lower() in ("true", "false"):
            return value.lower() == "true"

        # Try numeric conversions
        try:
            if "." in value:
                return float(value)
            return int(value)
        except ValueError:
            pass

        # Keep as string
        return value

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
            # Start with common config fields
            backend_config = {
                "name": backend_name,
                "enabled": True,
                "weight": DEFAULT_BACKEND_WEIGHT,
                "timeout": DEFAULT_BACKEND_TIMEOUT,
                "config": {},
            }

            # Only add parameters that this backend supports
            supported_params = backend_registry.get_supported_params(backend_name)
            if "email" in supported_params:
                backend_config["email"] = None  # Use backend default unless configured

            backends_config[backend_name] = backend_config

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
                "auto_sync": DEFAULT_CACHE_AUTO_SYNC,
                "cleanup_disabled": True,
                "update_threshold_days": DEFAULT_CACHE_UPDATE_THRESHOLD_DAYS,
            },
        }


# Global config manager instance with factory pattern
_config_manager_instance: ConfigManager | None = None


def get_config_manager(
    config_path: Path | None = None, force_reload: bool = False
) -> ConfigManager:
    """Get or create the global config manager instance.

    Args:
        config_path: Optional path to config file (only used on first call or with force_reload)
        force_reload: Force recreation of config manager with new path

    Returns:
        The global ConfigManager instance
    """
    global _config_manager_instance
    if _config_manager_instance is None or force_reload:
        _config_manager_instance = ConfigManager(config_path)
    return _config_manager_instance
