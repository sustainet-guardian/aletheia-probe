#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Quick connectivity check for CORE portal using urllib first, then requests."""

from __future__ import annotations

from urllib.request import urlopen

import requests

URLS = [
    "https://portal.core.edu.au/conf-ranks/?search=&by=all&source=ICORE2026&sort=atitle&page=1",
    "https://portal.core.edu.au/jnl-ranks/?search=&by=all&source=CORE2020&sort=atitle&page=1",
    "https://portal.core.edu.au/conf-ranks/?search=&by=all&source=ICORE2026&sort=atitle&page=1&do=Export",
    "https://portal.core.edu.au/jnl-ranks/?search=&by=all&source=CORE2020&sort=atitle&page=1&do=Export",
]


def check_with_urllib(url: str) -> None:
    """Check one URL with urllib."""
    try:
        with urlopen(url, timeout=30) as response:
            content = response.read()
            print(f"urllib  OK  status={response.status} bytes={len(content)} url={url}")
    except Exception as exc:  # nosec B110 - diagnostics script
        print(f"urllib  ERR type={type(exc).__name__} detail={exc!r} url={url}")


def check_with_requests(url: str) -> None:
    """Check one URL with requests."""
    try:
        response = requests.get(url, timeout=30)
        print(f"requests OK  status={response.status_code} bytes={len(response.text)} url={url}")
    except Exception as exc:  # nosec B110 - diagnostics script
        print(f"requests ERR type={type(exc).__name__} detail={exc!r} url={url}")


def main() -> None:
    print(f"requests version: {requests.__version__}")
    for url in URLS:
        check_with_urllib(url)
        check_with_requests(url)


if __name__ == "__main__":
    main()
