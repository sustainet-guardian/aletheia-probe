# OpenReview Integration Assessment for Aletheia-Probe

## Context

This assessment evaluates whether integrating [OpenReview](https://openreview.net/) data into aletheia-probe would provide meaningful value for the tool's core mission of detecting predatory journals and conferences.

**What is OpenReview?**

OpenReview is a US 501(c)(3) nonprofit platform (OpenReview Foundation, EIN 99-4025250) providing open and transparent peer review infrastructure for academic venues. It is the de-facto standard submission and review platform for flagship machine learning and AI conferences. Founded at the University of Massachusetts Amherst and now independently operated, it hosts the entire peer review workflow — submissions, reviews, rebuttals, meta-reviews, and decisions — with varying degrees of public transparency depending on venue policy.

Unlike all other data sources considered for aletheia-probe, OpenReview does not contain a journal list, an institution registry, or a citation graph. Instead, it contains the **peer review process itself** as structured data. For venues that use open review, acceptance rates and review quality metrics are directly computable from the API.

**Current Coverage (February 2026):**
- 3,200+ conferences and meetings (including workshops and co-located events)
- 278,000+ paper submissions processed in 2025 alone
- 3.3 million active monthly users
- Platform usage has approximately **doubled each year** for nine consecutive years
- **Journals**: TMLR (Transactions on Machine Learning Research, ISSN 2835-8856) is the primary journal hosted on OpenReview

**Domain Distribution:**
OpenReview's coverage is **heavily concentrated in machine learning, AI, and adjacent fields of computer science**:
- **Fully on OpenReview**: ICLR (since 2013), NeurIPS (~2019+), ICML (2025+), AAAI (2026), UAI, AISTATS, COLM, CVPR, ICCV, ECCV, ACL/EMNLP/NAACL (via ACL Rolling Review), KDD, TheWebConf
- **Also present**: Some venues in computational biology, social computing, and formal methods
- **Essentially absent**: Biology, chemistry, physics, medicine, economics, law, humanities, social sciences, engineering outside of CS

**Data Access:**
- **API v2** (current, all venues 2023+): `https://api2.openreview.net`
- **API v1** (legacy, pre-2023 venues): `https://api.openreview.net`
- **No authentication required** for public read access; authenticated sessions for write operations
- **Python client**: `openreview-py` v1.56.1 (released January 28, 2026), actively maintained, install via `pip install openreview-py`
- **No formal rate limits** documented; community practice suggests delays between bulk requests
- **No complete database dump** available; data retrieved via API pagination

**License and Terms:**
- Terms of Use at `https://openreview.net/legal/terms`
- Submitting authors retain copyright and grant OpenReview a non-exclusive, perpetual, royalty-free hosting license
- Individual articles may carry CC BY 4.0 or other licenses
- **Commercial use**: Not explicitly prohibited at the platform level for venue-level metadata access, but not explicitly permitted either — terms are ambiguous. For reading venue-level statistics (acceptance rates, review counts) rather than paper content, commercial restriction risk is low
- API access for research purposes is well-established and tolerated by the OpenReview team

---

## Deep Analysis: Pros and Cons

### Pros

#### 1. **Genuinely Unique Signals: Peer Review Process Data**

OpenReview provides data that is **unavailable from any other freely accessible source**:

- **Acceptance rates**: Directly computable from submission and decision notes
- **Review score distributions**: Numerical scores per review criterion (soundness, presentation, contribution, overall rating, confidence level — typically on 1–10 or 1–5 scales)
- **Reviewer count per paper**: How many reviewers were assigned (typically 3–5)
- **Review text and length**: Full text accessible at open venues; text length is a proxy for review depth
- **Rebuttal data**: Author responses available, allowing analysis of rebuttal quality and score changes
- **Meta-review data**: Area chair recommendations and justifications
- **Timeline reconstruction**: From `cdate`/`mdate` of notes: submission date → review period → rebuttal → decision; full processing time computable
- **Blinding policy**: Whether a venue uses single-blind, double-blind, or open review

For a tool that assesses conference quality, these signals constitute a **fundamentally different class of evidence** compared to what DBLP, OpenAlex, Crossref, or DOAJ can provide. Those sources tell you *what* was published; OpenReview tells you *how* it was reviewed.

**Signals relevant to legitimacy scoring:**

| Signal | Interpretation |
|--------|---------------|
| Low acceptance rate (10-30%) | Selective conference, positive legitimacy indicator |
| Very high acceptance rate (>60%) | May indicate low selectivity or workshop/demo track |
| Acceptance rate near 100% | Strong negative signal (effectively no selection) |
| Review scores available and non-trivial | Rigorous review process present |
| Long review text (median > 300 words) | Reviews are substantive, not perfunctory |
| High reviewer count per paper (≥ 3) | Standard practice followed |
| Short submission-to-decision timeline | Fast turnaround, potential red flag for vanity conferences |
| Open review policy | Highest transparency tier |

#### 2. **Strong Whitelist Signal for ML/AI Conferences**

Venue creation on OpenReview requires submitting a request form that is manually reviewed by the OpenReview team (`https://openreview.net/group?id=OpenReview.net/Support`). Organizers must agree to terms of service, and all submitting authors must have active OpenReview profiles. This is a light but genuine gatekeeping mechanism.

**Consequence**: A conference present on OpenReview with actual submissions and reviews has almost certainly:
- Operated through a real paper submission and review cycle
- Had authors submit papers through a verified platform
- Not been a pure spam/predatory operation (those do not use transparent review platforms)

This makes OpenReview presence — especially with multiple years of activity — a **strong positive legitimacy signal** for the ML/AI domain, comparable to DBLP indexing but with the added weight of review transparency.

For the specific ML/AI context, a user asking "Is NeurIPS 2024 legitimate?" receives strong confirmation from OpenReview data (25,000+ submissions, ~26% acceptance rate, thousands of reviews published). This cannot be obtained as directly from DBLP.

#### 3. **No False-Positive Legitimacy Risk for Predatory Venues**

Unlike DOAJ (where journals can apply and be accepted if they meet criteria, then later decline in quality) or Wikidata (where anyone notable can appear), OpenReview does not contain predatory conferences. Predatory conferences:
- Operate in opacity, not transparency
- Do not invite independent reviewers (or use fake reviews)
- Would not benefit from an open, auditable review trail
- Would not want their 95% acceptance rate to be discoverable via API

This means the OpenReview signal is highly **precision-safe**: if a conference is on OpenReview with real review data, it is almost certainly not predatory.

#### 4. **Conference-Focused Signal in a Gap Area**

Aletheia-probe's conference assessment capabilities are its weaker area compared to journal assessment. The existing conference backends are DBLP (indexed conferences whitelist) and kscien predatory conferences (blacklist). OpenReview would add a **quantitative process quality dimension** currently absent from conference assessment:

- DBLP says: "this conference exists and is indexed"
- OpenReview would add: "this conference has a 23% acceptance rate across 12,000 submissions, with median review length 450 words"

This is a qualitatively richer signal for researchers asking "how rigorous is this ML conference?"

#### 5. **Well-Maintained, Freely Accessible Python Client**

The `openreview-py` package (v1.56.1 as of January 2026) is actively maintained by the OpenReview team itself with frequent releases. Integration patterns are well-documented. No API key is required for public reads. The REST API is clean and consistent.

```python
import openreview

# Unauthenticated client for public data
client = openreview.api.OpenReviewClient(
    baseurl="https://api2.openreview.net"
)

# Get a venue
venue = client.get_group(id="ICLR.cc/2025/Conference")

# Get all submissions
submissions = client.get_all_notes(
    invitation="ICLR.cc/2025/Conference/-/Submission"
)

# Get decisions and compute acceptance rate
decisions = client.get_all_notes(
    invitation="ICLR.cc/2025/Conference/-/Decision"
)
accepted = [d for d in decisions
            if "Accept" in d.content.get("decision", "")]
acceptance_rate = len(accepted) / len(submissions)
```

The existing `ApiBackendWithCache` pattern in aletheia-probe fits this integration well.

#### 6. **Academic Precedent for Quality Research**

OpenReview data has been used in numerous published studies to assess conference quality, reviewer behavior, and peer review rigor — demonstrating that the data is reliable enough for academic research:

- Wang et al. (2023), *World Wide Web*: "What Have We Learned from OpenReview?" — ICLR 2017–2022 analysis
- "Insights from the ICLR Peer Review and Rebuttal Process" (arXiv:2511.15462, Nov 2025) — 28,358 submissions, 2017–2025
- "Paper Copilot: Tracking the Evolution of Peer Review in AI Conferences" (arXiv:2510.13201, Oct 2025)
- The berenslab/iclr-dataset (55,906 ICLR submissions 2017–2026 with full metadata)

This research base validates the signal quality and demonstrates that the data model is stable enough for longitudinal analysis.

---

### Cons

#### 1. **Extreme Domain Limitation: ML/AI Only**

**The single most critical limitation**: OpenReview is functionally useful only for machine learning and AI conferences. For any query outside this domain, OpenReview returns nothing.

**Estimated domain coverage for aletheia-probe queries:**

| Domain | OpenReview Coverage | Estimated % of aletheia-probe Queries |
|--------|---------------------|---------------------------------------|
| ML / AI / Deep Learning | Near 100% of major venues | ~10% |
| Computer Vision | ~60-70% | ~5% |
| NLP / Computational Linguistics | ~80% (via ARR) | ~5% |
| General CS / Software Engineering | ~10-15% | ~10% |
| Biomedical / Health Informatics | <5% | ~15% |
| Physics / Chemistry / Biology | <1% | ~15% |
| Social Sciences / Economics | <3% | ~10% |
| Engineering (non-CS) | <2% | ~10% |
| Humanities / Arts | ~0% | ~5% |
| Predatory conferences (any domain) | ~0% | ~15% |

**Estimated overall query coverage: ~15-25% would find an OpenReview entity; ~5-10% would find data of genuine utility.**

This is a more severe domain restriction than NLM Catalog (20-30% biomedical queries), which at least has a systematically defined scope.

#### 2. **Cannot Detect Predatory Conferences (Wrong Tool)**

OpenReview is a **whitelist by design and by nature** — predatory and spam conferences simply are not on it. This means it cannot help with the core detection mission for the queries that matter most:

- A user asking "Is [suspicious spam conference] legitimate?" → OpenReview returns nothing → completely uninformative
- A user asking "Is ICLR legitimate?" → already known; DBLP and OpenAlex already provide strong confirmation

For the hardest queries (genuinely suspicious venues), OpenReview provides zero signal. For the easy queries (major established ML conferences), OpenReview provides strong confirmation of something already known.

#### 3. **Venue Name Resolution Is Not Supported**

OpenReview has no free-text search for venues. Lookup requires knowing the **structured venue group ID** (e.g., `ICLR.cc/2025/Conference`, `NeurIPS.cc/2024/Conference`). There is no API endpoint for "find the venue for ICLR 2024."

For a user query of "ICLR" or "International Conference on Learning Representations", the integration requires:
1. A maintained **lookup table** mapping conference abbreviations and names to their OpenReview group ID prefixes
2. Versioned entries for each year (ICLR 2023, 2024, 2025 have different group IDs)
3. Handling of workshop vs. main conference track disambiguation

This lookup table must be **manually maintained** as new venues join OpenReview, adding ongoing maintenance burden not present with DBLP (which uses DBLP's own identifiers) or OpenAlex (which has text search).

**Example lookup table complexity:**

```python
OPENREVIEW_VENUE_MAP = {
    "iclr": ["ICLR.cc/{year}/Conference"],
    "neurips": ["NeurIPS.cc/{year}/Conference"],
    "icml": ["ICML.cc/{year}/Conference"],
    "aaai": ["AAAI.org/{year}/Conference"],
    "cvpr": ["thecvf.com/CVPR/{year}"],
    "naacl": ["aclweb.org/NAACL/{year}/Conference"],
    # ... dozens more, each needing year-range validation
}
```

Each year's venue ID must be verified, and new conferences joining OpenReview require table updates.

#### 4. **API v1 / v2 Split Adds Implementation Complexity**

OpenReview operates two concurrent API versions with different data structures:
- **API v2** (`https://api2.openreview.net`): All venues 2023+; uses `openreview.api.OpenReviewClient`
- **API v1** (`https://api.openreview.net`): Pre-2023 venues; uses `openreview.Client`; different Note schema

A complete integration must handle both APIs. Detecting which version a venue uses requires:

```python
venue_group = client_v2.get_group(id="ICLR.cc/2023/Conference")
is_v2 = hasattr(venue_group, 'domain') and venue_group.domain is not None
# If False: use client_v1 for this venue
```

ICLR historical data (2017–2022) requires API v1; ICLR 2023+ uses API v2. Any implementation that covers historical data must maintain both client instances.

#### 5. **Security Incidents and Infrastructure Reliability**

OpenReview had a **major security incident in November 2025**: an API bug exposed reviewer identities for all conferences on the platform, enabling de-anonymization of reviews for 45% of ICLR 2026 papers. The bug was patched within an hour, but the data had already been scraped and circulated. The ICLR 2026 blog response confirms the incident.

While the specific bug was patched, this reveals:
- OpenReview's **8-person team** operates critical infrastructure with limited security engineering resources
- API authentication checks were inadequate for sensitive operations
- The platform is under significant stress from exponential growth

The NeurIPS Foundation's $500,000 donation (December 2025) was explicitly made to strengthen security and scale the team — indicating the infrastructure challenge is recognized but not yet fully resolved.

For aletheia-probe, this means:
- **API availability is not guaranteed** (graceful degradation is mandatory)
- Querying reviewer assignment data should be avoided even if technically accessible
- The platform's stability should be monitored

#### 6. **Acceptance Rate Signal Has Nuances**

Acceptance rates are computable but require careful interpretation:

- **Main track vs. workshop**: Main conference tracks have strict acceptance rates (ICLR 2025: ~20-22%); co-located workshops may have 50%+ acceptance. If a user queries "ICLR Workshop on [X]", the acceptance rate is not a quality signal for the main conference.
- **Desk rejection vs. full review**: Many venues desk-reject papers before review. Whether the acceptance rate includes desk-rejects affects interpretation.
- **Year-over-year variation**: As submission volumes explode, acceptance rates at top venues are declining while total accepted papers grow.
- **Domain-specific baselines**: A 40% acceptance rate at a specialized workshop is not the same as 40% at a main conference.
- **Gaming**: Researchers have raised concerns that some venues inflate rejection rates by encouraging unready submissions.

For simple acceptance-rate heuristics, the signal is useful but must be presented with appropriate context, not as a binary good/bad signal.

#### 7. **Acceptance Rate Is Available for <50% of OpenReview Venues**

Not all OpenReview venues publish decisions. Some venues:
- Use OpenReview only for submission management, not for publishing reviews/decisions
- Have acceptance decisions that are not accessible to the public
- Are in review period (no decisions yet)

For NeurIPS specifically, reviews are released only after decisions. For CVPR, some data is restricted. Only fully open-review venues (ICLR, TMLR, some workshops) make the complete review + decision workflow public.

---

## Integration Effort Estimate

**Medium Effort: 3–5 developer days** for a basic conference presence + acceptance rate backend.

### Breakdown

#### Day 1: Venue Lookup Table and API Client Setup

**Core infrastructure challenge**: Build and validate the conference name → OpenReview group ID mapping.

```python
# New file: src/aletheia_probe/backends/openreview_backend.py

# Lookup table structure
OPENREVIEW_VENUES: dict[str, dict] = {
    "iclr": {
        "prefix": "ICLR.cc",
        "pattern": "ICLR.cc/{year}/Conference",
        "years": range(2013, 2027),
        "aliases": [
            "international conference on learning representations",
            "iclr",
        ],
    },
    "neurips": {
        "prefix": "NeurIPS.cc",
        "pattern": "NeurIPS.cc/{year}/Conference",
        "years": range(2019, 2027),  # OpenReview start year
        "aliases": [
            "neural information processing systems",
            "nips",
            "neurips",
        ],
    },
    "icml": {
        "prefix": "ICML.cc",
        "pattern": "ICML.cc/{year}/Conference",
        "years": range(2025, 2027),  # Recent start
        "aliases": ["international conference on machine learning", "icml"],
    },
    # ... add AAAI, CVPR, ICCV, ECCV, ACL, EMNLP, NAACL/ARR, TMLR, ...
}
```

Initial table can seed ~20 major ML/AI conferences (covers ~90% of meaningful ML/AI conference queries).

#### Day 2: Backend Implementation

**File:** `src/aletheia_probe/backends/openreview_backend.py`

- Create `OpenReviewBackend` extending `ApiBackendWithCache`
- Lookup by normalized conference name → venue group ID
- Query `get_group()` for venue existence (fast, single API call)
- Cache result (30-day TTL; conference metadata changes slowly)
- Optionally compute acceptance rate (slower; requires fetching all decisions)
- Return `BackendResult` with `AssessmentType.LEGITIMATE` and acceptance rate metadata
- Add `openreview-py` to project dependencies

**Assessment logic:**

```python
@dataclass
class OpenReviewVenueInfo:
    venue_id: str
    exists: bool
    submission_count: int | None = None
    accepted_count: int | None = None
    acceptance_rate: float | None = None
    review_policy: str | None = None  # "open", "blind", "double_blind"
    has_reviews_public: bool = False
    oldest_year: int | None = None
    newest_year: int | None = None
```

#### Day 3: Two-Tier Query Design

**Fast path** (for presence check only, <500ms):
1. Normalize input conference name
2. Lookup in `OPENREVIEW_VENUES` table
3. Call `client.get_group(id=venue_id)` for most recent year
4. Return `LEGITIMATE` if found, `NOT_FOUND` if not

**Slow path** (for acceptance rate, opt-in, 5-30 seconds per venue):
1. Fetch submissions and decisions
2. Compute acceptance rate
3. Cache result (acceptance rates don't change after conference ends)

The slow path should be optional or deferred — not run during interactive assessment.

#### Days 4–5: Testing, Dependency Addition, Documentation

- Add `openreview-py>=1.56` to `pyproject.toml` / `setup.cfg`
- Unit tests: mock API responses for venue found/not found, API v1/v2 routing
- Integration tests: real API calls against a stable venue (ICLR 2023)
- Document the domain limitation prominently in backend metadata
- Documentation: `dev-notes/integration/openreview.md`

### Database Impact

If using query-time API (no dump): No database changes needed beyond standard cache tables used by existing API backends.

Optional cache for acceptance rates:

```sql
CREATE TABLE openreview_acceptance_cache (
    venue_id TEXT PRIMARY KEY,
    submission_count INTEGER,
    accepted_count INTEGER,
    acceptance_rate REAL,
    review_policy TEXT,
    computed_at TIMESTAMP,
    ttl_days INTEGER DEFAULT 365  -- rates don't change post-conference
);
```

---

## Expected Coverage and Benefit Rate

### Coverage Analysis

| Query Type | OpenReview Coverage | Estimated % of aletheia-probe Queries |
|------------|---------------------|---------------------------------------|
| ICLR, NeurIPS, ICML, AAAI, top ML/AI | 100% | ~5% |
| Major CS conferences (ACM, IEEE) | ~10-20% (those using OpenReview) | ~15% |
| NLP conferences (via ACL Rolling Review) | ~80% | ~3% |
| Computer vision conferences | ~60% (main venues on OpenReview) | ~3% |
| Domain conferences outside CS | ~0-5% | ~30% |
| Journals (except TMLR) | ~0% | ~25% |
| Predatory conferences | ~0% | ~10% |
| Workshops / co-located events | Partial (some on OpenReview) | ~5% |
| Unknown / new venues | ~0% | ~4% |

**Estimated overall entity-found rate: ~15-25% of aletheia-probe conference queries**

**Estimated unique-value rate (adds something beyond DBLP + OpenAlex): ~8-15% of all queries**

For a tool serving a general academic audience, roughly 80-90% of conference queries receive no benefit from OpenReview. For a tool serving specifically the ML/AI research community, coverage rises to ~50-70% of venue queries.

### Benefit Rate by Query Type

**High benefit (presence + acceptance rate):**
- User queries a major ML/AI conference name
- OpenReview confirms venue exists with N years of history + acceptance rate
- Adds quantitative quality dimension not available from other backends
- ~5-10% of all aletheia-probe queries

**Medium benefit (presence only, rate unavailable):**
- Conference is on OpenReview but decisions not public
- Confirms legitimacy without acceptance rate
- ~5% of all queries

**No benefit (not found, but query is legitimate):**
- Non-ML/AI conference, not on OpenReview
- Absence means nothing
- ~50-60% of queries

**No benefit (predatory/suspicious conferences):**
- Not on OpenReview (predatory venues never use it)
- ~10-15% of queries

**Net unique high-value benefit: ~5-10% of queries** (compared to existing backends)

### Comparison to Existing Backends

| Backend | Conference Coverage | Direct Predatory Signal | Unique Value |
|---------|---------------------|------------------------|--------------|
| DBLP (`dblp_venues`) | Broad CS/IT, all years | None (whitelist only) | Broad whitelist |
| kscien predatory conferences | Predatory conferences | Strong | Explicit blacklist |
| OpenAlex Analyzer | All fields, patterns | Heuristic | Citation/volume patterns |
| **OpenReview** | **ML/AI only, deep** | **None (whitelist only)** | **Acceptance rate, review quality** |

---

## Critical Assessment: Alignment with Mission

### Aletheia-Probe's Core Mission

From README.md:
> "A command-line tool for evaluating the **legitimacy** of academic journals and conferences. By aggregating data from authoritative sources and applying advanced pattern analysis, it helps researchers, librarians, and institutions **detect predatory venues** and ensure the integrity of scholarly publishing."

### How OpenReview Relates

**What OpenReview provides:**
- Strong legitimacy confirmation for ML/AI conferences present on the platform
- Quantitative peer review process quality metrics (acceptance rate, review scores)
- Temporal venue history (multiple years of activity = established venue)
- Review policy transparency (open vs. blind vs. double-blind)

**What OpenReview does NOT provide:**
- Any signal for predatory conference detection (wrong tool)
- Coverage for non-ML/AI fields (70-85% of queries unaffected)
- Journal assessment (except TMLR)
- Free-text venue search (requires maintained lookup table)

### Mission Alignment Score: **Moderate (5.5/10)**

**Aligned aspects:**
- Legitimacy confirmation for one of the most-queried domains in academic tool use (ML/AI researchers are heavy tool users)
- Provides peer review quality signals aligning with research integrity mission
- Acceptance rate and review transparency are genuine quality indicators
- No false-positive risk (predatory venues not present)
- Unique capability not available from any other free source

**Misaligned aspects:**
- Zero direct predatory detection capability
- Domain restriction (70-85% of queries irrelevant)
- Absence is completely uninformative
- Easiest queries (ICLR, NeurIPS) are already confirmed legitimate by DBLP
- Hardest queries (suspicious new venues) receive no signal

### The Core Tension

OpenReview is most valuable for the **subset of queries where legitimacy confirmation is already clear from other sources**. The ML/AI conferences on OpenReview (ICLR, NeurIPS, etc.) are also indexed in DBLP, have thousands of OpenAlex works, and appear in Crossref. OpenReview adds depth to already-strong signals.

For aletheia-probe's **primary challenge** — detecting ambiguous or suspicious venues — OpenReview provides nothing. This is the opposite of what NLM Catalog provides (a unique fraud-detection capability for a narrow domain).

---

## Recommendation: EXPERIMENTAL / LOW PRIORITY

### Summary

After deep analysis, OpenReview integration is recommended as a **low-priority, experimental, ML/AI-specific supplementary backend**. The user's assessment of "Experimentell" is precisely correct.

The case for integration rests on two genuine strengths: a unique signal (acceptance rate + review quality) that is unavailable anywhere else, and a strong whitelist signal for the single most active user community (ML/AI researchers). The case against is driven by domain limitation and the fundamental mismatch with predatory detection.

### Key Reasoning

**For inclusion (weak case for experimental implementation):**

1. **Unique signal not available elsewhere**: Acceptance rate and peer review process transparency cannot be obtained from DBLP, OpenAlex, Crossref, or any other backend. This is a genuine data gap that OpenReview fills.

2. **ML/AI community is aletheia-probe's most active user segment**: The tool's existing DBLP and OpenAlex backends strongly suggest a CS-oriented user base. ML/AI researchers are the most likely to query conference legitimacy tools.

3. **Zero false-positive risk**: OpenReview presence implies genuine peer review. Unlike DOAJ (journals can be delisted) or DBLP (any indexed venue), OpenReview venues have demonstrable review history.

4. **Low implementation barrier**: `openreview-py` is well-maintained, requires no API key, and the integration pattern fits existing aletheia-probe architecture.

5. **Innovative for the tool**: No existing journal/conference assessment tool uses peer review process data as a quality signal. This would be genuinely novel.

**Against inclusion (reasons for caution):**

1. **No predatory detection capability**: Cannot help with the tool's primary mission.

2. **Heavy domain restriction**: 70-85% of queries receive no benefit.

3. **Venue lookup table maintenance**: Manual effort required to track OpenReview venue IDs as new conferences join.

4. **Infrastructure concerns**: 8-person nonprofit team, recent security incident, exponential growth pressure.

5. **The easy queries don't need it**: Any ML/AI researcher who queries ICLR or NeurIPS already knows they're legitimate. The value is informational enrichment, not fraud prevention.

### Implementation Recommendation

If pursued, implement as a **two-tier feature**:

**Tier 1: Venue presence check** (fast, always-on)
- Map common ML/AI conference names to OpenReview group IDs
- Return `LEGITIMATE` with venue existence confirmation
- ~500ms per lookup; cache 30 days
- Clear documentation: "Only covers ML/AI conferences using OpenReview"

**Tier 2: Acceptance rate computation** (optional, off by default)
- Fetch submission + decision counts
- Return acceptance rate as metadata (not as legitimacy score — it's a quality enrichment, not a binary signal)
- Enable via configuration: `openreview.compute_acceptance_rate: true`
- Not recommended for interactive use (5-30 seconds)

### When to Implement

Defer until:
1. **User demand from ML/AI community** confirms value (survey or feedback)
2. **Conference assessment coverage** is identified as a gap by users
3. **Maintenance volunteer available** to keep the venue lookup table current
4. **OpenReview infrastructure stabilizes** post the 2025 security incident growth

Do NOT implement before:
- Core predatory detection improvements (OpenAlex pattern analysis, additional blacklists)
- NLM Catalog integration (higher value-to-effort ratio for biomedical domain)
- Conference assessment enhancement via kscien or other direct blacklists

---

## Technical Integration Approach

### Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│  User Query: Conference Name (e.g., "ICLR", "NeurIPS 2024")        │
└────────────────────────────────────────────────────────────────────┘
                            ↓
┌────────────────────────────────────────────────────────────────────┐
│  OpenReviewBackend (ApiBackendWithCache)                            │
│  1. Normalize conference name                                       │
│  2. Lookup in OPENREVIEW_VENUES table                              │
│  3. Determine venue ID and API version (v1 or v2)                  │
│  4. Call get_group(id=...) → verify existence                      │
│  5. Optional: compute acceptance rate (from decisions/submissions)  │
│  6. Cache result (30-day TTL for presence; 365-day for rates)      │
│  7. Graceful degradation: timeout/unavailable → NOT_FOUND          │
└────────────────────────────────────────────────────────────────────┘
                            ↓
┌────────────────────────────────────────────────────────────────────┐
│  OpenReview API v2 (or v1 for pre-2023 venues)                     │
│  https://api2.openreview.net                                        │
│  - get_group(id=venue_id) — venue existence                         │
│  - get_all_notes(invitation=...) — submissions/decisions            │
│  No authentication required for public venues                       │
└────────────────────────────────────────────────────────────────────┘
                            ↓
┌────────────────────────────────────────────────────────────────────┐
│  Response Interpretation                                             │
│  - Venue exists → LEGITIMATE with metadata                          │
│    (years active, most recent year, acceptance rate if computed)    │
│  - Venue not found → NOT_FOUND (strictly neutral)                   │
│  - Out-of-domain query → NOT_APPLICABLE (documented limitation)     │
└────────────────────────────────────────────────────────────────────┘
```

### Code Structure

Following existing backend patterns:

```
src/aletheia_probe/
├── backends/
│   └── openreview_backend.py        # Backend query logic + venue table
└── config.py                        # Add openreview.compute_acceptance_rate config
dev-notes/
└── integration/
    └── openreview.md                # Integration documentation
```

### Example Assessment Output

**Scenario 1: Well-established ML conference with open review**
```
Conference: ICLR 2025
Assessment: LEGITIMATE

Evidence:
✓ OpenReview: Venue present (active since 2013, 12 consecutive years)
  Acceptance rate: 22.1% (2,650 accepted / 12,000+ submissions)
  Review policy: Double-blind, publicly open post-decision
  Reviewers per paper: typically 3-4
✓ DBLP: Venue indexed (all years 2013-2025)
✓ OpenAlex: 2,650+ papers, established citation record

Note: Acceptance rate from OpenReview reflects 2025 main track only.
Confidence: 0.98
```

**Scenario 2: Suspicious ML conference not on OpenReview**
```
Conference: International Journal of Advanced AI (suspicious)
Assessment: SUSPICIOUS (from other backends)

OpenReview:
⚠️ Not found on OpenReview (not using transparent peer review platform)
  Note: Absence is neutral — most conferences are not on OpenReview.
  However, for a conference claiming ML/AI focus in 2025, absence
  from OpenReview may be a minor soft negative signal.

Other backends provide primary assessment signals.
Note: OpenReview data not applicable for this venue.
```

**Scenario 3: Query outside ML/AI domain**
```
Conference: European Conference on Cardiology (medical)
Assessment: [from other backends]

OpenReview:
ℹ️ Not applicable — OpenReview covers ML/AI conferences only.
  This medical conference is outside OpenReview's scope.
  No signal (positive or negative) can be derived from absence.
```

---

## Risks and Mitigations

### Risk 1: Infrastructure Unavailability (Nonprofit Scale)
**Risk**: OpenReview's 8-person team runs critical infrastructure; outages possible
**Mitigation**:
- Mandatory graceful degradation: `NOT_FOUND` on any API failure
- Cache aggressively (30-day TTL; 365 days for static acceptance rates)
- Place OpenReview last in fallback chain — only queried after local backends succeed

### Risk 2: API Breaking Changes
**Risk**: API v1 → v2 migration happened; future breaking changes possible
**Mitigation**:
- Version-specific query routing (already handles v1/v2)
- Follow OpenReview mailing list / release notes
- Limit integration scope to stable endpoints (get_group, get_all_notes)

### Risk 3: Venue Lookup Table Staleness
**Risk**: New conferences join OpenReview; lookup table becomes incomplete
**Mitigation**:
- Table starts with ~20 most-queried ML/AI conferences (covers 90% of domain)
- Documentation: users can report missing venues
- Quarterly review of new OpenReview venues (the 3,200 venues total; only ~20-50 are high-traffic)
- Consider auto-discovery: query `get_all_groups(prefix=conference_name_guess)` as fallback

### Risk 4: Acceptance Rate Misinterpretation
**Risk**: Users interpret acceptance rate as binary good/bad signal
**Mitigation**:
- Never use acceptance rate as a `LEGITIMATE`/`SUSPICIOUS` trigger
- Present as enrichment metadata with context: "22% acceptance rate (main track)"
- Include year and caveat: "rates have declined as submission volumes grew"
- Document that workshop tracks have higher rates

### Risk 5: Security Incidents Affecting Data Integrity
**Risk**: API bugs (as in Nov 2025) might expose or corrupt data
**Mitigation**:
- Only read public venue metadata, never reviewer-to-paper assignments
- Cache prevents re-querying potentially compromised data
- Read-only access eliminates write-side risk

---

## Conclusion

OpenReview is a **pioneering resource for peer review transparency** in the machine learning community. It offers genuinely novel signals — acceptance rate, review quality metrics, review policy transparency — that are unavailable from any other freely accessible source. For ML/AI conference queries, it provides a depth of evidence that complements and enriches what DBLP and OpenAlex can provide.

However, its profound domain restriction (ML/AI only) and its fundamental incompatibility with predatory conference detection (predatory venues never use transparent review platforms) limit its value for aletheia-probe's primary mission.

### Key Strengths
1. Unique signal: acceptance rate + peer review process quality (no other free source)
2. Strong whitelist signal for ML/AI: presence implies genuine review cycle
3. Active Python client, no auth required, clean API
4. Innovative: no other conference assessment tool uses peer review data
5. Research-validated data quality (multiple published studies)

### Key Limitations
1. Zero predatory detection capability — wrong tool for the primary mission
2. Domain restriction: 70-85% of aletheia-probe queries are irrelevant
3. Absence is uninformative — cannot be used as negative signal
4. Venue lookup requires maintained name-to-ID table
5. API v1/v2 split adds implementation complexity
6. Infrastructure uncertainty (small nonprofit, recent security incident)

### Recommended Action

**Implement experimentally as a low-priority, opt-in supplementary backend:**

- Scope: ~20 major ML/AI conferences in initial venue table
- Tier 1 only (presence check): 1–2 developer days; low risk
- Tier 2 (acceptance rate): defer until user demand is clear; adds 1 day
- Document domain limitation prominently
- Position as "enrichment for ML/AI queries" not "predatory detection"

**Priority order**: Implement only after:
- NLM Catalog integration (higher value-per-effort)
- Additional predatory conference blacklists
- OpenAlex/Crossref pattern analysis improvements

**Long-term potential**: If aletheia-probe develops a dedicated ML/AI research community use case, OpenReview becomes significantly more valuable — offering the tool unique positioning as the only journal/conference assessor that incorporates peer review process quality metrics.

---

## References and Sources

### OpenReview Documentation
- [OpenReview API v2 Reference](https://docs.openreview.net/reference/api-v2)
- [Using the API](https://docs.openreview.net/getting-started/using-the-api)
- [OpenAPI Definition](https://docs.openreview.net/reference/api-v1/openapi-definition)
- [Introduction to Notes](https://docs.openreview.net/getting-started/objects-in-openreview/introduction-to-notes)
- [Introduction to Groups](https://docs.openreview.net/getting-started/objects-in-openreview/groups)
- [How to Check the API Version of a Venue](https://docs.openreview.net/how-to-guides/data-retrieval-and-modification/how-to-check-the-api-version-of-a-venue)
- [Creating a New Venue](https://docs.openreview.net/getting-started/hosting-a-venue-on-openreview/creating-your-venue-instance-submitting-a-venue-request-form)
- [OpenReview Venue Directory](https://openreview.net/venues)
- [OpenReview Terms of Use](https://openreview.net/legal/terms)

### Python Client
- [openreview-py on PyPI](https://pypi.org/project/openreview-py/)
- [openreview-py on GitHub](https://github.com/openreview/openreview-py)
- [openreview-py Documentation](https://openreview-py.readthedocs.io/)

### Research Using OpenReview Data
- [What have we learned from OpenReview? (Wang et al., 2023)](https://arxiv.org/abs/2103.05885)
- [Insights from the ICLR Peer Review and Rebuttal Process (arXiv:2511.15462, 2025)](https://arxiv.org/pdf/2511.15462)
- [Paper Copilot: Tracking the Evolution of Peer Review in AI Conferences (arXiv:2510.13201, 2025)](https://arxiv.org/abs/2510.13201)
- [OpenReview Should be Protected and Leveraged as Community Asset (arXiv:2505.21537, 2025)](https://arxiv.org/abs/2505.21537)
- [An Open Review of OpenReview (ICLR 2017-2020 analysis)](https://openreview.net/forum?id=Cn706AbJaKW)
- [ICLR Dataset (berenslab, 2017–2026, 55,906 submissions)](https://github.com/berenslab/iclr-dataset)

### Platform Events and Infrastructure
- [ICLR 2026 Response to Security Incident (November 2025)](https://blog.iclr.cc/2025/12/03/iclr-2026-response-to-security-incident/)
- [NeurIPS Foundation $500k Donation to OpenReview (December 2025)](https://blog.neurips.cc/2025/12/15/supporting-our-communitys-infrastructure-neurips-foundations-donation-to-openreview/)
- [OpenReview API Bug Exposed Anonymous Peer Reviewers (2025)](https://www.ctol.digital/news/openreview-api-bug-exposed-anonymous-peer-reviewers-academic-publishing-crisis/)
- [TMLR — Transactions on Machine Learning Research on OpenReview](https://openreview.net/group?id=TMLR)
