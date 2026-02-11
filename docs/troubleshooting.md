# Troubleshooting Guide

Common issues and solutions when using Aletheia-Probe.

## Installation Issues

### Python Version Compatibility

**Problem**: "Python 3.10 or higher required"

**Solution**:
```bash
# Check Python version
python --version

# Use Python 3.10+ specifically if needed
python3.10 -m pip install aletheia-probe
```

### Package Installation Fails

**Problem**: pip install fails with permission errors

**Solutions**:
```bash
# Install for user only
pip install --user aletheia-probe

# Use virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install aletheia-probe
```

## Command Line Problems

### Command Not Found

**Problem**: `aletheia-probe: command not found`

**Most Common Solution**:
```bash
# Install added to PATH automatically, but if not working:
python -m pip show aletheia-probe  # Find install location
~/.local/bin/aletheia-probe "Journal Name"  # Use full path

# Or use module syntax:
python -m aletheia_probe.cli "Journal Name"
```

**If using virtual environment**:
```bash
source venv/bin/activate
aletheia-probe "Journal Name"
```

## Data Sync Issues

### "retraction_watch: Failed to clone repository"

<!-- Documented in GitHub issue #1015 - actual user report -->

**Root Cause**: Missing Git system dependency (especially on Windows)

**Solution**: Install Git for your platform:
- **Windows**: Download from [git-scm.com](https://git-scm.com/downloads/win)
- **macOS**: `brew install git` or install Xcode Command Line Tools
- **Linux**: `sudo apt install git` (Ubuntu) or equivalent for your distribution

See [Quick Start Guide](quick-start.md#system-requirements) for detailed installation instructions.

**Verify installation**:
```bash
git --version
```

### "No data received from source"

**Solutions**:
```bash
# Force refresh all data sources
aletheia-probe sync --force

# Check network connectivity
curl -I https://doaj.org
curl -I https://gitlab.com

# Check backend status
aletheia-probe status
```

### Sync Takes Too Long or Fails

**Solutions**:
```bash
# Sync only essential backends first
aletheia-probe sync doaj bealls retraction_watch

# Check status to see which backends failed
aletheia-probe status

# Clear cache and retry if corrupted
aletheia-probe clear-cache
aletheia-probe sync
```

## Assessment Issues

### "Journal not found" for Known Journals

**Solutions**:
```bash
# Try with ISSN for better matching
aletheia-probe journal "Journal Name (ISSN: 1234-5679)"

# Use verbose mode to see what's happening
aletheia-probe journal --verbose "Journal Name"

# Check if data needs updating
aletheia-probe sync
```

### Outdated Results

**Solutions**:
```bash
# Clear cache and get fresh results
aletheia-probe clear-cache

# Update backend data
aletheia-probe sync

# Force fresh lookup for specific query
aletheia-probe --no-cache "Journal Name"
```

## Common Error Messages

### "Backend timeout"

**Solutions**:
- Check internet connectivity
- Try again (temporary network issue)
- Use `aletheia-probe status` to identify problematic backend

### "Cache write error"

**Solutions**:
```bash
# Check disk space
df -h

# Check cache directory permissions
ls -la ~/.cache/aletheia-probe/

# Clear corrupted cache
aletheia-probe clear-cache
```

### "Invalid ISSN format"

**Solution**: Use correct ISSN format with hyphen:
```bash
aletheia-probe "Journal (ISSN: 1234-5679)"  # Correct
# Not: 12345679 or 1234-567X
```

## Getting Help

### Check Log Files First

**Most important troubleshooting step**: Check the log file from your last command execution.

Aletheia-Probe creates a `.aletheia-probe/` directory in the current working directory where you run the command. The log file contains detailed information about what happened during the last command:

```bash
# View the most recent log file (in current directory)
cat .aletheia-probe/aletheia-probe.log

# On Windows
type .aletheia-probe\aletheia-probe.log

# View last 50 lines if file is large
tail -50 .aletheia-probe/aletheia-probe.log
```

**The log file shows:**
- Detailed backend execution steps
- Network connection attempts
- Error messages with full context
- File paths and system operations
- Timing information for each step

### Before Reporting Issues

1. **Check the log file**: `~/.aletheia-probe/aletheia-probe.log`
2. **Try verbose mode**: `aletheia-probe --verbose "Journal Name"`
3. **Check status**: `aletheia-probe status`
4. **Search existing issues**: [GitHub Issues](https://github.com/sustainet-guardian/aletheia-probe/issues)
5. **Update data**: `aletheia-probe sync`

### Reporting Bugs

Include this information:
```bash
# Tool and system info
aletheia-probe --version
python --version
uname -a  # Linux/macOS or systeminfo on Windows

# Most recent log file (very important!)
cat .aletheia-probe/aletheia-probe.log

# Reproduce issue with verbose output
aletheia-probe --verbose "Problematic Journal Name"

# Backend status
aletheia-probe status
```

**Attach the log file** (`.aletheia-probe/aletheia-probe.log` in your current directory) to your GitHub issue - it contains crucial debugging information.

### Where to Get Help

- **GitHub Issues**: [Report bugs and request features](https://github.com/sustainet-guardian/aletheia-probe/issues)
- **Documentation**: [User Guide](user-guide.md) and [Quick Start](quick-start.md)

## Frequently Asked Questions

### Q: How often should I sync data?

**A**:
- Weekly for active use
- Monthly for occasional use
- Before important decisions
- Use `aletheia-probe sync` to update

### Q: What does "insufficient_data" mean?

**A**: The tool couldn't find enough information to make a confident assessment. This doesn't mean the journal is problematic - it may be too new, specialized, or regional.

### Q: Can I trust the assessments for final publishing decisions?

**A**: This tool provides guidance but should supplement, not replace, your judgment. Consider your institution's policies, field-specific practices, and recent journal developments.