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

- **[openapc.md](openapc.md)** - OpenAPC (Article Processing Charges) integration assessment
  - **Status**: Deferred / Low Priority
  - **Reason**: Limited coverage (5-15% of queries), weak signal for predatory detection, cost data ≠ quality indicator
  - **Reconsider if**: Scope expands to include cost transparency, user demand, or for research use cases

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
