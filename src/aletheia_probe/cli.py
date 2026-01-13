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
from .cache import AcronymCache, AssessmentCache, RetractionCache
from .cache_sync import cache_sync_manager
from .config import get_config_manager
from .dispatcher import query_dispatcher
from .enums import AssessmentType
from .logging_config import get_detail_logger, get_status_logger, setup_logging
from .normalizer import input_normalizer, normalize_case
from .output_formatter import output_formatter
from .utils.dead_code import code_is_used


F = TypeVar("F", bound=Callable[..., Any])


@code_is_used  # This is called in error scenarios
def handle_cli_exception(
    exception: Exception, verbose: bool = False, context: str = ""
) -> None:
    """Handle CLI exceptions with consistent logging and exit behavior.

    Args:
        exception: The exception to handle
        verbose: Whether to show verbose error details
        context: Optional context string to include in error message
    """
    status_logger = get_status_logger()

    if isinstance(exception, FileNotFoundError):
        status_logger.error(f"Error: File not found: {exception}")
    elif isinstance(exception, ValueError):
        status_logger.error(f"Error: {exception}")
    elif isinstance(
        exception, (OSError, KeyError, RuntimeError, AttributeError, UnicodeDecodeError)
    ):
        if verbose:
            status_logger.error(
                f"Unexpected error{f' in {context}' if context else ''}: {exception}"
            )
            traceback.print_exc()
        else:
            status_logger.error("An unexpected error occurred. Use -v for details.")
    else:
        # Fallback for other exception types
        if verbose:
            status_logger.error(
                f"Error{f' in {context}' if context else ''}: {exception}"
            )
            traceback.print_exc()
        else:
            status_logger.error(f"Error: {exception}")

    sys.exit(1)


def handle_cli_errors(func: F) -> F:
    """Decorator to handle common CLI error patterns.

    Wraps CLI command functions with consistent error handling, logging,
    and exit behavior. Catches exceptions and logs them appropriately
    based on verbosity, then exits with status code 1.

    This decorator should be applied to Click command functions to reduce
    boilerplate try-except blocks throughout the CLI module.

    Args:
        func: The CLI command function to wrap.

    Returns:
        The wrapped function with error handling.
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        status_logger = get_status_logger()
        # Extract verbose flag if present in kwargs for error reporting
        verbose = kwargs.get("verbose", False)

        try:
            return func(*args, **kwargs)
        except Exception as e:
            # Catch all exceptions to provide user-friendly error messages
            # instead of crashing with stack traces in CLI context
            if verbose:
                status_logger.error(f"Error in {func.__name__}: {e}")
                traceback.print_exc()
            else:
                status_logger.error(f"Error: {e}")
            sys.exit(1)

    return wrapper  # type: ignore


def print_version(ctx: click.Context, param: click.Parameter, value: bool) -> None:
    """Print version and exit if requested.

    Args:
        ctx: Click context.
        param: Click parameter.
        value: Whether to print version information.
    """
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
@click.option(
    "--config",
    type=click.Path(exists=True, path_type=Path),
    help="Path to configuration file",
)
@click.pass_context
def main(ctx: click.Context, config: Path | None) -> None:
    """Aletheia-Probe - Assess whether journals are predatory or legitimate.

    Args:
        ctx: Click context.
        config: Path to an optional configuration file.
    """
    # Initialize logging on first command invocation
    detail_logger, status_logger = setup_logging()
    detail_logger.debug("CLI initialized")

    # Initialize config manager with custom path if provided
    if config:
        detail_logger.debug(f"Using config file: {config}")
        get_config_manager(config, force_reload=True)


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

    Args:
        journal_name: The name of the journal to assess.
        verbose: Whether to enable verbose output.
        output_format: The format of the output (text or json).
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

    Args:
        conference_name: The name of the conference to assess.
        verbose: Whether to enable verbose output.
        output_format: The format of the output (text or json).
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

    Args:
        force: Whether to force sync even if data appears fresh.
        backend_names: Optional tuple of backend names to sync.
    """
    # Auto-register custom lists before sync
    from .cache.custom_list_manager import auto_register_custom_lists

    auto_register_custom_lists()

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

    Args:
        confirm: Whether to skip the confirmation prompt.
    """
    status_logger = get_status_logger()

    if not confirm:
        click.confirm(
            "This will clear all cached assessment results. Continue?", abort=True
        )

    assessment_cache = AssessmentCache()

    # Get count before clearing
    count = assessment_cache.get_assessment_cache_count()

    if count == 0:
        status_logger.info("Cache is already empty.")
        return

    # Clear assessment cache
    assessment_cache.clear_assessment_cache()

    status_logger.info(f"Cleared {count} cached assessment(s).")


@main.command()
@handle_cli_errors
def status() -> None:
    """Show cache synchronization status for all backends."""
    # Auto-register custom lists before showing status
    from .cache.custom_list_manager import auto_register_custom_lists

    auto_register_custom_lists()

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

        if backend_type in ("cached", "api_cached") and (has_data or entry_count):
            status_text += f" {data_icon} {'has data' if has_data else 'no data'}"
            if entry_count is not None and entry_count > 0:
                status_text += f" ({entry_count:,} entries)"
            if last_updated:
                status_text += f" (updated: {last_updated})"

        status_logger.info(f"  {status_text}")


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

    Args:
        bibtex_file: Path to the BibTeX file to assess.
        verbose: Whether to enable verbose output.
        output_format: The format of the output (text or json).
        relax_bibtex: Whether to enable relaxed BibTeX parsing.

    Returns:
        None (exits with code 1 if predatory journals are found, 0 otherwise).
    """
    asyncio.run(_async_bibtex_main(bibtex_file, verbose, output_format, relax_bibtex))


