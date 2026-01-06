# SPDX-License-Identifier: MIT
"""Custom CSV/JSON journal list data source."""

import asyncio
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from ...cache import DataSourceManager
from ...enums import AssessmentType
from ...logging_config import get_detail_logger, get_status_logger
from ...normalizer import input_normalizer
from ..core import DataSource


detail_logger = get_detail_logger()
status_logger = get_status_logger()


class CustomListSource(DataSource):
    """Data source for custom CSV/JSON journal lists."""

    def __init__(self, file_path: Path, list_type: AssessmentType, source_name: str):
        self.file_path = file_path
        self.list_type = list_type
        self.source_name = source_name

    def get_name(self) -> str:
        return self.source_name

    def get_list_type(self) -> AssessmentType:
        return self.list_type

    def should_update(self) -> bool:
        """Check if file has been modified since last update."""
        if not self.file_path.exists():
            status_logger.warning(
                f"    {self.get_name()}: Custom list file not found: {self.file_path}"
            )
            self.skip_reason = "file_not_found"
            return False

        data_source_manager = DataSourceManager()
        last_update = data_source_manager.get_source_last_updated(self.get_name())
        if last_update is None:
            return True

        file_mtime = datetime.fromtimestamp(self.file_path.stat().st_mtime)
        if file_mtime <= last_update:
            self.skip_reason = "file_not_modified"
            return False

        return True

    async def fetch_data(self) -> list[dict[str, Any]]:
        """Load data from CSV or JSON file."""
        journals = []

        try:
            if self.file_path.suffix.lower() == ".json":
                journals = await self._load_json()
            elif self.file_path.suffix.lower() == ".csv":
                journals = await self._load_csv()
            else:
                status_logger.error(
                    f"    {self.get_name()}: Unsupported file format - {self.file_path.suffix}"
                )

        except Exception as e:
            status_logger.error(f"    {self.get_name()}: Failed to load file - {e}")

        return journals

    async def _load_json(self) -> list[dict[str, Any]]:
        """Load from JSON file."""

        def _load_file_sync() -> Any:
            with open(self.file_path, encoding="utf-8") as f:
                return json.load(f)

        data: list[dict[str, Any]] = await asyncio.to_thread(_load_file_sync)

        journals = []
        for item in data:
            try:
                journal_name = (
                    item.get("name") or item.get("journal_name") or item.get("title")
                )
                if journal_name:
                    normalized_input = input_normalizer.normalize(journal_name)
                    journals.append(
                        {
                            "journal_name": journal_name,
                            "normalized_name": normalized_input.normalized_name,
                            "issn": item.get("issn"),
                            "eissn": item.get("eissn"),
                            "publisher": item.get("publisher"),
                            "metadata": {
                                k: v
                                for k, v in item.items()
                                if k
                                not in [
                                    "name",
                                    "journal_name",
                                    "title",
                                    "issn",
                                    "eissn",
                                    "publisher",
                                ]
                            },
                        }
                    )
            except Exception as e:
                detail_logger.debug(f"Failed to process journal entry: {e}")

        return journals

    async def _load_csv(self) -> list[dict[str, Any]]:
        """Load from CSV file."""

        def _read_csv_sync() -> list[dict[str, Any]]:
            journals = []
            with open(self.file_path, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        journal_name = (
                            row.get("name")
                            or row.get("journal_name")
                            or row.get("title")
                        )
                        if journal_name:
                            normalized_input = input_normalizer.normalize(journal_name)
                            journals.append(
                                {
                                    "journal_name": journal_name,
                                    "normalized_name": normalized_input.normalized_name,
                                    "issn": row.get("issn"),
                                    "eissn": row.get("eissn"),
                                    "publisher": row.get("publisher"),
                                    "metadata": {
                                        k: v
                                        for k, v in row.items()
                                        if k
                                        not in [
                                            "name",
                                            "journal_name",
                                            "title",
                                            "issn",
                                            "eissn",
                                            "publisher",
                                        ]
                                        and v.strip()
                                    },
                                }
                            )
                    except Exception as e:
                        detail_logger.debug(f"Failed to process CSV row: {e}")
            return journals

        return await asyncio.to_thread(_read_csv_sync)
