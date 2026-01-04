# SPDX-License-Identifier: MIT
"""Crossref backend with metadata quality analysis for predatory journal detection."""

import asyncio
import time
from typing import Any

import aiohttp

from ..enums import AssessmentType
from ..logging_config import get_detail_logger, get_status_logger
from ..models import BackendResult, BackendStatus, QueryInput
from ..validation import validate_email
from .base import ApiBackendWithCache, get_backend_registry


# Local thresholds for Crossref metadata analysis
_ORCID_HIGH = 70.0
_ORCID_GOOD = 40.0
_ORCID_LOW = 10.0
_ORCID_VERY_LOW = 5.0

_FUNDING_GOOD = 40.0
_FUNDING_MODERATE = 20.0
_FUNDING_MINIMAL = 2.0

_LICENSE_EXCELLENT = 80.0
_LICENSE_GOOD = 50.0
_LICENSE_POOR = 5.0

_REFERENCE_GOOD = 60.0

_QUALITY_HIGH = 60.0
_QUALITY_GOOD = 40.0
_QUALITY_LOW = 25.0
_QUALITY_POOR = 15.0
_QUALITY_POOR_PRACTICES = 30.0

_DOI_MAJOR = 100000
_DOI_LARGE = 10000
_DOI_SUBSTANTIAL = 1000
_DOI_MEDIUM = 500
_DOI_SMALL = 100
_DOI_VERY_SMALL = 50

_EXPLOSION_MULTIPLIER = 3.0
_EXPLOSION_MIN_COUNT = 500


