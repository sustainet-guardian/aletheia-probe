# Quick Start Guide

This guide provides complete installation and setup instructions for Aletheia-Probe across all supported platforms.

## System Requirements

Before installing Aletheia-Probe, ensure your system has the required dependencies:

### Core Requirements
- **Python 3.10 or higher** - Runtime environment
- **Git** - Required for retraction data synchronization

### Platform-Specific Installation Instructions

#### Windows

**1. Install Python:**
- Download from [python.org](https://www.python.org/downloads/)
- During installation, check "Add Python to PATH"
- Verify: `python --version` in Command Prompt/PowerShell

**2. Install Git for Windows:**
- Download from [git-scm.com](https://git-scm.com/downloads/win)
- During installation, select "Git from the command line and also from 3rd-party software"
- Verify: `git --version` in Command Prompt/PowerShell

**3. Common Windows Issues:**
- If git is not recognized, restart your terminal
- Check PATH: `echo %PATH%` (CMD) or `echo $env:PATH` (PowerShell)
- Corporate networks may require proxy configuration

#### macOS

**1. Install Python (if not already present):**
```bash
# Using Homebrew (recommended)
brew install python@3.10

# Or download from python.org
```

**2. Install Git (usually pre-installed):**
```bash
# Check if git is available
git --version

# If not installed, install via Homebrew
brew install git

# Or install Xcode Command Line Tools
xcode-select --install
```

#### Linux (Ubuntu/Debian)

**1. Install Python:**
```bash
# Ubuntu/Debian
sudo apt update
sudo apt install python3.10 python3.10-pip python3.10-venv

# Verify installation
python3 --version
```

**2. Install Git:**
```bash
# Ubuntu/Debian
sudo apt install git

# Fedora/RHEL
sudo dnf install git

# Arch Linux
sudo pacman -S git

# Verify installation
git --version
```

#### Linux (Other Distributions)

**Python Installation:**
- **Fedora/CentOS/RHEL:** `sudo dnf install python3.10 python3-pip`
- **Arch Linux:** `sudo pacman -S python python-pip`
- **openSUSE:** `sudo zypper install python310 python3-pip`

**Git Installation:**
- **Fedora/CentOS/RHEL:** `sudo dnf install git`
- **Arch Linux:** `sudo pacman -S git`
- **openSUSE:** `sudo zypper install git`

## Installation

### Option 1: Install from PyPI (Recommended)

```bash
pip install aletheia-probe
```

### Option 2: Install from Source (For Development)

```bash
git clone https://github.com/sustainet-guardian/aletheia-probe.git
cd aletheia-probe
pip install -e .
```

### Verify Installation

```bash
# Check if aletheia-probe is installed
aletheia-probe --help

# Verify system dependencies
aletheia-probe status
```

## First-Time Setup

### 1. Initialize Data Sources

Before using Aletheia-Probe, you must sync the assessment databases:

```bash
# Download and process data from all sources (5-10 minutes)
aletheia-probe sync
```

**What this does:**
- Downloads journal lists from DOAJ, Beall's List, and other sources
- Clones retraction data from GitLab repository (requires Git)
- Processes and caches data for fast lookups
- Creates local SQLite database (~100MB)

### 2. Check Installation Status

```bash
# Verify all backends are working
aletheia-probe status
```

**Expected output:**
```
Aletheia-Probe Status
=====================
Configuration: Active
Database: Connected (12 backends enabled)
Cache: 125,431 journals cached
Last sync: 2024-10-15 14:30:22

Backend Status:
✅ doaj: 22,184 journals
✅ bealls: 2,891 publishers
✅ retraction_watch: 8,539 journals
✅ algerian_ministry: 3,312 journals
...
```

## Basic Usage

### 1. Assess a Single Journal

```bash
# Basic journal assessment
aletheia-probe journal "Nature"

# Include ISSN for more accurate matching
aletheia-probe journal "Nature (ISSN: 0028-0836)"

# Get detailed JSON output
aletheia-probe journal --format json --verbose "PLOS ONE"
```

### 2. Assess BibTeX References

```bash
# Assess all journals in a BibTeX file
aletheia-probe bibtex references.bib

# JSON output for integration with other tools
aletheia-probe bibtex references.bib --format json
```

### 3. Check Cache Status

```bash
# Display current cache state and backend information
aletheia-probe status

# Force refresh of all data sources
aletheia-probe sync --force
```

## BibTeX File Assessment

The tool can assess entire bibliographies from BibTeX files, making it perfect for checking manuscript references or research databases:

```bash
# Basic BibTeX assessment
aletheia-probe bibtex my_references.bib

# JSON output for integration with other tools
aletheia-probe bibtex my_references.bib --format json
```

**Exit Codes:**
- **0**: No predatory journals found (safe to proceed)
- **1**: Predatory journals detected (action needed)

**Integration with CI/CD:**
```bash
# In your build script
if aletheia-probe bibtex references.bib; then
    echo "✅ Bibliography is clean"
else
    echo "❌ Predatory journals found - please review"
    exit 1
fi
```

## Next Steps

- **Advanced Usage:** See the [User Guide](user-guide.md) for detailed features
- **Research Applications:** Check [Research Applications Guide](research-applications.md) for systematic literature reviews
- **API Reference:** Explore [API Documentation](api-reference/) for custom integrations
- **Configuration:** Review [Configuration Reference](configuration.md) for advanced settings

**Need help?** Check the [Troubleshooting Guide](troubleshooting.md) or [open an issue](https://github.com/sustainet-guardian/aletheia-probe/issues).
