# SPDX-License-Identifier: MIT
"""Batch assessment module for evaluating multiple journals from BibTeX files."""

import time
from pathlib import Path

from .article_retraction_checker import ArticleRetractionChecker
from .bibtex_parser import BibtexParser
from .dispatcher import query_dispatcher
from .enums import AssessmentType
from .logging_config import get_detail_logger, get_status_logger
from .models import (
    VENUE_TYPE_EMOJI,
    AssessmentResult,
    BibtexAssessmentResult,
    BibtexEntry,
    VenueType,
)
from .normalizer import input_normalizer


class BibtexBatchAssessor:
    """Handles batch assessment of journals from BibTeX files.

    This class provides functionality to parse BibTeX bibliographic files and
    assess each journal entry for predatory indicators using multiple data sources.

    Examples:
        Basic usage:
        >>> from pathlib import Path
        >>> import asyncio
        >>> from aletheia_probe import BibtexBatchAssessor
        >>>
        >>> async def assess_my_refs():
        ...     assessor = BibtexBatchAssessor()
        ...     result = await assessor.assess_bibtex_file(
        ...         Path("references.bib"),
        ...         verbose=True
        ...     )
        ...     print(f"Assessed {result.total_entries} entries")
        ...     print(f"Found {result.predatory_count} predatory journals")
        ...     return result
        >>>
        >>> # Run the assessment
        >>> asyncio.run(assess_my_refs())

        Processing results:
        >>> result = await assessor.assess_bibtex_file(Path("refs.bib"))
        >>> for entry in result.entries:
        ...     if entry.assessment.classification == AssessmentType.PREDATORY:
        ...         print(f"Warning: {entry.journal_name}")
        ...         print(f"  Confidence: {entry.assessment.confidence:.0%}")
        ...         print(f"  Reasoning: {entry.assessment.reasoning[:100]}")
    """

    @staticmethod
    async def assess_bibtex_file(
        file_path: Path, verbose: bool = False, relax_bibtex: bool = False
    ) -> BibtexAssessmentResult:
        """Assess all journals in a BibTeX file.

        Args:
            file_path: Path to the BibTeX file
            verbose: Whether to enable verbose output
            relax_bibtex: If True, enable relaxed BibTeX parsing to handle malformed files

        Returns:
            BibtexAssessmentResult containing aggregated assessment results

        Raises:
            FileNotFoundError: If the BibTeX file doesn't exist
            ValueError: If the file cannot be parsed
        """
        detail_logger = get_detail_logger()
        status_logger = get_status_logger()

        start_time = time.time()

        status_logger.info(f"Parsing BibTeX file: {file_path}")
        detail_logger.debug(f"Starting BibTeX file assessment: {file_path}")

        # Parse the BibTeX file to extract journal entries
        try:
            bibtex_entries, skipped_count, arxiv_count = BibtexParser.parse_bibtex_file(
                file_path, relax_bibtex
            )
            detail_logger.debug(
                f"Successfully parsed {len(bibtex_entries)} entries, skipped {skipped_count}, found {arxiv_count} arXiv entries"
            )
        except Exception as e:
            detail_logger.error(f"Failed to parse BibTeX file: {e}")
            raise ValueError(f"Failed to parse BibTeX file: {e}") from e

        total_entries = len(bibtex_entries) + skipped_count + arxiv_count
        status_logger.info(
            f"Found {len(bibtex_entries)} entries with journal information"
        )

        # Prepare result object
        result = BibtexAssessmentResult(
            file_path=str(file_path),
            total_entries=total_entries,
            entries_with_journals=len(bibtex_entries),
            arxiv_entries_count=arxiv_count,
            skipped_entries_count=skipped_count,
            predatory_count=0,
            legitimate_count=0,
            insufficient_data_count=0,
            suspicious_count=0,
            conference_entries=0,
            conference_predatory=0,
            conference_legitimate=0,
            conference_suspicious=0,
            journal_entries=0,
            journal_predatory=0,
            journal_legitimate=0,
            journal_suspicious=0,
            has_predatory_journals=False,
            venue_type_counts={},
            retracted_articles_count=0,
            articles_checked_for_retraction=0,
            processing_time=0.0,  # Will be updated at the end
        )

        # Initialize article retraction checker
        retraction_checker = ArticleRetractionChecker()

        # Assess each journal
        assessment_results: list[tuple[BibtexEntry, AssessmentResult]] = []

        # Cache for venue assessments using case-insensitive normalized names
        venue_assessment_cache: dict[str, AssessmentResult] = {}

        for i, entry in enumerate(bibtex_entries, 1):
            status_logger.info(
                f"[{i}/{len(bibtex_entries)}] Assessing: {entry.journal_name}"
            )
            detail_logger.debug(
                f"Processing entry {i}/{len(bibtex_entries)}: {entry.journal_name} (type: {entry.entry_type})"
            )

            try:
                # Check for article retraction if DOI is available
                if entry.doi:
                    result.articles_checked_for_retraction += 1
                    detail_logger.debug(
                        f"Checking retraction status for DOI: {entry.doi}"
                    )
                    retraction_result = await retraction_checker.check_doi(entry.doi)

                    if retraction_result.is_retracted:
                        entry.is_retracted = True
                        entry.retraction_info = retraction_result.to_dict()
                        result.retracted_articles_count += 1
                        status_logger.warning(
                            f"[{i}/{len(bibtex_entries)}] RETRACTED ARTICLE: {entry.title or entry.key}"
                        )
                        detail_logger.warning(
                            f"Retraction details: type={retraction_result.retraction_type}, "
                            f"date={retraction_result.retraction_date}, "
                            f"sources={retraction_result.sources}"
                        )

                # Normalize the journal name for assessment
                query_input = input_normalizer.normalize(entry.journal_name)
                # Pass venue type information to the query
                query_input.venue_type = entry.venue_type
                detail_logger.debug(
                    f"Normalized journal name: {query_input.normalized_name}, venue type: {entry.venue_type.value}"
                )

                # Create a cache key using lowercase normalized name for case-insensitive matching
                cache_key = (
                    query_input.normalized_name.lower()
                    if query_input.normalized_name
                    else entry.journal_name.lower()
                )

                # Check if we've already assessed this venue (case-insensitive)
                if cache_key in venue_assessment_cache:
                    assessment = venue_assessment_cache[cache_key]
                    detail_logger.debug(
                        f"Using cached assessment for '{entry.journal_name}' (matches '{cache_key}')"
                    )
                    status_logger.info("    → Using cached result for case variant")
                else:
                    # Assess the journal
                    assessment = await query_dispatcher.assess_journal(query_input)
                    # Update venue type information in the assessment result
                    assessment.venue_type = entry.venue_type
                    detail_logger.debug(
                        f"Assessment result: {assessment.assessment}, confidence: {assessment.confidence:.2f}"
                    )
                    # Cache the assessment for future case variants
                    venue_assessment_cache[cache_key] = assessment

                # Store the result
                assessment_results.append((entry, assessment))

                # Determine if this is a conference or journal entry
                is_conference = entry.entry_type.lower() in [
                    "inproceedings",
                    "conference",
                    "proceedings",
                ]

                # Update type-specific counters
                if is_conference:
                    result.conference_entries += 1
                else:
                    result.journal_entries += 1

                # Update venue type counters
                result.venue_type_counts[entry.venue_type] = (
                    result.venue_type_counts.get(entry.venue_type, 0) + 1
                )

                # Update counters based on assessment
                if assessment.assessment == AssessmentType.PREDATORY:
                    result.predatory_count += 1
                    if is_conference:
                        result.conference_predatory += 1
                    else:
                        result.journal_predatory += 1
                elif assessment.assessment == AssessmentType.LEGITIMATE:
                    result.legitimate_count += 1
                    if is_conference:
                        result.conference_legitimate += 1
                    else:
                        result.journal_legitimate += 1
                elif assessment.assessment == AssessmentType.SUSPICIOUS:
                    result.suspicious_count += 1
                    if is_conference:
                        result.conference_suspicious += 1
                    else:
                        result.journal_suspicious += 1
                else:
                    result.insufficient_data_count += 1

                confidence_str = f"{assessment.confidence:.2f}"
                status_logger.info(
                    f"    → {assessment.assessment.upper()} (confidence: {confidence_str})"
                )

            except Exception as e:
                status_logger.warning(f"    → ERROR: {e}")
                detail_logger.exception(f"Error assessing {entry.journal_name}: {e}")
                # Create a mock assessment result for errors
                error_assessment = AssessmentResult(
                    input_query=entry.journal_name,
                    assessment="insufficient_data",
                    confidence=0.0,
                    overall_score=0.0,
                    backend_results=[],
                    metadata=None,
                    reasoning=[f"Error during assessment: {e}"],
                    processing_time=0.0,
                )
                assessment_results.append((entry, error_assessment))
                result.insufficient_data_count += 1

        # Finalize the result
        result.assessment_results = assessment_results
        result.has_predatory_journals = result.predatory_count > 0
        result.processing_time = time.time() - start_time

        return result

    @staticmethod
    def format_summary(result: BibtexAssessmentResult, verbose: bool = False) -> str:
        """Format a summary of the batch assessment results.

        Args:
            result: The batch assessment result
            verbose: Whether to include detailed information

        Returns:
            Formatted summary string
        """
        summary_lines = []

        # Header
        summary_lines.append("BibTeX Assessment Summary")
        summary_lines.append("=" * 40)
        summary_lines.append(f"File: {result.file_path}")
        summary_lines.append(f"Total entries in file: {result.total_entries}")
        summary_lines.append(f"Entries assessed: {result.entries_with_journals}")
        if result.arxiv_entries_count > 0:
            summary_lines.append(
                f"Skipped arXiv preprints: {result.arxiv_entries_count}"
            )
        if result.skipped_entries_count > 0:
            summary_lines.append(
                f"Skipped other entries: {result.skipped_entries_count}"
            )
        summary_lines.append(f"Processing time: {result.processing_time:.2f}s")
        summary_lines.append("")

        # Assessment summary
        summary_lines.append("Assessment Results:")
        summary_lines.append(f"  Predatory: {result.predatory_count} total")

        # Display venue types with assessment breakdown where available
        predatory_venue_display = [
            # Legacy counters with assessment breakdown
            (
                VENUE_TYPE_EMOJI[VenueType.JOURNAL],
                "Journals",
                result.journal_entries,
                result.journal_predatory,
            ),
            (
                VENUE_TYPE_EMOJI[VenueType.CONFERENCE],
                "Conferences",
                result.conference_entries,
                result.conference_predatory,
            ),
        ]

        for emoji, name, total_count, predatory_count in predatory_venue_display:
            if total_count > 0:
                summary_lines.append(
                    f"    {emoji} {name}: {predatory_count}/{total_count}"
                )

        # New venue types with total counts only
        predatory_venue_types = {
            VenueType.WORKSHOP: (VENUE_TYPE_EMOJI[VenueType.WORKSHOP], "Workshops"),
            VenueType.SYMPOSIUM: (VENUE_TYPE_EMOJI[VenueType.SYMPOSIUM], "Symposiums"),
        }
        for venue_type, (emoji, name) in predatory_venue_types.items():
            count = result.venue_type_counts.get(venue_type, 0)
            if count > 0:
                summary_lines.append(f"    {emoji} {name}: {count}")
        summary_lines.append(f"  Suspicious: {result.suspicious_count} total")

        # Display venue types with assessment breakdown for suspicious
        suspicious_venue_display = [
            (
                VENUE_TYPE_EMOJI[VenueType.JOURNAL],
                "Journals",
                result.journal_entries,
                result.journal_suspicious,
            ),
            (
                VENUE_TYPE_EMOJI[VenueType.CONFERENCE],
                "Conferences",
                result.conference_entries,
                result.conference_suspicious,
            ),
        ]

        for emoji, name, total_count, suspicious_count in suspicious_venue_display:
            if total_count > 0:
                summary_lines.append(
                    f"    {emoji} {name}: {suspicious_count}/{total_count}"
                )
        summary_lines.append(f"  Legitimate: {result.legitimate_count} total")

        # Display venue types with assessment breakdown for legitimate
        legitimate_venue_display = [
            (
                VENUE_TYPE_EMOJI[VenueType.JOURNAL],
                "Journals",
                result.journal_entries,
                result.journal_legitimate,
            ),
            (
                VENUE_TYPE_EMOJI[VenueType.CONFERENCE],
                "Conferences",
                result.conference_entries,
                result.conference_legitimate,
            ),
        ]

        for emoji, name, total_count, legitimate_count in legitimate_venue_display:
            if total_count > 0:
                summary_lines.append(
                    f"    {emoji} {name}: {legitimate_count}/{total_count}"
                )
        summary_lines.append(f"  Insufficient data: {result.insufficient_data_count}")

        # Venue type breakdown
        if result.venue_type_counts:
            summary_lines.append("")
            summary_lines.append("Venue Type Breakdown:")

            for venue_type, count in result.venue_type_counts.items():
                if count > 0:
                    emoji = VENUE_TYPE_EMOJI.get(venue_type, "❓")
                    type_name = venue_type.value.title() + (
                        "s" if venue_type != VenueType.UNKNOWN else " venue type"
                    )
                    summary_lines.append(f"  {emoji} {type_name}: {count}")
        summary_lines.append("")

        # Retraction summary
        if result.articles_checked_for_retraction > 0:
            summary_lines.append("Article Retraction Check:")
            summary_lines.append(
                f"  Articles checked: {result.articles_checked_for_retraction}"
            )
            summary_lines.append(
                f"  Retracted articles: {result.retracted_articles_count}"
            )
            if result.retracted_articles_count > 0:
                summary_lines.append("  ⚠️  WARNING: Retracted articles found!")
            summary_lines.append("")

        # Overall result
        if result.has_predatory_journals or result.retracted_articles_count > 0:
            warnings = []
            if result.has_predatory_journals:
                warnings.append("Predatory journals detected")
            if result.retracted_articles_count > 0:
                warnings.append("Retracted articles detected")
            summary_lines.append(f"⚠️  WARNING: {', '.join(warnings)}!")
        else:
            summary_lines.append(
                "✅ No predatory journals or retracted articles detected"
            )

        # Detailed results if verbose
        if verbose and result.assessment_results:
            summary_lines.append("")
            summary_lines.append("Detailed Results:")
            summary_lines.append("-" * 40)

            for entry, assessment in result.assessment_results:
                emoji_map: dict[str, str] = {
                    AssessmentType.PREDATORY.value: "❌",
                    AssessmentType.LEGITIMATE.value: "✅",
                    AssessmentType.SUSPICIOUS.value: "⚠️",
                    AssessmentType.UNKNOWN.value: "❓",
                }
                status_emoji = emoji_map.get(assessment.assessment, "❓")

                # Add retraction indicator
                retraction_indicator = ""
                if entry.is_retracted:
                    retraction_indicator = " 🚫 RETRACTED"

                # Add venue type indicator
                venue_type_emoji = VENUE_TYPE_EMOJI.get(entry.venue_type, "❓")

                summary_lines.append(
                    f"{status_emoji} {venue_type_emoji} {entry.journal_name} "
                    f"({assessment.assessment}, confidence: {assessment.confidence:.2f})"
                    f"{retraction_indicator}"
                )

                # Show retraction details if available
                if entry.is_retracted and entry.retraction_info:
                    retraction_type = entry.retraction_info.get(
                        "retraction_type", "unknown"
                    )
                    retraction_date = entry.retraction_info.get(
                        "retraction_date", "unknown"
                    )
                    summary_lines.append(
                        f"    🚫 RETRACTED: type={retraction_type}, date={retraction_date}"
                    )
                    if entry.retraction_info.get("retraction_reason"):
                        summary_lines.append(
                            f"       Reason: {entry.retraction_info['retraction_reason']}"
                        )

                # Show reasoning if available
                if assessment.reasoning:
                    for reason in assessment.reasoning[:2]:  # Show first 2 reasons
                        summary_lines.append(f"    • {reason}")

        return "\n".join(summary_lines)

    @staticmethod
    def get_exit_code(result: BibtexAssessmentResult) -> int:
        """Get the appropriate exit code based on assessment results.

        Args:
            result: The batch assessment result

        Returns:
            0 if no issues found, 1 if predatory journals or retracted articles found
        """
        return (
            1
            if (result.has_predatory_journals or result.retracted_articles_count > 0)
            else 0
        )
