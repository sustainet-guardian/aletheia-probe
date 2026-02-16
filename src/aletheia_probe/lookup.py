# SPDX-License-Identifier: MIT
"""Venue lookup service for normalization candidates and identifiers."""

from dataclasses import asdict, dataclass, field

from .cache import AcronymCache, JournalCache
from .constants import DEFAULT_ACRONYM_CONFIDENCE_MIN
from .models import QueryInput, VenueType
from .normalizer import input_normalizer
from .validation import validate_issn


@dataclass
class LookupCandidate:
    """Single lookup candidate produced from a specific source."""

    source: str
    normalized_name: str
    confidence: float | None = None
    acronym: str | None = None
    issn: str | None = None
    eissn: str | None = None


@dataclass
class LookupValidation:
    """Validation result for a name/identifier pair against an external source."""

    source: str
    identifier: str
    status: str
    input_name: str | None = None
    resolved_name: str | None = None
    similarity: float | None = None
    details: str | None = None


@dataclass
class LookupResult:
    """Structured lookup result for one venue input."""

    raw_input: str
    venue_type: VenueType
    normalized_name: str | None
    normalized_names: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    identifiers: dict[str, str] = field(default_factory=dict)
    issn_valid: bool = False
    issns: list[str] = field(default_factory=list)
    eissns: list[str] = field(default_factory=list)
    candidates: list[LookupCandidate] = field(default_factory=list)
    validations: list[LookupValidation] = field(default_factory=list)
    consistency_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        return {
            **asdict(self),
            "venue_type": self.venue_type.value,
            "candidates": [asdict(candidate) for candidate in self.candidates],
            "validations": [asdict(validation) for validation in self.validations],
        }


