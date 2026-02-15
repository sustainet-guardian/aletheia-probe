# OpenAPC Integration Assessment for Aletheia-Probe

## Context

This assessment evaluates whether integrating [OpenAPC](https://openapc.github.io/) (Open Article Processing Charges) data into aletheia-probe would provide meaningful value for the tool's core mission of detecting predatory journals and conferences.

**What is OpenAPC?**

OpenAPC is an initiative based at Bielefeld University Library that collects and publishes data on fees paid for open access journal articles by universities, funders, and research institutions. The data is released under an open database license.

**Current Coverage (February 2026):**
- 256,534+ open access journal articles
- 474+ contributing institutions (primarily European/German-speaking)
- €543.2 million in documented APC expenditures
- Average APC: €2,043 | Median: €1,894
- Data spans 2005-2025
- Continuous updates as institutions report new data

**Data Access:**
- CSV files on GitHub ([OpenAPC/openapc-de](https://github.com/OpenAPC/openapc-de))
- OLAP server at olap.openapc.net
- Interactive visualizations at treemaps.openapc.net
- Persistent citation DOI: 10.5281/zenodo.6883472

**Data Fields:**
- Journal names and ISSNs
- Publisher information
- APC amounts (Euros)
- Institution identifiers (with ROR IDs)
- Publication DOIs
- Year of publication
- Optional supplementary costs

---

## Deep Analysis: Pros and Cons

### Pros

#### 1. **New Quality Signal: Pricing Transparency**
- Provides APC reference data for legitimate OA journals
- Can detect suspicious pricing patterns:
  - Unusually low APCs (predatory journals undercutting market)
  - Unusually high APCs (predatory journals maximizing profit)
  - Claims of "free" journals that actually charge APCs
  - Extreme APC variance across sources
- Context for cost assessment (e.g., "This journal charges 3x the median APC for its field")

#### 2. **Legitimacy Signal Through Institutional Trust**
- Journals with documented institutional APC payments have implicit legitimacy
- 474+ institutions perform due diligence before paying APCs
- Presence in OpenAPC = "real institutions paid money to publish here"
- Absence doesn't indicate predatory, but presence suggests legitimacy

#### 3. **Complementary to Existing Backends**
- DOAJ lists legitimate OA journals but doesn't include cost data
- OpenAPC adds cost dimension to existing legitimacy signals
- Can cross-validate DOAJ listings with actual institutional use

#### 4. **Detection of APC Fraud**
- Identify journals claiming to be "diamond OA" (free) but charging APCs
- Detect journals with hidden fees not disclosed on websites
- Flag journals with inconsistent pricing across sources

#### 5. **Open Data with Active Maintenance**
- Free, publicly accessible data
- Continuously updated as institutions report
- Well-documented data structure
- Active development (17,009+ GitHub commits)

#### 6. **Supports Research Use Cases**
- Institutional cost analysis (already a use case per README.md)
- Bibliometric studies on publishing costs
- Meta-research on APC trends and sustainability

#### 7. **Relatively Easy Integration**
- CSV format similar to existing backends (Beall's, UGC-CARE, etc.)
- Fits established DataSource/Backend architecture pattern
- No API authentication required
- Similar to Retraction Watch integration (periodic sync + cached queries)

### Cons

#### 1. **Limited Coverage (Major Limitation)**
- Only covers articles where institutions **reported** APC payments
- Biased toward European institutions (especially German-speaking)
- Misses:
  - Subscription journals (no APCs)
  - Free OA journals without APCs (diamond/platinum OA)
  - Predatory journals (institutions don't pay them)
  - Journals from underrepresented regions
  - Recent articles (reporting lag)

**Estimated query coverage: 5-15%** of aletheia-probe queries would find APC data.

Comparison to existing backends:
- DOAJ: 22,000+ journals (broader OA coverage)
- OpenAlex: 240M+ works (near-universal coverage)
- Scopus: 30,000+ journals (major publishers)

#### 2. **Weak Signal for Predatory Detection**
- **Critical issue**: APCs alone don't indicate predatory behavior
- Legitimate journals charge APCs (Nature Communications: €5,000+)
- Predatory journals charge APCs (but aren't in OpenAPC)
- APCs are a **cost metric**, not a **quality metric**
- Requires complex interpretation ("what is normal for this field?")

#### 3. **Institutional and Geographic Bias**
- Heavily weighted toward German/European institutions
- Underrepresents:
  - North American institutions
  - Asian institutions
  - Global South institutions
- Creates false negatives (legitimate journals not used by reporting institutions appear absent)

#### 4. **Maintenance Burden**
- Another data source to sync (quarterly updates recommended)
- Another CSV format to parse and normalize
- Another set of edge cases to handle (multi-language journal names, ISSN variations)
- Another integration doc to write and maintain

#### 5. **Temporal Lag**
- Institutions report APCs **after** publication and payment processing
- Lag can be 6-12 months for recent articles
- Doesn't help with detecting newly launched predatory journals

#### 6. **Unclear Direct Value for Core Mission**
- Aletheia-probe's mission: Detect predatory journals
- OpenAPC's value: Cost transparency and institutional payment tracking
- **Misalignment**: OpenAPC doesn't directly identify predatory journals
- Different use case: Cost awareness vs. quality assessment

#### 7. **Risk of Misinterpretation**
- Users might conflate "high APC" with "predatory"
- Legitimate high-impact journals (Nature, Science) have high APCs
- Users might conflate "not in OpenAPC" with "suspicious"
- Absence is more about institutional reporting than journal quality

---

## Integration Effort Estimate

**Medium Effort: 3-5 developer days**

### Breakdown

#### Day 1: DataSource Implementation
**File:** `src/aletheia_probe/updater/sources/openapc_source.py`

- Create `OpenAPCSource` class extending `DataSource`
- Implement `fetch_data()`:
  - Download `apc_de.csv` from GitHub
  - Parse CSV (handle encoding, multi-language names)
  - Normalize journal names (using existing `normalize_name()`)
  - Aggregate APC statistics per journal:
    - Median APC, mean APC, std deviation
    - Min/max APC
    - Number of institutions
    - Number of articles
    - Years of coverage
- Implement `should_update()`: Check if last sync > 90 days (quarterly)
- Add URL to `config.py` DataSourceUrlConfig

#### Day 2: Backend Implementation
**File:** `src/aletheia_probe/backends/openapc_backend.py`

- Create `OpenAPCBackend` extending `CachedBackend`
- Implement journal lookup by ISSN (primary) and normalized name (fallback)
- Return `BackendResult` with:
  - Assessment type: `QUALITY_INDICATOR` (not legitimate/predatory)
  - Evidence: APC statistics
  - Reasoning: "Documented in X institutional APC reports"
- Add configuration to backend registry

**Database schema:**
```sql
-- Option A: Store in journal_metadata
ALTER TABLE journal_metadata ADD COLUMN apc_median_euro REAL;
ALTER TABLE journal_metadata ADD COLUMN apc_count INTEGER;

-- Option B: New table (cleaner, recommended)
CREATE TABLE apc_statistics (
    journal_id INTEGER PRIMARY KEY,
    median_apc_euro REAL,
    mean_apc_euro REAL,
    stddev_apc_euro REAL,
    min_apc_euro REAL,
    max_apc_euro REAL,
    institution_count INTEGER,
    article_count INTEGER,
    first_year INTEGER,
    last_year INTEGER,
    FOREIGN KEY (journal_id) REFERENCES journals(id)
);
```

#### Day 3: Assessment Integration
**Files:** `src/aletheia_probe/core/dispatcher.py`, assessment logic

- Add APC data to assessment results
- Define APC-based indicators:
  - Unusually high APC: >2x median for field (requires field classification - complex!)
  - Institutional trust: Number of institutions (more = higher trust)
  - Consistency: Low std deviation suggests transparent pricing
- **Limitation**: Field-specific APC norms require additional data (e.g., "physics journals typically cost X")
- Add APC info to JSON/text output formats

#### Days 4-5: Testing and Documentation
- Unit tests for OpenAPCSource parsing
- Integration tests for OpenAPCBackend queries
- Update `dev-notes/integration/openapc.md`
- Update README.md data sources section
- Update assessment methodology docs
- Add examples to user guide

### Additional Considerations

**Dependencies:**
- None (uses existing CSV parsing, aiohttp)

**Database impact:**
- +256k rows in journals table (potential duplicates with existing entries)
- +256k rows in apc_statistics table
- ~50-100 MB additional database size

**Sync time:**
- Initial sync: ~2-3 minutes (CSV download + parse + insert)
- Subsequent syncs: ~1-2 minutes (incremental updates)

---

## Technical Integration Approach

### Recommended: Option B (Cached with Periodic Sync)

**Reasoning:**
- OpenAPC data is relatively stable (quarterly updates)
- Dataset size is manageable (~256k rows)
- Query-time efficiency (local cache faster than API calls)
- Consistent with Retraction Watch integration pattern

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  OpenAPC GitHub Repository (CSV files)                      │
└─────────────────────────────────────────────────────────────┘
                          ↓
                   (Quarterly sync)
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  OpenAPCSource (DataSource)                                 │
│  - fetch_data(): Download and parse CSV                     │
│  - Normalize journal names                                  │
│  - Aggregate APC statistics                                 │
└─────────────────────────────────────────────────────────────┘
                          ↓
                   (AsyncDBWriter)
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  SQLite Cache (apc_statistics table)                        │
│  - journal_id, median_apc, institution_count, etc.          │
└─────────────────────────────────────────────────────────────┘
                          ↓
                   (Query time)
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  OpenAPCBackend (CachedBackend)                             │
│  - Query by ISSN → normalized name fallback                 │
│  - Return APC statistics as BackendResult                   │
│  - Evidence type: QUALITY_INDICATOR                         │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  Dispatcher (Assessment aggregation)                        │
│  - Combine APC data with other backend results              │
│  - Add to confidence scoring (weak signal)                  │
│  - Include in reasoning output                              │
└─────────────────────────────────────────────────────────────┘
```

### Code Structure

Following existing patterns from `retraction_watch_backend.py` and `algerian_ministry_backend.py`:

```
src/aletheia_probe/
├── backends/
│   └── openapc_backend.py          # Backend query logic
├── updater/
│   └── sources/
│       └── openapc_source.py       # Data fetching and parsing
└── config.py                       # Add openapc_url config
dev-notes/
└── integration/
    └── openapc.md                  # Integration documentation
```

---

## Expected Coverage and Benefit Rate

### Coverage Analysis

**Query scenarios:**

| Journal Type | Likelihood in OpenAPC | Estimated % of Queries |
|--------------|----------------------|------------------------|
| Major OA journals (PLoS, BMC, MDPI) | High (70-90%) | 15% |
| Regional OA journals | Low (5-20%) | 20% |
| Subscription journals | None (0%) | 40% |
| Predatory journals | None (0%) | 10% |
| Conference proceedings | None (0%) | 10% |
| Diamond OA (free) | None (0%) | 5% |

**Estimated overall coverage: 5-15% of queries** would find APC data.

### Benefit Rate Analysis

Of the 5-15% coverage:

**High benefit (institutional legitimacy signal):**
- Regional OA journals not in DOAJ → 3-5% of queries
- Newer legitimate OA journals → 2-3% of queries

**Medium benefit (cost context):**
- Well-known OA journals (already in DOAJ) → 5-10% of queries
- Adds cost dimension but redundant legitimacy signal

**Low/no benefit:**
- Subscription journals → 40% (not applicable)
- Predatory journals → 10% (not in OpenAPC)
- Diamond OA → 5% (no APCs to report)

**Net high-value benefit: 5-8% of queries**

This means **92-95% of queries would not benefit** from OpenAPC integration.

### Comparison to Other Backends

| Backend | Coverage | Direct Impact on Detection |
|---------|----------|----------------------------|
| DOAJ | 22,000 journals | High (legitimacy list) |
| Beall's List | 2,900 entries | High (predatory list) |
| OpenAlex Analyzer | 240M works | High (pattern analysis) |
| Retraction Watch | 27,000 journals | Medium (quality signal) |
| **OpenAPC** | **5-15% queries** | **Low (cost context)** |

---

## Critical Assessment: Alignment with Mission

### Aletheia-Probe's Core Mission
From README.md:
> "A command-line tool for evaluating the **legitimacy** of academic journals and conferences. By aggregating data from authoritative sources and applying advanced pattern analysis, it helps researchers, librarians, and institutions **detect predatory venues** and ensure the integrity of scholarly publishing."

### How OpenAPC Relates

**What OpenAPC provides:**
- Cost transparency
- Institutional payment tracking
- Implicit legitimacy signal (institutions vetted journal)

**What OpenAPC does NOT provide:**
- Direct predatory journal identification
- Broad coverage of journal landscape
- Quality indicators beyond "institutions paid"

### Mission Alignment Score: **Moderate (6/10)**

**Aligned aspects:**
- Institutional trust signal supports legitimacy assessment
- Can detect APC fraud (journal claims free but charges)
- Supports research use cases (cost analysis)

**Misaligned aspects:**
- Cost data ≠ quality/legitimacy data
- Coverage gap (92-95% of queries unaffected)
- Maintenance burden for limited impact
- Risk of user misinterpretation (conflating cost with quality)

---

## Recommendation: DEFER / LOW PRIORITY

### Summary

After deep analysis, I recommend **deferring** OpenAPC integration or treating it as **low priority**. While the integration is technically feasible (3-5 days effort) and OpenAPC provides interesting data, the **cost-benefit ratio is unfavorable** for aletheia-probe's core mission.

### Key Reasoning

1. **Low impact on core mission**: OpenAPC doesn't directly improve predatory journal detection. It provides cost context, which is tangential to legitimacy assessment.

2. **Low coverage, low benefit**: Only 5-15% of queries would find data, and of those, only 5-8% gain meaningful new information (not already covered by DOAJ or other backends).

3. **Weak signal strength**: APCs are ambiguous indicators. High APCs don't mean predatory; low APCs don't mean legitimate. Requires complex field-specific interpretation that aletheia-probe currently lacks.

4. **Better alternatives exist** for improving detection accuracy:
   - Enhance OpenAlex pattern analysis (detect publication mills)
   - Improve Crossref metadata quality checks (detect suspicious publishers)
   - Add more predatory conference lists (direct evidence)
   - Expand DBLP coverage to more fields (legitimacy lists)

5. **Maintenance burden**: Another data source to sync, parse, normalize, test, and document. The effort is non-trivial for the limited benefit.

6. **Geographic/institutional bias**: Heavily European-centric data may create false impressions about non-European journals.

### When It WOULD Make Sense

Integration becomes valuable if:

1. **Scope expansion**: Aletheia-probe explicitly adds "cost transparency" as a goal (beyond predatory detection)
2. **Community demand**: Users/institutions specifically request APC data for procurement decisions
3. **Research use case**: Studies on APC trends, institutional spending, or OA economics
4. **Combined signal detection**: Used with other data to identify APC fraud patterns (e.g., "journal in DOAJ but charges 10x typical APC for field")
5. **Field-specific analysis**: After implementing journal field classification (requires additional data source)

### Alternative: Lightweight Integration

If pursuing integration despite concerns, consider a **minimal approach**:

- **No sync, query-time only**: Query OpenAPC's OLAP server on-demand (like OpenAlex)
- **Display only, no scoring**: Show APC data when available, but don't use in confidence calculation
- **User-facing feature**: "This journal has documented APC payments from X institutions" (transparency, not judgment)
- **Effort reduction**: 1-2 days instead of 3-5 days

This provides value for cost-conscious users without committing to full backend integration.

---

## Conclusion

OpenAPC is a well-maintained, valuable dataset for **cost transparency and institutional spending analysis**. However, its alignment with aletheia-probe's mission of **predatory journal detection** is moderate at best. The limited coverage (5-15%), weak signal strength for quality assessment, and maintenance burden outweigh the benefits for the current tool scope.

**Recommended action**: Defer integration. Focus development efforts on:
- Improving existing pattern analyzers (OpenAlex, Crossref)
- Adding more direct predatory/legitimacy lists
- Enhancing conference assessment coverage
- Refining confidence scoring algorithms

If user demand or scope expansion warrants APC data in the future, revisit with the lightweight query-time approach.

---

## Sources

- [OpenAPC Datasets](https://openapc.github.io/)
- [OpenAPC GitHub Repository](https://github.com/OpenAPC/openapc-de)
- [OpenAPC Service Guide (OpenAIRE)](https://www.openaire.eu/openapc-guide)
- [OpenAPC Treemap Visualization](https://treemaps.openapc.net/apcdata/openapc/publisher)
- [OpenAPC Publication (UKSG Insights)](https://insights.uksg.org/articles/10.1629/uksg.439)
- [Processed in OpenAPC: 2023 Data](https://www.opencost.de/en/news/openapc-data-2023/)