@main.group(name="acronym")
def acronym() -> None:
    """Manage the venue acronym database (journals, conferences, etc.)."""
    pass


@acronym.command(name="status")
@handle_cli_errors
def acronym_status() -> None:
    """Show conference acronym database status."""
    status_logger = get_status_logger()

    acronym_cache = AcronymCache()
    stats = acronym_cache.get_acronym_stats()
    count = stats.get("total_count", 0)

    status_logger.info("Conference Acronym Database Status")
    status_logger.info("=" * 40)

    if count == 0:
        status_logger.info("Database is empty (no acronyms stored)")
    else:
        status_logger.info(f"Total acronyms: {count:,}")


@acronym.command()
@handle_cli_errors
def stats() -> None:
    """Show detailed statistics about the acronym database."""
    status_logger = get_status_logger()

    acronym_cache = AcronymCache()
    stats = acronym_cache.get_acronym_stats()

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
        display_name = normalize_case(normalized_name)
        status_logger.info("\nMost Recently Used:")
        status_logger.info(f"  Acronym: {stats['most_recent_acronym']}")
        status_logger.info(f"  Conference: {display_name}")
        status_logger.info(f"  Last Used: {stats['most_recent_used']}")

    if "oldest_acronym" in stats:
        # Apply title casing for display
        normalized_name = str(stats["oldest_normalized_name"])
        display_name = normalize_case(normalized_name)
        status_logger.info("\nOldest Entry:")
        status_logger.info(f"  Acronym: {stats['oldest_acronym']}")
        status_logger.info(f"  Conference: {display_name}")
        status_logger.info(f"  Created: {stats['oldest_created']}")


@acronym.command()
@click.option("--limit", type=int, help="Maximum number of entries to display")
@click.option("--offset", type=int, default=0, help="Number of entries to skip")
@handle_cli_errors
def list(limit: int | None, offset: int) -> None:
    """List all acronym mappings in the database.

    Args:
        limit: Maximum number of entries to display.
        offset: Number of entries to skip.
    """
    status_logger = get_status_logger()

    acronym_cache = AcronymCache()
    acronyms = acronym_cache.list_all_acronyms(limit=limit, offset=offset)

    if not acronyms:
        status_logger.info("No acronyms found in the database.")
        return

    status_logger.info("Conference Acronym Mappings")
    status_logger.info("=" * 80)

    for entry in acronyms:
        # Apply title casing for display
        display_name = normalize_case(entry["normalized_name"])

        status_logger.info(f"\nAcronym: {entry['acronym']}")
        status_logger.info(f"  Conference: {display_name}")
        status_logger.info(f"  Normalized: {entry['normalized_name']}")
        status_logger.info(f"  Source: {entry['source']}")
        status_logger.info(f"  Created: {entry['created_at']}")
        status_logger.info(f"  Last Used: {entry['last_used_at']}")

    total_count = acronym_cache.get_acronym_stats()["total_count"]
    shown = len(acronyms)

    if limit is not None or offset > 0:
        status_logger.info(f"\nShowing {shown} of {total_count:,} total acronyms")


@acronym.command()
@click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
@handle_cli_errors
def clear(confirm: bool) -> None:
    """Clear all entries from the acronym database.

    Args:
        confirm: Whether to skip the confirmation prompt.
    """
    status_logger = get_status_logger()

    if not confirm:
        click.confirm(
            "This will delete all conference acronym mappings. Continue?", abort=True
        )

    acronym_cache = AcronymCache()
    count = acronym_cache.clear_acronym_database()

    if count == 0:
        status_logger.info("Acronym database is already empty.")
    else:
        status_logger.info(f"Cleared {count:,} acronym mapping(s).")


