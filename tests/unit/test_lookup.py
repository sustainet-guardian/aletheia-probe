# SPDX-License-Identifier: MIT
"""Tests for the venue lookup service."""

from unittest.mock import Mock

from aletheia_probe.lookup import VenueLookupService
from aletheia_probe.models import VenueType


class TestVenueLookupService:
    """Test cases for local lookup behavior."""

    def test_lookup_collects_cache_and_variant_candidates(self):
        """Collect normalized names and identifiers from local cache sources."""
        acronym_cache = Mock()
        journal_cache = Mock()

        journal_cache.get_journal_identifiers_by_normalized_name.return_value = {
            "issn": "0028-0836",
            "eissn": "1476-4687",
        }
        journal_cache.search_journals.return_value = [
            {"display_name": "Nature", "issn": "0028-0836", "eissn": "1476-4687"}
        ]

        acronym_cache.get_full_name_for_acronym.return_value = None
        acronym_cache.get_variant_match.return_value = {
            "canonical": "nature",
            "acronym": "NAT",
            "confidence_score": 0.91,
        }
        acronym_cache.get_issns.return_value = ["0028-0836"]
        acronym_cache.get_issn_match.return_value = {
            "canonical": "nature",
            "acronym": "NAT",
            "confidence_score": 0.91,
        }

        service = VenueLookupService(
            acronym_cache=acronym_cache,
            journal_cache=journal_cache,
        )
        result = service.lookup("Nature 0028-0836", VenueType.JOURNAL)

        assert result.issn_valid is True
        assert "nature" in result.normalized_names
        assert "0028-0836" in result.issns
        assert "1476-4687" in result.eissns
        assert any(c.source == "journal_cache_exact" for c in result.candidates)
        assert any(c.source == "acronym_variant" for c in result.candidates)
        assert any(c.source == "acronym_issn" for c in result.candidates)

    def test_lookup_resolves_standalone_conference_acronym(self):
        """Resolve standalone acronym candidates for conference lookup."""
        acronym_cache = Mock()
        journal_cache = Mock()

        journal_cache.get_journal_identifiers_by_normalized_name.return_value = None
        journal_cache.search_journals.return_value = []

        acronym_cache.get_full_name_for_acronym.return_value = (
            "international conference on machine learning"
        )
        acronym_cache.get_variant_match.return_value = None
        acronym_cache.get_issns.return_value = []
        acronym_cache.get_issn_match.return_value = None

        service = VenueLookupService(
            acronym_cache=acronym_cache,
            journal_cache=journal_cache,
        )
        result = service.lookup("ICML", VenueType.CONFERENCE, confidence_min=0.8)

        assert "international conference on machine learning" in result.normalized_names
        assert any(c.source == "acronym_exact" for c in result.candidates)

    def test_lookup_skips_broad_cache_search_for_standalone_acronym(self):
        """Avoid broad LIKE-based cache matching for standalone acronym inputs."""
        acronym_cache = Mock()
        journal_cache = Mock()

        journal_cache.get_journal_identifiers_by_normalized_name.side_effect = (
            lambda name: (
                {"issn": "0219-5259", "eissn": "1793-6802"}
                if name == "advances in complex systems"
                else None
            )
        )
        journal_cache.search_journals.return_value = [
            {"display_name": "acs applied materials and interfaces"}
        ]

        acronym_cache.get_full_name_for_acronym.return_value = (
            "advances in complex systems"
        )
        acronym_cache.get_variant_match.return_value = None
        acronym_cache.get_issns.return_value = []
        acronym_cache.get_issn_match.return_value = None

        service = VenueLookupService(
            acronym_cache=acronym_cache,
            journal_cache=journal_cache,
        )
        result = service.lookup("ACS", VenueType.JOURNAL)

        searched_names = [
            call.kwargs["normalized_name"]
            for call in journal_cache.search_journals.call_args_list
        ]
        assert "acs" not in searched_names
        assert "advances in complex systems" in result.normalized_names
        assert "0219-5259" in result.issns
        assert "1793-6802" in result.eissns

    def test_lookup_reverse_identifier_resolves_name(self):
        """Resolve a venue name from ISSN-only input via journal cache."""
        acronym_cache = Mock()
        journal_cache = Mock()

        journal_cache.get_journal_identifiers_by_normalized_name.return_value = None
        journal_cache.search_journals.side_effect = (
            lambda normalized_name=None, issn=None: (
                [
                    {
                        "display_name": "Advances in Complex Systems",
                        "issn": "0219-5259",
                        "eissn": "1793-6802",
                    }
                ]
                if issn == "0219-5259"
                else []
            )
        )

        acronym_cache.get_full_name_for_acronym.return_value = None
        acronym_cache.get_variant_match.return_value = None
        acronym_cache.get_issns.return_value = []
        acronym_cache.get_issn_match.return_value = None

        service = VenueLookupService(
            acronym_cache=acronym_cache,
            journal_cache=journal_cache,
        )
        result = service.lookup("0219-5259", VenueType.JOURNAL)

        assert result.issn_valid is True
        assert "advances in complex systems" in result.normalized_names
        assert "0219-5259" in result.issns
        assert "1793-6802" in result.eissns
        assert any(
            c.source == "journal_cache_identifier_reverse" for c in result.candidates
        )
