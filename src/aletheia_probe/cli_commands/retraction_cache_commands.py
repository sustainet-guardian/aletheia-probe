# SPDX-License-Identifier: MIT
"""Retraction cache command group registrations."""

import click

from ..logging_config import get_status_logger
from .context import CoreCommandContext


def register_retraction_cache_commands(
    main: click.Group, context: CoreCommandContext
) -> None:
    """Register retraction cache maintenance commands."""

    @main.group(name="retraction-cache")
    def retraction_cache() -> None:
        """Manage the article retraction cache."""
        pass

    @retraction_cache.command(name="clear")
    @click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
    @context.handle_cli_errors
    def clear_retraction_cache(confirm: bool) -> None:
        """Clear all article retraction cache entries."""
        status_logger = get_status_logger()

        if not confirm:
            click.confirm(
                "This will clear all cached article retraction data. Continue?",
                abort=True,
            )

        retraction_cache_obj = context.create_retraction_cache()
        count = retraction_cache_obj.clear_article_retractions()

        if count == 0:
            status_logger.info("No retraction cache entries to clear.")
        else:
            status_logger.info(f"Cleared {count:,} retraction cache entry/entries.")


__all__ = ["register_retraction_cache_commands"]
