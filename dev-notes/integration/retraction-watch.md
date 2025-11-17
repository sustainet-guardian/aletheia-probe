# Retraction Watch Integration

## Overview

The Retraction Watch Database provides comprehensive retraction data for academic journals. This integration enhances journal quality assessments by identifying patterns of retractions that may indicate quality issues or predatory behavior.

## Data Source

- **Authority**: Retraction Watch (maintained by Crossref)
- **Repository**: https://gitlab.com/crossref/retraction-watch-data
- **Format**: CSV database
- **Records**: ~67,000 retraction records across ~27,000 journals
- **Updates**: Daily (by Retraction Watch); synced weekly by this tool
- **License**: Open data (verify specific license in source repository)

## Architecture

### Data Source Component
- **Class**: `RetractionWatchSource`
- **Location**: `src/aletheia_probe/updater.py`
- **Update Method**: Git clone (depth=1 for efficiency)
- **Update Frequency**: Weekly
- **Processing**: CSV parsing with journal-level aggregation

### Backend Component
- **Class**: `RetractionWatchBackend`
- **Location**: `src/aletheia_probe/backends/retraction_watch.py`
- **Type**: Quality indicator (not binary predatory/legitimate classifier)
- **Assessment**: Returns risk level with detailed metadata

### OpenAlex Integration
- **Module**: `src/aletheia_probe/openalex.py`
- **Purpose**: Fetch publication volumes for contextual retraction rates
- **Method**: On-demand API calls during assessment
- **Caching**: 30-day cache for publication data

## Risk Assessment

### Rate-Based Thresholds (Primary)
Used when publication volume data is available from OpenAlex:

| Risk Level | Overall Rate | Recent Rate (2yr) | Context |
|-----------|--------------|-------------------|---------|
| **CRITICAL** | ≥1.0% | ≥2.0% | 25x+ normal rate |
| **HIGH** | ≥0.3% | ≥0.6% | 10x normal rate |
| **MODERATE** | ≥0.15% | ≥0.3% | 5x normal rate |
| **LOW** | ≥0.08% | ≥0.15% | 2-3x normal rate |
| **NOTE** | >0% | >0% | Within normal range (0.02-0.04%) |

### Count-Based Thresholds (Fallback)
Used when publication volume data is unavailable:

| Risk Level | Total Count | Recent Count (2yr) |
|-----------|-------------|-------------------|
| **CRITICAL** | ≥21 | ≥10 |
| **HIGH** | ≥11 | ≥5 |
| **MODERATE** | ≥6 | ≥3 |
| **LOW** | ≥3 | - |
| **NOTE** | 1-2 | - |

**Note**: Recent activity is weighted heavily as it indicates current quality problems.

## Data Processing Pipeline

```
Git Clone → Parse CSV → Aggregate by Journal → Calculate Metrics → Store in Cache
```

### Processing Steps

1. **Clone**: Fetches latest data from GitLab repository
2. **Parse**: Processes ~67,000 CSV records
3. **Aggregate**: Groups retractions by journal (~27,000 unique journals)
4. **Calculate**: Computes temporal metrics (total, recent, very recent)
5. **Enrich**: During assessment, fetches publication volumes from OpenAlex on-demand
6. **Store**: Saves to SQLite cache with comprehensive metadata

## Metadata Stored

```json
{
  "total_retractions": 153,
  "recent_retractions": 19,
  "very_recent_retractions": 8,
  "risk_level": "note",
  "first_retraction_date": "1995-03-15",
  "last_retraction_date": "2024-10-12",
  "retraction_types": {"Retraction": 145, "Correction": 8},
  "top_reasons": [
    {"reason": "Error in data", "count": 42},
    {"reason": "Duplication", "count": 18}
  ],
  "publishers": ["Nature Publishing Group"],
  "all_names": ["Nature", "Nat."],
  "publication_count": 446231,
  "retraction_rate_overall": 0.034,
  "retraction_rate_recent": 0.012
}
```

## Assessment Integration

### Cross-Validation Logic

