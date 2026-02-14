# SPDX-License-Identifier: MIT
"""Command-line interface for the journal assessment tool."""

import asyncio
import functools
import json
import re
import sys
import traceback
from collections.abc import Callable
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, TypeVar
from urllib.parse import urlparse

import aiohttp
import click

from . import __version__
from .batch_assessor import BibtexBatchAssessor
from .cache import AcronymCache, AssessmentCache, RetractionCache
from .cache.schema import SchemaVersionError
from .config import get_config_manager
from .constants import DEFAULT_ACRONYM_CONFIDENCE_MIN
from .dispatcher import query_dispatcher
from .enums import AssessmentType
from .logging_config import get_status_logger, setup_logging
from .models import AssessmentResult, CandidateAssessment, QueryInput, VenueType
from .normalizer import are_conference_names_equivalent, input_normalizer
from .output_formatter import output_formatter
from .utils.dead_code import code_is_used


LARGE_SYNC_BACKENDS: frozenset[str] = frozenset({"dblp_venues"})
ISSN_RESOLUTION_TIMEOUT_SECONDS: int = 8
ISSN_MIN_TOKEN_OVERLAP: float = 0.5
GITHUB_HTTP_TIMEOUT_SECONDS: int = 120
GITHUB_ALLOWED_HOSTS: set[str] = {
    "api.github.com",
    "github.com",
    "objects.githubusercontent.com",
    "raw.githubusercontent.com",
    "release-assets.githubusercontent.com",
}
CROSSREF_ALLOWED_HOSTS: set[str] = {"api.crossref.org"}


# Import cache_sync last: instantiation at module level may raise SchemaVersionError
# if the database schema is outdated. Caught here for a clean error message.
_startup_error: SchemaVersionError | None = None
try:
    from .cache_sync import cache_sync_manager  # noqa: E402
except SchemaVersionError as _e:
    _startup_error = _e
    cache_sync_manager = None  # type: ignore[assignment]


F = TypeVar("F", bound=Callable[..., Any])


def _is_allowed_host(host: str, allowed_hosts: set[str]) -> bool:
    """Check whether a host is in the allowlist (exact or subdomain)."""
    normalized = host.lower().strip()
    if not normalized:
        return False
    return any(
        normalized == allowed or normalized.endswith(f".{allowed}")
        for allowed in allowed_hosts
    )