class VenueLookupService:
    """Build lookup candidates from local normalization and cache sources."""

    def __init__(
        self,
        acronym_cache: AcronymCache | None = None,
        journal_cache: JournalCache | None = None,
    ) -> None:
        self.acronym_cache = acronym_cache or AcronymCache()
        self.journal_cache = journal_cache or JournalCache()

    def lookup(
        self,
        raw_input: str,
        venue_type: VenueType,
        confidence_min: float = DEFAULT_ACRONYM_CONFIDENCE_MIN,
    ) -> LookupResult:
        """Resolve local normalization candidates for a venue string."""
        base_query = input_normalizer.normalize(raw_input)
        base_query.venue_type = venue_type
        base_normalized_name = self._normalize_name_for_lookup(base_query.raw_input)
        base_normalized_venue = base_query.normalized_venue

        result = LookupResult(
            raw_input=raw_input.strip(),
            venue_type=venue_type,
            normalized_name=base_normalized_name,
            aliases=list(
                base_normalized_venue.aliases if base_normalized_venue else []
            ),
            identifiers=dict(
                base_normalized_venue.input_identifiers if base_normalized_venue else {}
            ),
        )
        candidate_keys: set[tuple[str, str, str | None, str | None]] = set()
        normalized_names: set[str] = set()
        issns: set[str] = set()
        eissns: set[str] = set()

        self._add_candidate(
            result=result,
            candidate_keys=candidate_keys,
            source="input",
            normalized_name=base_normalized_name,
        )

        if base_normalized_name:
            normalized_names.add(base_normalized_name)

        for alias in result.aliases:
            if alias:
                normalized_alias = self._normalize_name_for_lookup(alias)
                if normalized_alias:
                    normalized_names.add(normalized_alias)

        input_issn = result.identifiers.get("issn")
        if input_issn:
            issns.add(input_issn)
            result.issn_valid = validate_issn(input_issn)

        input_eissn = result.identifiers.get("eissn")
        if input_eissn:
            eissns.add(input_eissn)
        self._add_identifier_reverse_lookup_candidates(
            base_query,
            result,
            candidate_keys,
            normalized_names,
            issns,
            eissns,
        )

        self._add_journal_cache_candidates(
            normalized_name=(
                (base_normalized_venue.name if base_normalized_venue else "") or ""
            ),
            result=result,
            candidate_keys=candidate_keys,
            normalized_names=normalized_names,
            issns=issns,
            eissns=eissns,
        )
        acronym_normalized_names = self._add_acronym_candidates(
            base_query,
            venue_type,
            confidence_min,
            result,
            candidate_keys,
            normalized_names,
            issns,
            eissns,
        )
        for resolved_name in sorted(acronym_normalized_names):
            if resolved_name == base_normalized_name:
                continue
            self._add_journal_cache_candidates(
                normalized_name=resolved_name,
                result=result,
                candidate_keys=candidate_keys,
                normalized_names=normalized_names,
                issns=issns,
                eissns=eissns,
            )

        result.normalized_names = sorted(normalized_names)
        result.issns = sorted(issns)
        result.eissns = sorted(eissns)
        return result

    def _add_identifier_reverse_lookup_candidates(
        self,
        base_query: QueryInput,
        result: LookupResult,
        candidate_keys: set[tuple[str, str, str | None, str | None]],
        normalized_names: set[str],
        issns: set[str],
        eissns: set[str],
    ) -> None:
        """Reverse-resolve venue names from input ISSN/eISSN identifiers."""
        query_identifiers = [
            value
            for value in (
                base_query.normalized_venue.input_identifiers.values()
                if base_query.normalized_venue
                else []
            )
            if value
        ]
        for identifier in query_identifiers:
            rows = self.journal_cache.search_journals(issn=identifier)
            for row in rows[:5]:
                display_name = str(row.get("display_name") or "").strip()
                candidate_name = self._normalize_name_for_lookup(display_name)
                if not candidate_name:
                    continue

                normalized_names.add(candidate_name)
                row_issn = str(row.get("issn") or "").strip() or None
                row_eissn = str(row.get("eissn") or "").strip() or None
                if row_issn:
                    issns.add(row_issn)
                if row_eissn:
                    eissns.add(row_eissn)

                self._add_candidate(
                    result=result,
                    candidate_keys=candidate_keys,
                    source="journal_cache_identifier_reverse",
                    normalized_name=candidate_name,
                    confidence=0.9,
                    issn=row_issn,
                    eissn=row_eissn,
                )

    def _add_journal_cache_candidates(
        self,
        normalized_name: str,
        result: LookupResult,
        candidate_keys: set[tuple[str, str, str | None, str | None]],
        normalized_names: set[str],
        issns: set[str],
        eissns: set[str],
    ) -> None:
        """Add candidates from the journal cache."""
        normalized_name = normalized_name.strip().lower()
        if not normalized_name:
            return

        exact_ids = self.journal_cache.get_journal_identifiers_by_normalized_name(
            normalized_name
        )
        if exact_ids:
            issn = exact_ids.get("issn")
            eissn = exact_ids.get("eissn")
            if issn:
                issns.add(issn)
            if eissn:
                eissns.add(eissn)
            self._add_candidate(
                result=result,
                candidate_keys=candidate_keys,
                source="journal_cache_exact",
                normalized_name=normalized_name,
                confidence=0.9,
                issn=issn,
                eissn=eissn,
            )

    def _add_acronym_candidates(
        self,
        base_query: QueryInput,
        venue_type: VenueType,
        confidence_min: float,
        result: LookupResult,
        candidate_keys: set[tuple[str, str, str | None, str | None]],
        normalized_names: set[str],
        issns: set[str],
        eissns: set[str],
    ) -> set[str]:
        """Add candidates from acronym tables."""
        raw_input = base_query.raw_input.strip()
        entity_type = venue_type.value
        resolved_normalized_names: set[str] = set()

        if input_normalizer._is_standalone_acronym(raw_input):
            expanded = self.acronym_cache.get_full_name_for_acronym(
                raw_input,
                entity_type,
                min_confidence=confidence_min,
            )
            if expanded:
                normalized_expanded = self._normalize_name_for_lookup(expanded)
                if normalized_expanded:
                    normalized_names.add(normalized_expanded)
                    resolved_normalized_names.add(normalized_expanded)
                    self._add_candidate(
                        result=result,
                        candidate_keys=candidate_keys,
                        source="acronym_exact",
                        normalized_name=normalized_expanded,
                        confidence=confidence_min,
                        acronym=raw_input,
                    )
        variant_inputs = [raw_input]
        base_name = (
            base_query.normalized_venue.name if base_query.normalized_venue else None
        )
        if base_name:
            variant_inputs.append(base_name)
        base_aliases = (
            base_query.normalized_venue.aliases if base_query.normalized_venue else []
        )
        variant_inputs.extend(base_aliases[:10])

        for variant_input in variant_inputs:
            if not variant_input:
                continue
            variant_match = self.acronym_cache.get_variant_match(
                variant_input,
                entity_type,
                min_confidence=confidence_min,
            )
            if not variant_match:
                continue

            canonical = str(variant_match.get("canonical") or "").strip()
            acronym = str(variant_match.get("acronym") or "").strip() or None
            confidence = float(variant_match.get("confidence_score") or 0.0)
            canonical_normalized = self._normalize_name_for_lookup(canonical)
            if not canonical_normalized:
                continue

            normalized_names.add(canonical_normalized)
            resolved_normalized_names.add(canonical_normalized)
            self._add_candidate(
                result=result,
                candidate_keys=candidate_keys,
                source="acronym_variant",
                normalized_name=canonical_normalized,
                confidence=confidence,
                acronym=acronym,
            )

            if acronym:
                acronym_issns = self.acronym_cache.get_issns(
                    acronym,
                    entity_type,
                    min_confidence=confidence_min,
                )
                for acronym_issn in acronym_issns:
                    if acronym_issn:
                        issns.add(acronym_issn)

        input_issn = (
            base_query.normalized_venue.input_identifiers.get("issn")
            if base_query.normalized_venue
            else None
        )
        if input_issn:
            issn_match = self.acronym_cache.get_issn_match(
                input_issn, min_confidence=0.0
            )
            if issn_match:
                canonical = str(issn_match.get("canonical") or "").strip()
                acronym = str(issn_match.get("acronym") or "").strip() or None
                confidence = float(issn_match.get("confidence_score") or 0.0)
                canonical_normalized = self._normalize_name_for_lookup(canonical)
                if canonical_normalized:
                    normalized_names.add(canonical_normalized)
                    resolved_normalized_names.add(canonical_normalized)
                    self._add_candidate(
                        result=result,
                        candidate_keys=candidate_keys,
                        source="acronym_issn",
                        normalized_name=canonical_normalized,
                        confidence=confidence,
                        acronym=acronym,
                        issn=input_issn,
                    )
                    issns.add(input_issn)

        # No local table currently provides explicit eISSN variants.
        _ = eissns
        return resolved_normalized_names

    def _add_candidate(
        self,
        result: LookupResult,
        candidate_keys: set[tuple[str, str, str | None, str | None]],
        source: str,
        normalized_name: str | None,
        confidence: float | None = None,
        acronym: str | None = None,
        issn: str | None = None,
        eissn: str | None = None,
    ) -> None:
        """Add a candidate with deduplication."""
        cleaned_name = (normalized_name or "").strip().lower()
        if not cleaned_name:
            return

        key = (source, cleaned_name, issn, eissn)
        if key in candidate_keys:
            return
        candidate_keys.add(key)

        result.candidates.append(
            LookupCandidate(
                source=source,
                normalized_name=cleaned_name,
                confidence=confidence,
                acronym=acronym,
                issn=issn,
                eissn=eissn,
            )
        )

    def _normalize_name_for_lookup(self, text: str | None) -> str:
        """Normalize a name to lowercase canonical form for lookup output."""
        if not text:
            return ""
        normalized_query = input_normalizer.normalize(text)
        normalized = (
            normalized_query.normalized_venue.name
            if normalized_query.normalized_venue
            else None
        )
        if not normalized:
            return ""
        return normalized.strip().lower()
