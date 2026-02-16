# SPDX-License-Identifier: MIT
"""Publication assessment workflow helpers extracted from the CLI layer."""

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from .cache import AcronymCache
from .enums import AssessmentType, EvidenceType
from .models import (
    AssessmentResult,
    BackendStatus,
    CandidateAssessment,
    QueryInput,
    VenueType,
)
from .normalizer import are_conference_names_equivalent


ISSN_MIN_TOKEN_OVERLAP: float = 0.5


@dataclass
class PublicationCandidateBuildResult:
    """Structured candidate construction output for publication assessment."""

    candidates: list[tuple[str, QueryInput]]
    normalized_name: str | None
    identifiers: dict[str, str]
    issn_validation_notes: list[str]


@dataclass
class CandidateSelectionResult:
    """Best candidate selection outcome with optional reasoning notes."""

    best_label: str
    result: AssessmentResult
    best_query_input: QueryInput
    list_priority_note: str | None = None
    conservative_selection_note: str | None = None
    unresolved_conflict_note: str | None = None


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


def _is_acronym_like_candidate(
    label: str, query_text: str, input_normalizer: Any
) -> bool:
    """Return True when candidate represents an acronym-based query form."""
    if label.endswith("->full"):
        return False
    if "acronym" in label:
        return True
    return bool(input_normalizer._is_standalone_acronym(query_text.strip()))


def _is_decisive_assessment(assessment: AssessmentType) -> bool:
    """Return True when assessment is actionable (not unknown/insufficient)."""
    return assessment not in {
        AssessmentType.UNKNOWN,
        AssessmentType.INSUFFICIENT_DATA,
    }


def _candidate_has_list_evidence(candidate_result: AssessmentResult) -> bool:
    """Return True if candidate has curated list-based positive evidence."""
    return any(
        backend.status == BackendStatus.FOUND
        and backend.evidence_type
        in {
            EvidenceType.PREDATORY_LIST.value,
            EvidenceType.LEGITIMATE_LIST.value,
        }
        for backend in candidate_result.backend_results
    )


def _candidate_is_heuristic_only(candidate_result: AssessmentResult) -> bool:
    """Return True if candidate evidence is heuristic-only (no curated list hit)."""
    if not candidate_result.backend_results:
        return False
    has_heuristic_found = any(
        backend.status == BackendStatus.FOUND
        and backend.evidence_type == EvidenceType.HEURISTIC.value
        for backend in candidate_result.backend_results
    )
    return has_heuristic_found and not _candidate_has_list_evidence(candidate_result)


def _identifiers_contradict(left_ids: set[str], right_ids: set[str]) -> bool:
    """Return True when both sides have IDs and they are disjoint."""
    return bool(left_ids and right_ids and left_ids.isdisjoint(right_ids))


def _identifiers_overlap(left_ids: set[str], right_ids: set[str]) -> bool:
    """Return True when both sides have IDs and share at least one."""
    return bool(left_ids and right_ids and not left_ids.isdisjoint(right_ids))


def _collect_candidate_identifiers(
    query_input: QueryInput,
    requested_venue_type: VenueType,
    confidence_min: float,
    query_dispatcher: Any,
    validate_issn: Callable[[str], bool],
) -> set[str]:
    """Collect ISSN/eISSN identifiers for candidate consistency checks."""
    identifiers: set[str] = set()
    input_identifiers = (
        query_input.normalized_venue.input_identifiers
        if query_input.normalized_venue
        else {}
    )
    for value in input_identifiers.values():
        if isinstance(value, str) and validate_issn(value):
            identifiers.add(value)

    lookup_service = getattr(query_dispatcher, "lookup_service", None)
    if not lookup_service or not hasattr(lookup_service, "lookup"):
        return identifiers

    try:
        lookup_result = lookup_service.lookup(
            query_input.raw_input,
            venue_type=requested_venue_type,
            confidence_min=confidence_min,
        )
        identifiers.update(i for i in lookup_result.issns if i and validate_issn(i))
        identifiers.update(i for i in lookup_result.eissns if i and validate_issn(i))
    except Exception:
        return identifiers

    return identifiers


