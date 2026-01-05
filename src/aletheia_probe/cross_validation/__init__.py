# SPDX-License-Identifier: MIT
"""Cross-validation framework for backend result validation."""

from .registry import CrossValidationRegistry
from .validators import OpenAlexCrossRefValidator


__all__ = ["CrossValidationRegistry", "OpenAlexCrossRefValidator"]
