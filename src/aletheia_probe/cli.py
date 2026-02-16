# SPDX-License-Identifier: MIT
"""Command-line interface for the journal assessment tool."""

import asyncio
import functools
import json
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
from .cache import AcronymCache, AssessmentCache, OpenAlexCache, RetractionCache
from .cache.schema import SchemaVersionError
from .config import get_config_manager
from .constants import DEFAULT_ACRONYM_CONFIDENCE_MIN
from .dispatcher import query_dispatcher
from .enums import AssessmentType
from .logging_config import get_status_logger, setup_logging
from .lookup import (
    LookupCandidate,
    LookupResult,
    LookupValidation,
    VenueLookupService,
)
from .models import VenueType
from .normalizer import input_normalizer
from .openalex import OpenAlexClient
from .output_formatter import output_formatter
from .publication_assessment_workflow import (
    assess_candidates as workflow_assess_candidates,
)
from .publication_assessment_workflow import (
    build_publication_candidates as workflow_build_publication_candidates,
)
from .publication_assessment_workflow import (
    finalize_publication_result as workflow_finalize_publication_result,
)
from .publication_assessment_workflow import (
    persist_candidate_mappings as workflow_persist_candidate_mappings,
)
from .publication_assessment_workflow import (
    resolve_candidate_selection as workflow_resolve_candidate_selection,
)
from .utils.dead_code import code_is_used
from .validation import validate_issn


LARGE_SYNC_BACKENDS: frozenset[str] = frozenset({"dblp_venues"})
ISSN_RESOLUTION_TIMEOUT_SECONDS: int = 8
GITHUB_HTTP_TIMEOUT_SECONDS: int = 120
GITHUB_ALLOWED_HOSTS: set[str] = {
    "api.github.com",
    "github.com",
    "objects.githubusercontent.com",
    "raw.githubusercontent.com",
    "release-assets.githubusercontent.com",
}
CROSSREF_ALLOWED_HOSTS: set[str] = {"api.crossref.org"}
GENERIC_RESOLVED_TITLES: set[str] = {"proceedings", "journal", "conference"}


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


@main.group(name="lookup")
def lookup() -> None:
    """Look up normalized venue candidates and known identifiers."""
    pass


