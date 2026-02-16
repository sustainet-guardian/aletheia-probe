# SPDX-License-Identifier: MIT
"""Lookup command group registrations."""

import click

from ..models import VenueType
from .context import CoreCommandContext


def register_lookup_commands(main: click.Group, context: CoreCommandContext) -> None:
    """Register lookup group commands."""

    @main.group(name="lookup")
    def lookup() -> None:
        """Look up normalized venue candidates and known identifiers."""
        pass

    @lookup.command(name="journal")
    @click.argument("journal_name")
    @click.option(
        "--confidence-min",
        default=context.default_acronym_confidence_min,
        show_default=True,
        type=click.FloatRange(min=0.0, max=1.0),
        help="Minimum acronym dataset confidence for variant candidates",
    )
    @click.option(
        "--format",
        "output_format",
        default="text",
        type=click.Choice(["text", "json"]),
        help="Output format",
    )
    @click.option(
        "--online/--no-online",
        default=True,
        show_default=True,
        help="Run OpenAlex/Crossref enrichment + validation (non-blocking)",
    )
    @context.handle_cli_errors
    def lookup_journal(
        journal_name: str,
        confidence_min: float,
        output_format: str,
        online: bool,
    ) -> None:
        """Look up normalized forms and identifiers for a journal input."""
        context.run_lookup_cli(
            journal_name,
            VenueType.JOURNAL,
            output_format,
            confidence_min,
            online=online,
        )

    @lookup.command(name="conference")
    @click.argument("conference_name")
    @click.option(
        "--confidence-min",
        default=context.default_acronym_confidence_min,
        show_default=True,
        type=click.FloatRange(min=0.0, max=1.0),
        help="Minimum acronym dataset confidence for variant candidates",
    )
    @click.option(
        "--format",
        "output_format",
        default="text",
        type=click.Choice(["text", "json"]),
        help="Output format",
    )
    @click.option(
        "--online/--no-online",
        default=True,
        show_default=True,
        help="Run OpenAlex/Crossref enrichment + validation (non-blocking)",
    )
    @context.handle_cli_errors
    def lookup_conference(
        conference_name: str,
        confidence_min: float,
        output_format: str,
        online: bool,
    ) -> None:
        """Look up normalized forms and identifiers for a conference input."""
        context.run_lookup_cli(
            conference_name,
            VenueType.CONFERENCE,
            output_format,
            confidence_min,
            online=online,
        )


__all__ = ["register_lookup_commands"]
