# Logging Usage Guide

This project uses a dual-logger system to separate verbose technical logging from user-facing status messages.

## Logger Types

### 1. Detail Logger (`journal_assessment.detail`)
- **Purpose**: Verbose technical logging for debugging and troubleshooting
- **Output**: Log file only
- **Level**: DEBUG and above
- **Use for**:
  - Debug information
  - API calls and responses
  - Data processing details
  - Internal state changes
  - Technical diagnostics

### 2. Status Logger (`journal_assessment.status`)
- **Purpose**: User-facing progress and status information
- **Output**: Console (stderr) AND log file
- **Level**: INFO and above
- **Use for**:
  - Progress updates
  - Status messages
  - User-facing warnings
  - Error messages
  - Summary information

## Usage Examples

### Basic Usage

```python
from aletheia_probe.logging_config import get_detail_logger, get_status_logger

# Get logger instances
detail_logger = get_detail_logger()
status_logger = get_status_logger()

# Detail logging (file only)
detail_logger.debug("Processing data from API")
detail_logger.info("Normalized journal name: IEEE Transactions")

# Status logging (console + file)
status_logger.info("Processing 10 journals...")
status_logger.warning("Journal not found in database")
status_logger.error("Failed to connect to remote service")
```

### In a Module

```python
"""Example module showing logging usage."""

from .logging_config import get_detail_logger, get_status_logger


class DataProcessor:
    """Example class using dual logging."""

    def __init__(self):
        self.detail_logger = get_detail_logger()
        self.status_logger = get_status_logger()

    def process_items(self, items):
        """Process a list of items with progress updates."""
        self.status_logger.info(f"Processing {len(items)} items...")
        self.detail_logger.debug(f"Items: {items}")

        for i, item in enumerate(items, 1):
            self.detail_logger.debug(f"Processing item {i}: {item}")

            try:
                result = self._process_single_item(item)
                self.detail_logger.debug(f"Result: {result}")

                # Show progress every 10 items
                if i % 10 == 0:
                    self.status_logger.info(f"Progress: {i}/{len(items)} items processed")

            except Exception as e:
                self.status_logger.error(f"Failed to process item {item}: {e}")
                self.detail_logger.exception(f"Detailed error for {item}")

        self.status_logger.info(f"Completed processing {len(items)} items")
```

### Async Functions

```python
async def assess_journal(journal_name: str):
    """Example async function using logging."""
    detail_logger = get_detail_logger()
    status_logger = get_status_logger()

    status_logger.info(f"Assessing journal: {journal_name}")
    detail_logger.debug(f"Starting assessment for: {journal_name}")

    try:
        # Perform assessment
        result = await perform_assessment(journal_name)
        detail_logger.debug(f"Raw assessment result: {result}")

        status_logger.info(f"Assessment complete: {result.classification}")
        return result

    except Exception as e:
        status_logger.error(f"Assessment failed: {e}")
        detail_logger.exception("Detailed error information")
        raise
```

## Best Practices

1. **Use detail logger for technical details**: API responses, data transformations, intermediate values
2. **Use status logger for user communication**: Progress, warnings, errors they should know about
3. **Keep status messages concise**: Users see these on the console
4. **Be verbose in detail logs**: Include all information that might help debugging
5. **Use appropriate log levels**:
   - `DEBUG`: Detailed diagnostic information (detail logger only)
   - `INFO`: General informational messages
   - `WARNING`: Warning messages that users should notice
   - `ERROR`: Error messages
   - `CRITICAL`: Critical failures

## Log File Location

By default, logs are written to: `.aletheia-probe/aletheia-probe.log` (in the current working directory, alongside `cache.db`)

The log file is overwritten on each run to prevent unbounded growth.

## Example Output

### Console (stderr) - User sees this:

**BibTeX Assessment:**
```
Parsing BibTeX file: references.bib
Found 25 entries with journal information
[1/25] Assessing: IEEE Transactions on Software Engineering
    → LEGITIMATE (confidence: 0.95)
[2/25] Assessing: Predatory Journal XYZ
    → PREDATORY (confidence: 0.87)
...
```

**Sync Command:**
```
Synchronizing cache with backend configuration...
  bealls: Updated 1234 records
  doaj: Data is current
  scopus: Data is current
  predatoryjournals: Updated 567 records
Synchronization completed
```

### Log File - Contains both status and detail logs:

**BibTeX Assessment Example:**
```
2025-11-15 14:30:01 - journal_assessment.detail - INFO - Logging initialized. Log file: /home/user/.aletheia-probe/aletheia-probe.log
2025-11-15 14:30:01 - journal_assessment.status - INFO - Parsing BibTeX file: references.bib
2025-11-15 14:30:01 - journal_assessment.detail - DEBUG - Starting BibTeX file assessment: references.bib
2025-11-15 14:30:01 - journal_assessment.detail - DEBUG - Successfully parsed 25 entries
2025-11-15 14:30:01 - journal_assessment.status - INFO - Found 25 entries with journal information
2025-11-15 14:30:01 - journal_assessment.status - INFO - [1/25] Assessing: IEEE Transactions on Software Engineering
2025-11-15 14:30:01 - journal_assessment.detail - DEBUG - Processing entry 1/25: IEEE Transactions on Software Engineering (type: article)
2025-11-15 14:30:01 - journal_assessment.detail - DEBUG - Normalized journal name: ieee transactions on software engineering
2025-11-15 14:30:02 - journal_assessment.detail - DEBUG - Assessment result: legitimate, confidence: 0.95
2025-11-15 14:30:02 - journal_assessment.status - INFO -     → LEGITIMATE (confidence: 0.95)
...
```

**Sync Command Example:**
```
2025-11-15 14:35:01 - journal_assessment.detail - INFO - Starting cache synchronization with backend configuration
2025-11-15 14:35:01 - journal_assessment.status - INFO - Synchronizing cache with backend configuration...
2025-11-15 14:35:01 - journal_assessment.detail - DEBUG - Syncing all backends: bealls, doaj, scopus, predatoryjournals
2025-11-15 14:35:01 - journal_assessment.detail - DEBUG - Processing backend: bealls
2025-11-15 14:35:02 - journal_assessment.detail - INFO - Data for bealls is stale, updating...
2025-11-15 14:35:03 - journal_assessment.detail - INFO - Successfully fetched data for bealls: {'status': 'success', 'records_updated': 1234}
2025-11-15 14:35:03 - journal_assessment.status - INFO -   bealls: Updated 1234 records
2025-11-15 14:35:03 - journal_assessment.detail - DEBUG - Processing backend: doaj
2025-11-15 14:35:03 - journal_assessment.detail - DEBUG - Data for doaj is fresh, no update needed
2025-11-15 14:35:03 - journal_assessment.status - INFO -   doaj: Data is current
...
2025-11-15 14:35:10 - journal_assessment.detail - INFO - Cache synchronization completed
2025-11-15 14:35:10 - journal_assessment.status - INFO - Synchronization completed
```
