# Release Process Documentation

Quick reference for creating releases, with detailed setup instructions in appendices.

## Quick Start: Creating a Release

For experienced maintainers (first-time setup required - see Appendix A):

### 1. Prepare Release (5 minutes)

```bash
# Update version
python scripts/bump_version.py minor  # or: patch, major, or 1.0.0

# Update CHANGELOG
vim docs/CHANGELOG.md
git add docs/CHANGELOG.md
git commit -m "Update CHANGELOG for $(grep version pyproject.toml | cut -d'"' -f2)"

# Push and wait for CI
git push origin main
```

### 2. Create and Push Tag (1 minute)

```bash
# After CI passes, create and push tag
VERSION=$(grep 'version = ' pyproject.toml | cut -d'"' -f2)
git tag -a v$VERSION -m "Release version $VERSION"
git push origin v$VERSION
```

This automatically triggers the release pipeline which will:
- Run all tests and validations
- Publish to PyPI (after manual approval)
- Create GitHub Release with packages attached

### 3. Approve & Verify (10 minutes)

- Wait for CI checks (~10 min)
- Approve deployment when notified (production environment)
- CI automatically creates GitHub Release
- Verify: `pip install aletheia-probe==$VERSION`
- Check release: https://github.com/sustainet-guardian/aletheia-probe/releases

---

## Table of Contents

