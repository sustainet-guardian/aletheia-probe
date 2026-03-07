# SPDX-License-Identifier: MIT
"""OpenCitations client + local/remote factory."""

from __future__ import annotations

import importlib
import os
from typing import Any

import aiohttp

from .backend_exceptions import BackendError, RateLimitError

_DEFAULT_BASE_URL = "https://api.opencitations.net/index/v2"
_DEFAULT_TIMEOUT_SECONDS = 20


class OpenCitationsClient:
    """Async remote client for OpenCitations API."""

    def __init__(
        self, base_url: str = _DEFAULT_BASE_URL, timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> "OpenCitationsClient":
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self._timeout_seconds),
            trust_env=True,
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def get_venue_citation_count_by_issn(self, issn: str) -> int | None:
        url = f"{self._base_url}/venue-citation-count/issn:{issn.strip().upper()}"
        return await self._fetch_count(url)

    async def get_venue_reference_count_by_issn(self, issn: str) -> int | None:
        url = f"{self._base_url}/venue-reference-count/issn:{issn.strip().upper()}"
        return await self._fetch_count(url)

    async def _fetch_count(self, url: str) -> int | None:
        session = self._require_session()
        async with session.get(url) as response:
            if response.status == 429:
                raise RateLimitError(
                    "OpenCitations API rate limit exceeded", backend_name="opencitations_analyzer"
                )
            if response.status == 404:
                return None
            if response.status != 200:
                error_text = await response.text()
                raise BackendError(
                    (
                        f"OpenCitations API returned status {response.status}. "
                        f"Response: {error_text[:200]}"
                    ),
                    backend_name="opencitations_analyzer",
                )

            payload = await response.json()
            return _parse_count_payload(payload)

    def _require_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            raise RuntimeError("OpenCitationsClient must be used as an async context manager")
        return self._session


def _parse_count_payload(payload: Any) -> int | None:
    if isinstance(payload, list):
        if not payload:
            return None
        if isinstance(payload[0], dict):
            for key in ("count", "citation_count", "reference_count"):
                value = payload[0].get(key)
                parsed = _safe_int(value)
                if parsed is not None:
                    return parsed
        return None

    if isinstance(payload, dict):
        for key in ("count", "citation_count", "reference_count"):
            value = payload.get(key)
            parsed = _safe_int(value)
            if parsed is not None:
                return parsed

    return None


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return int(stripped)
        except ValueError:
            return None
    return None


def create_opencitations_client(
    base_url: str = _DEFAULT_BASE_URL, timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS
) -> Any:
    """Factory returning remote client or local adapter based on OPENCITATIONS_MODE.

    OPENCITATIONS_MODE=local requires optional package ``aletheia-opencitations-adapter``.
    """
    mode = os.environ.get("OPENCITATIONS_MODE", "remote").strip().lower()
    if mode == "local":
        try:
            adapter_module = importlib.import_module("aletheia_opencitations_adapter")
            return adapter_module.create_opencitations_client(mode="local")
        except ImportError as exc:
            raise ImportError(
                "OPENCITATIONS_MODE=local requires the aletheia-opencitations-adapter package. "
                "Install it from the aletheia-probe-opencitations-platform repo:\n"
                "  pip install 'git+https://github.com/sustainet-guardian/"
                "aletheia-probe-opencitations-platform.git#subdirectory=adapter'"
            ) from exc

    return OpenCitationsClient(base_url=base_url, timeout_seconds=timeout_seconds)
