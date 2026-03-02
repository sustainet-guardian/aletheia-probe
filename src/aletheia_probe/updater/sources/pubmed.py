# SPDX-License-Identifier: MIT
"""PubMed NLM journal list data source (MEDLINE and NLM Catalog)."""

import asyncio
import ssl
import urllib.request
from datetime import datetime
from typing import Any
from urllib.error import URLError
from urllib.parse import urlparse

from ...cache import DataSourceManager
from ...config import get_config_manager
from ...enums import AssessmentType
from ...logging_config import get_detail_logger, get_status_logger
from ...normalizer import input_normalizer
from ...validation import validate_issn
from ..core import DataSource
from ..utils import deduplicate_journals


detail_logger = get_detail_logger()
status_logger = get_status_logger()

_RECORD_DELIMITER = "--------------------------------------------------------"
_DEFAULT_TIMEOUT_SECONDS = 60
_DEFAULT_UPDATE_INTERVAL_DAYS = 30
_ALLOWED_HOST = "ftp.ncbi.nlm.nih.gov"


def _parse_nlm_records(text: str) -> list[dict[str, str]]:
    """Parse NLM journal list flat-file text into field dictionaries.

    Each record is delimited by a line of dashes. Fields are ``Key: Value``
    pairs, one per line.

    Args:
        text: Raw text content of the NLM flat file.

    Returns:
        List of dicts, one per journal record, with raw string values.
    """
    records: list[dict[str, str]] = []
    current: dict[str, str] = {}

    for line in text.splitlines():
        stripped = line.strip()
        if stripped == _RECORD_DELIMITER:
            if current:
                records.append(current)
                current = {}
            continue

        if ":" in stripped:
            key, _, value = stripped.partition(":")
            current[key.strip()] = value.strip()

    if current:
        records.append(current)

    return records


def _normalize_issn(raw: str, title: str) -> str | None:
    """Validate and normalize an ISSN string to ``NNNN-NNNN`` form.

    Args:
        raw: Raw ISSN value from the source file.
        title: Journal title (used only for logging).

    Returns:
        Normalized ISSN string, or ``None`` if invalid or empty.
    """
    issn = raw.strip()
    if not issn:
        return None

    if len(issn) == 8 and "-" not in issn:
        issn = f"{issn[:4]}-{issn[4:]}"

    if not validate_issn(issn):
        detail_logger.debug(
            f"pubmed_nlm: Invalid ISSN '{issn}' for '{title}' — skipping"
        )
        return None

    return issn


def _build_journal_entry(
    record: dict[str, str],
    is_medline: bool,
) -> dict[str, Any] | None:
    """Convert a raw NLM record dict into a normalized journal entry.

    Args:
        record: Raw field dict for one journal record.
        is_medline: Whether the entry comes from the MEDLINE subset.

    Returns:
        Normalized journal entry dict, or ``None`` if the title is missing.
    """
    title = record.get("JournalTitle", "").strip()
    if not title:
        return None

    issn = _normalize_issn(record.get("ISSN (Print)", ""), title)
    eissn = _normalize_issn(record.get("ISSN (Online)", ""), title)

    try:
        normalized_input = input_normalizer.normalize(title)
        normalized_name = (
            normalized_input.normalized_venue.name
            if normalized_input.normalized_venue
            else ""
        )
    except Exception as exc:
        detail_logger.debug(f"pubmed_nlm: Normalization failed for '{title}': {exc}")
        return None

    return {
        "journal_name": title,
        "normalized_name": normalized_name,
        "issn": issn,
        "eissn": eissn,
        "metadata": {
            "is_medline": is_medline,
            "med_abbr": record.get("MedAbbr", "").strip() or None,
            "nlm_id": record.get("NlmId", "").strip() or None,
        },
    }


