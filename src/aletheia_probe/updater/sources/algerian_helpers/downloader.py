# SPDX-License-Identifier: MIT
"""RAR file downloading for Algerian Ministry data."""

import asyncio
import ssl
from datetime import datetime
from pathlib import Path

from aiohttp import ClientError, ClientResponse, ClientSession, ServerTimeoutError

from aletheia_probe.config import get_config_manager
from aletheia_probe.logging_config import get_detail_logger, get_status_logger
from aletheia_probe.retry_utils import async_retry_with_backoff


detail_logger = get_detail_logger()
status_logger = get_status_logger()


class RARDownloader:
    """Downloads RAR files from Algerian Ministry website."""

    def __init__(self) -> None:
        """Initialize the RARDownloader with configuration."""
        config = get_config_manager().load_config()
        self.chunk_size = config.data_source_processing.download_chunk_size

    def _create_ssl_context(self) -> ssl.SSLContext | bool:
        """Create SSL context for secure downloads.

        Returns:
            SSL context if available, False if SSL must be disabled

        Security Note:
            This method attempts to create a secure SSL context with certificate
            validation. If SSL context creation fails, the method returns False,
            which signals the download method to fall back to disabled SSL
            verification. This fallback is a deliberate design decision with
            security implications (see download_rar method for details).
        """
        try:
            # Create SSL context with proper certificate validation
            ssl_context = ssl.create_default_context()
            detail_logger.debug("Using SSL context with certificate validation")
            return ssl_context
        except Exception as e:
            status_logger.warning(f"Failed to create SSL context: {e}")
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
                # SECURITY WARNING: SSL Verification Fallback
                # ============================================
                # This fallback disables SSL certificate verification, which opens
                # the door to man-in-the-middle (MITM) attacks. This is a deliberate
                # design decision based on the following considerations:
                #
                # WHY THIS FALLBACK EXISTS:
                # 1. The Algerian Ministry website may have certificate configuration
                #    issues that prevent proper SSL validation
                # 2. The data being downloaded is public academic journal listings,
                #    not sensitive personal or authentication data
                # 3. Complete failure to download would prevent assessment of journals
                #    from this geographic region
                #
                # SECURITY IMPLICATIONS:
                # - Potential MITM attack: An attacker could intercept the connection
                #   and substitute malicious data for the authentic journal list
                # - Data integrity risk: Downloaded data could be tampered with during
                #   transmission without detection
                # - Impact: Compromised data could lead to incorrect journal assessments
                #   (marking legitimate journals as predatory or vice versa)
                #
                # RISK MITIGATION:
                # - This is public, non-sensitive data (journal listings)
                # - Data is validated after download (RAR extraction, JSON parsing)
                # - Tampering would be detectable through data format validation
                # - The impact is limited to journal assessment accuracy, not system
                #   security or personal data exposure
                #
                # ALTERNATIVES CONSIDERED:
                # - Certificate pinning: Too brittle for government websites that may
                #   change certificates
                # - Fail completely: Would prevent assessment of Algerian journals
                # - User confirmation: Not practical for automated sync operations
                #
                # ACCEPTABLE USE:
                # This fallback is acceptable because:
                # 1. The data is public and non-sensitive
                # 2. The risk is limited to journal assessment accuracy
                # 3. The alternative (no data) is worse for the tool's purpose
                # 4. Users are warned about the SSL bypass in logs
                #
                # FUTURE IMPROVEMENTS:
                # - Consider adding a configuration option to disable this fallback
                # - Implement additional data integrity checks (checksums, signatures)
                # - Monitor for certificate issues and report to data source maintainers

                detail_logger.warning(
                    f"Algerian downloader: SSL verification failed: {ssl_error}, "
                    "falling back to disabled SSL verification"
                )
                status_logger.warning(
                    "    algerian_ministry: SSL verification failed - "
                    "SECURITY WARNING: Proceeding without SSL verification. "
                    "Connection is vulnerable to MITM attacks."
                )

                # Check if file exists without SSL first
                async with session.head(url, ssl=False, timeout=10) as head_response:
                    if head_response.status == 404:
                        detail_logger.info(
                            f"Algerian downloader: File not found (404) at {url} (no SSL)"
                        )
                        return None

                # Download without SSL verification (security risk documented above)
                detail_logger.warning(
                    "Algerian downloader: Downloading without SSL verification - "
                    "connection is not secure and vulnerable to MITM attacks"
                )
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
                async for chunk in response.content.iter_chunked(self.chunk_size):
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
