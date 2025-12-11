# User Guide

This comprehensive guide covers all aspects of using the Journal Assessment Tool for evaluating academic journals.

## Table of Contents

1. [Overview](#overview)
2. [Installation](#installation)
3. [Quick Start](#quick-start)
4. [Command Line Usage](#command-line-usage)
5. [Output Formats](#output-formats)
6. [Understanding Results](#understanding-results)
7. [Configuration](#configuration)
8. [Conference Acronym Management](#conference-acronym-management)
9. [Data Sources](#data-sources)
10. [Best Practices](#best-practices)
11. [Troubleshooting](#troubleshooting)

## Overview

The Journal Assessment Tool helps researchers and institutions evaluate whether academic journals are legitimate or potentially predatory by checking multiple authoritative data sources and providing confidence-scored assessments.

### Key Features

- **Multi-source verification**: Combines DOAJ, Beall's List, Retraction Watch, and institutional data
- **BibTeX batch processing**: Assess entire bibliographies from BibTeX files with automated exit codes
- **Intelligent matching**: Handles name variations, ISSNs, and publisher information
- **Confidence scoring**: Provides probabilistic assessments with clear reasoning
- **Fast performance**: Local caching reduces API calls and improves speed
- **Flexible output**: JSON, YAML, or human-readable formats

## Installation

### System Requirements

- Python 3.10 or higher
- Internet connection for data source queries
- 50MB disk space for local cache

### Install from PyPI

```bash
pip install aletheia-probe
```

### Install from Source

```bash
git clone https://github.com/sustainet-guardian/aletheia-probe.git
cd aletheia-probe
pip install -e ".[dev]"
```

### Verify Installation

```bash
aletheia-probe --version
aletheia-probe --help
```

## Quick Start

### Basic Assessment

```bash
# Assess a single journal by name
aletheia-probe journal "Journal of Computer Science"

# Include ISSN for better accuracy
aletheia-probe journal "Nature (ISSN: 0028-0836)"

# Assess all journals in a BibTeX file
aletheia-probe bibtex references.bib
```

### Output Examples

**Standard output:**
```
Journal: Journal of Computer Science
Assessment: insufficient_data
Confidence: 0.15
Sources checked: DOAJ, Beall's List, Retraction Watch
Reasoning: Journal not found in major indexes
```

**JSON output:**
```bash
aletheia-probe journal --format json "Nature"
```

```json
{
  "assessment": "legitimate",
  "confidence": 0.95,
  "overall_score": 0.92,
  "backend_results": [
    {
      "backend_name": "DOAJ",
      "status": "found",
      "confidence": 0.90,
      "assessment": "legitimate"
    }
  ],
  "reasoning": [
    "Found in DOAJ with verified publisher information",
    "Strong publication history and editorial board"
  ]
}
```

## Command Line Usage

### Basic Commands

```bash
# Single journal assessment
aletheia-probe journal "Journal Name"

# BibTeX file assessment
aletheia-probe bibtex references.bib

# Multiple formats
aletheia-probe journal --format json "Journal Name"
aletheia-probe bibtex --format json references.bib
```

### BibTeX Batch Assessment

The tool can process entire BibTeX files, making it ideal for checking manuscript bibliographies, research databases, or academic collections.

#### Why Assess BibTeX Files?
Aletheia-Probe helps answer a critical question for researchers: **Are the journal entries in my bibtex file valid?**

#### Basic BibTeX Commands

```bash
# Assess all journals in a BibTeX file
aletheia-probe bibtex my_references.bib

# JSON output for integration with other tools
aletheia-probe bibtex --format json my_references.bib
```

#### Exit Code Behavior

The BibTeX command returns specific exit codes for automation:

- **Exit code 0**: No predatory journals found (safe to proceed)
- **Exit code 1**: Predatory journals detected (action required)

#### Integration Examples

**In shell scripts:**
```bash
if aletheia-probe bibtex references.bib; then
    echo "✅ Bibliography is clean - proceeding with submission"
else
    echo "❌ Predatory journals found - please review bibliography"
    exit 1
fi
```

**In CI/CD pipelines:**
```yaml
# GitHub Actions example
- name: Check Bibliography
  run: |
    aletheia-probe bibtex manuscript/references.bib
```

**In Makefiles:**
```makefile
check-refs:
	aletheia-probe bibtex references.bib || (echo "Bibliography check failed" && exit 1)

submit: check-refs
	# Proceed with submission only if bibliography is clean
	submit-manuscript.sh
```

#### Handling Malformed BibTeX Files

When working with BibTeX files from various sources, you may encounter files with non-standard formatting or syntax issues. The `--relax-bibtex` flag enables relaxed parsing mode to handle these cases:

```bash
# Enable relaxed parsing for malformed BibTeX files
aletheia-probe bibtex --relax-bibtex references.bib

# Combine with other options
aletheia-probe bibtex --relax-bibtex --format json references.bib
```

**When to use `--relax-bibtex`:**
- Processing BibTeX files from different bibliography managers
- Handling files with non-standard formatting
- Working with legacy or auto-generated BibTeX files
- Troubleshooting parsing errors

This flag allows the parser to be more forgiving of common BibTeX syntax issues while still extracting journal information for assessment. See `src/aletheia_probe/cli.py` for implementation details.

#### BibTeX Output Examples

**Text format:**
```
BibTeX Assessment Summary
========================================
File: references.bib
Total entries processed: 25
Processing time: 12.3s

Assessment Results:
  Predatory journals: 2
  Legitimate journals: 18
  Insufficient data: 5

⚠️  WARNING: Predatory journals detected!

Detailed Results:
----------------------------------------
❌ International Journal of Computer Science Issues (predatory, confidence: 1.00)
    • Classified as predatory based on 2 source(s)
    • algerian_ministry: predatory (confidence: 0.90)
✅ Nature (legitimate, confidence: 0.85)
    • Classified as legitimate based on 1 source(s)
    • 📊 153 retraction(s): 0.034% rate (within normal range)
```

**JSON format for automation:**
```json
{
  "file_path": "references.bib",
  "total_entries": 25,
  "predatory_count": 2,
  "legitimate_count": 18,
  "insufficient_data_count": 5,
  "has_predatory_journals": true,
  "processing_time": 12.34,
  "assessment_results": [
    {
      "entry": {
        "key": "smith2023",
        "journal_name": "Nature",
        "entry_type": "article",
        "title": "Recent Advances in AI"
      },
      "assessment": {
        "assessment": "legitimate",
        "confidence": 0.85,
        "reasoning": ["Found in DOAJ with verified information"]
      }
    }
  ]
}
```

### Advanced Options

```bash
# Verbose output with detailed backend information
aletheia-probe journal --verbose "Journal Name"

# Different output format
aletheia-probe journal --format json "Journal Name"
```

### Batch Processing

#### BibTeX Files (Recommended)

```bash
# Assess entire bibliography
aletheia-probe bibtex references.bib

# Multiple BibTeX files
for file in *.bib; do aletheia-probe bibtex "$file"; done

# Save results
aletheia-probe bibtex --format json references.bib > assessment_results.json
```

#### Text Lists (Alternative)

```bash
# Process multiple journals from command line
echo "Journal of AI\nNature\nPredatory Journal" | xargs -I {} aletheia-probe journal "{}"

# From file
cat journals.txt | xargs -I {} aletheia-probe journal --format json "{}" > results.json
```

### Data Management

#### Syncing Backend Data

Update local cache with fresh data from configured backends:

```bash
# Sync all backends
aletheia-probe sync

# Sync specific backends only
aletheia-probe sync scopus
aletheia-probe sync bealls doaj

# Force sync even if data appears fresh
aletheia-probe sync --force
```

**Backend filtering** allows selective synchronization of data sources rather than updating all backends. This is useful for:
- Testing specific backend configurations
- Reducing sync time when only certain data needs updating
- Troubleshooting individual backend connections

To see available backend names, use `aletheia-probe status`. For implementation details, see `src/aletheia_probe/cli.py`.

#### Clearing the Cache

Remove all cached assessment results to force fresh queries:

```bash
# Clear cache with confirmation prompt
aletheia-probe clear-cache

# Clear cache without confirmation (for automation)
aletheia-probe clear-cache --confirm
```

The `--confirm` flag skips the interactive confirmation prompt, making it suitable for:
- Automated scripts and workflows
- CI/CD pipelines
- Scheduled maintenance tasks
- Non-interactive environments

**Note:** Clearing the cache does not remove backend data from sync operations, only assessment result caches.

#### Configuration

```bash
# Show configuration
aletheia-probe config
```

## Output Formats

### Text Format (Default)

Human-readable output suitable for terminal use:

```
Journal: PLOS ONE
Assessment: legitimate
Confidence: 0.88
Overall Score: 0.85

Sources:
  ✓ DOAJ: Found (confidence: 0.90)
  ✗ Beall's List: Not found
  ✓ Retraction Watch: Low retraction rate (confidence: 0.85)

Reasoning:
  • Listed in DOAJ directory with verified information
  • Retraction rate below 0.5% threshold
  • Established peer review process
```

### JSON Format

Structured data suitable for programmatic processing:

```json
{
  "input_query": "PLOS ONE",
  "assessment": "legitimate",
  "confidence": 0.88,
  "overall_score": 0.85,
  "backend_results": [
    {
      "backend_name": "DOAJ",
      "status": "found",
      "confidence": 0.90,
      "assessment": "legitimate",
      "data": {
        "issn": "1932-6203",
        "publisher": "Public Library of Science"
      },
      "response_time": 0.45
    }
  ],
  "metadata": {
    "name": "PLOS ONE",
    "issn": "1932-6203",
    "publisher": "Public Library of Science",
    "open_access": true
  },
  "reasoning": [
    "Listed in DOAJ directory with verified information",
    "Retraction rate below 0.5% threshold"
  ],
  "timestamp": "2024-11-08T12:30:45Z",
  "processing_time": 1.23
}
```

## Understanding Results

### Assessment Categories

- **`legitimate`**: Journal appears to be legitimate based on available evidence
- **`predatory`**: Journal shows characteristics of predatory practices
- **`insufficient_data`**: Not enough information to make confident assessment

### Confidence Scores

Confidence scores range from 0.0 to 1.0:

- **0.8-1.0**: High confidence - strong evidence available
- **0.6-0.8**: Moderate confidence - good evidence but some uncertainty
- **0.3-0.6**: Low confidence - limited evidence available
- **0.0-0.3**: Very low confidence - insufficient data

### Overall Score

The overall score combines individual backend results weighted by:
- Backend reliability and coverage
- Agreement between sources
- Quality of evidence found

### Reasoning

Each assessment includes human-readable explanations of:
- Which sources were checked
- What evidence was found (or not found)
- Why the assessment was made
- Any caveats or limitations

## Configuration

### Default Configuration

The tool works out of the box with sensible defaults. Configuration is optional for customization.

You can view and create the initial configuration using

```bash
aletheia-probe config
```

and overwrite only those parameters you want to change.

### Configuration File Locations

The tool looks for configuration files in this order:
1. File specified by `--config` option
2. `.aletheia-probe/config.yaml`
3. `./config/config.yaml`
4. `~/.config/aletheia-probe/config.yaml`
5. `/etc/aletheia-probe/config.yaml`

### Basic Configuration

Create `./.aletheia-probe/config.yaml`:

```yaml
# Backend configuration
backends:
  doaj:
    enabled: true
    weight: 1.0
    timeout: 10

  bealls:
    enabled: true
    weight: 0.8
    timeout: 5

  crossref_analyzer:
    enabled: true
    weight: 1.0
    timeout: 15
    email: "your.email@institution.org"  # Optional for API identification

  openalex_analyzer:
    enabled: true
    weight: 1.0
    timeout: 15
    email: "your.email@institution.org"  # Optional for API identification

  retraction_watch:
    enabled: true
    weight: 0.7
    timeout: 15

# Assessment thresholds
heuristics:
  confidence_threshold: 0.6
  unknown_threshold: 0.3
  backend_agreement_bonus: 0.2

# Output preferences
output:
  format: json
  verbose: false
  include_raw_data: false

# Cache settings
cache:
  auto_sync: true
  cleanup_disabled: true
  update_threshold_days: 7
```

### API Email Configuration

Some backends (crossref_analyzer, openalex_analyzer, cross_validator) require email addresses for API identification. This follows "polite pool" access patterns to get better rate limits and support.

**Important**: Use a valid email address. The email is sent only in the User-Agent header for API identification - no emails are sent to this address.

### Backend-Specific Settings

Each backend can be configured individually:

```yaml
backends:
  doaj:
    enabled: true
    weight: 1.0
    timeout: 10

  crossref_analyzer:
    enabled: true
    weight: 1.0
    timeout: 15
    email: "research.team@university.edu"  # Optional for API identification
    config:
      cache_ttl_hours: 72  # Extended cache for institutional use

  openalex_analyzer:
    enabled: true
    weight: 1.0
    timeout: 15
    email: "research.team@university.edu"  # Optional for API identification

  retraction_watch:
    enabled: true
    weight: 0.7
    timeout: 15
    config:
      gitlab_base_url: "https://gitlab.com"
      project_id: "your_project_id"
```

## Conference Acronym Management

The conference acronym management feature helps expand conference abbreviations to their full names. This is particularly useful when processing bibliographic data where conferences may be referenced by common acronyms like "ICSE" (International Conference on Software Engineering) or "NIPS" (Neural Information Processing Systems).

### Concept

Conference acronyms are stored in a local database that maps short forms to their full conference names. The system automatically builds this mapping as it encounters conference data during journal assessments, and also allows manual management of acronym mappings.

### Purpose

- **Standardization**: Ensure consistent conference naming across bibliographic data
- **Expansion**: Convert acronyms to full names for better readability and processing
- **Data Quality**: Maintain a curated database of conference name mappings
- **Automation**: Reduce manual effort in processing conference references

### Available Commands

The `aletheia-probe conference-acronym` command group provides the following subcommands:

#### Show Database Status

```bash
# Check if acronym database has entries
aletheia-probe conference-acronym status
```

Displays basic information about the acronym database, including total count of stored mappings.

#### Display Statistics

```bash
# Show detailed database statistics
aletheia-probe conference-acronym stats
```

Provides detailed statistics including:
- Total number of acronym mappings
- Most recently used acronym
- Oldest entry in database
- Usage timestamps

#### List All Mappings

```bash
# List all acronym mappings
aletheia-probe conference-acronym list

# List with pagination
aletheia-probe conference-acronym list --limit 10
aletheia-probe conference-acronym list --limit 20 --offset 50
```

Shows all stored acronym mappings with details:
- Acronym and full conference name
- Source of the mapping (automatic detection vs. manual entry)
- Creation and last-used timestamps
- Normalized name for internal processing

#### Add Manual Mapping

```bash
# Add a new acronym mapping
aletheia-probe conference-acronym add "ICSE" "International Conference on Software Engineering"

# Add with custom source attribution
aletheia-probe conference-acronym add "NIPS" "Neural Information Processing Systems" --source "manual-2024"
```

Manually adds acronym mappings to the database. Useful for:
- Pre-populating common acronyms
- Correcting automatic mappings
- Adding institution-specific acronyms

#### Clear Database

```bash
# Clear all mappings (with confirmation prompt)
aletheia-probe conference-acronym clear

# Clear without confirmation prompt
aletheia-probe conference-acronym clear --confirm
```

Removes all acronym mappings from the database. Use with caution as this action cannot be undone.

### Usage Examples

**Building an acronym database:**
```bash
# Start with empty database
aletheia-probe conference-acronym status

# Add common computer science conferences
aletheia-probe conference-acronym add "ICSE" "International Conference on Software Engineering"
aletheia-probe conference-acronym add "FSE" "Foundations of Software Engineering"
aletheia-probe conference-acronym add "ASE" "Automated Software Engineering"

# Check what was added
aletheia-probe conference-acronym list --limit 5

# View statistics
aletheia-probe conference-acronym stats
```

**Managing existing mappings:**
```bash
# See current database size
aletheia-probe conference-acronym status

# List recent entries
aletheia-probe conference-acronym list --limit 10

# Clear outdated mappings if needed
aletheia-probe conference-acronym clear --confirm
```

### Integration with Assessment

The acronym database integrates automatically with journal assessment workflows. When processing bibliographic data, the tool uses stored mappings to expand conference acronyms, improving the accuracy of conference name matching and assessment.

For implementation details, see `src/aletheia_probe/cli.py`.

## Data Sources

### DOAJ (Directory of Open Access Journals)

**Purpose**: Identifies legitimate open access journals
**Coverage**: 22,000+ journals with verified information
**Data**: Journal metadata, publisher verification, quality standards

**What it checks**:
- Journal is listed in DOAJ directory
- Publisher information is verified
- Meets DOAJ quality criteria

### Beall's List Archives

**Purpose**: Historical database of potentially predatory journals
**Coverage**: Archives of Beall's original list and updates
**Data**: Journal names, publisher names, identifying characteristics

**What it checks**:
- Journal appears on predatory lists
- Publisher has history of questionable practices
- Pattern matching with known predatory characteristics

### Retraction Watch

**Purpose**: Quality assessment via retraction analysis
**Coverage**: Global retraction data across disciplines
**Data**: Retraction rates, patterns, journal performance metrics

**What it checks**:
- Journal's retraction rate compared to field average
- Pattern of retractions (legitimate vs. misconduct)
- Overall journal quality indicators

### Institutional Lists

**Purpose**: Custom whitelists/blacklists from institutions
**Coverage**: Institution-specific approved/disapproved journals
**Data**: Local policies, regional preferences, subject-specific lists

**What it checks**:
- Institutional approval status
- Regional or disciplinary considerations
- Local policy compliance

## Best Practices

### For Researchers

1. **Use BibTeX for multiple journals**: Batch process entire bibliographies for efficiency
2. **Use ISSN when available**: More accurate than name matching
3. **Check during writing**: Assess journals as you add references, not just at submission
4. **Consider context**: Factor in your field and institution
5. **Verify results**: Use tool output as guidance, not absolute truth
6. **Integrate with workflow**: Use exit codes in scripts for automated checking
7. **Report issues**: Help improve accuracy by reporting problems

### For Institutions

1. **Deploy BibTeX checking**: Integrate into submission systems and review processes
2. **Configure backends**: Enable relevant sources for your needs
3. **Set appropriate thresholds**: Adjust confidence levels for your policies
4. **Regular updates**: Keep data sources current with sync commands
5. **Policy integration**: Use tool results within broader evaluation frameworks
6. **Automated workflows**: Use exit codes for systematic bibliography validation
7. **Training**: Ensure users understand tool limitations and proper usage

### For Assessment Accuracy

1. **Provide complete information**: Include ISSN, full journal name
2. **Check spelling**: Ensure journal names are spelled correctly
3. **Use official names**: Use journal's official title, not abbreviations
4. **Consider timing**: New journals may not be in indexes yet
5. **Validate edge cases**: Manually verify uncertain results

## Troubleshooting

### Common Issues

#### BibTeX parsing errors

**Causes**:
- Invalid BibTeX syntax
- Corrupted or incomplete BibTeX file
- Unsupported character encoding

**Solutions**:
```bash
# Check BibTeX file syntax
bibtex-tidy --check references.bib

# Try with a minimal test file first
echo '@article{test, journal={Nature}, year={2023}}' > test.bib
aletheia-probe bibtex test.bib

# Check file encoding
file references.bib
```

#### BibTeX returns "no journals found"

**Causes**:
- BibTeX entries missing journal fields
- Only conference proceedings or book chapters (no journals)
- Journal fields use non-standard names

**Solutions**:
- Ensure entries have `journal`, or `journaltitle`, fields
- Check that entry types are appropriate (article, inproceedings, etc.)
- Use `--verbose` to see which entries were processed

#### "Journal not found" for known legitimate journal

**Causes**:
- Journal too new to be indexed
- Spelling variations not recognized
- ISSN not provided or incorrect

**Solutions**:
- Check journal's official website for correct name/ISSN
- Try alternate name formats
- Verify journal is actually indexed in major databases

#### Low confidence scores for legitimate journals

**Causes**:
- Limited data availability
- New journal with little history
- Regional or specialized journal not well-covered

**Solutions**:
- Check journal's indexing status manually
- Consider institutional policies
- Use multiple assessment methods

#### Timeout errors

**Causes**:
- Network connectivity issues
- Backend service temporarily unavailable
- Timeout settings too aggressive

**Solutions**:
```bash
# Check connectivity
curl -I https://doaj.org
```

#### Cache issues

**Causes**:
- Corrupted cache files
- Outdated cached data
- Permission issues

**Solutions**:
```bash
# Clear cache
aletheia-probe clear-cache

# Update data
aletheia-probe sync
```

### Getting Help

1. **Check this documentation**: Especially troubleshooting sections
2. **Search GitHub issues**: Look for similar problems
3. **See Logfile**: in the directory `.aletheia-probe`
4. **Create GitHub issue**: Include error messages and context
5. **Community support**: Engage with user community

### Error Messages

**"Invalid ISSN format"**: Verify ISSN format (XXXX-XXXX)
**"Configuration error"**: Check YAML syntax in config file
**"Cache write error"**: Check disk space and permissions
**"API rate limit exceeded"**: Wait or reduce request frequency

### Custom Backends

Extend the tool with custom data sources by implementing the Backend interface. See the source code in `src/backends/` for implementation examples.

### Integration with Workflows

The tool can be integrated into:
- Manuscript submission systems
- Institutional repository workflows
- Grant application review processes
- Academic policy enforcement systems

See the examples in `examples/` directory for programmatic integration examples.