class PubMedNLMSource(DataSource):
    """Data source for PubMed NLM journal lists (MEDLINE and NLM Catalog).

    Downloads two plain-text flat files from the NCBI FTP server:

    - ``J_Medline.txt`` — ~5 000 journals indexed in MEDLINE (stricter vetting)
    - ``J_Entrez.txt`` — ~30 000 journals across all NCBI databases (NLM Catalog)

    Journals found in the MEDLINE subset are stored with ``is_medline: True``
    in their metadata; remaining NLM Catalog journals are stored with
    ``is_medline: False``.  This flag is used by :class:`PubMedBackend` to
    apply a lower confidence score for less-vetted entries.
    """

    def __init__(self) -> None:
        """Initialize PubMed NLM source from configuration."""
        config = get_config_manager().load_config()
        self.medline_url: str = config.data_source_urls.pubmed_nlm_medline_url
        self.catalog_url: str = config.data_source_urls.pubmed_nlm_catalog_url

    def get_name(self) -> str:
        """Return the unique source identifier."""
        return "pubmed_nlm"

    def get_list_type(self) -> AssessmentType:
        """Return assessment classification for PubMed NLM data."""
        return AssessmentType.LEGITIMATE

    def should_update(self) -> bool:
        """Check whether the source data needs refreshing.

        Returns ``True`` when no previous update exists or the last update
        is older than 30 days.

        Returns:
            ``True`` if an update should be performed, ``False`` otherwise.
        """
        data_source_manager = DataSourceManager()
        last_update = data_source_manager.get_source_last_updated(self.get_name())
        if last_update is None:
            return True

        if (datetime.now() - last_update).days < _DEFAULT_UPDATE_INTERVAL_DAYS:
            self.skip_reason = "already_up_to_date"
            return False

        return True

    async def fetch_data(self) -> list[dict[str, Any]]:
        """Download and parse NLM journal flat files.

        Downloads J_Medline.txt first, then J_Entrez.txt.  Journals already
        present in the MEDLINE set (matched by NlmId) are not duplicated from
        the Entrez file.

        Returns:
            Deduplicated list of normalized journal entry dicts.
        """
        status_logger.info(f"    {self.get_name()}: Starting data fetch")

        medline_text = await self._fetch_file(self.medline_url)
        catalog_text = await self._fetch_file(self.catalog_url)

        medline_entries = self._parse_file(medline_text, is_medline=True)
        medline_nlm_ids = {
            str(e.get("metadata", {}).get("nlm_id", ""))
            for e in medline_entries
            if e.get("metadata", {}).get("nlm_id")
        }

        catalog_entries = self._parse_file(catalog_text, is_medline=False)
        catalog_only = [
            e
            for e in catalog_entries
            if str(e.get("metadata", {}).get("nlm_id", "")) not in medline_nlm_ids
        ]

        all_entries = medline_entries + catalog_only
        unique_entries = deduplicate_journals(all_entries)

        status_logger.info(
            f"    {self.get_name()}: Processed {len(unique_entries)} unique entries "
            f"({len(medline_entries)} MEDLINE, {len(catalog_only)} NLM Catalog only)"
        )
        return unique_entries

    def _parse_file(self, text: str, *, is_medline: bool) -> list[dict[str, Any]]:
        """Parse a downloaded NLM flat file into journal entry dicts.

        Args:
            text: Raw file content.
            is_medline: Tag to apply to each parsed entry.

        Returns:
            List of journal entry dicts (entries with missing titles omitted).
        """
        if not text:
            return []

        records = _parse_nlm_records(text)
        entries: list[dict[str, Any]] = []

        for record in records:
            entry = _build_journal_entry(record, is_medline=is_medline)
            if entry is not None:
                entries.append(entry)

        detail_logger.info(
            f"pubmed_nlm: Parsed {len(entries)} entries "
            f"({'MEDLINE' if is_medline else 'NLM Catalog'})"
        )
        return entries

    async def _fetch_file(self, url: str) -> str:
        """Download a plain-text file from the NCBI FTP server.

        Args:
            url: HTTPS URL to fetch (must be on ``ftp.ncbi.nlm.nih.gov``).

        Returns:
            Decoded UTF-8 text content, or empty string on failure.
        """
        try:
            text: str = await asyncio.to_thread(self._fetch_file_blocking, url)
            return text
        except (URLError, OSError, TimeoutError) as exc:
            status_logger.warning(
                f"    {self.get_name()}: Failed to fetch {url} — {exc}"
            )
            return ""

    def _fetch_file_blocking(self, url: str) -> str:
        """Perform a blocking HTTPS GET and return UTF-8 decoded body.

        Only requests to ``ftp.ncbi.nlm.nih.gov`` over HTTPS are allowed.

        Args:
            url: Validated HTTPS URL.

        Returns:
            UTF-8 decoded response body.

        Raises:
            URLError: If the scheme is not HTTPS, the host is wrong, or the
                server returns a non-200 status code.
        """
        parsed = urlparse(url)

        if parsed.scheme.lower() != "https":
            raise URLError("Only HTTPS scheme is allowed for PubMed NLM source")
        if parsed.hostname is None or parsed.hostname.lower() != _ALLOWED_HOST:
            raise URLError(f"PubMed NLM source URL host must be {_ALLOWED_HOST!r}")

        ssl_ctx = ssl.create_default_context()
        req = urllib.request.Request(url)
        with urllib.request.urlopen(  # nosec B310 - scheme validated as https above
            req, timeout=_DEFAULT_TIMEOUT_SECONDS, context=ssl_ctx
        ) as response:
            if response.status != 200:
                raise URLError(f"HTTP {response.status} from {url}")
            content: bytes = response.read()

        return content.decode("utf-8", errors="ignore")
