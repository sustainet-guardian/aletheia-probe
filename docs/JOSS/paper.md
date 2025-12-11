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
date: 11 December 2025
bibliography: paper.bib
archive_doi: 10.5281/zenodo.17788487
---

# Summary

Predatory publishing poses a significant threat to research integrity, with fraudulent journals and conferences exploiting researchers through deceptive practices while undermining the credibility of scholarly communication [@grudniewicz2019predatory; @agricola2025]. Researchers, particularly early-career scientists and those in developing regions, face challenges in distinguishing legitimate venues from predatory ones [@xia2015predatory; @Sharma2018]. Aletheia-Probe is an open-source command-line tool that addresses this challenge by aggregating data from multiple authoritative sources and applying pattern analysis to evaluate the legitimacy of academic journals and conferences. The tool provides confidence-scored assessments that help researchers make informed publication decisions and protect the integrity of their bibliographies.

# Statement of Need

The proliferation of predatory journals and conferences has created a crisis in scholarly publishing, with estimates suggesting thousands of predatory venues targeting researchers [@shen2015predatory; @bohannon2013garbage]. While several curated lists and databases attempt to identify predatory venues, they suffer from coverage gaps, update delays, and lack of cross-validation. Individual researchers typically must manually check multiple sources, a time-consuming and error-prone process. Furthermore, existing tools often provide binary classifications without confidence scores or reasoning, making it difficult to assess edge cases.

Aletheia-Probe addresses these limitations by:

1. **Aggregating multiple authoritative sources**: Combining curated databases (DOAJ, Beall's List, Scopus, Kscien databases, Algerian Ministry lists, PredatoryJournals.org) with pattern analyzers (OpenAlex, Crossref, Retraction Watch) to provide comprehensive coverage.

2. **Providing confidence-scored assessments**: Rather than simple yes/no answers, the tool provides confidence levels and detailed reasoning based on evidence from multiple sources.

3. **Enabling bibliography validation**: Supporting BibTeX file analysis to check entire bibliographies, with CI/CD integration for automated quality checks.

4. **Offering extensible architecture**: Providing a plugin-based backend system that allows researchers to add custom data sources and assessment criteria.

The tool serves multiple research communities: individual researchers checking publication venues, librarians maintaining institutional policies, research administrators evaluating faculty publications, and funding agencies assessing research outputs.

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

Aletheia-Probe is actively developed on GitHub at [https://github.com/sustainet-guardian/aletheia-probe](https://github.com/sustainet-guardian/aletheia-probe). The project welcomes contributions through:

- **Bug reports and feature requests**: Via GitHub Issues
- **Backend development**: Comprehensive documentation for implementing custom data source backends is available
- **Code contributions**: Following established coding standards with full test coverage requirements
- **Documentation improvements**: User guides and API documentation

The project uses continuous integration with automated testing (pytest), type checking (mypy), code formatting (black, ruff), and security scanning. All contributions must pass quality checks before merging.

The project explicitly encourages the use of AI-assisted coding tools to enhance development productivity. However, all contributions—whether human- or AI-generated—must adhere to the project's strict coding standards and pass all automated quality checks. Contributors remain fully responsible for all submitted code, regardless of the tools used to generate it.

Support is provided through GitHub Issues and discussions. The project is licensed under the MIT License, encouraging academic and commercial use.

# Acknowledgments

This work was funded by the Federal Ministry of Research, Technology and Space (BMFTR) in Germany under grant number 16KIS2251 of the SUSTAINET-guardian project.

# References
