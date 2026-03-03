# OpenCitations Local Adapter Requirements

## Purpose
Define requirements for a separate adapter repository that enables `aletheia-probe` to use OpenCitations in two modes:

- `remote` mode (default): current HTTP calls to `api.opencitations.net`
- `local` mode (mass-eval): queries served from locally hosted OpenCitations data

This mirrors the existing OpenAlex strategy (`OPENALEX_MODE=remote|local`).

## Short Answer: PostgreSQL?
Yes. PostgreSQL is a good way to go for the OpenCitations adapter.

Rationale:
- Proven in this ecosystem via OpenAlex local mode.
- Strong indexing and aggregation support for large citation graphs.
- Easy to package in a companion adapter with SQL migrations.
- Lets us precompute venue-level aggregates to keep query latency low.

Note: OpenCitations also distributes OpenLink Virtuoso DB dumps. For Aletheia-Probe needs, PostgreSQL with precomputed tables is simpler to operate.

## Current OpenCitations Dumps (as of 2026-03-03)
Source: `https://download.opencitations.net/`

### OpenCitations Meta (Latest: January 2026, updated 2026-01-20)
- Metadata (CSV): 13 GB compressed (51 GB uncompressed)
- Metadata database (OpenLink Virtuoso): 42 GB compressed (190 GB uncompressed)
- Metadata + provenance (RDF): 48 GB compressed (69 GB uncompressed)
- Provenance database (RDF): 144 GB compressed (1 TB uncompressed)

### OpenCitations Index (Latest: February 2026, updated 2026-02-17)
- Citation data (CSV): TBA on page
- Citation data (N-Triple): TBA on page
- Citation data (Scholix): TBA on page
- Provenance data (CSV): 24 GB compressed (542 GB uncompressed)
- Provenance data (N-Triple): 144 GB compressed (4.5 TB uncompressed)
- Additional: Citation data sources info (N-Triple): 29 GB compressed (480 GB uncompressed)

## Exact Data Needed for Aletheia-Probe
The current backend only needs per-venue metrics for ISSN/eISSN:
- `venue-citation-count/issn:{issn}`
- `venue-reference-count/issn:{issn}`

To reproduce this locally, the adapter needs exactly these logical data elements:

1. Resource-to-venue mapping
- Resource identifier: `resource_omid` (required)
- Venue identifier: `venue_omid` (required)
- Venue ISSN list: `issn` and/or `eissn` (required)

2. Citation edges
- `citing_resource_omid` (required)
- `cited_resource_omid` (required)

3. Optional but recommended metadata
- `snapshot_id` or `snapshot_date` (required for observability)
- `source_collection` (optional: COCI/DOCI/POCI filtering)

From these, compute:
- `venue_reference_count(issn)`: number of outgoing references from resources in venue
- `venue_citation_count(issn)`: number of incoming citations to resources in venue

## Minimal Dataset Choice
For a minimal but correct local adapter:

Mandatory inputs:
- OpenCitations Meta CSV dump (for resource->venue and ISSN linkage)
- OpenCitations Index citation CSV dump (for citing->cited edges)

Not required for adapter v1:
- Provenance dumps
- RDF dumps
- Virtuoso DB dumps
- Source-info dumps

## Why Multiple Datasets Exist
OpenCitations publishes multiple artifacts for different workloads:
- CSV: easiest ETL for relational analytics
- RDF/N-Triple: semantic-web and triplestore workflows
- Virtuoso DB: prebuilt triplestore deployment
- Provenance: lineage/audit data, not needed for venue counts

For Aletheia-Probe adapter v1, CSV is sufficient and lowest complexity.

## Adapter Interface Contract (for aletheia-probe integration)
The adapter package should export:
- `LocalOpenCitationsAdapter` (async context manager)

Required methods:
- `get_venue_citation_count_by_issn(issn: str) -> int | None`
- `get_venue_reference_count_by_issn(issn: str) -> int | None`

Behavior:
- Return `None` for unknown ISSN (equivalent to API 404 semantics)
- Never block on network in local mode
- Raise typed adapter errors for DB/connectivity failures

## Recommended Storage Model (PostgreSQL)
Use a pre-aggregated table for query speed.

### Table: `opencitations_venue_metrics`
Columns:
- `issn TEXT NOT NULL`
- `citation_count BIGINT NOT NULL`
- `reference_count BIGINT NOT NULL`
- `snapshot_date DATE NOT NULL`
- `source TEXT NOT NULL DEFAULT 'opencitations'`

Indexes:
- `PRIMARY KEY (issn, snapshot_date)`
- Index on `(issn)` for latest-snapshot lookup

### Optional mapping tables (if you want traceability)
- `resource_venue_map(resource_omid, venue_omid, issn)`
- `citation_edges(citing_resource_omid, cited_resource_omid)`

In production, keep these optional tables only during build windows if storage is constrained.

## Build Pipeline Requirements
1. Download dumps (Meta CSV + Index CSV)
2. Parse and normalize ISSNs
3. Build resource->ISSN map
4. Stream citation edges and aggregate incoming/outgoing counts by ISSN
5. Upsert into `opencitations_venue_metrics`
6. Publish snapshot metadata (`snapshot_date`, input checksums, row counts)

Pipeline should be resumable and idempotent.

## Runtime and Configuration Requirements
Environment variables (adapter repo):
- `OPENCITATIONS_MODE=remote|local`
- `OPENCITATIONS_LOCAL_DB_DSN` (required in local mode)
- `OPENCITATIONS_LOCAL_SNAPSHOT_DATE` (optional pinning)

In Aletheia-Probe integration phase (later):
- Add OpenCitations client factory analogous to `create_openalex_client()`.
- Keep remote mode as default.

## Reliability Requirements
- p95 local lookup latency < 50 ms per count query
- No network dependency in local mode
- Graceful partial behavior in hybrid mode (optional):
  - if one metric missing, return available metric with reduced confidence

## Acceptance Criteria (Adapter Repo)
1. Given ISSN `0149-5992`, adapter returns integer citation/reference counts from local DB.
2. Unknown ISSN returns `None` without exception.
3. A full refresh can rebuild snapshot deterministically from the same input dumps.
4. Integration test validates counts for at least 20 known ISSNs.
5. Adapter package can be installed independently (optional dependency model).

## Open Questions for Implementation Repo
1. Snapshot cadence: monthly vs quarterly?
2. Keep full edge tables after aggregation or discard to save disk?
3. Single snapshot only vs multi-snapshot historical table?
4. Do we need source-level filtering (COCI/DOCI/POCI) in v1?

## References
- OpenCitations download portal: `https://download.opencitations.net/`
- OpenCitations Index API docs: `https://api.opencitations.net/index/v2`
- Existing OpenAlex local-mode pattern in this repo:
  - `docs/local-openalex-backend.md`
  - `src/aletheia_probe/openalex.py` (`create_openalex_client`)
