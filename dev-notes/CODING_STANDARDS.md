# Coding Standards and Style Guide

**Project:** Journal Assessment Tool
**Last Updated:** 2025-11-17
**Status:** Active Development Guidelines

This document outlines project-specific coding standards and patterns for the Journal Assessment Tool. For general Python style and best practices, we follow established community standards.

---

## Foundation: Standard Python Guidelines

This project adheres to the following Python Enhancement Proposals (PEPs) and community standards:

- **[PEP 8](https://peps.python.org/pep-0008/)** - Style Guide for Python Code
- **[PEP 257](https://peps.python.org/pep-0257/)** - Docstring Conventions
- **[PEP 484](https://peps.python.org/pep-0484/)** - Type Hints
- **[PEP 526](https://peps.python.org/pep-0526/)** - Syntax for Variable Annotations
- **[PEP 585](https://peps.python.org/pep-0585/)** - Type Hinting Generics in Standard Collections
- **[Google Python Style Guide](https://google.github.io/styleguide/pyguide.html)** - For docstring formatting

---

## Table of Contents

0. [Core Principle: Simplicity First](#core-principle-simplicity-first)
1. [Python Version and Tools](#python-version-and-tools)
2. [Project-Specific Conventions](#project-specific-conventions)
3. [Domain-Specific Patterns](#domain-specific-patterns)
4. [Security Practices](#security-practices)
5. [Database Operations](#database-operations)
6. [Testing Standards](#testing-standards)

---

## Core Principle: Simplicity First

**MANDATORY**: Simple solutions are ALWAYS preferred over complex ones.

- Choose the most straightforward implementation that solves the problem
- Avoid over-engineering or premature optimization
- Only add complexity when absolutely necessary and well-justified
- Refactor complex code to be simpler when possible
- If a simple solution works, use it

**Example:**
```python
# GOOD - Simple and clear
def is_empty(text: str) -> bool:
    return not text.strip()

# BAD - Unnecessarily complex (unless you need regex for specific validation)
def is_empty(text: str) -> bool:
    import re
    return bool(re.match(r"^\s*$", text))
```

---

## Python Version and Tools

### Target Environment
- **Python Version:** 3.11+
- **Use modern Python features:** Union types (`str | None`), match statements, structural pattern matching

### Code Quality Tools
- **Black** (default settings, 88 character line length) - Automatic code formatting
- **isort** (with Black profile) - Import sorting
- **mypy** - Static type checking
- **ruff** - Fast Python linting (replaces flake8, pylint)
- **pytest** - Testing framework

---

## Project-Specific Conventions

### Import Organization
All imports must be at the top of the file (per PEP 8). Do not place imports inside functions or methods unless required to avoid circular dependencies (document with comment if needed).

### String Formatting: f-strings Only
**All string formatting must use f-strings.** Do not use `.format()` or `%` formatting.

```python
# Good: f-strings for all cases
detail_logger.info(f"Processing {journal_name} with confidence {confidence:.2f}")
url = f"{self.base_url}/{quote(search_query, safe='')}"

# Multi-line f-strings
error_message = (
    f"Failed to process journal '{journal_name}' "
    f"from source '{source}': {error}"
)

# Bad: Do not use
"Found {} journals".format(count)  # NO
"Found %d journals" % count        # NO
```

### Type Annotations: Required for All Public APIs
All public functions, methods, and class attributes must have complete type annotations using modern Python 3.10+ syntax.

```python
# Good: Modern union syntax and complete annotations
def search_journals(
    self,
    normalized_name: str | None = None,
    issn: str | None = None,
    source_name: str | None = None,
) -> list[dict[str, Any]]:
    """Search for journals with optional filters."""
    pass

# Use built-in generics (PEP 585)
def process_result(data: dict[str, Any] | None) -> AssessmentResult | None:
    pass
```

### Enum Usage: No Magic Strings
Define enums for all constant values. Use string enums that inherit from both `str` and `Enum` for JSON serialization compatibility.

```python
from enum import Enum

class AssessmentType(str, Enum):
    """Assessment classification types."""
    PREDATORY = "predatory"
    LEGITIMATE = "legitimate"
    UNKNOWN = "unknown"
    QUESTIONABLE = "questionable"

# Good: Use enums
if assessment.assessment == AssessmentType.PREDATORY:
    result.predatory_count += 1

# Bad: Magic strings
# if assessment.assessment == "predatory":  # NO
```

---

## Domain-Specific Patterns

### Custom Exceptions
Define domain-specific exceptions for better error handling and API clarity.

```python
class RateLimitError(Exception):
    """Raised when API rate limit is exceeded."""

    def __init__(self, retry_after: int | None = None) -> None:
        self.retry_after = retry_after
        super().__init__(f"API rate limit hit. Retry after {retry_after}s")

class ValidationError(ValueError):
    """Raised when input validation fails."""
    pass
```

### Async Retry Pattern
Use the project's `@async_retry_with_backoff` decorator for network operations.

```python
@async_retry_with_backoff(
    max_retries=3,
    initial_delay=1.0,
    max_delay=30.0,
    exceptions=(RateLimitError, aiohttp.ClientError),
)
async def fetch_from_api(self, endpoint: str) -> dict[str, Any]:
    """Fetch data from API with automatic retry on transient failures."""
    async with aiohttp.ClientSession() as session:
        async with session.get(endpoint, timeout=30) as response:
            if response.status == 429:
                retry_after = int(response.headers.get("Retry-After", 60))
                raise RateLimitError(retry_after=retry_after)
            response.raise_for_status()
            return await response.json()
```

### Concurrent Assessment Pattern
Use `asyncio.gather()` for parallel journal assessments.

```python
async def assess_multiple_journals(
    self, queries: list[QueryInput]
) -> list[AssessmentResult]:
    """Assess multiple journals concurrently."""
    tasks = [self.assess_journal(query) for query in queries]
    return await asyncio.gather(*tasks, return_exceptions=False)
```

### Configuration Management
Use Pydantic models for all configuration structures.

```python
from pydantic import BaseModel, Field

class DataSourceUrlConfig(BaseModel):
    """Configuration for external data source URLs."""

    algerian_ministry_base_url: str = Field(
        "https://dgrsdt.dz/storage/revus/",
        description="Base URL for Algerian Ministry data"
    )
    doaj_api_base_url: str = Field(
        "https://doaj.org/api/search/journals",
        description="DOAJ API endpoint for journal search"
    )
```

### Logging Pattern: Dual-Logger System
This project uses a dual-logger system with separate loggers for technical details and user-facing messages.

See **[LOGGING_USAGE.md](LOGGING_USAGE.md)** for complete documentation on:
- Detail logger vs. status logger
- When to use each logger
- Usage examples and best practices

---

## Security Practices

### SSL Certificate Validation
Always use proper SSL certificate validation. Document any fallback behavior with security implications.

```python
def _create_ssl_context(self) -> ssl.SSLContext | bool:
    """Create SSL context for secure downloads with fallback."""
    try:
        if CERTIFI_AVAILABLE:
            ssl_context = ssl.create_default_context(cafile=certifi.where())
            logger.debug("Using SSL context with certificate validation")
            return ssl_context
    except Exception as e:
        logger.warning(f"Failed to create SSL context: {e}")

    # Fallback with documented security implications
    logger.warning(
        "Using disabled SSL verification. "
        "Security impact: MITM attacks possible but risk is low for public data. "
        "Data integrity will be validated after download."
    )
    return False
```

### Input Validation and Path Traversal Prevention
Always validate and sanitize user inputs. Prevent path traversal attacks in file operations.

```python
def safe_extract_rar(self, rar_path: Path, extract_dir: Path) -> Path | None:
    """Safely extract RAR archive with security validation."""
    # Validate and resolve paths
    rar_file = rar_path.resolve()
    temp_directory = extract_dir.resolve()

    # Security validations
    if not rar_file.exists() or not rar_file.is_file():
        raise ValueError(f"Invalid RAR file: {rar_file}")

    if rar_file.suffix.lower() != ".rar":
        raise ValueError(f"Invalid file extension: {rar_file}")

    # Prevent path traversal attacks
    try:
        extract_path = temp_directory / "extracted"
        extract_path.resolve().relative_to(temp_directory.resolve())
    except ValueError:
        raise ValueError("Extract directory is outside temp directory")

    return extract_path
```

---

## Database Operations

### SQLite Parameter Validation
Always use parameterized queries and validate inputs before database operations.

```python
def add_journal_entry(
    self,
    journal_name: str,
    issn: str | None = None,
    source: str = "unknown",
    **kwargs: Any,
) -> None:
    """Add journal entry with input validation."""
    # Validate required fields
    if not journal_name or not journal_name.strip():
        raise ValueError("Journal name is required and cannot be empty")

    # Validate string lengths to prevent database errors
    if len(journal_name) > 500:
        raise ValueError("Journal name exceeds maximum length (500 characters)")

    # Use parameterized queries to prevent SQL injection
    with sqlite3.connect(self.db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO journals
            (journal_name, issn, source, last_updated)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (journal_name.strip(), issn, source.strip()),
        )
```

### Query Optimization: Batch Operations
Avoid N+1 query problems by batching database operations.

```python
def get_journals_with_urls(self, journal_ids: list[int]) -> dict[int, list[str]]:
    """Fetch URLs for multiple journals efficiently in a single query."""
    if not journal_ids:
        return {}

    # Use parameterized placeholders for safe dynamic queries
    placeholders = ",".join("?" * len(journal_ids))
    with sqlite3.connect(self.db_path) as conn:
        cursor = conn.execute(
            f"""
            SELECT journal_id, url FROM journal_urls
            WHERE journal_id IN ({placeholders}) AND is_active = TRUE
            ORDER BY journal_id, priority
            """,
            journal_ids,
        )

        # Group results by journal_id
        urls_by_journal: dict[int, list[str]] = {}
        for journal_id, url in cursor.fetchall():
            urls_by_journal.setdefault(journal_id, []).append(url)

        return urls_by_journal
```

---

## Testing Standards

### Test Naming Convention
Use descriptive test names that explain what is being tested and the expected outcome.

```python
# Good: Descriptive test function names
def test_assess_journal_returns_predatory_for_known_predatory_journal():
    """Test that known predatory journals are correctly identified."""
    pass

def test_doaj_backend_handles_rate_limit_with_retry():
    """Test DOAJ backend properly retries on rate limit."""
    pass

async def test_batch_assessor_processes_large_bibtex_file():
    """Test batch processing of large BibTeX files."""
    pass
```

### Test Organization with Fixtures
Organize tests into classes and use pytest fixtures for test data.

```python
class TestJournalAssessment:
    """Test suite for journal assessment functionality."""

    @pytest.fixture
    def sample_query(self) -> QueryInput:
        """Provide sample query input for testing."""
        return QueryInput(
            raw_input="Nature",
            normalized_name="nature",
            identifiers={"issn": "0028-0836"}
        )

    async def test_legitimate_journal_assessment(self, sample_query):
        """Test assessment of legitimate journal."""
        result = await assess_journal(sample_query)
        assert result.assessment == AssessmentType.LEGITIMATE
        assert result.confidence > 0.8
```

---

## Code Smells and Anti-Patterns to Avoid

### Common Code Smells

Do NOT introduce these code quality issues:

- **Code Duplication** - Extract common code into reusable functions or classes
- **Magic Numbers/Strings** - Use named constants or enums (see Project-Specific Conventions above)
- **Long Functions** - Break down functions longer than 50 LOC (lines of code) into smaller, focused functions. LOC counts only executable code and declarations - comments, docstrings, and empty lines do not count.
- **Deep Nesting** - Use guard clauses and early returns to flatten conditionals
- **Mutable Default Arguments** - Use `None` as default and initialize inside the function
- **Bare Exceptions** - Catch specific exception types instead of generic `except:`
- **God Objects** - Keep classes focused and cohesive with single responsibility

### Development Practices to Avoid

- **Skipping Quality Checks** - Always run quality checks before committing (see `scripts/run-quality-checks.sh`)
- **Modifying Unknown Code** - Don't make changes in areas you don't fully understand
- **Adding Unnecessary Dependencies** - Use standard library when possible; justify new dependencies
- **Backwards-Compatibility Hacks** - Delete unused code cleanly; avoid underscore prefixes or commented-out code
- **Using `type: ignore` Without Justification** - Fix type issues properly or provide clear reasoning

**When uncertain about any change, ask for clarification before proceeding.**

---

## Summary

This coding standards document references established Python best practices (PEPs and community guidelines) and defines project-specific conventions for:

- **Simplicity First**: Prefer simple solutions over complex ones
- **String Formatting**: Exclusive use of f-strings
- **Type Safety**: Comprehensive type hints with modern syntax
- **Domain Patterns**: Custom exceptions, retry decorators, async patterns
- **Security**: Input validation, SQL injection prevention, path traversal protection
- **Database**: Parameterized queries and batch operations
- **Testing**: Descriptive naming and fixture organization
- **Quality**: Automated tooling (Black, isort, mypy, ruff, pytest)
- **Code Quality**: Avoid code smells and anti-patterns

All new code must follow these guidelines. When modifying existing code, bring it up to these standards where practical.
