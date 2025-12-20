# SPDX-License-Identifier: MIT
"""BibTeX parsing utilities for journal assessment."""

import re
from pathlib import Path

from pybtex import errors as pybtex_errors  # type: ignore
from pybtex.database import (  # type: ignore
    BibliographyData,
    Entry,
    parse_file,
    parse_string,
)
from pybtex.scanner import PybtexError, PybtexSyntaxError  # type: ignore

from .logging_config import get_detail_logger, get_status_logger
from .models import BibtexEntry, VenueType


detail_logger = get_detail_logger()
status_logger = get_status_logger()


class BibtexParser:
    """Parser for BibTeX files to extract journal information."""

    @staticmethod
    def parse_bibtex_file(
        file_path: Path, relax_parsing: bool = False
    ) -> tuple[list[BibtexEntry], int, int]:
        """Parse a BibTeX file and extract journal entries.

        This method tries multiple encoding strategies to maximize the number
        of successfully parsed entries, even in files with mixed encodings.

        Args:
            file_path: Path to the BibTeX file
            relax_parsing: If True, enable lenient parsing mode to handle
                         malformed BibTeX files (e.g., duplicate keys, syntax errors)

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
        if not file_path.exists():
            raise FileNotFoundError(f"BibTeX file not found: {file_path}")

        if not file_path.is_file():
            raise ValueError(f"Path is not a file: {file_path}")

        # Configure pybtex parsing mode based on relax_parsing parameter
        original_strict_mode = pybtex_errors.strict
        try:
            if relax_parsing:
                detail_logger.debug("Enabling relaxed BibTeX parsing mode")
                pybtex_errors.set_strict_mode(False)
            else:
                detail_logger.debug("Using strict BibTeX parsing mode")
                pybtex_errors.set_strict_mode(True)

            # Try different encoding strategies
            encoding_strategies = [
                ("utf-8", "UTF-8"),
                ("latin-1", "Latin-1"),
                ("cp1252", "Windows-1252"),
                ("utf-8", "UTF-8 with errors='replace'"),
            ]

            last_error = None

            for encoding, description in encoding_strategies:
                try:
                    detail_logger.debug(
                        f"Attempting to parse {file_path.name} with {description}"
                    )

                    if description.endswith("with errors='replace'"):
                        # For the final attempt, use error handling to replace problematic characters
                        bib_data = BibtexParser._parse_with_error_handling(
                            file_path, encoding
                        )
                    else:
                        # Standard parsing attempt
                        bib_data = parse_file(str(file_path), encoding=encoding)

                    entries = []
                    skipped_entries = 0
                    preprint_entries = 0

                    for entry_key, entry in bib_data.entries.items():
                        try:
                            # First, check for preprint entries to correctly categorize skipped entries
                            if BibtexParser._is_preprint_entry(entry):
                                preprint_entries += 1
                                detail_logger.debug(
                                    f"Skipping preprint entry: {entry_key}"
                                )
                                continue

                            # Extract each entry with individual error handling
                            processed_entry = BibtexParser._process_entry_safely(
                                entry_key, entry
                            )
                            if processed_entry:
                                entries.append(processed_entry)
                            else:
                                skipped_entries += 1
                        except (KeyError, AttributeError, ValueError, TypeError) as e:
                            status_logger.warning(
                                f"Skipping entry '{entry_key}' due to processing error: {e}"
                            )
                            skipped_entries += 1
                            continue

                    # Log parsing results with clear messaging
                    detail_logger.debug(
                        f"Successfully parsed {len(entries)} entries from {file_path.name} "
                        f"with {description}"
                    )

                    # Inform user about preprints (if any)
                    if preprint_entries > 0:
                        status_logger.info(
                            f"Skipped {preprint_entries} preprint(s) from legitimate repositories - not publication venues"
                        )

                    # Log other skipped entries
                    if skipped_entries > 0:
                        detail_logger.debug(
                            f"Skipped {skipped_entries} other entries due to processing errors"
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
        finally:
            # Restore original strict mode setting
            pybtex_errors.set_strict_mode(original_strict_mode)

    @staticmethod
    def _parse_with_error_handling(file_path: Path, encoding: str) -> BibliographyData:
        """Parse a BibTeX file with error handling for encoding issues."""
        try:
            with open(file_path, encoding=encoding, errors="replace") as f:
                content = f.read()

            # Parse from the string content
            return parse_string(content, bib_format="bibtex")
        except (OSError, UnicodeError, ValueError, AttributeError) as e:
            raise PybtexError(f"Error parsing with error handling: {e}") from e

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
        ]

        # Apply all escape sequence replacements
        for pattern, replacement in escape_mappings:
            value = re.sub(pattern, replacement, value)

        return value

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
        from .cache import get_cache_manager

        # Find all LaTeX commands (backslash followed by letters)
        latex_command_pattern = r"\\([a-zA-Z]+)"

        def replace_macro(match: re.Match[str]) -> str:
            macro_name = match.group(1)  # Get the name without backslash
            acronym = macro_name.upper()  # Convert to uppercase (e.g., pasp -> PASP)

            # Try to look up the acronym in the cache
            cache = get_cache_manager()
            full_name = cache.get_full_name_for_acronym(acronym)

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
        """
        # First, expand LaTeX journal macros (e.g., \pasp -> PASP or full name)
        value = BibtexParser._expand_latex_journal_macros(value)

        # Then, clean LaTeX escape sequences
        value = BibtexParser._clean_latex_escapes(value)

        # Finally, remove nested curly braces iteratively until none remain
        # This handles multiple levels like {{{text}}} -> {{text}} -> {text} -> text
        while re.search(r"\{[^{}]*\}", value):
            value = re.sub(r"\{([^{}]*)\}", r"\1", value)

        return value.strip()

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
        # Comprehensive patterns for arXiv (all variants from real-world data)
        arxiv_patterns = [
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
        preprint_patterns = [
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

        # Combine all patterns
        all_patterns = arxiv_patterns + preprint_patterns

        # Combine all relevant fields into a single string for pattern matching
        # Include publisher and howpublished fields based on real-world data analysis
        fields_to_check = [
            BibtexParser._get_field_safely(entry, "journal"),
            BibtexParser._get_field_safely(entry, "booktitle"),
            BibtexParser._get_field_safely(entry, "eprint"),
            BibtexParser._get_field_safely(entry, "url"),
            BibtexParser._get_field_safely(entry, "title"),
            BibtexParser._get_field_safely(entry, "publisher"),
            BibtexParser._get_field_safely(entry, "howpublished"),
        ]

        # Filter out None values and convert to lowercase for case-insensitive matching
        checked_content = " ".join(
            [f.lower() for f in fields_to_check if f is not None]
        )

        for pattern in all_patterns:
            if re.search(pattern, checked_content, re.IGNORECASE):
                detail_logger.debug(
                    f"Detected preprint pattern '{pattern}' in entry: {entry.key}"
                )
                return True

        return False

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
