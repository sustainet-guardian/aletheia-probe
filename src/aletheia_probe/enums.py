# SPDX-License-Identifier: MIT
"""Enums for the journal assessment tool."""

from enum import Enum


class UpdateStatus(str, Enum):
    """Status values for update operations."""

    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    IN_PROGRESS = "in_progress"
    CURRENT = "current"
    ERROR = "error"


class AssessmentType(str, Enum):
    """Assessment classification types."""

    PREDATORY = "predatory"
    LEGITIMATE = "legitimate"
    SUSPICIOUS = "suspicious"
    UNKNOWN = "unknown"
    QUESTIONABLE = "questionable"
    QUALITY_INDICATOR = "quality_indicator"
    HIJACKED = "hijacked"


class BackendType(str, Enum):
    """Backend types."""

    CURATED = "curated"
    PATTERN_ANALYSIS = "pattern_analysis"
    QUALITY_INDICATOR = "quality_indicator"


class EvidenceType(str, Enum):
    """Types of evidence provided by backends for classification purposes."""

    PREDATORY_LIST = "predatory_list"  # Curated lists of predatory journals
    LEGITIMATE_LIST = "legitimate_list"  # Curated lists of legitimate journals
    HEURISTIC = "heuristic"  # Analysis-based assessment (retraction rates, etc.)


class RiskLevel(str, Enum):
    """Risk levels for retraction watch data."""

    NONE = "none"
    NOTE = "note"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"
