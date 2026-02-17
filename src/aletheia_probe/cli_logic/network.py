# SPDX-License-Identifier: MIT
"""Network helpers for CLI workflows."""

import asyncio
import json
from typing import Any
from urllib.parse import urlparse

import aiohttp


ISSN_RESOLUTION_TIMEOUT_SECONDS: int = 8
GITHUB_HTTP_TIMEOUT_SECONDS: int = 120
GITHUB_ALLOWED_HOSTS: set[str] = {
    "api.github.com",
    "github.com",
    "objects.githubusercontent.com",
    "raw.githubusercontent.com",
    "release-assets.githubusercontent.com",
}
CROSSREF_ALLOWED_HOSTS: set[str] = {"api.crossref.org"}


def _is_allowed_host(host: str, allowed_hosts: set[str]) -> bool:
    """Check whether a host is in the allowlist (exact or subdomain)."""
    normalized = host.lower().strip()
    if not normalized:
        return False
    return any(
        normalized == allowed or normalized.endswith(f".{allowed}")
        for allowed in allowed_hosts
    )


def _validate_https_url(url: str, allowed_hosts: set[str]) -> None:
    """Validate URL scheme/host against strict HTTPS allowlist."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https":
        raise ValueError(f"Only https URLs are allowed: {url}")
    if not _is_allowed_host(host, allowed_hosts):
        raise ValueError(f"Host not allowed: {host}")


async def _fetch_https_text(
    url: str, timeout_seconds: int, allowed_hosts: set[str]
) -> str:
    """Fetch text over HTTPS with host allowlist + redirect host verification."""
    _validate_https_url(url, allowed_hosts)

    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    async with aiohttp.ClientSession(timeout=timeout, trust_env=True) as session:
        async with session.get(url, allow_redirects=True) as response:
            response.raise_for_status()
            final_host = (response.url.host or "").lower()
            if not _is_allowed_host(final_host, allowed_hosts):
                raise ValueError(f"Redirected to disallowed host: {final_host}")
            return await response.text()


async def _fetch_https_json(
    url: str, timeout_seconds: int, allowed_hosts: set[str]
) -> dict[str, Any] | list[Any]:
    """Fetch JSON over HTTPS with strict URL/host checks."""
    text = await _fetch_https_text(url, timeout_seconds, allowed_hosts)
    data = json.loads(text)
    if not isinstance(data, (dict, list)):
        raise ValueError("Expected JSON object or list")
    return data


async def _resolve_issn_title(issn: str) -> str | None:
    """Resolve ISSN to title via Crossref journals endpoint."""
    try:
        payload = await _fetch_https_json(
            f"https://api.crossref.org/journals/{issn}",
            ISSN_RESOLUTION_TIMEOUT_SECONDS,
            CROSSREF_ALLOWED_HOSTS,
        )
        if not isinstance(payload, dict):
            return None
        message = payload.get("message", {})
        if isinstance(message, dict):
            title = message.get("title")
            if isinstance(title, str) and title.strip():
                return title.strip()
    except (aiohttp.ClientError, json.JSONDecodeError, ValueError, OSError):
        return None
    return None


def _get_latest_acronym_dataset_url(repo: str) -> tuple[str, str]:
    """Get dataset download URL and source label from latest GitHub release."""
    if "/" not in repo:
        raise ValueError("Repository must be in 'owner/name' format")

    api_url = f"https://api.github.com/repos/{repo}/releases/latest"
    payload = asyncio.run(
        _fetch_https_json(api_url, GITHUB_HTTP_TIMEOUT_SECONDS, GITHUB_ALLOWED_HOSTS)
    )
    if not isinstance(payload, dict):
        raise ValueError("Unexpected GitHub releases response format")

    assets = payload.get("assets", [])
    for asset in assets:
        name = str(asset.get("name", ""))
        if name.endswith(".json") and "venue-acronyms-2025-curated" in name:
            return str(asset["browser_download_url"]), name

    raise ValueError("Latest release does not contain venue-acronyms JSON asset")
