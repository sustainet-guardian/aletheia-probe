# Algerian Ministry Integration

## Overview

The Algerian Ministry of Higher Education (DGRSDT) provides an authoritative list of predatory journals. This integration adds ~3,300 government-verified predatory journals to the assessment database.

## Data Source

- **Authority**: Algerian Ministry of Higher Education (DGRSDT)
- **URL Pattern**: `https://dgrsdt.dz/storage/revus/Liste%20des%20Revues%20Pr%C3%A9datrices,%20Editeurs%20pr%C3%A9dateurs/{YEAR}.zip`
- **Format**: Annual ZIP archives containing PDF lists
- **Content**: Numbered lists of predatory journals with multiple URLs per journal
- **Classification**: Predatory journals only
- **Volume**: ~3,300 unique journals (as of 2024)

## Architecture

### Data Source Component
- **Class**: `AlgerianMinistrySource`
- **Location**: `src/aletheia_probe/updater.py`
- **Update Schedule**: Monthly with fallback to previous year
- **Cache TTL**: 48 hours

### Backend Component
- **Class**: `AlgerianMinistryBackend`
- **Location**: `src/aletheia_probe/backends/algerian_ministry.py`
- **Type**: `CachedBackend` (exact matching)
- **Assessment**: Returns "predatory" for matches

## Data Processing Pipeline

```
Download ZIP Archive → Extract PDFs → Parse Text → Normalize Names → Store in Cache
```

### Processing Steps

1. **Download**: Fetches ZIP archive for current/previous year
2. **Extraction**: Uses Python's built-in zipfile module
3. **PDF Parsing**: PyPDF2 extracts text from PDF documents
4. **Text Processing**: Regex patterns identify numbered journal entries (`N° Journal Name URL1 URL2...`)
5. **URL Handling**: Preserves multiple URLs associated with each journal
6. **Normalization**: Standardizes journal names for matching
7. **Deduplication**: Removes duplicate entries based on normalized names
8. **Storage**: Saves to SQLite cache with metadata

## Dependencies

### Python Packages
- `PyPDF2>=3.0.0` - PDF text extraction
- Built-in `zipfile` module - ZIP archive handling (Python standard library)

See **[pyproject.toml](../../pyproject.toml)** for complete dependency list.

### System Requirements
No additional system packages required. ZIP archives are handled by Python's built-in zipfile module.

## Data Characteristics

- **Volume**: ~3,300 unique predatory journals
- **Languages**: Multilingual content (Arabic, French, English)
- **URLs**: Multiple URLs preserved per journal entry
- **Geographic Focus**: North African and Middle Eastern journals
- **Authority Level**: Government-backed classification (high credibility)

## Performance

- **PDF Processing**: ~3,300 journals in <30 seconds
- **Database Storage**: ~100 journals/second
- **Search Performance**: <100ms with indexing
- **Archive Size**: ~17MB download (varies by year and format)
- **Storage Impact**: ~3,000 database records plus URLs

## Integration Points

### Registration
- **Data Source**: `data_updater.add_source(AlgerianMinistrySource())` in `updater.py`
- **Backend**: Auto-registered via `backends/__init__.py` import

### CLI Usage
```bash
# Sync data
aletheia-probe sync

# Assess journal
aletheia-probe journal "Journal Name"
```

Backend automatically contributes to assessments with proper confidence scoring.

## Quality Assurance

### Data Validation
- Exact matching prevents false positives
- Multiple URLs properly stored and retrieved
- Input normalization handles name variations
- Metadata validation ensures data integrity

### Coverage
- Complements Western-focused lists (Beall's)
- Adds geographic diversity to predatory journal detection
- Government authority increases credibility of classifications

## Limitations

- **Update Frequency**: Limited to annual publication of official lists
- **Coverage**: Primarily focuses on journals relevant to North African region
- **Matching**: Relies on normalized name matching (no ISSN in source data)
- **Language**: PDF parsing must handle multilingual text

## Future Enhancements

Potential improvements:
- ISSN extraction from URLs where available
- Publisher-level tracking
- Temporal analysis of list changes
- Integration with similar government sources from other countries
