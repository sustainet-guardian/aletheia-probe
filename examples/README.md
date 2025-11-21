# Aletheia Probe Python API Examples

This directory contains standalone Python scripts demonstrating how to use the Aletheia Probe Python API for journal assessment.

## Setup Requirements

Before running the examples, ensure you have:

1. **Installed Aletheia Probe:**
   ```bash
   pip install aletheia-probe
   ```

2. **Synced backend data:**
   ```bash
   aletheia-probe sync
   ```
   This downloads the predatory journal lists and other data sources needed for assessment.

3. **(Optional) View configuration:**
   ```bash
   aletheia-probe config
   ```
   This displays the current configuration. The tool works with default settings, but you can customize backends and other options.

## Examples

### basic_assessment.py

Demonstrates core journal assessment functionality:

- **Single journal assessment** - Assess one journal with detailed results
- **Batch assessment** - Process multiple journals efficiently
- **Result interpretation** - How to work with assessment results

**Usage:**
```bash
python basic_assessment.py
```

**Expected Output (similar to):**
```
=== Single Journal Assessment ===
Journal: Nature Communications
Assessment: legitimate
Confidence: 98%
Backend Results: 13 sources checked

=== Batch Assessment ===
Science: legitimate (98% confidence)
PLOS ONE: legitimate (100% confidence)
Journal of Biomedicine: legitimate (83% confidence)
```

*Note: Results may vary based on enabled backends and available data.*

### bibtex_processing.py

Shows how to process BibTeX bibliography files:

- **BibTeX file parsing** - Extract journals from bibliography files
- **Batch journal assessment** - Assess all journals in a bibliography
- **Result aggregation** - Summarize findings and generate reports

**Usage:**
```bash
python bibtex_processing.py
```

**Expected Output (similar to):**
```
=== BibTeX File Processing ===
Created sample BibTeX file: /tmp/tmplbecdqnw.bib

=== Assessment Summary ===
Total entries processed: 3
Legitimate journals: 2
Predatory journals: 1
Insufficient data: 0

=== Detailed Results ===
Journal: Nature Communications
  Assessment: legitimate
  Confidence: 93%
  Risk Level: LOW - Safe to publish
```

*Note: Results may vary based on enabled backends and available data.*

## Integration Tips

### Error Handling

Always wrap API calls in try-catch blocks:

```python
try:
    result = await query_dispatcher.assess_journal(query)
    # Process result...
except Exception as e:
    print(f"Assessment failed: {e}")
```

### Configuration

The API uses configuration in this order of precedence:
1. Local `.aletheia-probe/` directory (project-specific settings)
2. User configuration directory (`~/.config/aletheia-probe/` or platform equivalent)
3. Default settings

For more details, see the [Configuration documentation](https://github.com/sustainet-guardian/aletheia-probe#configuration).

### Async/Await

All assessment functions are asynchronous. Use within async functions or with `asyncio.run()`:

```python
import asyncio

async def main():
    result = await query_dispatcher.assess_journal(query)
    return result

# Run the async function
result = asyncio.run(main())
```