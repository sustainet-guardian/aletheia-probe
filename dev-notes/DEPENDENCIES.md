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

The following system-level tools are generally pre-installed but listed for completeness:
- **git** - Version control (pre-installed on GitHub Actions runners, usually available on most systems)
- **curl** - HTTP requests (pre-installed on most systems)

## Installation Notes

1. **PDF Processing**: PDFs may contain text in multiple languages (Arabic, French, English)
2. **SSL Certificates**: Some data sources may require `--insecure` flags for development environments
3. **Memory Usage**: Large PDF files may require increased memory limits for processing
