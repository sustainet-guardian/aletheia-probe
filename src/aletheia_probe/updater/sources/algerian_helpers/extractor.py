# SPDX-License-Identifier: MIT
"""RAR file extraction utilities."""

import asyncio
import subprocess
from pathlib import Path

from ....config import get_config_manager
from ....logging_config import get_detail_logger, get_status_logger


detail_logger = get_detail_logger()
status_logger = get_status_logger()


class RARExtractor:
    """Extracts RAR archives using command line tool."""

    def __init__(self) -> None:
        """Initialize the RARExtractor with configuration."""
        config = get_config_manager().load_config()
        self.extraction_timeout = config.data_source_processing.rar_extraction_timeout

    async def extract_rar(self, rar_path: str, temp_dir: str) -> str | None:
        """Extract RAR file using command line tool.

        Args:
            rar_path: Path to RAR file
            temp_dir: Temporary directory for extraction

        Returns:
            Path to extraction directory, or None if extraction failed

        Raises:
            ValueError: If paths are invalid or unsafe
        """
        # Validate and sanitize input paths
        rar_file = Path(rar_path).resolve()
        temp_directory = Path(temp_dir).resolve()

        # Validate RAR file path
        if not rar_file.exists():
            detail_logger.error(f"RAR file does not exist: {rar_file}")
            return None

        if not rar_file.is_file():
            detail_logger.error(f"Not a file: {rar_file}")
            return None

        if rar_file.suffix.lower() != ".rar":
            detail_logger.error(f"Invalid file extension (expected .rar): {rar_file}")
            return None

        # Validate temp directory
        if not temp_directory.exists():
            detail_logger.error(f"Temp directory does not exist: {temp_directory}")
            return None

        extract_dir = temp_directory / "extracted"
        extract_dir.mkdir(exist_ok=True)

        # Ensure extract_dir is within temp_directory (prevent path traversal)
        try:
            extract_dir.resolve().relative_to(temp_directory.resolve())
        except ValueError:
            detail_logger.error(
                f"Extract directory is outside temp directory: {extract_dir}"
            )
            return None

        try:
            # Use command line unrar tool with validated absolute paths
            def _run_unrar() -> subprocess.CompletedProcess[str]:
                return subprocess.run(
                    ["unrar", "x", str(rar_file), str(extract_dir) + "/"],
                    capture_output=True,
                    text=True,
                    timeout=self.extraction_timeout,
                )

            result = await asyncio.to_thread(_run_unrar)

            if result.returncode == 0:
                detail_logger.info("Successfully extracted RAR archive")
                return str(extract_dir)
            else:
                detail_logger.error(f"RAR extraction failed: {result.stderr}")
                return None

        except subprocess.TimeoutExpired:
            detail_logger.error("RAR extraction timed out")
            return None
        except FileNotFoundError as e:
            if "unrar" in str(e):
                status_logger.error(
                    "Error extracting RAR: 'unrar' command not found. "
                    "Please install unrar and try again. "
                    "On Debian/Ubuntu: sudo apt-get install unrar"
                )
            else:
                detail_logger.error(f"Error extracting RAR: {e}")
            return None
        except Exception as e:
            detail_logger.error(f"Error extracting RAR: {e}")
            return None
