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

    @main.command("mass-eval")
    @click.argument("input_path", type=click.Path(exists=True))
    @click.option(
        "--mode",
        type=click.Choice(["collect", "assess"]),
        default="assess",
        show_default=True,
        help="Execution phase: collect (cache warm-up) or assess (write output)",
    )
    @click.option(
        "--output-dir",
        type=click.Path(file_okay=False, dir_okay=True),
        default=None,
        help="Directory for per-file JSONL output (required in assess mode)",
    )
    @click.option(
        "--state-file",
        type=click.Path(dir_okay=False),
        default=".aletheia-probe/mass-eval-state.json",
        show_default=True,
        help="Checkpoint state file for resume support",
    )
    @click.option(
        "--resume/--no-resume",
        default=True,
        show_default=True,
        help="Resume from checkpoint state if available",
    )
    @click.option(
        "--relax-bibtex",
        is_flag=True,
        help="Enable relaxed BibTeX parsing for malformed files",
    )
    @click.option(
        "--retry-forever",
        is_flag=True,
        help="Retry indefinitely on transient backend failures (rate limits/timeouts)",
    )
    def mass_eval(
        input_path: str,
        mode: str,
        output_dir: str | None,
        state_file: str,
        resume: bool,
        relax_bibtex: bool,
        retry_forever: bool,
    ) -> None:
        """Run massive multi-file BibTeX evaluation with checkpoint/resume."""
        context.run_async(
            context.async_mass_eval_main(
                input_path=input_path,
                mode=mode,
                output_dir=output_dir,
                state_file=state_file,
                resume=resume,
                relax_bibtex=relax_bibtex,
                retry_forever=retry_forever,
            )
        )


__all__ = ["register_assessment_commands", "VenueType"]
