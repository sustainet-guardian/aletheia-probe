# Research Applications

## Overview

Aletheia-Probe is designed to support research workflows where journal legitimacy assessment is a methodological requirement. While individual researchers can use it to check publication venues, the tool's architecture specifically addresses challenges in systematic literature reviews, bibliometric analysis, and meta-research on scholarly publishing.

This document describes research questions the tool helps address and how it integrates with established research methodologies.

## Research Questions This Tool Addresses

### 1. Source Quality Validation in Systematic Literature Reviews

**Research Question**: How can researchers systematically and reproducibly validate the legitimacy of journals across large reference sets in systematic reviews?

**Context**

Systematic literature review methodologies require explicit documentation of search strategies and inclusion/exclusion criteria. The PRISMA 2020 statement (Page et al., 2021) emphasizes transparency in the screening process and documentation of excluded studies. When the scientific literature itself constitutes the dataset, source quality validation becomes a critical methodological step-analogous to instrument calibration in experimental science.

The proliferation of predatory journals (Grudniewicz et al., 2019) complicates this process. Researchers must verify that included sources meet scholarly standards, but manually checking hundreds of references against multiple authoritative sources is time-consuming, error-prone, and difficult to document reproducibly.

**Challenge**

Traditional approaches to source validation involve:
- Manually checking each journal against curated lists (DOAJ, Beall's List, etc.)
- Consulting multiple sources that may provide conflicting information
- Making binary decisions without quantified confidence levels
- Limited documentation for reproducibility and peer review

This process doesn't scale to modern systematic reviews that may include hundreds or thousands of references.

**How Aletheia-Probe Addresses This**

The tool provides systematic, reproducible source validation through:

- **Batch processing**: Analyze entire BibTeX files containing 100s-1000s of references
- **Multi-source cross-checking**: Automated queries across 13+ authoritative sources
- **Confidence scoring**: Quantified assessment strength rather than binary classification
- **Detailed reasoning**: Each assessment includes evidence from multiple sources
- **Reproducible workflow**: Same inputs produce same outputs (deterministic)
- **Audit trails**: JSON export preserves full assessment history for methods documentation

See [Example 1: Systematic Review with 482 References](#example-1-systematic-review-with-482-references) for a detailed workflow including BibTeX processing, flagged entry extraction using `jq`, and PRISMA documentation templates.

### 2. Dataset Quality Control in Bibliometric Analysis

**Research Question**: How can bibliometric datasets be quality-controlled to ensure analyses are based on legitimate scholarly venues?

**Context**

Bibliometric studies analyze publication patterns, citation networks, and research impact across journal datasets. The validity of such studies depends critically on dataset composition (Mongeon & Paul-Hus, 2016). Including predatory journals can introduce noise and bias; excluding legitimate journals (especially from underrepresented regions or disciplines) introduces selection bias.

As Mongeon and Paul-Hus demonstrate, different journal databases have varying coverage, making database selection a consequential methodological decision. Similarly, decisions about which journals to include or exclude must be systematic, defensible, and documented.

**Challenge**

Bibliometric datasets often involve thousands or tens of thousands of journals, making manual review impractical. Researchers face several challenges:

- **Scale**: Large datasets (1000s-10000s of journals) preclude manual classification
- **Uncertainty**: Binary classification (legitimate/predatory) oversimplifies edge cases
- **Conflicting sources**: Authoritative databases may disagree about journal status
- **Documentation**: Need to quantify and document classification uncertainty
- **Reproducibility**: Classification decisions must be defensible to peer reviewers

**How Aletheia-Probe Addresses This**

The tool enables principled, documented quality control through:

- **Confidence scoring**: Enables threshold-based inclusion/exclusion with documented rationale
- **Multi-source validation**: Reduces single-source bias by aggregating evidence
- **Cross-validation**: Flags inconsistencies across sources for manual review
- **Programmatic access**: Python API integrates with data analysis pipelines
- **Export capabilities**: Full assessment data supports reproducible workflows

See [Example 2: Bibliometric Analysis of 3,200 Computer Science Journals](#example-2-bibliometric-analysis-of-3200-computer-science-journals) for a detailed workflow including Python API usage, confidence-based thresholds, manual review protocols, and methods section documentation.

### 3. Meta-Research on Predatory Publishing Patterns

**Research Question**: What patterns characterize predatory publishing across disciplines, publishers, geographic regions, and time periods?

**Context**

Understanding predatory publishing as a phenomenon requires systematic analysis across large journal datasets. The scale and growth of predatory publishing (Shen & Björk, 2015) raises questions about disciplinary variation, temporal trends, and the effectiveness of countermeasures. Such meta-research requires tools that can classify journals at scale while quantifying uncertainty.

Studying predatory publishing patterns can inform:
- Institutional policies for research assessment
- Researcher education and awareness programs
- Understanding of vulnerable disciplines or regions
- Evaluation of intervention effectiveness
- Development of automated detection methods

**Challenge**

Meta-research on predatory publishing faces several technical challenges:

- **Coverage gaps**: No single authoritative source has complete journal coverage
- **Heterogeneous criteria**: Different sources use different classification criteria
- **Update frequency**: Sources have varying update schedules and historical coverage
- **Data fusion**: Integrating evidence across heterogeneous sources requires normalization
- **Scalability**: Manual classification doesn't scale to research questions about trends

**How Aletheia-Probe Addresses This**

The tool's architecture specifically supports meta-research through:

- **Multi-source aggregation**: 13+ data sources covering 240M+ publication records
- **Normalized data model**: Enables cross-source comparisons and trend analysis
- **Pattern analysis**: Backends analyze publication volumes, citation rates, metadata quality
- **Confidence quantification**: Enables sensitivity analysis and uncertainty propagation
- **Programmatic access**: Supports research data pipelines and computational workflows
- **Temporal data**: Some backends track historical changes in journal status

**Research Applications**

The tool can support meta-research investigations such as:

- Analyzing temporal trends in predatory journal emergence and growth
- Comparing predatory publishing prevalence across academic disciplines
- Studying relationships between journal characteristics and legitimacy classifications
- Evaluating the effectiveness of identification methods
- Assessing geographic or linguistic patterns in predatory publishing
- Validating hypotheses about predatory venue indicators

**Important Note**: This tool provides classification infrastructure for such studies. Interpreting patterns, establishing causality, and making policy recommendations require domain expertise, theoretical frameworks, and additional research beyond what the tool provides.

See [Example 3: Meta-Research on Predatory Publishing](#example-3-meta-research-on-predatory-publishing-generalized) for a generalized workflow demonstrating how the tool can support such investigations.

## Integration with Research Methodologies

### PRISMA-Guideline Systematic Reviews

The PRISMA 2020 statement (Page et al., 2021) requires documentation of:
- Search strategies and databases used (ibid., page 4, item 16a)
- Inclusion and exclusion criteria with justification (ibid., page 4, item 16b)
- Screening and selection process (ibid., page 5, "Records marked as ineligible by automation tools (n= )")
- Numbers of studies screened, assessed, and included (ibid., page 5, "Reports assessed for eligibility (n= )" and "Reports excluded: Reason 1 (n= ) Reason 2 (n= ) Reason 3 (n= ) etc")

Aletheia-Probe supports the screening phase by:
- Batch processing BibTeX exports from reference managers
- Providing confidence-scored assessments for systematic exclusion decisions
- Generating audit trails for PRISMA flowchart documentation
- Enabling reproducible source validation methodology

**Example: Systematic Review with 482 References**

A research team conducting a PRISMA-guideline systematic review on climate change mitigation strategies. After database searches (Web of Science, Scopus, IEEE Xplore), 482 unique references were collected.

```bash
# Step 1: Export from reference manager to BibTeX
# (Done via Zotero/Mendeley/EndNote)

# Step 2: Run batch validation
aletheia-probe bibtex climate-mitigation-refs.bib --format json > validation.json

# Step 3: Extract flagged entries for review
jq '.assessment_results[] | select(.assessment.assessment == "predatory" and .assessment.confidence >= 0.75) | {key: .entry.key, journal: .entry.journal_name, confidence: .assessment.confidence}' validation.json > predatory-high-confidence.json

# Step 4: Extract low-confidence entries for manual review
jq '.assessment_results[] | select(.assessment.confidence < 0.50) | {key: .entry.key, journal: .entry.journal_name, assessment: .assessment.assessment, confidence: .assessment.confidence}' validation.json > uncertain-entries.json

# Step 5: Summary statistics
jq -r '.assessment_results[].assessment.assessment' validation.json | sort | uniq -c
```

Results:
- 7 journals flagged as predatory (confidence >0.75)
- 12 journals with insufficient data (confidence <0.50)
- 463 journals assessed as legitimate (confidence >0.75)

Follow-up actions: Excluded 7 predatory journals immediately. Two reviewers independently assessed 12 uncertain cases, resulting in 3 additional exclusions and 9 retained (regional journals with limited international indexing but legitimate practices).

**PRISMA Documentation Example**

In flowchart:
> "Records excluded: Predatory journal (n=10)"

In methods:
> "Source quality validation: All references were validated using Aletheia-Probe v0.7.0 to identify potential predatory journals. The tool cross-references journals against DOAJ, Beall's List historical archives, Kscien databases, and publication pattern analysis from OpenAlex and Crossref. Journals flagged as predatory with confidence ≥0.75 were excluded (n=7). Journals with confidence 0.50-0.75 underwent independent review by two authors (n=12), resulting in 3 additional exclusions. This process ensures the review dataset comprises publications from legitimate scholarly venues."

### Scientometric Studies

Bibliometric and scientometric research requires defensible dataset quality control. The tool supports:
- Large-scale batch assessment (1000s-10000s of journals)
- Confidence-based inclusion/exclusion thresholds
- Sensitivity analysis across different confidence levels
- Python API integration with data analysis pipelines

Key considerations:
- Document tool version, assessment date, and confidence thresholds
- Apply sensitivity analysis to test robustness of findings
- Archive complete assessment results for peer review
- Use manual review for uncertain cases (low confidence scores)

**Example: Bibliometric Analysis of 3,200 Computer Science Journals**

A scientometrician studying citation patterns and collaboration networks in computer science needed to ensure dataset quality before analysis.

```python
from aletheia_probe import JournalAssessor
import pandas as pd

# Load journal list from Web of Science CS category
df = pd.read_csv('cs-journals.csv')  # 3,200 journals

assessor = JournalAssessor()

# Batch assessment
results = []
for idx, journal in df.iterrows():
    assessment = assessor.assess(journal['Journal'], journal['ISSN'])
    results.append({
        'journal': journal['Journal'],
        'issn': journal['ISSN'],
        'classification': assessment.classification,
        'confidence': assessment.confidence,
        'sources': ', '.join([s.name for s in assessment.sources])
    })

    if idx % 100 == 0:
        print(f"Processed {idx}/3200...")

results_df = pd.DataFrame(results)

# Quality control thresholds
legitimate = results_df[
    (results_df['classification'] == 'legitimate') &
    (results_df['confidence'] > 0.80)
]  # n=2,847

predatory = results_df[
    (results_df['classification'] == 'predatory') &
    (results_df['confidence'] > 0.75)
]  # n=127

uncertain = results_df[
    results_df['confidence'] <= 0.70
]  # n=226
```

Manual review process: Two domain experts independently reviewed 226 uncertain journals with agreement on 198 (88%). Disagreements resolved by third reviewer. Final: 186 included, 40 excluded.

**Final Dataset**: 3,033 journals included (2,847 automated + 186 manual), 167 excluded (127 automated + 40 manual). Inclusion rate: 94.8%.

**Methods Documentation Example**:

> "Dataset quality control employed Aletheia-Probe for systematic journal classification. Journals classified as 'legitimate' with confidence ≥0.80 were included automatically (n=2,847). Journals classified as 'predatory' with confidence ≥0.75 were excluded (n=127). The remaining 226 journals with confidence <0.70 underwent independent review by two computer science domain experts, with a third reviewer resolving disagreements (κ=0.89). Final dataset: 3,033 journals. Complete classification data and inter-rater reliability statistics are provided in supplementary materials."

### Reproducibility Considerations

Aletheia-Probe supports reproducible research workflows, but researchers must understand the nature of reproducibility when using external data sources:

**Important: Data Source Variability**

Aletheia-Probe does not provide data itself-it aggregates information from external sources that change over time:

- **External APIs**: OpenAlex, Crossref, and other live APIs return data that may change as their databases are updated
- **Cached local data**: DOAJ, Beall's List, Kscien databases are downloaded and cached locally, representing a snapshot at sync time
- **Temporal dependency**: Running the same assessment on different dates may yield different results if external sources have updated

**Levels of Reproducibility**

1. **Strong reproducibility** (same time, same configuration):
   - Given the same input and cached data, the tool produces identical outputs
   - Assessment logic is deterministic
   - All API responses are cached after first query

2. **Limited reproducibility** (different times):
   - External API data (OpenAlex, Crossref) may change between assessments
   - Local cached data remains stable until explicitly re-synced
   - Configuration can be restricted to local-only sources for time-stable assessments

**Achieving Reproducible Assessments**

For research requiring strict reproducibility:

```yaml
# config.yml - Use only local (time-stable) backends
backends:
  enabled:
    - doaj              # Local cache
    - bealls            # Local cache
    - kscien_standalone # Local cache
    - kscien_publishers # Local cache
    - algerian_ministry # Local cache
  disabled:
    - openalex_analyzer  # External API (time-variant)
    - crossref_analyzer  # External API (time-variant)
```

**Documenting Assessments for Reproducibility**

All API responses and backend results are preserved in JSON output, enabling full audit trails:

```bash
# Run assessment with full documentation
aletheia-probe bibtex refs.bib --format json > assessment-full.json

# The JSON contains:
# - All backend responses (including API data)
# - Response timestamps
# - Confidence scores and reasoning
# - Data source versions
```

**Archival Support**

For reproducible research, archive:
```
research-project/
├── data/
│   ├── input-journals.csv              # Input dataset
│   └── cache.db                        # Cached data (optional but recommended)
├── assessments/
│   └── validation-results.json         # Full assessment output with all API responses
├── config/
│   └── aletheia-probe-config.yml       # Tool configuration (which backends used)
└── methods/
    └── journal-classification.md       # Methodology documentation
```

**Key Point**: The `validation-results.json` file contains complete backend responses, including all data retrieved from external APIs at the time of assessment. This preserves the evidence basis even if external sources change later.

**Documentation Requirements**

Include in methods or supplementary materials:

1. **Tool version**: Aletheia-Probe version (e.g., v0.7.0)
2. **Assessment date**: When assessments were performed
3. **Data sync date**: When local caches were last synchronized
4. **Enabled backends**: Which data sources were queried
5. **Configuration**: Confidence thresholds, backend weights
6. **Archived outputs**: Full JSON assessment results

**Example methodology text:**

> "Journal classification employed Aletheia-Probe v0.7.0 (DOI: 10.5281/zenodo.17788487) executed on 2025-12-15. Local data sources (DOAJ, Beall's List, Kscien databases) were synchronized on 2025-12-10. External APIs (OpenAlex, Crossref) were queried on 2025-12-15, with all responses cached and preserved in supplementary data files. The complete assessment output, including all backend responses and confidence scores, is archived in the supplementary materials (validation-results.json). The configuration file specifying enabled backends and thresholds is also provided for full methodological transparency."

**Trade-offs**

- **Local-only backends**: Maximum reproducibility, but potentially lower coverage and less current data
- **Including APIs**: Better coverage and current data, but assessments may change if sources update
- **Hybrid approach**: Use both, but document API query dates and archive complete responses for transparency

The tool's JSON output preserves all evidence at the time of assessment, providing an auditable record even when external sources evolve.

### Meta-Research Studies

For researchers studying predatory publishing patterns, the tool enables large-scale systematic classification with uncertainty quantification.

**Example: Meta-Research on Predatory Publishing Patterns**

Researchers studying predatory publishing patterns across disciplines use Aletheia-Probe's multi-source aggregation to classify journals and analyze trends.

```python
import pandas as pd
from aletheia_probe import JournalAssessor

# Load multi-disciplinary journal dataset
journals = pd.read_csv('multidisciplinary-journals.csv')
# Columns: name, issn, discipline, year_founded, publisher, country

assessor = JournalAssessor()

# Assess all journals
results = []
for _, journal in journals.iterrows():
    assessment = assessor.assess(journal['name'], journal['issn'])
    results.append({
        'name': journal['name'],
        'discipline': journal['discipline'],
        'year': journal['year_founded'],
        'publisher': journal['publisher'],
        'country': journal['country'],
        'classification': assessment.classification,
        'confidence': assessment.confidence,
        'num_sources': len(assessment.sources)
    })

df_results = pd.DataFrame(results)

# Example analytical questions
# 1. Disciplinary distribution
discipline_counts = df_results.groupby(['discipline', 'classification']).size()

# 2. Temporal trends
predatory_by_year = df_results[
    df_results['classification'] == 'predatory'
].groupby('year').size()

# 3. Publisher patterns
publisher_classifications = df_results.groupby('publisher')['classification'].value_counts()

# 4. Geographic patterns
country_stats = df_results.groupby(['country', 'classification']).size()

# 5. Sensitivity analysis
for threshold in [0.70, 0.75, 0.80, 0.85]:
    subset = df_results[df_results['confidence'] > threshold]
    print(f"Threshold {threshold}: Dataset size={len(subset)}")
```

**Important**: The tool provides classification infrastructure. Research contributions come from formulating meaningful questions, selecting appropriate datasets, interpreting patterns with domain expertise, and situating findings in theoretical frameworks.

## When This Tool is Appropriate

### Good Fit for Research Use

**Systematic Literature Reviews**
- ✅ PRISMA or similar guideline-based reviews
- ✅ Source quality validation as inclusion criterion
- ✅ Documentation for reproducibility
- ✅ Batch processing of reference databases

**Bibliometric/Scientometric Studies**
- ✅ Dataset quality control before analysis
- ✅ Large-scale journal classification (100s-1000s)
- ✅ Confidence-scored decisions for defensible methodology
- ✅ Sensitivity analysis across thresholds

**Meta-Research on Scholarly Publishing**
- ✅ Studying predatory publishing patterns
- ✅ Analyzing temporal or disciplinary trends
- ✅ Multi-source data fusion requirements
- ✅ Programmatic analysis workflows

**Institutional Applications**
- ✅ Research assessment policy enforcement
- ✅ Faculty publication venue validation
- ✅ Library acquisition decisions
- ✅ Custom whitelist/blacklist integration

### Not Designed For

**Individual Paper Assessment**
- ❌ Assessing quality of specific papers (tool evaluates venues, not papers)
- ❌ Peer review decisions (journal legitimacy ≠ paper quality)
- ❌ Determining whether to accept/reject manuscripts

**Author-Level Evaluation**
- ❌ Researcher reputation assessment
- ❌ Promotion/tenure decisions based solely on publication venues
- ❌ Attributing author intent or knowledge of predatory practices

**Predictive Applications**
- ❌ Forecasting future journal legitimacy
- ❌ Predicting which journals will become predatory
- ❌ Real-time fraud detection

**Legal Determinations**
- ❌ Legal evidence of fraudulent activity
- ❌ Definitive proof of predatory intent
- ❌ Regulatory compliance decisions

The tool provides **evidence-based classification** to inform research decisions, not definitive judgments that replace human expertise and domain knowledge.

## References

For comprehensive references, see the JOSS paper. Key methodological references:

- **PRISMA 2020**: Page MJ, McKenzie JE, Bossuyt PM, et al. The PRISMA 2020 statement: an updated guideline for reporting systematic reviews. *BMJ* 2021;372:n71. doi:10.1136/bmj.n71

- **Bibliometric Methodology**: Mongeon P, Paul-Hus A. The journal coverage of Web of Science and Scopus: a comparative analysis. *Scientometrics* 2016;106(1):213-228. doi:10.1007/s11192-015-1765-5

- **Predatory Publishing**: Grudniewicz A, Moher D, Cobey KD, et al. Predatory journals: no definition, no defence. *Nature* 2019;576:210-212. doi:10.1038/d41586-019-03759-y

- **Predatory Journal Growth**: Shen C, Björk BC. 'Predatory' open access: a longitudinal study of article volumes and market characteristics. *BMC Medicine* 2015;13:230. doi:10.1186/s12916-015-0469-2

## Further Documentation

- [Quick Start Guide](quick-start.md) - Installation and basic usage
- [User Guide](user-guide.md) - Comprehensive usage examples
- [API Reference](api-reference/) - Programmatic access documentation
- [Backend Documentation](api-reference/backends.md) - Extending the tool with custom backends
- [Configuration Reference](configuration.md) - All configuration options

For support or to report issues: [GitHub Issues](https://github.com/sustainet-guardian/aletheia-probe/issues)
