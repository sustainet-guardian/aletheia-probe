# PubMed NLM Integration

## Overview

The PubMed NLM integration adds a **weak legitimacy signal** for biomedical journals by cross-checking them against two journal lists published by the U.S. National Library of Medicine (NLM):

- **J_Medline.txt** — ~5 000 journals indexed in MEDLINE (stricter editorial vetting)
- **J_Entrez.txt** — ~30 000 journals across all NCBI databases (NLM Catalog)

Both files are plain-text flat files available on the NCBI public FTP server at no cost and without license restrictions.

## Data Sources

| File | URL | Journals | Vetting level |
|------|-----|----------|---------------|
| `J_Medline.txt` | `https://ftp.ncbi.nlm.nih.gov/pubmed/J_Medline.txt` | ~5 000 | Stricter (peer-reviewed, structured XML, Portico/CLOCKSS deposit) |
| `J_Entrez.txt` | `https://ftp.ncbi.nlm.nih.gov/pubmed/J_Entrez.txt` | ~30 000 | Broader NCBI coverage |

## Architecture

### Data Source Components

- **Module**: `src/aletheia_probe/updater/sources/pubmed.py`
- **Class**: `PubMedNLMSource`
- **Base class**: `DataSource`
- **Update cadence**: Monthly (30 days)

### Backend Components

- **Module**: `src/aletheia_probe/backends/pubmed.py`
- **Class**: `PubMedBackend`
- **Base class**: `ConfiguredCachedBackend`
- **Evidence type**: `LEGITIMATE_LIST`
- **Cache TTL**: `24 * 30` hours

### Configuration

Defined in `src/aletheia_probe/config.py` (`DataSourceUrlConfig`):

- `pubmed_nlm_medline_url` — URL for `J_Medline.txt`
- `pubmed_nlm_catalog_url` — URL for `J_Entrez.txt`

## Confidence Calibration

| Scenario | Status | Confidence |
|----------|--------|------------|
| Found in MEDLINE subset (`is_medline: True`) | LEGITIMATE | 0.65 |
| Found only in NLM Catalog (`is_medline: False`) | LEGITIMATE | 0.50 |
| Not found in either list | NOT_FOUND | — (no negative signal) |

The confidence values are deliberately conservative because:
- MEDLINE indexing is weaker than DOAJ or Scopus vetting
- Some predatory journals have been found to pass NLM's structural criteria
- Absence from the list is expected for all non-biomedical venues

## Data Processing Rules

1. Download `J_Medline.txt` and parse all records into journal entries tagged `is_medline: True`.
2. Download `J_Entrez.txt` and parse all records tagged `is_medline: False`.
3. Exclude from the Entrez entries any NlmId already present in the MEDLINE set to avoid duplicates.
4. Validate and normalize all ISSNs to `NNNN-NNNN` format; drop invalid ISSNs.
5. Deduplicate by normalized journal name before writing to the cache.

## Metadata Stored

Each PubMed NLM entry stores:

- `is_medline` — `True` if in MEDLINE subset, `False` if NLM Catalog only
- `med_abbr` — NLM abbreviation (e.g., `N Engl J Med`)
- `nlm_id` — NLM unique identifier

## Domain Coverage

This backend only covers **biomedical and life-science journals**. It has:

- **Zero coverage** for computer science, physics, social sciences, engineering, or any conference venue.
- **No negative signal** on non-biomedical journals — NOT_FOUND should not be interpreted as suspicious.

## Usage

```bash
# Sync PubMed NLM data only
aletheia-probe sync pubmed_nlm

# Normal sync includes PubMed NLM when enabled
aletheia-probe sync
```

## Limitations

1. **Predatory journals can be indexed** — MEDLINE is not a reliable purity filter; some predatory journals have been found indexed.
2. **Domain-limited** — biomedical-only; irrelevant for CS/physics/social-science journals.
3. **Weak negative signal** — not being listed is expected for most legitimate journals outside biomedicine.
4. **Slow editorial curation** — journal list changes are infrequent; new journals may lag.
5. **OpenAlex overlap** — the existing OpenAlex heuristic backend already provides biomedical coverage; PubMed NLM adds an independent editorial-vetting data point.

## References

- `src/aletheia_probe/updater/sources/pubmed.py`
- `src/aletheia_probe/backends/pubmed.py`
- `tests/unit/backends/test_pubmed.py`
- `tests/unit/updater/test_pubmed_source.py`
- https://www.nlm.nih.gov/bsd/serfile_addedinfo.html
- https://ftp.ncbi.nlm.nih.gov/pubmed/
