# SPDX-License-Identifier: MIT
"""Archive extraction utilities for ZIP files."""

import asyncio
import zipfile
from pathlib import Path

from ....logging_config import get_detail_logger


detail_logger = get_detail_logger()


class ArchiveExtractor:
    """Extracts ZIP archives."""

    async def extract_zip(self, zip_path: str, temp_dir: str) -> str | None:
        """Extract ZIP file using Python's zipfile module.

        Args:
            zip_path: Path to ZIP file
            temp_dir: Temporary directory for extraction

        Returns:
            Path to extraction directory, or None if extraction failed

        Raises:
            ValueError: If paths are invalid or unsafe
        """
        # Validate and sanitize input paths
        zip_file = Path(zip_path).resolve()
        temp_directory = Path(temp_dir).resolve()

        # Validate ZIP file path
        if not zip_file.exists():
            detail_logger.error(f"ZIP file does not exist: {zip_file}")
            return None

        if not zip_file.is_file():
            detail_logger.error(f"Not a file: {zip_file}")
            return None

        if zip_file.suffix.lower() != ".zip":
            detail_logger.error(f"Invalid file extension (expected .zip): {zip_file}")
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
            # Use Python's zipfile module for extraction
            def _extract_zip() -> None:
                with zipfile.ZipFile(zip_file, "r") as zf:
                    # Security check: Validate all paths before extraction
                    for member in zf.namelist():
                        member_path = (extract_dir / member).resolve()
                        try:
                            member_path.relative_to(extract_dir.resolve())
                        except ValueError:
                            raise ValueError(
                                f"Unsafe path in ZIP: {member} resolves outside extraction directory"
                            ) from None
                    # All paths validated, proceed with extraction
                    zf.extractall(extract_dir)

            await asyncio.to_thread(_extract_zip)
            detail_logger.info("Successfully extracted ZIP archive")
            return str(extract_dir)

        except zipfile.BadZipFile as e:
            detail_logger.error(f"Invalid or corrupted ZIP file: {e}")
            return None
        except ValueError as e:
            detail_logger.error(f"Security violation during ZIP extraction: {e}")
            return None
        except Exception as e:
            detail_logger.error(f"Error extracting ZIP: {e}")
            return None
