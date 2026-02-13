# SPDX-License-Identifier: MIT
"""Batch processing of BibTeX files for acronym extraction.

This module provides parallel processing of multiple BibTeX files for efficient
acronym collection. It uses ProcessPoolExecutor to parse files in parallel,
then merges results and writes to the database using existing functions.

Design Decision: Local Extraction Without Database
==================================================
The parallel workers extract acronyms WITHOUT database access. This is necessary
because:
1. ProcessPoolExecutor spawns separate processes that can't share DB connections
2. SQLite doesn't handle concurrent writes well from multiple processes
3. Keeping workers stateless allows for better parallelization

Conflict detection against existing database entries happens AFTER parallel
processing completes, in the main process.
"""

from __future__ import annotations

import io
import os
import re
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from collections.abc import Callable

    from .models import BibtexEntry


@dataclass
class FileProcessingResult:
    """Result from processing a single BibTeX file.

    This is a lightweight data structure that can be serialized between
    processes. It contains the raw extraction results before database
    conflict detection.
    """

    file_path: Path
    # Raw mappings: list of (acronym, venue_name, normalized_name, entity_type)
    mappings: list[tuple[str, str, str, str]] = field(default_factory=list)
    # In-file conflicts: list of (acronym, entity_type, [(venue_name, count), ...])
    in_file_conflicts: list[tuple[str, str, list[tuple[str, int]]]] = field(
        default_factory=list
    )
    # Occurrence counts: dict of (acronym, entity_type, normalized_name) -> count
    occurrence_counts: dict[tuple[str, str, str], int] = field(default_factory=dict)
    entry_count: int = 0
    error: str | None = None


def normalize_venue_name_local(full_name: str) -> str:
    """Normalize venue name without database access.

    This is a local version of AcronymCache._normalize_venue_name() that
    doesn't require a database connection.

    Args:
        full_name: The full venue name (may include year/edition)

    Returns:
        Normalized venue name
    """
    from .normalizer import input_normalizer

    # Extract conference series (removes years, ordinals, "Proceedings of" prefix)
    series_name = input_normalizer.extract_conference_series(full_name.lower())

    if series_name:
        # Use the extracted series name
        return re.sub(r"\s+", " ", series_name).strip()
    else:
        # No normalization possible, use original (lowercased, whitespace normalized)
        return re.sub(r"\s+", " ", full_name.lower()).strip()


def extract_acronyms_local(
    entries: list[BibtexEntry],
    file_path: Path | None = None,
) -> FileProcessingResult:
    """Extract acronym mappings from BibTeX entries without database access.

    This is a simplified version of BibtexParser.extract_acronyms_from_entries()
    that works without a database connection. It:
    - Extracts acronyms from venue names
    - Detects conflicts WITHIN the file only
    - Does NOT check against existing database entries (done later in merge phase)
    - Does NOT store learned abbreviations (done later in merge phase)

    Args:
        entries: List of BibtexEntry objects to process
        file_path: Optional file path for result tracking

    Returns:
        FileProcessingResult with extracted mappings and in-file conflicts
    """
    from .normalizer import are_conference_names_equivalent, input_normalizer

    result = FileProcessingResult(
        file_path=file_path or Path("unknown"),
        entry_count=len(entries),
    )

    # Track mappings: (acronym, entity_type) -> list of (venue_name, normalized_name)
    mappings: dict[tuple[str, str], list[tuple[str, str]]] = {}

    for entry in entries:
        if not entry.journal_name:
            continue

        # Use normalizer to extract acronyms from venue name
        extracted_acronyms = input_normalizer._extract_acronyms(entry.journal_name)
        acronym_mappings = input_normalizer._extract_acronym_mappings_from_text(
            entry.journal_name, extracted_acronyms
        )

        # Store each acronym mapping
        for acronym, full_name in acronym_mappings.items():
            # Normalize the venue name (local version, no DB)
            normalized_name = normalize_venue_name_local(full_name)
            entity_type = entry.venue_type.value

            key = (acronym, entity_type)
            if key not in mappings:
                mappings[key] = []

            # Check if this normalized name is equivalent to any existing one
            # (avoid false positive conflicts)
            is_duplicate = False
            for _, existing_normalized in mappings[key]:
                if are_conference_names_equivalent(
                    normalized_name, existing_normalized
                ):
                    is_duplicate = True
                    break

            if not is_duplicate:
                mappings[key].append((full_name, normalized_name))

            # Track occurrence count (increment even if duplicate for accurate stats)
            count_key = (acronym, entity_type, normalized_name)
            result.occurrence_counts[count_key] = (
                result.occurrence_counts.get(count_key, 0) + 1
            )

    # Detect in-file conflicts and build result lists
    # Note: We don't check against database here - that happens in merge phase
    # Simplified for main's schema - uses basic equivalence checking only
    from .normalizer import are_conference_names_equivalent

    for (acronym, entity_type), venue_list in mappings.items():
        if len(venue_list) == 1:
            # Single mapping - no in-file conflict
            full_name, normalized_name = venue_list[0]
            result.mappings.append((acronym, full_name, normalized_name, entity_type))
        else:
            # Multiple venues for same acronym within file
            # Try to determine if they're equivalent using basic equivalence check
            reference_name = venue_list[0][1]
            all_equivalent = True
            for _, normalized in venue_list[1:]:
                if not are_conference_names_equivalent(reference_name, normalized):
                    all_equivalent = False
                    break

            if all_equivalent:
                # All venues are equivalent - use first one
                full_name, normalized_name = venue_list[0]
                result.mappings.append(
                    (acronym, full_name, normalized_name, entity_type)
                )
            else:
                # In-file conflict - record for later resolution
                venue_with_counts = [
                    (
                        normalized,
                        result.occurrence_counts.get(
                            (acronym, entity_type, normalized), 1
                        ),
                    )
                    for _, normalized in venue_list
                ]
                result.in_file_conflicts.append(
                    (acronym, entity_type, venue_with_counts)
                )

    return result


