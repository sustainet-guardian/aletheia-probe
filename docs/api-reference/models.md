# Data Models Reference

Reference for core data models used in journal assessment.

## Overview

All models are defined in `src/aletheia_probe/models.py` using Pydantic for validation and serialization.

## Query Models

### QueryInput

Normalized query input passed to backends.

**Source:** `src/aletheia_probe/models.py`

**Concept:** Contains normalized journal information extracted from user input, including identifiers (ISSN, DOI), alternative names, and venue type detection.

**Key Fields:**
- `raw_input` - Original user input
- `normalized_name` - Normalized journal name
- `identifiers` - Dict of ISSN, DOI, etc.
- `aliases` - Alternative names
- `venue_type` - Journal, conference, workshop, etc.

## Result Models

### BackendResult

Individual backend query result.

**Concept:** Contains assessment from a single backend, including status, confidence score, and evidence metadata.

**Key Fields:**
- `backend_name` - Backend identifier
- `status` - FOUND, NOT_FOUND, ERROR, TIMEOUT, RATE_LIMITED
- `confidence` - Score 0.0-1.0 (validated)
- `assessment` - "predatory", "legitimate", "suspicious", or None
- `response_time` - Query timing
- `cached` - Cache hit indicator

### AssessmentResult

Final aggregated assessment.

**Concept:** Combines all backend results with weighted scoring, reasoning, and metadata.

**Key Fields:**
- `assessment` - Final classification
- `confidence` - Overall confidence
- `backend_results` - Individual backend results
- `reasoning` - Human-readable explanations
- `metadata` - Journal metadata if available

## Metadata Models

### JournalMetadata

Journal metadata collected during assessment.

**Concept:** Optional metadata about journal characteristics like publisher, subject areas, founding year, and peer review status.

**Key Fields:** `name`, `issn`, `eissn`, `publisher`, `subject_areas`, `founding_year`, `open_access`, `peer_reviewed`

## Configuration Models

### ConfigBackend

Backend configuration.

**Concept:** Defines backend behavior including enable/disable, weighting, timeout, rate limiting, and backend-specific parameters.

**Key Fields:**
- `enabled` - Whether backend is active
- `weight` - Assessment weight (≥ 0.0)
- `timeout` - Query timeout in seconds
- `email` - API contact email (validated with regex)
- `config` - Backend-specific settings dict

## BibTeX Models

### BibtexEntry

Single BibTeX entry representation.

**Concept:** Extracted venue information from BibTeX entries with retraction status tracking.

**Key Fields:** `key`, `journal_name`, `entry_type`, `venue_type`, `doi`, `issn`, `is_retracted`, `retraction_info`

### BibtexAssessmentResult

Aggregated BibTeX file assessment.

**Concept:** Statistics and results from assessing all venues in a BibTeX file, broken down by venue type and assessment category.

**Key Fields:** Entry counts, assessment counts (predatory/legitimate/suspicious), venue type breakdowns, retraction counts, processing time.

## Enumerations

**VenueType** (`src/aletheia_probe/models.py`): JOURNAL, CONFERENCE, WORKSHOP, SYMPOSIUM, PROCEEDINGS, BOOK, PREPRINT, UNKNOWN

**BackendStatus** (`src/aletheia_probe/models.py`): FOUND, NOT_FOUND, ERROR, RATE_LIMITED, TIMEOUT

**AssessmentType** (`src/aletheia_probe/enums.py`): PREDATORY, LEGITIMATE, SUSPICIOUS, UNKNOWN

**EvidenceType** (`src/aletheia_probe/enums.py`): PREDATORY_LIST, LEGITIMATE_LIST, HEURISTIC, QUALITY_INDICATOR

## Working with Models

### Serialization

```python
# To dict/JSON
data = model.model_dump()
json_str = model.model_dump_json(indent=2)

# From dict/JSON
obj = ModelClass(**data_dict)
obj = ModelClass.model_validate_json(json_string)
```

### Validation

Pydantic automatically validates:
- Required fields
- Type correctness
- Constraints (e.g., confidence in 0.0-1.0 range)
- Email format (for ConfigBackend)

Raises `ValidationError` on invalid data.

## Related Documentation

- [Backend API Reference](backends.md) - Backend interface using these models
- [Extending Guide](extending-guide.md) - Building backends with these models
