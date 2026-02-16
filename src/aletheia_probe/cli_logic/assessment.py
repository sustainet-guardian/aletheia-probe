# SPDX-License-Identifier: MIT
"""Assessment CLI workflow helpers."""

import json
import sys
from pathlib import Path

from ..batch_assessor import BibtexBatchAssessor
from ..cache import AcronymCache
from ..constants import DEFAULT_ACRONYM_CONFIDENCE_MIN
from ..dispatcher import query_dispatcher
from ..logging_config import get_status_logger
from ..models import VenueType
from ..normalizer import input_normalizer
from ..output_formatter import output_formatter
from ..publication_assessment_workflow import (
    assess_candidates as workflow_assess_candidates,
)
from ..publication_assessment_workflow import (
    build_publication_candidates as workflow_build_publication_candidates,
)
from ..publication_assessment_workflow import (
    finalize_publication_result as workflow_finalize_publication_result,
)
from ..publication_assessment_workflow import (
    persist_candidate_mappings as workflow_persist_candidate_mappings,
)
from ..publication_assessment_workflow import (
    resolve_candidate_selection as workflow_resolve_candidate_selection,
)
from ..validation import validate_issn
from .error_handling import handle_cli_exception
from .network import _resolve_issn_title


async def _async_bibtex_main(
    bibtex_file: str, verbose: bool, output_format: str, relax_bibtex: bool
) -> None:
    """Async main function for BibTeX assessment."""
    status_logger = get_status_logger()

    try:
        file_path = Path(bibtex_file)

        if verbose:
            status_logger.info(f"Assessing BibTeX file: {file_path}")

        result = await BibtexBatchAssessor.assess_bibtex_file(
            file_path, verbose, relax_bibtex
        )

        if output_format == "json":
            result_dict = result.model_dump()
            assessment_list = []
            for entry, assessment in result.assessment_results:
                assessment_list.append(
                    {"entry": entry.model_dump(), "assessment": assessment.model_dump()}
                )
            result_dict["assessment_results"] = assessment_list
            print(json.dumps(result_dict, indent=2, default=str))
        else:
            summary = BibtexBatchAssessor.format_summary(result, verbose)
            print(summary)

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
    """Async function for assessing publications with type specification."""
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

        if output_format == "json":
            print(json.dumps(result.model_dump(), indent=2, default=str))
        else:
            formatted_output = output_formatter.format_text_output(
                result, publication_type, verbose
            )
            print(formatted_output)

    except Exception as e:
        handle_cli_exception(e, verbose, "publication assessment")
