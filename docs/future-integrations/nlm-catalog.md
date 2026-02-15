# NLM Catalog (National Library of Medicine) Integration Assessment

## Context

This assessment evaluates whether integrating [NLM Catalog](https://www.ncbi.nlm.nih.gov/nlmcatalog) data into aletheia-probe would provide meaningful value for the tool's core mission of detecting predatory journals and conferences.

**What is NLM Catalog?**

The NLM Catalog is the National Library of Medicine's comprehensive database of journal titles and other resources indexed for MEDLINE/PubMed. Maintained by the U.S. National Institutes of Health, it serves as an authoritative registry for biomedical and life sciences journals that meet NLM's rigorous quality standards.

**Current Coverage (February 2026):**
- 5,600+ actively indexed journals for MEDLINE
- 40,000+ total journal records (including historical, discontinued, non-MEDLINE)
- Comprehensive coverage of biomedical and life sciences literature
- Global coverage with focus on scholarly biomedical publications
- Continuous updates as journals are reviewed and added/removed

**Data Access:**
- E-Utilities API (free, public domain)
- XML and JSON response formats
- No authentication required (API key optional for higher rate limits)
- Rate limits: 3 requests/second without key, 10 requests/second with key
- Commercial use explicitly allowed (U.S. Government work, public domain)

**Data Fields:**
- Journal title (current and historical)
- ISSN-L, print ISSN, electronic ISSN
- NLM ID (unique identifier)
- MEDLINE indexing status (currently indexed, not indexed, ceased publication)
- Publisher information
- Subject headings (MeSH terms)
- Publication start/end dates
- Language(s) of publication
- Country of publication
- Links to publisher website

**MEDLINE Indexing Criteria:**
- Rigorous peer review process
- Editorial board quality
- Scientific content quality
- Scope and coverage
- Ethics standards (ICMJE guidelines)
- Publishing regularity
- Technical quality

Journals are reviewed by the Literature Selection Technical Review Committee (LSTRC) before MEDLINE indexing.

---

## Deep Analysis: Pros and Cons

### Pros

#### 1. **Strong Legitimacy Signal for Biomedical Journals**
- MEDLINE indexing is a **gold standard** quality marker in biomedical sciences
- Journals must pass rigorous peer review to be indexed
- NLM actively monitors and removes journals that decline in quality
- Presence in NLM = strong legitimacy indicator
- Absence from NLM for biomedical journal = potential red flag (or journal too new/regional)

#### 2. **Authoritative Whitelist for Biomedical Domain**
- U.S. Government-maintained, highly trusted source
- Independent review committee (LSTRC) evaluates journals
- Standards aligned with research integrity principles
- Complementary to DOAJ (which covers all fields but with different criteria)

#### 3. **Detection of Fake MEDLINE Claims**
- **Critical use case**: Predatory journals often falsely claim MEDLINE indexing
- Example: "Indexed in PubMed/MEDLINE" on journal website but not in NLM Catalog
- Verifying MEDLINE status exposes fraudulent claims
- High precision: Binary check (indexed = yes/no)

#### 4. **Field-Specific Coverage Where It Matters**
- Biomedical sciences have high concentration of predatory journals
- Researchers in health sciences particularly vulnerable
- Complements existing backends:
  - DOAJ: Multidisciplinary OA journals
  - Scopus: Broad coverage but commercial
  - NLM: Biomedical-specific authoritative list

#### 5. **Public Domain Data with Stable API**
- No licensing restrictions (U.S. Government work)
- Well-documented E-Utilities API
- Long-term stability (NLM commitment to open access)
- No authentication barriers

#### 6. **Relatively Easy Integration**
- Query-time API (no large dataset sync needed)
- Simple lookup by ISSN or journal title
- Fits established `OnlineBackend` architecture pattern
- Similar complexity to OpenAlex/Crossref integrations

#### 7. **Complements Retraction Watch Integration**
- Both focus on biomedical research integrity
- NLM Catalog: Pre-publication quality (indexing standards)
- Retraction Watch: Post-publication quality (retractions)
- Combined view of journal quality lifecycle

### Cons

#### 1. **Limited Scope: Biomedical Journals Only**
- **Critical limitation**: Only covers biomedical and life sciences
- Irrelevant for:
  - Computer science journals (30%+ of aletheia-probe queries estimated)
  - Engineering, mathematics, physics
  - Social sciences, humanities
  - Business, law, education
  - Multidisciplinary journals outside life sciences

**Estimated domain coverage: 20-30% of aletheia-probe queries** (biomedical/health sciences only)

#### 2. **Absence ≠ Predatory**
- Many legitimate biomedical journals are NOT in MEDLINE:
  - Newly launched journals (not yet reviewed)
  - Regional/national journals (quality but limited scope)
  - Specialty journals (too narrow for MEDLINE)
  - OA journals not yet evaluated
  - Journals in LSTRC review queue (can take 1-2 years)

- Interpretation complexity: "Not in NLM" requires careful reasoning
- Risk of false positives if absence treated as negative signal

#### 3. **API Query Latency**
- Each assessment requires real-time API call
- Rate limiting (3-10 requests/second)
- Network dependency (availability risk)
- Slower than cached backends (DOAJ, Beall's)

#### 4. **Conference Assessment: Not Applicable**
- NLM Catalog is journal-focused
- Does NOT cover conferences
- Aletheia-probe supports conference assessment
- Zero benefit for conference queries

#### 5. **Overlap with Existing Backends**
- Many MEDLINE-indexed journals already in:
  - DOAJ (open access journals)
  - Scopus (major publishers)
  - OpenAlex (metadata-rich)
  - Web of Science (impact factor)

- Incremental value for already-known legitimate journals
- Main unique value: Detecting **false MEDLINE claims** by predatory journals

#### 6. **Temporal Lag for New Journals**
- LSTRC review process takes 6-24 months
- Newly launched legitimate journals: Not yet indexed
- Cannot help with detecting very recent predatory journals
- Complements but doesn't replace pattern analysis for new venues

#### 7. **Binary Signal Only**
- NLM provides: Indexed = yes/no
- Does NOT provide:
  - Quality metrics (impact factor, citation counts)
  - Detailed publisher information
  - Peer review process details
  - Editorial board composition

- Limited richness compared to OpenAlex/Crossref analyzers

---

## Integration Effort Estimate

**Low-Medium Effort: 1-2 developer days**

### Breakdown

#### Day 1: Backend Implementation
**File:** `src/aletheia_probe/backends/nlm_catalog_backend.py`

- Create `NLMCatalogBackend` extending `OnlineBackend`
- Implement E-Utilities API integration:
  - Primary query: ESearch by ISSN (most reliable)
  - Fallback query: ESearch by journal title (normalized)
  - Parse XML response (NLM uses XML, not JSON by default)
  - Extract NLM ID, indexing status, publisher, subjects
- Implement result interpretation:
  - **MEDLINE-indexed** → `LEGITIMATE` assessment
  - **Not indexed but in catalog** → `QUALITY_INDICATOR` (exists but not MEDLINE)
  - **Not found** → `NOT_FOUND` (no assessment)
- Add rate limiting (3 req/s default, 10 req/s with API key)
- Add configuration:
  - API base URL: `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/`
  - Optional API key support (config.py)
  - Timeout settings

#### Day 2: Testing, Documentation, and Integration
- Unit tests:
  - Mock API responses for indexed/not indexed/not found
  - ISSN query and title query fallback
  - Rate limiting validation
- Integration tests:
  - Real API calls to verify parsing (test suite)
- Documentation:
  - Create `dev-notes/integration/nlm_catalog.md`
  - Update README.md data sources section
  - Add examples to user guide
- Assessment integration:
  - Add NLM status to assessment output (JSON/text)
  - Include reasoning: "MEDLINE-indexed" or "Not indexed in MEDLINE"

### Database Impact
- **No database changes required** (query-time API backend)
- Optional caching layer in future (similar to OpenAlex response caching)

### API Call Pattern
```python
# Example E-Utilities query
# 1. ESearch: Find journal by ISSN
https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=nlmcatalog&term=1234-5678[ISSN]&retmode=json

# 2. ESummary: Get journal details
https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=nlmcatalog&id=<NLM_ID>&retmode=json

# 3. Parse JSON response for:
#    - CurrentIndexingStatus: "Y" (MEDLINE), "N" (not indexed)
#    - Title, Publisher, MeSH subjects
```

---

## Expected Coverage and Benefit Rate

### Coverage Analysis

**Query scenarios:**

| Journal Type | Likelihood in NLM Catalog | Estimated % of Queries |
|--------------|--------------------------|------------------------|
| Biomedical journals (major) | High (80-90% if MEDLINE-worthy) | 15% |
| Biomedical journals (regional/specialty) | Low (10-30%) | 10% |
| Computer science journals | None (0%) | 25% |
| Engineering/physics journals | None (0%) | 15% |
| Social sciences/humanities | None (0%) | 15% |
| Multidisciplinary (Science, Nature) | Varies (some indexed) | 5% |
| Predatory journals (biomedical) | None (0%) but may claim indexing | 10% |
| Conference proceedings | None (0%) | 5% |

**Estimated overall coverage: 20-30% of queries** (biomedical domain only)

### Benefit Rate Analysis

Of the 20-30% biomedical queries:

**High benefit (fraud detection):**
- Predatory journals falsely claiming MEDLINE indexing → **5-8% of queries**
- **Primary value**: Exposing fraudulent claims

**Medium benefit (legitimacy confirmation):**
- Regional biomedical journals not in DOAJ/Scopus → 5-8% of queries
- Adds authoritative legitimacy signal

**Low/redundant benefit:**
- Major biomedical journals already in DOAJ/Scopus → 10-15% of queries
- Confirms existing legitimacy signals (useful but not new information)

**No benefit:**
- Non-biomedical domains → 70-80% of queries

**Net high-value benefit: 10-16% of queries** (fraud detection + regional legitimacy)

This means **84-90% of queries** either don't benefit or receive redundant information.

### Comparison to Other Backends

| Backend | Coverage | Direct Impact on Detection | Domain Specificity |
|---------|----------|----------------------------|-------------------|
| DOAJ | 22,000 journals | High (legitimacy list) | All fields |
| Beall's List | 2,900 entries | High (predatory list) | All fields |
| OpenAlex Analyzer | 240M works | High (pattern analysis) | All fields |
| Retraction Watch | 27,000 journals | Medium (quality signal) | Mainly biomedical |
| **NLM Catalog** | **5,600 MEDLINE** | **Medium (legitimacy + fraud detection)** | **Biomedical only** |

---

## Critical Assessment: Alignment with Mission

### Aletheia-Probe's Core Mission
From README.md:
> "A command-line tool for evaluating the **legitimacy** of academic journals and conferences. By aggregating data from authoritative sources and applying advanced pattern analysis, it helps researchers, librarians, and institutions **detect predatory venues** and ensure the integrity of scholarly publishing."

### How NLM Catalog Relates

**What NLM Catalog provides:**
- Authoritative MEDLINE indexing status
- Biomedical journal quality validation
- Fake MEDLINE claim detection
- Publisher and subject information

**What NLM Catalog does NOT provide:**
- Coverage for non-biomedical fields (70-80% of queries)
- Conference assessment (irrelevant)
- Granular quality metrics
- Pattern analysis capabilities

### Mission Alignment Score: **Moderate-High (7/10)**

**Aligned aspects:**
- **Strong legitimacy signal** for biomedical journals
- **Fraud detection** for fake MEDLINE claims (high precision)
- Authoritative, government-maintained source
- Complements existing biomedical focus (Retraction Watch)

**Misaligned aspects:**
- **Domain limitation**: 70-80% of queries outside biomedical scope
- Conference assessment: Not applicable
- Redundancy: Major journals already covered by DOAJ/Scopus
- Absence ambiguity: "Not in NLM" ≠ predatory (careful interpretation needed)

**Nuanced perspective:**
- For **biomedical researchers**: Very high value (8-9/10)
- For **computer science/engineering researchers**: No value (0/10)
- For **multidisciplinary tool**: Moderate value (7/10)

---

## Recommendation: IMPLEMENT (LOW PRIORITY)

### Summary

After analysis, I recommend **implementing** NLM Catalog integration as a **low-priority, biomedical-specific backend**. While domain-limited, the combination of authoritative legitimacy signaling and fake MEDLINE claim detection provides meaningful value for a significant user segment.

### Key Reasoning

#### In Favor of Implementation:

1. **Strong signal strength**: MEDLINE indexing is a trusted, rigorous quality standard
   - Higher precision than many existing backends
   - Minimal false positives (only indexed journals get legitimacy signal)

2. **Unique fraud detection capability**: Exposes fake MEDLINE claims
   - Predatory journals frequently lie about MEDLINE indexing
   - NLM provides authoritative verification
   - High value for biomedical researchers

3. **Low implementation cost**: 1-2 developer days
   - Simple API integration (query-time, no sync)
   - No database schema changes
   - Fits existing OnlineBackend pattern

4. **Complements existing biomedical coverage**:
   - Retraction Watch (post-publication integrity)
   - NLM Catalog (pre-publication quality standards)
   - Combined biomedical research integrity suite

5. **User base alignment**: Aletheia-probe likely has significant biomedical user segment
   - Health sciences particularly vulnerable to predatory publishing
   - Academic medical centers, hospital libraries, NIH-funded researchers

6. **Public domain, stable API**: Zero licensing risk, long-term sustainability

#### Concerns (Manageable):

1. **Domain limitation** (70-80% queries irrelevant)
   - **Mitigation**: Clear documentation that NLM is biomedical-specific
   - **Acceptance**: Domain-specific backends acceptable (e.g., DBLP is CS-only)

2. **Absence ambiguity** (not in NLM ≠ predatory)
   - **Mitigation**: Conservative interpretation in assessment logic
   - Only treat MEDLINE-indexed as positive signal
   - "Not found" → neutral (not negative)

3. **API latency** (real-time queries)
   - **Mitigation**: Rate limiting, timeout handling
   - **Future**: Optional response caching

### When It Makes Sense

Integration is valuable because:

1. **Cost-benefit ratio favorable**: Low effort (1-2 days) for meaningful biomedical coverage
2. **Unique capability**: Fraud detection not available elsewhere
3. **User demand**: Biomedical researchers likely user segment
4. **Strategic fit**: Strengthens biomedical research integrity focus

### Implementation Priority

**Low priority** (after higher-impact improvements):

**Higher priority:**
- Enhance OpenAlex pattern analysis (all fields, publication mills)
- Add more predatory lists (regional, conference-specific)
- Improve Crossref metadata quality checks

**NLM Catalog priority:**
- Implement when:
  - Core pattern analyzers are robust
  - Biomedical user feedback requests MEDLINE verification
  - Development bandwidth available for domain-specific enhancements

---

## Technical Integration Approach

### Recommended: Query-Time API Backend

**Reasoning:**
- NLM dataset small enough for API queries (no need for full sync)
- Low query volume per assessment (1 call per journal)
- API stable and well-maintained
- Consistent with OpenAlex/Crossref integration patterns

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  User Query: Journal ISSN or Title                          │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  Dispatcher (Assessment orchestration)                      │
│  - Check if query is biomedical domain (optional filter)   │
│  - Route to NLMCatalogBackend                               │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  NLMCatalogBackend (OnlineBackend)                          │
│  - Query E-Utilities API by ISSN                            │
│  - Fallback: Query by normalized journal title             │
│  - Parse XML/JSON response                                  │
│  - Rate limiting (3-10 req/s)                               │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  NLM E-Utilities API                                        │
│  https://eutils.ncbi.nlm.nih.gov/entrez/eutils/            │
│  - ESearch: Find journal by ISSN/title                      │
│  - ESummary: Get indexing status and metadata              │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  Response Interpretation                                    │
│  - MEDLINE-indexed → LEGITIMATE (confidence: 0.95)          │
│  - In catalog, not indexed → QUALITY_INDICATOR (0.70)       │
│  - Not found → NOT_FOUND (neutral)                          │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  Assessment Output                                          │
│  - Add to evidence: "MEDLINE-indexed by NLM"                │
│  - Add to reasoning: "Journal meets NLM quality standards"  │
│  - Fraud detection: "Journal claims MEDLINE but not found"  │
└─────────────────────────────────────────────────────────────┘
```

### Code Structure

```
src/aletheia_probe/
├── backends/
│   └── nlm_catalog_backend.py    # Backend query logic
└── config.py                      # Add nlm_api_key config (optional)
dev-notes/
└── integration/
    └── nlm_catalog.md             # Integration documentation
```

### Example Assessment Output

**Scenario 1: MEDLINE-indexed journal**
```
Journal: Journal of Biological Chemistry
ISSN: 0021-9258
Assessment: LEGITIMATE

Evidence:
✓ MEDLINE-indexed by NLM (biomedical quality standard)
✓ Listed in DOAJ (open access)
✓ 240,000+ works in OpenAlex (established publication record)

Confidence: 0.98
```

**Scenario 2: Predatory journal with false MEDLINE claim**
```
Journal: International Journal of Advanced Medical Research
ISSN: 1234-5678
Assessment: PREDATORY (LIKELY)

Evidence:
✗ Claims MEDLINE indexing but NOT FOUND in NLM Catalog
✗ Listed in Beall's List (known predatory publisher)
✗ Suspicious publication patterns in OpenAlex (1,200 papers/year)

⚠️  Fraud detected: False MEDLINE indexing claim

Confidence: 0.92
```

**Scenario 3: Regional biomedical journal (not MEDLINE-indexed)**
```
Journal: Polish Journal of Pathology
ISSN: 1233-9687
Assessment: QUALITY_INDICATOR

Evidence:
✓ Found in NLM Catalog (recognized journal)
⚠️ Not currently MEDLINE-indexed (regional scope or under review)
✓ 1,200+ works in OpenAlex (consistent publication record)

Note: Absence from MEDLINE does not indicate low quality.
Many regional and specialty journals are not indexed.

Confidence: 0.75
```

---

## Fraud Detection: Key Value Proposition

### The Problem

Predatory journals frequently make **false claims** about MEDLINE/PubMed indexing:
- "Indexed in PubMed" (but only individual articles submitted, not journal indexed)
- "MEDLINE-listed" (fabricated claim)
- "NLM-approved" (meaningless term)

**Why this matters:**
- Researchers trust MEDLINE as quality indicator
- False indexing claims mislead authors and institutions
- Damages credibility of legitimate MEDLINE-indexed journals

### The Solution

NLM Catalog integration provides **authoritative verification**:

1. **User queries journal**: "Is Journal X legitimate?"
2. **Journal website claims**: "Indexed in MEDLINE"
3. **Aletheia-probe checks**: Query NLM Catalog API
4. **Result**: NOT FOUND in NLM
5. **Assessment**: ⚠️ **Fraud detected: False MEDLINE claim**

**High precision, high impact** for biomedical domain.

---

## Comparison to Similar Domain-Specific Backends

| Backend | Domain | Coverage | Status | Value |
|---------|--------|----------|--------|-------|
| **DBLP** | Computer Science | 8M+ publications | Implemented | High (CS researchers) |
| **Retraction Watch** | Mainly Biomedical | 27,000 journals | Implemented | High (integrity) |
| **NLM Catalog** | Biomedical | 5,600 MEDLINE | Not implemented | **High (fraud detection)** |
| **EconLit** (hypothetical) | Economics | ~1,000 journals | Not considered | Medium (niche) |

**Precedent**: Aletheia-probe already supports domain-specific backends (DBLP, Retraction Watch). NLM Catalog fits this pattern.

---

## Potential Enhancements (Future)

### Phase 1: Basic Integration (1-2 days)
- ISSN-based MEDLINE indexing check
- Binary signal: Indexed vs. Not found

### Phase 2: Enhanced Metadata (Additional 1 day)
- Extract publisher information
- Subject headings (MeSH terms) for domain validation
- Publication date range (detect ceased journals)

### Phase 3: Advanced Fraud Detection (Additional 2-3 days)
- Web scraping: Detect journals claiming MEDLINE on website
- Cross-validate website claims against NLM API
- Generate fraud report: "Claims MEDLINE but not indexed"

### Phase 4: PubMed Article-Level Integration (Future consideration)
- Verify if journal has articles in PubMed
- Distinguish: "Journal indexed" vs. "Individual articles submitted"
- Detect: Predatory journals with few PubMed articles claiming full indexing

**Recommendation**: Start with Phase 1. Evaluate user feedback before Phases 2-4.

---

## Alternative: Lightweight "On-Demand" Integration

If full backend integration is deferred, consider **user-facing utility**:

```bash
# Add subcommand for MEDLINE verification
aletheia-probe verify-medline --issn 0021-9258
aletheia-probe verify-medline --title "Journal of Biological Chemistry"

# Output:
✓ MEDLINE-indexed (NLM ID: 2985121R)
  Publisher: American Society for Biochemistry and Molecular Biology
  Subjects: Biochemistry, Molecular Biology
  Indexed since: 1905
```

**Effort**: 0.5 days
**Value**: Provides MEDLINE verification without full assessment integration

---

## Risks and Mitigations

### Risk 1: API Availability
**Risk**: NLM API downtime affects assessments
**Mitigation**:
- Graceful degradation (skip NLM if unavailable)
- Timeout handling (5-10 second limit)
- Optional response caching (future)

### Risk 2: False Negatives
**Risk**: Legitimate new journals not yet MEDLINE-indexed
**Mitigation**:
- Conservative interpretation: Absence = neutral (not negative)
- Assessment reasoning: "Not yet indexed" vs. "Likely not eligible"
- Combine with other signals (DOAJ, OpenAlex patterns)

### Risk 3: Rate Limiting
**Risk**: Exceed API rate limits (3-10 req/s)
**Mitigation**:
- Implement request throttling
- Queue-based API calls
- Optional API key support (10 req/s)

### Risk 4: User Misinterpretation
**Risk**: Users over-rely on MEDLINE status
**Mitigation**:
- Clear documentation: "Biomedical domain only"
- Assessment output: "Not applicable for non-biomedical journals"
- Educational content: MEDLINE criteria and limitations

---

## Conclusion

NLM Catalog integration offers **moderate-high value** for aletheia-probe, particularly for biomedical researchers. The **authoritative legitimacy signaling** and **fake MEDLINE claim detection** capabilities justify the **low implementation cost** (1-2 developer days).

### Key Strengths
1. Strong signal strength (rigorous MEDLINE indexing standards)
2. Unique fraud detection (verify MEDLINE claims)
3. Low effort, no database changes
4. Complements biomedical research integrity focus (Retraction Watch)
5. Public domain, stable API

### Key Limitations
1. Domain-specific (70-80% of queries irrelevant)
2. Absence ambiguity (requires careful interpretation)
3. API latency (real-time queries)

### Recommended Action

**Implement as low-priority, biomedical-specific backend:**
- **When**: After core pattern analyzers are robust
- **How**: Query-time API integration (OnlineBackend pattern)
- **Scope**: Phase 1 (basic MEDLINE indexing check)
- **Future**: Enhance based on biomedical user feedback

**If resources limited**: Defer until user demand from biomedical community is clear. Focus on cross-domain improvements (OpenAlex/Crossref pattern analysis) first.

**Alternative**: Implement lightweight "verify-medline" utility for immediate value without full integration.

---

## References and Sources

### NLM Documentation
- [NLM Catalog - Home](https://www.ncbi.nlm.nih.gov/nlmcatalog)
- [E-Utilities API Documentation](https://www.ncbi.nlm.nih.gov/books/NBK25501/)
- [MEDLINE Journal Selection](https://www.nlm.nih.gov/medline/medline_journal_selection.html)
- [NLM Catalog Help](https://www.ncbi.nlm.nih.gov/books/NBK3827/)

### MEDLINE Indexing Standards
- [MEDLINE Selection Process](https://www.nlm.nih.gov/medline/medline_overview.html)
- [Literature Selection Technical Review Committee (LSTRC)](https://www.nlm.nih.gov/lstrc/lstrc.html)
- [MEDLINE Data Element Descriptions](https://www.nlm.nih.gov/bsd/mms/medlineelements.html)

### Predatory Publishing Context
- [Beall's List Criteria - MEDLINE Indexing Indicator](https://beallslist.net/)
- [Think. Check. Submit. - Indexing Databases](https://thinkchecksubmit.org/)
- [COPE Discussion Document: Predatory Publishing](https://publicationethics.org/resources/discussion-documents/predatory-publishing)

### API Technical References
- [E-Utilities Quick Start](https://www.ncbi.nlm.nih.gov/books/NBK25500/)
- [ESearch Documentation](https://www.ncbi.nlm.nih.gov/books/NBK25499/#chapter4.ESearch)
- [ESummary Documentation](https://www.ncbi.nlm.nih.gov/books/NBK25499/#chapter4.ESummary)
- [NLM API Terms and Conditions](https://www.ncbi.nlm.nih.gov/home/about/policies/)
