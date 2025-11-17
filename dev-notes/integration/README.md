# Backend Integrations

This directory documents the data source integrations that power the journal assessment tool.

## Integration Architecture

### Data Flow

```
Data Sources → Updater → Cache → Backends → Dispatcher → Assessment Result
```

### Components

1. **Data Sources** (`updater.py`)
   - Fetch raw data from external sources
   - Process and normalize
   - Store in SQLite cache

2. **Backends** (`backends/*.py`)
   - Query cached data during assessment
   - Apply classification logic
   - Return structured results

3. **Dispatcher** (`dispatcher.py`)
   - Aggregates results from all backends
   - Applies cross-validation logic
   - Generates final assessment with confidence scores

## Adding New Integrations

When adding a new data source integration:

1. **Create Source Class** in `src/aletheia_probe/updater.py`
   - Inherit from `DataSource`
   - Implement `fetch_and_store()` method
   - Define update schedule in `should_update()`

2. **Create Backend Class** in `src/aletheia_probe/backends/`
   - Inherit from `Backend` or `CachedBackend`
   - Implement `assess()` method
   - Define backend metadata (name, description, capabilities)

3. **Register Backend** in `src/aletheia_probe/backends/__init__.py`
   - Import the backend module
   - Auto-registration via decorators

4. **Document Integration** in this directory
   - Create state-based documentation (not implementation history)
   - Follow existing template structure
   - Focus on what the integration provides, not how it was built

### Documentation Template

Each integration document should include:

- **Overview**: Purpose and value of the integration
- **Data Source**: Authority, URL, format, volume
- **Architecture**: Classes, locations, types
- **Data Processing**: Pipeline and steps
- **Dependencies**: Python packages and system requirements
- **Performance**: Timing, storage, query characteristics
- **Usage**: CLI commands and examples
- **Limitations**: Known constraints and coverage gaps
- **Future Enhancements**: Potential improvements
- **References**: Links to implementations and external resources

## Related Documentation

- **[DEPENDENCIES.md](../DEPENDENCIES.md)** - System and Python dependencies
- **[CODING_STANDARDS.md](../CODING_STANDARDS.md)** - Code style and patterns
- **[LOGGING_USAGE.md](../LOGGING_USAGE.md)** - Logging conventions

## See Also

- Source code: `src/aletheia_probe/updater.py`
- Backend code: `src/aletheia_probe/backends/`
- Cache implementation: `src/aletheia_probe/cache.py`
- Dispatcher logic: `src/aletheia_probe/dispatcher.py`