@acronym.command()
@click.argument("acronym")
@click.argument("full_name")
@click.option(
    "--entity-type",
    required=True,
    help="Entity type: journal, conference, workshop, symposium, etc.",
)
@click.option(
    "--source",
    default="manual",
    help="Source of the mapping (default: manual)",
)
@handle_cli_errors
def add(acronym: str, full_name: str, entity_type: str, source: str) -> None:
    """Manually add an acronym mapping to the database.

    Args:
        acronym: The venue acronym (e.g., ICML, JMLR).
        full_name: The full venue name.
        entity_type: Entity type: journal, conference, workshop, symposium, etc.
        source: Source of the mapping (default: manual).
    """
    status_logger = get_status_logger()

    acronym_cache = AcronymCache()
    acronym_cache.store_acronym_mapping(acronym, full_name, entity_type, source)

    status_logger.info(f"Added acronym mapping: {acronym} -> {full_name}")
    status_logger.info(f"Entity type: {entity_type}")
    status_logger.info(f"Source: {source}")


@acronym.command(name="add-bibtex")
@click.argument("bibtex_file", type=click.Path(exists=True))
@click.option("--dry-run", is_flag=True, help="Preview changes without storing")
@handle_cli_errors
def add_bibtex(bibtex_file: str, dry_run: bool) -> None:
    """Extract and add acronyms from a BibTeX file.

    Args:
        bibtex_file: Path to the BibTeX file to process.
        dry_run: If True, show what would be added without storing.
    """
    from pathlib import Path

    from .bibtex_parser import BibtexParser
    from .models import (
        AcronymCollectionResult,
        AcronymConflict,
        AcronymMapping,
        VenueWithCount,
    )

    status_logger = get_status_logger()
    detail_logger = get_detail_logger()

    file_path = Path(bibtex_file)
    status_logger.info(f"Processing BibTeX file: {file_path}")

    # Parse BibTeX file
    parser = BibtexParser()
    try:
        entries, skipped_non_preprint, preprint_count = parser.parse_bibtex_file(
            file_path, relax_parsing=True
        )
        detail_logger.debug(f"Parsed {len(entries)} entries from BibTeX file")
    except Exception as e:
        status_logger.error(f"Failed to parse BibTeX file: {e}")
        raise click.Abort() from e

    # Extract acronyms
    acronym_cache = AcronymCache()
    new_mappings, existing_mappings, conflicts = (
        BibtexParser.extract_acronyms_from_entries(entries, acronym_cache)
    )

    # Build result object
    result = AcronymCollectionResult(
        file_path=str(file_path),
        total_processed=len(entries),
        new_acronyms=[
            AcronymMapping(
                acronym=acronym,
                venue_name=venue_name,
                normalized_name=normalized_name,
                entity_type=entity_type,
            )
            for acronym, venue_name, normalized_name, entity_type in new_mappings
        ],
        existing_acronyms=[
            AcronymMapping(
                acronym=acronym,
                venue_name=venue_name,
                normalized_name=normalized_name,
                entity_type=entity_type,
            )
            for acronym, venue_name, normalized_name, entity_type in existing_mappings
        ],
        conflicts=[
            AcronymConflict(
                acronym=acronym,
                entity_type=entity_type,
                venues=[
                    VenueWithCount(venue_name=venue, count=count)
                    for venue, count in venue_counts
                ],
            )
            for acronym, entity_type, venue_counts in conflicts
        ],
        skipped=len(entries)
        - len(new_mappings)
        - len(existing_mappings)
        - len(conflicts),
        existing_count=len(existing_mappings),
    )

    # Display summary
    status_logger.info(f"Processed {result.total_processed} entries")
    status_logger.info(f"New acronyms found: {len(result.new_acronyms)}")
    status_logger.info(f"Existing acronyms: {len(result.existing_acronyms)}")
    status_logger.info(f"Conflicts detected: {len(result.conflicts)}")
    status_logger.info(f"Entries without acronyms: {result.skipped}")

    # Show new acronyms
    if result.new_acronyms:
        status_logger.info("\nNew acronyms to add:")
        for mapping in result.new_acronyms:
            status_logger.info(
                f"  - {mapping.acronym} → {mapping.normalized_name} ({mapping.entity_type})"
            )

    # Show existing acronyms (only if verbose or if there are many)
    if result.existing_acronyms and len(result.existing_acronyms) <= 10:
        status_logger.info("\nExisting acronyms (already in database):")
        for mapping in result.existing_acronyms:
            status_logger.info(
                f"  - {mapping.acronym} → {mapping.normalized_name} ({mapping.entity_type})"
            )

    # Show conflicts with frequency statistics
    if result.conflicts:
        status_logger.warning("\nConflicts detected (will be marked as ambiguous):")
        for conflict in result.conflicts:
            total_occurrences = sum(v.count for v in conflict.venues)
            status_logger.warning(
                f"  - {conflict.acronym} ({conflict.entity_type}): "
                f"{len(conflict.venues)} variants, {total_occurrences} total occurrences"
            )

            # Sort by count (descending) to show most common first
            sorted_venues = sorted(conflict.venues, key=lambda v: v.count, reverse=True)
            for i, venue_with_count in enumerate(sorted_venues):
                marker = " ← Most common" if i == 0 else ""
                status_logger.warning(
                    f"    - {venue_with_count.venue_name} ({venue_with_count.count} times){marker}"
                )

    # If dry-run, stop here
    if dry_run:
        status_logger.info("\nDry-run mode: No changes made to database")
        return

    # Store new acronyms
    stored_count = 0
    for mapping in result.new_acronyms:
        acronym_cache.store_acronym_mapping(
            mapping.acronym,
            mapping.venue_name,
            mapping.entity_type,
            source="bibtex_extraction",
        )
        stored_count += 1

    # Mark conflicts as ambiguous
    ambiguous_count = 0
    for conflict in result.conflicts:
        venue_names = [v.venue_name for v in conflict.venues]
        acronym_cache.mark_acronym_as_ambiguous(
            conflict.acronym, conflict.entity_type, venue_names
        )
        ambiguous_count += 1

    status_logger.info(f"\nAdded {stored_count} new acronyms to database")
    if ambiguous_count > 0:
        status_logger.warning(
            f"Marked {ambiguous_count} acronyms as ambiguous (cannot be used for matching)"
        )