def _acronym_lookup_for_type(
    acronym_cache: AcronymCache,
    acronym: str,
    requested_venue_type: VenueType,
    use_acronyms: bool,
    confidence_min: float,
) -> str | None:
    """Return acronym expansion scoped to venue type and confidence threshold."""
    if not use_acronyms:
        return None
    return acronym_cache.get_full_name_for_acronym(
        acronym,
        requested_venue_type.value,
        min_confidence=confidence_min,
    )


def persist_candidate_mappings(
    candidates: list[tuple[str, QueryInput]], acronym_cache: AcronymCache
) -> None:
    """Store all extracted acronym mappings from candidate query inputs."""
    for _, query_input in candidates:
        for acronym, full_name in query_input.extracted_acronym_mappings.items():
            acronym_cache.store_acronym_mapping(
                acronym,
                full_name,
                query_input.venue_type.value,
                source="user_input",
            )


async def build_publication_candidates(
    publication_name: str,
    requested_venue_type: VenueType,
    acronym_cache: AcronymCache,
    use_acronyms: bool,
    confidence_min: float,
    input_normalizer: Any,
    resolve_issn_title: Callable[[str], Awaitable[str | None]],
) -> PublicationCandidateBuildResult:
    """Build base and acronym/variant/ISSN expansion candidates for assessment."""
    raw_input = publication_name.strip()
    base_query = input_normalizer.normalize(publication_name)
    base_query.venue_type = requested_venue_type
    base_normalized_venue = base_query.normalized_venue

    normalized_name = base_normalized_venue.name if base_normalized_venue else None
    aliases = base_normalized_venue.aliases if base_normalized_venue else []
    identifiers = (
        dict(base_normalized_venue.input_identifiers) if base_normalized_venue else {}
    )

    candidates: list[tuple[str, QueryInput]] = [("input", base_query)]
    candidate_names_seen: set[str] = {raw_input.lower()}
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
            resolved_title = await resolve_issn_title(issn)
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
                issn,
                acronym_lookup=lambda acronym: _acronym_lookup_for_type(
                    acronym_cache,
                    acronym,
                    requested_venue_type,
                    use_acronyms,
                    confidence_min,
                ),
            )
            issn_query.venue_type = requested_venue_type
            issn_query.acronym_expanded_from = raw_input
            candidates.append((f"{source_label}->issn", issn_query))
            candidate_names_seen.add(issn.lower())

    if use_acronyms:
        variant_inputs = [raw_input]
        if normalized_name:
            variant_inputs.append(normalized_name)
        variant_inputs.extend(aliases[:10])  # keep bounded

        if input_normalizer._is_standalone_acronym(raw_input) is True:
            expanded = acronym_cache.get_full_name_for_acronym(
                raw_input,
                requested_venue_type.value,
                min_confidence=confidence_min,
            )
            if expanded and expanded.lower() not in candidate_names_seen:
                expanded_query = input_normalizer.normalize(
                    expanded,
                    acronym_lookup=lambda acronym: _acronym_lookup_for_type(
                        acronym_cache,
                        acronym,
                        requested_venue_type,
                        use_acronyms,
                        confidence_min,
                    ),
                )
                expanded_query.venue_type = requested_venue_type
                expanded_query.acronym_expanded_from = raw_input
                candidates.append(("acronym->full", expanded_query))
                candidate_names_seen.add(expanded.lower())
                await add_issn_candidates(raw_input, "acronym", expanded)

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
                    canonical,
                    acronym_lookup=lambda item: _acronym_lookup_for_type(
                        acronym_cache,
                        item,
                        requested_venue_type,
                        use_acronyms,
                        confidence_min,
                    ),
                )
                canonical_query.venue_type = requested_venue_type
                canonical_query.acronym_expanded_from = raw_input
                candidates.append(("variant->full", canonical_query))
                candidate_names_seen.add(canonical.lower())

            if acronym.lower() not in candidate_names_seen:
                acronym_query = input_normalizer.normalize(
                    acronym,
                    acronym_lookup=lambda item: _acronym_lookup_for_type(
                        acronym_cache,
                        item,
                        requested_venue_type,
                        use_acronyms,
                        confidence_min,
                    ),
                )
                acronym_query.venue_type = requested_venue_type
                acronym_query.acronym_expanded_from = raw_input
                candidates.append(("variant->acronym", acronym_query))
                candidate_names_seen.add(acronym.lower())

            await add_issn_candidates(acronym, "variant", canonical)

        issn = identifiers.get("issn")
        if issn:
            issn_match = acronym_cache.get_issn_match(
                issn, min_confidence=confidence_min
            )
            if issn_match:
                canonical = str(issn_match["canonical"])
                acronym = str(issn_match["acronym"])
                resolved_title = await resolve_issn_title(issn)
                if not resolved_title:
                    issn_validation_notes.append(
                        f"Skipped ISSN {issn}: unable to resolve title from Crossref"
                    )
                elif not _issn_title_matches_expected(
                    resolved_title, canonical, requested_venue_type
                ):
                    issn_validation_notes.append(
                        f"Skipped ISSN {issn}: resolves to '{resolved_title}', "
                        f"does not match '{canonical}'"
                    )
                else:
                    issn_validation_notes.append(
                        f"Accepted ISSN {issn}: resolves to '{resolved_title}'"
                    )

                    if canonical.lower() not in candidate_names_seen:
                        canonical_query = input_normalizer.normalize(
                            canonical,
                            acronym_lookup=lambda item: _acronym_lookup_for_type(
                                acronym_cache,
                                item,
                                requested_venue_type,
                                use_acronyms,
                                confidence_min,
                            ),
                        )
                        canonical_query.venue_type = requested_venue_type
                        canonical_query.acronym_expanded_from = raw_input
                        candidates.append(("issn->full", canonical_query))
                        candidate_names_seen.add(canonical.lower())

                    if acronym.lower() not in candidate_names_seen:
                        acronym_query = input_normalizer.normalize(
                            acronym,
                            acronym_lookup=lambda item: _acronym_lookup_for_type(
                                acronym_cache,
                                item,
                                requested_venue_type,
                                use_acronyms,
                                confidence_min,
                            ),
                        )
                        acronym_query.venue_type = requested_venue_type
                        acronym_query.acronym_expanded_from = raw_input
                        candidates.append(("issn->acronym", acronym_query))
                        candidate_names_seen.add(acronym.lower())

    return PublicationCandidateBuildResult(
        candidates=candidates,
        normalized_name=normalized_name,
        identifiers=identifiers,
        issn_validation_notes=issn_validation_notes,
    )


