# OpenCitations Integration

## Overview

OpenCitations provides open citation graph metrics that can be used as an additional heuristic signal for venue legitimacy assessment.

This integration adds:
- `opencitations_analyzer` backend (API-based, cache-first)
- Pairwise cross-validation support with:
  - `openalex_analyzer ↔ opencitations_analyzer`
  - `crossref_analyzer ↔ opencitations_analyzer`

## Data Source

- **Service**: OpenCitations Index API v2
- **Base URL**: `https://api.opencitations.net/index/v2`
- **Key endpoints used**:
  - `venue-citation-count/issn:{issn}`
  - `venue-reference-count/issn:{issn}`
- **Authentication**: None
- **License**: Open citation data (OpenCitations project)

## Architecture

### Backend
- **Module**: `src/aletheia_probe/backends/opencitations_analyzer.py`
- **Class**: `OpenCitationsAnalyzerBackend`
- **Base class**: `ApiBackendWithCache`
- **Evidence type**: `HEURISTIC`
- **Fallback strategies**: `ISSN`, `EISSN`

### Cross-validation
- **Module**: `src/aletheia_probe/cross_validation/validators.py`
- **Validators**:
  - `OpenAlexOpenCitationsValidator`
  - `CrossRefOpenCitationsValidator`
- **Registry wiring**: `src/aletheia_probe/cross_validation/registry.py`

## Processing

1. Query by ISSN/eISSN.
2. Fetch venue citation count and venue reference count.
3. Derive lightweight metrics (citation/reference ratio, footprint size).
4. Produce heuristic assessment with flags and reasoning.
5. Cross-validate with OpenAlex/CrossRef when those results are available.

## Limitations

- Identifier-driven: name-only queries do not use this backend directly.
- Coverage differs across venues and disciplines.
- Citation counts are useful for corroboration but are not a standalone quality guarantee.

## Testing

- `tests/unit/backends/test_opencitations_analyzer.py`
- `tests/unit/test_cross_validation.py` (new validator coverage)
