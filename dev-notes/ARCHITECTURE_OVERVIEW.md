# Aletheia-Probe Architecture Overview

**Project:** Aletheia-Probe - Journal and Conference Assessment Tool
**Last Updated:** 2026-01-05
**Status:** High-Level Architecture Guide

This document provides a high-level overview of the Aletheia-Probe system architecture, describing the main building blocks and their interactions.

---

## System Purpose

Aletheia-Probe assesses academic journals and conferences by aggregating evidence from multiple authoritative sources and pattern analysis engines. It combines curated predatory/legitimate lists with evidence-based heuristics to produce confidence-scored assessments.

---

## Architectural Building Blocks

### 1. CLI Interface Layer
**Responsibility:** User interaction and command routing

The CLI layer exposes journal assessment, BibTeX batch processing, cache synchronization, and status reporting commands. It handles argument parsing, output formatting, and error presentation to users.

### 2. Input Normalization Layer
**Responsibility:** Query standardization and preprocessing

Transforms raw user input into normalized query structures. Expands acronyms, detects venue types (journal vs. conference), generates name variants, and extracts identifiers (ISSN, DOI). Maintains an acronym cache for consistent expansion.

### 3. Query Orchestration Layer
**Responsibility:** Multi-source query coordination and aggregation

The dispatcher coordinates parallel queries across all enabled backends, applies timeout controls, aggregates results using weighted voting, and produces confidence-scored assessments. Implements cross-validation to detect and resolve conflicting evidence.

### 4. Backend Abstraction Layer
**Responsibility:** Uniform interface to heterogeneous data sources

Provides a protocol-based abstraction over diverse assessment sources. Each backend implements a common interface for querying journal status, returning standardized results with assessment type, confidence, and evidence metadata. Backends are registered in a central factory-based registry.

### 5. Data Source Integration Layer
**Responsibility:** External data acquisition and parsing

Fetches and parses data from external sources including curated lists, API services, and downloadable datasets. Handles format diversity (JSON, Excel, ZIP, PDF, HTML) and maintains update timestamps. Implements retry logic and error handling for network operations.

### 6. Cache and Persistence Layer
**Responsibility:** Data storage and query optimization

SQLite-based persistence for journal metadata, source assessments, and query results. Multi-tier caching strategy with in-memory caches for hot data and persistent caches with TTL-based expiration. Implements normalized schema to eliminate redundancy.

### 7. Evidence Analysis Layer
**Responsibility:** Pattern detection and quality assessment

Analyzes publication patterns, citation metrics, metadata completeness, and growth trajectories. Processes large-scale datasets to identify suspicious patterns. Generates evidence scores based on configurable heuristics.

### 8. Output Formatting Layer
**Responsibility:** Result presentation and serialization

Transforms assessment results into user-requested formats (text, JSON, YAML). Generates human-readable explanations, detailed reasoning chains, and machine-parseable structured output. Provides verbose modes for debugging and transparency.

---

## Data Flow Architecture

```
┌─────────────┐
│  User Input │
└──────┬──────┘
       │
       ▼
┌──────────────────────┐
│ Input Normalization  │  ← Acronym Cache
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│ Query Orchestration  │
└──────┬───────────────┘
       │
       ├─────────────────────────┬────────────────┬──────────────┐
       ▼                         ▼                ▼              ▼
┌──────────────┐      ┌───────────────┐   ┌──────────────┐  [...]
│ Curated List │      │ API Analyzer  │   │ Pattern      │
│ Backends     │      │ Backends      │   │ Heuristics   │
│              │      │               │   │              │
│ • DOAJ       │      │ • OpenAlex    │   │ • Crossref   │
│ • Beall's    │      │ • Scopus      │   │ • Retraction │
│ • Kscien     │      │               │   │   Watch      │
└──────┬───────┘      └───────┬───────┘   └──────┬───────┘
       │                      │                   │
       └──────────┬───────────┴───────────────────┘
                  │
                  ▼
       ┌──────────────────────┐
       │  Cross-Validation    │
       └──────┬───────────────┘
              │
              ▼
       ┌──────────────────────┐
       │ Evidence Aggregation │
       │ & Confidence Scoring │
       └──────┬───────────────┘
              │
              ▼
       ┌──────────────────────┐
       │  Output Formatting   │
       └──────┬───────────────┘
              │
              ▼
       ┌─────────────┐
       │ User Output │
       └─────────────┘
```

### Data Persistence Flow

