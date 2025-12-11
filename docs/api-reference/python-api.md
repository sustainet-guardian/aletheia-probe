# Python API Reference

This document describes the high-level public API for programmatic journal assessment.

## Single Journal Assessment

**Function**: `query_dispatcher.assess_journal(query_input)`

Assesses a single journal or conference by querying multiple data sources and returning a consolidated classification.

**Usage**:
```python
import asyncio
from aletheia_probe import query_dispatcher
from aletheia_probe.normalizer import input_normalizer

async def assess():
    # Normalize the journal name
    query = input_normalizer.normalize("Nature Communications")

    # Get assessment
    result = await query_dispatcher.assess_journal(query)

    # Use results
    print(f"Classification: {result.assessment}")
    print(f"Confidence: {result.confidence:.0%}")

    return result

asyncio.run(assess())
```

**Result object** contains:
- `assessment`: Classification (predatory, legitimate, suspicious, unknown)
- `confidence`: Confidence score (0.0 to 1.0)
- `reasoning`: List of explanation strings
- `backend_results`: Details from each data source queried

---

## BibTeX File Assessment

**Function**: `BibtexBatchAssessor.assess_bibtex_file(file_path, verbose=False)`

Processes an entire BibTeX file and assesses all journals and conferences referenced.

**Usage**:
```python
import asyncio
from pathlib import Path
from aletheia_probe import BibtexBatchAssessor

async def assess_bibliography():
    result = await BibtexBatchAssessor.assess_bibtex_file(
        Path("references.bib"),
        verbose=True
    )

    # Get statistics
    print(f"Total venues: {result.entries_with_journals}")
    print(f"Predatory: {result.predatory_count}")
    print(f"Retracted articles: {result.retracted_articles_count}")

    # Format summary
    summary = BibtexBatchAssessor.format_summary(result)
    print(summary)

    return result

asyncio.run(assess_bibliography())
```

**Result object** contains:
- `entries_with_journals`: Number of venues assessed
- `predatory_count`, `legitimate_count`, `suspicious_count`: Classification counts
- `retracted_articles_count`: Articles found to be retracted
- `assessment_results`: List of (entry, assessment) tuples for detailed processing

---

## Notes

- Both functions are asynchronous and require `await` or `asyncio.run()`
- Input normalization handles abbreviations, special characters, and acronyms
- Results include detailed reasoning for transparency
- BibTeX assessor automatically detects and skips preprints (arXiv, bioRxiv, etc.)
