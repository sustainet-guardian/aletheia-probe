"""BibTeX parsing utilities for journal assessment."""

from pathlib import Path

from pybtex.database import (  # type: ignore
    BibliographyData,
    Entry,
    parse_file,
    parse_string,
)
from pybtex.scanner import PybtexError, PybtexSyntaxError  # type: ignore

from .logging_config import get_detail_logger, get_status_logger
from .models import BibtexEntry

detail_logger = get_detail_logger()
status_logger = get_status_logger()


class BibtexParser:
    """Parser for BibTeX files to extract journal information."""

    @staticmethod
    def parse_bibtex_file(file_path: Path) -> list[BibtexEntry]:
        """Parse a BibTeX file and extract journal entries.

        This method tries multiple encoding strategies to maximize the number
        of successfully parsed entries, even in files with mixed encodings.

        Args:
            file_path: Path to the BibTeX file

        Returns:
            List of BibtexEntry objects with extracted journal information

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
                detail_logger.debug(f"Attempting to parse {file_path.name} with {description}")

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

                for entry_key, entry in bib_data.entries.items():
                    try:
                        # Extract each entry with individual error handling
                        processed_entry = BibtexParser._process_entry_safely(
                            entry_key, entry
                        )
                        if processed_entry:
                            entries.append(processed_entry)
                        else:
                            skipped_entries += 1
                    except Exception as e:
                        status_logger.warning(
                            f"Skipping entry '{entry_key}' due to processing error: {e}"
                        )
                        skipped_entries += 1
                        continue

                if skipped_entries > 0:
                    status_logger.info(
                        f"Successfully parsed {len(entries)} entries from {file_path.name} "
                        f"with {description}, skipped {skipped_entries} problematic entries"
                    )
                else:
                    detail_logger.debug(
                        f"Successfully parsed {len(entries)} entries from {file_path.name} "
                        f"with {description}"
                    )

                return entries

            except UnicodeDecodeError as e:
                last_error = e
                detail_logger.debug(f"{description} decoding failed for {file_path.name}: {e}")
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
    def _parse_with_error_handling(file_path: Path, encoding: str) -> BibliographyData:
        """Parse a BibTeX file with error handling for encoding issues."""
        try:
            with open(file_path, encoding=encoding, errors="replace") as f:
                content = f.read()

            # Parse from the string content
            return parse_string(content, bib_format="bibtex")
        except Exception as e:
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
                return None

            return BibtexEntry(
                key=entry_key,
                journal_name=venue_name,
                entry_type=entry.type,
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
        except Exception as e:
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

        # For journal entry types, check appropriate fields
        journal_fields = ["journal", "journaltitle"]

        for field in journal_fields:
            journal_name = BibtexParser._get_field(entry, field)
            if journal_name:
                return journal_name

        return None

    @staticmethod
    def _extract_conference_name(entry: Entry) -> str | None:
        """Extract conference name from a BibTeX @inproceedings entry.

        Prioritizes series name (normalized) over full booktitle.
        Attempts to extract conference series by removing years and ordinals.

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
                return series

        # Priority 2: Try to extract from booktitle
        booktitle = BibtexParser._get_field_safely(entry, "booktitle")
        if booktitle:
            return booktitle

        # Priority 3: Fallback to organization
        organization = BibtexParser._get_field_safely(entry, "organization")
        if organization:
            return organization

        return None

    @staticmethod
    def _extract_authors_safely(entry: Entry) -> str | None:
        """Extract author information from a BibTeX entry with error handling.

        Args:
            entry: BibTeX entry

        Returns:
            Formatted author string if found, None otherwise
        """
        try:
            if "author" in entry.fields:
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
                                detail_logger.debug(f"Encoding error in author field: {e}")
                                # Try to get a safe representation
                                author_str = repr(person)
                                authors.append(author_str)
                        return "; ".join(authors)
                except (AttributeError, KeyError, UnicodeError):
                    pass

            # Fallback to raw field value
            return BibtexParser._get_field_safely(entry, "author")
        except Exception as e:
            detail_logger.debug(f"Error extracting authors: {e}")
            return None

    @staticmethod
    def _extract_authors(entry: Entry) -> str | None:
        """Extract author information from a BibTeX entry.

        This is the original method, kept for backward compatibility.
        New code should use _extract_authors_safely.
        """
        return BibtexParser._extract_authors_safely(entry)

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
                        # Remove curly braces and extra whitespace
                        cleaned = value.strip("{}").strip()
                        return cleaned if cleaned else None
                    except (UnicodeDecodeError, UnicodeEncodeError) as e:
                        detail_logger.debug(f"Encoding error in field '{field_name}': {e}")
                        # Try to get a safe representation
                        try:
                            # Attempt to encode/decode safely
                            safe_value = value.encode("utf-8", errors="replace").decode(
                                "utf-8"
                            )
                            cleaned = safe_value.strip("{}").strip()
                            return cleaned if cleaned else None
                        except Exception:
                            # Last resort: return a safe representation
                            return repr(value).strip("'\"")
            return None
        except Exception as e:
            detail_logger.debug(f"Error getting field '{field_name}': {e}")
            return None

    @staticmethod
    def _get_field(entry: Entry, field_name: str) -> str | None:
        """Get a field value from a BibTeX entry.

        This is the original method, kept for backward compatibility.
        New code should use _get_field_safely.
        """
        return BibtexParser._get_field_safely(entry, field_name)
