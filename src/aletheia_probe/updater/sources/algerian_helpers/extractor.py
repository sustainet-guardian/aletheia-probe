"""RAR file extraction utilities."""

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class RARExtractor:
    """Extracts RAR archives using command line tool."""

    def extract_rar(self, rar_path: str, temp_dir: str) -> str | None:
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
            logger.error(f"RAR file does not exist: {rar_file}")
            return None

        if not rar_file.is_file():
            logger.error(f"Not a file: {rar_file}")
            return None

        if rar_file.suffix.lower() != ".rar":
            logger.error(f"Invalid file extension (expected .rar): {rar_file}")
            return None

        # Validate temp directory
        if not temp_directory.exists():
            logger.error(f"Temp directory does not exist: {temp_directory}")
            return None

        extract_dir = temp_directory / "extracted"
        extract_dir.mkdir(exist_ok=True)

        # Ensure extract_dir is within temp_directory (prevent path traversal)
        try:
            extract_dir.resolve().relative_to(temp_directory.resolve())
        except ValueError:
            logger.error(f"Extract directory is outside temp directory: {extract_dir}")
            return None

        try:
            # Use command line unrar tool with validated absolute paths
            result = subprocess.run(
                ["unrar", "x", str(rar_file), str(extract_dir) + "/"],
                capture_output=True,
                text=True,
                timeout=120,  # 2 minute timeout
            )

            if result.returncode == 0:
                logger.info("Successfully extracted RAR archive")
                return str(extract_dir)
            else:
                logger.error(f"RAR extraction failed: {result.stderr}")
                return None

        except subprocess.TimeoutExpired:
            logger.error("RAR extraction timed out")
            return None
        except FileNotFoundError as e:
            if "unrar" in str(e):
                logger.error(
                    "Error extracting RAR: 'unrar' command not found. "
                    "Please install unrar and try again. "
                    "On Debian/Ubuntu: sudo apt-get install unrar"
                )
            else:
                logger.error(f"Error extracting RAR: {e}")
            return None
        except Exception as e:
            logger.error(f"Error extracting RAR: {e}")
            return None