@acronym.command(name="list-ambiguous")
@click.option(
    "--entity-type",
    help="Filter by entity type: journal, conference, workshop, symposium, etc.",
)
@handle_cli_errors
def list_ambiguous(entity_type: str | None) -> None:
    """List all acronyms marked as ambiguous.

    Args:
        entity_type: Optional entity type filter.
    """
    status_logger = get_status_logger()

    acronym_cache = AcronymCache()
    ambiguous_acronyms = acronym_cache.list_ambiguous_acronyms(entity_type)

    if not ambiguous_acronyms:
        if entity_type:
            status_logger.info(
                f"No ambiguous acronyms found for entity_type '{entity_type}'"
            )
        else:
            status_logger.info("No ambiguous acronyms found")
        return

    status_logger.info(f"Ambiguous acronyms ({len(ambiguous_acronyms)} total):")
    status_logger.info("These acronyms cannot be used for automatic matching:\n")

    for entry in ambiguous_acronyms:
        status_logger.info(f"  {entry['acronym']} ({entry['entity_type']})")
        status_logger.info(f"    Normalized name: {entry['normalized_name']}")
        status_logger.info(f"    Source: {entry['source']}")
        status_logger.info(f"    Created: {entry['created_at']}\n")


@main.group(name="retraction-cache")
def retraction_cache() -> None:
    """Manage the article retraction cache."""
    pass


@retraction_cache.command(name="clear")
@click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
@handle_cli_errors
def clear_retraction_cache(confirm: bool) -> None:
    """Clear all article retraction cache entries.

    Args:
        confirm: Whether to skip the confirmation prompt.
    """
    status_logger = get_status_logger()

    if not confirm:
        click.confirm(
            "This will clear all cached article retraction data. Continue?", abort=True
        )

    retraction_cache_obj = RetractionCache()

    # Get count before clearing
    count = retraction_cache_obj.clear_article_retractions()

    if count == 0:
        status_logger.info("No retraction cache entries to clear.")
    else:
        status_logger.info(f"Cleared {count:,} retraction cache entry/entries.")


@main.group(name="custom-list")
def custom_list() -> None:
    """Manage custom journal lists."""
    pass


