# Configuration Reference

Complete reference for configuring the Journal Assessment Tool.

## TL;DR

- **View current config**: `aletheia-probe config` displays the complete configuration
- **Override settings**: Use the same YAML schema structure to override any configuration option
- **Config file location**: `.aletheia-probe/config.yaml` in your project directory

## Table of Contents

1. [Overview](#overview)
2. [Configuration File Format](#configuration-file-format)
3. [Configuration Locations](#configuration-locations)
4. [Backend Configuration](#backend-configuration)
5. [Assessment Heuristics](#assessment-heuristics)
6. [Output Configuration](#output-configuration)
7. [Cache Configuration](#cache-configuration)
8. [Environment Variables](#environment-variables)
9. [Examples](#examples)

## Overview

The Journal Assessment Tool uses YAML configuration files to customize behavior, backend settings, and assessment parameters. Configuration is optional - the tool works with sensible defaults out of the box.

## Configuration File Format

Configuration uses YAML format with four main sections:

```yaml
backends:      # Backend-specific settings
heuristics:    # Assessment algorithm parameters
output:        # Output formatting options
cache:         # Cache and synchronization settings
```

## Configuration Locations

The tool searches for configuration files in this order:

1. **Command line**: File specified with `--config /path/to/config.yaml`
2. **Project directory**: `.aletheia-probe/config.yaml` (recommended)
3. **User directory**: `~/.config/aletheia-probe/config.yaml`
4. **System directory**: `/etc/aletheia-probe/config.yaml`

The first file found is used. Later files are ignored.

**Recommended**: Place your configuration in `.aletheia-probe/config.yaml` within your project directory for project-specific settings.

## Backend Configuration

### General Backend Settings

Each backend can be configured with these common parameters:

```yaml
backends:
  backend_name:
    enabled: true           # Enable/disable backend
    weight: 1.0            # Weight in final assessment (0.0-2.0)
    timeout: 10            # Timeout in seconds
    rate_limit: 60         # Requests per minute (null for unlimited)
    email: null            # Email for API identification (Crossref, OpenAlex)
    config: {}             # Backend-specific settings
```

### API Email Configuration

Several backends (crossref_analyzer, openalex_analyzer, cross_validator) use the `email` parameter for API identification and rate limiting. These APIs follow "polite pool" access patterns and require contact information for higher rate limits.

**Default Behavior**: If no email is configured, backends use `noreply@aletheia-probe.org` as a default contact address.

**Recommended Configuration**: Configure your own email address to:
- Comply with API provider policies
- Get better rate limits and support
- Identify your requests in API logs

```yaml
backends:
  crossref_analyzer:
    enabled: true
    email: "your.email@institution.org"  # Your contact email

  openalex_analyzer:
    enabled: true
    email: "your.email@institution.org"  # Your contact email

  cross_validator:
    enabled: true
    email: "your.email@institution.org"  # Your contact email

  doaj:
    enabled: true
    config:
      cache_ttl_hours: 48  # Cache results for 48 hours instead of default 24
```

**Important Notes**:
- Use a valid email address that you monitor
- The same email can be used for all backends
- Email is sent in the User-Agent header as `AletheiaProbe/1.0 (mailto:your.email@institution.org)`
- No emails are sent to this address - it's purely for identification
- In shared or public setups, consider using a dedicated service email rather than personal addresses
- Additional parameters like `cache_ttl_hours` can be configured in the `config` section
- Email format is validated - invalid emails will cause configuration errors

### DOAJ Backend

```yaml
backends:
  doaj:
    enabled: true
    weight: 1.0
    timeout: 10
    rate_limit: 60
    config:
      api_base_url: "https://doaj.org/api/v1"
      search_fields: ["title", "issn", "eissn"]
      require_seal: false    # Require DOAJ Seal for legitimacy
```

**Parameters**:
- `api_base_url`: DOAJ API endpoint
- `search_fields`: Fields to search in DOAJ
- `require_seal`: Whether DOAJ Seal is required for positive assessment

### Beall's List Backend

```yaml
backends:
  bealls:
    enabled: true
    weight: 0.8
    timeout: 5
    config:
      list_sources:
        - "bealls_list_journals.csv"
        - "bealls_list_publishers.csv"
      match_threshold: 0.8   # String similarity threshold
```

**Parameters**:
- `list_sources`: CSV files containing predatory journal/publisher lists
- `match_threshold`: Minimum similarity score for matches (0.0-1.0)

### Retraction Watch Backend

```yaml
backends:
  retraction_watch:
    enabled: true
    weight: 0.7
    timeout: 15
    config:
      gitlab_base_url: "https://gitlab.com"
      project_id: "your_project_id"
      retraction_threshold: 0.005  # 0.5% retraction rate threshold
      min_publications: 100        # Minimum publications for analysis
```

**Parameters**:
- `gitlab_base_url`: GitLab instance URL
- `project_id`: GitLab project containing retraction data
- `retraction_threshold`: Retraction rate above which journal is flagged
- `min_publications`: Minimum publication count for statistical significance

### Algerian Ministry Backend

```yaml
backends:
  algerian_ministry:
    enabled: true
    weight: 1.2
    timeout: 10
    config:
      whitelist_file: "algerian_ministry_whitelist.csv"
      blacklist_file: "algerian_ministry_blacklist.csv"
      category_weights:
        "Category A": 1.0
        "Category B": 0.8
        "Category C": 0.6
```

**Parameters**:
- `whitelist_file`: CSV file with approved journals
- `blacklist_file`: CSV file with disapproved journals
- `category_weights`: Weights for different journal categories

### PredatoryJournals.com Backend

```yaml
backends:
  predatoryjournals:
    enabled: true
    weight: 0.9
    timeout: 5
    config:
      cache_ttl_hours: 720  # 30 days - monthly cache for community lists
```

**Configuration**:
- `cache_ttl_hours`: How long cached predatory journal list data remains valid before requiring re-sync. Default is 720 hours (30 days). The predatoryjournals.org lists are community-maintained and updated monthly, so longer cache periods are appropriate.

See `src/aletheia_probe/backends/predatoryjournals.py`

### UGC-CARE Discontinued Lists Backends

```yaml
backends:
  ugc_care_cloned:
    enabled: true
    weight: 0.9
    timeout: 5
    config:
      cache_ttl_hours: 720  # 30 days - discontinued static list

  ugc_care_cloned_group2:
    enabled: true
    weight: 0.9
    timeout: 5
    config:
      cache_ttl_hours: 720  # 30 days - discontinued static list

  ugc_care_delisted_group2:
    enabled: true
    weight: 0.9
    timeout: 5
    config:
      cache_ttl_hours: 720  # 30 days - discontinued static list

  ugc_care_included_from_clone_group1:
    enabled: true
    weight: 1.0
    timeout: 5
    config:
      cache_ttl_hours: 720  # 30 days - discontinued static list

  ugc_care_included_from_clone_group2:
    enabled: true
    weight: 1.0
    timeout: 5
    config:
      cache_ttl_hours: 720  # 30 days - discontinued static list
```

**Configuration**:
- `cache_ttl_hours`: How long cached UGC-CARE list data remains valid before requiring re-sync. Default is 720 hours (30 days), appropriate for discontinued/frozen sources.

**Backend Descriptions**:
- `ugc_care_cloned`: UGC-CARE Group I cloned journals list
- `ugc_care_cloned_group2`: UGC-CARE Group II cloned journals list
- `ugc_care_delisted_group2`: UGC-CARE Group II delisted journals list
- `ugc_care_included_from_clone_group1`: UGC-CARE Group I included journals from clone correction page (left side)
- `ugc_care_included_from_clone_group2`: UGC-CARE Group II included journals from clone correction page (left side)

See implementations in:
- `src/aletheia_probe/backends/ugc_care_cloned.py`
- `src/aletheia_probe/backends/ugc_care_cloned_group2.py`
- `src/aletheia_probe/backends/ugc_care_delisted_group2.py`
- `src/aletheia_probe/backends/ugc_care_included_from_clone_group1.py`
- `src/aletheia_probe/backends/ugc_care_included_from_clone_group2.py`

### Kscien Backends

The Kscien suite provides curated lists of predatory journals, publishers, hijacked journals, and conferences. All Kscien backends share the same configuration pattern.

```yaml
backends:
  kscien_standalone_journals:
    enabled: true
    weight: 0.9
    timeout: 5
    config:
      cache_ttl_hours: 168  # 7 days - weekly cache

  kscien_publishers:
    enabled: true
    weight: 0.9
    timeout: 5
    config:
      cache_ttl_hours: 168  # 7 days - weekly cache

  kscien_hijacked_journals:
    enabled: true
    weight: 1.0
    timeout: 5
    config:
      cache_ttl_hours: 168  # 7 days - weekly cache

  kscien_predatory_conferences:
    enabled: true
    weight: 0.8
    timeout: 5
    config:
      cache_ttl_hours: 168  # 7 days - weekly cache
```

**Configuration**:
- `cache_ttl_hours`: How long cached list data remains valid. Default is 168 hours (7 days). Kscien lists are updated weekly, so weekly cache refresh is recommended. Increase for more stable environments, decrease if you need the latest additions.

**Backend Descriptions**:
- `kscien_standalone_journals`: Checks against standalone predatory journals
- `kscien_publishers`: Checks against predatory publishers
- `kscien_hijacked_journals`: Identifies hijacked journals (clones of legitimate journals)
- `kscien_predatory_conferences`: Checks against predatory conference lists

See backend implementations in `src/aletheia_probe/backends/kscien_*.py`

### Scopus Backend

```yaml
backends:
  scopus:
    enabled: true
    weight: 1.2
    timeout: 5
    config:
      cache_ttl_hours: 720  # 30 days - monthly cache
```

**Configuration**:
- `cache_ttl_hours`: How long cached Scopus data remains valid. Default is 720 hours (30 days). Since Scopus uses user-provided static files, longer cache periods are appropriate.

**Important Notes**:
- Scopus backend requires manual setup - users must download and place Scopus journal list Excel file in `~/.aletheia-probe/scopus/`
- This backend identifies legitimate journals indexed in Scopus
- Backend remains inactive until Scopus data file is provided

See `src/aletheia_probe/backends/scopus.py`

### Cross-Validator Backend

```yaml
backends:
  cross_validator:
    enabled: true
    weight: 1.3
    timeout: 20
    email: "your.email@institution.org"
    config:
      cache_ttl_hours: 24  # Cache query results for 24 hours
```

**Configuration**:
- `email`: Contact email for API identification (OpenAlex and Crossref). Default is `noreply@aletheia-probe.org`. Configure your own email for better rate limits and API compliance.
- `cache_ttl_hours`: How long individual query results are cached. Default is 24 hours. Cross-validator performs API queries to both OpenAlex and Crossref, so caching reduces API load.

**Purpose**:
Cross-validator combines and cross-validates data from OpenAlex and Crossref backends. It performs consistency checks on publisher names, publication volumes, DOAJ listings, and activity timelines across both sources. When backends agree, confidence is boosted; when they disagree, confidence is reduced.

**When to Adjust**:
- Set shorter `cache_ttl_hours` (1-6 hours) when assessing newly published journals or during active research
- Set longer `cache_ttl_hours` (48-168 hours) for batch processing or when API rate limits are a concern
- Configure `email` to comply with API polite pool policies and get better rate limits

See `src/aletheia_probe/backends/cross_validator.py`

## Assessment Heuristics

Configuration for the assessment algorithm:

```yaml
heuristics:
  confidence_threshold: 0.6        # Minimum confidence for definitive assessment
  unknown_threshold: 0.3           # Below this threshold, assessment is "unknown"
  backend_agreement_bonus: 0.2     # Bonus when multiple backends agree
  disagreement_penalty: 0.1        # Penalty when backends disagree
  new_journal_penalty: 0.1         # Penalty for journals with limited history

  # Confidence scoring weights
  scoring:
    exact_match_bonus: 0.2         # Bonus for exact name/ISSN matches
    issn_match_bonus: 0.3          # Bonus when ISSN matches
    publisher_match_bonus: 0.1     # Bonus when publisher matches
    multiple_source_bonus: 0.15    # Bonus when found in multiple sources

  # Thresholds for assessment categories
  thresholds:
    legitimate: 0.7                # Score above this = legitimate
    predatory: 0.4                 # Score below this = predatory
    # Between predatory and legitimate = insufficient_data
```

**Parameters**:
- `confidence_threshold`: Minimum confidence for non-"unknown" assessment
- `unknown_threshold`: Below this confidence, assessment becomes "unknown"
- `backend_agreement_bonus`: Added when multiple backends agree
- `disagreement_penalty`: Subtracted when backends disagree
- `new_journal_penalty`: Applied to recently founded journals
- `scoring.*`: Various bonus/penalty factors for match quality
- `thresholds.*`: Score boundaries for assessment categories

## Output Configuration

Settings for output formatting:

```yaml
output:
  format: "text"                   # Default format: text, json, yaml
  verbose: false                   # Include detailed backend information
  include_raw_data: false          # Include raw backend responses
  color: true                      # Use color in terminal output

  # Text output customization
  text:
    show_sources: true             # Show individual source results
    show_reasoning: true           # Show assessment reasoning
    show_metadata: true            # Show journal metadata
    show_timing: false             # Show processing times

  # JSON output customization
  json:
    pretty_print: true             # Format JSON with indentation
    include_null_fields: false     # Include fields with null values

  # YAML output customization
  yaml:
    default_style: null            # YAML style (null, '|', '>', etc.)
    indent: 2                      # Indentation spaces
```

## Cache Configuration

Settings for data caching and synchronization:

```yaml
cache:
  # Automatic synchronization
  auto_sync: true                  # Sync backend data automatically
  sync_on_startup: true            # Sync when tool starts (if data is old)
  update_threshold_days: 7         # Sync if data older than N days

  # Cache management
  cleanup_disabled: true           # Remove data for disabled backends
  max_cache_size_mb: 100          # Maximum cache size in megabytes
  cache_ttl_hours: 24             # Default cache TTL for backend results

  # Storage locations
  cache_directory: null           # Custom cache directory (null = default)
  backend_data_dir: null          # Directory for backend data files

  # Performance settings
  async_cache_writes: true        # Write cache data asynchronously
  compress_cache: true            # Compress cached data
```

**Parameters**:
- `auto_sync`: Whether to automatically update backend data
- `sync_on_startup`: Check for updates when tool starts
- `update_threshold_days`: Age in days before data is considered stale
- `cleanup_disabled`: Remove cached data for disabled backends
- `max_cache_size_mb`: Maximum cache size before cleanup
- `cache_ttl_hours`: How long to cache individual query results

## Environment Variables

Configuration can also be set via environment variables:

```bash
# Override configuration file location
export JOURNAL_ASSESS_CONFIG="/path/to/config.yaml"

# Override specific settings
export JOURNAL_ASSESS_FORMAT="json"
export JOURNAL_ASSESS_VERBOSE="true"
export JOURNAL_ASSESS_TIMEOUT="30"

# Backend-specific settings
export JOURNAL_ASSESS_DOAJ_ENABLED="true"
export JOURNAL_ASSESS_DOAJ_WEIGHT="1.0"
export JOURNAL_ASSESS_BEALLS_ENABLED="false"
```

Environment variables use the format: `JOURNAL_ASSESS_[SECTION_][SUBSECTION_]KEY`

## Examples

### Minimal Configuration

```yaml
# ~/.config/aletheia-probe/config.yaml
backends:
  doaj:
    enabled: true
  bealls:
    enabled: true
  crossref_analyzer:
    enabled: true
    email: "researcher@university.edu"  # Your contact email for API access

heuristics:
  confidence_threshold: 0.6

output:
  format: json
```

### Conservative Configuration

Higher confidence requirements, stricter thresholds:

```yaml
backends:
  doaj:
    enabled: true
    weight: 1.5
    config:
      require_seal: true

  bealls:
    enabled: true
    weight: 1.0
    config:
      match_threshold: 0.9

  retraction_watch:
    enabled: true
    weight: 1.0
    config:
      retraction_threshold: 0.003  # Stricter 0.3% threshold

heuristics:
  confidence_threshold: 0.8        # Higher confidence required
  unknown_threshold: 0.5
  thresholds:
    legitimate: 0.8
    predatory: 0.3

output:
  verbose: true
  text:
    show_reasoning: true
```

### Development Configuration

Useful for testing and development:

```yaml
backends:
  doaj:
    enabled: true
    timeout: 30
    config:
      api_base_url: "http://localhost:8000/api/v1"  # Local test server

cache:
  auto_sync: false                 # Manual control over data updates
  cache_ttl_hours: 1              # Short cache TTL for testing

output:
  verbose: true
  include_raw_data: true
  text:
    show_timing: true
```

### Institutional Configuration

Example for a university setting:

```yaml
backends:
  doaj:
    enabled: true
    weight: 1.2

  algerian_ministry:              # Or other institutional backend
    enabled: true
    weight: 1.5                   # Higher weight for institutional policy
    config:
      whitelist_file: "/etc.aletheia-probe/university-approved.csv"

  bealls:
    enabled: true
    weight: 1.0

heuristics:
  confidence_threshold: 0.7
  backend_agreement_bonus: 0.3    # Reward agreement

  thresholds:
    legitimate: 0.75              # Higher bar for legitimacy
    predatory: 0.35

cache:
  update_threshold_days: 3        # Keep data fresh
  cleanup_disabled: true

output:
  format: json
  json:
    pretty_print: true
```

### Performance-Optimized Configuration

For high-throughput usage:

```yaml
backends:
  doaj:
    enabled: true
    timeout: 5                    # Shorter timeouts
    rate_limit: 120              # Higher rate limit

  bealls:
    enabled: true
    timeout: 3

cache:
  async_cache_writes: true        # Async cache operations
  compress_cache: false          # Skip compression for speed
  cache_ttl_hours: 48            # Longer cache TTL

heuristics:
  confidence_threshold: 0.5       # Lower threshold for speed

output:
  format: json
  verbose: false                  # Minimal output
  json:
    include_null_fields: false
```

## Validation

The tool validates configuration on startup. Common validation errors:

- **Invalid YAML syntax**: Check indentation and syntax
- **Unknown backend names**: Verify backend names are correct
- **Invalid weight values**: Weights must be 0.0-2.0
- **Invalid timeout values**: Timeouts must be positive integers
- **Missing required files**: Backend data files must exist
- **Invalid threshold ranges**: Confidence/score thresholds must be 0.0-1.0

## Configuration Testing

Test your configuration:

```bash
# Validate configuration
aletheia-probe config

# Check backend status
aletheia-probe status

# Test with verbose output
aletheia-probe journal --verbose "Test Journal"
```

## Troubleshooting Configuration

### Common Issues

1. **YAML syntax errors**: Use online YAML validators
2. **File not found**: Check file paths and permissions
3. **Backend failures**: Verify API endpoints and credentials
4. **Unexpected results**: Review weights and thresholds

### Debug Configuration

```bash
# Show current configuration
aletheia-probe config

# Check backend status
aletheia-probe status

# Test with verbose output
aletheia-probe journal --verbose "Test Journal"
```
