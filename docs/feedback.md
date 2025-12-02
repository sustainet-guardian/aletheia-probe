# Providing Feedback

Thank you for using Aletheia-Probe! Your feedback is invaluable in helping us improve the tool and ensure it meets the needs of the research community.

## Current Features

Aletheia-Probe provides comprehensive journal and conference assessment capabilities. The core functionality is stable and well-tested, but we continuously work to improve accuracy, performance, and usability based on user feedback.

## Tool Capabilities

### Core Features
- ✅ Comprehensive journal assessment functionality
- ✅ Conference assessment capabilities
- ✅ Multiple data source integration (DOAJ, Beall's List, Retraction Watch, OpenAlex, etc.)
- ✅ BibTeX file batch processing
- ✅ Multiple output formats (JSON, text, verbose)
- ✅ Flexible configuration management
- ✅ Automatic data source synchronization
- ✅ Extensive documentation and examples

### Current Limitations
- ⚠️ **First sync takes time**: Initial data download can take 5-10 minutes depending on your connection
- ⚠️ **Regional journals**: Journals from non-Western regions may have limited coverage in data sources
- ⚠️ **New journals**: Very recently launched journals (< 1 year) may return "insufficient_data"
- ⚠️ **Conference coverage**: Limited compared to journal assessment due to fewer comprehensive conference databases

## Areas Where We Value Your Feedback
1. **Installation experience** - Any issues or confusion during setup?
2. **Real-world usage** - Does it work with your actual reference files?
3. **Performance** - How long do assessments take for your use cases?
4. **Accuracy** - Do results match your expectations for journals you know?
5. **Documentation** - Is anything unclear or missing?
6. **Platform issues** - Any problems on your OS (Linux/macOS/Windows)?
7. **Error handling** - How does it behave with malformed inputs?

## Getting Started

For installation instructions and basic usage, please see:
- [Quick Start Guide](quick-start.md) - Installation and first steps
- [User Guide](user-guide.md) - Comprehensive usage examples

## Common Usage Scenarios

Here are typical use cases you might encounter. If you experience issues with any of these, please let us know:

### 1. Basic Single Journal Assessment

```bash
# Test with well-known legitimate journals
aletheia-probe journal "Nature"
aletheia-probe journal "Science"
aletheia-probe journal "PLOS ONE"

# Test with ISSN
aletheia-probe journal "Nature (ISSN: 0028-0836)"

# Test with verbose output
aletheia-probe journal --verbose "Journal of Advanced Research"

# Test JSON output
aletheia-probe journal --format json "Cell"
```

**What to check:**
- Does it correctly identify legitimate journals?
- Are confidence scores reasonable (typically > 0.7 for well-known journals)?
- Is the reasoning clear and understandable?

### 2. BibTeX File Processing

```bash
# Test with your own BibTeX files
aletheia-probe bibtex your_references.bib

# Test with verbose output
aletheia-probe bibtex your_references.bib --verbose

# Test JSON output
aletheia-probe bibtex your_references.bib --format json
```

**What to check:**
- Does it parse your BibTeX file correctly?
- Are journals extracted properly from different entry types?
- How long does processing take for files with 10, 50, 100+ entries?
- Does it handle malformed BibTeX entries gracefully?

### 3. Configuration

```bash
# View current configuration
aletheia-probe config

# Check backend status
aletheia-probe status
```

**What to check:**
- Is the configuration output clear?
- Are all expected backends listed?
- Does status show data properly synced?

### 4. Edge Cases

```bash
# Test with variations
aletheia-probe journal "journal of advanced research"  # lowercase
aletheia-probe journal "Journal of Advanced Research (JAR)"  # with abbreviation
aletheia-probe journal "ISSN: 2090-1232"  # ISSN only
aletheia-probe journal ""  # empty string
aletheia-probe journal "XYZ123NotAJournal"  # nonsense input

# Test with special characters
aletheia-probe journal "Café Scientifique Journal"
aletheia-probe journal "Журнал (Russian characters)"
```

**What to check:**
- Does it handle different input formats gracefully?
- Are error messages helpful?
- Does it crash or handle errors properly?

### 5. Performance Testing

```bash
# Time a simple assessment
time aletheia-probe journal "Nature"

# Time a BibTeX file with many entries
time aletheia-probe bibtex large_references.bib
```

**What to check:**
- Is response time acceptable (< 5 seconds for single journal after sync)?
- Does performance degrade with large BibTeX files?
- Does caching improve subsequent queries?

## Reporting Issues

### Before Reporting
1. Check the [Troubleshooting Guide](troubleshooting.md)
2. Search [existing issues](https://github.com/sustainet-guardian/aletheia-probe/issues)
3. Try with `--verbose` flag for more details
4. Ensure you're using the latest version

### How to Report

Create a new issue on GitHub with:

**Required Information:**
```
**Issue Summary**
Brief description of the problem

**Steps to Reproduce**
1. Command run: `aletheia-probe journal ...` or `aletheia-probe bibtex ...`
2. Input used: ...
3. Expected result: ...
4. Actual result: ...

**Environment**
- Tool version: `aletheia-probe --version`
- Python version: `python --version`
- Operating System: [e.g., Ubuntu 22.04, macOS 14, Windows 11]
- Installation method: [git clone, ...]

**Verbose Output** (if applicable)
```
Paste output from command with --verbose flag
```

**Additional Context**
Any other relevant information
```

### Issue Labels

When creating issues, please suggest appropriate labels:
- `bug` - Something isn't working correctly
- `enhancement` - Suggestion for improvement
- `documentation` - Documentation issues or improvements
- `question` - Questions about usage or behavior
- `performance` - Performance-related issues
- `feedback` - General user feedback

## Expected Behavior vs. Bugs

### Expected Behavior (Not Bugs)
- **"insufficient_data" results** - For new, regional, or specialized journals with limited coverage
- **Different results over time** - As data sources update
- **Low confidence for niche journals** - Specialized field journals may not be well-represented in data sources
- **Sync takes several minutes** - First-time data download from multiple sources

### Actual Bugs to Report
- **Crashes or unhandled exceptions** - Tool exits unexpectedly
- **Incorrect assessments** - Well-known journals misclassified
- **Cannot complete sync** - Sync fails repeatedly
- **Parsing errors** - Valid BibTeX files rejected
- **Installation failures** - Cannot install on supported Python versions
- **Platform-specific issues** - Works on one OS but not another

## Providing Feedback

Beyond bug reports, we welcome general feedback on:

1. **User Experience**
   - Is the tool intuitive to use?
   - Are command-line options clear?
   - Is output formatting helpful?

2. **Documentation**
   - What documentation is missing or unclear?
   - What examples would be helpful?
   - Are error messages understandable?

3. **Features**
   - What features would be most useful to add?
   - What workflows need better support?
   - What data sources should be added?

4. **Use Cases**
   - How are you using the tool?
   - What works well for your workflow?
   - What's missing for your needs?

Please share feedback by:
- Creating a GitHub issue with the `feedback` label
- Discussing in GitHub Discussions (if enabled)
- Emailing maintainers (check CONTRIBUTING.md for contacts)

## Feedback Checklist

Use this checklist to help provide comprehensive feedback:

**Installation & Setup**
- [ ] Installation process was straightforward
- [ ] `aletheia-probe --version` shows expected version
- [ ] First `sync` completed without errors
- [ ] `aletheia-probe status` shows data properly synced

**Basic Functionality**
- [ ] Assess a well-known journal with `journal` command (e.g., "Nature")
- [ ] Assess with ISSN
- [ ] Assess with `--verbose` flag
- [ ] Assess with `--format json`
- [ ] Results make sense and have reasonable confidence scores

**BibTeX Processing**
- [ ] Process a small BibTeX file (< 10 entries)
- [ ] Process a larger BibTeX file (50+ entries)
- [ ] Try with `--verbose` flag
- [ ] Check exit codes (should be 1 if predatory journals found)

**Error Handling**
- [ ] Try with empty input
- [ ] Try with nonsense input
- [ ] Try with malformed BibTeX file
- [ ] Error messages are helpful

**Platform-Specific** (if applicable)
- [ ] Tested on Linux
- [ ] Tested on macOS
- [ ] Tested on Windows
- [ ] No platform-specific issues found

**Documentation**
- [ ] README is clear and accurate
- [ ] Quick Start guide works as written
- [ ] Troubleshooting guide helped resolve issues
- [ ] No major gaps in documentation

## Thank You!

Your feedback helps ensure Aletheia-Probe remains reliable, accurate, and useful for the research community. We greatly appreciate your time and input in making this tool better for everyone!

## Questions?

- Check the [User Guide](user-guide.md)
- Review [Troubleshooting](troubleshooting.md)
- Create an issue with the `question` label
- See [CONTRIBUTING.md](../.github/community/CONTRIBUTING.md) for development questions
