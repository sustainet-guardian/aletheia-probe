# Data Models Reference

Reference for core data models used in journal assessment.

## Overview

All models are defined in `src/aletheia_probe/models.py` using Pydantic for validation and serialization.

## Query Models

### QueryInput

Normalized query input passed to backends.

**Concept:** Contains normalized journal information extracted from user input, including identifiers (ISSN, DOI), alternative names, and venue type detection.

**Key Fields:** `raw_input`, `normalized_name`, `identifiers` (dict), `aliases` (list), `venue_type`

## Result Models

### BackendResult

Individual backend query result.

**Concept:** Contains assessment from a single backend, including status (FOUND/NOT_FOUND/ERROR/TIMEOUT/RATE_LIMITED), confidence score (0.0-1.0, validated), assessment type, response timing, and cache indicator.

**Key Fields:** `backend_name`, `status`, `confidence`, `assessment`, `response_time`, `cached`

### AssessmentResult

Final aggregated assessment.

**Concept:** Combines all backend results with weighted scoring, reasoning, and metadata.

**Key Fields:** `assessment`, `confidence`, `backend_results` (list), `reasoning` (list), `metadata`, `processing_time`

## Metadata Models

### JournalMetadata

Journal metadata collected during assessment.

**Concept:** Optional metadata about journal characteristics like publisher, subject areas, founding year, and peer review status.

**Fields:** `name`, `issn`, `eissn`, `publisher`, `subject_areas`, `founding_year`, `open_access`, `peer_reviewed`

## Configuration Models

### ConfigBackend

Backend configuration.

**Concept:** Defines backend behavior including enable/disable, weighting, timeout, rate limiting, and backend-specific parameters.

**Key Fields:** `enabled`, `weight` (≥ 0.0), `timeout`, `email` (validated with regex), `config` (dict)

## BibTeX Models

### BibtexEntry

Single BibTeX entry representation.

**Concept:** Extracted venue information from BibTeX entries with retraction status tracking.

**Fields:** `key`, `journal_name`, `entry_type`, `venue_type`, `doi`, `issn`, `is_retracted`, `retraction_info`

### BibtexAssessmentResult

Aggregated BibTeX file assessment.

**Concept:** Statistics and results from assessing all venues in a BibTeX file, broken down by venue type and assessment category.

**Fields:** Entry counts, assessment counts (predatory/legitimate/suspicious), venue type breakdowns, retraction counts, processing time

## Enumerations

**VenueType:** JOURNAL, CONFERENCE, WORKSHOP, SYMPOSIUM, PROCEEDINGS, BOOK, PREPRINT, UNKNOWN

**BackendStatus:** FOUND, NOT_FOUND, ERROR, RATE_LIMITED, TIMEOUT

**AssessmentType** (`src/aletheia_probe/enums.py`): PREDATORY, LEGITIMATE, SUSPICIOUS, UNKNOWN

**EvidenceType** (`src/aletheia_probe/enums.py`): PREDATORY_LIST, LEGITIMATE_LIST, HEURISTIC, QUALITY_INDICATOR

## Working with Models

**Serialization:** Pydantic provides `model_dump()` (to dict), `model_dump_json()` (to JSON), `model_validate_json()` (from JSON).

**Validation:** Automatic validation of required fields, type correctness, constraints (e.g., confidence in 0.0-1.0), and email format. Raises `ValidationError` on invalid data.

## Related Documentation

- [Backend API Reference](backends.md) - Backend interface using these models
- [Extending Guide](extending-guide.md) - Building backends with these models
