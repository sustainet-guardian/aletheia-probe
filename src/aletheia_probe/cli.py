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
    """Show statistics about the acronym database."""
    status_logger = get_status_logger()

    acronym_cache = AcronymCache()
    stats = acronym_cache.get_acronym_stats()

    total = stats.get("total_count", 0)

    if total == 0:
        status_logger.info("Database is empty (no acronyms stored)")
        return

    status_logger.info(f"Total acronyms: {total:,}")


@acronym.command(name="abbreviation-stats")
@handle_cli_errors
def abbreviation_stats() -> None:
    """Show statistics about the learned abbreviations database."""
    status_logger = get_status_logger()

    acronym_cache = AcronymCache()
    abbreviations = acronym_cache.export_all_abbreviations()
    total = len(abbreviations)

    if total == 0:
        status_logger.info("No abbreviations learned yet")
    else:
        status_logger.info(f"Total learned abbreviations: {total:,}")


@acronym.command(name="list")
@click.option("--limit", type=int, help="Maximum number of entries to display")
@click.option("--offset", type=int, default=0, help="Number of entries to skip")
@handle_cli_errors
def list_acronyms(limit: int | None, offset: int) -> None:
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

    for entry in acronyms:
        display_name = normalize_case(entry["normalized_name"])
        count = entry.get("usage_count", 0)
        status_logger.info(
            f"{entry['acronym']} -> {display_name} [{entry['entity_type']}] (count: {count})"
        )

    total_count = acronym_cache.get_acronym_stats()["total_count"]
    shown = len(acronyms)

    if limit is not None or offset > 0:
        status_logger.info(f"\nShowing {shown} of {total_count:,} total acronyms")


@acronym.command()
@click.argument("output_file", type=click.Path())
@handle_cli_errors
def export(output_file: str) -> None:
    """Export the entire acronym and abbreviation database to a JSON file.

    Args:
        output_file: Path to the output JSON file.
    """
    status_logger = get_status_logger()
    acronym_cache = AcronymCache()

    variants = acronym_cache.export_all_variants()
    abbreviations = acronym_cache.export_all_abbreviations()

    dataset = {
        "acronyms": variants,
        "abbreviations": abbreviations,
        "metadata": {
            "version": "1.0",
            "type": "aletheia-probe-venue-intelligence",
        },
    }

    try:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(dataset, f, indent=2, ensure_ascii=False)

        status_logger.info(
            f"Successfully exported {len(variants)} acronym variants and "
            f"{len(abbreviations)} learned abbreviations to {output_file}"
        )
    except Exception as e:
        status_logger.error(f"Failed to export dataset: {e}")
        raise click.ClickException(str(e)) from e


@acronym.command(name="import")
@click.argument("input_file", type=click.Path(exists=True))
@click.option(
    "--merge/--no-merge",
    default=True,
    help="Merge with existing data (default) or replace",
)
@handle_cli_errors
def import_acronyms(input_file: str, merge: bool) -> None:
    """Import acronyms and abbreviations from a JSON file.

    Supports both unified dataset format and legacy list-only format.

    Args:
        input_file: Path to the input JSON file.
        merge: Whether to merge with existing data.
    """
    status_logger = get_status_logger()
    acronym_cache = AcronymCache()

    try:
        with open(input_file, encoding="utf-8") as f:
            data = json.load(f)

        variants = []
        abbreviations = []

        # Detect format
        if isinstance(data, list):
            # Legacy format: list of variants
            variants = data
            status_logger.info(f"Detected legacy format with {len(variants)} variants")
        elif isinstance(data, dict):
            # Unified format
            variants = data.get("acronyms", [])
            abbreviations = data.get("abbreviations", [])
            status_logger.info(
                f"Detected unified format with {len(variants)} variants and "
                f"{len(abbreviations)} abbreviations"
            )
        else:
            raise ValueError("Input file must contain a JSON list or object")

        if not merge:
            if click.confirm(
                "This will clear existing data before importing. Continue?",
                abort=True,
            ):
                acronym_cache.clear_acronym_database()
                acronym_cache.clear_learned_abbreviations()

        variant_count = acronym_cache.import_variants(variants, merge=True)
        abbrev_count = acronym_cache.import_abbreviations(abbreviations, merge=True)

        status_logger.info(
            f"Successfully imported {variant_count} acronym variants and "
            f"{abbrev_count} learned abbreviations"
        )

    except Exception as e:
        status_logger.error(f"Failed to import dataset: {e}")
        raise click.ClickException(str(e)) from e


