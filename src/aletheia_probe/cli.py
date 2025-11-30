# SPDX-License-Identifier: MIT
"""Command-line interface for the journal assessment tool."""

import asyncio
import functools
import json
import sys
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

import click

from . import __version__
from .batch_assessor import BibtexBatchAssessor
from .cache import get_cache_manager
from .cache_sync import cache_sync_manager
from .config import get_config_manager
from .dispatcher import query_dispatcher
from .enums import AssessmentType
from .logging_config import get_status_logger, setup_logging
from .normalizer import input_normalizer
from .output_formatter import output_formatter
from .updater import data_updater  # Global updater instance from updater package


F = TypeVar("F", bound=Callable[..., Any])


def handle_cli_errors(func: F) -> F:
    """Decorator to handle common CLI error patterns.

    Wraps CLI command functions with consistent error handling, logging,
    and exit behavior. Catches exceptions and logs them appropriately
    based on verbosity, then exits with status code 1.

    This decorator should be applied to Click command functions to reduce
    boilerplate try-except blocks throughout the CLI module.
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        status_logger = get_status_logger()
        # Extract verbose flag if present in kwargs for error reporting
        verbose = kwargs.get("verbose", False)

        try:
            return func(*args, **kwargs)
        except (
            ValueError,
            OSError,
            KeyError,
            AttributeError,
            RuntimeError,
            Exception,
        ) as e:
            if verbose:
                status_logger.error(f"Error in {func.__name__}: {e}")
                traceback.print_exc()
            else:
                status_logger.error(f"Error: {e}")
            sys.exit(1)

    return wrapper  # type: ignore


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
@handle_cli_errors
def config() -> None:
    """Show the complete current configuration."""
    config_output = get_config_manager().show_config()
    print(config_output)


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
            sys.exit(1)

        # Check if any backend had an error
        for backend_result in result.values():
            if isinstance(backend_result, dict):
                if backend_result.get("status") in ["error", "failed"]:
                    sys.exit(1)

    except (ValueError, OSError, KeyError, RuntimeError) as e:
        status_logger = get_status_logger()
        status_logger.error(f"Error during sync: {e}")
        sys.exit(1)


@main.command()
@click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
@handle_cli_errors
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

    cache_manager = get_cache_manager()

    # Get count before clearing
    count = cache_manager.get_assessment_cache_count()

    if count == 0:
        status_logger.info("Cache is already empty.")
        return

    # Clear assessment cache using CacheManager method
    cache_manager.clear_assessment_cache()

    status_logger.info(f"Cleared {count} cached assessment(s).")


@main.command()
@handle_cli_errors
def status() -> None:
    """Show cache synchronization status for all backends."""
    status_logger = get_status_logger()

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
            status_logger.info(f"  ❌ {backend_name}: Error - {backend_info['error']}")
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


@main.command()
@click.argument("file_path", type=click.Path(exists=True))
@click.option(
    "--list-type",
    type=click.Choice(
        [
            AssessmentType.PREDATORY,
            AssessmentType.LEGITIMATE,
            AssessmentType.SUSPICIOUS,
            AssessmentType.UNKNOWN,
        ]
    ),
    default=AssessmentType.PREDATORY,
    help="Type of journals in the list",
)
@click.option("--list-name", required=True, help="Name for the custom list source")
@handle_cli_errors
def add_list(file_path: str, list_type: str, list_name: str) -> None:
    """Add a custom journal list from a file.

    FILE_PATH: Path to CSV or JSON file containing journal names
    """
    status_logger = get_status_logger()

    file_path_obj = Path(file_path)

    status_logger.info(f"Adding custom list '{list_name}' from {file_path}")
    status_logger.info(f"List type: {list_type}")

    # Convert string to AssessmentType enum
    assessment_type = AssessmentType(list_type)

    # Add the custom list to the updater
    data_updater.add_custom_list(file_path_obj, assessment_type, list_name)

    # Trigger immediate sync to load the data
    status_logger.info("Loading custom list data...")
    asyncio.run(cache_sync_manager.sync_cache_with_config(force=True))

    status_logger.info(f"Successfully added custom list '{list_name}'")


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


@main.group(name="conference-acronym")
def conference_acronym() -> None:
    """Manage the conference acronym database."""
    pass


@conference_acronym.command(name="status")
@handle_cli_errors
def acronym_status() -> None:
    """Show conference acronym database status."""
    status_logger = get_status_logger()

    cache_manager = get_cache_manager()
    stats = cache_manager.get_acronym_stats()
    count = stats.get("total_count", 0)

    status_logger.info("Conference Acronym Database Status")
    status_logger.info("=" * 40)

    if count == 0:
        status_logger.info("Database is empty (no acronyms stored)")
    else:
        status_logger.info(f"Total acronyms: {count:,}")


@conference_acronym.command()
@handle_cli_errors
def stats() -> None:
    """Show detailed statistics about the acronym database."""
    status_logger = get_status_logger()

    cache_manager = get_cache_manager()
    stats = cache_manager.get_acronym_stats()

    status_logger.info("Conference Acronym Database Statistics")
    status_logger.info("=" * 40)

    total = stats.get("total_count", 0)

    if total == 0:
        status_logger.info("Database is empty (no acronyms stored)")
        return

    status_logger.info(f"Total acronyms: {total:,}")

    if "most_recent_acronym" in stats:
        # Apply title casing for display
        normalized_name = str(stats["most_recent_normalized_name"])
        display_name = input_normalizer._normalize_case(normalized_name)
        status_logger.info("\nMost Recently Used:")
        status_logger.info(f"  Acronym: {stats['most_recent_acronym']}")
        status_logger.info(f"  Conference: {display_name}")
        status_logger.info(f"  Last Used: {stats['most_recent_used']}")

    if "oldest_acronym" in stats:
        # Apply title casing for display
        normalized_name = str(stats["oldest_normalized_name"])
        display_name = input_normalizer._normalize_case(normalized_name)
        status_logger.info("\nOldest Entry:")
        status_logger.info(f"  Acronym: {stats['oldest_acronym']}")
        status_logger.info(f"  Conference: {display_name}")
        status_logger.info(f"  Created: {stats['oldest_created']}")


@conference_acronym.command()
@click.option("--limit", type=int, help="Maximum number of entries to display")
@click.option("--offset", type=int, default=0, help="Number of entries to skip")
@handle_cli_errors
def list(limit: int | None, offset: int) -> None:
    """List all acronym mappings in the database."""
    status_logger = get_status_logger()

    cache_manager = get_cache_manager()
    acronyms = cache_manager.list_all_acronyms(limit=limit, offset=offset)

    if not acronyms:
        status_logger.info("No acronyms found in the database.")
        return

    status_logger.info("Conference Acronym Mappings")
    status_logger.info("=" * 80)

    for entry in acronyms:
        # Apply title casing for display
        display_name = input_normalizer._normalize_case(entry["normalized_name"])

        status_logger.info(f"\nAcronym: {entry['acronym']}")
        status_logger.info(f"  Conference: {display_name}")
        status_logger.info(f"  Normalized: {entry['normalized_name']}")
        status_logger.info(f"  Source: {entry['source']}")
        status_logger.info(f"  Created: {entry['created_at']}")
        status_logger.info(f"  Last Used: {entry['last_used_at']}")

    total_count = cache_manager.get_acronym_stats()["total_count"]
    shown = len(acronyms)

    if limit is not None or offset > 0:
        status_logger.info(f"\nShowing {shown} of {total_count:,} total acronyms")


@conference_acronym.command()
@click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
@handle_cli_errors
def clear(confirm: bool) -> None:
    """Clear all entries from the acronym database."""
    status_logger = get_status_logger()

    if not confirm:
        click.confirm(
            "This will delete all conference acronym mappings. Continue?", abort=True
        )

    cache_manager = get_cache_manager()
    count = cache_manager.clear_acronym_database()

    if count == 0:
        status_logger.info("Acronym database is already empty.")
    else:
        status_logger.info(f"Cleared {count:,} acronym mapping(s).")


@conference_acronym.command()
@click.argument("acronym")
@click.argument("full_name")
@click.option(
    "--source",
    default="manual",
    help="Source of the mapping (default: manual)",
)
@handle_cli_errors
def add(acronym: str, full_name: str, source: str) -> None:
    """Manually add an acronym mapping to the database.

    ACRONYM: The conference acronym (e.g., ICML)
    FULL_NAME: The full conference name
    """
    status_logger = get_status_logger()

    cache_manager = get_cache_manager()
    cache_manager.store_acronym_mapping(acronym, full_name, source)

    status_logger.info(f"Added acronym mapping: {acronym} -> {full_name}")
    status_logger.info(f"Source: {source}")


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
    except (
        OSError,
        KeyError,
        RuntimeError,
        AttributeError,
        UnicodeDecodeError,
    ) as e:
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
    from .cache import get_cache_manager

    status_logger = get_status_logger()
    cache = get_cache_manager()

    try:
        # Normalize the input with acronym lookup from cache
        query_input = input_normalizer.normalize(
            publication_name, acronym_lookup=cache.get_full_name_for_acronym
        )

        # Store any extracted acronym mappings in cache
        for acronym, full_name in query_input.extracted_acronym_mappings.items():
            cache.store_acronym_mapping(acronym, full_name, source="user_input")

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
            # Use enhanced formatter for text output
            formatted_output = output_formatter.format_text_output(
                result, publication_type, verbose
            )
            print(formatted_output)

    except ValueError as e:
        status_logger.error(f"Error: {e}")
        sys.exit(1)
    except (OSError, KeyError, RuntimeError, AttributeError) as e:
        if verbose:
            status_logger.error(f"Unexpected error: {e}")
            traceback.print_exc()
        else:
            status_logger.error("An unexpected error occurred. Use -v for details.")
        sys.exit(1)


if __name__ == "__main__":
    main()
