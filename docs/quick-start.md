# Quick Start

## Installation

### Prerequisites

The tool requires RAR extraction utilities to be installed for processing data sources:

**Debian/Ubuntu:**
```bash
sudo apt-get install unrar
```

**macOS:**
```bash
brew install unar
```

**Windows:**
```bash
# Using chocolatey
choco install unrar
```

Alternatively on Windows, you can install [7-Zip](https://www.7-zip.org/) if you don't have chocolatey

### Install Aletheia-Probe

```bash
pip install aletheia-probe
```

## Basic Usage

```bash
# Assess a single journal by name
aletheia-probe journal "Journal of Advanced Research"

# Include ISSN for more accurate matching
aletheia-probe journal "Nature (ISSN: 0028-0836)"

# Assess all journals in a BibTeX file
aletheia-probe bibtex references.bib

# Get detailed JSON output
aletheia-probe journal --format json --verbose "PLOS ONE"
```

## BibTeX File Assessment

The tool can assess entire bibliographies from BibTeX files, making it perfect for checking manuscript references or research databases:

```bash
# Basic BibTeX assessment
aletheia-probe bibtex my_references.bib

# JSON output for integration with other tools
aletheia-probe bibtex my_references.bib --format json
```

**Exit Codes**:
- **0**: No predatory journals found (safe to proceed)
- **1**: Predatory journals detected (action needed)

**Example BibTeX Output**:
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
```

**Integration with CI/CD**:
```bash
# In your build script
if aletheia-probe bibtex references.bib; then
    echo "✅ Bibliography is clean"
else
    echo "❌ Predatory journals found - please review"
    exit 1
fi
```

## Single Journal Example Output

```json
{
  "assessment": "legitimate",
  "confidence": 0.92,
  "sources": ["DOAJ", "Retraction Watch"],
  "reasoning": [
    "Found in DOAJ with verified publisher information",
    "Low retraction rate (0.1% over 5 years)"
  ]
}
```
