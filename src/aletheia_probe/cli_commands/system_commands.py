# SPDX-License-Identifier: MIT
"""System and cache lifecycle CLI commands."""

import sys

import click

from ..logging_config import get_status_logger
from .context import CoreCommandContext


def register_system_commands(main: click.Group, context: CoreCommandContext) -> None:
    """Register config/sync/status/cache maintenance commands."""

    @main.command()
    @context.handle_cli_errors
    def config() -> None:
        """Show the complete current configuration."""
        config_output = context.get_config_manager_fn().show_config()
        print(config_output)

    @main.command()
    @click.option("--force", is_flag=True, help="Force sync even if data appears fresh")
    @click.option(
        "--include-large-datasets",
        is_flag=True,
        help=(
            "Include large datasets in default sync. "
            f"Currently: {', '.join(sorted(context.large_sync_backends))}"
        ),
    )
    @click.argument("backend_names", nargs=-1, required=False)
    def sync(
        force: bool, include_large_datasets: bool, backend_names: tuple[str, ...]
    ) -> None:
        """Manually sync cache with backend configuration."""
        context.auto_register_custom_lists_fn()
        backend_filter: list[str] | None = None
        if backend_names:
            backend_filter = list(backend_names)
        elif not include_large_datasets:
            backend_filter = [
                backend_name
                for backend_name in context.get_backend_registry_fn().get_backend_names()
                if backend_name not in context.large_sync_backends
            ]

        try:
            cache_sync_manager = context.get_cache_sync_manager_fn()
            result = context.run_async(
                cache_sync_manager.sync_cache_with_config(
                    force=force,
                    backend_filter=backend_filter,
                    show_progress=True,
                )
            )

            if result.get("status") == "error":
                sys.exit(1)

            for backend_result in result.values():
                if isinstance(backend_result, dict):
                    if backend_result.get("status") in ["error", "failed"]:
                        sys.exit(1)

        except (ValueError, OSError, KeyError, RuntimeError) as e:
            status_logger = get_status_logger()
            status_logger.error(f"Error during sync: {e}")
            sys.exit(1)

    @main.command(name="clear-cache")
    @click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
    @context.handle_cli_errors
    def clear_cache(confirm: bool) -> None:
        """Clear volatile assessment-related caches."""
        status_logger = get_status_logger()

        if not confirm:
            click.confirm(
                "This will clear assessment and OpenAlex caches. Continue?", abort=True
            )

        assessment_cache = context.create_assessment_cache()
        openalex_cache = context.create_openalex_cache()

        assessment_count = assessment_cache.get_assessment_cache_count()
        openalex_count = openalex_cache.get_openalex_cache_count()

        if assessment_count == 0 and openalex_count == 0:
            status_logger.info("Caches are already empty.")
            return

        cleared_assessment = assessment_cache.clear_assessment_cache()
        cleared_openalex = openalex_cache.clear_openalex_cache()

        status_logger.info(
            f"Cleared {cleared_assessment} assessment cache entries and "
            f"{cleared_openalex} OpenAlex cache entries."
        )

    @main.command()
    @context.handle_cli_errors
    def status() -> None:
        """Show cache synchronization status for all backends."""
        context.auto_register_custom_lists_fn()

        status_logger = get_status_logger()
        status_data = context.get_cache_sync_manager_fn().get_sync_status()

        status_logger.info("Cache Synchronization Status")
        status_logger.info("=" * 40)

        if status_data["sync_in_progress"]:
            status_logger.info("⚠️  Sync in progress...")
        else:
            status_logger.info("✅ No sync in progress")

        status_logger.info("\nBackend Status:")
        for backend_name, backend_info in status_data["backends"].items():
            if "error" in backend_info:
                status_logger.info(
                    f"  ❌ {backend_name}: Error - {backend_info['error']}"
                )
                continue

            enabled = backend_info.get("enabled", False)
            has_data = backend_info.get("has_data", False)
            backend_type = backend_info.get("type", "unknown")
            last_updated = backend_info.get("last_updated")
            entry_count = backend_info.get("entry_count")

            status_icon = "✅" if enabled else "❌"
            data_icon = "📊" if has_data else "📭"

            status_text = (
                f"{status_icon} {backend_name} "
                f"({'enabled' if enabled else 'disabled'}, {backend_type})"
            )

            if backend_type in ("cached", "api_cached") and (has_data or entry_count):
                status_text += f" {data_icon} {'has data' if has_data else 'no data'}"
                if entry_count is not None and entry_count > 0:
                    status_text += f" ({entry_count:,} entries)"
                if last_updated:
                    status_text += f" (updated: {last_updated})"

            status_logger.info(f"  {status_text}")


__all__ = ["register_system_commands"]
