# Aletheia Probe Python API Examples

This directory contains standalone Python scripts demonstrating how to use the Aletheia Probe Python API for journal assessment.

## Setup Requirements

Before running the examples, ensure you have:

1. **Installed Aletheia Probe:**
   ```bash
   pip install aletheia-probe
   ```

2. **Configured the tool:**
   ```bash
   aletheia-probe config
   ```
   Follow the prompts to set up your data sources and preferences.

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

**Expected Output:**
```
=== Single Journal Assessment ===
Journal: Nature Communications
Assessment: legitimate
Confidence: 95%
Backend Results: 3 sources checked

=== Batch Assessment ===
Science: legitimate (98% confidence)
PLOS ONE: legitimate (92% confidence)
Journal of Biomedicine: predatory (87% confidence)
```

### bibtex_processing.py

Shows how to process BibTeX bibliography files:

- **BibTeX file parsing** - Extract journals from bibliography files
- **Batch journal assessment** - Assess all journals in a bibliography
- **Result aggregation** - Summarize findings and generate reports

**Usage:**
```bash
python bibtex_processing.py
```

**Expected Output:**
```
=== BibTeX File Processing ===
Created sample BibTeX file: /tmp/sample.bib

=== Assessment Summary ===
Total entries processed: 3
Legitimate journals: 2
Predatory journals: 1
Unknown/unclear: 0

=== Detailed Results ===
Journal: Nature Communications
  Assessment: legitimate
  Confidence: 95%
  Risk Level: LOW - Safe to publish
```

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

The API uses your configured settings from `aletheia-probe config`. For programmatic configuration:

```python
from aletheia_probe.config_manager import get_config_manager

config_manager = get_config_manager()
config = config_manager.load_config()
# Access configuration settings...
```

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

## Support

For questions or issues:
- Check the main documentation
- Review the source code examples in the docstrings
- Report bugs via the project issue tracker