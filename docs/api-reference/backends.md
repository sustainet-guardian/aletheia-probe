# Backend API Reference

Reference for developing custom backends and understanding the backend system architecture.

## Overview

The backend system provides an extensible architecture for assessing journals against different data sources. Backends implement a common interface and provide evidence of varying types (curated lists, heuristic analysis, quality indicators).

**Source:** `src/aletheia_probe/backends/base.py`

## Backend Interface

All backends implement the abstract `Backend` class with four required methods:

### Required Methods

**`get_name() -> str`**
Returns unique backend identifier (e.g., "doaj", "bealls").

**`get_description() -> str`**
Returns human-readable description for CLI help and status output.

**`get_evidence_type() -> EvidenceType`**
Returns evidence type: `PREDATORY_LIST`, `LEGITIMATE_LIST`, `HEURISTIC`, or `QUALITY_INDICATOR`.
See `src/aletheia_probe/enums.py` for definitions.

**`async query(query_input: QueryInput) -> BackendResult`**
Performs assessment query. Must be async, always return `BackendResult`, never raise exceptions.
See `src/aletheia_probe/models.py` for `QueryInput` and `BackendResult` structures.

## Base Classes

### Backend

Abstract base class providing core functionality including timeout handling and cache TTL configuration.

### CachedBackend

For backends using local cached data (e.g., Beall's List, predatory journal databases).

**Features:**
- Automatic ISSN and name-based searching
- Exact match with SQL optimization
- Confidence calculation based on match quality (ISSN: 0.95, exact name: 0.90)
- Integration with cache manager

**Constructor:**
```python
CachedBackend(
    source_name: str,           # Name in cache database
    list_type: AssessmentType,  # PREDATORY or LEGITIMATE
    cache_ttl_hours: int = 24
)
```

**Example:** See `src/aletheia_probe/backends/bealls.py` for simple implementation.

### HybridBackend

For backends that check cache first, then query live API.

**Features:**
- Automatic cache lookup with key generation
- Result caching after successful API queries
- Cache hit/miss tracking

**Implementation:**
- Inherit from `HybridBackend`
- Implement `async _query_api(query_input: QueryInput) -> BackendResult`
- Base class handles caching automatically

**Example:** See `src/aletheia_probe/backends/doaj.py` for API-based implementation.

## Backend Registry

The `BackendRegistry` manages backend discovery and instantiation using a factory pattern.

### Registering Backends

```python
from aletheia_probe.backends.base import get_backend_registry

# Simple registration
get_backend_registry().register_factory(
    "my_backend",
    lambda: MyBackend(),
    default_config={}
)

# With configuration parameters
get_backend_registry().register_factory(
    "configured_backend",
    lambda cache_ttl_hours=24, api_key=None: ConfiguredBackend(
        cache_ttl_hours=cache_ttl_hours,
        api_key=api_key
    ),
    default_config={"cache_ttl_hours": 48, "api_key": None}
)
```

**Configuration Filtering:** Registry automatically filters config parameters based on factory signature, ignoring unsupported parameters.

### Registry Methods

- `create_backend(name, **config)` - Create with custom config
- `get_backend(name)` - Get with default config
- `get_all_backends()` - List all registered backends
- `get_backend_names()` - Get backend names
- `get_supported_params(name)` - Get supported config parameters

## Creating Custom Backends

### Step 1: Choose Base Class

- `Backend` - Custom logic from scratch
- `CachedBackend` - Local data sources
- `HybridBackend` - API-based with caching

### Step 2: Implement Interface

```python
from aletheia_probe.backends.base import Backend
from aletheia_probe.enums import AssessmentType, EvidenceType
from aletheia_probe.models import BackendResult, BackendStatus, QueryInput

class CustomBackend(Backend):
    def __init__(self, api_key: str | None = None, cache_ttl_hours: int = 24):
        super().__init__(cache_ttl_hours)
        self.api_key = api_key

    async def query(self, query_input: QueryInput) -> BackendResult:
        # Always return BackendResult, never raise exceptions
        try:
            # Backend logic here
            pass
        except Exception as e:
            return BackendResult(
                backend_name=self.get_name(),
                status=BackendStatus.ERROR,
                confidence=0.0,
                assessment=None,
                error_message=str(e),
                response_time=response_time,
                cached=False
            )

    def get_name(self) -> str:
        return "custom_backend"

    def get_description(self) -> str:
        return "Custom backend description"

    def get_evidence_type(self) -> EvidenceType:
        return EvidenceType.HEURISTIC
```

### Step 3: Register Backend

```python
# At module level
get_backend_registry().register_factory(
    "custom_backend",
    lambda api_key=None, cache_ttl_hours=24: CustomBackend(
        api_key=api_key,
        cache_ttl_hours=cache_ttl_hours
    ),
    default_config={"api_key": None, "cache_ttl_hours": 24}
)
```

### Step 4: Configure

Create `.aletheia-probe/config.yaml`:
```yaml
backends:
  custom_backend:
    enabled: true
    weight: 0.8
    timeout: 10
    config:
      api_key: "your-key"
      cache_ttl_hours: 48
```

### Step 5: Import

Add to `src/aletheia_probe/backends/__init__.py`:
```python
from .custom_backend import CustomBackend
```

## Best Practices

### Error Handling
Never raise exceptions from `query()`. Return `BackendResult` with `BackendStatus.ERROR` and error message.

### Confidence Scores
- **0.95+** - Exact ISSN match with authoritative source
- **0.85-0.95** - Exact name match with reputable source
- **0.70-0.85** - Strong heuristic indicators
- **0.50-0.70** - Moderate indicators
- **0.30-0.50** - Weak indicators
- **0.0** - Not found or no assessment

### Caching Strategy
- Use `HybridBackend` for API-based backends
- Set appropriate TTL based on data freshness:
  - Static lists: 168 hours (7 days)
  - API data: 24-48 hours
  - Quality indicators: 12-24 hours
- Mark results with `cached=True/False` correctly

### Rate Limiting
Handle gracefully by returning `BackendStatus.RATE_LIMITED` when rate limited.

### Logging
Use dual-logger system (see `dev-notes/LOGGING_USAGE.md`):
```python
from aletheia_probe.logging_config import get_detail_logger, get_status_logger

status_logger = get_status_logger()  # User-facing messages
detail_logger = get_detail_logger()  # Debug information
```

### Response Timing
Always track and report response times for monitoring.

## Testing

Write unit tests covering:
- Successful queries (FOUND status)
- Unsuccessful queries (NOT_FOUND status)
- Error handling (ERROR status)
- Timeout behavior (TIMEOUT status)
- ISSN, normalized name, and alias searches
- Confidence calculation
- Cache behavior (for HybridBackend)
- Configuration parameter filtering

See `tests/unit/backends/` for examples.

## Reference Implementations

- **Simple CachedBackend:** `src/aletheia_probe/backends/bealls.py`
- **HybridBackend with API:** `src/aletheia_probe/backends/doaj.py`
- **Complex patterns:** `src/aletheia_probe/backends/kscien_publishers.py`

## Related Documentation

- [Data Models Reference](models.md) - Model specifications
- [Extending Guide](extending-guide.md) - Step-by-step tutorial
- [Configuration Reference](../configuration.md) - Backend configuration
- [Coding Standards](../../dev-notes/CODING_STANDARDS.md) - Code quality requirements
