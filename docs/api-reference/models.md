# Data Models Reference

Reference for core data models used in journal assessment.

## Overview

All models are defined in `src/aletheia_probe/models.py` using Pydantic for validation and serialization.

## Query Models

### QueryInput

Normalized query input passed to backends.

**Concept:** Contains normalized journal information extracted from user input, including identifiers (ISSN, DOI), alternative names, venue type detection, and acronym expansion tracking.

**Key Fields:**
- `raw_input` - Original user input
- `normalized_name` - Processed journal/conference name
- `identifiers` - Dictionary of ISSN, DOI, etc.
- `aliases` - Alternative names discovered
- `venue_type` - Detected venue classification
- `acronym_expanded_from` - Original acronym if expansion was applied (e.g., "ICSE" → "International Conference on Software Engineering"). Populated when acronym expansion feature resolves conference abbreviations.
- `extracted_acronym_mappings` - Dictionary of acronym-to-full-name mappings discovered during normalization. Tracks what expansions were found and applied.

## Result Models

### BackendResult

Individual backend query result.

**Concept:** Contains assessment from a single backend, including status, confidence score, assessment type, response timing, evidence classification, and execution metrics.

**Key Fields:**
- `backend_name` - Name of the backend that produced this result
- `status` - Query result status (FOUND/NOT_FOUND/ERROR/TIMEOUT/RATE_LIMITED)
- `confidence` - Confidence score (0.0-1.0, validated)
- `assessment` - Assessment classification (predatory/legitimate/suspicious/unknown)
- `response_time` - Query response time in seconds
- `cached` - Whether result was retrieved from cache
- `execution_time_ms` - Backend execution time in milliseconds. Measures actual backend processing time separate from network/cache overhead.
- `evidence_type` - Type of evidence used: "predatory_list", "legitimate_list", or "heuristic". Indicates the source and nature of the assessment evidence.

### AssessmentResult

Final aggregated assessment.

**Concept:** Combines all backend results with weighted scoring, reasoning, metadata, and acronym expansion tracking.

**Key Fields:**
- `assessment` - Final classification (predatory/legitimate/suspicious/insufficient_data)
- `confidence` - Overall confidence score (0.0-1.0)
- `backend_results` - List of individual backend results
- `reasoning` - Human-readable explanations
- `metadata` - Journal metadata if available
- `processing_time` - Total assessment duration
- `acronym_expanded_from` - Original acronym if assessment used acronym expansion (e.g., "ICSE" → full conference name). Tracks when expansion influenced results.
- `acronym_expansion_used` - Boolean indicating whether acronym expansion was applied. Distinguishes direct name queries from acronym-based queries.

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

**Concept:** Extracted venue information from BibTeX entries with comprehensive metadata and retraction status tracking.

**Key Fields:**
- `key` - BibTeX entry key identifier
- `journal_name` - Extracted journal or conference name
- `entry_type` - BibTeX entry type (article, inproceedings, etc.)
- `venue_type` - Detected venue classification (journal/conference/etc.)
- `doi` - Digital Object Identifier if available
- `issn` - International Standard Serial Number if available
- `is_retracted` - Boolean indicating whether the article has been retracted. Determined by checking retraction databases for articles with DOIs.
- `retraction_info` - Dictionary containing retraction details when `is_retracted` is true. Includes retraction reason, date, and source information.

### BibtexAssessmentResult

Aggregated BibTeX file assessment.

**Concept:** Comprehensive statistics and results from assessing all venues in a BibTeX file, with detailed breakdowns by venue type, assessment category, and retraction analysis.

**Key Fields:**
- `total_entries` - Total number of entries processed
- `entries_with_journals` - Number of entries with identifiable venues
- `assessment_results` - List of (entry, assessment) pairs for detailed results
- `predatory_count` / `legitimate_count` / `suspicious_count` - Assessment category counts
- `conference_entries` / `journal_entries` - Venue type breakdowns with specific counters
- `venue_type_counts` - Dictionary mapping venue types to counts
- `retracted_articles_count` - Number of retracted articles discovered. Populated by checking articles with DOIs against retraction databases.
- `articles_checked_for_retraction` - Number of articles that were checked for retraction status. Indicates how many articles had DOIs available for retraction checking.
- `processing_time` - Total assessment duration in seconds

## Enumerations

**VenueType:** JOURNAL, CONFERENCE, WORKSHOP, SYMPOSIUM, PROCEEDINGS, BOOK, PREPRINT, UNKNOWN

**BackendStatus:** FOUND, NOT_FOUND, ERROR, RATE_LIMITED, TIMEOUT

**AssessmentType** (`src/aletheia_probe/enums.py`): Classification results from backend assessments. Core values PREDATORY, LEGITIMATE, SUSPICIOUS, UNKNOWN represent standard assessment outcomes. QUESTIONABLE indicates venues requiring closer scrutiny. QUALITY_INDICATOR represents positive quality signals. HIJACKED identifies legitimate venues compromised by predatory operators. Used by aggregation logic to determine final assessment confidence.

**EvidenceType** (`src/aletheia_probe/enums.py`): PREDATORY_LIST, LEGITIMATE_LIST, HEURISTIC, QUALITY_INDICATOR

**UpdateStatus** (`src/aletheia_probe/enums.py`): Tracks data source synchronization outcomes. SUCCESS indicates completed updates, FAILED represents synchronization errors, SKIPPED shows intentionally bypassed updates, IN_PROGRESS tracks active sync operations, CURRENT indicates data is already up-to-date, ERROR represents unexpected failures. Used by cache systems to manage backend data freshness and sync reliability.

**RiskLevel** (`src/aletheia_probe/enums.py`): Categorizes risk assessment severity for retraction analysis. NONE indicates no risk detected, NOTE represents informational findings, LOW/MODERATE/HIGH represent increasing risk levels, CRITICAL indicates severe risk requiring immediate attention. Used by retraction checking systems to prioritize and classify findings based on severity and impact.

## Working with Models

**Serialization:** Pydantic provides `model_dump()` (to dict), `model_dump_json()` (to JSON), `model_validate_json()` (from JSON).

**Validation:** Automatic validation of required fields, type correctness, constraints (e.g., confidence in 0.0-1.0), and email format. Raises `ValidationError` on invalid data.

## Related Documentation

- [Backend API Reference](backends.md) - Backend interface using these models
- [Extending Guide](extending-guide.md) - Building backends with these models