@acronym.command()
@click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
@click.option(
    "--include-abbreviations", is_flag=True, help="Also clear learned abbreviations"
)
@handle_cli_errors
def clear(confirm: bool, include_abbreviations: bool) -> None:
    """Clear entries from the acronym database.

    Args:
        confirm: Whether to skip the confirmation prompt.
        include_abbreviations: Whether to also clear learned abbreviations.
    """
    status_logger = get_status_logger()

    msg = "This will delete all conference acronym mappings."
    if include_abbreviations:
        msg = "This will delete all acronym mappings AND learned abbreviations."

    if not confirm:
        click.confirm(f"{msg} Continue?", abort=True)

    acronym_cache = AcronymCache()
    count = acronym_cache.clear_acronym_database()

    if count == 0:
        status_logger.info("Acronym database is already empty.")
    else:
        status_logger.info(f"Cleared {count:,} acronym mapping(s).")

    if include_abbreviations:
        abbrev_count = acronym_cache.clear_learned_abbreviations()
        if abbrev_count == 0:
            status_logger.info("Learned abbreviations database is already empty.")
        else:
            status_logger.info(f"Cleared {abbrev_count:,} learned abbreviation(s).")


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
@click.argument("bibtex_file", type=click.Path(exists=True), required=False)
@click.option(
    "--directory",
    "-d",
    type=click.Path(exists=True),
    help="Process all .bib files in directory",
)
@click.option(
    "--recursive", "-r", is_flag=True, help="Search subdirectories recursively"
)
@click.option(
    "--workers", "-w", type=int, default=None, help="Number of parallel workers"
)
@click.option(
    "--batch-size",
    "-b",
    type=int,
    default=100,
    help="Batch size for database operations",
)
@click.option("--dry-run", is_flag=True, help="Preview changes without storing")
@handle_cli_errors
def add_bibtex(
    bibtex_file: str | None,
    directory: str | None,
    recursive: bool,
    workers: int | None,
    batch_size: int,
    dry_run: bool,
) -> None:
    """Extract and add acronyms from BibTeX file(s).

    Can process a single file or multiple files from a directory.

    Examples:
        # Single file
        aletheia-probe acronym add-bibtex paper.bib

        # All files in directory
        aletheia-probe acronym add-bibtex -d /path/to/bibtex/files

        # Recursive directory search
        aletheia-probe acronym add-bibtex -d /path/to/bibtex -r

        # With parallel processing
        aletheia-probe acronym add-bibtex -d /path/to/bibtex -r -w 4

    Args:
        bibtex_file: Path to a single BibTeX file to process.
        directory: Path to directory containing BibTeX files.
        recursive: Search subdirectories recursively.
        workers: Number of parallel workers for processing.
        batch_size: Batch size for database operations.
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

    # Validate arguments
    if not bibtex_file and not directory:
        status_logger.error("Must provide either BIBTEX_FILE or --directory")
        raise click.Abort()

    if bibtex_file and directory:
        status_logger.error("Cannot use both BIBTEX_FILE and --directory")
        raise click.Abort()

    # Multi-file processing mode
    if directory or (bibtex_file and workers and workers > 1):
        from .batch_acronym_processor import (
            discover_bibtex_files,
            merge_file_results,
            process_files_parallel,
        )

        # Discover files
        files = discover_bibtex_files(
            single_file=bibtex_file,
            directory=directory,
            recursive=recursive,
        )

        if not files:
            status_logger.warning("No BibTeX files found")
            return

        status_logger.info(f"Found {len(files)} BibTeX file(s) to process")

        # Process files in parallel
        def progress_callback(completed: int, total: int, file_path: Path) -> None:
            status_logger.info(f"[{completed}/{total}] Processed {file_path.name}")

        results = process_files_parallel(
            files, max_workers=workers, progress_callback=progress_callback
        )

        # Merge results and check against database
        acronym_cache = AcronymCache()
        merged = merge_file_results(results, acronym_cache)

        # Display errors
        if merged.files_with_errors:
            status_logger.warning(
                f"\n{len(merged.files_with_errors)} file(s) had errors:"
            )
            for file_path, error in merged.files_with_errors:
                status_logger.warning(f"  - {file_path.name}: {error}")

        # Display summary
        status_logger.info(f"\nProcessed {merged.files_processed} file(s)")
        status_logger.info(f"Total entries: {merged.total_entries}")
        status_logger.info(f"New acronyms: {len(merged.new_acronyms)}")
        status_logger.info(f"Existing acronyms: {len(merged.existing_acronyms)}")
        status_logger.info(f"Conflicts: {len(merged.conflicts)}")

        # Show new acronyms (limited to first 50)
        if merged.new_acronyms:
            status_logger.info("\nNew acronyms to add:")
            for (
                acronym,
                _venue_name,
                normalized,
                entity_type,
                count,
            ) in merged.new_acronyms[:50]:
                status_logger.info(
                    f"  - {acronym} → {normalized} ({entity_type}) [{count} occurrence(s)]"
                )
            if len(merged.new_acronyms) > 50:
                status_logger.info(f"  ... and {len(merged.new_acronyms) - 50} more")

        # Show conflicts
        if merged.conflicts:
            status_logger.warning("\nConflicts detected (will be marked as ambiguous):")
            for acronym, entity_type, venue_counts in merged.conflicts:
                status_logger.warning(f"  - {acronym} ({entity_type}):")
                for venue, count in venue_counts:
                    status_logger.warning(f"    - {venue} [{count} occurrence(s)]")

        # If dry-run, stop here
        if dry_run:
            status_logger.info("\nDry-run mode: No changes made to database")
            return

        # Store new acronyms using bulk method (delegates to store_variant internally)
        if merged.new_acronyms:
            mappings = [
                (acronym, venue_name, normalized, entity_type)
                for acronym, venue_name, normalized, entity_type, _ in merged.new_acronyms
            ]
            stored_count = acronym_cache.bulk_store_acronyms(
                mappings, source="bibtex_extraction"
            )
            status_logger.info(f"\nAdded {stored_count} new acronyms to database")

        # Update usage counts for existing acronyms
        if merged.existing_acronyms:
            for (
                acronym,
                _venue_name,
                normalized,
                entity_type,
                count,
            ) in merged.existing_acronyms:
                variants = acronym_cache.get_variants(acronym, entity_type)
                for v in variants:
                    if v["normalized_name"] == normalized:
                        acronym_cache.increment_variant_count(v["id"], count)
                        acronym_cache.update_canonical_variant(acronym, entity_type)
                        break

        # Store conflict variants and mark as ambiguous
        if merged.conflicts:
            ambiguous_count = 0
            for acronym, entity_type, venue_counts in merged.conflicts:
                for venue, count in venue_counts:
                    acronym_cache.store_variant(
                        acronym=acronym,
                        entity_type=entity_type,
                        variant_name=venue,
                        normalized_name=venue,
                        usage_count=count,
                        source="bibtex_extraction",
                    )
                with acronym_cache.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        UPDATE venue_acronym_variants
                        SET is_ambiguous = TRUE
                        WHERE acronym = ? COLLATE NOCASE AND entity_type = ?
                        """,
                        (acronym, entity_type),
                    )
                    conn.commit()
                ambiguous_count += 1
            status_logger.warning(
                f"Marked {ambiguous_count} acronyms as ambiguous (cannot be used for matching)"
            )

        return

    # Single file processing mode
    file_path = Path(bibtex_file)  # type: ignore[arg-type]

    # Parse BibTeX file (suppress pybtex warnings)
    import io

    import pybtex.io  # type: ignore[import-untyped]

    old_pybtex_stderr = pybtex.io.stderr
    pybtex.io.stderr = io.StringIO()

    parser = BibtexParser()
    try:
        entries, skipped_non_preprint, preprint_count = parser.parse_bibtex_file(
            file_path, relax_parsing=True
        )
        detail_logger.debug(f"Parsed {len(entries)} entries from BibTeX file")
    except Exception as e:
        status_logger.error(f"Failed to parse BibTeX file: {e}")
        raise click.Abort() from e
    finally:
        pybtex.io.stderr = old_pybtex_stderr

    # Extract acronyms (3-tuple: new, existing, conflicts)
    acronym_cache = AcronymCache()
    new_mappings, existing_mappings, conflicts = (
        BibtexParser.extract_acronyms_from_entries(entries, acronym_cache, file_path)
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
    )

    # Skip empty reports
    if not result.new_acronyms and not result.conflicts:
        detail_logger.debug(
            f"No acronyms found in {file_path} (processed {result.total_processed} entries)"
        )
        return

    # Show new acronyms in concise format
    if result.new_acronyms:
        for mapping in result.new_acronyms:
            status_logger.info(
                f"{file_path}: added {mapping.acronym} → {mapping.normalized_name} ({mapping.entity_type})"
            )

    # Show conflicts in one-line format
    if result.conflicts:
        for conflict in result.conflicts:
            sorted_venues = sorted(conflict.venues, key=lambda v: v.count, reverse=True)
            venue_summary = ", ".join(
                f"{v.venue_name}({v.count})" for v in sorted_venues[:3]
            )
            if len(sorted_venues) > 3:
                venue_summary += f" +{len(sorted_venues) - 3} more"
            status_logger.warning(
                f"{file_path}: conflict {conflict.acronym} ({conflict.entity_type}): {venue_summary}"
            )

    # If dry-run, stop here
    if dry_run:
        status_logger.info("\nDry-run mode: No changes made to database")
        return

    # Store new acronyms as variants
    stored_count = 0
    for mapping in result.new_acronyms:
        acronym_cache.store_variant(
            acronym=mapping.acronym,
            entity_type=mapping.entity_type,
            variant_name=mapping.venue_name,
            normalized_name=mapping.normalized_name,
            usage_count=1,
            source="bibtex_extraction",
        )
        acronym_cache.update_canonical_variant(mapping.acronym, mapping.entity_type)
        stored_count += 1

    # Update usage counts for existing acronyms
    for mapping in result.existing_acronyms:
        variants = acronym_cache.get_variants(mapping.acronym, mapping.entity_type)
        for v in variants:
            if v["normalized_name"] == mapping.normalized_name:
                acronym_cache.increment_variant_count(v["id"], 1)
                acronym_cache.update_canonical_variant(
                    mapping.acronym, mapping.entity_type
                )
                break

    # Store conflict variants and mark as ambiguous
    ambiguous_count = 0
    for conflict in result.conflicts:
        for venue_with_count in conflict.venues:
            acronym_cache.store_variant(
                acronym=conflict.acronym,
                entity_type=conflict.entity_type,
                variant_name=venue_with_count.venue_name,
                normalized_name=venue_with_count.venue_name,
                usage_count=venue_with_count.count,
                source="bibtex_extraction",
            )

        # Mark all variants as ambiguous
        with acronym_cache.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE venue_acronym_variants
                SET is_ambiguous = TRUE
                WHERE acronym = ? COLLATE NOCASE AND entity_type = ?
                """,
                (conflict.acronym, conflict.entity_type),
            )
            conn.commit()
        ambiguous_count += 1


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

    for entry in ambiguous_acronyms:
        display_name = normalize_case(entry["normalized_name"])
        count = entry.get("usage_count", 0)
        status_logger.info(
            f"{entry['acronym']} -> {display_name} [{entry['entity_type']}] (count: {count})"
        )


@main.group(name="db")
def db() -> None:
    """Manage database schema and versioning."""
    pass


@db.command(name="version")
@handle_cli_errors
def db_version() -> None:
    """Show the current database schema version."""
    from .cache.schema import SCHEMA_VERSION, get_schema_version
    from .config import get_config_manager

    status_logger = get_status_logger()

    # Get database path from config
    db_path = Path(get_config_manager().load_config().cache.db_path)

    if not db_path.exists():
        status_logger.info("Database does not exist yet (will be created on first use)")
        status_logger.info(f"Expected schema version: {SCHEMA_VERSION}")
        return

    current_version = get_schema_version(db_path)

    if current_version is None:
        status_logger.warning("⚠️  Legacy database detected (no version tracking)")
        status_logger.info(f"Current code expects: version {SCHEMA_VERSION}")
        status_logger.info("\nTo migrate to current version:")
        status_logger.info("  aletheia-probe db migrate")
    elif current_version < SCHEMA_VERSION:
        status_logger.warning(f"⚠️  Database schema version: {current_version}")
        status_logger.info(f"Current code expects: version {SCHEMA_VERSION}")
        status_logger.info("\nDatabase needs migration:")
        status_logger.info("  aletheia-probe db migrate")
    elif current_version > SCHEMA_VERSION:
        status_logger.error(f"❌ Database schema version: {current_version}")
        status_logger.error(f"Current code supports up to: version {SCHEMA_VERSION}")
        status_logger.info("\nPlease upgrade aletheia-probe:")
        status_logger.info("  pip install --upgrade aletheia-probe")
    else:
        status_logger.info(f"✅ Database schema version: {current_version}")
        status_logger.info("Schema is up to date")


@db.command(name="migrate")
@click.option(
    "--target-version",
    type=int,
    help="Target version to migrate to (default: latest)",
)
@handle_cli_errors
def db_migrate(target_version: int | None) -> None:
    """Migrate database to a newer schema version.

    Creates a backup before migration.

    Args:
        target_version: Target version to migrate to (default: latest).
    """
    from .cache.migrations import migrate_database
    from .cache.schema import SCHEMA_VERSION
    from .config import get_config_manager

    status_logger = get_status_logger()

    # Get database path from config
    db_path = Path(get_config_manager().load_config().cache.db_path)

    if not db_path.exists():
        status_logger.error("Database does not exist yet")
        status_logger.info("Run any command to create a new database automatically")
        sys.exit(1)

    if target_version is None:
        target_version = SCHEMA_VERSION

    try:
        success = migrate_database(db_path, target_version)
        if success:
            sys.exit(0)
        else:
            sys.exit(1)
    except Exception as e:
        status_logger.error(f"Migration failed: {e}")
        sys.exit(1)


@db.command(name="reset")
@click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
@handle_cli_errors
def db_reset(confirm: bool) -> None:
    """Reset database to current schema version.

    WARNING: This deletes all data! Creates a backup first.

    Args:
        confirm: Whether to skip the confirmation prompt.
    """
    from .cache.migrations import reset_database
    from .config import get_config_manager

    status_logger = get_status_logger()

    # Get database path from config
    db_path = Path(get_config_manager().load_config().cache.db_path)

    if not db_path.exists():
        status_logger.info("Database does not exist yet (nothing to reset)")
        return

    if not confirm:
        status_logger.warning("⚠️  WARNING: This will DELETE ALL DATA in the database!")
        status_logger.info("A backup will be created before deletion.")
        click.confirm("\nAre you sure you want to reset the database?", abort=True)

    try:
        success = reset_database(db_path, confirm=True)
        if success:
            sys.exit(0)
        else:
            sys.exit(1)
    except Exception as e:
        status_logger.error(f"Reset failed: {e}")
        sys.exit(1)


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
