# OpenAlex Integration

## Overview

OpenAlex provides publication volume data that enables **contextual retraction rate calculations** instead of absolute retraction counts. This dramatically improves assessment accuracy by accounting for journal size.

### The Problem Solved

**Before**: Absolute retraction counts were misleading
- Nature: 153 retractions → flagged as CRITICAL ⚠️
- Small journal: 10 retractions → flagged as MODERATE

**After**: Retraction rates provide proper context
- Nature: 153 retractions / 446,231 publications = 0.034% → NOTE ✅
- Small journal: 10 retractions / 100 publications = 10% → CRITICAL ⚠️

## Data Source

- **Service**: OpenAlex API
- **Website**: https://openalex.org/
- **Coverage**: 240+ million scholarly works across 249,000+ sources
- **License**: CC0 (free to use)
- **Updates**: Daily (~50,000 new works/day)
- **Rate Limit**: 100,000 requests/day
- **Authentication**: None required

### Data Sources Aggregated by OpenAlex
- Crossref (primary source)
- PubMed / PubMed Central
- arXiv and other preprint servers
- Institutional repositories
- Field-specific databases

## Architecture

### OpenAlex Client
- **Module**: `src/aletheia_probe/openalex.py`
- **Class**: `OpenAlexClient`
- **Method**: On-demand API calls during journal assessment
- **Caching**: 30-day cache in key-value store
- **Rate Limiting**: Respects API limits with delays

### Integration Point
- **Location**: `src/aletheia_probe/backends/retraction_watch.py`
- **Method**: Retraction Watch backend calls OpenAlex during assessment
- **Fallback**: Gracefully degrades to count-based assessment if OpenAlex unavailable

### Cache Storage
- **Location**: `src/aletheia_probe/cache.py`
- **Table**: `key_value_cache`
- **Key Format**: `openalex:issn:{ISSN}` or `openalex:name:{normalized_name}`
- **TTL**: 30 days
- **Auto-cleanup**: Expires old entries

## Data Retrieved

For each journal, OpenAlex provides:

```json
{
  "id": "https://openalex.org/S137773608",
  "display_name": "Nature",
  "issn": ["0028-0836", "1476-4687"],
  "works_count": 446231,
  "cited_by_count": 89234567,
  "publisher": "Nature Publishing Group",
  "is_in_doaj": false,
  "homepage_url": "https://www.nature.com/",
  "country_code": "GB",
  "type": "journal",
  "works_api_url": "https://api.openalex.org/works?filter=primary_location.source.id:S137773608"
}
```

## API Endpoints Used

### 1. Search by ISSN
```http
GET https://api.openalex.org/sources?filter=issn:0028-0836
```

### 2. Search by Journal Name
```http
GET https://api.openalex.org/sources?search=Nature
```

### 3. Get Publication Counts (if needed)
```http
GET https://api.openalex.org/works?filter=primary_location.source.id:S137773608&group_by=publication_year
```

## On-Demand Enrichment

### Workflow

1. **User Assessment Request**: `aletheia-probe journal "Nature"`
2. **Retraction Data Lookup**: Backend checks for retractions
3. **OpenAlex Query**: If retractions found, fetch publication data
   - Check 30-day cache first
   - If cache miss, call OpenAlex API
   - Store result with 30-day TTL
4. **Rate Calculation**: Compute retraction rate from counts
5. **Risk Assessment**: Apply rate-based thresholds
6. **Display**: Show contextual retraction information

### Advantages of On-Demand Approach

- **Efficient**: Only fetches data for journals actually assessed
- **Fast**: <2 seconds first assessment, <1 second with cache
- **Scalable**: No bulk processing during sync
- **Fresh**: 30-day cache balances freshness and performance
- **No Waste**: Doesn't fetch data for journals never queried

## Rate Calculation

### Formula

```python
retraction_rate_overall = (total_retractions / publication_count) * 100
retraction_rate_recent = (recent_retractions / recent_publications) * 100
```

### Thresholds

Based on research showing normal retraction rates of 0.02-0.04%:

| Risk Level | Overall Rate | Multiplier |
|-----------|--------------|------------|
| **CRITICAL** | ≥1.0% | 25x+ normal |
| **HIGH** | ≥0.3% | 10x normal |
| **MODERATE** | ≥0.15% | 5x normal |
| **LOW** | ≥0.08% | 2-3x normal |
| **NOTE** | >0% | Within normal range |

## Performance

