# SPDX-License-Identifier: MIT
"""BibTeX parsing utilities for journal assessment."""

import re
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from pybtex import errors as pybtex_errors  # type: ignore
from pybtex.database import (  # type: ignore
    BibliographyData,
    Entry,
    parse_file,
)
from pybtex.scanner import PybtexError, PybtexSyntaxError  # type: ignore

from .cache import AcronymCache
from .logging_config import get_detail_logger, get_status_logger
from .models import BibtexEntry, VenueType


detail_logger = get_detail_logger()
status_logger = get_status_logger()


# Comprehensive patterns for arXiv (all variants from real-world data)
ARXIV_PREPRINT_PATTERNS: list[str] = [
    # Standard arXiv patterns
    r"arxiv\s*preprint\s*(?:arxiv\s*:)?\s*\d{4}\.\d{5}(?:v\d+)?",  # arXiv preprint arXiv:XXXX.XXXXX
    r"arxiv\s*preprint\s*:?\s*\d{4}\.\d{5}(?:v\d+)?",  # ArXivPreprint:2510.09378
    r"arxiv\s*e-?prints?",  # ArXiv e-prints, ArXive-prints
    r"arxiv:\d{4}\.\d{5}(?:v\d+)?",  # bare arXiv identifier
    r"arxiv:\w+\.\w+(?:v\d+)?",  # arXiv:cs.AI/9901001 (old style)
    r"eprint:\s*arxiv",  # for entries where eprint field is "eprint = {arXiv}"
    # ArXiv with classifications and institutional info
    r"arxiv\s*\[[^\]]+\]",  # arXiv with subject classification (e.g., "arXiv [cs.LG]")
    r"arxiv\s*\([^)]*\)",  # arXiv with parenthetical info (e.g., "arXiv (Cornell University)")
    # Common variants found in real bibliographies
    r"\barxive?\s*preprints?\b",  # ArXivpreprint, ArXivepreprint
    r"\barxive?\b",  # Just "ArXiv" or "ArXive" as word boundary
    r"^arxive?$",  # Just "ArXiv" or "ArXive" as whole field
    r"^arxive?\s*preprints?",  # ArXiv preprint at start
    r"arxive?\s*preprints?\s*$",  # ArXiv preprint at end
]

# Patterns for other legitimate preprint repositories
OTHER_PREPRINT_PATTERNS: list[str] = [
    # bioRxiv - biology preprints
    r"biorxiv",
    r"bio\s*rxiv",
    r"www\.biorxiv\.org",
    r"doi\.org/10\.1101/",
    # SSRN - social sciences preprints
    r"ssrn\s*electronic\s*journal",
    r"social\s*science\s*research\s*network",
    r"ssrn\.com",
    r"\bssrn\b",
    # medRxiv - medical preprints
    r"medrxiv",
    r"med\s*rxiv",
    r"www\.medrxiv\.org",
    # Zenodo - multidisciplinary repository
    r"\bzenodo\b",
    r"zenodo\.org",
    r"doi\.org/10\.5281/zenodo",
    # Other legitimate preprint repositories
    r"psyarxiv",  # Psychology preprints
    r"socarxiv",  # Social sciences preprints
    r"eartharxiv",  # Earth sciences preprints
    r"engrxiv",  # Engineering preprints
    r"techrxiv",  # IEEE preprints
    r"preprints\.org",  # MDPI preprints
    r"research\s*square",  # Research Square preprints
    r"researchsquare\.com",
    r"osf\.io/preprints",  # Open Science Framework preprints
    r"chemrxiv",  # Chemistry preprints
    r"authorea\.com",  # Authorea preprints platform
]


