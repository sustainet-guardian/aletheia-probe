# Extension and Customization Guide

Guide for extending Aletheia-Probe with custom backends and integrations.

## Overview

Aletheia-Probe uses a plugin-based backend system. Extend by implementing the `Backend` interface and registering with `BackendRegistry`.

**Core concepts:**
- **Backend Interface**: Four required methods (get_name, get_description, get_evidence_type, query)
- **Base Classes**: CachedBackend (local data), HybridBackend (API with caching), Backend (custom)
- **Registry Pattern**: Factory-based registration with config filtering

## Quick Start

1. **Choose base class:** CachedBackend (local DB/files), HybridBackend (external APIs), Backend (custom)
2. **Implement interface:** See `src/aletheia_probe/backends/bealls.py` or `src/aletheia_probe/backends/doaj.py`
3. **Register:** `get_backend_registry().register_factory(name, factory_func, default_config)`
4. **Import:** Add to `src/aletheia_probe/backends/__init__.py`
5. **Configure:** YAML config with enabled, weight, timeout, and backend-specific params

## Extension Patterns

**Institutional database:** Extend CachedBackend, override query() for custom DB.

**REST API:** Extend HybridBackend, implement `_query_api()`.

**File-based:** Extend CachedBackend, load data in `__init__`, use in query().

**Heuristic analysis:** Implement pattern-based analysis (publication volume, acceptance rates, review times). Return EvidenceType.HEURISTIC.

**Multi-source:** Query multiple sources in query(), combine with custom logic.

**Conference-specific:** Check `query_input.venue_type`, return appropriate result. Use EvidenceType.QUALITY_INDICATOR for rankings.

## Best Practices

**Error handling:** Never raise from query(). Return BackendResult with BackendStatus.ERROR.

**Confidence scores:** 0.95+ (ISSN match), 0.85-0.95 (exact name), 0.70-0.85 (strong indicators), lower for weaker signals.

**Caching:** Use HybridBackend for APIs. Set TTL by data volatility (static: 168h, dynamic: 24-48h).

**Logging:** Dual-logger system - `get_status_logger()` for users, `get_detail_logger()` for debug.

**Testing:** Cover FOUND, NOT_FOUND, ERROR, TIMEOUT. Test ISSN, name, alias searches.

## Configuration Patterns

**Environment-specific:** Different configs for dev/prod (API URLs, timeouts).

**Weighted assessment:** Higher weights for trusted sources (institutional: 2.0, curated: 1.5, heuristics: 0.7).

**Security:** Environment variables for API keys, never hardcode credentials.

## Reference

- [Backend API](backends.md) - Interface details
- [Data Models](models.md) - Model specs
- [Configuration](../configuration.md) - Config reference
- [Examples](../../src/aletheia_probe/backends/) - bealls.py, doaj.py
