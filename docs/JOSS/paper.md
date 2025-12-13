---
title: 'Aletheia-Probe: A Multi-Source Toolkit for Automated Assessment of Academic Journal and Conference Legitimacy'
tags:
  - Python
  - scholarly publishing
  - predatory journals
  - research integrity
  - bibliometrics
  - open access
authors:
  - name: Andreas Florath
    orcid: 0009-0001-6471-7372
    affiliation: 1
affiliations:
  - name: Deutsche Telekom AG, Germany
    index: 1
date: 13 December 2025
bibliography: paper.bib
archive_doi: 10.5281/zenodo.17788487
---

# Summary

Predatory publishing poses a significant threat to research integrity, with fraudulent journals and conferences exploiting researchers through deceptive practices while undermining the credibility of scholarly communication [@grudniewicz2019predatory; @agricola2025]. Researchers face challenges both in selecting legitimate publication venues and in ensuring source quality in research workflows such as systematic literature reviews [@xia2015predatory; @Sharma2018].

Aletheia-Probe is an open-source command-line tool and Python library that addresses these challenges by serving as both a practical utility for individual researchers and as research infrastructure for empirical studies where the scientific literature itself constitutes the dataset. The tool aggregates data from multiple authoritative sources (DOAJ, Beall's List, OpenAlex, Crossref, and others—covering over 240 million publication records) and applies pattern analysis to extract knowledge from these large, heterogeneous datasets. It provides confidence-scored assessments of academic journal and conference legitimacy, supporting research methodologies such as systematic literature reviews (where source quality validation is required by PRISMA guidelines [@page2021prisma]), bibliometric analyses where dataset composition affects study validity [@mongeon2016journal], and meta-research studies examining predatory publishing trends.

# Statement of Need

The proliferation of predatory journals and conferences has created a crisis in scholarly publishing, with estimates suggesting thousands of predatory venues targeting researchers [@shen2015predatory; @bohannon2013garbage]. While several curated lists and databases attempt to identify predatory venues, they suffer from coverage gaps, update delays, and lack of cross-validation. Individual researchers typically must manually check multiple sources, a time-consuming and error-prone process. Furthermore, existing tools often provide binary classifications without confidence scores or reasoning, making it difficult to assess edge cases.

Aletheia-Probe addresses these limitations by:

1. **Aggregating multiple authoritative sources**: Combining curated databases (DOAJ, Beall's List, Scopus, Kscien databases, Algerian Ministry lists, PredatoryJournals.org) with pattern analyzers (OpenAlex, Crossref, Retraction Watch) to provide comprehensive coverage.

2. **Providing confidence-scored assessments**: Rather than simple yes/no answers, the tool provides confidence levels and detailed reasoning based on evidence from multiple sources.

3. **Enabling bibliography validation**: Supporting BibTeX file analysis to check entire bibliographies, with CI/CD integration for automated quality checks.

4. **Offering extensible architecture**: Providing a plugin-based backend system that allows researchers to add custom data sources and assessment criteria.

## Research Applications

Beyond supporting individual researchers in publication venue selection, Aletheia-Probe serves as research infrastructure for empirical studies where journal legitimacy assessment is a methodological requirement:

**Systematic Literature Reviews (SLR)**: Established SLR methodologies (e.g., PRISMA guidelines [@page2021prisma]) require explicit documentation of search strategies and inclusion/exclusion criteria. Source quality validation is a critical step—predatory journals must be screened out to maintain review integrity. Aletheia-Probe automates this validation step, which traditionally required manual checking across dozens of sources, and provides audit trails for reproducibility.

**Bibliometric Analysis**: When analyzing publication patterns, citation networks, or research impact, dataset composition directly affects study validity [@mongeon2016journal]. Researchers must defensibly classify journals by legitimacy before conducting analyses. Aletheia-Probe provides confidence-scored assessments based on multiple authoritative sources, enabling researchers to document their quality control methodology.

**Meta-Research Studies**: Scholars studying predatory publishing phenomena need tools to systematically classify journals across large datasets. The tool's data aggregation architecture enables quantitative analysis of predatory publishing trends across disciplines, regions, and temporal dimensions.

The tool extracts knowledge from large, heterogeneous datasets through sophisticated data fusion—normalizing journal names across sources, resolving ISSN variations, cross-validating publisher information, and applying pattern analysis to publication metrics. This multi-source reasoning addresses a core challenge in bibliometric research: reliable journal classification at scale.

# Architecture and Features

Aletheia-Probe employs a modular architecture with three main components:

## Backend System

The tool implements a plugin-based backend system where each data source is encapsulated in a dedicated backend module. Backends fall into two categories:

- **Curated Databases**: Provide authoritative classifications for journals they cover (e.g., DOAJ for legitimate open-access journals, Beall's List for known predatory publishers).
- **Pattern Analyzers**: Evaluate publication patterns, metadata quality, and citation metrics to detect predatory characteristics in journals not covered by curated lists (e.g., OpenAlex for publication volume analysis, Crossref for metadata quality).

Each backend implements a common interface defined in the base backend class, enabling consistent querying and result formatting. This design allows easy extension with new data sources.

## Assessment Dispatcher

The dispatcher orchestrates concurrent queries across all enabled backends and combines their results into a unified assessment. It implements a weighted voting system where source authority, agreement across sources, and evidence strength determine the final confidence score. Cross-validation checks identify inconsistencies between sources, flagging potential data quality issues.

## Data Normalization

To enable accurate matching across heterogeneous data sources, the tool implements a sophisticated normalization pipeline that handles:

- Journal name variations and transliterations
- ISSN formatting (print vs. electronic)
- Publisher name matching
- Unicode normalization

Data and previous evaluation results are stored in a local SQLite cache database, reducing API calls and speeding up the process of re-evaluation of the same journals or BibTeX files.

## Key Features

- **Multi-format support**: Command-line queries for individual journals/conferences and batch processing of BibTeX files
- **Flexible output**: Human-readable text and JSON formats for integration with other tools
- **CI/CD integration**: Exit codes enable automated quality checks in publication workflows
- **Configurable**: YAML-based configuration for enabling/disabling backends and customizing assessment thresholds

This tool acts as a data aggregator - it doesn't provide data itself.

# Community Guidelines

Aletheia-Probe is developed on GitHub at [https://github.com/sustainet-guardian/aletheia-probe](https://github.com/sustainet-guardian/aletheia-probe). The project welcomes contributions through bug reports, backend development, and documentation improvements.

The project uses continuous integration with automated testing, type checking, and code formatting. All contributions must pass quality checks before merging.

The project encourages AI-assisted coding tools. However, all contributions must adhere to strict coding standards and pass automated quality checks.

The project is licensed under the MIT License.

# Acknowledgments

This work was funded by the Federal Ministry of Research, Technology and Space (BMFTR) in Germany under grant number 16KIS2251 of the SUSTAINET-guardian project.

# References
