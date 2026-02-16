# SPDX-License-Identifier: MIT
"""Acronym dataset management commands."""

import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import aiohttp
import click

from ..logging_config import get_status_logger
from .context import CoreCommandContext


def register_acronym_commands(main: click.Group, context: CoreCommandContext) -> None:
    """Register acronym command group."""

    @main.group(name="acronym")
    def acronym() -> None:
        """Manage the venue acronym database (journals, conferences, etc.)."""
        pass

    @acronym.command(name="status")
    @context.handle_cli_errors
    def acronym_status() -> None:
        """Show venue acronym database status (counts by entity type)."""
        status_logger = get_status_logger()

        acronym_cache = context.create_acronym_cache()
        stats = acronym_cache.get_full_stats()

        status_logger.info("Venue Acronym Database Status")
        status_logger.info("=" * 44)

        if stats["total_acronyms"] == 0:
            status_logger.info(
                "Database is empty — run 'acronym import' or 'acronym sync' to load data"
            )
            return

        status_logger.info(f"Acronyms : {stats['total_acronyms']:>8,}")
        status_logger.info(f"Variants : {stats['total_variants']:>8,}")
        status_logger.info(f"ISSNs    : {stats['total_issns']:>8,}")

        if stats["by_entity_type"]:
            status_logger.info("")
            status_logger.info(
                f"{'Entity type':<16}  {'Acronyms':>9}  {'Variants':>9}  {'ISSNs':>7}"
            )
            status_logger.info("-" * 44)
            for row in stats["by_entity_type"]:
                status_logger.info(
                    f"{row['entity_type']:<16}  {row['acronyms']:>9,}"
                    f"  {row['variants']:>9,}  {row['issns']:>7,}"
                )

    @acronym.command(name="import")
    @click.argument("input_file", type=click.Path(exists=True))
    @click.option(
        "--merge/--no-merge",
        default=True,
        help="Merge with existing data (default) or replace",
    )
    @click.option(
        "--source",
        default=None,
        help="Override source label stored with each imported entry (default: 'import')",
    )
    @context.handle_cli_errors
    def import_acronyms(input_file: str, merge: bool, source: str | None) -> None:
        """Import acronyms from a venue-acronyms-2025 pipeline JSON file."""
        status_logger = get_status_logger()
        acronym_cache = context.create_acronym_cache()

        try:
            with open(input_file, encoding="utf-8") as f:
                data = json.load(f)

            if isinstance(data, list):
                entries = data
            elif isinstance(data, dict):
                entries = data.get("acronyms", [])
            else:
                raise ValueError("Input file must contain a JSON list or object")

            status_logger.info(f"Loaded {len(entries)} entries from {input_file}")

            if not merge:
                if click.confirm(
                    "This will clear existing data before importing. Continue?",
                    abort=True,
                ):
                    acronym_cache.clear_acronym_database()

            source_file = source or Path(input_file).name
            count = acronym_cache.import_acronyms(entries, source_file=source_file)

            status_logger.info(f"Successfully imported {count} acronym entries")

        except Exception as e:
            status_logger.error(f"Failed to import dataset: {e}")
            raise click.ClickException(str(e)) from e

    @acronym.command(name="sync")
    @click.option(
        "--repo",
        default="sustainet-guardian/venue-acronyms-2025",
        show_default=True,
        help="GitHub repository in owner/name format",
    )
    @click.option(
        "--merge/--no-merge",
        default=True,
        help="Merge with existing data (default) or replace",
    )
    @click.option(
        "--source",
        default=None,
        help="Override source label stored with each imported entry",
    )
    @context.handle_cli_errors
    def sync_acronyms(repo: str, merge: bool, source: str | None) -> None:
        """Download latest venue-acronyms dataset from GitHub and import it."""
        status_logger = get_status_logger()
        acronym_cache = context.create_acronym_cache()

        try:
            dataset_url, asset_name = context.get_latest_acronym_dataset_url(repo)
            status_logger.info(f"Downloading dataset from {dataset_url}")

            payload_data: dict[str, Any] | list[Any] = context.run_async(
                context.fetch_https_json(
                    dataset_url,
                    context.github_http_timeout_seconds,
                    context.github_allowed_hosts,
                )
            )

            with NamedTemporaryFile("w", suffix=".json", encoding="utf-8") as tmp_file:
                tmp_file.write(json.dumps(payload_data))
                tmp_file.flush()

                with open(tmp_file.name, encoding="utf-8") as f:
                    data = json.load(f)

            entries = data.get("acronyms", []) if isinstance(data, dict) else data
            if not isinstance(entries, list):
                raise ValueError("Downloaded dataset has invalid format")

            status_logger.info(f"Loaded {len(entries)} entries from latest release")

            if not merge:
                if click.confirm(
                    "This will clear existing data before importing. Continue?",
                    abort=True,
                ):
                    acronym_cache.clear_acronym_database()

            source_file = source or asset_name
            count = acronym_cache.import_acronyms(entries, source_file=source_file)
            status_logger.info(f"Successfully imported {count} acronym entries")

        except aiohttp.ClientError as e:
            status_logger.error(f"Failed to download dataset: {e}")
            raise click.ClickException(str(e)) from e
        except Exception as e:
            status_logger.error(f"Failed to sync acronym dataset: {e}")
            raise click.ClickException(str(e)) from e

    @acronym.command()
    @click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
    @context.handle_cli_errors
    def clear(confirm: bool) -> None:
        """Clear all entries from the acronym database."""
        status_logger = get_status_logger()

        if not confirm:
            click.confirm(
                "This will delete all acronym mappings. Continue?", abort=True
            )

        acronym_cache = context.create_acronym_cache()
        count = acronym_cache.clear_acronym_database()

        if count == 0:
            status_logger.info("Acronym database is already empty.")
        else:
            status_logger.info(f"Cleared {count:,} acronym mapping(s).")


__all__ = ["register_acronym_commands"]