### Sync Time
- **No Impact**: OpenAlex calls happen during assessment, not sync
- **Sync remains**: 5-10 minutes (retraction data only)

### Query Time
- **First Assessment** (cache miss): ~2 seconds
  - Includes OpenAlex API call (~1.5s)
  - Plus local processing (~0.5s)
- **Subsequent Assessments** (cache hit): <1 second
  - Uses cached publication data
  - Only local computation

### Storage
- **Minimal**: Only journals queried by user
- **Growth**: ~1-2 KB per journal assessed
- **Auto-cleanup**: 30-day TTL prevents unbounded growth

### API Usage
- **Typical**: <10 requests/day for normal use
- **Maximum**: Limited by 30-day cache
- **Well within limits**: 100,000 requests/day available

## Coverage and Fallback

### OpenAlex Coverage
- **Legitimate Journals**: 80-90% indexed
- **Predatory Journals**: 30-50% indexed (less likely to be in scholarly databases)
- **Overall**: ~60-80% of journals have publication data

### Fallback Behavior
When OpenAlex data unavailable:
- Falls back to count-based thresholds
- Uses original absolute count risk assessment
- No degradation in functionality
- Transparent in output (shows counts, not rates)

## Example Assessments

### High-Volume Legitimate Journal
```
Journal: Nature
Total Retractions: 153
Publications: 446,231
Rate: 0.034%
Risk: NOTE ✅
Reasoning: Within normal range for high-volume journal
```

### Problem Journal with High Rate
```
Journal: Journal of Healthcare Engineering
Total Retractions: 1,074
Publications: 4,105
Rate: 26.16%
Risk: CRITICAL 🚫
Reasoning: Retraction rate 650x normal - severe quality problems
```

### Without OpenAlex Data
```
Journal: Unknown Predatory Journal
Total Retractions: 10
Publications: (unavailable)
Risk: MODERATE ⚠️
Reasoning: Count-based assessment - 10 total retractions
```

## Configuration

OpenAlex integration is automatic and requires no configuration. It is used internally by the Retraction Watch backend.

### Optional: Adjust Cache TTL

Modify in `src/aletheia_probe/cache.py`:

```python
# Default: 30 days
OPENALEX_CACHE_TTL = 30 * 24 * 60 * 60  # seconds
```

## Error Handling

### Network Errors
- Logs warning
- Falls back to count-based assessment
- Assessment continues without interruption

### API Rate Limiting
- Respects 429 responses
- Implements exponential backoff
- Falls back if retries exhausted

### Invalid Data
- Validates response structure
- Handles missing fields gracefully
- Logs errors for debugging

## Limitations

1. **Internet Dependency**: Requires network access for first assessment
   - **Mitigation**: 30-day cache provides offline capability

2. **Coverage Gaps**: Not all journals indexed in OpenAlex
   - **Mitigation**: Graceful fallback to count-based assessment

3. **First Query Latency**: ~2 seconds for uncached journals
   - **Mitigation**: Subsequent queries <1 second with cache

4. **Predatory Journal Coverage**: Lower OpenAlex coverage for predatory journals
   - **Mitigation**: This is actually beneficial - predatory journals get count-based assessment which is often more severe

## Testing

### Test Script
Location: `scripts/test_openalex_integration.py`

Run tests:
```bash
python scripts/test_openalex_integration.py
```

Tests verify:
- API connectivity
- Rate calculation logic
- Cache functionality
- Error handling
- Fallback behavior

### Manual Testing

```bash
# Sync retraction data
aletheia-probe sync

# Test with high-volume journal
aletheia-probe journal "Nature"
# Expected: NOTE risk level with rate displayed

# Test with problematic journal
aletheia-probe journal "Journal of Healthcare Engineering"
# Expected: CRITICAL risk level with high rate

# Test cache
aletheia-probe journal "Nature"
# Expected: Faster response (<1s), same results
```

## Future Enhancements

Potential improvements:
- Background pre-fetching for commonly assessed journals
- Historical trend analysis (publication volume over time)
- Field-specific normalization (different disciplines have different norms)
- Citation impact weighting
- Publisher-level aggregation

## References

- **OpenAlex API Documentation**: https://docs.openalex.org/
- **OpenAlex Website**: https://openalex.org/
- **Client Implementation**: `src/aletheia_probe/openalex.py`
- **Retraction Watch Backend**: `src/aletheia_probe/backends/retraction_watch.py`
- **Cache Implementation**: `src/aletheia_probe/cache.py`