def process_single_file(file_path: Path) -> FileProcessingResult:
    """Process a single BibTeX file for acronym extraction.

    This function is designed for use with multiprocessing. It:
    - Creates its own BibtexParser instance (no shared state)
    - Does NOT access the database
    - Returns a lightweight result object

    Args:
        file_path: Path to the BibTeX file to process

    Returns:
        FileProcessingResult with extracted mappings
    """
    import pybtex.io  # type: ignore[import-untyped]

    from .bibtex_parser import BibtexParser

    try:
        # Suppress pybtex parser warnings
        old_pybtex_stderr = pybtex.io.stderr
        pybtex.io.stderr = io.StringIO()

        parser = BibtexParser()
        try:
            entries, _, _ = parser.parse_bibtex_file(file_path, relax_parsing=True)
        finally:
            pybtex.io.stderr = old_pybtex_stderr

        # Extract acronyms locally (no DB access)
        return extract_acronyms_local(entries, file_path)

    except Exception as e:
        return FileProcessingResult(
            file_path=file_path,
            error=str(e),
        )


def process_files_parallel(
    files: list[Path],
    max_workers: int | None = None,
    progress_callback: Callable[[int, int, Path], None] | None = None,
) -> list[FileProcessingResult]:
    """Process multiple BibTeX files in parallel.

    Uses ProcessPoolExecutor for CPU-bound BibTeX parsing.

    Args:
        files: List of file paths to process
        max_workers: Number of parallel workers (default: min(CPU count, 8, len(files)))
        progress_callback: Optional callback(completed, total, file_path) for progress

    Returns:
        List of FileProcessingResult objects
    """
    if not files:
        return []

    if max_workers is None:
        max_workers = min(os.cpu_count() or 4, len(files), 8)

    # For single file, just process directly (avoid process overhead)
    if len(files) == 1:
        result = process_single_file(files[0])
        if progress_callback:
            progress_callback(1, 1, files[0])
        return [result]

    results: list[FileProcessingResult] = []

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        future_to_file = {executor.submit(process_single_file, f): f for f in files}

        completed = 0
        for future in as_completed(future_to_file):
            completed += 1
            file_path = future_to_file[future]

            if progress_callback:
                progress_callback(completed, len(files), file_path)

            results.append(future.result())

    return results


def discover_bibtex_files(
    single_file: str | None = None,
    directory: str | None = None,
    recursive: bool = False,
) -> list[Path]:
    """Discover BibTeX files from various input methods.

    Args:
        single_file: Path to a single BibTeX file
        directory: Path to a directory containing BibTeX files
        recursive: If True, search subdirectories when using directory mode

    Returns:
        Sorted list of unique, resolved file paths
    """
    files: list[Path] = []

    if single_file:
        files.append(Path(single_file))

    if directory:
        dir_path = Path(directory)
        pattern = "**/*.bib" if recursive else "*.bib"
        files.extend(dir_path.glob(pattern))

    # Deduplicate and validate
    seen: set[Path] = set()
    unique_files: list[Path] = []
    for f in files:
        resolved = f.resolve()
        if resolved not in seen and resolved.is_file():
            seen.add(resolved)
            unique_files.append(resolved)

    return sorted(unique_files)