- [Quick Start: Creating a Release](#quick-start-creating-a-release)
- [Automated CI/CD Overview](#automated-cicd-overview)
- [Versioning Strategy](#versioning-strategy)
- [Troubleshooting](#troubleshooting)
- [Appendix A: Initial Setup](#appendix-a-initial-setup)
- [Appendix B: Manual Testing](#appendix-b-manual-testing)
- [Appendix C: Security Best Practices](#appendix-c-security-best-practices)

---

## Automated CI/CD Overview

The release pipeline includes automated safety checks:

**Every push to `main`:**
- ✅ Full test suite (lint, type-check, unit tests, integration tests)
- ✅ Build package and validate with `twine check`
- ✅ Publish to TestPyPI for validation
- ✅ Test installation from TestPyPI

**GitHub Release (tagged):**
- ✅ All above checks
- ✅ Validate version format (PEP 440)
- ✅ Verify version matches git tag
- ✅ Check version doesn't exist on PyPI
- ✅ Validate package metadata
- ⏸️ **Manual approval required** (production environment)
- ✅ Publish to PyPI
- ✅ Verify publication succeeded

## Versioning Strategy

We follow [Semantic Versioning 2.0.0](https://semver.org/):

- **MAJOR** (X.0.0): Breaking changes, incompatible API changes
- **MINOR** (0.X.0): New features, backwards compatible
- **PATCH** (0.0.X): Bug fixes, backwards compatible

### Using the Version Bump Script

```bash
python scripts/bump_version.py patch    # 0.1.0 -> 0.1.1
python scripts/bump_version.py minor    # 0.1.0 -> 0.2.0
python scripts/bump_version.py major    # 0.1.0 -> 1.0.0
python scripts/bump_version.py 1.0.0    # Set specific version

# With options
python scripts/bump_version.py minor --tag     # Also create git tag
python scripts/bump_version.py 1.0.0 --no-git  # Only update file
```

The script automatically:
- Updates `pyproject.toml`
- Creates a git commit
- Optionally creates a git tag
- Validates version format

---

## Troubleshooting

### Version Already Exists on PyPI

**Symptom:** CI fails with "Version X.Y.Z already exists on PyPI"

**Solution:**
```bash
# Bump to next version
python scripts/bump_version.py patch
git push origin main
```

### Version Mismatch Between Tag and pyproject.toml

**Symptom:** CI fails with "Version mismatch" error

**Solution:**
```bash
# Delete incorrect tag
git tag -d vX.Y.Z
git push origin :refs/tags/vX.Y.Z

# Fix version and recreate tag
python scripts/bump_version.py X.Y.Z --tag
git push origin main v$VERSION
```

### Manual Approval Not Received

**Symptom:** Deployment stuck waiting for approval

**Solution:**
- Check GitHub Actions page for approval button
- Ensure reviewers are configured in production environment
- Re-run workflow if needed

### Build Fails Locally

**Symptom:** `python -m build` fails with errors

**Solution:**
```bash
# Install build dependencies
pip install -e .[release]

# Clean previous builds
rm -rf dist/ build/ *.egg-info

# Try again
python -m build
```

---

## Appendix A: Initial Setup

This section is for first-time setup by repository administrators.

### Prerequisites

- Maintainer access to the GitHub repository
- PyPI account with 2FA enabled
- TestPyPI account (separate from PyPI)

### A.1: Create PyPI Accounts

1. **PyPI**: https://pypi.org/account/register/
   - Enable 2FA (required)
   - Verify email address

2. **TestPyPI**: https://test.pypi.org/account/register/
   - Separate account from PyPI
   - Enable 2FA (required)

### A.2: Generate PyPI API Tokens

#### For Production PyPI:

1. Log in to https://pypi.org/
2. Go to Account Settings → API tokens
3. Click "Add API token"
4. Token name: `aletheia-probe-github-actions`
5. Scope: Select "Project: aletheia-probe" (after first manual upload) or "Entire account" (for initial setup)
6. Click "Add token"
7. **IMPORTANT**: Copy the token immediately (starts with `pypi-`)
8. You won't be able to see it again!

#### For TestPyPI:

1. Log in to https://test.pypi.org/
2. Go to Account Settings → API tokens
3. Click "Add API token"
4. Token name: `aletheia-probe-github-actions-test`
5. Scope: "Entire account" (TestPyPI doesn't have project-scoped tokens)
6. Click "Add token"
7. **IMPORTANT**: Copy the token immediately (starts with `pypi-`)

### A.3: Add Secrets to GitHub

1. Go to repository Settings → Secrets and variables → Actions
2. Click "New repository secret"
3. Add both secrets:
   - `PYPI_API_TOKEN` - Token from PyPI (starts with `pypi-`)
   - `TESTPYPI_API_TOKEN` - Token from TestPyPI (starts with `pypi-`)

### A.4: Configure GitHub Environments

#### Create Production Environment:

1. Go to: Settings → Environments
2. Click "New environment"
3. Name: `production`
4. Click "Configure environment"

Configure protection rules:
- ✅ **Required reviewers**: Add 1-2 maintainers who must approve releases
- ✅ **Wait timer**: Optional - add 5-10 minute delay for final checks
- ✅ **Deployment branches**: Only allow `main` branch

#### Create Test-PyPI Environment:

1. Click "New environment"
2. Name: `test-pypi`
3. Configure: Only allow `main` branch deployments

Initial setup is complete! The CI/CD pipeline will now automatically test and publish releases.

---

## Appendix B: Manual Testing

### B.1: Build and Test Package Locally

```bash
# Install build tools
pip install -e .[release]

# Build package
python -m build

# Validate package
twine check dist/*

# Test installation in clean environment
python -m venv test_env
source test_env/bin/activate
pip install dist/*.whl
aletheia-probe --help
deactivate
rm -rf test_env
```

### B.2: Test Installation from TestPyPI

```bash
# Create a test environment
python -m venv test_env
source test_env/bin/activate  # On Windows: test_env\Scripts\activate

# Install from TestPyPI
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ aletheia-probe

# Test the installation
aletheia-probe --help
aletheia-probe --version

# Cleanup
deactivate
rm -rf test_env
```

View TestPyPI uploads at: https://test.pypi.org/project/aletheia-probe/

---

## Appendix C: Security Best Practices

### Token Management

- ✅ Always use API tokens, never passwords
- ✅ Enable 2FA on PyPI and TestPyPI accounts
- ✅ Use project-scoped tokens when possible
- ✅ Rotate tokens annually
- ✅ Revoke tokens immediately if compromised

### Release Safety

- ✅ Always require manual approval for production
- ✅ Use protected branches (main)
- ✅ Require pull request reviews
- ✅ Run full test suite before release
- ✅ Test on TestPyPI first

### Audit Trail

All releases are tracked:
- Git tags in repository
- GitHub Releases with descriptions
- Environment deployment history
- PyPI release history

## Appendix D: Manual Release (Emergency)

If CI/CD is unavailable, you can release manually:

```bash
# Install tools
pip install build twine

# Build package
python -m build

# Check package
twine check dist/*

# Upload to TestPyPI (test first!)
twine upload --repository testpypi dist/*

# Upload to PyPI (production)
twine upload dist/*
```

**Note**: Manual releases bypass safety checks. Use only in emergencies.

## Additional Resources

- [Python Packaging Guide](https://packaging.python.org/)
- [PyPI Help](https://pypi.org/help/)
- [Semantic Versioning](https://semver.org/)
- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Twine Documentation](https://twine.readthedocs.io/)
