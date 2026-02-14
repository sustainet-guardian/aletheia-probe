# CORE Integration

## Overview

The CORE integration adds ranked conference and journal venue signals from the CORE/ICORE portal to assessment decisions.

- **Conference source**: ICORE/CORE conference rankings portal
- **Journal source**: CORE journal rankings portal (legacy/discontinued dataset)
- **Classification**: Legitimate-list evidence for ranked entries

## Data Sources

### Conferences
- **Portal**: `https://portal.core.edu.au/conf-ranks/`
- **Default source filter**: `ICORE2026`
- **Format**: HTML (paginated table)
- **Fields used**: title, acronym, source, rank

### Journals
- **Portal**: `https://portal.core.edu.au/jnl-ranks/`
- **Default source filter**: `CORE2020`
- **Format**: HTML (paginated table)
- **Fields used**: title, source, rank

## Architecture

### Data Source Components
- **Module**: `src/aletheia_probe/updater/sources/core.py`
- **Classes**:
  - `CoreConferenceSource`
  - `CoreJournalSource`
- **Base class**: `DataSource`
- **Update cadence**: Monthly (`30` days)

### Backend Components
- **Conference backend**: `src/aletheia_probe/backends/core_conferences.py`
- **Journal backend**: `src/aletheia_probe/backends/core_journals.py`
- **Base class**: `CachedBackend`
- **Evidence type**: `LEGITIMATE_LIST`
- **Cache TTL**: `24 * 30` hours

### Configuration
Defined in `src/aletheia_probe/config.py` (`DataSourceUrlConfig`):
- `core_conference_rankings_url`
- `core_journal_rankings_url`
- `core_conference_default_source`
- `core_journal_default_source`

## Data Processing Rules

1. Fetch paginated portal pages (`50` rows per page).
2. Parse table rows into normalized venue entries.
3. Keep only ranked entries with these rank labels:
   - `A*`, `A`, `B`, `C`, `Australasian B`, `Australasian C`
4. Exclude non-ranked/non-classification statuses (for example `Unranked`, `National`, `Journal Published`, `Not ranked`, `not primarily CS`).
5. Deduplicate by normalized name before writing to cache.

## Metadata Stored

Each CORE entry stores source metadata in `metadata`:
- `source_url`
- `core_entity_type` (`conference` or `journal`)
- `core_source` (for example `ICORE2026`, `CORE2020`)
- `core_rank`
- `core_acronym` (conference source only)

## Usage

```bash
# Sync only CORE conferences
aletheia-probe sync core_conferences

# Sync only CORE journals
aletheia-probe sync core_journals

# Normal sync includes CORE backends when enabled
aletheia-probe sync
```

## Limitations

1. CORE journal rankings are legacy/discontinued and should be interpreted accordingly.
2. Parsing depends on portal table structure and rank label conventions.
3. Matching is normalized name based; source-side aliases/variants may still miss edge cases.

## References

- `src/aletheia_probe/updater/sources/core.py`
- `src/aletheia_probe/backends/core_conferences.py`
- `src/aletheia_probe/backends/core_journals.py`
- `tests/unit/updater/test_core_source.py`
- `tests/unit/backends/test_core_backends.py`
- https://portal.core.edu.au/conf-ranks/
- https://portal.core.edu.au/jnl-ranks/
