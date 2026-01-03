# Backend and Data Synchronization Architecture

**Project:** Aletheia-Probe - Journal Assessment Tool
**Last Updated:** 2026-01-03
**Status:** Active Architecture Guide

This document describes the backend architecture and data synchronization design implemented in the project.

---

## Architecture Overview

The system uses a **protocol-based architecture** with a single registry pattern for managing data source backends and their synchronization.

### Core Components

1. **BackendRegistry** (`backends/base.py`)
   - Single factory-based registry for all backends
   - Manages backend instantiation and configuration
   - Provides discovery and lifecycle management

2. **DataSyncCapable Protocol** (`backends/base.py`)
   - Runtime-checkable protocol for backends that sync with external data
   - Enables duck-typed backend discovery without inheritance constraints
   - Method: `get_data_source() -> DataSource | None`

3. **Standalone Sync Utility** (`updater/sync_utils.py`)
   - `update_source_data()` function handles data synchronization
   - No singleton or global state
   - Clean separation from backend management

4. **DataSource ABC** (`updater/core.py`)
   - Abstract base class for data sources
   - Defines interface: `fetch_data()`, `should_update()`, `get_name()`, etc.
   - Independent of backend implementations

---

## Key Design Decisions

### 1. Protocol Over Inheritance
Backends implement `DataSyncCapable` protocol rather than inheriting from a sync-specific base class. This allows:
- Flexible composition without tight coupling
- Easy testing with mock objects
- Runtime checking via `isinstance(backend, DataSyncCapable)`

### 2. Single Registry Pattern
Using `BackendRegistry` exclusively:
- Backends are the source of truth for their data sources
- No separate registration for update vs. query operations
- Clearer ownership and lifecycle management

### 3. Standalone Functions Over Singletons
Standalone `update_source_data()` function:
- No global state
- Easy testing and dependency injection
- Explicit dependencies (db_writer, source) passed as arguments

### 4. Lazy Data Source Creation
Backends create their `DataSource` instances on-demand via `get_data_source()`:
- Avoids circular import issues
- Reduces initialization overhead
- Allows backends to exist without data sources (e.g., API-only backends)

---

## Benefits

### Code Quality
- **~350 lines removed from old singleton implementation**: Eliminated redundant registry and singleton code
- **No global state**: All dependencies explicitly passed
- **Better testability**: Functions easier to test than singletons
- **Clearer boundaries**: Backend logic separated from sync logic

### Architecture
- **Single source of truth**: BackendRegistry manages all backend concerns
- **Flexible design**: Protocols allow duck typing without inheritance constraints
- **Scalability**: Easy to add new backends or data sources
- **No circular dependencies**: TYPE_CHECKING and lazy initialization patterns

### Maintainability
- **Simpler mental model**: One registry, clear data flow
- **Explicit dependencies**: No hidden global state or magic imports
- **Standard patterns**: Factory pattern, protocol-based design
- **Easy to extend**: New backends just implement DataSyncCapable if they need sync

---

## Usage Patterns

### Adding a New Backend with Data Sync

```python
from aletheia_probe.backends.base import CachedBackend
from aletheia_probe.enums import AssessmentType

class MyBackend(CachedBackend):
    def __init__(self):
        super().__init__(source_name="my_source", list_type=AssessmentType.PREDATORY)
        self._data_source = None

    def get_data_source(self):
        """Implement DataSyncCapable protocol."""
        if self._data_source is None:
            from ..updater.sources.my_source import MyDataSource
            self._data_source = MyDataSource()
        return self._data_source
```

### Triggering Data Sync

```python
from aletheia_probe.updater.sync_utils import update_source_data
from aletheia_probe.backends.base import DataSyncCapable, get_backend_registry

registry = get_backend_registry()
for name, backend in registry.iter_backends():
    if isinstance(backend, DataSyncCapable):
        source = backend.get_data_source()
        if source:
            result = await update_source_data(source, db_writer, force=False)
```

