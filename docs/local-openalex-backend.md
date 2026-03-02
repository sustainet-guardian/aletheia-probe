# Local OpenAlex Backend

By default, `aletheia-probe` queries the public [OpenAlex REST API](https://openalex.org/)
over the network.  For large batch runs this can be slow (rate limits, latency).
The **local mode** lets you point `aletheia-probe` at a self-hosted OpenAlex
snapshot running in PostgreSQL — no network calls, no rate limiting.

> **Availability:** local mode requires the companion
> `aletheia-openalex-adapter` package from the
> [`aletheia-probe-openalex-platform`](https://github.com/sustainet-guardian/aletheia-probe-openalex-platform)
> repository.  It is an *optional* dependency; `aletheia-probe` itself does
> not require it.

---

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| Running OpenAlex snapshot | See the platform repo for ETL / deployment instructions |
| PostgreSQL reachable from your machine | Direct connection or `kubectl port-forward` |
| `aletheia-openalex-adapter` installed | One-time pip install (see below) |

---

## Step 1 — Install the adapter package

```bash
pip install \
  "git+https://github.com/sustainet-guardian/aletheia-probe-openalex-platform.git#subdirectory=adapter"
```

This pulls in `aletheia-openalex-provider` (psycopg2-based) as a transitive
dependency.  Nothing is added to `aletheia-probe`'s own dependency tree.

---

## Step 2 — Make PostgreSQL reachable

### Kubernetes cluster (port-forward)

```bash
sudo kubectl port-forward \
  -n aletheia-probe-openalex-platform \
  svc/openalex-platform-postgres 5432:5432 &
```

### Direct / local PostgreSQL

No extra step needed if PostgreSQL is already accessible on your machine.

---

## Step 3 — Set environment variables

```bash
# Switch the OpenAlex client to local mode
export OPENALEX_MODE=local

# Standard libpq connection variables
export PGHOST=localhost
export PGPORT=5432
export PGUSER=openalex
export PGDATABASE=openalex
# export PGPASSWORD=...   # set if your cluster requires a password
```

The `PGPASSWORD` / `PGHOST` / … variables are the standard PostgreSQL
[connection environment variables](https://www.postgresql.org/docs/current/libpq-envars.html)
read directly by psycopg2.

---

## Step 4 — Run aletheia-probe as usual

```bash
# Assess a single journal by name
aletheia-probe journal "Nature"

# Assess by ISSN
aletheia-probe journal "0028-0836"

# Process a BibTeX file
aletheia-probe bibtex references.bib
```

No other flags or config changes are needed.  The `openalex_analyzer` backend
silently uses the local snapshot instead of the remote API.

---

## Switching back to remote mode

```bash
unset OPENALEX_MODE
# or explicitly:
export OPENALEX_MODE=remote
```

---

## Verifying the setup

### Quick smoke test

```bash
OPENALEX_MODE=local aletheia-probe journal "Nature"
```

A successful run will return an assessment without any network calls to
`api.openalex.org`.

### Regression test — compare remote vs. local

```bash
aletheia-probe bibtex references.bib --output remote-results.json
OPENALEX_MODE=local aletheia-probe bibtex references.bib --output local-results.json
diff remote-results.json local-results.json
```

Minor numeric differences are expected (the public API is updated continuously;
the snapshot has a fixed cutoff date).  Assessments (LEGITIMATE / PREDATORY /
UNCERTAIN) should agree for well-established journals.

### Missing adapter — clear error message

If `OPENALEX_MODE=local` is set but the adapter is not installed, you will see:

```
ImportError: OPENALEX_MODE=local requires the aletheia-openalex-adapter package.
Install it from the aletheia-probe-openalex-platform repo:
  pip install 'git+https://github.com/sustainet-guardian/aletheia-probe-openalex-platform.git#subdirectory=adapter'
```

---

## Architecture overview

```
aletheia-probe
  openalex_analyzer backend
    └─► create_openalex_client()          ← factory in openalex.py
            │
            ├─ OPENALEX_MODE=remote ──► OpenAlexClient   (aiohttp, public API)
            │
            └─ OPENALEX_MODE=local  ──► LocalOpenAlexAdapter
                                          (aletheia-openalex-adapter package)
                                          └─► LocalOpenAlexProvider
                                                └─► psycopg2 / PostgreSQL
```

`LocalOpenAlexAdapter` exposes the same async context-manager interface as
`OpenAlexClient`, so the rest of `aletheia-probe` requires no changes.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `ImportError: OPENALEX_MODE=local requires …` | Adapter not installed | Run the `pip install` command in Step 1 |
| `psycopg2.OperationalError: could not connect` | PostgreSQL not reachable | Check `PGHOST` / `PGPORT` and the port-forward process |
| Journal not found locally, found remotely | Journal absent from snapshot | The snapshot has a cutoff date; very new journals may be missing |
| `PGPASSWORD` prompt | Password not set | Export `PGPASSWORD` or use a `.pgpass` file |
