"""Crossref backend with metadata quality analysis for predatory journal detection."""

import asyncio
import time
from typing import Any

import aiohttp

from ..constants import (
    MIN_ABSTRACT_LENGTH,
    MIN_AUTHOR_INFO_COMPLETENESS,
    MIN_REFERENCE_COUNT,
)
from ..models import BackendResult, BackendStatus, QueryInput
from .base import HybridBackend, get_backend_registry


class CrossrefAnalyzerBackend(HybridBackend):
    """Backend that analyzes Crossref metadata quality to assess journal legitimacy."""

    def __init__(
        self, email: str = "noreply.aletheia-probe.org", cache_ttl_hours: int = 24
    ):
        """Initialize Crossref analyzer backend.

        Args:
            email: Email for Crossref polite pool access
            cache_ttl_hours: Cache TTL in hours
        """
        super().__init__(cache_ttl_hours)
        self.email = email
        self.base_url = "https://api.crossref.org"
        self.headers = {
            "User-Agent": f"AletheiaProbe/1.0 (mailto:{email})",
        }

    def get_name(self) -> str:
        """Return backend name."""
        return "Crossref Analyzer"

    def get_description(self) -> str:
        """Return backend description."""
        return "Analyzes metadata quality and publisher information from Crossref to detect predatory journals"

    async def _query_api(self, query_input: QueryInput) -> BackendResult:
        """Query Crossref API and analyze metadata quality."""
        start_time = time.time()

        try:
            # Try to find journal by ISSN first
            journal_data = None
            issn = query_input.identifiers.get("issn")
            eissn = query_input.identifiers.get("eissn")

            if issn:
                journal_data = await self._get_journal_by_issn(issn)

            if not journal_data and eissn:
                journal_data = await self._get_journal_by_issn(eissn)

            response_time = time.time() - start_time

            if not journal_data:
                # Not found in Crossref
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
            analysis = self._analyze_metadata_quality(journal_data)

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

        async with aiohttp.ClientSession(
            headers=self.headers, timeout=aiohttp.ClientTimeout(total=30)
        ) as session:
            try:
                async with session.get(url) as response:
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
        publisher = metrics["publisher"]

        # Extract quality scores
        orcid_score = quality_scores.get("orcids", 0)
        funders_score = quality_scores.get("funders", 0)
        license_score = quality_scores.get("licenses", 0)
        references_score = quality_scores.get("references", 0)

        # GREEN FLAGS (indicators of legitimate practices)

        # High ORCID adoption indicates professional publishing practices
        orcid_score = quality_scores.get("orcids", 0)
        if orcid_score >= 70:
            green_flags.append(
                f"High ORCID adoption: {orcid_score}% of articles include author ORCIDs"
            )
        elif orcid_score >= 40:
            green_flags.append(
                f"Good ORCID adoption: {orcid_score}% of articles include author ORCIDs"
            )

        # Funding data indicates proper research documentation
        funders_score = quality_scores.get("funders", 0)
        if funders_score >= 40:
            green_flags.append(
                f"Good funding transparency: {funders_score}% of articles include funding information"
            )
        elif funders_score >= 20:
            green_flags.append(
                f"Moderate funding transparency: {funders_score}% of articles include funding information"
            )

        # License information indicates proper open access practices
        license_score = quality_scores.get("licenses", 0)
        if license_score >= 80:
            green_flags.append(
                f"Excellent license documentation: {license_score}% of articles have license information"
            )
        elif license_score >= MIN_ABSTRACT_LENGTH:
            green_flags.append(
                f"Good license documentation: {license_score}% of articles have license information"
            )

        # Reference linking indicates scholarly rigor
        references_score = quality_scores.get("references", 0)
        if references_score >= 60:
            green_flags.append(
                f"Good reference linking: {references_score}% of articles have linked references"
            )

        # Overall high metadata quality
        if overall_quality >= 60:
            green_flags.append(
                f"High overall metadata quality: {overall_quality:.1f}% average across key fields"
            )
        elif overall_quality >= 40:
            green_flags.append(
                f"Good overall metadata quality: {overall_quality:.1f}% average across key fields"
            )

        # Publisher assessment (basic name check for known legitimate publishers)
        known_publishers = [
            "springer",
            "elsevier",
            "wiley",
            "ieee",
            "acm",
            "nature",
            "science",
            "taylor & francis",
            "sage",
            "oxford",
            "cambridge",
            "mit press",
            "american chemical society",
            "royal society",
            "plos",
            "frontiers",
            "mdpi",
            "bmj",
            "lancet",
            "karger",
            "thieme",
        ]

        publisher_lower = publisher.lower()
        is_known_publisher = any(known in publisher_lower for known in known_publishers)
        if is_known_publisher:
            green_flags.append(f"Recognized publisher: {publisher}")

        # Substantial publication volume indicates established operation
        if total_dois >= 100000:
            green_flags.append(
                f"Major publisher volume: {total_dois:,} DOIs registered (well-established)"
            )
        elif total_dois >= 10000:
            green_flags.append(
                f"Large publication volume: {total_dois:,} DOIs registered"
            )
        elif total_dois >= 1000:
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
        publisher = metrics["publisher"]
        dois_by_year = metrics.get("dois_by_year", [])

        # Extract quality scores
        orcid_score = quality_scores.get("orcids", 0)
        funders_score = quality_scores.get("funders", 0)
        license_score = quality_scores.get("licenses", 0)

        # RED FLAGS (indicators of poor practices)

        # Very low ORCID adoption suggests poor editorial standards
        # BUT: account for established journals with lots of historical content
        if orcid_score < 5 and total_dois >= 100 and total_dois < 10000:
            # Only flag if it's a smaller journal (not a major established one)
            red_flags.append(
                f"Very low ORCID adoption: only {orcid_score}% of articles include author ORCIDs"
            )
        elif (
            orcid_score < MIN_REFERENCE_COUNT
            and total_dois >= 500
            and total_dois < 50000
        ):
            # Moderate flag for medium-sized journals
            red_flags.append(
                f"Low ORCID adoption: only {orcid_score}% of articles include author ORCIDs"
            )

        # No funding information suggests poor research documentation
        # BUT: account for established journals and regional differences
        if funders_score < 2 and total_dois >= 100 and total_dois < 10000:
            red_flags.append(
                f"Minimal funding transparency: only {funders_score}% of articles include funding information"
            )

        # Poor license documentation (mainly relevant for open access journals)
        if license_score < 5 and total_dois >= 100 and total_dois < 10000:
            red_flags.append(
                f"Poor license documentation: only {license_score}% of articles have license information"
            )

        # Overall poor metadata quality
        if overall_quality < 15:
            red_flags.append(
                f"Poor overall metadata quality: {overall_quality:.1f}% average across key fields"
            )
        elif overall_quality < 25:
            red_flags.append(
                f"Low overall metadata quality: {overall_quality:.1f}% average across key fields"
            )

        # Suspicious publisher names (basic heuristics)
        suspicious_words = [
            "international",
            "global",
            "world",
            "universal",
            "advanced",
            "modern",
            "open",
        ]

        # Define publisher variables needed for analysis
        publisher_lower = publisher.lower()
        known_publishers = [
            "springer",
            "elsevier",
            "wiley",
            "ieee",
            "acm",
            "oxford",
            "cambridge",
            "nature",
            "science",
            "cell",
            "plos",
            "bmj",
            "nejm",
            "lancet",
            "karger",
            "thieme",
        ]
        is_known_publisher = any(known in publisher_lower for known in known_publishers)

        publisher_words = publisher_lower.split()
        suspicious_count = sum(
            1 for word in suspicious_words if word in publisher_words
        )
        if suspicious_count >= 2 and not is_known_publisher:
            red_flags.append(
                f"Potentially suspicious publisher name: '{publisher}' contains multiple generic terms"
            )

        # Very new publisher with minimal metadata quality
        if total_dois < MIN_ABSTRACT_LENGTH and overall_quality < 30:
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

                    if latest_year_count > previous_avg * 3 and latest_year_count > 500:
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
            assessment = "predatory"
            confidence = min(0.80, 0.55 + red_flag_weight * 0.05)
        elif green_flag_weight >= 2:
            assessment = "legitimate"
            confidence = min(0.85, 0.65 + green_flag_weight * 0.04)
        elif red_flag_weight == 1 and green_flag_weight == 0:
            assessment = "predatory"
            confidence = 0.50
        elif green_flag_weight == 1 and red_flag_weight == 0:
            assessment = "legitimate"
            confidence = 0.55
        else:
            assessment = None
            confidence = 0.30

        # Adjust confidence based on data volume (more DOIs = more reliable assessment)
        if total_dois >= 1000:
            confidence = min(
                1.0, confidence * 1.1
            )  # Boost confidence for high-volume publishers
        elif total_dois < MIN_ABSTRACT_LENGTH:
            confidence = max(
                0.1, confidence * MIN_AUTHOR_INFO_COMPLETENESS
            )  # Reduce confidence for low-volume publishers

        return assessment, confidence

    def _generate_reasoning(
        self, red_flags: list[str], green_flags: list[str], metrics: dict[str, Any]
    ) -> list[str]:
        """Generate human-readable reasoning for the assessment."""
        reasoning = []

        if green_flags:
            reasoning.append("Positive metadata indicators:")
            reasoning.extend([f"  • {flag}" for flag in green_flags])

        if red_flags:
            reasoning.append("Concerning metadata patterns:")
            reasoning.extend([f"  • {flag}" for flag in red_flags])

        # Add summary statistics
        reasoning.append(f"Publisher: {metrics['publisher']}")
        reasoning.append(f"Total DOIs registered: {metrics['total_dois']:,}")
        reasoning.append(
            f"Overall metadata quality: {metrics['overall_metadata_quality']:.1f}%"
        )

        if not green_flags and not red_flags:
            reasoning.append("Limited metadata available for assessment")

        return reasoning


# Register the backend
get_backend_registry().register(CrossrefAnalyzerBackend())
