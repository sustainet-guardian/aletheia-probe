# Local OpenCitations Backend

By default, `aletheia-probe` queries the public OpenCitations API.
For repeatable, high-volume runs you can switch to a local PostgreSQL-backed
OpenCitations snapshot through the optional adapter package.

> Availability: local mode requires `aletheia-opencitations-adapter` from
> `aletheia-probe-opencitations-platform`. It is optional and not a core
> dependency of `aletheia-probe`.

## Step 1 - Install the adapter package

```bash
pip install \
  "git+https://github.com/sustainet-guardian/aletheia-probe-opencitations-platform.git#subdirectory=adapter"
```

## Step 2 - Set environment variables

```bash
export OPENCITATIONS_MODE=local
export OPENCITATIONS_LOCAL_DB_DSN='host=localhost port=5432 dbname=opencitations user=opencitations password=...'
```

Optional:

```bash
export OPENCITATIONS_LOCAL_SNAPSHOT_DATE=2026-03-03
```

If `OPENCITATIONS_LOCAL_SNAPSHOT_DATE` is unset, the latest snapshot row per
ISSN is used.

## Step 3 - Run aletheia-probe as usual

```bash
aletheia-probe journal "Nature"
aletheia-probe bibtex references.bib
```

## Switch back to remote mode

```bash
unset OPENCITATIONS_MODE
# or
export OPENCITATIONS_MODE=remote
```
