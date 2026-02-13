# SPDX-License-Identifier: MIT
"""DBLP conference data source using locally cached XML dump."""

import asyncio
import gzip
import html.entities
import io
import re
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from aiohttp import ClientSession, ClientTimeout
from defusedxml import ElementTree as DefusedET
from defusedxml.common import DefusedXmlException

from ...cache import DataSourceManager
from ...config import get_config_manager
from ...enums import AssessmentType
from ...logging_config import get_detail_logger, get_status_logger
from ...normalizer import input_normalizer
from ..core import DataSource


detail_logger = get_detail_logger()
status_logger = get_status_logger()


DEFAULT_UPDATE_INTERVAL_DAYS = 30
DEFAULT_DOWNLOAD_CHUNK_SIZE = 1024 * 1024  # 1 MiB
DEFAULT_MIN_ENTRIES_FOR_SERIES = 20
DEFAULT_MIN_ACTIVE_YEARS = 3
DEFAULT_SOCKET_READ_TIMEOUT_SECONDS = 900
DEFAULT_CONNECT_TIMEOUT_SECONDS = 30
DEFAULT_PARSE_PROGRESS_STEP_BYTES = 100 * 1024 * 1024  # 100 MiB
DEFAULT_PARSE_PROGRESS_STEP_RECORDS = 200_000

CONFERENCE_KEY_PREFIX = "conf/"
JOURNAL_KEY_PREFIX = "journals/"
PROCEEDINGS_TAG = "proceedings"
INPROCEEDINGS_TAG = "inproceedings"
ARTICLE_TAG = "article"
_NAMED_ENTITY_PATTERN = re.compile(r"&([A-Za-z][A-Za-z0-9]+);")
_XML_CORE_ENTITIES = {"amp", "lt", "gt", "apos", "quot"}


@dataclass
class _ConferenceSeriesAggregate:
    """Aggregated conference-series data from DBLP XML."""

    series_slug: str
    entry_count: int = 0
    years: set[int] = field(default_factory=set)
    preferred_name: str | None = None
    secondary_name: str | None = None


@dataclass
class _JournalSeriesAggregate:
    """Aggregated journal-series data from DBLP XML."""

    series_slug: str
    entry_count: int = 0
    years: set[int] = field(default_factory=set)
    preferred_name: str | None = None
    secondary_name: str | None = None
    issn_values: set[str] = field(default_factory=set)


