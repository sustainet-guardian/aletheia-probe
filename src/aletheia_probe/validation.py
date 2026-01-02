# SPDX-License-Identifier: MIT
"""
Validation utilities for journal and article identifiers.

This module provides validation and normalization functions for:
- ISSN (International Standard Serial Number)
- Email addresses

It handles checksum verification, format validation, and normalization
to canonical formats.
"""

import re


EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


def normalize_issn(issn: str | None) -> str | None:
    """
    Normalize ISSN to canonical format (####-####).

    Args:
        issn: Raw ISSN string in various formats

    Returns:
        Normalized ISSN with hyphen, or None if invalid format

    Examples:
        >>> normalize_issn("12345679")
        '1234-5679'
        >>> normalize_issn("1234-5679")
        '1234-5679'
        >>> normalize_issn("invalid")
        None
    """
    if not issn:
        return None

    # Remove all non-alphanumeric characters
    clean_issn = "".join(c for c in str(issn).upper() if c.isalnum())

    # Check if it's 8 characters and first 7 are digits
    if len(clean_issn) != 8 or not clean_issn[:7].isdigit():
        return None

    # Check last character is digit or X
    if clean_issn[7] not in "0123456789X":
        return None

    # Format as ####-####
    return f"{clean_issn[:4]}-{clean_issn[4:]}"


def validate_issn(issn: str | None) -> bool:
    """
    Validate ISSN format and checksum.

    Args:
        issn: ISSN string to validate

    Returns:
        True if valid ISSN with correct checksum, False otherwise

    Examples:
        >>> validate_issn("0028-0836")  # Nature
        True
        >>> validate_issn("1234-5679")  # Test ISSN
        True
        >>> validate_issn("1234-5678")  # Invalid Checksum
        False
    """
    if not issn or len(issn) != 9:
        return False

    # Normalize first
    normalized = normalize_issn(issn)
    if not normalized:
        return False

    # Verify checksum
    return _verify_issn_checksum(normalized)


def _verify_issn_checksum(issn: str) -> bool:
    """
    Verify ISSN checksum digit.

    The ISSN check digit is calculated using modulus 11 with weights 8-1.
    If the weighted sum of all 8 digits (where X=10) is divisible by 11,
    the ISSN is valid.

    Args:
        issn: ISSN in format ####-####

    Returns:
        True if checksum is valid
    """
    # Remove hyphen
    digits = issn.replace("-", "")

    # Calculate weighted sum
    total = 0
    for i, char in enumerate(digits):
        if char == "X":
            value = 10
        else:
            value = int(char)

        # Weights are 8, 7, 6, 5, 4, 3, 2, 1
        total += value * (8 - i)

    return total % 11 == 0


def validate_email(email: str) -> str:
    """Validate email format.

    Note: This function is designed for use as a Pydantic Field Validator.
    It returns the validated email on success or raises exceptions on failure.

    Args:
        email: Email string to validate

    Returns:
        The validated email string

    Raises:
        TypeError: If email is not a string
        ValueError: If email format is invalid
    """
    if not isinstance(email, str):
        raise TypeError("email must be a string")

    if not EMAIL_PATTERN.match(email):
        raise ValueError("Invalid email format")

    return email