@custom_list.command(name="add")
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
def add_custom_list(file_path: str, list_type: str, list_name: str) -> None:
    """Add a custom journal list from a file.

    Args:
        file_path: Path to CSV or JSON file containing journal names.
        list_type: Type of journals in the list (predatory, legitimate, etc.).
        list_name: Name for the custom list source.
    """
    from .cache.custom_list_manager import CustomListManager

    status_logger = get_status_logger()

    status_logger.info(f"Adding custom list '{list_name}' from {file_path}")
    status_logger.info(f"List type: {list_type}")

    # Convert string to AssessmentType enum
    assessment_type = AssessmentType(list_type)

    # Store custom list persistently in database
    try:
        custom_list_manager = CustomListManager()
        custom_list_manager.add_custom_list(list_name, file_path, assessment_type)

        status_logger.info(f"Successfully added custom list '{list_name}'")
        status_logger.info("Run 'aletheia-probe sync' to load the data into cache")

    except ValueError as e:
        status_logger.error(f"Failed to add custom list: {e}")
        raise click.ClickException(str(e)) from e


@custom_list.command(name="list")
@handle_cli_errors
def list_custom_lists() -> None:
    """List all registered custom journal lists."""
    from .cache.custom_list_manager import CustomListManager

    status_logger = get_status_logger()

    try:
        custom_list_manager = CustomListManager()
        custom_lists = custom_list_manager.get_all_custom_lists()

        if not custom_lists:
            status_logger.info("No custom lists found")
            return

        status_logger.info(f"Found {len(custom_lists)} custom list(s):")
        status_logger.info("")

        for custom_list in custom_lists:
            list_name = custom_list["list_name"]
            file_path = custom_list["file_path"]
            list_type = custom_list["list_type"]
            enabled = custom_list["enabled"]
            created_at = custom_list["created_at"]

            # Check if file still exists
            file_exists = Path(file_path).exists()
            file_status = "✓" if file_exists else "✗ (missing)"

            status_text = f"  {list_name}:"
            status_logger.info(status_text)
            status_logger.info(f"    Type: {list_type}")
            status_logger.info(f"    File: {file_path} {file_status}")
            status_logger.info(f"    Status: {'Enabled' if enabled else 'Disabled'}")
            status_logger.info(f"    Created: {created_at}")
            status_logger.info("")

    except Exception as e:
        status_logger.error(f"Failed to list custom lists: {e}")
        raise click.ClickException(str(e)) from e


@custom_list.command(name="remove")
@click.argument("list_name")
@click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
@handle_cli_errors
def remove_custom_list(list_name: str, confirm: bool) -> None:
    """Remove a custom journal list.

    Args:
        list_name: Name of the custom list to remove.
        confirm: Whether to skip the confirmation prompt.
    """
    from .cache.custom_list_manager import CustomListManager

    status_logger = get_status_logger()

    try:
        custom_list_manager = CustomListManager()

        # Check if list exists
        if not custom_list_manager.custom_list_exists(list_name):
            status_logger.error(f"Custom list '{list_name}' not found")
            raise click.ClickException(f"Custom list '{list_name}' does not exist")

        # Confirmation prompt
        if not confirm:
            click.confirm(
                f"Are you sure you want to remove custom list '{list_name}'?",
                abort=True,
            )

        # Remove the list
        success = custom_list_manager.remove_custom_list(list_name)

        if success:
            status_logger.info(f"Successfully removed custom list '{list_name}'")
        else:
            status_logger.error(f"Failed to remove custom list '{list_name}'")
            raise click.ClickException("Removal failed")

    except click.ClickException:
        raise
    except Exception as e:
        status_logger.error(f"Failed to remove custom list: {e}")
        raise click.ClickException(str(e)) from e


async def _async_bibtex_main(
    bibtex_file: str, verbose: bool, output_format: str, relax_bibtex: bool
) -> None:
    """Async main function for BibTeX assessment.

    Args:
        bibtex_file: Path to the BibTeX file to assess.
        verbose: Whether to enable verbose output.
        output_format: The format of the output (text or json).
        relax_bibtex: Whether to enable relaxed BibTeX parsing.
    """
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

    except Exception as e:
        handle_cli_exception(e, verbose, "BibTeX processing")


async def _async_assess_publication(
    publication_name: str, publication_type: str, verbose: bool, output_format: str
) -> None:
    """Async function for assessing publications with type specification.

    Args:
        publication_name: The name of the publication to assess.
        publication_type: The type of publication (journal or conference).
        verbose: Whether to enable verbose output.
        output_format: The format of the output (text or json).
    """
    status_logger = get_status_logger()
    acronym_cache = AcronymCache()

    try:
        # Normalize the input (without acronym lookup for now)
        query_input = input_normalizer.normalize(publication_name)

        # Store any extracted acronym mappings in cache with detected venue type
        for acronym, full_name in query_input.extracted_acronym_mappings.items():
            acronym_cache.store_acronym_mapping(
                acronym, full_name, query_input.venue_type.value, source="user_input"
            )

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

    except Exception as e:
        handle_cli_exception(e, verbose, "publication assessment")


if __name__ == "__main__":
    main()
