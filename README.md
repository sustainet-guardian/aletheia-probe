# Aletheia-Probe: Automated Integrity Checks for Academic Journals & Conferences

[![CI/CD Pipeline](https://github.com/sustainet-guardian/aletheia-probe/actions/workflows/ci.yml/badge.svg)](https://github.com/sustainet-guardian/aletheia-probe/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.17788487.svg)](https://doi.org/10.5281/zenodo.17788487)

Aletheia-Probe is a command-line tool for evaluating the legitimacy of academic journals and conferences. By aggregating data from authoritative sources and applying advanced pattern analysis, it helps researchers, librarians, and institutions detect predatory venues and ensure the integrity of scholarly publishing.

**Dual-Purpose Tool**: Aletheia-Probe serves both individual researchers checking publication venues and as research infrastructure for empirical studies on scholarly publishing. Beyond individual use, the tool supports systematic literature reviews, bibliometric analysis, and meta-research workflows leveraging 240M+ publication records. For detailed research applications, see the [Research Applications Guide](docs/research-applications.md).

**Setting Realistic Expectations**: If you are an honest researcher using established, well-known journals and conferences through major search engines and databases, you will likely never encounter predatory venues. This tool functions like a virus scanner for academic publishing—you should have it installed and running, but hopefully never receive any warnings. It's designed to catch the edge cases and protect against the less obvious threats that might slip through normal research workflows.

**About the Name**: The name "Aletheia" (ἀλήθεια) comes from ancient Greek philosophy, where it represents the concept of truth and unconcealment. In Greek mythology, Aletheia was personified as the goddess or spirit (daimona) of truth and sincerity. This reflects the tool's core mission: to reveal the truth about academic journals and conferences, helping researchers distinguish legitimate venues from predatory ones.

## System Requirements

Aletheia-Probe requires external system dependencies beyond Python. Before installation, ensure your system has the required programs installed. Platform-specific installation instructions are available in the [Quick Start Guide](docs/quick-start.md#system-requirements).

**Required System Dependencies:**
- **Git** - Required for retraction data synchronization
- **Python 3.10+** - Runtime environment

## TL;DR

Aletheia-Probe helps answer two critical questions for researchers:

1.  **Is the journal I want to publish in legitimate?**
    ```bash
    aletheia-probe journal "Journal of Computer Science"
    ```
2.  **Are the references in my paper legitimate?**
    ```bash
    aletheia-probe bibtex references.bib
    ```

```bash
# Install from PyPI or source

# Option 1: Install from PyPI (recommended)
pip install aletheia-probe

# Option 2: Install from source (for development)
git clone https://github.com/sustainet-guardian/aletheia-probe.git
cd aletheia-probe
pip install -e .

# First time: Sync data sources (takes a few minutes)
aletheia-probe sync

# Check the current state of the cache database
aletheia-probe status

# Assess a single journal
aletheia-probe journal "Journal of Computer Science"

# Assess all journals in a BibTeX file (returns exit code 1 if predatory journals found)
aletheia-probe bibtex references.bib

# Get detailed analysis with confidence scores from multiple sources
aletheia-probe journal --format json "Nature Reviews Drug Discovery"
```

**Output**: Combines data from multiple authoritative sources and advanced pattern analysis to provide confidence-scored assessments of journal legitimacy.

**Note**: The first sync downloads and processes data from multiple sources (DOAJ, Beall's List, UGC-CARE discontinued lists, etc.), which takes a few minutes. After that, queries typically complete in under 5 seconds.

## Data Sources

This tool acts as a **data aggregator** - it doesn't provide data itself, but combines information from multiple authoritative sources:

- **DOAJ** - Directory of Open Access Journals
- **Beall's List** - Historical predatory journal archives
- **UGC-CARE Cloned (Group I)** - UGC-CARE discontinued cloned journal list
- **UGC-CARE Cloned (Group II)** - UGC-CARE discontinued cloned journal list
- **UGC-CARE Delisted (Group II)** - UGC-CARE discontinued delisted journal list
- **UGC-CARE Included from Clone Page (Group I/II)** - Left-side included journals from public clone-correction pages
- **Algerian Ministry** - Algerian Ministry of Higher Education predatory journals list
- **OpenAlex** - Publication pattern analysis
- **Crossref** - Metadata quality assessment
- **Retraction Watch** - Journal retraction history analysis
- **Scopus** - Optional premium journal database
- **Institutional Lists** - Custom whitelist/blacklist configurations
- **Cross-Validator** - Cross-source consistency validation system
- **Kscien Standalone Journals** - Individual predatory journals identified by Kscien
- **Kscien Publishers** - Known predatory publishers
- **Kscien Hijacked Journals** - Legitimate journals that have been hijacked by predatory actors
- **Kscien Predatory Conferences** - Database of predatory conferences
- **DBLP Venues** - Curated computer science journals and conference series from DBLP XML
- **CORE Conferences (ICORE/CORE)** - Ranked conference venues from the CORE portal
- **CORE Journals (legacy)** - Ranked journals from the CORE journal portal (latest list: CORE2020)

The tool analyzes publication patterns, citation metrics, and metadata quality to provide comprehensive coverage beyond traditional blacklist/whitelist approaches.

**Note on Conference Assessment**: Conference checking now combines curated predatory conference signals (Kscien) with curated legitimacy signals from DBLP and CORE/ICORE ranked venues. Coverage is strongest for computer science venues.

## Quick Start

See the [Quick Start Guide](docs/quick-start.md) for installation and basic usage examples.

## Assessment Methodology

The tool uses a **hybrid approach** combining curated databases with advanced pattern analysis to achieve comprehensive coverage and high accuracy.

### Backend Types

#### **Curated Databases** (High Trust)
These provide authoritative yes/no decisions for journals they cover:

| Backend | Type | Coverage | Purpose |
|---------|------|----------|---------|
| **DOAJ** | Legitimate OA journals | 22,000+ journals | Gold standard for open access legitimacy |
| **Scopus** (optional) | Legitimate indexed journals | 30,000+ journals | Major subscription and OA journals |
| **Beall's List** | Predatory journal archives | ~2,900 entries | Historically identified predatory publishers |
| **UGC-CARE Cloned (Group I)** | Cloned journals | ~80 entries | Public UGC-CARE discontinued Group I clone list |
| **UGC-CARE Cloned (Group II)** | Cloned journals | ~114 entries | Public UGC-CARE discontinued Group II clone list |
| **UGC-CARE Delisted (Group II)** | Delisted journals | ~12 entries | Public UGC-CARE discontinued Group II delisted list |
| **UGC-CARE Included from Clone Page (Group I)** | Included journals | ~80 entries | Left-side included journals from Group I clone-correction page |
| **UGC-CARE Included from Clone Page (Group II)** | Included journals | ~114 entries | Left-side included journals from Group II clone-correction page |
| **PredatoryJournals.org** | Predatory journals/publishers | 15,000+ entries | Curated lists from predatoryjournals.org |
| **Algerian Ministry** | Predatory journal list | ~3,300 entries | Ministry of Higher Education predatory journals |
| **Kscien Standalone Journals** | Predatory journals | 1,400+ entries | Individual predatory journals identified by Kscien |
| **Kscien Publishers** | Predatory publishers | 1,200+ entries | Known predatory publishers |
| **Kscien Hijacked Journals** | Hijacked journals | ~200 entries | Legitimate journals compromised by predatory actors |
| **Kscien Predatory Conferences** | Predatory conferences | ~450 entries | Identified predatory conference venues |
| **DBLP Venues** | Legitimate venues (CS) | dump-derived | Curated DBLP journals and conference series from local XML cache |
| **CORE Conferences** | Legitimate ranked conferences | ~825 entries (ICORE2026 ranked) | CORE/ICORE conference rankings portal |
| **CORE Journals (legacy)** | Legitimate ranked journals | ~582 entries (CORE2020 ranked) | CORE journal rankings portal (discontinued, no post-2020 updates) |
| **Retraction Watch** | Quality indicator | ~27,000 journals | Retraction rates and patterns for quality assessment |
| **Institutional Lists** | Custom whitelist/blacklist | Organization-specific | Local policy enforcement |

#### **Pattern Analysis** (Evidence-Based)
These analyze publication patterns and metadata quality to detect predatory characteristics:

| Backend | Data Source | What It Analyzes | Key Indicators |
|---------|-------------|------------------|----------------|
| **OpenAlex Analyzer** | OpenAlex API (240M+ works) | Publication volume, citation patterns, author diversity, growth rates | Abnormal publication volumes (>1000/year), suspicious citation ratios, rapid growth patterns |
| **Crossref Analyzer** | Crossref metadata API | Metadata completeness, abstracts, references, author information | Missing metadata, poor quality abstracts (<100 chars), low reference counts |
| **Cross-Validator** | Cross-source data | Publisher name consistency, data correlation across sources | Mismatched publisher names, data inconsistencies between sources |

### How Assessment Works

#### **1. Multi-Backend Query**
The tool queries all enabled backends concurrently for comprehensive coverage:

```
Journal Query → [Curated Databases + Pattern Analyzers] → Combined Assessment
                 │
                 ├─ DOAJ (legitimate OA)
                 ├─ Scopus (indexed journals)
                 ├─ Beall's List (predatory)
                 ├─ UGC-CARE discontinued lists
                 ├─ PredatoryJournals.org
                 ├─ Kscien databases
                 ├─ CORE Conferences / CORE Journals
                 ├─ Retraction Watch (quality)
                 ├─ OpenAlex Analyzer (patterns)
                 ├─ Crossref Analyzer (metadata)
                 └─ Cross-Validator (consistency)
```

**Note**: Not all backends will find every journal. A journal may be:
- Found in DOAJ → strong legitimate evidence
- Found in Beall's → strong predatory evidence
- Found in UGC-CARE cloned/delisted lists → strong predatory evidence
- Not found in any curated database → rely on pattern analysis
- Found in contradictory sources → cross-validation resolves conflicts

#### **2. Assessment Logic**

**Curated Database Results (Authoritative)**:
- **DOAJ/Scopus match** → Classified as `legitimate` (high confidence)
- **Predatory list match** → Classified as `predatory` (high confidence)
- **No matches found** → Proceed to pattern analysis

**Pattern Analysis (Evidence-Based)**:
When curated databases don't have the journal, pattern analyzers evaluate quality:

**🟢 Legitimacy Indicators (OpenAlex/Crossref)**:
- Consistent publication volume (20-500 papers/year)
- Healthy citation patterns (>3 citations/paper average)
- Complete metadata (abstracts >100 chars, references, author ORCIDs)
- Recognized publisher with history
- Stable growth patterns

**🔴 Predatory Indicators (OpenAlex/Crossref)**:
- Publication mill patterns (>1000 papers/year)
- Extremely low citations (<0.5/paper)
- Incomplete metadata (no abstracts, missing author info)
- Suspicious/unknown publisher
- Sudden publication volume spikes

#### **3. Confidence Scoring**
Final confidence is determined by:
- **Source authority**: DOAJ/Scopus > Pattern analysis > Smaller lists
- **Agreement**: Multiple sources agreeing → higher confidence
- **Evidence strength**: Strong indicators > weak signals
- **Cross-validation**: Consistent data across sources increases confidence
- **Retraction data**: High retraction rates lower confidence for "legitimate" journals

#### **4. Result Combination**
The dispatcher aggregates all backend results:
- Conflicting assessments are resolved by source weight
- Multiple agreeing sources boost confidence
- Pattern analysis supplements curated databases
- Detailed reasoning explains the assessment

### Example Assessment Scenarios

#### **Scenario 1: Well-Known Legitimate Journal**
```
Input: "Nature"
│
├─ DOAJ: ✗ Not found (subscription journal, not open access)
├─ Scopus: ✓ Found → "legitimate"
├─ Predatory Lists: ✗ Not found
├─ Retraction Watch: ✓ Found → 153 retractions, 0.034% rate (within normal)
├─ OpenAlex: ✓ Found → 446,231 publications, healthy citations
├─ Crossref: ✓ Found → Complete metadata, Nature Publishing Group
│
Result: LEGITIMATE (confidence: 0.95)
Reasoning: "Found in Scopus with excellent publication patterns and metadata quality"
```

#### **Scenario 2: Known Predatory Journal**
```
Input: "Journal Appearing in UGC-CARE Cloned Group II"
│
├─ DOAJ: ✗ Not found
├─ Predatory Lists: ✓ Found in UGC-CARE Cloned (Group II) → "predatory"
├─ Retraction Watch: ✗ Not found
├─ OpenAlex: ✓ Found → suspicious pattern indicators
├─ Crossref: ✓ Found → weak metadata quality
│
Result: PREDATORY (confidence: 0.90)
Reasoning: "Listed in UGC-CARE cloned journal list, corroborated by pattern analysis"
```

#### **Scenario 3: Unknown Journal (Pattern Analysis)**
```
Input: "Emerging Regional Journal"
│
├─ DOAJ: ✗ Not found
├─ Scopus: ✗ Not found
├─ Predatory Lists: ✗ Not found
├─ OpenAlex: ✓ Found → 150 papers/year, 5 citations/paper average
├─ Crossref: ✓ Found → Good metadata, established publisher
│
Result: INSUFFICIENT_DATA (confidence: 0.45)
Reasoning: "Not in major databases; pattern analysis suggests legitimate practices but low confidence"
```

### Optional: Scopus Journal List

To enhance coverage with Scopus data:

1. Download the spreadsheet from [researchgate.net](https://www.researchgate.net/publication/384898389_Last_Update_of_Scopus_Indexed_Journal's_List_-_October_2024)
2. Create directory: `mkdir -p .aletheia-probe/scopus`
3. Place Excel file (e.g., `ext_list_October_2024.xlsx`) in this directory
4. Run `aletheia-probe sync` to process the data

**Benefits**: Adds nearly 30,000 subscription journals from major publishers (Elsevier, Springer, Wiley, etc.)

## Documentation

### User Documentation
- [Quick Start Guide](docs/quick-start.md) - Installation and basic usage
- [User Guide](docs/user-guide.md) - Comprehensive usage examples and features
- [Research Applications](docs/research-applications.md) - Using the tool in research workflows (SLR, bibliometrics, meta-research)
- [Media Mentions](docs/media-mentions.md) - Curated external coverage and institutional references
- [Configuration Reference](docs/configuration.md) - All configuration options
- [Troubleshooting](docs/troubleshooting.md) - Common issues and solutions

### Developer Documentation
- [API Reference](docs/api-reference/) - Backend API and data models
  - [Backend API](docs/api-reference/backends.md) - Creating custom backends
  - [Data Models](docs/api-reference/models.md) - Core data structures
  - [Extending Guide](docs/api-reference/extending-guide.md) - Extension patterns
- [Backend Integration Docs](dev-notes/integration/README.md) - Source-specific backend documentation
- [Contributing Guide](.github/community/CONTRIBUTING.md) - Development setup and guidelines
- [Coding Standards](dev-notes/CODING_STANDARDS.md) - Code quality requirements

## Paper and Citation

This tool and its methodology are described in the following academic paper:

**Aletheia-Probe: A Tool for Automated Journal Assessment**
Available at: https://arxiv.org/abs/2601.10431

To cite this work, please use the following BibTeX entry:

```bibtex
@misc{florath2026aletheiaprobetoolautomatedjournal,
      title={Aletheia-Probe: A Tool for Automated Journal Assessment},
      author={Andreas Florath},
      year={2026},
      eprint={2601.10431},
      archivePrefix={arXiv},
      primaryClass={cs.DL},
      url={https://arxiv.org/abs/2601.10431},
}
```

## Funding Acknowledgment

This work was funded by the Federal Ministry of Research, Technology
and Space (BMFTR) in Germany under the grant number 16KIS2251 of the
SUSTAINET-guardian project. The views expressed are those of the author.

## License

MIT License - see [LICENSE](LICENSE) file for details.
