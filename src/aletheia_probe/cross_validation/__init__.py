# SPDX-License-Identifier: MIT
"""Cross-validation framework for backend result validation."""

from .protocols import CrossValidationCapable
from .registry import CrossValidationRegistry, get_cross_validation_registry
from .validators import (
    CrossRefOpenCitationsValidator,
    OpenAlexCrossRefValidator,
    OpenAlexOpenCitationsValidator,
)


__all__ = [
    "CrossValidationCapable",
    "CrossValidationRegistry",
    "get_cross_validation_registry",
    "OpenAlexCrossRefValidator",
    "OpenAlexOpenCitationsValidator",
    "CrossRefOpenCitationsValidator",
]
