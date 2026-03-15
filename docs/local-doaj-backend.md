# Local DOAJ Backend

By default, `aletheia-probe` checks journal legitimacy against the
[DOAJ (Directory of Open Access Journals)](https://doaj.org/) REST API.
The **local mode** lets you run entirely offline using a CSV snapshot
downloaded directly from DOAJ — no network calls, no rate limiting.

---

## Step 1 — Download the DOAJ CSV

1. Go to <https://doaj.org/docs/public-data-dump/>
2. Click **"Download journals CSV"**.  No login is required.
3. The downloaded file will be named something like:

   ```
   journalcsv__doaj_20260314_1626_utf8.csv
   ```

> **Note:** Use the CSV export (not the JSON bulk-download).

---

## Step 2 — Place the file

Create the directory `.aletheia-probe/doaj/` **inside your working directory**
(the directory from which you run `aletheia-probe`) and copy the file there:

```bash
mkdir -p .aletheia-probe/doaj/
cp ~/Downloads/journalcsv__doaj_*.csv .aletheia-probe/doaj/
```

If multiple files matching `journalcsv__doaj_*.csv` are present, the most
recently modified one is used.

---

## Step 3 — Sync the local cache

```bash
aletheia-probe sync doaj
```

This reads the CSV and writes the journal records into the local SQLite
database.  Re-running sync within 30 days of the last update is a no-op
unless `--force` is passed.

---

## Step 4 — Enable local mode

Set the environment variable `DOAJ_MODE=local` before running any
`aletheia-probe` command:

```bash
export DOAJ_MODE=local
aletheia-probe assess "Nature"
```

Or inline for a single run:

```bash
DOAJ_MODE=local aletheia-probe mass-eval --input papers.bib
```

---

## Verifying the setup

```bash
DOAJ_MODE=local aletheia-probe status
```

The DOAJ line should show `mode=local` together with the entry count and
last-updated date:

```
✅ doaj (enabled, cached, mode=local) 📊 has data (22,672 entries) (updated: 2026-03-14)
```

---

## Keeping the data fresh

DOAJ publishes updated snapshots regularly.  To refresh:

1. Download the latest CSV from <https://doaj.org/docs/public-data-dump/>.
2. Replace the file in `.aletheia-probe/doaj/`.
3. Run `aletheia-probe sync doaj --force`.

---

## Differences from remote mode

Local mode is **not** a 1:1 replacement for the remote DOAJ API.  There are
two notable differences:

**Coverage** — The CSV contains only journals that DOAJ has accepted as fully
open access.  The remote API may return results for journals that are in
DOAJ's index but not yet reflected in the most recently downloaded CSV
snapshot.  Conversely, journals removed from DOAJ since the snapshot was
taken will still appear in the local cache until the next sync.

**Matching strategy** — The remote API performs server-side fuzzy/full-text
search and may return approximate matches for journal names it cannot find
exactly (for example, matching "Nature" against "Nature-Nurture Journal of
Psychology").  The local mode uses exact name and ISSN matching only, so
it will not return such approximate hits.  This makes local mode
**more precise** but means it may return `not_found` for queries where the
remote API would have returned a low-confidence fuzzy match.

In practice, for well-formed journal names or ISSNs the two modes produce
identical results.  Discrepancies are a sign that the remote API result was
a false positive, or that the local snapshot is out of date.

---

## Switching back to remote mode

Remove or unset `DOAJ_MODE` (or set it to `remote`) to use the live DOAJ API:

```bash
unset DOAJ_MODE
aletheia-probe assess "Nature"
```
