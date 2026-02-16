# SPDX-License-Identifier: MIT
"""Lookup and enrichment CLI workflow helpers."""

import asyncio
import json
from typing import Any

import click

from ..lookup import LookupCandidate, LookupResult, LookupValidation, VenueLookupService
from ..models import VenueType
from ..normalizer import input_normalizer
from ..openalex import OpenAlexClient
from ..validation import validate_issn
from .network import _resolve_issn_title


GENERIC_RESOLVED_TITLES: set[str] = {"proceedings", "journal", "conference"}


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
