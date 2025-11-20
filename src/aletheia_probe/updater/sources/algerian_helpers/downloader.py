"""RAR file downloading for Algerian Ministry data."""

import asyncio
import logging
import ssl
from datetime import datetime
from pathlib import Path

from aiohttp import ClientError, ClientResponse, ClientSession, ServerTimeoutError

from aletheia_probe.logging_config import get_detail_logger, get_status_logger
from aletheia_probe.retry_utils import async_retry_with_backoff


logger = logging.getLogger(__name__)
detail_logger = get_detail_logger()
status_logger = get_status_logger()


class RARDownloader:
    """Downloads RAR files from Algerian Ministry website."""

    def _create_ssl_context(self) -> ssl.SSLContext | bool:
        """Create SSL context for secure downloads.

        Returns:
            SSL context if available, False if SSL must be disabled
        """
        try:
            # Create SSL context with proper certificate validation
            ssl_context = ssl.create_default_context()
            logger.debug("Using SSL context with certificate validation")
            return ssl_context
        except Exception as e:
            logger.warning(f"Failed to create SSL context: {e}")
            return False

    @async_retry_with_backoff(
        max_retries=3,
        initial_delay=2.0,
        max_delay=30.0,
        exceptions=(
            ClientError,
            ServerTimeoutError,
            asyncio.TimeoutError,
            ConnectionError,
        ),
    )
    async def download_rar(
        self, session: ClientSession, url: str, temp_dir: str
    ) -> str | None:
        """Download RAR file to temporary directory with retry logic.

        Uses exponential backoff for transient failures (network issues, timeouts).

        Args:
            session: HTTP session
            url: URL of the RAR file
            temp_dir: Temporary directory path

        Returns:
            Path to downloaded RAR file, or None if download failed

        Raises:
            ClientError: On persistent HTTP client errors
            ServerTimeoutError: On persistent server timeout errors
            asyncio.TimeoutError: On persistent timeout errors
        """
        rar_path = Path(temp_dir) / f"algerian_{datetime.now().year}.rar"

        try:
            detail_logger.info(f"Algerian downloader: Starting download from {url}")

            # Try with proper SSL context first
            ssl_context = self._create_ssl_context()

            try:
                # First check if file exists with a HEAD request (faster than full download)
                if ssl_context is not False:
                    detail_logger.info(
                        "Algerian downloader: Checking if file exists..."
                    )
                    async with session.head(
                        url, ssl=ssl_context, timeout=10
                    ) as head_response:
                        if head_response.status == 404:
                            detail_logger.info(
                                f"Algerian downloader: File not found (404) at {url}"
                            )
                            return None

                    # File exists, proceed with download (longer timeout for large files)
                    detail_logger.info(
                        "Algerian downloader: File exists, starting download with SSL verification"
                    )
                    async with session.get(
                        url,
                        ssl=ssl_context,
                        timeout=300,  # 5 minutes for large files
                    ) as response:
                        detail_logger.info(
                            f"Algerian downloader: Got response {response.status}"
                        )
                        return await self._process_download_response(
                            response, rar_path, url
                        )
                else:
                    raise ssl.SSLError("SSL context creation failed")

            except (ssl.SSLError, ClientError) as ssl_error:
                # Fall back to disabled SSL with enhanced monitoring
                detail_logger.warning(
                    f"Algerian downloader: SSL verification failed: {ssl_error}, falling back to disabled SSL"
                )
                status_logger.info(
                    "    algerian_ministry: SSL verification failed, retrying without SSL..."
                )

                # Check if file exists without SSL first
                async with session.head(url, ssl=False, timeout=10) as head_response:
                    if head_response.status == 404:
                        detail_logger.info(
                            f"Algerian downloader: File not found (404) at {url} (no SSL)"
                        )
                        return None

                async with session.get(
                    url, ssl=False, timeout=300
                ) as response:  # 5 minutes for large files
                    detail_logger.info(
                        f"Algerian downloader: Got response {response.status} (no SSL)"
                    )
                    return await self._process_download_response(
                        response, rar_path, url
                    )

        except (ClientError, ServerTimeoutError, asyncio.TimeoutError) as e:
            detail_logger.warning(
                f"Algerian downloader: Retryable error downloading RAR from {url}: {e}"
            )
            status_logger.info(
                f"    algerian_ministry: Download error (will retry): {type(e).__name__}"
            )
            raise  # Let retry decorator handle it
        except Exception as e:
            detail_logger.error(
                f"Algerian downloader: Non-retryable error downloading RAR from {url}: {e}"
            )
            status_logger.warning(f"    algerian_ministry: Download failed: {e}")
            return None

    async def _process_download_response(
        self, response: ClientResponse, rar_path: Path, url: str
    ) -> str | None:
        """Process HTTP response and download file content.

        Args:
            response: aiohttp response object
            rar_path: Path where to save the downloaded file
            url: Source URL for logging

        Returns:
            Path to downloaded file or None if failed
        """
        response.raise_for_status()  # Raise for 4xx/5xx status codes

        if response.status == 200:
            detail_logger.info(
                f"Algerian downloader: Starting file write to {rar_path}"
            )
            content_length = response.headers.get("content-length")
            if content_length:
                detail_logger.info(
                    f"Algerian downloader: File size: {content_length} bytes"
                )

            bytes_written = 0
            last_log_mb = 0
            with open(rar_path, "wb") as f:
                async for chunk in response.content.iter_chunked(8192):
                    f.write(chunk)
                    bytes_written += len(chunk)
                    current_mb = bytes_written // (1024 * 1024)
                    if current_mb > last_log_mb:  # Log each MB
                        detail_logger.info(
                            f"Algerian downloader: Downloaded {current_mb} MB"
                        )
                        status_logger.info(
                            f"    algerian_ministry: Downloaded {current_mb} MB..."
                        )
                        last_log_mb = current_mb

            detail_logger.info(
                f"Algerian downloader: Successfully downloaded {bytes_written} bytes to {rar_path}"
            )
            status_logger.info(
                f"    algerian_ministry: Downloaded RAR file ({bytes_written // (1024 * 1024)} MB)"
            )
            return str(rar_path)
        else:
            detail_logger.warning(
                f"Algerian downloader: Failed to download RAR: HTTP {response.status}"
            )
            return None
