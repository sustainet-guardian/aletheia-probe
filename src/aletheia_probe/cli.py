# SPDX-License-Identifier: MIT
"""Command-line interface for the journal assessment tool."""

import asyncio
import json
import sqlite3
import sys
import traceback
from pathlib import Path

import click

from . import __version__
from .batch_assessor import BibtexBatchAssessor
from .cache import get_cache_manager
from .cache_sync import cache_sync_manager
from .config import get_config_manager
from .dispatcher import query_dispatcher
from .enums import AssessmentType
from .logging_config import get_status_logger, setup_logging
from .models import BackendStatus
from .normalizer import input_normalizer
from .updater import data_updater  # Global updater instance from updater package


def print_version(ctx: click.Context, param: click.Parameter, value: bool) -> None:
    """Print version and exit if requested."""
    if value:
        # Ensure logging is set up before using it (--version is eager)
        setup_logging()
        status_logger = get_status_logger()
        status_logger.info(f"Aletheia-Probe version {__version__}")
        ctx.exit(0)


@click.group()
@click.option(
    "--version",
    is_flag=True,
    callback=print_version,
    expose_value=False,
    is_eager=True,
    help="Show version information and exit",
)
def main() -> None:
    """Aletheia-Probe - Assess whether journals are predatory or legitimate."""
    # Initialize logging on first command invocation
    detail_logger, status_logger = setup_logging()
    detail_logger.debug("CLI initialized")


@main.command()
@click.argument("journal_name")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.option(
    "--format",
    "output_format",
    default="text",
    type=click.Choice(["text", "json"]),
    help="Output format",
)
def journal(journal_name: str, verbose: bool, output_format: str) -> None:
    """Assess whether a journal is predatory or legitimate.

    JOURNAL_NAME: The name of the journal to assess
    """
    asyncio.run(
        _async_assess_publication(journal_name, "journal", verbose, output_format)
    )


@main.command()
@click.argument("conference_name")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.option(
    "--format",
    "output_format",
    default="text",
    type=click.Choice(["text", "json"]),
    help="Output format",
)
def conference(conference_name: str, verbose: bool, output_format: str) -> None:
    """Assess whether a conference is predatory or legitimate.

    CONFERENCE_NAME: The name of the conference to assess
    """
    asyncio.run(
        _async_assess_publication(conference_name, "conference", verbose, output_format)
    )


@main.command()
def config() -> None:
    """Show the complete current configuration."""
    status_logger = get_status_logger()
    try:
        config_output = get_config_manager().show_config()
        print(config_output)
    except Exception as e:
        status_logger.error(f"Error displaying configuration: {e}")
        exit(1)


@main.command()
@click.option("--force", is_flag=True, help="Force sync even if data appears fresh")
@click.argument("backend_names", nargs=-1, required=False)
def sync(force: bool, backend_names: tuple[str, ...]) -> None:
    """Manually sync cache with backend configuration.

    Optionally specify one or more backend names to sync only those backends.
    Examples:
      aletheia-probe sync              # Sync all backends
      aletheia-probe sync scopus       # Sync only scopus
      aletheia-probe sync bealls doaj  # Sync only bealls and doaj
    """
    try:
        # The cache_sync_manager handles all output through the dual logger
        result = asyncio.run(
            cache_sync_manager.sync_cache_with_config(
                force=force,
                backend_filter=list(backend_names) if backend_names else None,
                show_progress=True,
            )
        )

        # Check for errors and exit accordingly
        if result.get("status") == "error":
            exit(1)

        # Check if any backend had an error
        for backend_result in result.values():
            if isinstance(backend_result, dict):
                if backend_result.get("status") in ["error", "failed"]:
                    exit(1)

    except Exception as e:
        status_logger = get_status_logger()
        status_logger.error(f"Error during sync: {e}")
        exit(1)