@dataclass
class MergedAcronymResult:
    """Result of merging acronym results across multiple files."""

    # New acronyms not in database: list of (acronym, venue_name, normalized, entity_type, count)
    new_acronyms: list[tuple[str, str, str, str, int]] = field(default_factory=list)
    # Existing acronyms already in database: list of (acronym, venue_name, normalized, entity_type, count)
    existing_acronyms: list[tuple[str, str, str, str, int]] = field(
        default_factory=list
    )
    # Conflicts: list of (acronym, entity_type, [(venue_name, count), ...])
    conflicts: list[tuple[str, str, list[tuple[str, int]]]] = field(
        default_factory=list
    )
    # Total files processed
    files_processed: int = 0
    # Files with errors
    files_with_errors: list[tuple[Path, str]] = field(default_factory=list)
    # Total entries processed
    total_entries: int = 0


def merge_file_results(
    results: list[FileProcessingResult],
    acronym_cache: AcronymCache,  # type: ignore[name-defined]  # noqa: F821
) -> MergedAcronymResult:
    """Merge results from multiple files and check against database.

    Uses the variant system with learned abbreviations for intelligent
    conflict resolution.

    This function:
    1. Aggregates mappings across all files
    2. Uses learned abbreviations to resolve cross-file variants
    3. Detects cross-file conflicts (same acronym -> truly different venues)
    4. Checks against existing database variants

    Args:
        results: List of FileProcessingResult from parallel processing
        acronym_cache: AcronymCache instance for database operations

    Returns:
        MergedAcronymResult with categorized acronyms
    """
    from .normalizer import are_conference_names_equivalent

    merged = MergedAcronymResult()

    # Track errors
    for result in results:
        merged.total_entries += result.entry_count
        merged.files_processed += 1
        if result.error:
            merged.files_with_errors.append((result.file_path, result.error))

    # Aggregate mappings across files
    # Key: (acronym, entity_type) -> dict of normalized_name -> (venue_name, total_count)
    aggregated: dict[tuple[str, str], dict[str, tuple[str, int]]] = {}

    for result in results:
        if result.error:
            continue

        for acronym, venue_name, normalized, entity_type in result.mappings:
            key = (acronym, entity_type)
            if key not in aggregated:
                aggregated[key] = {}

            count = result.occurrence_counts.get((acronym, entity_type, normalized), 1)

            if normalized in aggregated[key]:
                # Same normalized name - add counts
                existing_venue, existing_count = aggregated[key][normalized]
                aggregated[key][normalized] = (existing_venue, existing_count + count)
            else:
                aggregated[key][normalized] = (venue_name, count)

        # Also aggregate in-file conflicts
        for acronym, entity_type, venue_counts in result.in_file_conflicts:
            key = (acronym, entity_type)
            if key not in aggregated:
                aggregated[key] = {}

            for normalized, count in venue_counts:
                if normalized in aggregated[key]:
                    existing_venue, existing_count = aggregated[key][normalized]
                    aggregated[key][normalized] = (
                        existing_venue,
                        existing_count + count,
                    )
                else:
                    aggregated[key][normalized] = (normalized, count)

    # Now check each aggregated mapping against database using variant system
    for (acronym, entity_type), normalized_dict in aggregated.items():
        file_normalized_names = list(normalized_dict.keys())

        # Detect cross-file conflicts
        if len(file_normalized_names) > 1:
            reference_name = file_normalized_names[0]
            all_equivalent = all(
                are_conference_names_equivalent(reference_name, normalized)
                for normalized in file_normalized_names[1:]
            )

            if not all_equivalent:
                venue_with_counts = [
                    (normalized, normalized_dict[normalized][1])
                    for normalized in file_normalized_names
                ]
                merged.conflicts.append((acronym, entity_type, venue_with_counts))
                continue

        # Use the most frequent variant
        best_normalized = max(
            file_normalized_names, key=lambda n: normalized_dict[n][1]
        )
        venue_name, total_count = normalized_dict[best_normalized]

        # Check against database
        existing_variants = acronym_cache.get_variants(acronym, entity_type)
        if not existing_variants:
            merged.new_acronyms.append(
                (acronym, venue_name, best_normalized, entity_type, total_count)
            )
        else:
            existing_name = existing_variants[0]["normalized_name"]
            if are_conference_names_equivalent(best_normalized, existing_name):
                merged.existing_acronyms.append(
                    (acronym, venue_name, best_normalized, entity_type, total_count)
                )
            else:
                existing_count = max(v.get("usage_count", 0) for v in existing_variants)
                merged.conflicts.append(
                    (
                        acronym,
                        entity_type,
                        [
                            (best_normalized, total_count),
                            (existing_name, existing_count),
                        ],
                    )
                )

    return merged
