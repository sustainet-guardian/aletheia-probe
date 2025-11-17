# Scripts Directory

This directory contains utility scripts for development, testing, and analysis.

## Quality Assurance Scripts

### `run-quality-checks.sh`

Pre-commit quality checks script that runs all code quality checks executed in CI/CD.

**Usage:**
```bash
./scripts/run-quality-checks.sh
```

**What it does:**
1. **Ruff linting** - Checks code for style and common issues
2. **Ruff format check** - Verifies code formatting consistency
3. **Mypy type checking** - Validates type annotations with strict mode
4. **Pytest with coverage** - Runs all tests with coverage reporting

**When to use:**
- Before committing code changes
- Before creating a pull request
- To ensure your changes will pass CI/CD checks

**Exit codes:**
- `0` - All checks passed
- `1` - One or more checks failed

The script provides colored output showing the status of each check and a final summary.

### `validate_setup.sh`

Validates the development environment setup.

## Analysis Scripts

### `analyze_retraction_data.py`

Python script for analyzing retraction data patterns.

### `test_openalex_integration.py`

Integration testing script for OpenAlex API interactions.

## Notes

- All shell scripts are executable (`chmod +x`)
- Scripts should be run from the project root directory
- Python scripts require the development environment to be activated