def _validate_https_url(url: str, allowed_hosts: set[str]) -> None:
    """Validate URL scheme/host against strict HTTPS allowlist."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https":
        raise ValueError(f"Only https URLs are allowed: {url}")
    if not _is_allowed_host(host, allowed_hosts):
        raise ValueError(f"Host not allowed: {host}")


async def _fetch_https_text(
    url: str, timeout_seconds: int, allowed_hosts: set[str]
) -> str:
    """Fetch text over HTTPS with host allowlist + redirect host verification."""
    _validate_https_url(url, allowed_hosts)

    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, allow_redirects=True) as response:
            response.raise_for_status()
            final_host = (response.url.host or "").lower()
            if not _is_allowed_host(final_host, allowed_hosts):
                raise ValueError(f"Redirected to disallowed host: {final_host}")
            return await response.text()


async def _fetch_https_json(
    url: str, timeout_seconds: int, allowed_hosts: set[str]
) -> dict[str, Any] | list[Any]:
    """Fetch JSON over HTTPS with strict URL/host checks."""
    text = await _fetch_https_text(url, timeout_seconds, allowed_hosts)
    data = json.loads(text)
    if not isinstance(data, (dict, list)):
        raise ValueError("Expected JSON object or list")
    return data


async def _resolve_issn_title(issn: str) -> str | None:
    """Resolve ISSN to title via Crossref journals endpoint."""
    try:
        payload = await _fetch_https_json(
            f"https://api.crossref.org/journals/{issn}",
            ISSN_RESOLUTION_TIMEOUT_SECONDS,
            CROSSREF_ALLOWED_HOSTS,
        )
        if not isinstance(payload, dict):
            return None
        message = payload.get("message", {})
        if isinstance(message, dict):
            title = message.get("title")
            if isinstance(title, str) and title.strip():
                return title.strip()
    except (aiohttp.ClientError, json.JSONDecodeError, ValueError, OSError):
        return None
    return None


def _token_overlap(left: str, right: str) -> float:
    """Compute token overlap ratio using the shorter token set as denominator."""
    left_tokens = set(re.findall(r"[a-z0-9]+", left.lower()))
    right_tokens = set(re.findall(r"[a-z0-9]+", right.lower()))
    if not left_tokens or not right_tokens:
        return 0.0
    overlap = left_tokens.intersection(right_tokens)
    return len(overlap) / min(len(left_tokens), len(right_tokens))


def _issn_title_matches_expected(
    resolved_title: str, expected_name: str, venue_type: VenueType
) -> bool:
    """Check whether resolved ISSN title is consistent with expected venue name."""
    if venue_type == VenueType.CONFERENCE:
        if are_conference_names_equivalent(resolved_title, expected_name):
            return True
    return _token_overlap(resolved_title, expected_name) >= ISSN_MIN_TOKEN_OVERLAP


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

    # Fail cleanly if the database schema was incompatible at startup
    if _startup_error is not None:
        status_logger.error(str(_startup_error))
        sys.exit(1)

    # Initialize config manager with custom path if provided
    if config:
        detail_logger.debug(f"Using config file: {config}")
        get_config_manager(config, force_reload=True)


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
    default=DEFAULT_ACRONYM_CONFIDENCE_MIN,
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
    """Assess whether a journal is predatory or legitimate.

    Args:
        journal_name: The name of the journal to assess.
        verbose: Whether to enable verbose output.
        no_acronyms: Disable acronym/abbreviation/ISSN expansions.
        confidence_min: Minimum confidence score for acronym expansions.
        output_format: The format of the output (text or json).
    """
    asyncio.run(
        _async_assess_publication(
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
    default=DEFAULT_ACRONYM_CONFIDENCE_MIN,
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
    """Assess whether a conference is predatory or legitimate.

    Args:
        conference_name: The name of the conference to assess.
        verbose: Whether to enable verbose output.
        no_acronyms: Disable acronym/abbreviation/ISSN expansions.
        confidence_min: Minimum confidence score for acronym expansions.
        output_format: The format of the output (text or json).
    """
    asyncio.run(
        _async_assess_publication(
            conference_name,
            "conference",
            verbose,
            output_format,
            use_acronyms=not no_acronyms,
            confidence_min=confidence_min,
        )
    )


@main.command()
@handle_cli_errors
def config() -> None:
    """Show the complete current configuration."""
    config_output = get_config_manager().show_config()
    print(config_output)


@main.command()
@click.option("--force", is_flag=True, help="Force sync even if data appears fresh")
@click.option(
    "--include-large-datasets",
    is_flag=True,
    help=(
        "Include large datasets in default sync. "
        f"Currently: {', '.join(sorted(LARGE_SYNC_BACKENDS))}"
    ),
)
@click.argument("backend_names", nargs=-1, required=False)
def sync(
    force: bool, include_large_datasets: bool, backend_names: tuple[str, ...]
) -> None:
    """Manually sync cache with backend configuration.

    Optionally specify one or more backend names to sync only those backends.
    Examples:
      aletheia-probe sync              # Sync all backends
      aletheia-probe sync --include-large-datasets  # Include large datasets
      aletheia-probe sync scopus       # Sync only scopus
      aletheia-probe sync bealls doaj  # Sync only bealls and doaj

    Args:
        force: Whether to force sync even if data appears fresh.
        include_large_datasets: Whether to include large datasets in default sync.
        backend_names: Optional tuple of backend names to sync.
    """
    # Auto-register custom lists before sync
    from .cache.custom_list_manager import auto_register_custom_lists

    auto_register_custom_lists()
    backend_filter: list[str] | None = None
    if backend_names:
        backend_filter = list(backend_names)
    elif not include_large_datasets:
        from .backends.base import get_backend_registry

        backend_filter = [
            backend_name
            for backend_name in get_backend_registry().get_backend_names()
            if backend_name not in LARGE_SYNC_BACKENDS
        ]

    try:
        # The cache_sync_manager handles all output through the dual logger
        result = asyncio.run(
            cache_sync_manager.sync_cache_with_config(
                force=force,
                backend_filter=backend_filter,
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
    """Show venue acronym database status (counts by entity type)."""
    status_logger = get_status_logger()

    acronym_cache = AcronymCache()
    stats = acronym_cache.get_full_stats()

    status_logger.info("Venue Acronym Database Status")
    status_logger.info("=" * 44)

    if stats["total_acronyms"] == 0:
        status_logger.info(
            "Database is empty — run 'acronym import' or 'acronym sync' to load data"
        )
        return

    status_logger.info(f"Acronyms : {stats['total_acronyms']:>8,}")
    status_logger.info(f"Variants : {stats['total_variants']:>8,}")
    status_logger.info(f"ISSNs    : {stats['total_issns']:>8,}")

    if stats["by_entity_type"]:
        status_logger.info("")
        status_logger.info(
            f"{'Entity type':<16}  {'Acronyms':>9}  {'Variants':>9}  {'ISSNs':>7}"
        )
        status_logger.info("-" * 44)
        for row in stats["by_entity_type"]:
            status_logger.info(
                f"{row['entity_type']:<16}  {row['acronyms']:>9,}"
                f"  {row['variants']:>9,}  {row['issns']:>7,}"
            )


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
    """Import acronyms from a venue-acronyms-2025 pipeline JSON file.

    Accepts the v2.0 pipeline output format: a JSON object with an ``acronyms``
    key containing a list of entries, each with ``acronym``, ``entity_type``,
    ``canonical``, ``confidence_score``, ``issn`` (list), and ``variants`` (list).
    A plain JSON list of entries is also accepted for compatibility.

    Entries missing ``acronym``, ``entity_type``, or ``canonical`` are skipped.

    Args:
        input_file: Path to the pipeline output JSON file.
        merge: Whether to merge with existing data (default) or replace.
        source: Optional source label stored with each imported entry.
    """
    status_logger = get_status_logger()
    acronym_cache = AcronymCache()

    try:
        with open(input_file, encoding="utf-8") as f:
            data = json.load(f)

        # Accept both list and dict (v2.0) formats
        if isinstance(data, list):
            entries = data
        elif isinstance(data, dict):
            entries = data.get("acronyms", [])
        else:
            raise ValueError("Input file must contain a JSON list or object")

        status_logger.info(f"Loaded {len(entries)} entries from {input_file}")

        if not merge:
            if click.confirm(
                "This will clear existing data before importing. Continue?",
                abort=True,
            ):
                acronym_cache.clear_acronym_database()

        source_file = source or Path(input_file).name
        count = acronym_cache.import_acronyms(entries, source_file=source_file)

        status_logger.info(f"Successfully imported {count} acronym entries")

    except Exception as e:
        status_logger.error(f"Failed to import dataset: {e}")
        raise click.ClickException(str(e)) from e


def _get_latest_acronym_dataset_url(repo: str) -> tuple[str, str]:
    """Get dataset download URL and source label from latest GitHub release.

    Args:
        repo: GitHub repository in owner/name format.

    Returns:
        Tuple of (download_url, source_label).

    Raises:
        ValueError: If repo format is invalid or dataset asset is missing.
    """
    if "/" not in repo:
        raise ValueError("Repository must be in 'owner/name' format")

    api_url = f"https://api.github.com/repos/{repo}/releases/latest"
    payload = asyncio.run(
        _fetch_https_json(api_url, GITHUB_HTTP_TIMEOUT_SECONDS, GITHUB_ALLOWED_HOSTS)
    )
    if not isinstance(payload, dict):
        raise ValueError("Unexpected GitHub releases response format")
    release_data = payload

    assets = release_data.get("assets", [])
    for asset in assets:
        name = str(asset.get("name", ""))
        if name.endswith(".json") and "venue-acronyms-2025-curated" in name:
            return str(asset["browser_download_url"]), name

    raise ValueError("Latest release does not contain venue-acronyms JSON asset")


@acronym.command(name="sync")
@click.option(
    "--repo",
    default="sustainet-guardian/venue-acronyms-2025",
    show_default=True,
    help="GitHub repository in owner/name format",
)
@click.option(
    "--merge/--no-merge",
    default=True,
    help="Merge with existing data (default) or replace",
)
@click.option(
    "--source",
    default=None,
    help="Override source label stored with each imported entry",
)
@handle_cli_errors
def sync_acronyms(repo: str, merge: bool, source: str | None) -> None:
    """Download latest venue-acronyms dataset from GitHub and import it."""
    status_logger = get_status_logger()
    acronym_cache = AcronymCache()

    try:
        dataset_url, asset_name = _get_latest_acronym_dataset_url(repo)
        status_logger.info(f"Downloading dataset from {dataset_url}")

        payload_data = asyncio.run(
            _fetch_https_json(
                dataset_url,
                GITHUB_HTTP_TIMEOUT_SECONDS,
                GITHUB_ALLOWED_HOSTS,
            )
        )

        with NamedTemporaryFile("w", suffix=".json", encoding="utf-8") as tmp_file:
            tmp_file.write(json.dumps(payload_data))
            tmp_file.flush()

            with open(tmp_file.name, encoding="utf-8") as f:
                data = json.load(f)

        entries = data.get("acronyms", []) if isinstance(data, dict) else data
        if not isinstance(entries, list):
            raise ValueError("Downloaded dataset has invalid format")

        status_logger.info(f"Loaded {len(entries)} entries from latest release")

        if not merge:
            if click.confirm(
                "This will clear existing data before importing. Continue?",
                abort=True,
            ):
                acronym_cache.clear_acronym_database()

        source_file = source or asset_name
        count = acronym_cache.import_acronyms(entries, source_file=source_file)
        status_logger.info(f"Successfully imported {count} acronym entries")

    except aiohttp.ClientError as e:
        status_logger.error(f"Failed to download dataset: {e}")
        raise click.ClickException(str(e)) from e
    except Exception as e:
        status_logger.error(f"Failed to sync acronym dataset: {e}")
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
        status_logger.info(f"Current code requires: schema version {SCHEMA_VERSION}")
        status_logger.info("\nDelete the database and run sync again:")
        status_logger.info(f"  rm {db_path}")
        status_logger.info("  aletheia-probe sync")
    elif current_version < SCHEMA_VERSION:
        status_logger.warning(f"⚠️  Database schema version: {current_version}")
        status_logger.info(f"Current code requires: version {SCHEMA_VERSION}")
        status_logger.info("\nDelete the database and run sync again:")
        status_logger.info(f"  rm {db_path}")
        status_logger.info("  aletheia-probe sync")
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
    publication_name: str,
    publication_type: str,
    verbose: bool,
    output_format: str,
    use_acronyms: bool = True,
    confidence_min: float = DEFAULT_ACRONYM_CONFIDENCE_MIN,
) -> None:
    """Async function for assessing publications with type specification.

    Args:
        publication_name: The name of the publication to assess.
        publication_type: The type of publication (journal or conference).
        verbose: Whether to enable verbose output.
        output_format: The format of the output (text or json).
        use_acronyms: Whether to use acronym/variant/ISSN expansion candidates.
        confidence_min: Minimum acronym dataset confidence score for expansions.
    """
    status_logger = get_status_logger()
    acronym_cache = AcronymCache()

    try:
        requested_venue_type = (
            VenueType.CONFERENCE
            if publication_type == "conference"
            else VenueType.JOURNAL
        )

        def acronym_lookup_for_type(acronym: str) -> str | None:
            if not use_acronyms:
                return None
            return acronym_cache.get_full_name_for_acronym(
                acronym,
                requested_venue_type.value,
                min_confidence=confidence_min,
            )

        # Candidate 1: user-provided input exactly as entered
        base_query = input_normalizer.normalize(publication_name)
        base_query.venue_type = requested_venue_type

        normalized_name = (
            base_query.normalized_name
            if isinstance(base_query.normalized_name, str)
            else None
        )
        aliases = base_query.aliases if isinstance(base_query.aliases, list) else []
        identifiers = (
            base_query.identifiers if isinstance(base_query.identifiers, dict) else {}
        )

        candidates: list[tuple[str, QueryInput]] = [("input", base_query)]
        candidate_names_seen: set[str] = {publication_name.strip().lower()}
        issn_validation_notes: list[str] = []

        async def add_issn_candidates(
            acronym: str, source_label: str, expected_name: str
        ) -> None:
            """Add ISSN-based candidates for an acronym entry."""
            issns = acronym_cache.get_issns(
                acronym,
                requested_venue_type.value,
                min_confidence=confidence_min,
            )
            for issn in issns:
                if issn.lower() in candidate_names_seen:
                    continue
                resolved_title = await _resolve_issn_title(issn)
                if not resolved_title:
                    note = f"Skipped ISSN {issn}: unable to resolve title from Crossref"
                    issn_validation_notes.append(note)
                    continue
                if not _issn_title_matches_expected(
                    resolved_title, expected_name, requested_venue_type
                ):
                    note = (
                        f"Skipped ISSN {issn}: resolves to '{resolved_title}', "
                        f"does not match '{expected_name}'"
                    )
                    issn_validation_notes.append(note)
                    continue

                issn_validation_notes.append(
                    f"Accepted ISSN {issn}: resolves to '{resolved_title}'"
                )
                issn_query = input_normalizer.normalize(
                    issn, acronym_lookup=acronym_lookup_for_type
                )
                issn_query.venue_type = requested_venue_type
                issn_query.acronym_expanded_from = raw_input
                candidates.append((f"{source_label}->issn", issn_query))
                candidate_names_seen.add(issn.lower())

        # Candidates 2-N: acronym/variant/ISSN expansions (optional)
        if use_acronyms:
            raw_input = publication_name.strip()
            variant_inputs = [raw_input]
            if normalized_name:
                variant_inputs.append(normalized_name)
            variant_inputs.extend(aliases[:10])  # keep bounded

            # (2) Standalone acronym -> canonical full name
            if input_normalizer._is_standalone_acronym(raw_input) is True:
                expanded = acronym_cache.get_full_name_for_acronym(
                    raw_input,
                    requested_venue_type.value,
                    min_confidence=confidence_min,
                )
                if expanded and expanded.lower() not in candidate_names_seen:
                    expanded_query = input_normalizer.normalize(
                        expanded, acronym_lookup=acronym_lookup_for_type
                    )
                    expanded_query.venue_type = requested_venue_type
                    expanded_query.acronym_expanded_from = raw_input
                    candidates.append(("acronym->full", expanded_query))
                    candidate_names_seen.add(expanded.lower())
                    await add_issn_candidates(raw_input, "acronym", expanded)

            # (3) Abbreviation/variant -> acronym and canonical
            for variant in variant_inputs:
                match = acronym_cache.get_variant_match(
                    variant,
                    requested_venue_type.value,
                    min_confidence=confidence_min,
                )
                if not match:
                    continue

                canonical = str(match["canonical"])
                acronym = str(match["acronym"])

                if canonical.lower() not in candidate_names_seen:
                    canonical_query = input_normalizer.normalize(
                        canonical, acronym_lookup=acronym_lookup_for_type
                    )
                    canonical_query.venue_type = requested_venue_type
                    canonical_query.acronym_expanded_from = raw_input
                    candidates.append(("variant->full", canonical_query))
                    candidate_names_seen.add(canonical.lower())

                if acronym.lower() not in candidate_names_seen:
                    acronym_query = input_normalizer.normalize(
                        acronym, acronym_lookup=acronym_lookup_for_type
                    )
                    acronym_query.venue_type = requested_venue_type
                    acronym_query.acronym_expanded_from = raw_input
                    candidates.append(("variant->acronym", acronym_query))
                    candidate_names_seen.add(acronym.lower())

                await add_issn_candidates(acronym, "variant", canonical)

            # (4) ISSN -> acronym and canonical (if ISSN present in input)
            issn = identifiers.get("issn")
            if issn:
                issn_match = acronym_cache.get_issn_match(
                    issn, min_confidence=confidence_min
                )
                if issn_match:
                    canonical = str(issn_match["canonical"])
                    acronym = str(issn_match["acronym"])

                    if canonical.lower() not in candidate_names_seen:
                        canonical_query = input_normalizer.normalize(
                            canonical, acronym_lookup=acronym_lookup_for_type
                        )
                        canonical_query.venue_type = requested_venue_type
                        canonical_query.acronym_expanded_from = raw_input
                        candidates.append(("issn->full", canonical_query))
                        candidate_names_seen.add(canonical.lower())

                    if acronym.lower() not in candidate_names_seen:
                        acronym_query = input_normalizer.normalize(
                            acronym, acronym_lookup=acronym_lookup_for_type
                        )
                        acronym_query.venue_type = requested_venue_type
                        acronym_query.acronym_expanded_from = raw_input
                        candidates.append(("issn->acronym", acronym_query))
                        candidate_names_seen.add(acronym.lower())

        # Persist learned mappings from all candidate queries
        for _, query_input in candidates:
            for acronym, full_name in query_input.extracted_acronym_mappings.items():
                acronym_cache.store_acronym_mapping(
                    acronym,
                    full_name,
                    query_input.venue_type.value,
                    source="user_input",
                )

        if verbose:
            status_logger.info(f"Publication type: {publication_type}")
            status_logger.info(f"Normalized input: {normalized_name}")
            if identifiers:
                status_logger.info(f"Identifiers: {identifiers}")

        if use_acronyms and len(candidates) > 1:
            status_logger.info(
                f"Acronym workflow enabled (confidence_min={confidence_min:.2f}): "
                f"trying {len(candidates)} candidates"
            )
            for label, candidate in candidates:
                status_logger.info(f"  - {label}: {candidate.raw_input}")

        # Assess all candidates and keep the strongest outcome
        assessed_candidates: list[tuple[str, AssessmentResult, str]] = []
        for label, query_input in candidates:
            candidate_result = await query_dispatcher.assess_journal(query_input)
            assessed_candidates.append((label, candidate_result, query_input.raw_input))

        # Choose best by confidence (tie-breaker: higher overall score)
        best_label, result, best_query_text = max(
            assessed_candidates,
            key=lambda item: (item[1].confidence, item[1].overall_score),
        )
        result.candidate_assessments = [
            CandidateAssessment(
                label=label,
                query=query_text,
                assessment=candidate_result.assessment,
                confidence=candidate_result.confidence,
                overall_score=candidate_result.overall_score,
                selected=(label == best_label and query_text == best_query_text),
            )
            for label, candidate_result, query_text in assessed_candidates
        ]
        # Always display the original user query in output header
        result.input_query = publication_name.strip()

        if use_acronyms and len(assessed_candidates) > 1:
            result.reasoning.insert(
                0,
                f"Acronym workflow: tried {len(assessed_candidates)} candidate forms; "
                f"selected '{best_query_text}' ({best_label})",
            )
        if issn_validation_notes:
            result.reasoning.extend(
                [f"ISSN validation: {n}" for n in issn_validation_notes]
            )

        if best_label != "input":
            result.acronym_expansion_used = True
            if not result.acronym_expanded_from:
                if input_normalizer._is_standalone_acronym(best_query_text) is True:
                    result.acronym_expanded_from = best_query_text
                else:
                    result.acronym_expanded_from = publication_name.strip()

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
