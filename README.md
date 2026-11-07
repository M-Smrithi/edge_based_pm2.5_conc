# Edge-Based Air Quality Prediction Under Incomplete IoT Sensor Data

A research platform that measures how **the amount and pattern of missing sensor readings** affect the accuracy and
local processing latency of a lightweight PM2.5 estimator running in a **software-simulated edge gateway**.

* **Public portal (no login):** Overview · Air quality dashboard · Prediction Studio (form + CSV) · Research Lab · Methodology
* **Private admin portal:** Overview · Dataset Manager (batch upload, validation, review decisions, versions) · Model Training Center (background jobs, logs) · Experiment Manager (run / reproduce) · Model Registry (candidate → active, promotion checks, rollback) · Audit Log · Settings/users
* **Not claimed:** no physical Raspberry Pi or other edge hardware was used; latency is measured on the host computer.

Every number shown in the UI and in `docs/research_report.*` is read from saved artifacts (dataset manifests, frozen benchmark,
model metrics, experiment results). Nothing is hard-coded; with no data the pages show empty states.

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 1. first administrator (no default credentials exist)
AIOT_ADMIN_PASSWORD='a-long-passphrase-1' python manage.py create-admin --email you@example.org --password-env AIOT_ADMIN_PASSWORD

# 2. run
python manage.py serve --port 5055          # http://127.0.0.1:5055   admin: /admin
```

On macOS port 5000 is taken by AirPlay Receiver; use another port. The dev server is for local use; for a shared host run
`gunicorn -w 2 "app:create_app()"` behind HTTPS with `AIOT_SECURE_COOKIES=1`.

### Using your own data
Station files are the CPCB hourly CSVs (`From Date`, `To Date`, `PM2.5 (ug/m3)` + sensor columns).

```bash
python manage.py audit  /path/to/csvs        # reproducible audit -> storage/audits/audit_latest.{md,json,csv}
python manage.py ingest /path/to/csvs        # register files (originals stored unmodified, content-addressed)
python manage.py retrain --trials 10         # build dataset version + frozen benchmark + train + experiments
python manage.py promote model-0001          # or promote in the admin UI (checks + typed confirmation)
python scripts/build_report.py               # docs/research_report.{md,pdf} from saved artifacts
```
or do the same in the browser (Dataset Manager → Model Training Center → Model Registry). Retraining always uses **all accepted
files accumulated so far**; a new model is only a *candidate* until promoted.

`python manage.py verify` checks dataset and model checksums. `python manage.py restore-originals DIR` re-attaches original CSVs
(matched by SHA-256) if `storage/originals/` was not copied along with the project.

## How the data is handled

1. **Audit first.** Each file: size, rows, columns, timestamp span, duplicate timestamps, missing rates, valid-target count, unit/header issues.
   Verdicts: `accepted`, `accepted_recovered` (alias header or exact SI conversion only), `pending_review` (sensor absent / unit unverifiable — an administrator may admit it with an audit-logged decision), `rejected` (no PM2.5 target, unreadable, …).
2. **No guessing.** Units are never inferred. `CO µg/m³→mg/m³` and `NO mg/m³→µg/m³` are the only conversions, each logged with its factor.
3. **Cleaning policy** (counts reported per file): bad timestamps and duplicate `(station, timestamp)` rows dropped (first kept); values outside physical ranges → missing; rows without a valid PM2.5 dropped; rows with *some* missing inputs are **kept** and median-imputed.
4. **Cumulative datasets.** Originals are stored by SHA-256 and never overwritten; byte-identical re-uploads are recognised and explained; overlapping records are de-duplicated at build time and counted as identical vs conflicting; a *dataset version* is an immutable manifest + records built in a temp directory and renamed atomically.
5. **Frozen benchmark.** Chronological split + hash-chosen unseen stations; later data goes to training or a reserve, never into the frozen test sets, so results remain comparable. Creating a new benchmark is an explicit, audit-logged choice.

## Layout
`core/` pure data/ML code (schema, ingest, audit, datasets, benchmark, train, sim, gateway, experiments, reporting, analytics) ·
`app/` Flask app (db + migrations, security, services, jobs, worker, public/admin APIs, pages) · `templates/` `static/` UI (no CDN, no external fonts) ·
`tests/` · `docs/` · `scripts/` · `storage/` (data & artifacts) · `instance/` (SQLite DB, secret key; not shared).

## Tests
`python manage.py test` — see `docs/TESTING.md` for what ran and what could not run in the build environment.

## Documents
`docs/API.md` · `docs/LIMITATIONS_AND_REPRODUCIBILITY.md` · `docs/research_report.pdf|md` · `docs/TESTING.md`