class CrossrefAnalyzerBackend(ApiBackendWithCache):
    """Backend that analyzes Crossref metadata quality to assess journal legitimacy."""

    def __init__(
        self, email: str = "noreply@aletheia-probe.org", cache_ttl_hours: int = 24
    ):
        """Initialize Crossref analyzer backend.

        Args:
            email: Email for Crossref polite pool access
            cache_ttl_hours: Cache TTL in hours

        Raises:
            TypeError: If email is not a string
            ValueError: If email format is invalid
        """
        super().__init__(cache_ttl_hours)
        self.email = validate_email(email)
        self.base_url = "https://api.crossref.org"
        self.headers = {
            "User-Agent": f"AletheiaProbe/1.0 (mailto:{email})",
        }
        self.detail_logger = get_detail_logger()
        self.status_logger = get_status_logger()

    def get_name(self) -> str:
        """Return backend name."""
        return "crossref_analyzer"

    def _is_small_to_medium_journal(self, total_dois: int) -> bool:
        """Check if journal is in the small-to-medium size range for targeted analysis."""
        return _DOI_SMALL <= total_dois < _DOI_LARGE

    def _is_very_small_journal(self, total_dois: int) -> bool:
        """Check if journal is very small (less than 50 DOIs)."""
        return total_dois < _DOI_VERY_SMALL

    def _adjust_confidence_by_volume(self, confidence: float, total_dois: int) -> float:
        """Adjust confidence based on publication volume (more DOIs = more reliable assessment)."""
        if total_dois >= _DOI_SUBSTANTIAL:
            return min(1.0, confidence * 1.1)  # Boost for high-volume publishers
        elif self._is_very_small_journal(total_dois):
            return max(0.1, confidence * 0.8)  # Reduce for low-volume publishers
        return confidence

    def _check_orcid_quality(self, orcid_score: float) -> str | None:
        """Check ORCID adoption level and return description if notable."""
        if orcid_score >= _ORCID_HIGH:
            return (
                f"High ORCID adoption: {orcid_score}% of articles include author ORCIDs"
            )
        elif orcid_score >= _ORCID_GOOD:
            return (
                f"Good ORCID adoption: {orcid_score}% of articles include author ORCIDs"
            )
        return None

    def _check_funding_quality(self, funding_score: float) -> str | None:
        """Check funding transparency level and return description if notable."""
        if funding_score >= _FUNDING_GOOD:
            return f"Good funding transparency: {funding_score}% of articles include funding information"
        elif funding_score >= _FUNDING_MODERATE:
            return f"Moderate funding transparency: {funding_score}% of articles include funding information"
        return None

    def _check_license_quality(self, license_score: float) -> str | None:
        """Check license documentation level and return description if notable."""
        if license_score >= _LICENSE_EXCELLENT:
            return f"Excellent license documentation: {license_score}% of articles have license information"
        elif license_score >= _LICENSE_GOOD:
            return f"Good license documentation: {license_score}% of articles have license information"
        return None

    async def _query_api(self, query_input: QueryInput) -> BackendResult:
        """Query Crossref API and analyze metadata quality."""
        start_time = time.time()
        self.status_logger.info(
            f"Crossref: Analyzing metadata for '{query_input.raw_input}'"
        )
        self.detail_logger.debug(
            f"Crossref: Starting API query with identifiers: {query_input.identifiers}"
        )

        try:
            # Try to find journal by ISSN first
            journal_data = None
            issn = query_input.identifiers.get("issn")
            eissn = query_input.identifiers.get("eissn")

            if issn:
                self.detail_logger.debug(f"Crossref: Searching by ISSN {issn}")
                journal_data = await self._get_journal_by_issn(issn)

            if not journal_data and eissn:
                self.detail_logger.debug(f"Crossref: Searching by eISSN {eissn}")
                journal_data = await self._get_journal_by_issn(eissn)

            response_time = time.time() - start_time

            if not journal_data:
                # Not found in Crossref
                self.detail_logger.info(
                    f"Crossref: Journal not found for {query_input.raw_input}"
                )
                return BackendResult(
                    backend_name=self.get_name(),
                    status=BackendStatus.NOT_FOUND,
                    confidence=0.0,
                    assessment=None,
                    data={
                        "searched_for": query_input.raw_input,
                        "issn": issn,
                        "eissn": eissn,
                    },
                    sources=["https://api.crossref.org"],
                    error_message=None,
                    response_time=response_time,
                )

            # Analyze metadata quality
            self.detail_logger.debug(
                f"Crossref: Analyzing metadata for {journal_data.get('title')}"
            )
            analysis = self._analyze_metadata_quality(journal_data)
            self.detail_logger.info(
                f"Crossref: Analysis complete. Assessment: {analysis['assessment']}, Confidence: {analysis['confidence']:.2f}"
            )

            return BackendResult(
                backend_name=self.get_name(),
                status=BackendStatus.FOUND,
                confidence=analysis["confidence"],
                assessment=analysis["assessment"],
                data={
                    "crossref_data": journal_data,
                    "analysis": analysis,
                    "metrics": analysis["metrics"],
                    "red_flags": analysis["red_flags"],
                    "green_flags": analysis["green_flags"],
                },
                sources=[
                    "https://api.crossref.org",
                    f"https://api.crossref.org/journals/{issn or eissn}",
                ],
                error_message=None,
                response_time=response_time,
            )

        except Exception as e:
            response_time = time.time() - start_time
            self.status_logger.error(f"Crossref API error: {e}")
            self.detail_logger.exception(f"Crossref API error details: {e}")
            return BackendResult(
                backend_name=self.get_name(),
                status=BackendStatus.ERROR,
                confidence=0.0,
                assessment=None,
                error_message=str(e),
                response_time=response_time,
            )

    async def _get_journal_by_issn(self, issn: str) -> dict[str, Any] | None:
        """Get journal data by ISSN from Crossref API."""
        url = f"{self.base_url}/journals/{issn}"
        self.detail_logger.debug(f"Crossref API request: GET {url}")

        async with aiohttp.ClientSession(
            headers=self.headers, timeout=aiohttp.ClientTimeout(total=30)
        ) as session:
            try:
                async with session.get(url) as response:
                    self.detail_logger.debug(
                        f"Crossref API response: {response.status}"
                    )
                    if response.status == 200:
                        data = await response.json()
                        message = data.get("message", {})
                        return message if isinstance(message, dict) else {}
                    elif response.status == 404:
                        return None
                    else:
                        raise Exception(
                            f"Crossref API returned status {response.status}"
                        )
            except asyncio.TimeoutError:
                self.detail_logger.error("Crossref API timeout")
                raise Exception("Crossref API timeout") from None

    def _analyze_metadata_quality(self, journal_data: dict[str, Any]) -> dict[str, Any]:
        """Analyze Crossref metadata quality patterns.

        Args:
            journal_data: Raw journal data from Crossref

        Returns:
            Analysis dictionary with assessment, confidence, and flags
        """
        # Calculate metrics from raw data
        metrics, quality_scores = self._calculate_metadata_metrics(journal_data)

        # Check for green flags (quality indicators)
        green_flags = self._check_metadata_green_flags(metrics, quality_scores)

        # Check for red flags (quality issues)
        red_flags = self._check_metadata_red_flags(
            metrics, quality_scores, journal_data
        )

        # Determine final assessment and confidence
        assessment, confidence = self._determine_metadata_assessment(
            red_flags, green_flags, metrics
        )

        return {
            "assessment": assessment,
            "confidence": confidence,
            "metrics": metrics,
            "red_flags": red_flags,
            "green_flags": green_flags,
            "quality_scores": quality_scores,
        }

    def _calculate_metadata_metrics(
        self, journal_data: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, float]]:
        """Calculate metadata quality metrics from Crossref data.

        Args:
            journal_data: Raw journal data from Crossref

        Returns:
            Tuple of (metrics dict, quality_scores dict)
        """
        # Extract basic information
        title_list = journal_data.get("title", [])
        title = (
            title_list[0]
            if isinstance(title_list, list) and title_list
            else str(title_list)
            if title_list
            else ""
        )
        publisher = journal_data.get("publisher", "")
        counts = journal_data.get("counts", {})
        coverage = journal_data.get("coverage", {})
        coverage_current = journal_data.get("coverage-type", {}).get("current", {})

        # Extract DOI counts
        total_dois = counts.get("total-dois", 0)
        current_dois = counts.get("current-dois", 0)
        backfile_dois = counts.get("backfile-dois", 0)

        # Extract publication pattern
        dois_by_year = journal_data.get("breakdowns", {}).get("dois-by-issued-year", [])

        # Calculate derived metrics
        metrics = {
            "total_dois": total_dois,
            "current_dois": current_dois,
            "backfile_dois": backfile_dois,
            "publisher": publisher,
            "title": title,
            "dois_by_year": dois_by_year,
        }

        # Metadata quality scores (0-100 scale in Crossref)
        quality_indicators = [
            ("orcids", "ORCID adoption"),
            ("funders", "Funding data"),
            ("licenses", "License information"),
            ("abstracts", "Abstract availability"),
            ("affiliations", "Author affiliations"),
            ("references", "Reference linking"),
            ("award-numbers", "Award numbers"),
            ("ror-ids", "ROR institution IDs"),
            ("similarity-checking", "Similarity checking"),
        ]

        # Analyze current metadata quality (for recent publications)
        quality_scores = {}
        for field, _description in quality_indicators:
            # Use current coverage if available, fallback to overall coverage
            score = coverage_current.get(field, coverage.get(field, 0))
            quality_scores[field] = score
            metrics[f"{field}_coverage"] = score

        # Calculate overall metadata quality score
        important_fields = [
            "orcids",
            "funders",
            "licenses",
            "abstracts",
            "affiliations",
        ]
        overall_quality = sum(
            quality_scores.get(field, 0) for field in important_fields
        ) / len(important_fields)
        metrics["overall_metadata_quality"] = overall_quality

        return metrics, quality_scores

    def _check_metadata_green_flags(
        self, metrics: dict[str, Any], quality_scores: dict[str, float]
    ) -> list[str]:
        """Check for metadata quality green flags.

        Args:
            metrics: Dictionary of calculated metrics
            quality_scores: Dictionary of quality scores

        Returns:
            List of green flag descriptions
        """
        green_flags = []

        total_dois = metrics["total_dois"]
        overall_quality = metrics["overall_metadata_quality"]

        # Extract quality scores
        orcid_score = quality_scores.get("orcids", 0)
        funders_score = quality_scores.get("funders", 0)
        license_score = quality_scores.get("licenses", 0)
        references_score = quality_scores.get("references", 0)

        # GREEN FLAGS (indicators of legitimate practices)

        # High ORCID adoption indicates professional publishing practices
        orcid_flag = self._check_orcid_quality(orcid_score)
        if orcid_flag:
            green_flags.append(orcid_flag)

        # Funding data indicates proper research documentation
        funding_flag = self._check_funding_quality(funders_score)
        if funding_flag:
            green_flags.append(funding_flag)

        # License information indicates proper open access practices
        license_flag = self._check_license_quality(license_score)
        if license_flag:
            green_flags.append(license_flag)

        # Reference linking indicates scholarly rigor
        if references_score >= _REFERENCE_GOOD:
            green_flags.append(
                f"Good reference linking: {references_score}% of articles have linked references"
            )

        # Overall high metadata quality
        if overall_quality >= _QUALITY_HIGH:
            green_flags.append(
                f"High overall metadata quality: {overall_quality:.1f}% average across key fields"
            )
        elif overall_quality >= _QUALITY_GOOD:
            green_flags.append(
                f"Good overall metadata quality: {overall_quality:.1f}% average across key fields"
            )

        # Substantial publication volume indicates established operation
        if total_dois >= _DOI_MAJOR:
            green_flags.append(
                f"Major publisher volume: {total_dois:,} DOIs registered (well-established)"
            )
        elif total_dois >= _DOI_LARGE:
            green_flags.append(
                f"Large publication volume: {total_dois:,} DOIs registered"
            )
        elif total_dois >= _DOI_SUBSTANTIAL:
            green_flags.append(
                f"Substantial publication volume: {total_dois:,} DOIs registered"
            )

        return green_flags

    def _check_metadata_red_flags(
        self,
        metrics: dict[str, Any],
        quality_scores: dict[str, float],
        journal_data: dict[str, Any],
    ) -> list[str]:
        """Check for metadata quality red flags.

        Args:
            metrics: Dictionary of calculated metrics
            quality_scores: Dictionary of quality scores
            journal_data: Raw journal data from Crossref

        Returns:
            List of red flag descriptions
        """
        red_flags = []

        total_dois = metrics["total_dois"]
        overall_quality = metrics["overall_metadata_quality"]
        dois_by_year = metrics.get("dois_by_year", [])

        # Extract quality scores
        orcid_score = quality_scores.get("orcids", 0)
        funders_score = quality_scores.get("funders", 0)
        license_score = quality_scores.get("licenses", 0)

        # RED FLAGS (indicators of poor practices)

        # Very low ORCID adoption suggests poor editorial standards
        # BUT: account for established journals with lots of historical content
        if orcid_score < _ORCID_VERY_LOW and self._is_small_to_medium_journal(
            total_dois
        ):
            # Only flag if it's a smaller journal (not a major established one)
            red_flags.append(
                f"Very low ORCID adoption: only {orcid_score}% of articles include author ORCIDs"
            )
        elif orcid_score < _ORCID_LOW and _DOI_MEDIUM <= total_dois < _DOI_MEDIUM * 100:
            # Moderate flag for medium-sized journals
            red_flags.append(
                f"Low ORCID adoption: only {orcid_score}% of articles include author ORCIDs"
            )

        # No funding information suggests poor research documentation
        # BUT: account for established journals and regional differences
        if funders_score < _FUNDING_MINIMAL and self._is_small_to_medium_journal(
            total_dois
        ):
            red_flags.append(
                f"Minimal funding transparency: only {funders_score}% of articles include funding information"
            )

        # Poor license documentation (mainly relevant for open access journals)
        if license_score < _LICENSE_POOR and self._is_small_to_medium_journal(
            total_dois
        ):
            red_flags.append(
                f"Poor license documentation: only {license_score}% of articles have license information"
            )

        # Overall poor metadata quality
        if overall_quality < _QUALITY_POOR:
            red_flags.append(
                f"Poor overall metadata quality: {overall_quality:.1f}% average across key fields"
            )
        elif overall_quality < _QUALITY_LOW:
            red_flags.append(
                f"Low overall metadata quality: {overall_quality:.1f}% average across key fields"
            )

        # Very new publisher with minimal metadata quality
        if (
            self._is_very_small_journal(total_dois)
            and overall_quality < _QUALITY_POOR_PRACTICES
        ):
            red_flags.append(
                f"New operation with poor practices: only {total_dois} DOIs and {overall_quality:.1f}% metadata quality"
            )

        # Recent DOI registration patterns
        if dois_by_year:
            # Sort by year and check for sudden spikes
            # dois_by_year format: [[year, count], [year, count], ...]
            yearly_counts = {
                int(item[0]): item[1]
                for item in dois_by_year
                if isinstance(item, list)
                and len(item) >= 2
                and isinstance(item[0], int)
            }
            if len(yearly_counts) >= 3:
                sorted_years = sorted(yearly_counts.keys())
                recent_years = sorted_years[-3:]

                # Check for recent explosion in volume
                if len(recent_years) >= 2:
                    latest_year_count = yearly_counts[recent_years[-1]]
                    previous_avg = sum(
                        yearly_counts[year] for year in recent_years[:-1]
                    ) / (len(recent_years) - 1)

                    if (
                        latest_year_count > previous_avg * _EXPLOSION_MULTIPLIER
                        and latest_year_count > _EXPLOSION_MIN_COUNT
                    ):
                        red_flags.append(
                            f"Recent publication explosion: {latest_year_count} DOIs in {recent_years[-1]} vs {previous_avg:.0f} average"
                        )

        return red_flags

    def _determine_metadata_assessment(
        self, red_flags: list[str], green_flags: list[str], metrics: dict[str, Any]
    ) -> tuple[str | None, float]:
        """Determine final assessment and confidence based on metadata flags.

        Args:
            red_flags: List of red flag descriptions
            green_flags: List of green flag descriptions
            metrics: Dictionary of calculated metrics

        Returns:
            Tuple of (assessment, confidence)
        """
        total_dois = metrics["total_dois"]

        # Assessment logic
        red_flag_weight = len(red_flags)
        green_flag_weight = len(green_flags)

        # Base confidence on metadata quality and flags
        if red_flag_weight >= 2:
            assessment = AssessmentType.PREDATORY
            confidence = min(0.80, 0.55 + red_flag_weight * 0.05)
        elif green_flag_weight >= 2:
            assessment = AssessmentType.LEGITIMATE
            confidence = min(0.85, 0.65 + green_flag_weight * 0.04)
        elif red_flag_weight == 1 and green_flag_weight == 0:
            assessment = AssessmentType.PREDATORY
            confidence = 0.50
        elif green_flag_weight == 1 and red_flag_weight == 0:
            assessment = AssessmentType.LEGITIMATE
            confidence = 0.55
        else:
            assessment = None
            confidence = 0.30

        # Adjust confidence based on data volume
        confidence = self._adjust_confidence_by_volume(confidence, total_dois)

        return assessment, confidence


# Register the backend with factory for configuration support
get_backend_registry().register_factory(
    "crossref_analyzer",
    lambda email="noreply@aletheia-probe.org",
    cache_ttl_hours=24: CrossrefAnalyzerBackend(
        email=email, cache_ttl_hours=cache_ttl_hours
    ),
    default_config={"email": "noreply@aletheia-probe.org", "cache_ttl_hours": 24},
)