async def assess_candidates(
    candidates: list[tuple[str, QueryInput]], query_dispatcher: Any
) -> list[tuple[str, AssessmentResult, QueryInput]]:
    """Assess all candidates and return their outcomes."""
    assessed_candidates: list[tuple[str, AssessmentResult, QueryInput]] = []
    for label, query_input in candidates:
        candidate_result = await query_dispatcher.assess_journal(query_input)
        assessed_candidates.append((label, candidate_result, query_input))
    return assessed_candidates


def resolve_candidate_selection(
    assessed_candidates: list[tuple[str, AssessmentResult, QueryInput]],
    requested_venue_type: VenueType,
    confidence_min: float,
    query_dispatcher: Any,
    input_normalizer: Any,
    validate_issn: Callable[[str], bool],
) -> CandidateSelectionResult:
    """Select strongest candidate and resolve conflicts conservatively."""
    best_label, result, best_query_input = max(
        assessed_candidates,
        key=lambda item: (item[1].confidence, item[1].overall_score),
    )
    best_query_text = best_query_input.raw_input
    candidate_ids = {
        (label, candidate_query.raw_input): _collect_candidate_identifiers(
            candidate_query,
            requested_venue_type,
            confidence_min,
            query_dispatcher,
            validate_issn,
        )
        for label, _, candidate_query in assessed_candidates
    }

    selection_result = CandidateSelectionResult(
        best_label=best_label,
        result=result,
        best_query_input=best_query_input,
    )

    decisive_candidates = [
        item
        for item in assessed_candidates
        if _is_decisive_assessment(item[1].assessment)
    ]

    list_preferred_candidates: list[tuple[str, AssessmentResult, QueryInput]] = []
    for left in decisive_candidates:
        for right in decisive_candidates:
            if left is right or left[1].assessment == right[1].assessment:
                continue
            left_result = left[1]
            right_result = right[1]
            if not (
                _candidate_has_list_evidence(left_result)
                and _candidate_is_heuristic_only(right_result)
            ):
                continue
            left_key = (left[0], left[2].raw_input)
            right_key = (right[0], right[2].raw_input)
            if _identifiers_contradict(
                candidate_ids[left_key], candidate_ids[right_key]
            ):
                continue
            list_preferred_candidates.append(left)

    if list_preferred_candidates:
        preferred_label, preferred_result, preferred_query = max(
            list_preferred_candidates,
            key=lambda item: (item[1].confidence, item[1].overall_score),
        )
        if (preferred_label, preferred_query.raw_input) != (
            selection_result.best_label,
            selection_result.best_query_input.raw_input,
        ):
            selection_result.best_label = preferred_label
            selection_result.result = preferred_result
            selection_result.best_query_input = preferred_query
            best_query_text = preferred_query.raw_input
            selection_result.list_priority_note = (
                "Prioritized curated list-backed evidence over a conflicting "
                "heuristic-only candidate."
            )

    if _is_acronym_like_candidate(
        selection_result.best_label, best_query_text, input_normalizer
    ):
        conflicting_non_acronym = [
            (label, candidate_result, candidate_query)
            for label, candidate_result, candidate_query in assessed_candidates
            if not _is_acronym_like_candidate(
                label, candidate_query.raw_input, input_normalizer
            )
            and _is_decisive_assessment(candidate_result.assessment)
            and candidate_result.assessment != selection_result.result.assessment
        ]
        if conflicting_non_acronym:
            best_ids = candidate_ids[(selection_result.best_label, best_query_text)]
            consistency_confirmed = False
            for other_label, _, candidate_query in conflicting_non_acronym:
                other_ids = candidate_ids[(other_label, candidate_query.raw_input)]
                if _identifiers_overlap(best_ids, other_ids):
                    consistency_confirmed = True
                    break

            if not consistency_confirmed:
                fallback_candidates = [
                    item
                    for item in assessed_candidates
                    if (
                        not _is_acronym_like_candidate(
                            item[0], item[2].raw_input, input_normalizer
                        )
                        and _is_decisive_assessment(item[1].assessment)
                    )
                ]
                if fallback_candidates:
                    (
                        selection_result.best_label,
                        selection_result.result,
                        selection_result.best_query_input,
                    ) = max(
                        fallback_candidates,
                        key=lambda item: (item[1].confidence, item[1].overall_score),
                    )
                    best_query_text = selection_result.best_query_input.raw_input
                    selection_result.conservative_selection_note = (
                        "Conservative candidate selection: acronym candidate "
                        "conflicted with a non-acronym result and identifier "
                        "consistency could not be confirmed; selected "
                        "non-acronym candidate."
                    )

    decisive_candidates = [
        item
        for item in assessed_candidates
        if _is_decisive_assessment(item[1].assessment)
    ]
    conflict_pairs: list[
        tuple[
            tuple[str, AssessmentResult, QueryInput],
            tuple[str, AssessmentResult, QueryInput],
        ]
    ] = []
    for index, left in enumerate(decisive_candidates):
        for right in decisive_candidates[index + 1 :]:
            if left[1].assessment != right[1].assessment:
                conflict_pairs.append((left, right))

    if conflict_pairs:
        best_has_list = _candidate_has_list_evidence(selection_result.result)
        resolved_by_list_priority = False
        if best_has_list:
            best_key = (selection_result.best_label, best_query_text)
            best_ids = candidate_ids[best_key]
            conflicting_with_best = [
                pair
                for pair in conflict_pairs
                if (
                    pair[0][0] == selection_result.best_label
                    and pair[0][2].raw_input == best_query_text
                )
                or (
                    pair[1][0] == selection_result.best_label
                    and pair[1][2].raw_input == best_query_text
                )
            ]
            if conflicting_with_best:
                resolved_by_list_priority = True
                for left, right in conflicting_with_best:
                    other = right
                    if (
                        right[0] == selection_result.best_label
                        and right[2].raw_input == best_query_text
                    ):
                        other = left
                    other_result = other[1]
                    other_key = (other[0], other[2].raw_input)
                    other_ids = candidate_ids[other_key]
                    if not _candidate_is_heuristic_only(other_result) or (
                        _identifiers_contradict(best_ids, other_ids)
                    ):
                        resolved_by_list_priority = False
                        break

        any_identifier_validated = any(
            _identifiers_overlap(
                candidate_ids[(left[0], left[2].raw_input)],
                candidate_ids[(right[0], right[2].raw_input)],
            )
            for left, right in conflict_pairs
        )
        if not resolved_by_list_priority and not any_identifier_validated:
            selection_result.result.assessment = AssessmentType.INSUFFICIENT_DATA
            selection_result.result.confidence = 0.0
            selection_result.result.overall_score = 0.0
            selection_result.unresolved_conflict_note = (
                "Candidate outcomes conflict and could not be "
                "identifier-validated; no reliable assessment possible."
            )

    return selection_result


