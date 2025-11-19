# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2025-11-19

Initial release of Aletheia Probe - an automated tool for assessing predatory journals using multiple data sources.

### Added

#### Core Features
- Multi-backend architecture for journal assessment from diverse data sources
- CLI interface with `aletheia-probe` command-line tool
- Intelligent input normalization and validation
- ISSN extraction and validation
- Confidence scoring based on multiple sources
- Assessment aggregation with detailed reasoning
- Local caching system for improved performance
- Configuration management via YAML files

#### Backend Integrations
- **DOAJ Backend**: Queries Directory of Open Access Journals for legitimate journals
- **Beall's List Backend**: Checks against archived predatory journal lists
- **Retraction Watch Backend**: Analyzes journal quality via retraction data
  - ~67,000 retraction records across ~27,000 journals
  - Risk-based assessment (NOTE, LOW, MODERATE, HIGH, CRITICAL)
  - Rate-based and count-based thresholds
- **Algerian Ministry Backend**: Government-verified predatory journal list (~3,300 journals)
  - RAR archive processing
  - PDF text extraction
  - Multilingual support (Arabic, French, English)
- **OpenAlex Integration**: Publication volume data for contextual retraction rates
  - On-demand API calls during assessment
  - 30-day caching
  - 240+ million scholarly works coverage

#### BibTeX Support
- `aletheia-probe bibtex <file.bib>` command for batch assessment of bibliographies
- BibTeX parsing via pybtex library
- Concurrent processing of multiple journal entries
- Exit code integration (returns 1 if predatory journals found, 0 otherwise)
- JSON and text output formats
- CI/CD integration capabilities

#### Output Formats
- JSON format for programmatic processing
- YAML format for human-readable structured output
- Text format with detailed reasoning and confidence scores
- Verbose mode with comprehensive backend results

#### Commands
- `aletheia-probe journal <name>` - Assess a single journal
- `aletheia-probe bibtex <file>` - Batch assess BibTeX bibliography
- `aletheia-probe sync` - Synchronize data from all backends
- `aletheia-probe status` - Check backend and cache status
- `aletheia-probe config` - Display current configuration

#### Database & Caching
- Normalized SQLite database schema
- Deduplication across multiple sources
- Cross-source journal tracking
- Source authority weighting
- Assessment result caching
- Key-value cache for external API data (OpenAlex)
- Article-level retraction cache

#### Technical Features
- Python 3.10+ support (tested on 3.10, 3.11, 3.12, 3.13)
- Async/await support throughout
- Comprehensive type hints with mypy strict checking
- Dual-logger system (detail logger for debugging, status logger for user output)
- Error handling with graceful degradation
- Rate limiting and API throttling
- Retry logic with exponential backoff

#### Code Quality & Development
- Ruff for fast Python linting
- Black for code formatting
- mypy for static type checking
- pytest with async support
- Pre-commit hooks
- GitHub Actions CI/CD pipeline
- Cross-platform testing (Linux, macOS, Windows)
- Code coverage reporting

#### Documentation
- Comprehensive README with quick start guide
- Backend integration documentation (state-based, not process-based)
- Coding standards referencing PEPs
- Logging usage guide
- Dependencies documentation
- Database schema reference
- Development notes and guidelines

### Infrastructure
- MIT License
- PyPI package structure
- GitHub repository with issue templates
- Security scanning (bandit, safety)
- Automated testing and builds
- Cross-platform compatibility (Linux, macOS, Windows)
