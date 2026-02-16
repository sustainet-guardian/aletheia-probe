# SPDX-License-Identifier: MIT
"""Assessment-oriented CLI commands."""

import click

from ..models import VenueType
from .context import CoreCommandContext


def register_assessment_commands(
    main: click.Group, context: CoreCommandContext
) -> None:
    """Register assessment and BibTeX commands."""

    @main.command()
    @click.argument("journal_name")
    @click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
    @click.option(
        "--no-acronyms",
        is_flag=True,
        help="Disable acronym/abbreviation/ISSN expansion candidates",
    )
    @click.option(
        "--confidence-min",
        default=context.default_acronym_confidence_min,
        show_default=True,
        type=click.FloatRange(min=0.0, max=1.0),
        help="Minimum acronym dataset confidence for expansion candidates",
    )
    @click.option(
        "--format",
        "output_format",
        default="text",
        type=click.Choice(["text", "json"]),
        help="Output format",
    )
    def journal(
        journal_name: str,
        verbose: bool,
        no_acronyms: bool,
        confidence_min: float,
        output_format: str,
    ) -> None:
        """Assess whether a journal is predatory or legitimate."""
        context.run_async(
            context.async_assess_publication(
                journal_name,
                "journal",
                verbose,
                output_format,
                use_acronyms=not no_acronyms,
                confidence_min=confidence_min,
            )
        )

    @main.command()
    @click.argument("conference_name")
    @click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
    @click.option(
        "--no-acronyms",
        is_flag=True,
        help="Disable acronym/abbreviation/ISSN expansion candidates",
    )
    @click.option(
        "--confidence-min",
        default=context.default_acronym_confidence_min,
        show_default=True,
        type=click.FloatRange(min=0.0, max=1.0),
        help="Minimum acronym dataset confidence for expansion candidates",
    )
    @click.option(
        "--format",
        "output_format",
        default="text",
        type=click.Choice(["text", "json"]),
        help="Output format",
    )
    def conference(
        conference_name: str,
        verbose: bool,
        no_acronyms: bool,
        confidence_min: float,
        output_format: str,
    ) -> None:
        """Assess whether a conference is predatory or legitimate."""
        context.run_async(
            context.async_assess_publication(
                conference_name,
                "conference",
                verbose,
                output_format,
                use_acronyms=not no_acronyms,
                confidence_min=confidence_min,
            )
        )

    @main.command()
    @click.argument("bibtex_file", type=click.Path(exists=True))
    @click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
    @click.option(
        "--format",
        "output_format",
        default="text",
        type=click.Choice(["text", "json"]),
        help="Output format",
    )
    @click.option(
        "--relax-bibtex",
        is_flag=True,
        help="Enable relaxed BibTeX parsing to handle malformed files",
    )
    def bibtex(
        bibtex_file: str, verbose: bool, output_format: str, relax_bibtex: bool
    ) -> None:
        """Assess all journals in a BibTeX file for predatory status."""
        context.run_async(
            context.async_bibtex_main(
                bibtex_file,
                verbose,
                output_format,
                relax_bibtex,
            )
        )


__all__ = ["register_assessment_commands", "VenueType"]
