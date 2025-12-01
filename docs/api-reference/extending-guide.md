# Extension and Customization Guide

Guide for extending Aletheia-Probe with custom backends and integrations.

## Overview

Aletheia-Probe uses a plugin-based backend system. Add custom backends by implementing the `Backend` interface and registering with the `BackendRegistry`.

**Core concepts:**
- **Backend Interface**: Abstract class defining required methods (`get_name`, `get_description`, `get_evidence_type`, `query`)
- **Base Classes**: `CachedBackend` (local data), `HybridBackend` (API with caching), `Backend` (custom logic)
- **Registry Pattern**: Factory-based registration with configuration filtering

## Quick Start

**1. Choose base class:**
- `CachedBackend` - Local databases/files
- `HybridBackend` - External APIs with caching
- `Backend` - Custom implementation

**2. Implement interface:**
See `src/aletheia_probe/backends/bealls.py` (CachedBackend) or `src/aletheia_probe/backends/doaj.py` (HybridBackend) for reference.

**3. Register backend:**
```python
get_backend_registry().register_factory(
    "backend_name",
    lambda config_param=default: BackendClass(config_param),
    default_config={"config_param": default}
)
```

**4. Import in `__init__.py`:**
Add to `src/aletheia_probe/backends/__init__.py`

**5. Configure:**
```yaml
backends:
  backend_name:
    enabled: true
    weight: 0.8
    config:
      config_param: value
```

## Extension Patterns

### Custom Data Source Integration

**Institutional database:** Extend `CachedBackend`, override `query()` to use custom DB connection.

**REST API:** Extend `HybridBackend`, implement `_query_api()` method.

**File-based:** Extend `CachedBackend`, load data in `__init__`, use in `query()`.

### Heuristic Analysis

Implement pattern-based analysis (e.g., publication volume, acceptance rates, review times). Return `EvidenceType.HEURISTIC` from `get_evidence_type()`.

### Multi-Source Aggregation

Query multiple sources in one backend's `query()` method, combine results with custom logic.

### Conference-Specific Assessment

Check `query_input.venue_type` and return appropriate result. Use `EvidenceType.QUALITY_INDICATOR` for ranking-based assessment.

## Best Practices

**Error handling:** Never raise from `query()`. Return `BackendResult` with `BackendStatus.ERROR`.

**Confidence scores:** 0.95+ (ISSN match), 0.85-0.95 (exact name), 0.70-0.85 (strong indicators), lower for weaker signals.

**Caching:** Use `HybridBackend` for APIs. Set TTL based on data volatility (static: 168h, dynamic: 24-48h).

**Logging:** Use dual-logger system (`get_status_logger()` for user messages, `get_detail_logger()` for debug).

**Testing:** Cover FOUND, NOT_FOUND, ERROR, TIMEOUT statuses. Test ISSN, name, and alias searches.

## Configuration Patterns

**Environment-specific:** Use different configs for dev/prod (API URLs, timeouts).

**Weighted assessment:** Higher weights for trusted sources (institutional: 2.0, curated lists: 1.5, heuristics: 0.7).

**Security:** Use environment variables for API keys, never hardcode credentials.

## Reference

- **Backend API:** [backends.md](backends.md)
- **Data Models:** [models.md](models.md)
- **Configuration:** [../configuration.md](../configuration.md)
- **Examples:** `src/aletheia_probe/backends/bealls.py`, `src/aletheia_probe/backends/doaj.py`
