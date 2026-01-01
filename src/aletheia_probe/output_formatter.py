# SPDX-License-Identifier: MIT
"""Enhanced output formatting for journal assessment results."""

from .enums import AssessmentType
from .models import AssessmentResult, BackendResult, BackendStatus


class OutputFormatter:
    """Formats assessment results with detailed explanations and recommendations."""

    def format_text_output(
        self, result: AssessmentResult, publication_type: str, verbose: bool
    ) -> str:
        """Format assessment result as enhanced text output.

        Args:
            result: Assessment result to format
            publication_type: Type of publication (journal, conference)
            verbose: Whether to include verbose details

        Returns:
            Formatted text output string
        """
        lines = []

        # Header with publication name
        label = "Conference" if publication_type == "conference" else "Journal"
        lines.append(f"{label}: {result.input_query}")

        # Acronym expansion note
        if result.acronym_expansion_used and result.acronym_expanded_from:
            lines.append(
                f"Note: Expanded acronym '{result.acronym_expanded_from}' using cached mapping"
            )

        # Assessment summary
        lines.append(f"Assessment: {result.assessment.upper()}")
        lines.append(f"Confidence: {result.confidence:.2f}")
        lines.append(f"Overall Score: {result.overall_score:.2f}")
        lines.append(f"Processing Time: {result.processing_time:.2f}s")

        # Detailed analysis section
        if verbose:
            lines.append(self._format_detailed_analysis(result))

        # Backend results (always show in verbose mode)
        if verbose and result.backend_results:
            lines.append(self._format_backend_results(result.backend_results))

        # Reasoning (show if available)
        if result.reasoning:
            lines.append("\nReasoning:")
            for reason in result.reasoning:
                lines.append(f"  • {reason}")

        # Recommendation
        lines.append(self._format_recommendation(result))

        return "\n".join(lines)

    def _format_detailed_analysis(self, result: AssessmentResult) -> str:
        """Format detailed analysis section with metrics and flags.

        Args:
            result: Assessment result containing backend data

        Returns:
            Formatted detailed analysis section
        """
        lines = ["\nDetailed Analysis:"]

        # Find OpenAlex analyzer result for detailed metrics
        openalex_result = self._find_backend_result(result, "openalex_analyzer")
        if openalex_result and openalex_result.status == BackendStatus.FOUND:
            lines.append(self._format_openalex_analysis(openalex_result))

        # Publication pattern indicators
        lines.append(self._format_quality_indicators(result))

        # List presence
        lines.append(self._format_list_presence(result))

        # Conflicting signals warning
        conflicting_msg = self._check_conflicting_signals(result)
        if conflicting_msg:
            lines.append(f"\n  {conflicting_msg}")

        return "\n".join(lines)

    def _format_openalex_analysis(self, openalex_result: BackendResult) -> str:
        """Format OpenAlex analysis metrics.

        Args:
            openalex_result: Backend result from OpenAlex analyzer

        Returns:
            Formatted OpenAlex metrics section
        """
        lines = ["  Publication Pattern (OpenAlex):"]

        data = openalex_result.data
        metrics = data.get("metrics", {})

        if not metrics:
            return ""

        # Extract metrics
        years_active = metrics.get("years_active", 0)
        total_pubs = metrics.get("total_publications", 0)
        pub_rate = metrics.get("publication_rate_per_year", 0)
        citation_ratio = metrics.get("citation_ratio", 0)
        first_year = metrics.get("first_year")
        last_year = metrics.get("last_year")
        pub_type = data.get("publication_type", "journal")

        # Format basic metrics
        if first_year and last_year:
            lines.append(
                f"    • Years active: {years_active} years ({first_year}-{last_year})"
            )
        elif years_active:
            lines.append(f"    • Years active: {years_active} years")

        if total_pubs:
            lines.append(f"    • Total publications: {total_pubs:,} papers")

        if pub_rate:
            flag = " [⚠️ Publication mill pattern]" if pub_rate > 1000 else ""
            lines.append(f"    • Publication rate: {pub_rate:.0f} papers/year{flag}")

        if citation_ratio is not None:
            flag = " [⚠️ Very low]" if citation_ratio < 1.0 else ""
            lines.append(
                f"    • Citation ratio: {citation_ratio:.1f} citations/paper{flag}"
            )

        # Note publication type if it's a conference
        if pub_type == "conference":
            lines.append("    • Type: Conference proceedings")

        return "\n".join(lines)

    def _format_quality_indicators(self, result: AssessmentResult) -> str:
        """Format quality indicators (red and green flags).

        Args:
            result: Assessment result containing backend data

        Returns:
            Formatted quality indicators section
        """
        lines = ["\n  Quality Indicators:"]

        # Collect red and green flags from OpenAlex
        openalex_result = self._find_backend_result(result, "openalex_analyzer")
        red_flags: list[str] = []
        green_flags: list[str] = []

        if openalex_result and openalex_result.status == BackendStatus.FOUND:
            red_flags = openalex_result.data.get("red_flags", [])
            green_flags = openalex_result.data.get("green_flags", [])

        # Display red flags
        if red_flags:
            lines.append(f"    ⚠️  Red Flags ({len(red_flags)}):")
            for flag in red_flags:
                lines.append(f"      • {flag}")
        else:
            lines.append("    ⚠️  Red Flags: None detected")

        # Display green flags
        if green_flags:
            lines.append(f"    ✓ Green Flags ({len(green_flags)}):")
            for flag in green_flags:
                lines.append(f"      • {flag}")
        else:
            lines.append("    ✓ Green Flags: None detected")

        return "\n".join(lines)

    def _format_list_presence(self, result: AssessmentResult) -> str:
        """Format list presence section showing which databases found the venue.

        Args:
            result: Assessment result containing backend data

        Returns:
            Formatted list presence section
        """
        lines = ["\n  List Presence:"]

        # Key databases to check
        key_backends = [
            ("bealls", "Beall's List"),
            ("kscien_predatory_conferences", "Kscien Predatory Conferences"),
            ("kscien_standalone_journals", "Kscien Standalone Journals"),
            ("predatoryjournals", "PredatoryJournals.com"),
            ("doaj", "Directory of Open Access Journals (DOAJ)"),
            ("scopus", "Scopus"),
        ]

        for backend_name, display_name in key_backends:
            backend_result = self._find_backend_result(result, backend_name)
            if not backend_result:
                continue

            if backend_result.status == BackendStatus.FOUND:
                assessment = backend_result.assessment or "unknown"
                assessment_text = (
                    assessment.value
                    if hasattr(assessment, "value")
                    else str(assessment)
                )
                confidence = backend_result.confidence
                emoji = "•" if assessment == AssessmentType.PREDATORY else "✓"
                lines.append(
                    f"    {emoji} {display_name}: Found ({assessment_text}, confidence: {confidence:.2f})"
                )
            elif backend_result.status == BackendStatus.NOT_FOUND:
                lines.append(f"    ○ {display_name}: Not found")

        return "\n".join(lines)

    def _format_backend_results(self, backend_results: list[BackendResult]) -> str:
        """Format backend results section (technical details).

        Args:
            backend_results: List of backend results

        Returns:
            Formatted backend results section
        """
        lines = [f"\nBackend Results ({len(backend_results)}):"]

        for backend_result in backend_results:
            status_emoji = (
                "✓"
                if backend_result.status == BackendStatus.FOUND
                else ("✗" if backend_result.status == BackendStatus.NOT_FOUND else "⚠")
            )
            cache_indicator = " [cached]" if backend_result.cached else ""
            timing_info = ""
            if backend_result.execution_time_ms is not None:
                timing_info = f" ({backend_result.execution_time_ms:.2f}ms)"

            lines.append(
                f"  {status_emoji} {backend_result.backend_name}: {backend_result.status.value}{cache_indicator}{timing_info}"
            )

            if backend_result.assessment:
                assessment_text = (
                    backend_result.assessment.value
                    if hasattr(backend_result.assessment, "value")
                    else str(backend_result.assessment)
                )
                lines.append(
                    f"    → {assessment_text} (confidence: {backend_result.confidence:.2f})"
                )

            if backend_result.error_message:
                lines.append(f"    → Error: {backend_result.error_message}")

        return "\n".join(lines)

    def _format_recommendation(self, result: AssessmentResult) -> str:
        """Generate actionable recommendation based on assessment.

        Args:
            result: Assessment result

        Returns:
            Formatted recommendation string
        """
        assessment = result.assessment.lower()
        confidence = result.confidence

        lines = ["\nRecommendation:"]

        if assessment == AssessmentType.PREDATORY:
            if confidence >= 0.8:
                lines.append(
                    "  🚫 AVOID - Strong evidence of predatory characteristics detected"
                )
            elif confidence >= 0.6:
                lines.append(
                    "  ⚠️  AVOID - Multiple predatory indicators present, proceed with caution"
                )
            else:
                lines.append(
                    "  ⚠️  USE CAUTION - Some predatory indicators detected, investigate further"
                )
        elif assessment == AssessmentType.LEGITIMATE:
            if confidence >= 0.8:
                lines.append(
                    "  ✓ ACCEPTABLE - Strong evidence of legitimacy, appears trustworthy"
                )
            elif confidence >= 0.6:
                lines.append(
                    "  ✓ ACCEPTABLE - Generally legitimate, minor concerns if any"
                )
            else:
                lines.append(
                    "  ℹ️  INVESTIGATE - Appears legitimate but confidence is moderate"
                )
        elif assessment == AssessmentType.SUSPICIOUS:
            lines.append(
                "  ⚠️  INVESTIGATE - Mixed signals detected, requires careful evaluation"
            )
        else:  # insufficient_data or unknown
            lines.append(
                "  ℹ️  INSUFFICIENT DATA - Unable to make definitive assessment, research required"
            )

        # Add specific guidance based on conflicting signals
        conflicting = self._check_conflicting_signals(result)
        if conflicting and assessment == AssessmentType.PREDATORY:
            lines.append(
                "  Note: Despite some positive indicators, predatory patterns dominate the assessment"
            )

        return "\n".join(lines)

    def _check_conflicting_signals(self, result: AssessmentResult) -> str | None:
        """Check if there are conflicting signals from different backends.

        Args:
            result: Assessment result

        Returns:
            Conflict message if found, None otherwise
        """
        predatory_count = 0
        legitimate_count = 0

        for backend_result in result.backend_results:
            if (
                backend_result.status == BackendStatus.FOUND
                and backend_result.assessment
            ):
                if backend_result.assessment == AssessmentType.PREDATORY:
                    predatory_count += 1
                elif backend_result.assessment == AssessmentType.LEGITIMATE:
                    legitimate_count += 1

        if predatory_count > 0 and legitimate_count > 0:
            return (
                f"⚠️  CONFLICTING SIGNALS: {predatory_count} backend(s) report predatory, "
                f"{legitimate_count} report legitimate - review carefully"
            )

        return None

    def _find_backend_result(
        self, result: AssessmentResult, backend_name: str
    ) -> BackendResult | None:
        """Find a specific backend result by name.

        Args:
            result: Assessment result
            backend_name: Name of backend to find

        Returns:
            Backend result if found, None otherwise
        """
        for backend_result in result.backend_results:
            if backend_result.backend_name == backend_name:
                return backend_result
        return None


# Global formatter instance
output_formatter = OutputFormatter()
