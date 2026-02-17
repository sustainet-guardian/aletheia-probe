# Future Integrations and Data Sources

This directory contains assessments and evaluations of potential data sources and integrations that have been considered for aletheia-probe but are currently deferred or not implemented.

## Purpose

Each file in this directory documents:
- **What** the data source or integration is
- **Why** it was considered
- **Pros and cons** of integration
- **Technical feasibility** and effort estimates
- **Recommendation** (defer, low priority, or conditions for implementation)

## Current Assessments

- **[nlm-catalog.md](nlm-catalog.md)** - NLM Catalog (National Library of Medicine) integration assessment
  - **Status**: Recommended / Low Priority
  - **Reason**: Strong legitimacy signal for biomedical journals, fraud detection for fake MEDLINE claims, low implementation cost (1-2 days)
  - **Limitation**: Domain-specific (biomedical only, 20-30% of queries), 70-80% of queries irrelevant
  - **Implement when**: After core pattern analyzers are robust, or when biomedical user demand is clear

- **[openapc.md](openapc.md)** - OpenAPC (Article Processing Charges) integration assessment
  - **Status**: Deferred / Low Priority
  - **Reason**: Limited coverage (5-15% of queries), weak signal for predatory detection, cost data ≠ quality indicator
  - **Reconsider if**: Scope expands to include cost transparency, user demand, or for research use cases

- **[ror.md](ror.md)** - ROR (Research Organization Registry) integration assessment
  - **Status**: Not Recommended
  - **Reason**: Fundamental mismatch (institutions ≠ journals), catastrophically low coverage (<10%), extremely weak signal, massive complexity (2,437 LOC, 7 tables)
  - **Related**: PR #1034 fully implemented and tested ROR integration before rejection

- **[openreview.md](openreview.md)** - OpenReview (peer review transparency platform) integration assessment
  - **Status**: Experimental / Low Priority
  - **Reason**: Unique acceptance-rate and peer review quality signals (unavailable elsewhere), but only covers ML/AI conferences; zero predatory detection capability; predatory venues never use transparent review platforms; requires maintained venue lookup table
  - **Unique value**: First tool to use peer review process data as a quality signal; strong whitelist for NeurIPS/ICLR/ICML/AAAI/CVx queries
  - **Implement when**: ML/AI community user demand confirmed; after NLM Catalog and predatory list improvements; maintenance volunteer available for venue table

- **[wikidata.md](wikidata.md)** - Wikidata (Wikimedia Foundation knowledge graph) integration assessment
  - **Status**: Deferred / Low Priority
  - **Reason**: No direct predatory signal (Wikidata is a notability graph, not a quality filter), presence ≠ legitimate, low unique-information yield (11-17% of queries), SPARQL infrastructure complexity from May 2025 graph split
  - **Unique value**: Publisher name disambiguation and historical anchoring — best realized as a lightweight utility improving existing backends rather than a full backend
  - **Reconsider if**: Publisher name mismatches confirmed as significant source of false negatives, or scope expands to knowledge-graph-enriched scholarly intelligence

## Adding New Assessments

When evaluating a new potential integration:

1. Create a new markdown file named after the data source (e.g., `scopus-alternative.md`, `pubpeer.md`)
2. Use the OpenAPC assessment as a template structure
3. Include at minimum:
   - Context and overview of the data source
   - Pros and cons analysis
   - Integration effort estimate
   - Coverage and benefit analysis
   - Alignment with aletheia-probe's mission
   - Clear recommendation with reasoning
   - Sources and references

## Philosophy

Not every available data source should be integrated. Consider:

- **Mission alignment**: Does it directly support predatory journal detection?
- **Coverage**: What percentage of queries benefit?
- **Signal strength**: Is it direct evidence or weak/ambiguous signal?
- **Maintenance burden**: Is the effort justified by the benefit?
- **Alternatives**: Could existing backends be improved instead?

Focus should remain on **high-impact integrations** that meaningfully improve detection accuracy for the majority of queries.
