# SPDX-License-Identifier: MIT
"""UGC-CARE discontinued list data sources."""

import re
from datetime import datetime
from html import unescape
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout

from ...cache import DataSourceManager
from ...config import get_config_manager
from ...enums import AssessmentType
from ...logging_config import get_detail_logger, get_status_logger
from ...normalizer import input_normalizer
from ..core import DataSource
from ..utils import deduplicate_journals


detail_logger = get_detail_logger()
status_logger = get_status_logger()

DEFAULT_TIMEOUT_SECONDS = 60
UPDATE_INTERVAL_DAYS = 30


class UgcCareListSource(DataSource):
    """Base data source for scraping discontinued UGC-CARE list pages."""

    def __init__(
        self, source_name: str, source_url: str, list_type: AssessmentType
    ) -> None:
        self._source_name = source_name
        self.source_url = source_url
        self._list_type = list_type
        self.timeout = ClientTimeout(total=DEFAULT_TIMEOUT_SECONDS)

    def get_name(self) -> str:
        """Return unique source name."""
        return self._source_name

    def get_list_type(self) -> AssessmentType:
        """Return list type used for discontinued UGC-CARE lists."""
        return self._list_type

    def should_update(self) -> bool:
        """Check if source should be refreshed from UGC-CARE pages."""
        data_source_manager = DataSourceManager()
        last_update = data_source_manager.get_source_last_updated(self.get_name())
        if last_update is None:
            return True

        if (datetime.now() - last_update).days < UPDATE_INTERVAL_DAYS:
            self.skip_reason = "already_up_to_date"
            return False

        return True

    async def fetch_data(self) -> list[dict[str, Any]]:
        """Fetch and parse list entries from the configured UGC-CARE page."""
        status_logger.info(f"    {self.get_name()}: Starting data fetch")
        try:
            async with ClientSession(timeout=self.timeout) as session:
                async with session.get(self.source_url) as response:
                    if response.status != 200:
                        status_logger.warning(
                            f"    {self.get_name()}: HTTP {response.status} from source page"
                        )
                        return []
                    html_content = await response.text()
        except (ClientError, TimeoutError) as e:
            status_logger.error(f"    {self.get_name()}: Failed to fetch data - {e}")
            return []

        entries = self._parse_entries(html_content)
        deduplicated_entries = deduplicate_journals(entries)
        status_logger.info(
            f"    {self.get_name()}: Processed {len(deduplicated_entries)} unique entries"
        )
        detail_logger.info(
            f"{self.get_name()}: Parsed {len(entries)} entries from {self.source_url}"
        )
        return deduplicated_entries

    def _parse_entries(self, html_content: str) -> list[dict[str, Any]]:
        """Parse source-specific HTML into normalized journal entries."""
        raise NotImplementedError("Subclasses must implement entry parsing")

    def _build_entry(
        self,
        title: str,
        publisher: str | None,
        issn: str | None,
        eissn: str | None,
        metadata: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Build normalized journal entry dictionary."""
        clean_title = self._clean_text(title)
        if not clean_title:
            return None

        try:
            normalized = input_normalizer.normalize(clean_title)
        except Exception as e:
            detail_logger.debug(
                f"{self.get_name()}: Failed to normalize title '{clean_title}' - {e}"
            )
            return None

        return {
            "journal_name": clean_title,
            "normalized_name": normalized.normalized_name,
            "issn": self._normalize_issn(issn),
            "eissn": self._normalize_issn(eissn),
            "publisher": self._clean_text(publisher) if publisher else None,
            "metadata": metadata,
        }

    @staticmethod
    def _clean_text(value: str | None) -> str:
        """Clean HTML text into compact plain text."""
        if not value:
            return ""
        cleaned = re.sub(r"<[^>]+>", " ", value)
        cleaned = unescape(cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    @staticmethod
    def _normalize_issn(value: str | None) -> str | None:
        """Normalize ISSN to NNNN-NNNX if pattern is present."""
        if not value:
            return None

        match = re.search(r"\b(\d{4})\s*-\s*([\dXx]{4})\b", value)
        if not match:
            return None

        return f"{match.group(1)}-{match.group(2).upper()}"


class UgcCareClonedSource(UgcCareListSource):
    """Data source for UGC-CARE Group-I cloned journals list."""

    def __init__(self) -> None:
        config = get_config_manager().load_config()
        super().__init__(
            source_name="ugc_care_cloned",
            source_url=config.data_source_urls.ugc_care_cloned_url,
            list_type=AssessmentType.PREDATORY,
        )

    def _parse_entries(self, html_content: str) -> list[dict[str, Any]]:
        """Parse cloned-journal blocks and keep the cloned title per record."""
        return self._parse_clone_pair_entries(
            html_content=html_content,
            included_status="included_group_i_from_clone_page",
            cloned_status="cloned_group_i",
            include_left_side=False,
        )

    def _parse_clone_pair_entries(
        self,
        html_content: str,
        included_status: str,
        cloned_status: str,
        include_left_side: bool,
    ) -> list[dict[str, Any]]:
        """Parse UGC clone-pair records and emit left/right side entries."""
        text_with_lines = re.sub(r"<[^>]+>", "\n", html_content)
        text_with_lines = unescape(text_with_lines)
        text_with_lines = re.sub(r"\r", "\n", text_with_lines)
        text_with_lines = re.sub(r"[ \t]+", " ", text_with_lines)
        text_with_lines = re.sub(r"\n+", "\n", text_with_lines).strip()

        record_start_matches = list(
            re.finditer(r"(?m)^\s*\d+\s+Title\s*-", text_with_lines)
        )
        records: list[str] = []
        for index, match in enumerate(record_start_matches):
            start = match.start()
            end = (
                record_start_matches[index + 1].start()
                if index + 1 < len(record_start_matches)
                else len(text_with_lines)
            )
            records.append(text_with_lines[start:end])

        entries: list[dict[str, Any]] = []
        for record in records:
            sides = self._extract_clone_record_sides(record)
            if not sides:
                continue

            original_side = sides[0]
            cloned_side = sides[-1]
            original_title_raw = original_side.get("title")
            cloned_title_raw = cloned_side.get("title")
            if not isinstance(original_title_raw, str) or not isinstance(
                cloned_title_raw, str
            ):
                continue
            original_title = original_title_raw
            cloned_title = cloned_title_raw

            if include_left_side:
                included_entry = self._build_entry(
                    title=original_title,
                    publisher=original_side.get("publisher"),
                    issn=original_side.get("issn"),
                    eissn=original_side.get("eissn"),
                    metadata={
                        "source_url": self.source_url,
                        "ugc_status": included_status,
                        "paired_cloned_title": (
                            cloned_title if cloned_title != original_title else None
                        ),
                    },
                )
                if included_entry:
                    entries.append(included_entry)

            cloned_entry = self._build_entry(
                title=cloned_title,
                publisher=cloned_side.get("publisher"),
                issn=cloned_side.get("issn"),
                eissn=cloned_side.get("eissn"),
                metadata={
                    "source_url": self.source_url,
                    "ugc_status": cloned_status,
                    "original_title": (
                        original_title
                        if original_title and original_title != cloned_title
                        else None
                    ),
                },
            )
            if cloned_entry:
                entries.append(cloned_entry)

        return entries

    def _extract_clone_record_sides(self, record: str) -> list[dict[str, str | None]]:
        """Extract ordered sides (included/cloned) from one clone-page record."""
        title_matches = list(
            re.finditer(
                r"Title\s*-\s*(.+?)(?=\s+(?:URL|Publisher|ISSN|E-ISSN|Title\s*-|$))",
                record,
                re.IGNORECASE | re.DOTALL,
            )
        )
        if not title_matches:
            return []

        sides: list[dict[str, str | None]] = []
        for index, match in enumerate(title_matches):
            title = self._clean_text(match.group(1))
            start = match.end()
            end = (
                title_matches[index + 1].start()
                if index + 1 < len(title_matches)
                else len(record)
            )
            segment = record[start:end]

            publisher_match = re.search(
                r"Publisher\s*:?\s*(.+?)(?=\s+(?:ISSN|E-ISSN|$))",
                segment,
                re.IGNORECASE | re.DOTALL,
            )
            publisher = (
                self._clean_text(publisher_match.group(1)) if publisher_match else None
            )
            segment_issns = re.findall(r"\b\d{4}\s*-\s*[\dXx]{4}\b", segment)
            issn = segment_issns[0] if len(segment_issns) >= 1 else None
            eissn = segment_issns[1] if len(segment_issns) >= 2 else None

            sides.append(
                {
                    "title": title,
                    "publisher": publisher,
                    "issn": issn,
                    "eissn": eissn,
                }
            )

        return sides


class UgcCareClonedGroup2Source(UgcCareClonedSource):
    """Data source for UGC-CARE Group-II cloned journals list."""

    def __init__(self) -> None:
        config = get_config_manager().load_config()
        UgcCareListSource.__init__(
            self,
            source_name="ugc_care_cloned_group2",
            source_url=config.data_source_urls.ugc_care_cloned_group2_url,
            list_type=AssessmentType.PREDATORY,
        )

    def _parse_entries(self, html_content: str) -> list[dict[str, Any]]:
        """Parse cloned-journal blocks for Group II source."""
        return self._parse_clone_pair_entries(
            html_content=html_content,
            included_status="included_group_ii_from_clone_page",
            cloned_status="cloned_group_ii",
            include_left_side=False,
        )


class UgcCareDelistedGroup2Source(UgcCareListSource):
    """Data source for UGC-CARE Group-II delisted journals list."""

    def __init__(self) -> None:
        config = get_config_manager().load_config()
        super().__init__(
            source_name="ugc_care_delisted_group2",
            source_url=config.data_source_urls.ugc_care_delisted_group2_url,
            list_type=AssessmentType.PREDATORY,
        )

    def _parse_entries(self, html_content: str) -> list[dict[str, Any]]:
        """Parse delisted table rows into normalized journal entries."""
        rows = re.findall(
            r"<tr[^>]*>(.*?)</tr>", html_content, re.IGNORECASE | re.DOTALL
        )
        entries: list[dict[str, Any]] = []

        for row in rows:
            cells = re.findall(
                r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.IGNORECASE | re.DOTALL
            )
            if len(cells) < 6:
                continue

            first_cell = self._clean_text(cells[0]).lower()
            if not first_cell.isdigit():
                continue

            title = self._clean_text(cells[1])
            if not title or "journal title" in title.lower():
                continue

            publisher = self._clean_text(cells[2])
            issn = self._clean_text(cells[3])
            eissn = self._clean_text(cells[4])
            coverage = self._clean_text(cells[5])

            entry = self._build_entry(
                title=title,
                publisher=publisher,
                issn=issn,
                eissn=eissn,
                metadata={
                    "source_url": self.source_url,
                    "ugc_status": "delisted_group_ii",
                    "coverage": coverage or None,
                },
            )
            if entry:
                entries.append(entry)

        return entries


class UgcCareIncludedFromCloneGroup1Source(UgcCareClonedSource):
    """Data source for included (left-side) journals from Group-I clone page."""

    def __init__(self) -> None:
        config = get_config_manager().load_config()
        UgcCareListSource.__init__(
            self,
            source_name="ugc_care_included_from_clone_group1",
            source_url=config.data_source_urls.ugc_care_cloned_url,
            list_type=AssessmentType.LEGITIMATE,
        )

    def _parse_entries(self, html_content: str) -> list[dict[str, Any]]:
        return self._parse_clone_pair_entries(
            html_content=html_content,
            included_status="included_group_i_from_clone_page",
            cloned_status="cloned_group_i",
            include_left_side=True,
        )


class UgcCareIncludedFromCloneGroup2Source(UgcCareClonedSource):
    """Data source for included (left-side) journals from Group-II clone page."""

    def __init__(self) -> None:
        config = get_config_manager().load_config()
        UgcCareListSource.__init__(
            self,
            source_name="ugc_care_included_from_clone_group2",
            source_url=config.data_source_urls.ugc_care_cloned_group2_url,
            list_type=AssessmentType.LEGITIMATE,
        )

    def _parse_entries(self, html_content: str) -> list[dict[str, Any]]:
        return self._parse_clone_pair_entries(
            html_content=html_content,
            included_status="included_group_ii_from_clone_page",
            cloned_status="cloned_group_ii",
            include_left_side=True,
        )
