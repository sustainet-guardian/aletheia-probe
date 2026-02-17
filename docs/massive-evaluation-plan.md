# Massive Evaluation Plan (100,000+ BibTeX Files)

## Purpose
This document captures the agreed preconditions and implementation plan for a statistically robust large-scale run over 100,000+ BibTeX files.

It is intended to be reusable across sessions.

---

## Validation of Key Requirements

1. JSON-first output for post-processing is valid.
- Keep full per-entry JSON output so statistics can be computed later without rerunning assessments.
- This supports questions like: "How many references hit Beall's list?", "How many are suspicious?", "How many are contradictory?"

2. Two-step cache strategy is valid.
- Assessment outcomes can change when caches become richer (identifier and acronym mappings, API-derived metadata).
- Use separate phases:
  - Phase A: cache collection/warm-up
  - Phase B: final assessment on warmed caches

3. Retry-forever mode is valid (with controlled backoff).
- For very large runs, transient API failures/rate limits should not terminate the run.
- Use wait-and-retry behavior for rate-limited/transient failures.

4. Resume-after-interruption is mandatory.
- Long runs need durable checkpointing and restart support.
- A power outage must not lose overall progress.

---

## What to Implement Before the Huge Run

## 1) New Massive Workflow Command
Add a dedicated command (e.g. `mass-eval`) with deterministic multi-file processing.

Required capabilities:
- Input directory traversal for `*.bib` (recursive)
- Stable file ordering
- Optional sharding/slicing for distributed execution

## 2) Two-Phase Execution Model

### Phase A: `collect` (cache warm-up)
Goal: populate caches, not final classification.

Actions:
- Parse all files and entries
- Normalize venue names and identifiers
- Trigger acronym/ISSN/name enrichment
- Trigger API-backed cache population used by analyzers

Output:
- Run metadata and progress records
- Optional lightweight per-entry collection log

### Phase B: `assess` (final run)
Goal: run classification with already warmed caches.

Actions:
- Execute full assessment pipeline
- Write per-entry JSON output suitable for downstream statistical analysis

Output:
- JSONL (one JSON object per processed entry) to support incremental appends and resume

---

## 3) Output Schema Requirements (JSON/JSONL)
Each output record should include at least:
- `run_id`
- `file_path`
- `entry_key`
- `venue_raw`
- `venue_normalized`
- `venue_type`
- `issn`, `eissn`, `doi` (if available)
- `final_assessment`
- `confidence`
- `overall_score`
- `backend_results` (status + assessment + confidence per backend)
- `predatory_list_hits` (derived)
- `legitimate_list_hits` (derived)
- `heuristic_predatory_votes` (derived)
- `heuristic_legitimate_votes` (derived)
- `has_conflict` (derived)
- `is_suspicious` (derived)
- `processing_timestamp`

This preserves full flexibility for later statistics.

---

## 4) Contradiction and Suspicious Tracking
Explicitly persist indicators used for analysis:
- Contradiction signal:
  - `has_conflict = true` when predatory and legitimate evidence both exist
- Suspicious signal:
  - `final_assessment == suspicious`
- Evidence tallies:
  - number of predatory-list hits
  - number of legitimate-list hits
  - number of heuristic votes by polarity

---

## 5) Retry-Forever Mode
Implement opt-in mode for both `collect` and `assess`.

Behavior:
- On rate limit/transient network error: retry indefinitely
- Use bounded exponential backoff + jitter
- Log retry reason and next retry time
- Persist retry state in run database so restart continues correctly

Non-transient errors should be recorded and classified separately.

---

## 6) Durable Progress + Resume
Use persistent run-state storage (SQLite) for long-run safety.

Minimum tables/entities:
- Run metadata (`run_id`, mode, started_at, config snapshot)
- File progress (`pending`, `in_progress`, `done`, `failed`)
- Entry progress (`pending`, `done`, `error`, retry metadata)
- Output write index (to prevent duplicates on resume)

Checkpoint behavior:
- Flush progress at least every N entries or every 2 minutes
- On restart, continue unfinished items only

---

## 7) Reproducibility Metadata
Persist manifest-level context:
- Enabled backends and their weights/timeouts
- Heuristic settings
- Cache/data-source "as of" timestamps
- Code version (git commit hash if available)
- Run mode (`collect`/`assess`)

This is required for defensible statistics.

---

## 8) Post-Processing Tool
Add a dedicated analysis script/command that reads JSONL outputs and computes:
- counts by final assessment (predatory/suspicious/legitimate/unknown)
- counts by backend list hit (e.g. Beall's)
- contradiction counts and rates
- per-backend error/rate-limit incidence
- optional stratification by venue type

This separates execution from statistical analysis cleanly.

---

## 9) Suggested Rollout Sequence

1. Implement run-state storage + resume engine
2. Implement `collect` mode with retry-forever support
3. Implement `assess` mode JSONL writer (idempotent on resume)
4. Add contradiction/suspicious derived fields
5. Add post-processing statistics tool
6. Validate on small/medium sample before full 100k+ run

---

## Operational Recommendation
Before the full production-scale run:
1. Execute `collect` on a representative subset and verify cache growth + retry behavior.
2. Execute `assess` on the same subset and validate contradiction/suspicious statistics.
3. Freeze config and backend set.
4. Run full `collect` then full `assess` with resume enabled.
