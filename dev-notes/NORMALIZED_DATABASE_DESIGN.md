# Normalized Database Schema

## Overview

The journal assessment tool uses a normalized SQLite database schema to handle multiple data sources, deduplication, and rich metadata while maintaining data integrity.

**Implementation**: `src/aletheia_probe/cache.py`

## Current Schema

### 1. Core Journals Table
```sql
CREATE TABLE journals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    normalized_name TEXT UNIQUE NOT NULL,  -- Primary identifier
    display_name TEXT NOT NULL,            -- Best/preferred display name
    issn TEXT,                             -- Primary ISSN
    eissn TEXT,                            -- Electronic ISSN
    publisher TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 2. Journal Names Table (for aliases/variants)
```sql
CREATE TABLE journal_names (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    journal_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    name_type TEXT DEFAULT 'alias',        -- 'canonical', 'alias', 'abbreviation'
    source_name TEXT,                      -- Which source provided this name
    FOREIGN KEY (journal_id) REFERENCES journals(id) ON DELETE CASCADE,
    UNIQUE(journal_id, name)
);
```

### 3. Journal URLs Table
```sql
CREATE TABLE journal_urls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    journal_id INTEGER NOT NULL,
    url TEXT NOT NULL,
    url_type TEXT DEFAULT 'website',       -- 'website', 'submission', 'archive'
    is_active BOOLEAN DEFAULT TRUE,
    first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (journal_id) REFERENCES journals(id) ON DELETE CASCADE,
    UNIQUE(journal_id, url)
);
```

### 4. Data Sources Table
```sql
CREATE TABLE data_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,             -- 'bealls', 'algerian_ministry', 'doaj'
    display_name TEXT NOT NULL,            -- 'Beall\'s List', 'Algerian Ministry'
    source_type TEXT NOT NULL,             -- 'predatory', 'legitimate', 'mixed'
    authority_level INTEGER DEFAULT 5,     -- 1-10 credibility score
    base_url TEXT,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 5. Source Assessments Table (many-to-many)
```sql
CREATE TABLE source_assessments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    journal_id INTEGER NOT NULL,
    source_id INTEGER NOT NULL,
    assessment TEXT NOT NULL,              -- 'predatory', 'legitimate', 'unknown'
    confidence REAL DEFAULT 1.0,          -- 0.0-1.0 confidence score
    first_listed_at TIMESTAMP,            -- When first appeared in this source
    last_confirmed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'active',         -- 'active', 'removed', 'disputed'
    FOREIGN KEY (journal_id) REFERENCES journals(id) ON DELETE CASCADE,
    FOREIGN KEY (source_id) REFERENCES data_sources(id) ON DELETE CASCADE,
    UNIQUE(journal_id, source_id)
);
```

### 6. Source Updates Table
```sql
CREATE TABLE source_updates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL,
    update_type TEXT NOT NULL,             -- 'full', 'incremental', 'verification'
    status TEXT NOT NULL,                  -- 'success', 'failed', 'partial'
    records_added INTEGER DEFAULT 0,
    records_updated INTEGER DEFAULT 0,
    records_removed INTEGER DEFAULT 0,
    error_message TEXT,
    started_at TIMESTAMP,
    completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (source_id) REFERENCES data_sources(id)
);
```

### 7. Retraction Statistics Table
```sql
CREATE TABLE retraction_statistics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    journal_id INTEGER NOT NULL,
    total_retractions INTEGER NOT NULL DEFAULT 0,
    recent_retractions INTEGER NOT NULL DEFAULT 0,
    very_recent_retractions INTEGER NOT NULL DEFAULT 0,
    retraction_types TEXT,                 -- JSON: dictionary of retraction types and counts
    top_reasons TEXT,                      -- JSON: array of [reason, count] tuples
    publishers TEXT,                       -- JSON: array of publisher names
    first_retraction_date TEXT,            -- ISO format date string
    last_retraction_date TEXT,             -- ISO format date string
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (journal_id) REFERENCES journals(id) ON DELETE CASCADE,
    UNIQUE(journal_id)
);
```

