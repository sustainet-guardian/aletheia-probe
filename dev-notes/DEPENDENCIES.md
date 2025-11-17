# Dependencies Documentation

## Python Dependencies

All Python package dependencies are defined in **[pyproject.toml](../pyproject.toml)**.

To install:
```bash
# Install package with runtime dependencies
pip install -e .

# Install package with development dependencies
pip install -e .[dev]
```

**Python Version Requirement:** 3.10 or higher

## System Dependencies

The following system-level tools are required for full functionality:

### RAR Archive Support (Required for Algerian Ministry Data Source)

The Algerian Ministry of Higher Education provides predatory journal lists as RAR archives containing PDF files. You need a RAR extraction tool installed.

#### Ubuntu/Debian
```bash
sudo apt-get update
sudo apt-get install -y unrar git curl
```

Alternative if `unrar` is not available:
```bash
sudo apt-get install -y unrar-free
```

#### RHEL/CentOS/Fedora
```bash
# Enable EPEL repository first (RHEL/CentOS only)
sudo yum install -y epel-release

# Install unrar
sudo yum install -y unrar git curl
```

#### macOS
```bash
# Using Homebrew - try unar first (open-source)
brew install unar

# Alternative: unrar
brew install unrar
```

Note: macOS may use either `unar` or `unrar` for RAR support.

#### Windows
Using Chocolatey (recommended):
```powershell
# Install chocolatey package manager first if not available
# See: https://chocolatey.org/install

# Install unrar
choco install unrar -y

# Alternative: 7-Zip (also supports RAR)
choco install 7zip -y
```

**Windows-specific configuration:**
- Ensure UTF-8 encoding is enabled for proper text handling
- Set environment variables: `PYTHONIOENCODING=utf-8` and `PYTHONUTF8=1`
- Console code page should be set to UTF-8 (65001)

### Additional System Tools

The following tools are generally pre-installed but listed for completeness:
- **git** - Version control (pre-installed on GitHub Actions runners, usually available on most systems)
- **curl** - HTTP requests (pre-installed on most systems)

### Verification

To verify that RAR extraction is working:

**Linux/macOS:**
```bash
# Test Python rarfile library
python3 -c "import rarfile; print('RAR support available')"

# Test command line tool
unrar --help
# or on macOS
unar --help
```

**Windows (PowerShell):**
```powershell
# Test Python rarfile library
python -c "import rarfile; print('RAR support available')"

# Test command line tool
unrar --help
# or
7z --help
```

## Installation Notes

1. **RAR Support**: The `rarfile` Python library requires a system-level unrar tool to function properly
2. **PDF Processing**: PDFs may contain text in multiple languages (Arabic, French, English)
3. **SSL Certificates**: Some data sources may require `--insecure` flags for development environments
4. **Memory Usage**: Large PDF files may require increased memory limits for processing
