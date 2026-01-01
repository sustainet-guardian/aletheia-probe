# Troubleshooting Guide

Common issues and solutions when using the Journal Assessment Tool.

## Table of Contents

1. [Installation Issues](#installation-issues)
2. [Command Line Problems](#command-line-problems)
3. [Assessment Issues](#assessment-issues)
4. [Configuration Problems](#configuration-problems)
5. [Performance Issues](#performance-issues)
6. [Data Source Problems](#data-source-problems)
7. [Error Messages](#error-messages)
8. [Getting Help](#getting-help)

## Installation Issues

### Python Version Compatibility

**Problem**: "Python 3.10 or higher required"

**Solution**:
```bash
# Check Python version
python --version
python3 --version

# Use Python 3.10+ specifically
python3.10 -m pip install aletheia-probe
```

### Package Installation Fails

**Problem**: pip install fails with permission errors

**Solutions**:
```bash
# Install for user only
pip install --user aletheia-probe

# Use virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install aletheia-probe
```

### Missing Dependencies

**Problem**: Import errors or missing modules

**Solution**:
```bash
# Reinstall with all dependencies
pip uninstall aletheia-probe
pip install aletheia-probe

# For development
pip install aletheia-probe[dev]
```

## Command Line Problems

### Command Not Found

**Problem**: `aletheia-probe: command not found`

**Causes and Solutions**:

1. **Not in PATH** (most common):
   ```bash
   # Find installation location
   python -m pip show aletheia-probe

   # Add to PATH or use full path
   ~/.local/bin/aletheia-probe "Journal Name"
   ```

2. **Virtual environment not activated**:
   ```bash
   source venv/bin/activate
   aletheia-probe "Journal Name"
   ```

3. **Installed for different Python version**:
   ```bash
   python3.9 -m aletheia_probe.cli "Journal Name"
   ```

### Permission Errors

**Problem**: Permission denied when running commands

**Solutions**:
```bash
# Check file permissions
ls -la ~/.local/bin/aletheia-probe

# Fix permissions
chmod +x ~/.local/bin/aletheia-probe

# Run with Python module syntax
python -m aletheia_probe.cli "Journal Name"
```

## Assessment Issues

### "Journal not found" for Known Legitimate Journals

**Common Causes**:

1. **Journal too new**: Recently launched journals may not be indexed yet
2. **Name variations**: Official name differs from common usage
3. **Missing ISSN**: Some journals require ISSN for accurate matching

**Solutions**:
```bash
# Try with ISSN
aletheia-probe journal "Journal Name (ISSN: 1234-5679)"

# Check official journal name
aletheia-probe journal "Official Journal Title"

# Use verbose mode for debugging
aletheia-probe journal --verbose "Journal Name"
```

### Low Confidence Scores

**Problem**: Legitimate journals getting low confidence scores

**Causes and Solutions**:

1. **Limited data availability**:
   - New journals have little historical data
   - Regional journals may be less covered
   - Specialized fields may have fewer data sources

2. **Configuration tuning**:
   ```yaml
   # Lower thresholds for specialized domains
   heuristics:
     confidence_threshold: 0.5
     unknown_threshold: 0.2
   ```

3. **Enable more backends**:
   ```yaml
   backends:
     doaj:
       enabled: true
     retraction_watch:
       enabled: true
     institutional_backend:  # Add institutional lists
       enabled: true
   ```

### Incorrect "Predatory" Assessments

**Problem**: Legitimate journals flagged as predatory

**Investigation Steps**:

1. **Check data sources**:
   ```bash
   aletheia-probe journal --verbose "Journal Name"
   # Look at which backends flagged the journal
   ```

2. **Verify journal legitimacy**:
   - Check journal's official website
   - Look up in Scopus/Web of Science
   - Review editorial board and policies

3. **Report false positives**:
   - Create GitHub issue with details
   - Include journal name, ISSN, and evidence of legitimacy

## Configuration Problems

### Configuration Not Loading

**Problem**: Default configuration used despite config file existing

**Debug Steps**:
```bash
# Check configuration loading
aletheia-probe config

# Check if backends are loaded properly
aletheia-probe status
```

**Common Issues**:
- YAML syntax errors (indentation, missing colons)
- File permissions preventing reading
- Configuration file in wrong location

### Backend Configuration Errors

**Problem**: Backend fails to initialize or work correctly

**Solutions**:

1. **Check backend status**:
   ```bash
   aletheia-probe status
   ```

2. **Test with verbose output**:
   ```bash
   aletheia-probe journal --verbose "Test Journal"
   ```

3. **Verify configuration**:
   ```yaml
   backends:
     doaj:
       enabled: true      # Must be boolean, not string
       timeout: 10        # Must be integer
       weight: 1.0        # Must be float
   ```

## Performance Issues

### Slow Response Times

**Problem**: Tool takes too long to respond

**Diagnosis**:
```bash
# Check with timing information and backend details
aletheia-probe journal --verbose "Journal Name"
# Look at response_time for each backend
```

**Solutions**:

1. **Adjust timeouts**:
   ```yaml
   backends:
     doaj:
       timeout: 5        # Reduce from default 10
     retraction_watch:
       timeout: 10       # Reduce from default 15
   ```

2. **Optimize cache settings**:
   ```yaml
   cache:
     cache_ttl_hours: 48  # Cache longer
     async_cache_writes: true
   ```

3. **Disable slow backends**:
   ```yaml
   backends:
     slow_backend:
       enabled: false
   ```

### High Memory Usage

**Problem**: Tool uses excessive memory

**Solutions**:
```yaml
cache:
  max_cache_size_mb: 50    # Reduce cache size
  compress_cache: true     # Enable compression
```

### Network Issues

**Problem**: Connection timeouts or failures

**Diagnosis**:
```bash
# Test connectivity to data sources
curl -I https://doaj.org/api/v1/
curl -I https://gitlab.com/

# Check proxy settings
echo $HTTP_PROXY
echo $HTTPS_PROXY
```

**Solutions**:
1. **Increase timeouts**:
   ```yaml
   backends:
     doaj:
       timeout: 30
   ```

2. **Configure proxy** (if needed):
   ```bash
   export HTTP_PROXY=http://proxy.company.com:8080
   export HTTPS_PROXY=http://proxy.company.com:8080
   ```

## Data Source Problems

### DOAJ API Issues

**Problem**: DOAJ backend fails or returns errors

**Solutions**:
1. **Check DOAJ status**: Visit [DOAJ website](https://doaj.org/)
2. **Verify API endpoint**:
   ```bash
   curl "https://doaj.org/api/v1/search/journals/title:test"
   ```
3. **Rate limiting**:
   ```yaml
   backends:
     doaj:
       rate_limit: 30  # Reduce request rate
   ```

### Retraction Watch Data Issues

**Problem**: Retraction Watch backend fails

**Common Causes**:
- GitLab repository not accessible
- Data files moved or updated
- Network connectivity to GitLab

**Solutions**:
1. **Update data**:
   ```bash
   aletheia-probe sync
   ```
2. **Check data location**:
   ```bash
   aletheia-probe cache-info
   ```

### Stale Cache Data

**Problem**: Outdated assessment results

**Solutions**:
```bash
# Clear cache completely
aletheia-probe clear-cache

# Force refresh for specific query
aletheia-probe --no-cache "Journal Name"

# Update backend data
aletheia-probe sync
```

## Error Messages

### Common Error Messages and Solutions

#### "Configuration validation failed"

**Error**: YAML configuration syntax problems

**Solution**:
```bash
# Validate YAML syntax
python -c "import yaml; yaml.safe_load(open('config.yaml'))"

# Use YAML linter
yamllint config.yaml
```

#### "Backend timeout"

**Error**: Backend didn't respond within timeout

**Solutions**:
- Increase timeout in configuration
- Check internet connectivity
- Try with single backend: `--backend backend_name`

#### "Invalid ISSN format"

**Error**: ISSN not in correct format

**Solution**:
```bash
# Correct ISSN format: XXXX-XXXX
aletheia-probe "Journal (ISSN: 1234-5679)"

# Not: 12345678 or 1234-567X (wrong format)
```

#### "Cache write error"

**Error**: Cannot write to cache directory

**Solutions**:
```bash
# Check disk space
df -h

# Check permissions
ls -la ~/.cache/aletheia-probe/

# Clear cache if corrupted
aletheia-probe clear-cache
```

#### "API rate limit exceeded"

**Error**: Too many requests to external APIs

**Solutions**:
```bash
# Wait and retry
sleep 60 && aletheia-probe "Journal Name"

# Reduce rate limit in config
# backends -> backend_name -> rate_limit: 30
```

## Getting Help

### Before Asking for Help

1. **Check this troubleshooting guide**
2. **Search existing GitHub issues**
3. **Try with `--verbose` flag for more details**
4. **Test with minimal configuration**

### Gathering Debug Information

When reporting issues, include:

```bash
# Tool version
aletheia-probe --version

# Python version
python --version

# Operating system
uname -a  # Linux/macOS
systeminfo  # Windows

# Verbose output
aletheia-probe --verbose "Problematic Journal Name"

# Configuration (remove sensitive data)
aletheia-probe config --show
```

### Where to Get Help

1. **GitHub Issues**: [Report bugs and request features](https://github.com/sustainet-guardian/aletheia-probe/issues)
2. **Documentation**: Review [User Guide](user-guide.md) and [Configuration Reference](configuration.md)
3. **Community**: Engage with other users in discussions

### Creating Effective Bug Reports

Include in your bug report:

1. **Clear description** of the problem
2. **Steps to reproduce** the issue
3. **Expected behavior** vs actual behavior
4. **Debug information** (version, OS, verbose output)
5. **Configuration** (sanitized)
6. **Error messages** (complete text)

### Example Bug Report Template

```
**Description**
Brief description of the issue

**Steps to Reproduce**
1. Run command: aletheia-probe "Journal Name"
2. See error...

**Expected Behavior**
Should return assessment result

**Actual Behavior**
Returns error: "..."

**Environment**
- Tool version: 0.1.0
- Python version: 3.9.7
- OS: Ubuntu 22.04

**Configuration**
```yaml
backends:
  doaj:
    enabled: true
```

**Additional Context**
Any other relevant information
```

## Frequently Asked Questions

### Q: Why does the tool give different results for the same journal?

**A**: Results can change due to:
- Updated data sources
- Cache expiration
- Configuration changes
- New information becoming available

### Q: How accurate are the assessments?

**A**: Accuracy depends on:
- Quality of data sources
- Completeness of journal information
- Currency of backend data
- Appropriateness of configuration for your domain

### Q: Can I trust "insufficient_data" results?

**A**: "Insufficient_data" means the tool couldn't find enough information to make a confident assessment. This doesn't mean the journal is problematic - it may be:
- Too new to be indexed
- From a specialized field with limited coverage
- Regional journal not well-represented in data sources

### Q: How often should I update the data?

**A**: Recommended update frequency:
- Weekly for active use
- Monthly for occasional use
- Before important decisions
- After tool updates

Use `aletheia-probe sync` to update backend data.

### Q: Can I use this tool for final publishing decisions?

**A**: This tool provides guidance but should not be the sole factor in publishing decisions. Consider:
- Your institution's policies
- Field-specific practices
- Journal's recent developments
- Editorial board and peer review practices

The tool is designed to assist, not replace, human judgment in academic publishing decisions.