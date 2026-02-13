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
from .logging_config import get_status_logger, setup_logging
from .normalizer import input_normalizer
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
@handle_cli_errors
def import_acronyms(input_file: str, merge: bool, source: str | None) -> None:
    """Import acronyms from a JSON file.

    Supports the venue-acronyms-2025 consensus format (plain list with
    original_name and confidence_score), the unified dataset format
    (dict with 'acronyms' key), and the legacy list-only format.

    Entries with a null normalized_name are skipped automatically.
    is_canonical and is_ambiguous are computed from the imported batch.

    Args:
        input_file: Path to the input JSON file.
        merge: Whether to merge with existing data.
        source: Optional source label for imported entries.
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
            variants = data
            status_logger.info(f"Detected list format with {len(variants)} variants")
        elif isinstance(data, dict):
            variants = data.get("acronyms", [])
            abbreviations = data.get("abbreviations", [])
            status_logger.info(
                f"Detected dict format with {len(variants)} variants and "
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

        # Determine default source: use --source flag, or detect from file content
        default_source = source
        if default_source is None:
            # venue-acronyms-2025 consensus format has confidence_score but no source
            first = variants[0] if variants else {}
            if "confidence_score" in first and "source" not in first:
                default_source = "venue-acronyms-2025"
            else:
                default_source = "import"

        variant_count = acronym_cache.import_variants(
            variants, merge=True, default_source=default_source
        )

        status_logger.info(f"Successfully imported {variant_count} acronym variants")

    except Exception as e:
        status_logger.error(f"Failed to import dataset: {e}")
        raise click.ClickException(str(e)) from e


@acronym.command()
@click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
@handle_cli_errors
def clear(confirm: bool) -> None:
    """Clear all entries from the acronym database."""
    status_logger = get_status_logger()

    if not confirm:
        click.confirm("This will delete all acronym mappings. Continue?", abort=True)

    acronym_cache = AcronymCache()
    count = acronym_cache.clear_acronym_database()

    if count == 0:
        status_logger.info("Acronym database is already empty.")
    else:
        status_logger.info(f"Cleared {count:,} acronym mapping(s).")



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
