# SPDX-License-Identifier: MIT
"""Journal Assessment Tool - Automated predatory journal detection."""

from importlib.metadata import PackageNotFoundError, version

# Import main components to ensure they're available
from . import backends as backends
from . import dispatcher as dispatcher


__all__: list[str] = ["backends", "dispatcher", "__version__"]

# Get version from installed package metadata
__version__: str
try:
    __version__ = version("aletheia-probe")
except PackageNotFoundError:
    # Package is not installed, use development fallback
    __version__ = "development"
