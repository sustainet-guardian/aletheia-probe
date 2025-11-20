# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2025-11-20

### Added
- **Configurable API Email Addresses**: Email addresses for Crossref and OpenAlex APIs are now configurable through YAML configuration
  - Supports proper "polite pool" access patterns for better rate limits
  - Email validation with clear error messages
  - Configuration via `email` parameter in backend settings
  - Affects crossref_analyzer, openalex_analyzer, and cross_validator backends
- **Factory-Based Backend Registry**: Refactored backend registration system to support dynamic configuration
  - Enables runtime backend creation with custom parameters
  - Foundation for future configurable backend parameters
- **Centralized Logging System**: Implemented project-wide standardized logging architecture
  - Automated logging consistency checker (scripts/check-logging.py)
  - Clear separation between technical details and user-facing messages
  - Integrated into quality assurance pipeline

### Changed
- **Backend Architecture**: Moved from singleton backend instances to factory-based creation for configurable backends
- **Logging Infrastructure**: Replaced direct logging.getLogger() calls with centralized project loggers across 12 modules
  - detail_logger: Technical details, debug info, internal processing (file only)
  - status_logger: User-facing progress, status, errors (console + file)
- **Documentation**: Updated configuration examples and user guide to include email configuration
- **API Integration**: Crossref and OpenAlex backends now use configured email addresses in User-Agent headers
- **Security Documentation**: Enhanced security policy with email address privacy considerations

### Fixed
- **Code Quality**: Resolved linting and formatting issues with ruff
- **Type Safety**: Added comprehensive type annotations for new factory methods
- **Email Validation**: Proper validation prevents invalid email formats in configuration
- **Import Sorting**: Fixed import organization across codebase
- **Test Compatibility**: Updated bibtex parser test mocks for new logging system

### Removed
- **Legacy Backend Support**: Cleaned up deprecated singleton backend registration patterns
- **Temporary Test Files**: Removed bot attribution test artifacts

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