@lookup.command(name="journal")
@click.argument("journal_name")
@click.option(
    "--confidence-min",
    default=DEFAULT_ACRONYM_CONFIDENCE_MIN,
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
@handle_cli_errors
def lookup_journal(
    journal_name: str,
    confidence_min: float,
    output_format: str,
    online: bool,
) -> None:
    """Look up normalized forms and identifiers for a journal input."""
    _run_lookup_cli(
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
    default=DEFAULT_ACRONYM_CONFIDENCE_MIN,
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
@handle_cli_errors
def lookup_conference(
    conference_name: str,
    confidence_min: float,
    output_format: str,
    online: bool,
) -> None:
    """Look up normalized forms and identifiers for a conference input."""
    _run_lookup_cli(
        conference_name,
        VenueType.CONFERENCE,
        output_format,
        confidence_min,
        online=online,
    )


def _run_lookup_cli(
    publication_name: str,
    venue_type: VenueType,
    output_format: str,
    confidence_min: float,
    online: bool = True,
) -> None:
    """Run lookup and print results in the requested format."""
    service = VenueLookupService()
    result = service.lookup(
        publication_name, venue_type=venue_type, confidence_min=confidence_min
    )
    if online:
        asyncio.run(_enrich_lookup_result_online(result))
    _enforce_lookup_input_consistency(result)

    if output_format == "json":
        print(json.dumps(result.to_dict(), indent=2))
        return

    print(_format_lookup_result_text(result))


async def _enrich_lookup_result_online(result: LookupResult) -> None:
    """Enrich lookup result with OpenAlex/Crossref and validate name-ISSN consistency."""
    names = {
        _normalize_lookup_name(name)
        for name in ([result.normalized_name] + result.normalized_names)
        if name
    }
    names.discard("")

    issns = {i for i in (result.issns + result.eissns) if i}
    input_issn = result.identifiers.get("issn")
    if input_issn:
        issns.add(input_issn)
    input_eissn = result.identifiers.get("eissn")
    if input_eissn:
        issns.add(input_eissn)

    await _enrich_from_openalex(
        result,
        names,
        issns,
        has_input_identifiers=bool(result.identifiers),
    )
    await _enrich_from_crossref(result, names, issns)


async def _enrich_from_openalex(
    result: LookupResult,
    names: set[str],
    issns: set[str],
    has_input_identifiers: bool,
) -> None:
    """Enrich result with OpenAlex name/ISSN lookups."""
    try:
        async with OpenAlexClient() as client:
            for name in sorted(names)[:5]:
                source = await client.get_source_by_name(name)
                _check_name_identifier_consistency_from_openalex(
                    result=result,
                    expected_name=name,
                    source=source,
                )
                _apply_openalex_source(
                    result=result,
                    source=source,
                    names=names,
                    issns=issns,
                    validation_identifier=name,
                    source_label="openalex_name_lookup",
                    expected_name=name,
                    allow_enrichment=not has_input_identifiers,
                )

            for issn in sorted(issns):
                source = await client.get_source_by_issn(issn)
                _apply_openalex_source(
                    result=result,
                    source=source,
                    names=names,
                    issns=issns,
                    validation_identifier=issn,
                    source_label="openalex_issn_lookup",
                    expected_name=None,
                    allow_enrichment=True,
                )
    except Exception as e:
        result.validations.append(
            LookupValidation(
                source="openalex",
                identifier="*",
                status="unverified",
                details=f"OpenAlex unavailable: {e}",
            )
        )


async def _enrich_from_crossref(
    result: LookupResult, names: set[str], issns: set[str]
) -> None:
    """Enrich result with Crossref ISSN lookups."""
    for issn in sorted(issns):
        resolved_title = await _resolve_issn_title(issn)
        if not resolved_title:
            result.validations.append(
                LookupValidation(
                    source="crossref",
                    identifier=issn,
                    status="unverified",
                    details="No title resolved from Crossref",
                )
            )
            continue

        normalized_resolved = _normalize_lookup_name(resolved_title)
        is_generic_resolved = _is_generic_resolved_name(normalized_resolved)
        if normalized_resolved and not is_generic_resolved:
            _append_lookup_candidate(
                result=result,
                source="crossref_issn_lookup",
                normalized_name=normalized_resolved,
                issn=issn,
            )
            result.normalized_names = sorted(
                set(result.normalized_names).union({normalized_resolved})
            )

        if is_generic_resolved:
            status, similarity, matched_name = "unverified", None, None
            details = f"Crossref resolved generic title '{resolved_title}'"
        else:
            status, similarity, matched_name = _compare_resolved_name(
                normalized_resolved,
                names,
                result.venue_type,
            )
            details = (
                f"Crossref resolved '{resolved_title}'"
                if status != "conflict"
                else (
                    f"Crossref resolved '{resolved_title}' which differs from "
                    f"'{matched_name or 'local names'}'"
                )
            )
        result.validations.append(
            LookupValidation(
                source="crossref",
                identifier=issn,
                status=status,
                input_name=matched_name,
                resolved_name=normalized_resolved or resolved_title,
                similarity=similarity,
                details=details,
            )
        )


def _apply_openalex_source(
    result: LookupResult,
    source: dict[str, Any] | None,
    names: set[str],
    issns: set[str],
    validation_identifier: str,
    source_label: str,
    expected_name: str | None,
    allow_enrichment: bool,
) -> None:
    """Apply one OpenAlex source payload to lookup result."""
    if not isinstance(source, dict):
        result.validations.append(
            LookupValidation(
                source="openalex",
                identifier=validation_identifier,
                status="unverified",
                details="No source resolved",
            )
        )
        return

    display_name = str(source.get("display_name") or "").strip()
    normalized_display = _normalize_lookup_name(display_name)
    openalex_type = str(source.get("type") or "").strip().lower()
    is_generic_resolved = _is_generic_resolved_name(normalized_display)
    is_exact_name_mismatch = (
        expected_name is not None
        and bool(normalized_display)
        and normalized_display != expected_name
    )

    if is_exact_name_mismatch:
        result.validations.append(
            LookupValidation(
                source="openalex",
                identifier=validation_identifier,
                status="unverified",
                input_name=expected_name,
                resolved_name=normalized_display,
                similarity=0.0,
                details=(
                    "OpenAlex name lookup returned a different title; "
                    "strict exact-title mode kept local value"
                ),
            )
        )
        return

    issn_pair = _extract_reliable_openalex_issn_pair(source)

    if allow_enrichment and normalized_display and not is_generic_resolved:
        _append_lookup_candidate(
            result=result,
            source=source_label,
            normalized_name=normalized_display,
            issn=issn_pair[0] if issn_pair else None,
            eissn=issn_pair[1] if issn_pair else None,
        )
        result.normalized_names = sorted(
            set(result.normalized_names).union({normalized_display})
        )

    if allow_enrichment and issn_pair:
        if issn_pair[0]:
            issns.add(issn_pair[0])
        if issn_pair[1]:
            issns.add(issn_pair[1])
        issn_values = set(result.issns)
        eissn_values = set(result.eissns)
        if issn_pair[0]:
            issn_values.add(issn_pair[0])
        if issn_pair[1]:
            eissn_values.add(issn_pair[1])
        result.issns = sorted(issn_values)
        result.eissns = sorted(eissn_values)

    if is_generic_resolved:
        status, similarity, matched_name = "unverified", None, None
    else:
        status, similarity, matched_name = _compare_resolved_name(
            normalized_display,
            names,
            result.venue_type,
        )
    if not is_generic_resolved and not _openalex_type_matches_requested_venue(
        openalex_type, result.venue_type
    ):
        status = "conflict"
    result.validations.append(
        LookupValidation(
            source="openalex",
            identifier=validation_identifier,
            status=status,
            input_name=matched_name,
            resolved_name=normalized_display or None,
            similarity=similarity,
            details=(
                f"OpenAlex resolved generic title '{display_name}'"
                if is_generic_resolved
                else (
                    f"Venue-type mismatch: requested {result.venue_type.value}, "
                    f"OpenAlex returned type={openalex_type or 'unknown'} for '{display_name}'"
                    if not _openalex_type_matches_requested_venue(
                        openalex_type, result.venue_type
                    )
                    else (
                        f"OpenAlex resolved '{display_name}' (type={openalex_type or 'unknown'})"
                        if display_name
                        else "OpenAlex returned source without display name"
                    )
                )
            ),
        )
    )


def _check_name_identifier_consistency_from_openalex(
    result: LookupResult,
    expected_name: str,
    source: dict[str, Any] | None,
) -> None:
    """Record strict mismatch when mixed input (name + identifier) disagrees."""
    if not result.identifiers:
        return
    if not isinstance(source, dict):
        return

    normalized_display = _normalize_lookup_name(str(source.get("display_name") or ""))
    if not normalized_display or normalized_display != expected_name:
        return

    issn_pair = _extract_reliable_openalex_issn_pair(source)
    if not issn_pair:
        return

    resolved_ids = {value for value in issn_pair if value}
    if not resolved_ids:
        return

    input_ids = {value for value in result.identifiers.values() if value}
    if not input_ids:
        return

    if input_ids.isdisjoint(resolved_ids):
        result.consistency_errors.append(
            "Input mismatch: provided identifier(s) "
            f"{sorted(input_ids)} do not match '{expected_name}' "
            f"(resolved identifiers: {sorted(resolved_ids)})"
        )


def _extract_reliable_openalex_issn_pair(
    source: dict[str, Any],
) -> tuple[str | None, str | None] | None:
    """Extract a reliable ISSN/eISSN pair from OpenAlex payload."""
    issn_l_raw = source.get("issn_l")
    issn_l = str(issn_l_raw).strip() if issn_l_raw else None
    if issn_l and not validate_issn(issn_l):
        issn_l = None

    issn_values = source.get("issn", [])
    candidates: list[str] = []
    if isinstance(issn_values, list):
        for value in issn_values:
            candidate = str(value).strip()
            if validate_issn(candidate):
                candidates.append(candidate)

    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate not in seen:
            deduped.append(candidate)
            seen.add(candidate)
    candidates = deduped

    if issn_l and issn_l not in seen:
        candidates.insert(0, issn_l)

    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0], None
    if issn_l:
        eissn = next((c for c in candidates if c != issn_l), None)
        return issn_l, eissn
    return candidates[0], candidates[1]


def _normalize_lookup_name(name: str | None) -> str:
    """Normalize venue name for lookup comparisons."""
    if not name:
        return ""
    normalized_query = input_normalizer.normalize(name)
    normalized = (
        normalized_query.normalized_venue.name
        if normalized_query.normalized_venue
        else ""
    )
    if not normalized:
        return ""
    return normalized.strip().lower()


def _compare_resolved_name(
    resolved_name: str,
    known_names: set[str],
    venue_type: VenueType,
) -> tuple[str, float | None, str | None]:
    """Compare resolved name with known names and classify agreement."""
    del venue_type
    if not resolved_name:
        return "unverified", None, None
    if not known_names:
        return "enriched", None, None

    normalized_resolved = _normalize_lookup_name(resolved_name)
    if not normalized_resolved:
        return "unverified", None, None

    if normalized_resolved in known_names:
        return "agree", 1.0, normalized_resolved

    best_match_name = sorted(known_names)[0]
    return "conflict", 0.0, best_match_name


def _enforce_lookup_input_consistency(result: LookupResult) -> None:
    """Fail lookup when mixed input name+identifier does not resolve consistently."""
    primary_name = _normalize_lookup_name(result.normalized_name)
    input_ids = {value for value in result.identifiers.values() if value}
    if not primary_name or not input_ids:
        return

    matching_name_ids: set[str] = set()
    for candidate in result.candidates:
        if _normalize_lookup_name(candidate.normalized_name) != primary_name:
            continue
        if candidate.issn:
            matching_name_ids.add(candidate.issn)
        if candidate.eissn:
            matching_name_ids.add(candidate.eissn)

    if matching_name_ids and input_ids.isdisjoint(matching_name_ids):
        result.consistency_errors.append(
            "Input mismatch: provided identifier(s) "
            f"{sorted(input_ids)} do not match '{primary_name}' "
            f"(resolved identifiers: {sorted(matching_name_ids)})"
        )

    if result.consistency_errors:
        unique_errors = sorted(set(result.consistency_errors))
        raise click.ClickException(" ; ".join(unique_errors))


def _openalex_type_matches_requested_venue(
    openalex_type: str, requested_venue_type: VenueType
) -> bool:
    """Check whether OpenAlex source type is compatible with requested venue type."""
    if not openalex_type:
        return True

    if requested_venue_type == VenueType.JOURNAL and openalex_type == "journal":
        return True
    if requested_venue_type == VenueType.CONFERENCE and openalex_type == "conference":
        return True

    return False


def _is_generic_resolved_name(normalized_name: str) -> bool:
    """Return True if resolved title is too generic to trust as canonical."""
    return normalized_name in GENERIC_RESOLVED_TITLES


def _append_lookup_candidate(
    result: LookupResult,
    source: str,
    normalized_name: str,
    confidence: float | None = None,
    acronym: str | None = None,
    issn: str | None = None,
    eissn: str | None = None,
) -> None:
    """Append candidate if equivalent entry is not already present."""
    candidate_key = (source, normalized_name, issn, eissn)
    existing_keys = {
        (c.source, c.normalized_name, c.issn, c.eissn) for c in result.candidates
    }
    if candidate_key in existing_keys:
        return
    result.candidates.append(
        LookupCandidate(
            source=source,
            normalized_name=normalized_name,
            confidence=confidence,
            acronym=acronym,
            issn=issn,
            eissn=eissn,
        )
    )


def _format_lookup_result_text(result: LookupResult) -> str:
    """Format lookup results for human-readable CLI output."""
    lines = [
        f"Lookup: {result.raw_input}",
        f"Venue Type: {result.venue_type.value}",
        f"Primary Normalized Name: {result.normalized_name or '-'}",
        f"ISSN Checksum Valid: {'yes' if result.issn_valid else 'no'}",
        "",
        "Normalized Names:",
    ]

    if result.normalized_names:
        for name in result.normalized_names:
            lines.append(f"- {name}")
    else:
        lines.append("- (none)")

    lines.extend(["", "Identifiers:"])
    lines.append(f"- input identifiers: {result.identifiers or {}}")
    lines.append(f"- issns: {result.issns or []}")
    lines.append(f"- eissns: {result.eissns or []}")

    lines.extend(["", "Candidates:"])
    if not result.candidates:
        lines.append("- (none)")
        return "\n".join(lines)

    for candidate in result.candidates:
        candidate_line = f"- {candidate.source}: {candidate.normalized_name}"
        details: list[str] = []
        if candidate.acronym:
            details.append(f"acronym={candidate.acronym}")
        if candidate.confidence is not None:
            details.append(f"confidence={candidate.confidence:.2f}")
        if candidate.issn:
            details.append(f"issn={candidate.issn}")
        if candidate.eissn:
            details.append(f"eissn={candidate.eissn}")
        if details:
            candidate_line += f" ({', '.join(details)})"
        lines.append(candidate_line)

    lines.extend(["", "Validations:"])
    if not result.validations:
        lines.append("- (none)")
        return "\n".join(lines)

    for validation in result.validations:
        validation_line = (
            f"- {validation.source} [{validation.status}] {validation.identifier}"
        )
        details = []
        if validation.resolved_name:
            details.append(f"resolved={validation.resolved_name}")
        if validation.input_name:
            details.append(f"input={validation.input_name}")
        if validation.similarity is not None:
            details.append(f"similarity={validation.similarity:.2f}")
        if validation.details:
            details.append(validation.details)
        if details:
            validation_line += f" ({'; '.join(details)})"
        lines.append(validation_line)

    return "\n".join(lines)


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
    # Local import avoids circular dependency with backend registry initialization.
    from .cache.custom_list_manager import auto_register_custom_lists

    auto_register_custom_lists()
    backend_filter: list[str] | None = None
    if backend_names:
        backend_filter = list(backend_names)
    elif not include_large_datasets:
        # Local import avoids circular dependency with backend registry initialization.
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
    """Clear volatile assessment-related caches.

    This removes cached assessment results and cached OpenAlex analyzer data,
    forcing fresh API-backed analysis on next assessment.

    Args:
        confirm: Whether to skip the confirmation prompt.
    """
    status_logger = get_status_logger()

    if not confirm:
        click.confirm(
            "This will clear assessment and OpenAlex caches. Continue?", abort=True
        )

    assessment_cache = AssessmentCache()
    openalex_cache = OpenAlexCache()

    # Get count before clearing
    assessment_count = assessment_cache.get_assessment_cache_count()
    openalex_count = openalex_cache.get_openalex_cache_count()

    if assessment_count == 0 and openalex_count == 0:
        status_logger.info("Caches are already empty.")
        return

    cleared_assessment = assessment_cache.clear_assessment_cache()
    cleared_openalex = openalex_cache.clear_openalex_cache()

    status_logger.info(
        f"Cleared {cleared_assessment} assessment cache entries and "
        f"{cleared_openalex} OpenAlex cache entries."
    )


@main.command()
@handle_cli_errors
def status() -> None:
    """Show cache synchronization status for all backends."""
    # Auto-register custom lists before showing status
    # Local import avoids circular dependency with backend registry initialization.
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
    # Local imports defer schema/config tooling until maintenance command execution.
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
    # Local imports defer migration/schema/config tooling to maintenance commands.
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
    # Local imports defer migration/config tooling to maintenance commands.
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
    # Local import avoids circular dependency with backend registry initialization.
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
    # Local import avoids circular dependency with backend registry initialization.
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
    # Local import avoids circular dependency with backend registry initialization.
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
        candidate_build_result = await workflow_build_publication_candidates(
            publication_name=publication_name,
            requested_venue_type=requested_venue_type,
            acronym_cache=acronym_cache,
            use_acronyms=use_acronyms,
            confidence_min=confidence_min,
            input_normalizer=input_normalizer,
            resolve_issn_title=_resolve_issn_title,
        )
        candidates = candidate_build_result.candidates

        workflow_persist_candidate_mappings(candidates, acronym_cache)

        if verbose:
            status_logger.info(f"Publication type: {publication_type}")
            status_logger.info(
                f"Normalized input: {candidate_build_result.normalized_name}"
            )
            if candidate_build_result.identifiers:
                status_logger.info(f"Identifiers: {candidate_build_result.identifiers}")

        if use_acronyms and len(candidates) > 1:
            status_logger.info(
                f"Acronym workflow enabled (confidence_min={confidence_min:.2f}): "
                f"trying {len(candidates)} candidates"
            )
            for label, candidate in candidates:
                status_logger.info(f"  - {label}: {candidate.raw_input}")

        assessed_candidates = await workflow_assess_candidates(
            candidates, query_dispatcher
        )
        selection_result = workflow_resolve_candidate_selection(
            assessed_candidates=assessed_candidates,
            requested_venue_type=requested_venue_type,
            confidence_min=confidence_min,
            query_dispatcher=query_dispatcher,
            input_normalizer=input_normalizer,
            validate_issn=validate_issn,
        )
        result = selection_result.result

        workflow_finalize_publication_result(
            result=result,
            publication_name=publication_name,
            assessed_candidates=assessed_candidates,
            selection_result=selection_result,
            use_acronyms=use_acronyms,
            issn_validation_notes=candidate_build_result.issn_validation_notes,
            input_normalizer=input_normalizer,
        )

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