### 8. Venue Acronyms Cluster (three tables)

**Purpose**: Pre-compiled venue name lookup, imported from the venue-acronyms-2025 pipeline.
Normalized into three tables so every value is directly queryable.

```sql
-- One row per (acronym, entity_type) pair
CREATE TABLE venue_acronyms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    acronym TEXT NOT NULL COLLATE NOCASE,
    entity_type TEXT NOT NULL,          -- VenueType: 'journal', 'conference', ...
    canonical TEXT NOT NULL,            -- Fully-expanded lowercase authoritative name
    confidence_score REAL DEFAULT 0.0,  -- LLM consensus confidence (0.0–1.0)
    source_file TEXT,                   -- Source acronyms-YYYY-MM.json filename
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(acronym, entity_type)
);

-- All observed name forms (expanded and abbreviated) — one row per variant
CREATE TABLE venue_acronym_variants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    venue_acronym_id INTEGER NOT NULL,
    variant TEXT NOT NULL COLLATE NOCASE,
    FOREIGN KEY (venue_acronym_id) REFERENCES venue_acronyms(id) ON DELETE CASCADE,
    UNIQUE(venue_acronym_id, variant)
);

-- Known ISSNs — one row per ISSN
CREATE TABLE venue_acronym_issns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    venue_acronym_id INTEGER NOT NULL,
    issn TEXT NOT NULL,
    FOREIGN KEY (venue_acronym_id) REFERENCES venue_acronyms(id) ON DELETE CASCADE,
    UNIQUE(venue_acronym_id, issn)
);
```

**Lookup patterns**:
- Acronym → canonical: `SELECT canonical FROM venue_acronyms WHERE acronym = ? AND entity_type = ?`
- Variant → canonical: `SELECT va.canonical FROM venue_acronyms va JOIN venue_acronym_variants vav ON va.id = vav.venue_acronym_id WHERE vav.variant = ? AND va.entity_type = ?`
- ISSN → acronym entries: `SELECT va.* FROM venue_acronyms va JOIN venue_acronym_issns vai ON va.id = vai.venue_acronym_id WHERE vai.issn = ?`

**Import source**: `aletheia-probe acronym import <acronyms-YYYY-MM.json>`

### 9. Assessment Cache Table

**Purpose**: Domain-specific caching for structured journal/conference assessment results

This table stores complete `AssessmentResult` objects as JSON along with their query metadata. It uses MD5 hashes (32 hex characters) of normalized query parameters as keys.

**Use this for**: Caching complete assessment operations and their results

```sql
CREATE TABLE assessment_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query_hash TEXT UNIQUE NOT NULL,
    query_input TEXT NOT NULL,
    assessment_result TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL
);
```

### 9. Article Retractions Table
```sql
CREATE TABLE article_retractions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doi TEXT UNIQUE NOT NULL,
    is_retracted BOOLEAN NOT NULL DEFAULT FALSE,
    retraction_type TEXT,
    retraction_date TEXT,
    retraction_doi TEXT,
    retraction_reason TEXT,
    source TEXT NOT NULL,
    checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL
);
```

## Indexes

For performance optimization:

```sql
CREATE INDEX idx_journals_normalized_name ON journals(normalized_name);
CREATE INDEX idx_journals_issn ON journals(issn);
CREATE INDEX idx_journals_eissn ON journals(eissn);
CREATE INDEX idx_journal_names_name ON journal_names(name);
CREATE INDEX idx_journal_names_journal_id ON journal_names(journal_id);
CREATE INDEX idx_journal_urls_journal_id ON journal_urls(journal_id);
CREATE INDEX idx_journal_urls_url ON journal_urls(url);
CREATE INDEX idx_source_assessments_journal_id ON source_assessments(journal_id);
CREATE INDEX idx_source_assessments_source_id ON source_assessments(source_id);
CREATE INDEX idx_retraction_statistics_journal_id ON retraction_statistics(journal_id);
CREATE INDEX idx_assessment_cache_expires ON assessment_cache(expires_at);
CREATE INDEX idx_article_retractions_doi ON article_retractions(doi);
CREATE INDEX idx_article_retractions_expires ON article_retractions(expires_at);
```