```
┌──────────────────┐
│ External Sources │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Data Sync Engine │
└────────┬─────────┘
         │
         ▼
┌──────────────────────────┐
│ SQLite Database          │
│                          │
│ • journals               │
│ • journal_names          │
│ • source_assessments     │
│ • retraction_statistics  │
│ • assessment_cache       │
└────────┬─────────────────┘
         │
         ▼
┌──────────────────┐
│ In-Memory Caches │
│                  │
│ • Journal Cache  │
│ • OpenAlex Cache │
│ • Acronym Cache  │
└──────────────────┘
```

---

## Key Architectural Patterns

### Protocol-Based Abstraction
Backends implement runtime-checkable protocols rather than inheriting from rigid base classes. This enables duck-typed composition, flexible testing with mocks, and decoupling between backend logic and synchronization concerns.

### Registry Pattern
A centralized BackendRegistry serves as the single factory for backend instantiation, discovery, and lifecycle management. Configuration-driven backend enabling/disabled and runtime backend iteration support dynamic system composition.

### Concurrent Query Execution
All backend queries execute in parallel using asynchronous I/O. Timeout controls prevent slow backends from blocking assessment. Results aggregate incrementally as backends complete.

### Weighted Evidence Aggregation
Assessment confidence derives from weighted voting across backend results. Curated lists receive higher weight than heuristics. Agreement bonuses increase confidence when multiple independent sources concur. Conflict resolution uses source authority hierarchies.

### Multi-Tier Caching
Hot data resides in memory (journal lookups, acronym mappings). Warm data persists in SQLite with TTL expiration (assessment results, pattern analysis). Cold data syncs periodically from external sources. Cache invalidation occurs on source updates.

### Lazy Initialization
Backends instantiate their data sources on-demand to avoid circular dependencies and reduce startup overhead. Configuration loads incrementally as features activate. Database connections pool and reuse.

### Normalized Data Schema
Journal information normalizes to eliminate redundancy: canonical names separate from aliases, ISSNs normalize to hyphenated format, URLs deduplicate with discovery timestamps. Source assessments link journals to authoritative lists via many-to-many relationships.

### Standalone Function Composition
Synchronization utilities operate as stateless functions rather than singletons. Dependencies inject explicitly (database writer, data source) to enable testing and parallel execution. No global state or hidden coupling.

---

## Backend Categories

### Curated List Backends
Query pre-compiled authoritative lists of predatory or legitimate journals. High confidence, binary assessments (present/absent). Examples: DOAJ (legitimate), Beall's List (predatory), Kscien databases (predatory/hijacked).

### API Analyzer Backends
Query external APIs for real-time pattern analysis. Variable confidence based on evidence strength. Examples: OpenAlex (publication patterns), Crossref (metadata quality).

### Local Database Backends
Query SQLite for cached source data. Fast, offline-capable assessments. Require periodic synchronization with external sources.

### Heuristic Backends
Apply algorithmic rules to detect suspicious patterns. Configurable thresholds and scoring functions. Examples: retraction rate analysis, citation distribution analysis.

---

## Cross-Cutting Concerns

### Configuration Management
YAML-based configuration defines backend weights, timeouts, cache settings, API credentials, and heuristic thresholds. Layered configuration supports defaults with per-backend overrides.

### Error Handling
Backends fail independently without blocking overall assessment. Timeout errors, network failures, and parsing errors generate ERROR status results. Partial results still produce assessments with reduced confidence.

### Logging
Dual-logger system separates user-facing status messages from detailed diagnostic logs. Status logger provides progress feedback during long operations. Detail logger captures backend responses for debugging.

### Extensibility
New backends integrate by implementing the Backend protocol and registering in the BackendRegistry. New data sources extend the DataSource abstract class. No modification of core orchestration logic required.

### Testing
Unit tests validate individual backend behavior with mocked data sources. Integration tests verify end-to-end assessment flows. Fixtures provide reproducible test data.

---

## Performance Characteristics

### Scalability
Concurrent backend queries achieve near-linear speedup with backend count. Database indexes optimize journal lookups by name and ISSN. In-memory caching eliminates redundant database queries within a session.

### Response Time
Typical single journal assessment: 2-5 seconds (parallel queries with 10-second timeout). BibTeX batch processing: linear in entry count with parallel backend queries per entry. Cache hits: <100ms.

### Resource Usage
SQLite database size: proportional to unique journal count across all sources (~50MB for 50K journals). Memory footprint: <200MB with full cache population. Network bandwidth: dominated by initial source synchronization.

---

## Security and Privacy

### Data Handling
No user tracking or telemetry. Local-only data storage. API queries include user-provided email for identification (Crossref, OpenAlex) but no personal data collection.

### Input Validation
Input normalization sanitizes journal names to prevent injection attacks. ISSN format validation prevents malformed queries. URL parsing validates schemes and domains.

### External Dependencies
Minimal dependency footprint. All external libraries audited for known vulnerabilities. Data sources fetched over HTTPS with certificate validation.