class BibtexParser:
    """Parser for BibTeX files to extract journal information."""

    @staticmethod
    @contextmanager
    def _configure_pybtex(relax_parsing: bool) -> Generator[None, None, None]:
        """Configure pybtex parsing mode and restore original settings after use.

        Args:
            relax_parsing: If True, enable lenient parsing mode

        Yields:
            None
        """
        original_strict_mode = pybtex_errors.strict
        try:
            if relax_parsing:
                detail_logger.debug("Enabling relaxed BibTeX parsing mode")
                pybtex_errors.set_strict_mode(False)
            else:
                detail_logger.debug("Using strict BibTeX parsing mode")
                pybtex_errors.set_strict_mode(True)
            yield
        finally:
            # Restore original strict mode setting
            pybtex_errors.set_strict_mode(original_strict_mode)

    @staticmethod
    def _process_all_entries(
        bib_data: BibliographyData, max_workers: int
    ) -> tuple[list[BibtexEntry], int, int]:
        """Process all BibTeX entries in parallel and categorize results.

        Args:
            bib_data: Parsed bibliography data
            max_workers: Maximum number of parallel workers

        Returns:
            Tuple of (processed_entries, skipped_entries, preprint_entries)
        """
        entries = []
        skipped_entries = 0
        preprint_entries = 0

        # Process all entries in parallel for improved performance
        entries_list = list(bib_data.entries.items())
        detail_logger.debug(
            f"Processing {len(entries_list)} entries with {max_workers} workers"
        )

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all entry processing tasks
            future_to_entry = {
                executor.submit(
                    BibtexParser._process_single_entry, entry_key, entry
                ): entry_key
                for entry_key, entry in entries_list
            }

            # Collect results as they complete
            for future in as_completed(future_to_entry):
                entry_key = future_to_entry[future]
                try:
                    result = future.result()
                    if result["type"] == "preprint":
                        preprint_entries += 1
                        detail_logger.debug(f"Skipping preprint entry: {entry_key}")
                    elif result["type"] == "processed":
                        entries.append(result["entry"])
                    elif result["type"] == "skipped":
                        skipped_entries += 1
                except Exception as e:
                    status_logger.warning(
                        f"Skipping entry '{entry_key}' due to processing error: {e}"
                    )
                    skipped_entries += 1

        return entries, skipped_entries, preprint_entries

    @staticmethod
    def _log_parsing_results(
        file_path: Path,
        encoding_description: str,
        entries: list[BibtexEntry],
        skipped_entries: int,
        preprint_entries: int,
    ) -> None:
        """Log the results of BibTeX parsing.

        Args:
            file_path: Path to the parsed file
            encoding_description: Description of encoding used
            entries: List of successfully processed entries
            skipped_entries: Number of entries skipped due to processing errors
            preprint_entries: Number of preprint entries detected and skipped
        """
        # Log parsing results with clear messaging
        detail_logger.debug(
            f"Successfully parsed {len(entries)} entries from {file_path.name} "
            f"with {encoding_description}"
        )

        # Log skipped preprints at debug level only
        if preprint_entries > 0:
            detail_logger.debug(
                f"Skipped {preprint_entries} preprint(s) from legitimate repositories - not publication venues"
            )

        # Log other skipped entries
        if skipped_entries > 0:
            detail_logger.debug(
                f"Skipped {skipped_entries} other entries due to processing errors"
            )

    @staticmethod
    def _parse_with_encoding_fallback(
        file_path: Path, max_workers: int
    ) -> tuple[list[BibtexEntry], int, int]:
        """Parse a BibTeX file with encoding fallback strategies.

        Args:
            file_path: Path to the BibTeX file
            max_workers: Maximum number of parallel workers

        Returns:
            Tuple of (processed_entries, skipped_entries, preprint_entries)

        Raises:
            ValueError: If the file has invalid BibTeX syntax or parsing fails
            UnicodeDecodeError: If the file encoding is unsupported
            PermissionError: If the file cannot be read
        """
        # Try different encoding strategies
        # Note: Latin-1 and cp1252 accept all byte values, so they effectively
        # never raise UnicodeDecodeError
        encoding_strategies = [
            ("utf-8", "UTF-8"),
            ("latin-1", "Latin-1"),
            ("cp1252", "Windows-1252"),
        ]

        last_error = None

        for encoding, description in encoding_strategies:
            try:
                detail_logger.debug(
                    f"Attempting to parse {file_path.name} with {description}"
                )

                bib_data = parse_file(str(file_path), encoding=encoding)

                # Process all entries in parallel
                entries, skipped_entries, preprint_entries = (
                    BibtexParser._process_all_entries(bib_data, max_workers)
                )

                # Log parsing results
                BibtexParser._log_parsing_results(
                    file_path, description, entries, skipped_entries, preprint_entries
                )

                return entries, skipped_entries, preprint_entries

            except UnicodeDecodeError as e:
                last_error = e
                detail_logger.debug(
                    f"{description} decoding failed for {file_path.name}: {e}"
                )
                continue

            except PybtexSyntaxError as e:
                # Syntax errors are not encoding-related, so don't try other encodings
                raise ValueError(
                    f"Invalid BibTeX syntax in {file_path.name}: {e}"
                ) from e

            except PermissionError as e:
                raise PermissionError(f"Cannot read {file_path}: {e}") from e

            except PybtexError as e:
                last_error = e
                detail_logger.debug(
                    f"PyBTeX error with {description} for {file_path.name}: {e}"
                )
                continue

        # If we get here, all encoding strategies failed
        if last_error:
            if isinstance(last_error, UnicodeDecodeError):
                raise UnicodeDecodeError(
                    "utf-8",
                    b"",
                    0,
                    1,
                    f"Could not decode {file_path.name} with any supported encoding "
                    f"(tried UTF-8, Latin-1, Windows-1252).",
                ) from last_error
            else:
                raise ValueError(
                    f"Error parsing BibTeX file {file_path.name}: {last_error}"
                ) from last_error
        else:
            raise ValueError(f"Unknown error parsing BibTeX file {file_path.name}")

    @staticmethod
    def _validate_file_path(file_path: Path) -> None:
        """Validate that the file path exists and is a file.

        Args:
            file_path: Path to validate

        Raises:
            FileNotFoundError: If the BibTeX file doesn't exist
            ValueError: If the path is not a file
        """
        if not file_path.exists():
            raise FileNotFoundError(f"BibTeX file not found: {file_path}")

        if not file_path.is_file():
            raise ValueError(f"Path is not a file: {file_path}")

    @staticmethod
    def parse_bibtex_file(
        file_path: Path, relax_parsing: bool = False, max_workers: int = 12
    ) -> tuple[list[BibtexEntry], int, int]:
        """Parse a BibTeX file and extract journal entries with parallel processing.

        This method tries multiple encoding strategies to maximize the number
        of successfully parsed entries, even in files with mixed encodings.
        All entries are processed in parallel for improved performance.

        Args:
            file_path: Path to the BibTeX file
            relax_parsing: If True, enable lenient parsing mode to handle
                         malformed BibTeX files (e.g., duplicate keys, syntax errors)
            max_workers: Maximum number of parallel workers for entry processing (default: 12)

        Returns:
            A tuple containing:
            - List of BibtexEntry objects with extracted journal information
            - Number of entries skipped (excluding arXiv)
            - Number of arXiv entries detected and skipped

        Raises:
            FileNotFoundError: If the BibTeX file doesn't exist
            ValueError: If the file has invalid BibTeX syntax
            UnicodeDecodeError: If the file encoding is unsupported
            PermissionError: If the file cannot be read
        """
        BibtexParser._validate_file_path(file_path)

        # Configure pybtex parsing mode based on relax_parsing parameter
        with BibtexParser._configure_pybtex(relax_parsing):
            return BibtexParser._parse_with_encoding_fallback(file_path, max_workers)

    @staticmethod
    def _process_single_entry(entry_key: str, entry: Entry) -> dict[str, Any]:
        """Process a single BibTeX entry and return structured result.

        Args:
            entry_key: The BibTeX entry key
            entry: The BibTeX entry object

        Returns:
            Dictionary containing processing result:
            - {"type": "preprint", "key": entry_key} for preprint entries
            - {"type": "processed", "entry": BibtexEntry} for successfully processed entries
            - {"type": "skipped", "key": entry_key} for entries that couldn't be processed

        Raises:
            Exception: For any processing errors that need to be handled by caller
        """
        # First, check for preprint entries to correctly categorize skipped entries
        if BibtexParser._is_preprint_entry(entry):
            return {"type": "preprint", "key": entry_key}

        # Extract each entry with individual error handling
        processed_entry = BibtexParser._process_entry_safely(entry_key, entry)
        if processed_entry:
            return {"type": "processed", "entry": processed_entry}
        else:
            return {"type": "skipped", "key": entry_key}

    @staticmethod
    def _process_entry_safely(entry_key: str, entry: Entry) -> BibtexEntry | None:
        """Process a single BibTeX entry with error handling for individual fields."""
        try:
            # Extract venue name based on entry type
            if entry.type.lower() in ["inproceedings", "conference", "proceedings"]:
                venue_name = BibtexParser._extract_conference_name(entry)
            else:
                venue_name = BibtexParser._extract_journal_name(entry)

            if not venue_name:
                # This can happen if the entry is an arXiv preprint or if it's a non-journal/conference type
                detail_logger.debug(
                    f"Skipping entry '{entry_key}' because no venue name could be extracted."
                )
                return None

            # Detect venue type
            venue_type = BibtexParser._detect_venue_type(entry, venue_name)

            return BibtexEntry(
                key=entry_key,
                journal_name=venue_name,
                entry_type=entry.type,
                venue_type=venue_type,
                title=BibtexParser._get_field_safely(entry, "title"),
                authors=BibtexParser._extract_authors_safely(entry),
                year=BibtexParser._get_field_safely(entry, "year"),
                doi=BibtexParser._get_field_safely(entry, "doi"),
                isbn=BibtexParser._get_field_safely(entry, "isbn"),
                issn=BibtexParser._get_field_safely(entry, "issn"),
                url=BibtexParser._get_field_safely(entry, "url"),
                publisher=BibtexParser._get_field_safely(entry, "publisher"),
                booktitle=BibtexParser._get_field_safely(entry, "booktitle"),
                series=BibtexParser._get_field_safely(entry, "series"),
                organization=BibtexParser._get_field_safely(entry, "organization"),
                raw_entry=entry,
            )
        except (KeyError, AttributeError, ValueError, TypeError) as e:
            detail_logger.debug(f"Error processing entry {entry_key}: {e}")
            return None

    @staticmethod
    def _extract_journal_name(entry: Entry) -> str | None:
        """Extract journal name from a BibTeX entry.

        Only extracts journal names from entry types that represent journal publications.
        Conference papers, books, and other non-journal publications are skipped.

        Args:
            entry: BibTeX entry

        Returns:
            Journal name if found, None otherwise
        """
        # Entry types that should have journals (actual journal publications)
        journal_entry_types = {
            "article",  # Journal article
            "periodical",  # Complete issue of a periodical
            "suppperiodical",  # Supplemental material in a periodical
        }

        # Skip non-journal entry types (conferences, books, etc.)
        if entry.type.lower() not in journal_entry_types:
            return None

        # For journal entry types, check appropriate fields ONLY
        # DO NOT extract from publisher, address, organization, note, or institution fields
        journal_fields = ["journal", "journaltitle"]

        for field in journal_fields:
            journal_name = BibtexParser._get_field_safely(entry, field)
            if journal_name:
                return journal_name

        return None

    @staticmethod
    def _extract_conference_name(entry: Entry) -> str | None:
        """Extract conference name from a BibTeX @inproceedings entry.

        Prioritizes series name (normalized) over full booktitle.
        Normalizes conference names to improve matching across variations.

        Args:
            entry: BibTeX entry

        Returns:
            Conference name if found, None otherwise
        """
        # Priority 1: Try series field first (most reliable for recurring conferences)
        series = BibtexParser._get_field_safely(entry, "series")
        if series:
            # Remove common artifacts (quotes, extra spaces)
            series = series.strip("'\"").strip()
            if series:
                normalized = BibtexParser._normalize_conference_name(series)
                if normalized:
                    return normalized

        # Priority 2: Try to extract from booktitle
        booktitle = BibtexParser._get_field_safely(entry, "booktitle")
        if booktitle:
            normalized = BibtexParser._normalize_conference_name(booktitle)
            if normalized:
                return normalized

        # Priority 3: Fallback to organization
        organization = BibtexParser._get_field_safely(entry, "organization")
        if organization:
            normalized = BibtexParser._normalize_conference_name(organization)
            if normalized:
                return normalized

        return None

    @staticmethod
    def _normalize_conference_name(name: str) -> str:
        """Normalize conference names to improve matching across variations.

        Removes common prefixes like "Proceedings of" and "Proceedings of the"
        to reduce variation between different citation styles.

        Args:
            name: Raw conference name

        Returns:
            Normalized conference name

        Examples:
            "Proceedings of the IEEE conference on computer vision" ->
            "IEEE conference on computer vision"
            "Proceedings of Semantic Web" -> "Semantic Web"
        """
        # Remove "Proceedings of the" prefix (case-insensitive)
        name = re.sub(r"^proceedings\s+of\s+the\s+", "", name, flags=re.IGNORECASE)

        # Remove "Proceedings of" prefix (case-insensitive)
        name = re.sub(r"^proceedings\s+of\s+", "", name, flags=re.IGNORECASE)

        # Clean up any extra whitespace
        name = re.sub(r"\s+", " ", name).strip()

        return name

    @staticmethod
    def _extract_authors_safely(entry: Entry) -> str | None:
        """Extract author information from a BibTeX entry with error handling.

        Args:
            entry: BibTeX entry

        Returns:
            Formatted author string if found, None otherwise
        """
        try:
            # Check if entry has persons attribute and author data
            # Note: pybtex stores authors in entry.persons, NOT entry.fields
            if hasattr(entry, "persons") and "author" in entry.persons:
                try:
                    # Convert pybtex Person objects to string
                    persons = entry.persons.get("author", [])
                    if persons:
                        authors = []
                        for person in persons:
                            try:
                                # Format: "Last, First" or just the string representation
                                author_str = str(person)
                                authors.append(author_str)
                            except (UnicodeDecodeError, UnicodeEncodeError) as e:
                                detail_logger.debug(
                                    f"Encoding error in author field: {e}"
                                )
                                # Try to get a safe representation
                                author_str = repr(person)
                                authors.append(author_str)
                        return "; ".join(authors)
                except (AttributeError, KeyError, UnicodeError):
                    pass

            # Fallback to raw field value
            return BibtexParser._get_field_safely(entry, "author")
        except (KeyError, AttributeError, ValueError, TypeError) as e:
            detail_logger.debug(f"Error extracting authors: {e}")
            return None

    @staticmethod
    def _get_field_safely(entry: Entry, field_name: str) -> str | None:
        """Get a field value from a BibTeX entry with error handling.

        Args:
            entry: BibTeX entry
            field_name: Name of the field to extract

        Returns:
            Field value if found, None otherwise
        """
        try:
            if field_name in entry.fields:
                value = entry.fields[field_name]
                # Clean up common BibTeX formatting
                if isinstance(value, str):
                    try:
                        # Remove nested curly braces (BibTeX formatting)
                        cleaned = BibtexParser._remove_nested_braces(value)
                        return cleaned if cleaned else None
                    except (UnicodeDecodeError, UnicodeEncodeError) as e:
                        detail_logger.debug(
                            f"Encoding error in field '{field_name}': {e}"
                        )
                        # Try to get a safe representation
                        try:
                            # Attempt to encode/decode safely
                            safe_value = value.encode("utf-8", errors="replace").decode(
                                "utf-8"
                            )
                            cleaned = safe_value.strip("{}").strip()
                            return cleaned if cleaned else None
                        except (UnicodeError, AttributeError, ValueError):
                            # Last resort: return a safe representation
                            return repr(value).strip("'\"")
            return None
        except (KeyError, AttributeError, ValueError, TypeError) as e:
            detail_logger.debug(f"Error getting field '{field_name}': {e}")
            return None

    @staticmethod
    def _strip_latex_formatting_commands(value: str) -> str:
        """Strip LaTeX formatting commands while preserving their content.

        Removes LaTeX commands like \\textcolor{blue}{content} and \\textbf{content}
        while keeping the actual content. Also removes LaTeX math mode content.

        Args:
            value: BibTeX field value that may contain LaTeX formatting commands

        Returns:
            Value with LaTeX formatting commands stripped, content preserved

        Examples:
            "\\textcolor{blue}{IEEE Conference}" -> "IEEE Conference"
            "\\textbf{Important}" -> "Important"
            "\\emph{emphasized text}" -> "emphasized text"
            "8$^{th}$ Workshop" -> "8th Workshop"
            "$\\text{8}^\\text{th}$" -> "8th"
        """
        # First, handle LaTeX math mode ordinals like $\text{8}^\text{th}$ or $8^{th}$
        # Extract the number and ordinal suffix, discard the rest
        # Pattern: $\text{N}^\text{th}$ or $N^{th}$ or similar
        ordinal_pattern = r"\$\\?t?e?x?t?\{?(\d+)\}?\^\\?t?e?x?t?\{?(st|nd|rd|th)\}?\$"
        value = re.sub(ordinal_pattern, r"\1\2", value, flags=re.IGNORECASE)

        # Handle ordinal suffix in math mode without number: 8$^{th}$ -> 8th
        suffix_only_pattern = r"\$\^\\?t?e?x?t?\{?(st|nd|rd|th)\}?\$"
        value = re.sub(suffix_only_pattern, r"\1", value, flags=re.IGNORECASE)

        # Remove any remaining LaTeX math mode content ($...$)
        # This handles cases like $\alpha$ or other math symbols
        value = re.sub(r"\$[^$]*\$", "", value)

        # Handle commands with two arguments: \command{arg1}{arg2} -> arg2
        # This handles \textcolor{blue}{content}, \colorbox{color}{content}, etc.
        # Use non-greedy matching and handle nested braces
        two_arg_pattern = (
            r"\\(?:textcolor|colorbox|fcolorbox|hyperref)\s*\{[^{}]*\}\s*\{([^{}]*)\}"
        )
        while re.search(two_arg_pattern, value):
            value = re.sub(two_arg_pattern, r"\1", value)

        # Handle commands with one argument: \command{arg} -> arg
        # This handles \textbf{}, \textit{}, \emph{}, \underline{}, etc.
        one_arg_commands = [
            "textbf",
            "textit",
            "texttt",
            "textrm",
            "textsf",
            "textsc",
            "emph",
            "underline",
            "sout",
            "uline",
            "uwave",
            "bfseries",
            "itshape",
            "mbox",
            "hbox",
            "vbox",
        ]
        one_arg_pattern = r"\\(?:" + "|".join(one_arg_commands) + r")\s*\{([^{}]*)\}"
        while re.search(one_arg_pattern, value):
            value = re.sub(one_arg_pattern, r"\1", value)

        return value

    @staticmethod
    def _clean_latex_escapes(value: str) -> str:
        """Clean LaTeX escape sequences from BibTeX field values.

        BibTeX files often contain LaTeX escape sequences like \\& or \\'
        that need to be converted to their actual characters for proper
        database matching and display.

        Args:
            value: BibTeX field value that may contain LaTeX escape sequences

        Returns:
            Value with LaTeX escape sequences converted to actual characters

        Examples:
            "Computers \\& Security" -> "Computers & Security"
            "Journal of \\"Research\\"" -> 'Journal of "Research"'
            "Test\\_Case" -> "Test_Case"
        """
        # Map of LaTeX escape sequences to their actual characters
        # Handle both single and double backslash patterns
        escape_mappings = [
            (r"\\\\&", "&"),  # Double backslash (raw string in files)
            (r"\\&", "&"),  # Single backslash
            (r"\\\\'", "'"),
            (r"\\'", "'"),
            (r'\\\\"', '"'),
            (r'\\"', '"'),
            (r"\\\\{", "{"),
            (r"\\{", "{"),
            (r"\\\\}", "}"),
            (r"\\}", "}"),
            (r"\\\\\$", "$"),
            (r"\\\$", "$"),
            (r"\\\\%", "%"),
            (r"\\%", "%"),
            (r"\\\\#", "#"),
            (r"\\#", "#"),
            (r"\\\\_", "_"),
            (r"\\_", "_"),
            (r"\\\\\^", "^"),
            (r"\\\^", "^"),
            (r"\\\\~", "~"),
            (r"\\~", "~"),
            # LaTeX space commands
            (r"\\\\ ", " "),  # Double backslash + space (forced space)
            (r"\\ ", " "),  # Single backslash + space (forced space)
        ]

        # Apply all escape sequence replacements
        for pattern, replacement in escape_mappings:
            value = re.sub(pattern, replacement, value)

        # Replace LaTeX non-breaking space (~) with regular space
        value = value.replace("~", " ")

        # Clean up multiple spaces
        value = re.sub(r"\s+", " ", value)

        return value.strip()

    @staticmethod
    def _expand_latex_journal_macros(value: str) -> str:
        """Expand LaTeX journal macros using the acronym cache.

        Many astronomy and physics BibTeX files use LaTeX macros for journal names
        (e.g., \\pasp, \\apj, \\mnras). This method converts them to uppercase
        acronyms and looks them up in the cache to get the full journal name.

        Args:
            value: BibTeX field value that may contain LaTeX journal macros

        Returns:
            Value with LaTeX journal macros expanded when possible

        Examples:
            "\\pasp" -> "PASP" -> (lookup in cache) -> "Publications of..."
            "\\ieee" -> "IEEE" -> (lookup in cache) -> full name or "IEEE"
            "\\unknownmacro" -> "UNKNOWNMACRO" (or removed if not in cache)
        """
        # Find all LaTeX commands (backslash followed by letters)
        latex_command_pattern = r"\\([a-zA-Z]+)"

        def replace_macro(match: re.Match[str]) -> str:
            macro_name = match.group(1)  # Get the name without backslash
            acronym = macro_name.upper()  # Convert to uppercase (e.g., pasp -> PASP)

            # Try to look up the acronym in the cache (for journals)
            acronym_cache = AcronymCache()
            full_name = acronym_cache.get_full_name_for_acronym(acronym, "journal")

            if full_name:
                return full_name
            else:
                # If not in cache, just return the uppercase acronym
                # This is better than keeping the backslash
                return acronym

        # Replace all LaTeX commands with their expansions
        value = re.sub(latex_command_pattern, replace_macro, value)

        return value

    @staticmethod
    def _remove_nested_braces(value: str) -> str:
        """Remove nested curly braces and clean LaTeX escapes from BibTeX field values.

        BibTeX often uses nested braces like {{IEEE}} or {{{CLOUD}}} for formatting,
        and LaTeX escape sequences like \\& for special characters.
        This method removes all levels of curly braces and converts escape sequences.

        Args:
            value: BibTeX field value that may contain nested braces and escapes

        Returns:
            Value with all curly braces removed and LaTeX escapes cleaned

        Examples:
            "{{IEEE}} Conference" -> "IEEE Conference"
            "{{{CLOUD}}}" -> "CLOUD"
            "Computers \\& Security" -> "Computers & Security"
            "Normal text" -> "Normal text"
            "\\pasp" -> "PASP" (or full name if in cache)
            "\\textcolor{blue}{IEEE Conference}" -> "IEEE Conference"
        """
        # First, strip LaTeX formatting commands (e.g., \textcolor{blue}{text} -> text)
        # This must happen before brace removal to preserve the structure
        value = BibtexParser._strip_latex_formatting_commands(value)

        # Then, expand LaTeX journal macros (e.g., \pasp -> PASP or full name)
        value = BibtexParser._expand_latex_journal_macros(value)

        # Then, clean LaTeX escape sequences
        value = BibtexParser._clean_latex_escapes(value)

        # Finally, remove nested curly braces iteratively until none remain
        # This handles multiple levels like {{{text}}} -> {{text}} -> {text} -> text
        while re.search(r"\{[^{}]*\}", value):
            value = re.sub(r"\{([^{}]*)\}", r"\1", value)

        return value.strip()

    @staticmethod
    def _get_preprint_check_content(entry: Entry) -> str:
        """Extract and combine relevant fields for preprint pattern matching.

        Args:
            entry: BibTeX entry object.

        Returns:
            Lowercase string combining all relevant fields for pattern matching.
        """
        fields_to_check = [
            BibtexParser._get_field_safely(entry, "journal"),
            BibtexParser._get_field_safely(entry, "booktitle"),
            BibtexParser._get_field_safely(entry, "eprint"),
            BibtexParser._get_field_safely(entry, "url"),
            BibtexParser._get_field_safely(entry, "title"),
            BibtexParser._get_field_safely(entry, "publisher"),
            BibtexParser._get_field_safely(entry, "howpublished"),
        ]
        return " ".join([f.lower() for f in fields_to_check if f is not None])

    @staticmethod
    def _is_arxiv_entry(entry: Entry) -> bool:
        """Check if entry is from arXiv preprint repository.

        Args:
            entry: BibTeX entry object.

        Returns:
            True if the entry is from arXiv, False otherwise.
        """
        checked_content = BibtexParser._get_preprint_check_content(entry)
        for pattern in ARXIV_PREPRINT_PATTERNS:
            if re.search(pattern, checked_content, re.IGNORECASE):
                detail_logger.debug(
                    f"Detected arXiv pattern '{pattern}' in entry: {entry.key}"
                )
                return True
        return False

    @staticmethod
    def _is_biorxiv_entry(entry: Entry) -> bool:
        """Check if entry is from bioRxiv preprint repository.

        Args:
            entry: BibTeX entry object.

        Returns:
            True if the entry is from bioRxiv, False otherwise.
        """
        biorxiv_patterns = [
            r"biorxiv",
            r"bio\s*rxiv",
            r"www\.biorxiv\.org",
            r"doi\.org/10\.1101/",
        ]
        checked_content = BibtexParser._get_preprint_check_content(entry)
        for pattern in biorxiv_patterns:
            if re.search(pattern, checked_content, re.IGNORECASE):
                detail_logger.debug(
                    f"Detected bioRxiv pattern '{pattern}' in entry: {entry.key}"
                )
                return True
        return False

    @staticmethod
    def _is_ssrn_entry(entry: Entry) -> bool:
        """Check if entry is from SSRN preprint repository.

        Args:
            entry: BibTeX entry object.

        Returns:
            True if the entry is from SSRN, False otherwise.
        """
        ssrn_patterns = [
            r"ssrn\s*electronic\s*journal",
            r"social\s*science\s*research\s*network",
            r"ssrn\.com",
            r"\bssrn\b",
        ]
        checked_content = BibtexParser._get_preprint_check_content(entry)
        for pattern in ssrn_patterns:
            if re.search(pattern, checked_content, re.IGNORECASE):
                detail_logger.debug(
                    f"Detected SSRN pattern '{pattern}' in entry: {entry.key}"
                )
                return True
        return False

    @staticmethod
    def _is_medrxiv_entry(entry: Entry) -> bool:
        """Check if entry is from medRxiv preprint repository.

        Args:
            entry: BibTeX entry object.

        Returns:
            True if the entry is from medRxiv, False otherwise.
        """
        medrxiv_patterns = [
            r"medrxiv",
            r"med\s*rxiv",
            r"www\.medrxiv\.org",
        ]
        checked_content = BibtexParser._get_preprint_check_content(entry)
        for pattern in medrxiv_patterns:
            if re.search(pattern, checked_content, re.IGNORECASE):
                detail_logger.debug(
                    f"Detected medRxiv pattern '{pattern}' in entry: {entry.key}"
                )
                return True
        return False

    @staticmethod
    def _is_zenodo_entry(entry: Entry) -> bool:
        """Check if entry is from Zenodo preprint repository.

        Args:
            entry: BibTeX entry object.

        Returns:
            True if the entry is from Zenodo, False otherwise.
        """
        zenodo_patterns = [
            r"\bzenodo\b",
            r"zenodo\.org",
            r"doi\.org/10\.5281/zenodo",
        ]
        checked_content = BibtexParser._get_preprint_check_content(entry)
        for pattern in zenodo_patterns:
            if re.search(pattern, checked_content, re.IGNORECASE):
                detail_logger.debug(
                    f"Detected Zenodo pattern '{pattern}' in entry: {entry.key}"
                )
                return True
        return False

    @staticmethod
    def _is_other_rxiv_preprint_entry(entry: Entry) -> bool:
        """Check if entry is from other *rxiv preprint repositories.

        Checks for psyarxiv, socarxiv, eartharxiv, engrxiv, techrxiv, chemrxiv.

        Args:
            entry: BibTeX entry object.

        Returns:
            True if the entry is from an *rxiv repository, False otherwise.
        """
        rxiv_patterns = [
            r"psyarxiv",
            r"socarxiv",
            r"eartharxiv",
            r"engrxiv",
            r"techrxiv",
            r"chemrxiv",
        ]
        checked_content = BibtexParser._get_preprint_check_content(entry)
        for pattern in rxiv_patterns:
            if re.search(pattern, checked_content, re.IGNORECASE):
                detail_logger.debug(
                    f"Detected *rxiv pattern '{pattern}' in entry: {entry.key}"
                )
                return True
        return False

    @staticmethod
    def _is_other_preprint_repository_entry(entry: Entry) -> bool:
        """Check if entry is from other preprint repositories.

        Checks for preprints.org, Research Square, OSF preprints, and authorea.com.

        Args:
            entry: BibTeX entry object.

        Returns:
            True if the entry is from a recognized preprint repository, False otherwise.
        """
        other_patterns = [
            r"preprints\.org",
            r"research\s*square",
            r"researchsquare\.com",
            r"osf\.io/preprints",
            r"authorea\.com",
        ]
        checked_content = BibtexParser._get_preprint_check_content(entry)
        for pattern in other_patterns:
            if re.search(pattern, checked_content, re.IGNORECASE):
                detail_logger.debug(
                    f"Detected preprint repository pattern '{pattern}' in entry: {entry.key}"
                )
                return True
        return False

    @staticmethod
    def _is_preprint_entry(entry: Entry) -> bool:
        """Detects if a BibTeX entry is a preprint from a legitimate repository.

        Checks the 'journal', 'booktitle', 'eprint', 'url', and 'title' fields
        for patterns from legitimate preprint repositories to prevent false positives.

        Args:
            entry: BibTeX entry object.

        Returns:
            True if the entry is identified as a legitimate preprint, False otherwise.
        """
        return (
            BibtexParser._is_arxiv_entry(entry)
            or BibtexParser._is_biorxiv_entry(entry)
            or BibtexParser._is_ssrn_entry(entry)
            or BibtexParser._is_medrxiv_entry(entry)
            or BibtexParser._is_zenodo_entry(entry)
            or BibtexParser._is_other_rxiv_preprint_entry(entry)
            or BibtexParser._is_other_preprint_repository_entry(entry)
        )

    @staticmethod
    def _detect_venue_type(entry: Entry, venue_name: str) -> VenueType:
        """Detect the type of venue based on BibTeX entry and venue name patterns.

        This method classifies venues into journals, conferences, workshops, symposiums,
        etc., based on naming patterns and BibTeX entry types.

        Args:
            entry: BibTeX entry object
            venue_name: Extracted venue name

        Returns:
            VenueType enum value representing the detected venue type

        Examples:
            "4th Deep Learning and Security Workshop" -> VenueType.WORKSHOP
            "30th USENIX Security Symposium" -> VenueType.SYMPOSIUM
            "IEEE Transactions on Neural Networks" -> VenueType.JOURNAL
            "Proceedings of the IEEE conference on computer vision" -> VenueType.CONFERENCE
        """
        # Convert venue name to lowercase for case-insensitive matching
        venue_name_lower = venue_name.lower()
        entry_type_lower = entry.type.lower()

        # Check for preprints first (highest priority)
        # This includes arXiv, bioRxiv, SSRN, medRxiv, Zenodo, and other legitimate repositories
        if BibtexParser._is_preprint_entry(entry):
            return VenueType.PREPRINT

        # Symposium patterns (check first since they should have highest priority)
        symposium_patterns = [
            r"\bsymposium\b",
            r"\bsymposia\b",
            r"\d+(st|nd|rd|th)\s+.*\s+symposium\b",  # "30th USENIX Security Symposium"
            r"symposium\s+on\b",  # "Symposium on Security"
            r"international\s+symposium\b",
            r"annual\s+symposium\b",
        ]

        for pattern in symposium_patterns:
            if re.search(pattern, venue_name_lower):
                detail_logger.debug(
                    f"Detected symposium pattern '{pattern}' in '{venue_name}'"
                )
                return VenueType.SYMPOSIUM

        # Workshop patterns (check before conference since workshops often contain "conference")
        workshop_patterns = [
            r"\bworkshop\b",
            r"\bworkshops\b",
            r"\d+(st|nd|rd|th)\s+.*\s+workshop\b",  # "4th Deep Learning Workshop"
            r"workshop\s+on\b",  # "Workshop on Security"
            r"\bws\b",  # Workshop abbreviation
            r"international\s+workshop\b",
        ]

        for pattern in workshop_patterns:
            if re.search(pattern, venue_name_lower):
                detail_logger.debug(
                    f"Detected workshop pattern '{pattern}' in '{venue_name}'"
                )
                return VenueType.WORKSHOP

        # Conference patterns (check after workshop/symposium)
        if entry_type_lower in ["inproceedings", "conference", "proceedings"]:
            conference_patterns = [
                r"\bconference\b",
                r"\bconf\b",
                r"proceedings\s+of\b",
                r"international\s+conference\b",
                r"annual\s+conference\b",
                r"\bacm\s+.+\s+conference\b",
                r"\bieee\s+.+\s+conference\b",
                # Common conference series patterns
                r"\b(sigchi|sigcomm|sigmod|sigkdd|icml|nips|iclr|aaai|ijcai)\b",
                r"\b(cvpr|iccv|eccv|neurips|icassp|interspeech)\b",
            ]

            # Default to conference for conference-type entries
            venue_type = VenueType.CONFERENCE

            for pattern in conference_patterns:
                if re.search(pattern, venue_name_lower):
                    detail_logger.debug(
                        f"Detected conference pattern '{pattern}' in '{venue_name}'"
                    )
                    return VenueType.CONFERENCE

            # If it's a conference-type entry but no conference patterns, might be proceedings
            if "proceedings" in venue_name_lower:
                return VenueType.PROCEEDINGS

            return venue_type

        # Journal patterns
        journal_patterns = [
            r"\bjournal\b",
            r"\btransactions\b",
            r"\bletters\b",
            r"\breview\b",
            r"\bannals\b",
            r"\barchives\b",
            r"\bbulletin\b",
            r"\bmagazine\b",
            r"ieee\s+transactions\b",
            r"acm\s+transactions\b",
            r"journal\s+of\b",
            r"international\s+journal\b",
            r"european\s+journal\b",
            r"american\s+journal\b",
        ]

        # Check for journal entry types
        if entry_type_lower in ["article", "periodical", "suppperiodical"]:
            for pattern in journal_patterns:
                if re.search(pattern, venue_name_lower):
                    detail_logger.debug(
                        f"Detected journal pattern '{pattern}' in '{venue_name}'"
                    )
                    return VenueType.JOURNAL

            # Default to journal for article-type entries
            return VenueType.JOURNAL

        # Book patterns
        if entry_type_lower in ["book", "inbook", "incollection", "booklet"]:
            return VenueType.BOOK

        # Check for other venue type patterns regardless of entry type
        for pattern in journal_patterns:
            if re.search(pattern, venue_name_lower):
                detail_logger.debug(
                    f"Detected journal pattern '{pattern}' in '{venue_name}'"
                )
                return VenueType.JOURNAL

        # If no patterns match, return UNKNOWN
        detail_logger.debug(
            f"No venue type pattern matched for '{venue_name}' (entry type: {entry.type})"
        )
        return VenueType.UNKNOWN

    @staticmethod
    def extract_acronyms_from_entries(
        entries: list[BibtexEntry],
        acronym_cache: AcronymCache,
        file_path: Path | None = None,
    ) -> tuple[
        list[tuple[str, str, str, str]],
        list[tuple[str, str, str, str]],
        list[tuple[str, str, list[tuple[str, int]]]],
    ]:
        """Extract acronym mappings from BibTeX entries.

        Args:
            entries: List of BibtexEntry objects to process
            acronym_cache: AcronymCache instance for conflict checking
            file_path: Optional file path for logging context

        Returns:
            Tuple of (new_mappings, existing_mappings, conflicts) where:
            - new_mappings: List of (acronym, venue_name, normalized_name, entity_type)
            - existing_mappings: List of (acronym, venue_name, normalized_name, entity_type)
            - conflicts: List of (acronym, entity_type, [(venue_name, count), ...])
        """
        from .normalizer import input_normalizer

        # Create log prefix with file path if available
        log_prefix = f"{file_path}: " if file_path else ""

        detail_logger.debug(
            f"{log_prefix}Extracting acronyms from {len(entries)} BibTeX entries"
        )

        # Track mappings: (acronym, entity_type) -> list of (venue_name, normalized_name)
        mappings: dict[tuple[str, str], list[tuple[str, str]]] = {}
        # Track occurrence counts: (acronym, entity_type, normalized_name) -> count
        occurrence_counts: dict[tuple[str, str, str], int] = {}

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
                # Normalize the venue name
                normalized_name = acronym_cache._normalize_venue_name(full_name)
                entity_type = entry.venue_type.value

                key = (acronym, entity_type)
                if key not in mappings:
                    mappings[key] = []

                # Check if this normalized name is equivalent to any existing one (avoid false positive conflicts)
                from .normalizer import are_conference_names_equivalent

                is_duplicate = False
                for _, existing_normalized in mappings[key]:
                    if are_conference_names_equivalent(
                        normalized_name, existing_normalized
                    ):
                        is_duplicate = True
                        break

                if not is_duplicate:
                    mappings[key].append((full_name, normalized_name))

                # Track occurrence count (increment even if duplicate for accurate statistics)
                count_key = (acronym, entity_type, normalized_name)
                occurrence_counts[count_key] = occurrence_counts.get(count_key, 0) + 1

        # Detect conflicts and build result lists using new variant system
        from .abbreviation_learner import learn_abbreviations_from_pair
        from .normalizer import are_variants_of_same_venue

        new_mappings: list[tuple[str, str, str, str]] = []
        existing_mappings: list[tuple[str, str, str, str]] = []
        conflicts: list[tuple[str, str, list[tuple[str, int]]]] = []

        # Load learned abbreviations once for all comparisons
        learned_abbrevs = acronym_cache.get_learned_abbreviations()

        for (acronym, entity_type), venue_list in mappings.items():
            # Get existing variants from database (needed for both single and multiple venue cases)
            existing_variants = acronym_cache.get_variants(acronym, entity_type)

            # Skip if acronym is already marked as ambiguous - no need to re-log the conflict
            if existing_variants and any(
                v.get("is_ambiguous") for v in existing_variants
            ):
                detail_logger.debug(
                    f"{log_prefix}Skipping already-ambiguous acronym: '{acronym}'"
                )
                continue

            if len(venue_list) == 1:
                # No conflict within file, check against database variants
                full_name, normalized_name = venue_list[0]
                count_key = (acronym, entity_type, normalized_name)
                count = occurrence_counts.get(count_key, 1)

                if not existing_variants:
                    # New acronym - store it
                    detail_logger.debug(
                        f"{log_prefix}New acronym: '{acronym}' → '{full_name}' (normalized: '{normalized_name}')"
                    )
                    new_mappings.append(
                        (acronym, full_name, normalized_name, entity_type)
                    )
                else:
                    # Check if this variant is similar to any existing variants
                    similar_found = False
                    truly_different_variants = []

                    for existing_variant in existing_variants:
                        existing_normalized = existing_variant["normalized_name"]

                        # Check similarity using learned abbreviations
                        if are_variants_of_same_venue(
                            normalized_name, existing_normalized, learned_abbrevs
                        ):
                            # Similar variant found - learn abbreviations from this pair
                            detail_logger.debug(
                                f"{log_prefix}Found similar variant for '{acronym}': '{normalized_name}' ≈ '{existing_normalized}'"
                            )

                            # Learn abbreviations from this pair
                            new_abbrevs = learn_abbreviations_from_pair(
                                normalized_name, existing_normalized
                            )
                            for abbrev_form, expanded_form, confidence in new_abbrevs:
                                acronym_cache.store_learned_abbreviation(
                                    abbrev_form,
                                    expanded_form,
                                    confidence,
                                    log_prefix=log_prefix,
                                )

                            # Mark as existing variant (will be updated in storage phase)
                            similar_found = True
                            existing_mappings.append(
                                (acronym, full_name, normalized_name, entity_type)
                            )
                            break
                        else:
                            # Truly different variant
                            truly_different_variants.append(existing_normalized)

                    if not similar_found:
                        # Not similar yet - try to learn abbreviations from each pair
                        for existing_variant in existing_variants:
                            existing_normalized = existing_variant["normalized_name"]
                            new_abbrevs = learn_abbreviations_from_pair(
                                normalized_name, existing_normalized
                            )
                            for abbrev_form, expanded_form, confidence in new_abbrevs:
                                acronym_cache.store_learned_abbreviation(
                                    abbrev_form,
                                    expanded_form,
                                    confidence,
                                    log_prefix=log_prefix,
                                )
                                # Update local cache for immediate re-check
                                if abbrev_form not in learned_abbrevs:
                                    learned_abbrevs[abbrev_form] = []
                                learned_abbrevs[abbrev_form].append(
                                    (expanded_form, confidence)
                                )

                        # Re-check with updated abbreviations
                        now_similar = False
                        for existing_variant in existing_variants:
                            existing_normalized = existing_variant["normalized_name"]
                            if are_variants_of_same_venue(
                                normalized_name, existing_normalized, learned_abbrevs
                            ):
                                now_similar = True
                                detail_logger.debug(
                                    f"{log_prefix}Resolved via learned abbreviations: '{acronym}': '{normalized_name}' ≈ '{existing_normalized}'"
                                )
                                existing_mappings.append(
                                    (acronym, full_name, normalized_name, entity_type)
                                )
                                break

                        if not now_similar:
                            # Still truly different - this creates ambiguity
                            if len(existing_variants) >= 1:
                                detail_logger.debug(
                                    f"{log_prefix}Ambiguity detected: '{acronym}' maps to multiple DIFFERENT venues"
                                )
                                # Create conflict with all truly different variants
                                venue_with_counts = [(normalized_name, count)]
                                for existing_variant in existing_variants:
                                    venue_with_counts.append(
                                        (
                                            existing_variant["normalized_name"],
                                            existing_variant["usage_count"],
                                        )
                                    )
                                conflicts.append(
                                    (acronym, entity_type, venue_with_counts)
                                )
                            else:
                                # This shouldn't happen, but handle gracefully
                                new_mappings.append(
                                    (acronym, full_name, normalized_name, entity_type)
                                )
            else:
                # Multiple venues for same acronym within file - try to resolve via abbreviations
                # First, try to learn abbreviations from all pairs
                for i, (_, norm1) in enumerate(venue_list):
                    for _, norm2 in venue_list[i + 1 :]:
                        new_abbrevs = learn_abbreviations_from_pair(norm1, norm2)
                        for abbrev_form, expanded_form, confidence in new_abbrevs:
                            acronym_cache.store_learned_abbreviation(
                                abbrev_form,
                                expanded_form,
                                confidence,
                                log_prefix=log_prefix,
                            )
                            # Update local cache for immediate re-check
                            if abbrev_form not in learned_abbrevs:
                                learned_abbrevs[abbrev_form] = []
                            learned_abbrevs[abbrev_form].append(
                                (expanded_form, confidence)
                            )

                # Re-check: group venues that are now equivalent
                # Use first venue as reference, check if others match
                reference_name = venue_list[0][1]
                all_equivalent = True
                for _, normalized in venue_list[1:]:
                    if not are_variants_of_same_venue(
                        reference_name, normalized, learned_abbrevs
                    ):
                        all_equivalent = False
                        break

                if all_equivalent:
                    # All venues are now equivalent - treat as single mapping
                    full_name, normalized_name = venue_list[0]
                    detail_logger.debug(
                        f"{log_prefix}Resolved conflict for '{acronym}': all {len(venue_list)} variants are equivalent"
                    )
                    new_mappings.append(
                        (acronym, full_name, normalized_name, entity_type)
                    )
                else:
                    # Still a conflict after learning abbreviations
                    venue_with_counts = [
                        (
                            normalized,
                            occurrence_counts.get(
                                (acronym, entity_type, normalized), 1
                            ),
                        )
                        for _, normalized in venue_list
                    ]
                    detail_logger.debug(
                        f"{log_prefix}File conflict: '{acronym}' maps to multiple venues: {[v for v, _ in venue_with_counts]}"
                    )
                    conflicts.append((acronym, entity_type, venue_with_counts))

        detail_logger.debug(
            f"{log_prefix}Extracted {len(new_mappings)} new acronyms, {len(existing_mappings)} existing, found {len(conflicts)} conflicts"
        )

        return new_mappings, existing_mappings, conflicts