def finalize_publication_result(
    result: AssessmentResult,
    publication_name: str,
    assessed_candidates: list[tuple[str, AssessmentResult, QueryInput]],
    selection_result: CandidateSelectionResult,
    use_acronyms: bool,
    issn_validation_notes: list[str],
    input_normalizer: Any,
) -> None:
    """Populate candidate details and reasoning notes on final result."""
    best_label = selection_result.best_label
    best_query_text = selection_result.best_query_input.raw_input

    result.candidate_assessments = [
        CandidateAssessment(
            label=label,
            query=candidate_query.raw_input,
            assessment=candidate_result.assessment,
            confidence=candidate_result.confidence,
            overall_score=candidate_result.overall_score,
            selected=(
                label == best_label and candidate_query.raw_input == best_query_text
            ),
        )
        for label, candidate_result, candidate_query in assessed_candidates
    ]
    result.input_query = publication_name.strip()

    if use_acronyms and len(assessed_candidates) > 1:
        result.reasoning.insert(
            0,
            f"Acronym workflow: tried {len(assessed_candidates)} candidate forms; "
            f"selected '{best_query_text}' ({best_label})",
        )
    if selection_result.list_priority_note:
        result.reasoning.insert(1, selection_result.list_priority_note)
    if selection_result.conservative_selection_note:
        result.reasoning.insert(1, selection_result.conservative_selection_note)
    if selection_result.unresolved_conflict_note:
        result.reasoning.insert(1, selection_result.unresolved_conflict_note)
    if issn_validation_notes:
        result.reasoning.extend(
            [f"ISSN validation: {note}" for note in issn_validation_notes]
        )

    if best_label != "input":
        result.acronym_expansion_used = True
        if not result.acronym_expanded_from:
            if input_normalizer._is_standalone_acronym(best_query_text) is True:
                result.acronym_expanded_from = best_query_text
            else:
                result.acronym_expanded_from = publication_name.strip()