## Benefits of This Design

### 1. **Proper Normalization**
- Each journal exists once with a canonical normalized name
- Multiple sources can reference the same journal
- No duplicate entries for the same journal

### 2. **Cross-Source Analysis**
- Multiple sources can assess the same journal
- Track confidence levels from different sources
- Historical tracking of assessments via timestamps

### 3. **Purpose-Built Tables**
- Dedicated tables for specific data types (e.g., retraction_statistics)
- Proper column types instead of generic key-value storage
- More efficient queries and better type safety

### 4. **URL Management**
- URLs linked to journals, not source entries
- No conflicts when same URL appears in multiple sources
- Track URL discovery timeline

### 5. **Source Authority**
- Weight sources by authority level
- Track source reliability and update history
- Enable source-specific configuration

### 6. **Performance**
- Comprehensive indexing for fast lookups
- Efficient queries via normalized structure
- Deduplication happens at insert time

## Example Queries

### Find journals assessed by multiple sources:
```sql
SELECT j.display_name, COUNT(sa.source_id) as source_count
FROM journals j
JOIN source_assessments sa ON j.id = sa.journal_id
GROUP BY j.id
HAVING COUNT(sa.source_id) > 1;
```

### Find conflicting assessments:
```sql
SELECT j.display_name,
       GROUP_CONCAT(ds.name || ':' || sa.assessment) as assessments
FROM journals j
JOIN source_assessments sa ON j.id = sa.journal_id
JOIN data_sources ds ON sa.source_id = ds.id
GROUP BY j.id
HAVING COUNT(DISTINCT sa.assessment) > 1;
```

### Get weighted confidence score:
```sql
SELECT j.display_name,
       SUM(sa.confidence * ds.authority_level) / SUM(ds.authority_level) as weighted_confidence
FROM journals j
JOIN source_assessments sa ON j.id = sa.journal_id
JOIN data_sources ds ON sa.source_id = ds.id
WHERE sa.assessment = 'predatory'
GROUP BY j.id;
```

## Database Location

- **Default Path**: `.aletheia-probe/cache.db` (in current working directory)
- **Custom Path**: Can be configured via `CacheManager(db_path=...)`

## Usage

### Registering Data Sources

```python
from aletheia_probe.cache import CacheManager

cache = CacheManager()
source_id = cache.register_data_source(
    name="doaj",
    display_name="Directory of Open Access Journals",
    source_type="legitimate",
    authority_level=9,
    base_url="https://doaj.org/",
    description="Curated list of legitimate open access journals"
)
```

### Adding Journal Entries

```python
from aletheia_probe.data_models import JournalEntryData

entry = JournalEntryData(
    normalized_name="nature",
    display_name="Nature",
    source_name="doaj",
    list_type="legitimate",
    issn="0028-0836",
    urls=["https://www.nature.com/"],
    metadata={"impact_factor": "49.962"}
)

cache.add_journal_entry(entry)
```

### Querying Journals

```python
# Search by normalized name
results = cache.search_journals(normalized_name="nature")

# Search by ISSN
results = cache.search_journals(issn="0028-0836")

# Search by source
results = cache.search_journals(source_name="doaj")
```

## Implementation Details

See `src/aletheia_probe/cache.py` for complete implementation including:
- Database initialization
- CRUD operations for all tables
- Query methods with proper indexing
- Transaction management
- Error handling

## Related Documentation

- **Cache Implementation**: `src/aletheia_probe/cache.py`
- **Data Models**: `src/aletheia_probe/data_models.py`
- **Integration Docs**: [dev-notes/integration/](integration/)