@main.command()
@click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
def clear_cache(confirm: bool) -> None:
    """Clear the assessment cache.

    This removes all cached assessment results, forcing fresh queries
    to all backends on next assessment.
    """
    status_logger = get_status_logger()

    if not confirm:
        click.confirm(
            "This will clear all cached assessment results. Continue?", abort=True
        )

    try:
        cache_manager = get_cache_manager()

        # Clear assessment cache
        with sqlite3.connect(cache_manager.db_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM assessment_cache")
            count = cursor.fetchone()[0]

            if count == 0:
                status_logger.info("Cache is already empty.")
                return

            conn.execute("DELETE FROM assessment_cache")
            conn.commit()

        status_logger.info(f"Cleared {count} cached assessment(s).")

    except Exception as e:
        status_logger.error(f"Error clearing cache: {e}")
        exit(1)


@main.command()
def status() -> None:
    """Show cache synchronization status for all backends."""
    status_logger = get_status_logger()

    try:
        status = cache_sync_manager.get_sync_status()

        status_logger.info("Cache Synchronization Status")
        status_logger.info("=" * 40)

        if status["sync_in_progress"]:
            status_logger.info("⚠️  Sync in progress...")
        else:
            status_logger.info("✅ No sync in progress")

        status_logger.info("\nBackend Status:")
        for backend_name, backend_info in status["backends"].items():
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

            status_text = f"{status_icon} {backend_name} ({'enabled' if enabled else 'disabled'}, {backend_type})"

            if backend_type == "cached":
                status_text += f" {data_icon} {'has data' if has_data else 'no data'}"
                if entry_count is not None and entry_count > 0:
                    status_text += f" ({entry_count:,} entries)"
                if last_updated:
                    status_text += f" (updated: {last_updated})"

            status_logger.info(f"  {status_text}")

    except Exception as e:
        status_logger.error(f"Error getting status: {e}")
        exit(1)


@main.command()
@click.argument("file_path", type=click.Path(exists=True))
@click.option(
    "--list-type",
    type=click.Choice(
        [AssessmentType.PREDATORY, AssessmentType.LEGITIMATE, AssessmentType.UNKNOWN]
    ),
    default=AssessmentType.PREDATORY,
    help="Type of journals in the list",
)
@click.option("--list-name", required=True, help="Name for the custom list source")
def add_list(file_path: str, list_type: str, list_name: str) -> None:
    """Add a custom journal list from a file.

    FILE_PATH: Path to CSV or JSON file containing journal names
    """
    status_logger = get_status_logger()

    try:
        file_path_obj = Path(file_path)

        status_logger.info(f"Adding custom list '{list_name}' from {file_path}")
        status_logger.info(f"List type: {list_type}")

        # Add the custom list to the updater
        data_updater.add_custom_list(file_path_obj, list_type, list_name)

        # Trigger immediate sync to load the data
        status_logger.info("Loading custom list data...")
        asyncio.run(cache_sync_manager.sync_cache_with_config(force=True))

        status_logger.info(f"Successfully added custom list '{list_name}'")

    except Exception as e:
        status_logger.error(f"Error adding custom list: {e}")
        exit(1)


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
    """Assess all journals in a BibTeX file for predatory status.

    BIBTEX_FILE: Path to the BibTeX file to assess

    Returns exit code 1 if any predatory journals are found, 0 otherwise.
    This allows the command to be used in automated scripts to check
    if a bibliography contains predatory journals.
    """
    asyncio.run(_async_bibtex_main(bibtex_file, verbose, output_format, relax_bibtex))


async def _async_bibtex_main(
    bibtex_file: str, verbose: bool, output_format: str, relax_bibtex: bool
) -> None:
    """Async main function for BibTeX assessment."""
    status_logger = get_status_logger()

    try:
        file_path = Path(bibtex_file)

        if verbose:
            status_logger.info(f"Assessing BibTeX file: {file_path}")

        # Assess all journals in the BibTeX file
        result = await BibtexBatchAssessor.assess_bibtex_file(
            file_path, verbose, relax_bibtex
        )

        # Output results
        if output_format == "json":
            # Convert result to JSON-serializable format
            result_dict = result.model_dump()
            # Convert assessment_results to a more JSON-friendly format
            assessment_list = []
            for entry, assessment in result.assessment_results:
                assessment_list.append(
                    {"entry": entry.model_dump(), "assessment": assessment.model_dump()}
                )
            result_dict["assessment_results"] = assessment_list
            print(json.dumps(result_dict, indent=2, default=str))
        else:
            # Display text summary
            summary = BibtexBatchAssessor.format_summary(result, verbose)
            print(summary)

        # Set exit code based on results
        exit_code = BibtexBatchAssessor.get_exit_code(result)
        sys.exit(exit_code)

    except FileNotFoundError:
        status_logger.error(f"Error: BibTeX file not found: {bibtex_file}")
        sys.exit(1)
    except ValueError as e:
        status_logger.error(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        if verbose:
            status_logger.error(f"Unexpected error: {e}")
            traceback.print_exc()
        else:
            status_logger.error("An unexpected error occurred. Use -v for details.")
        sys.exit(1)


async def _async_assess_publication(
    publication_name: str, publication_type: str, verbose: bool, output_format: str
) -> None:
    """Async function for assessing publications with type specification."""
    status_logger = get_status_logger()

    try:
        # Normalize the input
        query_input = input_normalizer.normalize(publication_name)

        if verbose:
            status_logger.info(f"Publication type: {publication_type}")
            status_logger.info(f"Normalized input: {query_input.normalized_name}")
            if query_input.identifiers:
                status_logger.info(f"Identifiers: {query_input.identifiers}")

        # Assess the publication - currently all types use the same backend pipeline
        result = await query_dispatcher.assess_journal(query_input)

        # Output results
        if output_format == "json":
            print(json.dumps(result.model_dump(), indent=2, default=str))
        else:
            # Determine display label based on publication type
            if publication_type == "conference":
                label = "Conference"
            else:  # journal
                label = "Journal"

            print(f"{label}: {result.input_query}")
            print(f"Assessment: {result.assessment.upper()}")
            print(f"Confidence: {result.confidence:.2f}")
            print(f"Overall Score: {result.overall_score:.2f}")
            print(f"Processing Time: {result.processing_time:.2f}s")

            if verbose and result.backend_results:
                print(f"\nBackend Results ({len(result.backend_results)}):")
                for backend_result in result.backend_results:
                    status_emoji = (
                        "✓"
                        if backend_result.status == BackendStatus.FOUND
                        else (
                            "✗"
                            if backend_result.status == BackendStatus.NOT_FOUND
                            else "⚠"
                        )
                    )
                    cache_indicator = " [cached]" if backend_result.cached else ""
                    timing_info = ""
                    if backend_result.execution_time_ms is not None:
                        timing_info = f" ({backend_result.execution_time_ms:.2f}ms)"
                    print(
                        f"  {status_emoji} {backend_result.backend_name}: {backend_result.status}{cache_indicator}{timing_info}"
                    )
                    if backend_result.assessment:
                        print(
                            f"    → {backend_result.assessment} (confidence: {backend_result.confidence:.2f})"
                        )
                    if backend_result.error_message:
                        print(f"    → Error: {backend_result.error_message}")

            if result.reasoning:
                print("\nReasoning:")
                for reason in result.reasoning:
                    print(f"  • {reason}")

    except ValueError as e:
        status_logger.error(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        if verbose:
            status_logger.error(f"Unexpected error: {e}")
            traceback.print_exc()
        else:
            status_logger.error("An unexpected error occurred. Use -v for details.")
        sys.exit(1)


if __name__ == "__main__":
    main()
