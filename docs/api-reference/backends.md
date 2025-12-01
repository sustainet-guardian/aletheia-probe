# Backend API Reference

Reference for developing custom backends and understanding the backend system architecture.

## Overview

The backend system provides an extensible architecture for assessing journals against different data sources. Backends implement a common interface and provide evidence of varying types (curated lists, heuristic analysis, quality indicators).

**Source:** `src/aletheia_probe/backends/base.py`

## Backend Interface

All backends implement the abstract `Backend` class with four required methods:

- **`get_name() -> str`** - Returns unique backend identifier (e.g., "doaj", "bealls")
- **`get_description() -> str`** - Returns human-readable description for CLI help
- **`get_evidence_type() -> EvidenceType`** - Returns evidence type (PREDATORY_LIST, LEGITIMATE_LIST, HEURISTIC, QUALITY_INDICATOR)
- **`async query(query_input: QueryInput) -> BackendResult`** - Performs assessment, must be async, always returns BackendResult, never raises

See `src/aletheia_probe/models.py` for QueryInput and BackendResult structures.

## Base Classes

### Backend

Abstract base class providing core functionality including timeout handling and cache TTL configuration.

### CachedBackend

For backends using local cached data (e.g., Beall's List, predatory journal databases).

**Concept:** Searches local cache database by ISSN (confidence 0.95) or exact name match (confidence 0.90). Inherits from Backend.

**Constructor:** Takes `source_name` (cache DB identifier), `list_type` (PREDATORY/LEGITIMATE), `cache_ttl_hours`.

**Reference:** `src/aletheia_probe/backends/bealls.py`

### HybridBackend

For backends that check cache first, then query live API.

**Concept:** Automatic cache lookup with key generation. On cache hit, returns cached result. On miss, calls subclass's `_query_api()`, then caches successful results.

**Implementation:** Inherit and implement `async _query_api(query_input) -> BackendResult`.

**Reference:** `src/aletheia_probe/backends/doaj.py`

## Backend Registry

The `BackendRegistry` manages backend discovery and instantiation using a factory pattern.

**Concept:** Factory functions create backend instances with configuration. Registry filters config parameters based on factory signature, ignoring unsupported parameters.

**Registration:** Call `get_backend_registry().register_factory(name, factory_func, default_config)` at module level.

**Methods:** `create_backend(name, **config)`, `get_backend(name)`, `get_all_backends()`, `get_backend_names()`, `get_supported_params(name)`

## Creating Custom Backends

### Process

1. **Choose base class:** Backend (custom), CachedBackend (local data), HybridBackend (API with caching)
2. **Implement interface:** Four required methods
3. **Register:** Factory function with `get_backend_registry().register_factory()`
4. **Import:** Add to `src/aletheia_probe/backends/__init__.py`
5. **Configure:** Add YAML config in `.aletheia-probe/config.yaml`

### Configuration

YAML structure:
- `backends.[name].enabled` - Enable/disable
- `backends.[name].weight` - Assessment weight (≥ 0.0)
- `backends.[name].timeout` - Query timeout
- `backends.[name].config.*` - Backend-specific parameters

## Best Practices

**Error handling:** Never raise from `query()`. Return BackendResult with BackendStatus.ERROR.

**Confidence scores:**
- 0.95+ = ISSN match with authoritative source
- 0.85-0.95 = Exact name match with reputable source
- 0.70-0.85 = Strong heuristic indicators
- 0.50-0.70 = Moderate indicators
- 0.30-0.50 = Weak indicators
- 0.0 = Not found

**Caching:** Use HybridBackend for APIs. Set TTL based on data volatility (static: 168h, dynamic: 24-48h).

**Logging:** Use dual-logger system - `get_status_logger()` for user messages, `get_detail_logger()` for debug. See `dev-notes/LOGGING_USAGE.md`.

**Testing:** Cover FOUND, NOT_FOUND, ERROR, TIMEOUT statuses. Test ISSN, name, and alias searches. See `tests/unit/backends/`.

## Reference Implementations

- **Simple CachedBackend:** `src/aletheia_probe/backends/bealls.py`
- **HybridBackend with API:** `src/aletheia_probe/backends/doaj.py`
- **Complex patterns:** `src/aletheia_probe/backends/kscien_publishers.py`

## Related Documentation

- [Data Models Reference](models.md) - Model specifications
- [Extending Guide](extending-guide.md) - Extension patterns
- [Configuration Reference](../configuration.md) - Backend configuration
- [Coding Standards](../../dev-notes/CODING_STANDARDS.md) - Code quality requirements
