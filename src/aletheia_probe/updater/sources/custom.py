"""Custom CSV/JSON journal list data source."""

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from ...cache import get_cache_manager
from ...logging_config import get_detail_logger, get_status_logger
from ...normalizer import input_normalizer
from ..core import DataSource

detail_logger = get_detail_logger()
status_logger = get_status_logger()


class CustomListSource(DataSource):
    """Data source for custom CSV/JSON journal lists."""

    def __init__(self, file_path: Path, list_type: str, source_name: str):
        self.file_path = file_path
        self.list_type = list_type
        self.source_name = source_name

    def get_name(self) -> str:
        return self.source_name

    def get_list_type(self) -> str:
        return self.list_type

    def should_update(self) -> bool:
        """Check if file has been modified since last update."""
        if not self.file_path.exists():
            return False

        last_update = get_cache_manager().get_source_last_updated(self.get_name())
        if last_update is None:
            return True

        file_mtime = datetime.fromtimestamp(self.file_path.stat().st_mtime)
        return file_mtime > last_update

    async def fetch_data(self) -> list[dict[str, Any]]:
        """Load data from CSV or JSON file."""
        journals = []

        try:
            if self.file_path.suffix.lower() == ".json":
                journals = await self._load_json()
            elif self.file_path.suffix.lower() == ".csv":
                journals = await self._load_csv()
            else:
                status_logger.error(f"Unsupported file format: {self.file_path}")

        except Exception as e:
            status_logger.error(f"Failed to load {self.file_path}: {e}")

        return journals

    async def _load_json(self) -> list[dict[str, Any]]:
        """Load from JSON file."""
        with open(self.file_path, encoding="utf-8") as f:
            data = json.load(f)

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
        journals = []

        with open(self.file_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    journal_name = (
                        row.get("name") or row.get("journal_name") or row.get("title")
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
