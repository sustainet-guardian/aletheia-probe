# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.7.0] - 2025-12-11

### Added
- **JOSS Paper**: Complete Journal of Open Source Software submission document (#210)
  - Comprehensive paper for academic publication
  - Bibliography with academic references
  - Automated PDF generation and validation
- **Zenodo DOI Integration**: Added DOI badge for improved citation support (#200)
  - Enhanced academic attribution
  - Improved research reproducibility
  - Better integration with citation managers

### Changed
- **Documentation Completeness**: Comprehensive documentation improvements
  - Backend-specific configuration documentation (#217)
  - Complete enumeration documentation in models.md (#216)
  - High-level Python API documentation (#215)
  - Complete field descriptions in models.md (#214)
  - Backend catalog documentation (#213)
  - Retraction checking and acronym expansion documentation (#212)
  - CLI flags documentation (#211)
  - Conference acronym CLI command documentation (#209)

### Improved
- **Release Infrastructure**: Enhanced for stable releases and academic publishing
  - JOSS-ready documentation structure
  - Automated paper validation in CI/CD
  - Complete API reference documentation
  - Enhanced installation and usage guides

## [0.6.0] - 2025-12-02

### Added
- **Performance Testing Suite**: Mandatory performance testing infrastructure (MVP for #172) (#188)
  - Benchmark tests for critical operations
  - Performance regression detection
  - Automated performance validation in CI/CD pipeline
- **Comprehensive Integration Tests**: Full test coverage for integration scenarios (#170) (#189)
  - End-to-end workflow testing
  - Backend integration validation
  - Realistic usage scenario coverage
- **API Documentation**: Comprehensive documentation for backend developers (#184)
  - Detailed backend architecture documentation
  - Integration guide for new backends
  - API reference and usage examples
- **CITATION.cff**: Citation metadata file for academic references (#160)
  - Standardized citation format
  - Easy integration with reference managers
  - Improved academic attribution support

### Changed
- **JournalEntryData Migration**: Migrated from dataclass to Pydantic BaseModel (#163)
  - Enhanced data validation
  - Better type safety and serialization
  - Improved integration with modern Python tooling
- **CLI Architecture**: Improved maintainability and consistency (#162)
  - More maintainable command structure
  - Consistent error handling across commands
  - Better separation of concerns
- **UpdateSourceRegistry Pattern**: Implemented for better extensibility (#159)
  - More flexible source registration
  - Easier addition of new data sources
  - Improved configuration management
- **Configuration Externalization**: Moved hardcoded values to config.py (#156)
  - Centralized configuration management
  - Easier customization and deployment
  - Better maintainability
- **Async I/O Operations**: Wrapped blocking operations with asyncio.to_thread() (#153)
  - Improved async/await compliance
  - Better performance in concurrent operations
  - Proper non-blocking I/O handling
- **Deduplication Logic**: Centralized across all data sources (#152)
  - Consistent deduplication behavior
  - Reduced code duplication
  - Improved maintainability
- **Type Safety**: Replaced magic strings with AssessmentType enum (#151)
  - Better type checking and IDE support
  - Reduced risk of typos and errors
  - More maintainable code

### Fixed
- **Email Format and User-Agent Validation**: Corrected default formats and improved validation (#182) (#187)
  - Proper email format in API requests
  - Better User-Agent string construction
  - Improved API compatibility
- **Exception Handling**: Complete removal of bare exception handlers (#165, #174, #176)
  - More specific exception catching
  - Better error messages and debugging
  - Strict compliance with coding standards
- **Import Organization**: Moved mid-function imports to top of files (#180)
  - PEP 8 compliance
  - Improved code organization
  - Better static analysis support
- **Example Script Timeout**: Increased from 30 to 90 seconds (#192)
  - More reliable example execution
  - Better handling of slow network conditions
  - Improved user experience with examples
- **Flaky Test Assertions**: Removed timing-dependent test assertions (#183)
  - More reliable test suite
  - Eliminated intermittent test failures
  - Improved CI/CD stability

### Refactored
- **_make_final_assessment Method**: Broke down from 113 to 29 code lines (#181)
  - Improved readability and maintainability
  - Better testability through smaller functions
  - Reduced complexity
- **InputNormalizer Decoupling**: Separated from CacheManager (#158)
  - Better separation of concerns
  - More testable components
  - Improved modularity
- **HybridBackend and Kscien**: Removed redundant code (#154)
  - Cleaner codebase
  - Reduced maintenance burden
  - Improved clarity

### Documentation
- **Security Documentation**: Comprehensive SSL verification fallback documentation (#155)
  - Clear security considerations
  - Fallback behavior explanation
  - Risk mitigation guidance
- **README Improvements**: Reorganized AI-Assisted Development section (#161)
  - Better documentation structure
  - Clearer guidance for contributors
  - Improved accessibility

### Testing & Quality
- **Test Coverage Improvements**: Significant coverage increases across multiple modules
  - article_retraction_checker: 98% coverage (#167) (#179)
  - batch_assessor.py: 9% → 93% coverage (#177)
  - CrossrefAnalyzerBackend: Improved coverage (#196)
  - General test coverage for issue #6 (#195, #197)
- **Parallel Test Execution**: Added parallel testing to speed up quality checks (#186) (#190)
  - Faster CI/CD pipeline
  - Improved developer experience
  - More efficient resource utilization
- **Pytest Warnings**: Removed warnings for non-async test functions (#194)
  - Cleaner test output
  - Better test suite hygiene
  - Improved debugging experience

### Development Workflow
- **Release Preparation**: Infrastructure for first official 1.0.0 release (#191)
  - Version management improvements
  - Release process documentation
  - Quality assurance enhancements

## [0.5.0] - 2025-11-24

### Added
- **Conference Acronym Management**: New `conference-acronym` CLI command group for managing conference acronyms (#101)
  - List, add, update, and delete conference acronyms
  - Support for acronym normalization and equivalence management
  - Integration with self-learning acronym recognition system
- **Venue Type Detection**: Enhanced publication type handling for journals, conferences, and preprints (#100)
  - Automatic detection of publication venue types
  - Specialized assessment paths for different publication categories
  - Improved classification accuracy through type-aware processing
- **ArXiv Preprint Support**: Dedicated handling for arXiv preprints separate from journal/conference assessment (#89)
  - Recognizes arXiv identifiers and URLs
  - Bypasses predatory journal assessment for legitimate preprint servers
  - Maintains assessment quality while reducing false positives
- **Self-Learning Conference Acronym Recognition**: Intelligent acronym matching system (#86)
  - Automatic learning and recognition of conference acronyms
  - Dynamic acronym database updates
  - Improved venue identification through acronym equivalence
- **Post-PR Merge Cleanup Script**: Automated development workflow cleanup (#99)
  - Streamlines post-merge branch cleanup
  - Integrated with development workflow documentation
  - Reduces manual maintenance overhead

### Enhanced
- **Conference Name Normalization**: Comprehensive venue name processing to reduce 'unknown' assessments (#85, #81)
  - Preserves critical acronyms while normalizing variations
  - Handles common conference name patterns and variations
  - Significantly improves venue identification accuracy
- **Case-Insensitive Venue Matching**: Improved matching accuracy through case normalization (#84)
  - Eliminates case-sensitivity issues in venue identification
  - Better handling of mixed-case venue names
  - Consistent matching across different input formats
- **LaTeX Processing**: Enhanced cleaning of LaTeX escape sequences in venue names (#83)
  - Removes LaTeX formatting artifacts from BibTeX entries
  - Improves venue name clarity and matching accuracy
  - Better handling of special characters and formatting
- **OpenAlex Conference Scoring**: Enhanced recognition of high-quality single-year conference instances (#82)
  - Better assessment of conference quality metrics
  - Improved handling of one-time or irregular conferences
  - More nuanced quality scoring for diverse conference patterns
- **Bracket Removal**: Improved journal name processing by removing brackets for better matching (#68)
  - Handles common bracketed additions in venue names
  - Improves matching accuracy by focusing on core venue names
  - Reduces false negatives in venue identification

### Fixed
- **Acronym and Venue Name Normalization**: Improved processing accuracy (#119)
  - More robust acronym processing and normalization
  - Better handling of edge cases in venue name variants
  - Enhanced consistency in acronym recognition
- **Documentation Links**: Fixed broken markdown links across documentation (#118)
  - Comprehensive link validation and repair
  - Improved documentation accessibility and navigation
  - Added automated link checking to prevent future issues
- **Database Isolation**: Test database now properly isolated from production cache (#116)
  - Prevents test data contamination of production cache
  - Ensures clean separation of test and production environments
  - Improves reliability of both testing and production usage
- **Configuration Management**: Corrected tool names in settings and configuration files (#108)
  - Fixed inconsistencies in tool naming conventions
  - Improved configuration accuracy and reliability
  - Better alignment with actual tool implementations
- **CI/CD Pipeline**: Enhanced caching and file handling in GitHub Actions workflows (#96, #93)
  - Replaced manual cache implementations with built-in solutions
  - Fixed glob pattern issues in CI file handling
  - Improved build reliability and performance

### Assessment Quality
- **Suspicious Assessment Category**: New evaluation result for heuristic-only assessments (#66)
  - Provides intermediate assessment category for uncertain cases
  - Better granularity in assessment confidence reporting
  - Helps users understand assessment reliability levels
- **Conference Architecture Refactoring**: Fixed conference misclassification issues (#80)
  - Improved separation between journal and conference assessment paths
  - Better handling of hybrid publication venues
  - More accurate classification of publication types

### Documentation
- **README Enhancements**: Improved documentation with core assessment questions and expectations (#106)
  - Clearer explanation of tool capabilities and limitations
  - Better guidance on expected outcomes and usage
  - Enhanced user understanding of assessment methodology
- **Agent Configuration Unification**: Standardized AI agent configuration through AGENTS.md (#97)
  - Consolidated agent guidelines and best practices
  - Improved consistency across development tools
  - Better integration with AI-assisted development workflows

### Development Workflow
- **Error Handling Improvements**: Enhanced logging and encapsulation for conference processing (#91)
  - Better error reporting and debugging capabilities
  - Improved fault tolerance in conference series processing
  - More informative error messages for troubleshooting

## [0.4.0] - 2025-11-21

### Added
- **Python API Examples**: Comprehensive standalone demonstration scripts in examples/ directory
  - basic_assessment.py: Single journal and batch assessment examples
  - bibtex_processing.py: BibTeX file processing and result aggregation
  - Complete README with setup instructions and usage guidance
- **Relaxed BibTeX Parsing**: Optional --relax-bibtex flag for handling malformed BibTeX files
  - Enables lenient parsing mode for files with common formatting issues
  - Handles too many commas in author lists, repeated entries, and syntax errors
  - Maintains strict parsing as default for quality control
- **Performance Timing Instrumentation**: Per-backend execution timing for performance monitoring
- **Enhanced Caching System**: Multiple performance optimization features
  - Cross Validator results caching to prevent redundant backend queries
  - Retraction Watch backend results caching to prevent redundant API calls
  - Scopus backend queries optimization with functional indexes
  - CachedBackend database query optimization to eliminate O(n) filtering

### Changed
- **Cross Validator Backend Architecture**: Refactored to use HybridBackend pattern
  - Eliminates redundant queries to OpenAlex and Crossref backends
  - Cached queries complete in <50ms vs 400-800ms for fresh queries
  - Cross-validation results cached as complete units with 24-hour TTL

### Fixed
- **Email Configuration**: Resolved backend email configuration issues
- **Cache Flag Propagation**: Fixed cached flag propagation in CrossValidatorBackend
- **Database Performance**: Optimized query patterns across multiple backend implementations

### Performance Improvements
- **Query Optimization**: Significant performance gains through comprehensive caching strategy
- **Database Efficiency**: Functional indexes and optimized filtering reduce query overhead
- **API Call Reduction**: Smart caching prevents redundant external API requests

## [0.3.0] - 2025-11-20

### Added
- **Enhanced Database Schema**: Journal URLs are now extracted and stored in dedicated journal_urls table for improved data structure
- **Comprehensive Development Workflow**: Added detailed development process documentation in AICodingAgent.md
- **Code Quality Standards**: Implemented SPDX license identifiers across all Python files for better compliance

### Changed
- **Backend Naming Convention**: Unified all backend names to consistent lowercase snake_case format
- **Import Organization**: Reorganized import statements across codebase to follow PEP 8 guidelines
- **CI/CD Pipeline**: Enhanced security scanning alignment with release pipeline and optimized PyPI publishing workflow

### Fixed
- **Database Operations**: Fixed URL extraction in AsyncDBWriter to properly populate journal_urls table
- **Configuration Output**: Removed timestamp prefix from config command output to ensure valid YAML format
- **Test Suite**: Eliminated RuntimeWarning about unawaited coroutines in test suite
- **CI Infrastructure**:
  - Removed unnecessary unrar fallback in macOS CI to eliminate warnings
  - Cleaned up unused GitHub Pages deployment configuration
  - Improved security scanning integration

### Removed
- **Legacy Code**: Removed backward compatibility code and comments no longer needed
- **Redundant CI Jobs**: Cleaned up duplicate PyPI publishing jobs from CI configuration

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
