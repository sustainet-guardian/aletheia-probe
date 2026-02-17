# Wikidata Integration Assessment for Aletheia-Probe

## Context

This assessment evaluates whether integrating [Wikidata](https://www.wikidata.org/) data into aletheia-probe would provide meaningful value for the tool's core mission of detecting predatory journals and conferences.

**What is Wikidata?**

Wikidata is the free, collaborative, multilingual knowledge graph maintained by the Wikimedia Foundation. It serves as a central repository of structured data for Wikipedia and all other Wikimedia projects. Every entity (item) has a unique Q-identifier, every property has a P-identifier, and all statements are machine-readable and queryable via SPARQL. The scholarly publishing domain is one of Wikidata's most densely populated areas: as of early 2025, scholarly articles alone account for approximately 37–41 million Wikidata items and roughly 50% of all triples in the graph (~6.4 billion triples).

**Current Coverage (February 2026):**

- ~1.1 billion total triples in the main (non-scholarly) Wikidata graph
- ~37–41 million scholarly article items (in dedicated scholarly graph since May 2025)
- Tens of thousands of journal and publisher entities in the main graph (exact count requires live SPARQL; 2021 analysis found ~50,000–70,000 journal-type entities with ISSNs)
- Supported by the WikiCite and WikiProject Periodicals community efforts
- Continuously updated by volunteers, bots, and automated imports

**Data Access:**

- **SPARQL endpoints** (free, no authentication required):
  - Main graph (journals, publishers, concepts): `https://query.wikidata.org/`
  - Scholarly articles subgraph (post May 2025 split): `https://query-scholarly.wikidata.org/`
  - Federation required for cross-graph queries
- **REST API** for single-entity lookup: `https://www.wikidata.org/wiki/Special:EntityData/Q{id}.json`
- **Bulk dumps**: JSON and RDF formats at `https://dumps.wikimedia.org/wikidatawiki/` (full dump ~100 GB compressed; journal-only subset manageable)
- **License**: CC0 (public domain) — commercial use explicitly allowed, no attribution required
- **Rate limits**: 60-second query timeout, 5 concurrent queries per IP, HTTP 429 on throttle; `User-Agent` header required to avoid blocking

**Key Properties Relevant to Journal and Publisher Assessment:**

| Property | Identifier | Description |
|----------|-----------|-------------|
| ISSN | P236 | International Standard Serial Number |
| ISSN-L | P7363 | Linking ISSN |
| publisher | P123 | Publisher of a journal |
| inception | P571 | Founding/launch date |
| dissolved, abolished or demolished | P576 | End date |
| instance of | P31 | Classification (Q737498 = academic journal, Q5633421 = scientific journal) |
| DOAJ journal ID | P5115 | Cross-reference to DOAJ |
| Crossref journal ID | P8375 | Cross-reference to Crossref |
| NLM unique ID | P628 | Cross-reference to NLM Catalog |
| Scopus EID | P1156 | Cross-reference to Scopus |
| country of origin | P495 | Country where journal is published |
| language of work | P407 | Publication language |
| subject matter | P921 | Academic subject areas |
| official website | P856 | Publisher/journal website |
| named after | P138 | For disambiguation of namesakes |
| followed by / follows | P156/P155 | Journal succession relationships |
| owner of | P1830 / subsidiary | Publisher portfolio relationships |

**WDQS Infrastructure Change (May 2025):**

A critical operational change affects any future integration: on 9 May 2025, the Wikidata Query Service was split into two separate SPARQL graphs. Journal entities and publisher entities reside in the **main graph** (`query.wikidata.org`). Scholarly articles reside in the **scholarly graph** (`query-scholarly.wikidata.org`). Any query combining journal metadata with article counts requires SPARQL federation, significantly increasing implementation and query complexity. The legacy full-graph endpoint (`query-legacy-full.wikidata.org`) was deprecated and scheduled for removal in December 2025.

---

## Deep Analysis: Pros and Cons

### Pros

#### 1. **Publisher Name Disambiguation and Fuzzy Matching**

This is Wikidata's most genuinely unique capability for aletheia-probe's use case.

Publisher names in the wild are notoriously inconsistent: "Elsevier B.V.", "Elsevier Science", "Reed Elsevier", "Elsevier Ltd." all refer to the same publisher. Wikidata stores:
- Primary English label
- Aliases in dozens of languages and historical name variants
- Former names (P1448) and name changes over time
- Successor/predecessor relationships for merged publishers (P1365/P1366)

This means a SPARQL query looking up "Springer Verlag" would correctly resolve to the Springer Nature entity and its full alias list. **No other free data source provides this cross-lingual, historically-anchored publisher name normalization at scale.** This could improve match rates across all existing backends (Beall's List, Crossref, OpenAlex) that currently rely on string normalization.

#### 2. **Publisher Historical Anchoring**

Wikidata's `inception` (P571) property allows verification of when a publisher was actually founded. Combined with `dissolved` (P576), this enables detection of temporal inconsistencies:

- Publisher claims "established 1987" but Wikidata inception shows 2019 → suspicious
- Publisher entity created in Wikidata in 2022 with no historical edits → very new, no track record
- Publisher marked as dissolved but still soliciting submissions → possible zombie publisher

This is a genuinely new signal not available from existing backends. It requires Wikidata to have the publisher entity (major publishers only), but for large predatory publishers (e.g., OMICS International, Hindawi before acquisition) this data is available.

#### 3. **Cross-Identifier Consistency Checking**

Wikidata links multiple external identifiers for the same journal entity:
- P236 (ISSN) + P5115 (DOAJ ID) + P8375 (Crossref ID) + P628 (NLM ID) + P1156 (Scopus EID)

A journal that claims to be in DOAJ but the DOAJ ID on Wikidata is absent or mismatched could signal an inconsistency worth investigating. Similarly, ISSN mismatches between what a journal claims and what Wikidata records can reveal ISSN fraud (predatory journals sometimes claim ISSNs of legitimate journals).

**Caveat**: This requires Wikidata data to be correct, which is not guaranteed for all journals.

#### 4. **Entity Existence as a Soft Crowd-Whitelist Signal — and a Rare but High-Value Blacklist Signal**

Wikidata's notability threshold requires at least one verifiable reference. For academic journals, being listed in Wikidata implies the journal has been noticed and documented by at least one Wikimedia volunteer. While this is a very soft signal, it provides:

- **De-facto crowd whitelist** for established journals: Major journals (Nature, Science, PLOS ONE, etc.) have rich Wikidata entries with extensive metadata
- **Publisher portfolio verification**: A publisher with 50+ journal entities on Wikidata is likely established; a publisher with no Wikidata entity is either very new or very obscure

The key distinction from other lists (DOAJ, Beall's): **Wikidata does not claim to be a quality filter.** Presence means notability-by-some-measure, not legitimacy. Even well-documented predatory publishers like OMICS International have Wikidata entries.

**Exception — explicit predatory typing (rare, high value):**

Wikidata has dedicated item classes:
- **Q65770378** — `predatory journal` (the concept item, but also usable as a P31 value)
- **Q65770389** — `predatory publisher`
- **Q56273878** — `Beall's list of predatory open access journals` (as a subject reference)

A journal item typed `instance of (P31) = Q65770378` is a **high-confidence negative signal** — it means the Wikidata community has explicitly classified it as predatory. However, **coverage is extremely sparse**: there is no systematic import of Beall's list, Cabell's, or any other predatory journal database into Wikidata as structured data. Only a handful of high-profile cases (journals that received Wikipedia articles due to media coverage) carry this typing. This signal should be treated as: *"if present, strong negative; if absent, completely neutral."*

```sparql
# Check if a journal has been explicitly classified as predatory in Wikidata
ASK {
  ?journal wdt:P236 "1234-5678" .          # lookup by ISSN
  { ?journal wdt:P31 wd:Q65770378 . }      # instance of: predatory journal
  UNION
  { ?journal wdt:P123 ?publisher .
    ?publisher wdt:P31 wd:Q65770389 . }    # publisher is a predatory publisher
}
```

#### 5. **Knowledge Graph Context for Conferences**

Unlike most scholarly data sources that focus on journals, Wikidata has entities for academic conferences (Q2020153), conference series (Q47258130), and conference proceedings. This means Wikidata could potentially provide entity matching and publisher disambiguation for **conference assessment** — a gap in the current backend landscape. The WikiProject Academic Conferences exists within Wikidata.

#### 6. **Free, Stable, Long-term Open Data**

CC0 license eliminates all legal and licensing risk. Wikidata is maintained by the Wikimedia Foundation with indefinite commitment. No API keys, no usage quotas for reasonable use, no commercial restrictions. Bulk dumps provide a stable offline copy. This stability profile is superior to commercial sources and even some community sources.

#### 7. **Integration with the Broader Linked Open Data Ecosystem**

Wikidata is the hub of scholarly linked open data: OpenAlex uses 65,000 Wikidata concepts, OCLC Meridian (2024) provides APIs linking WorldCat entries to Wikidata entities, and Crossref collaborates on publisher identifier mapping. If aletheia-probe integrates Wikidata, it positions well for future interoperability with SPARQL-based scholarly infrastructure.

---

### Cons

#### 1. **Not a Quality Database — No Curated Blacklist**

**Critical limitation**: Wikidata's inclusion criterion is **notability**, not quality. There is no systematic Wikidata effort to flag or exclude predatory journals. Predatory publishers that have achieved notoriety (OMICS International, Bentham Science when it had quality issues, etc.) DO have Wikidata entities.

This means:
- **Presence in Wikidata ≠ legitimate** (predatory journals can and do appear)
- **Absence from Wikidata ≠ predatory** (many excellent regional journals are absent)
- Wikidata provides **zero direct predatory signal**

The user's framing — "De-facto Crowd-Whitelist" and "Heuristik-Datenbasis" — is the right mental model. Wikidata is a consistency-checking and context-enrichment tool, not a ground-truth quality filter.

#### 2. **Absence is Meaningless for Assessment**

For a tool that answers "Is this journal predatory?", the answer "Not found in Wikidata" provides no useful information. Thousands of legitimate regional journals, newer venues, and specialist publications lack Wikidata entries. This severely limits the tool's utility: for the most dangerous queries (newly-launched predatory journals), Wikidata returns nothing.

**Estimated coverage for aletheia-probe queries:**
- Major established journals (Nature, Lancet, PLOS ONE): Near 100% in Wikidata
- Mid-tier journals (Scopus-indexed): ~50-70% in Wikidata
- DOAJ-listed OA journals: ~30-50% in Wikidata
- Regional/national specialty journals: ~10-30% in Wikidata
- Newly-launched journals (2020+, any type): ~5-15% in Wikidata
- Predatory journals (active, recent): ~3-10% in Wikidata (only famous ones)
- Conference proceedings: ~20-40% (major conferences only)

**Estimated overall query coverage: 30-50% would find any Wikidata entity; perhaps 15-25% would find data useful enough to generate a non-trivial signal.**

#### 3. **Data Quality and Reliability Risks**

Wikidata is edited by anyone. While:
- SHACL/SPARQL property constraints catch some errors
- Anti-vandalism bots (ORES, ML-based) detect most deliberate vandalism (ROC-AUC 0.991)
- The community actively monitors high-traffic items

For journal/publisher data specifically:
- **ISSN values can be wrong or outdated** (journal merges, ISSN-L not always maintained)
- **Inception dates** are often missing or approximate
- **Publisher relationships** (subsidiary, parent, successor) are inconsistently maintained
- **Indexing status claims** (e.g., "indexed in PubMed") are almost never updated when journals are de-indexed

Using Wikidata data as authoritative source for fraud detection would be risky. Using it as a soft, secondary signal is more appropriate.

#### 4. **SPARQL Complexity and Infrastructure Instability**

The May 2025 graph split fundamentally changes integration strategy:

- **Simple journal-entity lookup** (does this ISSN resolve to a Wikidata item?): Feasible, main graph only
- **Publisher disambiguation queries**: Feasible, main graph only
- **"How many articles has this journal published?"**: Requires federation across both endpoints
- **Any cross-graph query**: Complex federation SPARQL, higher latency, two endpoints to maintain

Post-split, implementing a reliable SPARQL-based backend requires handling:
1. Query routing (main vs. scholarly vs. federated)
2. Federation timeout risks (federated queries can cascade-fail)
3. Two distinct rate-limit contexts
4. Infrastructure changes (the split itself was a breaking change with minimal migration time)

This complexity is qualitatively different from, say, the NLM Catalog API integration (single, stable endpoint) or OpenAlex (well-documented versioned API).

#### 5. **SPARQL Rate Limits Incompatible with High-Throughput Use**

The 60-second query timeout and 5 concurrent queries per IP hard ceiling means:
- Batch processing is impractical without caching
- A 500ms SPARQL lookup per assessment adds visible latency
- Queries that time out during complex federation provide no graceful fallback

For aletheia-probe's interactive use case, SPARQL queries to Wikidata would need to be:
1. Carefully designed to be fast (index-friendly patterns, avoid expensive traversals)
2. Cached aggressively (response caching layer)
3. Treated as non-critical (graceful degradation when unavailable)

#### 6. **Impact Factor Data Is Sparse and Unreliable**

Wikidata does have some impact factor data (stored as point-in-time values on journal items), but:
- Coverage is estimated at <20% of journals with any IF data
- The data is often years out of date (IFs change annually)
- Predatory journals sometimes falsely report IFs on their websites, and this misinformation can propagate to Wikidata
- No systematic bot or project maintains current IF values across all journals

Wikidata's IF data should **not** be used as a detection signal without cross-validation.

#### 7. **Indexing Status Claims Are Not Curated**

Some Wikidata journal items have statements like "indexed in Scopus" or "indexed in PubMed." However:
- These claims are added by volunteers and not automatically updated
- When journals are de-indexed (common for journals that improve quality or decline), Wikidata often retains the stale claim
- No systematic project maintains indexing status currency
- For predatory journal detection (where false indexing claims are the key fraud), stale data creates false negatives

This makes Wikidata **strictly worse** than NLM Catalog (for MEDLINE claims) or DOAJ (for OA status) for indexing verification — those sources are authoritative and maintained by the indexers themselves.

#### 8. **Conference Data Underdeveloped for Predatory Detection**

While Wikidata has conference entities, coverage for the predatory/spam conference space is sparse. WikiProject Academic Conferences has focused on notable venues (ACM, IEEE, Springer LNCS proceedings). Predatory conferences (often named with deliberately vague, prestigious-sounding titles) are unlikely to have accurate Wikidata entries.

---

## Integration Effort Estimate

**Medium Effort: 3–5 developer days** for a basic SPARQL-based backend; more if caching layer is included.

### Breakdown

#### Day 1: Backend Architecture Decision and SPARQL Design

The post-2025 infrastructure split requires a fundamental design decision:

**Option A: Simple Entity Lookup Only (recommended if pursued)**
- Query the main graph only: Lookup journal/publisher by ISSN or name
- Return: entity exists (yes/no), publisher name canonical form, publisher inception date
- **No federation required**
- Queries typically complete in <1 second

**Option B: Full SPARQL with Article Counts and Cross-Source Links**
- Federation queries across main + scholarly graphs
- Much higher implementation complexity
- Query latency 5-30 seconds for federated queries
- **Not recommended**

For Option A:

```sparql
# Lookup journal by ISSN
SELECT ?journal ?journalLabel ?publisher ?publisherLabel ?inception WHERE {
  ?journal wdt:P236 "1234-5678" .  # ISSN
  OPTIONAL { ?journal wdt:P123 ?publisher . }
  OPTIONAL { ?journal wdt:P571 ?inception . }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en" . }
}
LIMIT 5
```

```sparql
# Publisher disambiguation: find canonical name + aliases
SELECT ?publisher ?publisherLabel ?alias ?inception WHERE {
  ?publisher wdt:P31/wdt:P279* wd:Q2085381 .  # instance of publisher
  { ?publisher wdt:P1448 ?alias }              # former names
  UNION
  { ?publisher skos:altLabel ?alias . FILTER(LANG(?alias) = "en") }
  ?publisher wdt:P571 ?inception .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en" . }
}
```

#### Day 2: Backend Implementation

**File:** `src/aletheia_probe/backends/wikidata_backend.py`

- Create `WikidataBackend` extending `OnlineBackend`
- Implement SPARQL query via aiohttp to `https://query.wikidata.org/sparql`
- Set descriptive `User-Agent` header (required by Wikidata ToS)
- Implement retry logic with exponential backoff for HTTP 429
- Query by ISSN first (P236), fall back to normalized journal title
- Return `BackendResult` with:
  - Assessment: `QUALITY_INDICATOR` (never `LEGITIMATE` or `PREDATORY` — see reasoning below)
  - Publisher canonical name, aliases, inception date
  - Cross-identifier links (DOAJ ID, Crossref ID) if available

#### Day 3: Publisher Name Disambiguation Utility

This is the highest-value output: a standalone utility function `resolve_publisher_name()` that queries Wikidata to canonicalize publisher names. This could be used internally by other backends (Beall's List string matching, Crossref publisher normalization) to improve their match rates.

```python
async def resolve_publisher_name(name: str) -> list[str]:
    """Return canonical name + known aliases for a publisher.

    Uses Wikidata alias lookup. Returns empty list if not found.
    Useful for fuzzy-matching improvements in other backends.
    """
```

#### Days 4–5: Caching, Testing, Documentation

- **Local cache mandatory**: SPARQL queries must be cached to avoid rate-limiting
  - Cache hit: ~0ms latency
  - Cache miss: ~500ms–3s for SPARQL query
  - Recommended TTL: 7 days (Wikidata journal data changes slowly)
- Unit tests: Mock SPARQL responses for entity found/not found
- Integration tests: Live API calls (rate-limited test suite)
- Documentation: `dev-notes/integration/wikidata.md`

### Database Impact

If using query-time API (no dump sync): No database changes needed. Optional cache table:

```sql
CREATE TABLE wikidata_cache (
    query_key TEXT PRIMARY KEY,    -- hash of ISSN or publisher name
    result_json TEXT,              -- serialized WikidataResult
    cached_at TIMESTAMP,
    ttl_days INTEGER DEFAULT 7
);
```

If using bulk dump (journal entities only):
- Filter JSON dump for `instance of` (P31) = Q737498/Q5633421 and subclasses
- Estimated filtered size: ~1–3 GB (tens of thousands of journal items)
- Additional ~500 MB for publisher entities
- Significant one-time processing; monthly sync

### Recommended Approach: Query-time API (not dump sync)

Wikidata's journal coverage is too sparse and too slowly changing to justify bulk sync. Query-time lookup with caching provides the same effective performance at much lower operational cost.

---

## Expected Coverage and Benefit Rate

### Coverage Analysis

| Query Type | Wikidata Coverage | Estimated % of aletheia-probe Queries |
|------------|------------------|---------------------------------------|
| Major established journals (Nature, PLOS ONE, etc.) | ~95% | 10% |
| Mid-tier indexed journals | ~50-65% | 25% |
| Regional OA journals | ~20-35% | 20% |
| Computer science conferences | ~40-60% (major only) | 10% |
| Predatory journals (active) | ~5-15% | 15% |
| Newly-launched journals (2020+) | ~5-15% | 10% |
| Conference proceedings (general) | ~20-30% | 10% |

**Estimated overall entity-found rate: ~35-45% of queries**

### Benefit Rate Analysis

Of the ~35-45% that find a Wikidata entity:

**High benefit (publisher disambiguation):**
- Journal's publisher name normalized and canonicalized → helps Beall's/Crossref matching → ~8-12% of all queries
- This is **indirect** benefit through improving other backends, not a standalone signal

**Medium benefit (publisher historical check):**
- Publisher inception date verifiable → detects temporal inconsistencies → ~3-5% of all queries
- Only applies when publisher has Wikidata entity AND has inception date stored

**Low benefit (cross-identifier check):**
- DOAJ ID / Crossref ID cross-validation → ~5-8% of all queries
- Only useful when Wikidata has the external ID AND it contradicts other sources

**No benefit (entity exists but adds nothing new):**
- Entity exists but data duplicates what Crossref/OpenAlex already return → ~20-25% of all queries

**No benefit (entity not found):**
- ~55-65% of queries → completely neutral result

**Net unique high-value benefit: ~11-17% of queries** (mainly publisher disambiguation + historical check)

This means **83-89% of queries** get no unique information from Wikidata that couldn't be obtained elsewhere.

### Comparison to Other Backends

| Backend | Coverage | Direct Predatory Signal | Unique Value |
|---------|----------|------------------------|--------------|
| DOAJ | 22,000 journals | High (legitimacy list) | OA journal whitelist |
| Beall's List | 2,900 entries | High (predatory list) | Explicit blacklist |
| OpenAlex Analyzer | 240M works | High (pattern analysis) | Citation/volume patterns |
| NLM Catalog | 5,600 MEDLINE | Medium (fraud detection) | MEDLINE verification |
| **Wikidata** | **35-45% query hit rate** | **Zero (no quality filter)** | **Publisher disambiguation, historical anchoring** |

---

## Critical Assessment: Alignment with Mission

### Aletheia-Probe's Core Mission

From README.md:
> "A command-line tool for evaluating the **legitimacy** of academic journals and conferences. By aggregating data from authoritative sources and applying advanced pattern analysis, it helps researchers, librarians, and institutions **detect predatory venues** and ensure the integrity of scholarly publishing."

### How Wikidata Relates

**What Wikidata provides:**
- Publisher name canonicalization and disambiguation
- Publisher historical anchoring (inception dates)
- Cross-identifier consistency checking
- Entity existence as a very soft notability signal
- Linked open data context for knowledge graph integration

**What Wikidata does NOT provide:**
- Any direct predatory journal signal (no blacklist)
- Reliable indexing status (stale crowdsourced data)
- Quality metrics (impact factor data sparse and unreliable)
- Coverage for the most dangerous queries (new/predatory journals)
- Conference blacklist or quality assessment

### Mission Alignment Score: **Moderate-Low (4/10)**

**Aligned aspects:**
- Publisher disambiguation helps improve signal quality across all backends
- Publisher historical anchoring is a novel (if weak) fraud signal
- Knowledge graph integration supports future research tool development
- Zero licensing risk, long-term stable

**Misaligned aspects:**
- **No direct predatory detection capability**: The core mission requirement is unaddressed
- **Absence is uninformative**: The most important queries (new suspicious venues) return nothing
- **Data quality risks for fraud detection**: Stale indexing claims could mislead
- **Implementation complexity** (post-2025 SPARQL split) high relative to signal strength
- **Predatory journals CAN appear in Wikidata**: Presence provides false reassurance risk

### The Fundamental Problem

Wikidata is a **knowledge graph**, not a **quality database**. The questions it answers well are:
- "What is the canonical name of this publisher?"
- "When was this publisher founded?"
- "What external identifiers link to this journal?"

The question aletheia-probe needs to answer is:
- "Is this journal or conference venue predatory?"

These are orthogonal concerns. Wikidata enriches knowledge representation but does not directly assess scholarly quality.

---

## Recommendation: DEFER / LOW PRIORITY

### Summary

After deep analysis, Wikidata integration as a **standalone backend** is **not recommended in the near term**. The absence of direct predatory signal, combined with SPARQL infrastructure complexity, data quality caveats, and low unique-information yield, creates an unfavorable cost-benefit ratio for aletheia-probe's core mission.

However, a **targeted lightweight use case** — publisher name disambiguation utility — has genuine value and could be pursued as a modest enhancement to existing backends rather than a full integration.

### Key Reasoning

1. **Zero direct predatory detection value**: Wikidata has no curated list of predatory venues, no systematic quality filter, and no indexing-status database that aletheia-probe can trust. This is a fundamental mismatch with the tool's purpose.

2. **Presence ≠ legitimate**: Even documented predatory publishers have Wikidata entries. Adding a "found in Wikidata" signal risks creating false legitimacy impressions — the opposite of aletheia-probe's purpose.

3. **Low unique benefit rate**: Only ~11-17% of queries yield information not available from existing backends. The highest-value use case (publisher disambiguation) is an indirect benefit, not a direct assessment signal.

4. **Infrastructure complexity penalty**: The May 2025 WDQS graph split introduced a permanent layer of complexity (federation SPARQL for cross-graph queries). Any full integration now requires reasoning about two endpoints and managing federation failures.

5. **Data quality risks for adversarial contexts**: Predatory publishers have incentive to add or edit their Wikidata entries to appear legitimate. While Wikidata's vandalism detection is strong for obvious attacks, subtle self-promotion (adding plausible-looking inception dates, indexing claims) is harder to detect and could compromise assessment accuracy.

6. **Better uses of development effort**: Enhancing OpenAlex pattern analysis, adding regional predatory lists, or improving Crossref metadata quality checks would all deliver stronger, more direct improvements to predatory detection than Wikidata integration.

### When Wikidata Integration Would Make Sense

Full backend integration becomes more appropriate if:

1. **Scope expansion**: aletheia-probe explicitly aims to become a knowledge-graph-enriched scholarly intelligence tool, not just a predatory detector
2. **Publisher disambiguation is prioritized**: Significant research shows current publisher name mismatches are a major source of false negatives in Beall's or Crossref lookups
3. **Historical anchoring signal is validated**: User studies confirm that "publisher with no Wikidata history" is a meaningful fraud signal in practice
4. **Wikidata's curated scholarly data improves**: WikiProject Periodicals adds systematic indexing status maintenance, or a dedicated project emerges for predatory venue tracking
5. **Federation complexity is resolved**: If Wikimedia provides a stable, unified endpoint for journal+article queries without federation

### Alternative: Publisher Disambiguation Utility (Low Effort, Moderate Value)

Instead of a full backend, consider a **lightweight publisher name resolution utility**:

```python
# New utility: src/aletheia_probe/utils/publisher_disambiguator.py
# Used internally by other backends to normalize publisher names

async def resolve_publisher_aliases(publisher_name: str) -> PublisherInfo:
    """
    Query Wikidata for canonical publisher name + aliases.

    Returns:
    - canonical_name: Wikidata-preferred English label
    - aliases: list of known alternative names
    - inception: founding year (if available)
    - successor: name of successor organization (if dissolved)

    This improves match rates in:
    - Beall's List string matching
    - Crossref publisher normalization
    - OpenAlex publisher entity linking
    """
```

**Effort**: 1–1.5 developer days
**Value**: Improves existing backend recall by resolving name variants
**Risk**: Low (utility function, not part of primary assessment logic)
**Recommendation**: Implement as a quality-of-life enhancement when publisher name matching is identified as a significant source of false negatives.

---

## Technical Integration Approach (if pursued)

### Recommended: Option A — Query-time API, Main Graph Only

```
┌─────────────────────────────────────────────────────────────────────┐
│  User Query: Journal ISSN or Publisher Name                         │
└─────────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────────┐
│  WikidataBackend (OnlineBackend)                                     │
│  - Query main graph only (journals + publishers)                     │
│  - Priority 1: Lookup by ISSN (P236)                                │
│  - Priority 2: Lookup by normalized publisher name                  │
│  - Return: EntityInfo (labels, aliases, inception, external IDs)    │
│  - Cache results (7-day TTL, SQLite cache table)                    │
│  - Graceful degradation: timeout → skip, rate-limit → skip          │
└─────────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────────┐
│  Wikidata SPARQL Endpoint (Main Graph)                              │
│  https://query.wikidata.org/sparql                                  │
│  - Lookup journal entity by ISSN                                    │
│  - Extract: publisher, inception, DOAJ ID, Crossref ID              │
│  - Timeout: 10s (fail gracefully, do not block assessment)          │
└─────────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────────┐
│  Response Interpretation                                             │
│  - Entity found → QUALITY_INDICATOR (NOT legitimate/predatory)      │
│  - Publisher inception > X years → soft positive signal             │
│  - Publisher inception very recent → soft negative signal           │
│  - ISSN mismatch with claimed ISSN → cross-validation flag          │
│  - Entity NOT found → NOT_FOUND (strictly neutral, never negative)  │
└─────────────────────────────────────────────────────────────────────┘
```

### Critical Safety Constraint

Wikidata **must never** be used to generate `LEGITIMATE` assessments. The highest signal level allowed is `QUALITY_INDICATOR`.

**One exception** for negative assessments: if `P31 = Q65770378` (predatory journal) or `P31 = Q65770389` (predatory publisher) is present on the entity, a `PREDATORY` signal is justified — but must be flagged explicitly as a Wikidata community classification, not an authoritative blacklist lookup. Coverage is sparse; absence of this flag is completely neutral.

Rationale for the general constraint: Wikidata presence = community-acknowledged notability, not vetted quality. Predatory venues can be notable.

### Example Assessment Output

**Scenario 1: Well-known journal with publisher historical anchoring**
```
Journal: Journal of Biomedical Informatics
ISSN: 1532-0464
Assessment: QUALITY_INDICATOR

Wikidata:
✓ Wikidata entity found (Q15753218)
  Publisher: Elsevier (Wikidata Q746413, founded 1880)
  Publisher historical anchoring: 145-year-old publisher
  Cross-reference: DOAJ ID present, Crossref ID present
  ISSN match: consistent
  Note: Publisher name aliases include "Reed Elsevier", "Elsevier BV"

Combined assessment includes evidence from DOAJ, OpenAlex, Crossref.
Wikidata provides supplementary publisher context only.
```

**Scenario 2: Suspicious journal with new publisher**
```
Journal: International Journal of Advanced Biotechnology Research
ISSN: 0976-2612
Assessment: SUSPICIOUS (from other backends)

Wikidata:
⚠️ No Wikidata entity found for this journal
⚠️ Publisher "Bioinfo Publications" has no Wikidata entity
  Note: Absence is neutral; does not confirm or deny legitimacy

Other backends provide primary assessment signals.
```

**Scenario 3: Publisher name disambiguation (internal use)**
```
Input: "Springer Verlag"
Wikidata lookup: Resolves to Q194657 (Springer Nature)
Aliases: ["Springer", "Springer-Verlag", "Springer Verlag GmbH",
          "Springer Science+Business Media", "Springer Fachmedien"]
Inception: 1842
→ Improves Beall's/Crossref lookup: "Springer Verlag" now matches
  all variants in publisher name normalization
```

---

## Alternative Use Case: Conference Entity Matching

Wikidata may offer more value for **conference assessment** than for journals, because:

- aletheia-probe's conference data sources are more limited than journal sources
- WikiProject Academic Conferences maintains legitimate conference entities (ACM, IEEE, major venues)
- A conference claiming to be an ACM event but not findable in Wikidata is a soft red flag
- Conference organizer disambiguation (who runs this conference series?) is poorly served by other backends

However, the same fundamental limitation applies: predatory/spam conferences have no Wikidata entries, so absence is uninformative for the most-needed queries.

---

## Risks and Mitigations

### Risk 1: Predatory Publisher Self-Promotion via Wikidata
**Risk**: Predatory publishers edit their own Wikidata entries to add legitimacy signals (old inception dates, false indexing claims)
**Mitigation**:
- Never use Wikidata as authoritative source for indexing claims
- Weight publisher inception claims conservatively (require corroborating sources)
- Log Wikidata evidence source IDs for human review
- Never output `LEGITIMATE` based on Wikidata data alone

### Risk 2: SPARQL Infrastructure Instability
**Risk**: WDQS infrastructure changes (as happened in May 2025) can break integration silently
**Mitigation**:
- Monitor `https://www.wikidata.org/wiki/Wikidata:SPARQL_query_service` for announcements
- Implement health-check endpoint in backend startup
- Graceful degradation: WDQS unavailable → skip, never block
- Cache aggressively (7-day TTL reduces live query frequency)

### Risk 3: Rate Limit Violations
**Risk**: High query volume triggers IP ban from WDQS
**Mitigation**:
- Mandatory caching layer (cache-miss rate must be low in production)
- Descriptive `User-Agent` header identifying aletheia-probe
- Respect `Retry-After` headers on HTTP 429
- Maximum 3 concurrent SPARQL queries (well below the 5-limit)

### Risk 4: Stale Data Leading to False Assessments
**Risk**: Wikidata indexing or publication status data is years out of date
**Mitigation**:
- Never trust Wikidata for indexing status (use NLM Catalog, DOAJ directly)
- Use Wikidata only for publisher entity data (slow-changing: names, inception)
- Explicitly document in output: "Wikidata data as of [cache date]"

---

## Conclusion

Wikidata is an exceptional knowledge graph resource for **scholarly entity disambiguation and context enrichment**. For aletheia-probe's specific mission of **predatory journal detection**, however, the cost-benefit calculation is unfavorable:

### Key Strengths
1. Free, stable, CC0-licensed data with no commercial restrictions
2. Publisher name disambiguation across languages and historical variants (unique capability)
3. Publisher historical anchoring via inception dates (novel weak signal)
4. Cross-identifier linking enables consistency checks
5. Conference entity coverage useful for future conference assessment work

### Key Limitations
1. **Zero direct predatory signal**: No blacklist, no quality filter — fundamentally wrong tool for direct detection
2. **Presence ≠ legitimacy**: Predatory venues can be in Wikidata; using presence as positive signal risks false legitimacy conclusions
3. **Low coverage where it matters most**: New and predatory venues (the hardest queries) are absent
4. **SPARQL infrastructure complexity**: Post-2025 graph split makes cross-graph queries require federation
5. **Data quality risks**: Stale indexing claims, community-edited accuracy inconsistent with security-critical use

### Recommended Action

**Defer full backend integration.** Focus development effort on higher-impact improvements:
- Enhance OpenAlex/Crossref pattern analyzers (cross-domain improvements)
- Add more direct predatory/legitimacy lists (direct evidence)
- Improve conference assessment coverage

**Consider lightweight publisher disambiguation utility** (1–1.5 days effort):
- Query Wikidata for publisher name aliases and inception
- Use internally to improve string matching in Beall's List, Crossref backends
- Does not add Wikidata as a visible backend; improves existing signal quality silently

**Reconsider full integration when:**
- Publisher name mismatches are confirmed as a significant source of false negatives
- WikiProject Periodicals adds systematic, maintained indexing status
- aletheia-probe's scope expands to scholarly knowledge graph enrichment beyond predatory detection
- WDQS infrastructure stabilizes with a predictable, simple API for journal queries

---

## References and Sources

### Wikidata Documentation
- [Wikidata Main Page](https://www.wikidata.org/wiki/Wikidata:Main_Page)
- [Wikidata SPARQL Query Service](https://www.wikidata.org/wiki/Wikidata:SPARQL_query_service)
- [WDQS Graph Split (May 2025)](https://www.wikidata.org/wiki/Wikidata:SPARQL_query_service/WDQS_graph_split)
- [WDQS Scholarly Graph Split Impact Paper](https://ceur-ws.org/Vol-4064/PD-paper3.pdf)
- [Wikidata SPARQL Query Optimization Guide](https://www.wikidata.org/wiki/Wikidata:SPARQL_query_service/query_optimization)
- [WikiProject Periodicals](https://www.wikidata.org/wiki/Wikidata:WikiProject_Periodicals)
- [WikiCite / WikiProject Source MetaData](https://www.wikidata.org/wiki/Wikidata:WikiProject_Source_MetaData)
- [WikiCite Scholarly Journals List](https://www.wikidata.org/wiki/Wikidata:WikiCite/Wikidata_lists/Scholarly_journals)

### Key Wikidata Properties for Journals
- [P236 – ISSN](https://www.wikidata.org/wiki/Property:P236)
- [P5115 – DOAJ journal ID](https://www.wikidata.org/wiki/Property:P5115)
- [P8375 – Crossref journal ID](https://www.wikidata.org/wiki/Property:P8375)

### Scholarly Infrastructure Integration
- [Scholia – Wikidata-based scholarly profiles](https://scholia.toolforge.org/)
- [Scholia, Scientometrics and Wikidata (paper)](https://arxiv.org/abs/1703.04222)
- [Wikidata Scholarly Articles Subgraph Analysis](https://wikitech.wikimedia.org/wiki/User:AKhatun/Wikidata_Scholarly_Articles_Subgraph_Analysis)
- [Scholarly Wikidata: Population and Exploration of Conference Data using LLMs](https://arxiv.org/html/2411.08696v1)
- [National Academic Journals in Wikidata and Wikipedia](https://dwayzer.netlify.app/posts/2021-05-27-academic-journals-through-the-lens-of-wikidata/)
- [DOI Prefix Analysis augmented with Wikidata (GitHub)](https://github.com/csisc/DOIPrefixAnalysis)

### Data Quality and Vandalism
- [Vandalism Detection in Wikidata (ACM CIKM 2016)](https://dl.acm.org/doi/10.1145/2983323.2983740)
- [Formalizing Wikidata's property constraints using SHACL and SPARQL (2024)](https://journals.sagepub.com/doi/full/10.3233/SW-243611)
- [Wikidata:WikiProject Counter-Vandalism](https://www.wikidata.org/wiki/Wikidata:WikiProject_Counter-Vandalism)

### Context: OpenAlex and Wikidata
- [OpenAlex — geographic and disciplinary coverage study (PLOS ONE)](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0320347)
- [OpenAlex intro — 65,000 Wikidata concepts integrated](https://openalex.org/Intro_OpenAlex.pdf)

### OCLC and Linked Data
- [OCLC Meridian launch (2024)](https://www.oclc.org/en/news/releases/2024/20240507-introducing-oclc-meridian.html)
- [Libraries Leverage Wikimedia — OCLC Research](https://www.oclc.org/research/areas/community-catalysts/libraries-wikimedia.html)