The retraction data enhances existing assessments:

```python
# Predatory journal + high retractions → increased confidence
if predatory_classification AND high_retractions:
    confidence_boost = +0.05
    reason = "High retraction rate corroborates predatory classification"

# Legitimate journal + high retractions → warning added
elif legitimate_classification AND high_retractions:
    # Classification unchanged, but flag issued
    warning = "⚠️ WARNING: High retraction rate despite legitimate classification"

# Unknown journal + high retractions → flagged as concerning
elif insufficient_data AND high_retractions:
    warning = "⚠️ WARNING: High retraction rate detected - proceed with caution"
```

### Display Format

**With publication data** (rate-based):
```
📊 153 retraction(s): 0.034% rate
   (within normal range for 446,231 publications)
```

**Without publication data** (count-based fallback):
```
⚠️ HIGH retraction risk: 1,253 total retractions (534 recent)
```

**Critical cases**:
```
⚠️ CRITICAL retraction risk: 1,074 retractions (1,013 recent)
   = 21.480% rate (4,105 total publications)
```

## Dependencies

### Python Packages
See **[pyproject.toml](../../pyproject.toml)** for complete list.

###System Requirements
- **git** - For cloning Retraction Watch repository

See **[DEPENDENCIES.md](../DEPENDENCIES.md)** for installation instructions.

## Performance

### Initial Sync
- **Time**: 5-10 minutes (git clone + processing)
- **Memory**: ~500MB peak
- **Network**: ~60MB download
- **Storage**: ~20MB in SQLite cache

### Subsequent Updates
- **Frequency**: Weekly (configurable)
- **Time**: 5-10 minutes (full re-import)

### Query Performance
- **Cached Lookup**: <1ms (SQLite)
- **With OpenAlex**: ~2 seconds first time, <1 second cached (30-day cache)
- **Fallback**: Instant (uses cached retraction data only)

## Usage

```bash
# Sync retraction data
aletheia-probe sync

# Assess journal (automatically includes retraction risk)
aletheia-probe journal "Nature"

# Force resync of data
aletheia-probe sync --force
```

Output includes retraction data in assessment reasoning and backend results.

## Database Schema

Stored in `journal_lists` table:

```sql
source_name: "retraction_watch"
list_type: "quality_indicator"  -- Not binary predatory/legitimate
metadata: JSON blob (see Metadata Stored section above)
```

## Configuration

Auto-enabled by default. Example configuration:

```yaml
backends:
  retraction_watch:
    name: retraction_watch
    enabled: true
    weight: 0.8
    timeout: 10
    config: {}
```

## Limitations

1. **No ISSN in Dataset**: Matching relies on normalized journal names
   - May miss matches due to name variations
   - Normalizer handles most common variations

2. **Full Re-import**: No incremental updates
   - Weekly full dataset reprocessing
   - Could be optimized with change detection

3. **Quality Indicator Only**: Does not independently classify as predatory/legitimate
   - Enhances existing classifications
   - Adds warnings and confidence adjustments

4. **OpenAlex Coverage**: ~60-80% of journals have publication data
   - Predatory journals less likely to be indexed
   - Falls back to count-based assessment when unavailable

## Future Enhancements

Potential improvements:
- Publisher-level risk scoring aggregation
- Temporal trend analysis (increasing vs. decreasing retraction rates)
- Reason-based severity weighting (distinguish fraud from honest errors)
- Incremental updates to avoid full re-import
- Field-specific retraction rate normalization
- Author-level retraction tracking

## References

- **Retraction Watch Database**: https://gitlab.com/crossref/retraction-watch-data
- **OpenAlex API**: https://openalex.org/
- **Backend Implementation**: `src/aletheia_probe/backends/retraction_watch.py`
- **OpenAlex Client**: `src/aletheia_probe/openalex.py`
- **Source Implementation**: `src/aletheia_probe/updater.py` (`RetractionWatchSource`)
- **Logging Documentation**: [LOGGING_USAGE.md](../LOGGING_USAGE.md)