class DblpVenueSource(DataSource):
    """Data source for DBLP conference and journal venues from local XML dump."""

    def __init__(
        self,
        data_dir: Path | None = None,
        update_interval_days: int = DEFAULT_UPDATE_INTERVAL_DAYS,
        min_entries_for_series: int = DEFAULT_MIN_ENTRIES_FOR_SERIES,
        min_active_years: int = DEFAULT_MIN_ACTIVE_YEARS,
    ) -> None:
        """Initialize DBLP venue source.

        Args:
            data_dir: Directory for local DBLP dump cache.
            update_interval_days: Minimum days between full refreshes.
            min_entries_for_series: Minimum records required for inclusion.
            min_active_years: Minimum distinct years required for inclusion.
        """
        config = get_config_manager().load_config()
        self.dump_url = config.data_source_urls.dblp_xml_dump_url
        self.update_interval_days = update_interval_days
        self.min_entries_for_series = min_entries_for_series
        self.min_active_years = min_active_years
        self.timeout = ClientTimeout(
            total=None,
            connect=DEFAULT_CONNECT_TIMEOUT_SECONDS,
            sock_read=DEFAULT_SOCKET_READ_TIMEOUT_SECONDS,
        )

        if data_dir is None:
            data_dir = Path.cwd() / ".aletheia-probe" / "dblp"
        self.data_dir = data_dir
        self.dump_path = self.data_dir / "dblp.xml.gz"

    def get_name(self) -> str:
        """Return source name."""
        return "dblp_venues"

    def get_list_type(self) -> AssessmentType:
        """Return list type for DBLP venue entries."""
        return AssessmentType.LEGITIMATE

    def should_update(self) -> bool:
        """Check whether DBLP dump should be refreshed."""
        if not self.dump_path.exists():
            self.skip_reason = "local_dump_missing"
            return True

        data_source_manager = DataSourceManager()
        last_update = data_source_manager.get_source_last_updated(self.get_name())
        if last_update is None:
            return True

        if (datetime.now() - last_update).days < self.update_interval_days:
            self.skip_reason = "already_up_to_date"
            return False

        return True

    async def fetch_data(self) -> list[dict[str, Any]]:
        """Download DBLP dump and extract venue series entries."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if self.dump_path.exists():
            status_logger.info(
                f"    {self.get_name()}: Local dump found, skipping download"
            )
        journals = await self._load_or_refresh_dump_data()
        status_logger.info(
            f"    {self.get_name()}: Extracted {len(journals):,} venue entries"
        )
        return journals

    async def _load_or_refresh_dump_data(self) -> list[dict[str, Any]]:
        """Load venue data from local dump, refreshing only on missing/corrupt files."""
        if self.dump_path.exists():
            status_logger.info(
                f"    {self.get_name()}: Using existing local dump {self.dump_path}"
            )
            try:
                status_logger.info(f"    {self.get_name()}: Parsing local XML dump...")
                return await asyncio.to_thread(self._parse_dump_file)
            except (
                DefusedET.ParseError,
                DefusedXmlException,
                OSError,
                EOFError,
                gzip.BadGzipFile,
            ) as e:
                status_logger.warning(
                    "    "
                    f"{self.get_name()}: Existing dump invalid ({e}); "
                    "re-downloading"
                )
                detail_logger.exception("Failed to parse existing DBLP dump")

        await self._download_dump()
        status_logger.info(f"    {self.get_name()}: Parsing local XML dump...")
        return await asyncio.to_thread(self._parse_dump_file)

    async def _download_dump(self) -> None:
        """Download DBLP XML dump to local cache path."""
        status_logger.info(
            f"    {self.get_name()}: Downloading DBLP dump to {self.dump_path}"
        )
        detail_logger.info(f"DBLP download URL: {self.dump_url}")

        with tempfile.NamedTemporaryFile(
            mode="wb",
            delete=False,
            dir=str(self.data_dir),
            prefix="dblp-",
            suffix=".xml.gz.part",
        ) as tmp_file:
            tmp_path = Path(tmp_file.name)

        total_bytes = 0
        log_interval_bytes = 100 * 1024 * 1024  # 100 MiB
        next_log_at = log_interval_bytes

        try:
            async with ClientSession(timeout=self.timeout) as session:
                async with session.get(self.dump_url) as response:
                    response.raise_for_status()

                    with open(tmp_path, "wb") as f:
                        async for chunk in response.content.iter_chunked(
                            DEFAULT_DOWNLOAD_CHUNK_SIZE
                        ):
                            if not chunk:
                                continue
                            f.write(chunk)
                            total_bytes += len(chunk)

                            if total_bytes >= next_log_at:
                                status_logger.info(
                                    "    "
                                    f"{self.get_name()}: Downloaded "
                                    f"{total_bytes / (1024 * 1024):,.0f} MiB..."
                                )
                                next_log_at += log_interval_bytes

            tmp_path.replace(self.dump_path)
            status_logger.info(
                "    "
                f"{self.get_name()}: Download complete "
                f"({total_bytes / (1024 * 1024):,.0f} MiB)"
            )
        finally:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)

    def _parse_dump_file(self) -> list[dict[str, Any]]:
        """Parse local DBLP XML dump and build conference and journal entries."""
        series_map: dict[str, _ConferenceSeriesAggregate] = {}
        journal_map: dict[str, _JournalSeriesAggregate] = {}
        processed_records = 0
        next_record_log = DEFAULT_PARSE_PROGRESS_STEP_RECORDS
        total_compressed_bytes = self.dump_path.stat().st_size
        next_byte_log = DEFAULT_PARSE_PROGRESS_STEP_BYTES

        with open(self.dump_path, "rb") as raw_file:
            with gzip.GzipFile(fileobj=raw_file, mode="rb") as gz_file:
                text_stream = io.TextIOWrapper(
                    gz_file, encoding="utf-8", errors="ignore"
                )
                sanitized_reader = _NamedEntitySanitizingReader(text_stream)
                for _event, elem in DefusedET.iterparse(
                    sanitized_reader, events=("end",)
                ):
                    compressed_pos = raw_file.tell()
                    if compressed_pos >= next_byte_log:
                        percent = (
                            (compressed_pos / total_compressed_bytes) * 100
                            if total_compressed_bytes > 0
                            else 0.0
                        )
                        status_logger.info(
                            "    "
                            f"{self.get_name()}: Parse progress "
                            f"{compressed_pos / (1024 * 1024):,.0f} / "
                            f"{total_compressed_bytes / (1024 * 1024):,.0f} MiB "
                            f"({percent:.1f}%)"
                        )
                        next_byte_log += DEFAULT_PARSE_PROGRESS_STEP_BYTES

                    tag = elem.tag
                    key = elem.attrib.get("key", "")
                    if tag in (PROCEEDINGS_TAG, INPROCEEDINGS_TAG):
                        if not key.startswith(CONFERENCE_KEY_PREFIX):
                            elem.clear()
                            continue

                        self._accumulate_conference_entry(series_map, key, tag, elem)
                        processed_records += 1
                    elif tag == ARTICLE_TAG:
                        if not key.startswith(JOURNAL_KEY_PREFIX):
                            elem.clear()
                            continue

                        self._accumulate_journal_entry(journal_map, key, elem)
                        processed_records += 1
                    else:
                        continue

                    if processed_records >= next_record_log:
                        status_logger.info(
                            "    "
                            f"{self.get_name()}: Parsed "
                            f"{processed_records:,} records..."
                        )
                        next_record_log += DEFAULT_PARSE_PROGRESS_STEP_RECORDS

                    elem.clear()

        status_logger.info(
            "    "
            f"{self.get_name()}: XML scan complete "
            f"({processed_records:,} matching records)"
        )
        status_logger.info(
            f"    {self.get_name()}: Building aggregated venue entries..."
        )

        conference_entries = self._build_conference_entries(series_map)
        journal_entries = self._build_journal_series_entries(journal_map)
        return conference_entries + journal_entries

    def _accumulate_conference_entry(
        self,
        series_map: dict[str, _ConferenceSeriesAggregate],
        key: str,
        tag: str,
        elem: Any,
    ) -> None:
        """Accumulate one conference entry into aggregate map."""
        series_slug = self._extract_series_slug(key, CONFERENCE_KEY_PREFIX)
        if not series_slug:
            return

        aggregate = series_map.setdefault(
            series_slug, _ConferenceSeriesAggregate(series_slug=series_slug)
        )
        aggregate.entry_count += 1

        year_value = self._parse_year(elem.findtext("year"))
        if year_value is not None:
            aggregate.years.add(year_value)

        # Keep memory bounded: capture only a small number of stable series names.
        booktitle = self._clean_text(elem.findtext("booktitle"))
        self._update_preferred_names(aggregate, booktitle)

        # Proceedings titles can contain useful series aliases; paper titles do not.
        if tag == PROCEEDINGS_TAG:
            title_hint = self._extract_title_series_hint(
                self._clean_text(elem.findtext("title"))
            )
            self._update_preferred_names(aggregate, title_hint)

    def _accumulate_journal_entry(
        self,
        journal_map: dict[str, _JournalSeriesAggregate],
        key: str,
        elem: Any,
    ) -> None:
        """Accumulate one journal article entry into aggregate map."""
        series_slug = self._extract_series_slug(key, JOURNAL_KEY_PREFIX)
        if not series_slug:
            return

        aggregate = journal_map.setdefault(
            series_slug, _JournalSeriesAggregate(series_slug=series_slug)
        )
        aggregate.entry_count += 1

        year_value = self._parse_year(elem.findtext("year"))
        if year_value is not None:
            aggregate.years.add(year_value)

        # Journal field is stable series metadata; article titles are high-cardinality.
        journal_name = self._clean_text(elem.findtext("journal"))
        self._update_preferred_names(aggregate, journal_name)

        issn_value = self._normalize_issn(self._clean_text(elem.findtext("issn")))
        if issn_value:
            aggregate.issn_values.add(issn_value)

    def _build_conference_entries(
        self, series_map: dict[str, _ConferenceSeriesAggregate]
    ) -> list[dict[str, Any]]:
        """Convert aggregated conference series into cache entries."""
        journals: list[dict[str, Any]] = []
        seen_name_pairs: set[tuple[str, str]] = set()

        for series_slug, aggregate in series_map.items():
            if aggregate.entry_count < self.min_entries_for_series:
                continue
            if len(aggregate.years) < self.min_active_years:
                continue

            top_names = self._build_top_names(
                aggregate.preferred_name, aggregate.secondary_name, series_slug
            )
            if not top_names:
                fallback_name = series_slug.replace("-", " ").strip()
                top_names = [fallback_name]

            series_url = f"https://dblp.org/db/conf/{series_slug}/"
            first_year = min(aggregate.years) if aggregate.years else None
            last_year = max(aggregate.years) if aggregate.years else None

            for name in top_names:
                normalized_name = self._normalize_name(name)
                if not normalized_name:
                    continue

                pair_key = (normalized_name, name)
                if pair_key in seen_name_pairs:
                    continue
                seen_name_pairs.add(pair_key)

                journals.append(
                    {
                        "journal_name": name,
                        "normalized_name": normalized_name,
                        "urls": [series_url],
                        "metadata": {
                            "source_url": series_url,
                            "dblp_entry_type": "conference",
                            "dblp_series": series_slug,
                            "dblp_entry_count": aggregate.entry_count,
                            "dblp_first_year": first_year,
                            "dblp_last_year": last_year,
                            "dblp_active_years": len(aggregate.years),
                        },
                    }
                )

        return journals

    def _build_journal_series_entries(
        self, journal_map: dict[str, _JournalSeriesAggregate]
    ) -> list[dict[str, Any]]:
        """Convert aggregated journal series into cache entries."""
        journals: list[dict[str, Any]] = []
        seen_name_pairs: set[tuple[str, str]] = set()

        for series_slug, aggregate in journal_map.items():
            if aggregate.entry_count < self.min_entries_for_series:
                continue
            if len(aggregate.years) < self.min_active_years:
                continue

            top_names = self._build_top_names(
                aggregate.preferred_name, aggregate.secondary_name, series_slug
            )
            if not top_names:
                fallback_name = series_slug.replace("-", " ").strip()
                top_names = [fallback_name]

            series_url = f"https://dblp.org/db/journals/{series_slug}/"
            first_year = min(aggregate.years) if aggregate.years else None
            last_year = max(aggregate.years) if aggregate.years else None
            primary_issn = (
                sorted(aggregate.issn_values)[0] if aggregate.issn_values else None
            )

            for name in top_names:
                normalized_name = self._normalize_name(name)
                if not normalized_name:
                    continue

                pair_key = (normalized_name, name)
                if pair_key in seen_name_pairs:
                    continue
                seen_name_pairs.add(pair_key)

                journals.append(
                    {
                        "journal_name": name,
                        "normalized_name": normalized_name,
                        "issn": primary_issn,
                        "urls": [series_url],
                        "metadata": {
                            "source_url": series_url,
                            "dblp_entry_type": "journal",
                            "dblp_series": series_slug,
                            "dblp_entry_count": aggregate.entry_count,
                            "dblp_first_year": first_year,
                            "dblp_last_year": last_year,
                            "dblp_active_years": len(aggregate.years),
                        },
                    }
                )

        return journals

    def _extract_series_slug(self, key: str, prefix: str) -> str | None:
        """Extract DBLP series slug from XML key and expected prefix."""
        if not key.startswith(prefix):
            return None

        suffix = key[len(prefix) :]
        if not suffix:
            return None

        parts = suffix.split("/")
        if not parts:
            return None
        return parts[0].strip() or None

    def _parse_year(self, year_text: str | None) -> int | None:
        """Parse year from XML text value."""
        if not year_text:
            return None
        try:
            year = int(year_text.strip())
        except ValueError:
            return None
        return year if 1900 <= year <= 2100 else None

    def _clean_text(self, value: str | None) -> str:
        """Normalize whitespace in source text."""
        if not value:
            return ""
        return re.sub(r"\s+", " ", value).strip()

    def _extract_title_series_hint(self, title: str) -> str | None:
        """Extract coarse series hint from proceedings title."""
        if not title:
            return None

        if ":" in title:
            title = title.split(":", 1)[0]
        hint = title.split(",", 1)[0].strip()
        return hint if len(hint) >= 3 else None

    def _update_preferred_names(
        self,
        aggregate: _ConferenceSeriesAggregate | _JournalSeriesAggregate,
        candidate: str | None,
    ) -> None:
        """Store at most two distinct candidate names per series to bound memory."""
        if not candidate:
            return

        name = candidate.strip()
        if len(name) < 2:
            return

        if aggregate.preferred_name is None:
            aggregate.preferred_name = name
            return

        if name == aggregate.preferred_name:
            return

        if aggregate.secondary_name is None:
            aggregate.secondary_name = name
            return

        if name == aggregate.secondary_name:
            return

    def _build_top_names(
        self, preferred_name: str | None, secondary_name: str | None, series_slug: str
    ) -> list[str]:
        """Return stable candidate names for series entry generation."""
        names = []
        if preferred_name:
            names.append(preferred_name)
        if secondary_name and secondary_name != preferred_name:
            names.append(secondary_name)

        if not names:
            fallback_name = series_slug.replace("-", " ").strip()
            if fallback_name:
                names.append(fallback_name)
        return names

    def _normalize_name(self, name: str) -> str | None:
        """Normalize conference name for cache insertion."""
        try:
            normalized = input_normalizer.normalize(name).normalized_name
        except Exception:
            detail_logger.debug(f"Failed to normalize DBLP conference name: {name}")
            return None

        if not normalized or len(normalized) < 3:
            return None
        return normalized

    def _normalize_issn(self, issn: str) -> str | None:
        """Normalize ISSN into NNNN-NNNN form when possible."""
        if not issn:
            return None

        compact = re.sub(r"[^0-9Xx]", "", issn)
        if len(compact) != 8:
            return None

        return f"{compact[:4]}-{compact[4:].upper()}"


class _NamedEntitySanitizingReader:
    """File-like wrapper that decodes named HTML entities safely for XML parsing."""

    def __init__(self, wrapped: Any) -> None:
        self._wrapped = wrapped
        self._carry = ""

    def read(self, size: int = -1) -> str:
        """Read text and decode named entities while preserving XML core entities."""
        chunk = self._wrapped.read(size)
        if chunk == "":
            data = self._carry
            self._carry = ""
            return self._decode_named_entities(data)

        data = self._carry + chunk
        main, self._carry = self._split_incomplete_entity_tail(data)
        return self._decode_named_entities(main)

    def _split_incomplete_entity_tail(self, data: str) -> tuple[str, str]:
        """Keep incomplete trailing entity text for the next read call."""
        last_amp = data.rfind("&")
        if last_amp == -1:
            return data, ""

        trailing = data[last_amp:]
        if ";" in trailing:
            return data, ""

        return data[:last_amp], trailing

    def _decode_named_entities(self, text: str) -> str:
        """Decode HTML named entities except XML core entities."""

        def replacer(match: re.Match[str]) -> str:
            entity_name = match.group(1)
            if entity_name in _XML_CORE_ENTITIES:
                return match.group(0)

            decoded = html.unescape(match.group(0))
            return decoded if decoded != match.group(0) else " "

        return _NAMED_ENTITY_PATTERN.sub(replacer, text)
