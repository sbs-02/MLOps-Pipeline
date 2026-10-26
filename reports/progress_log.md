# Progress log

Short running log so the project can be resumed after a restart.
One entry per gate: date, status, commit, and what was verified.

## Gate 0 — read-only inspection (2026-10-23)

- Read `CONTEXT.md`, `IMPLEMENTATION_GUIDE.md`, `README.md`, `notebooks/structure.md`, `reports/*.md`.
- Re-verified all 12 facts from the user's earlier ZIP review: 12 CONFIRMED.
- Decisions approved: notebook rule + fate of the three `.py` scripts; keep this log.

## Gate 1 — cleanup (2026-10-23)

- Deleted six named paths: `llm_context.zip`, `_sizelist.ps1`, `warehouse/.gitkeep`,
  `warehouse/README.md`, `session-ses_1.md`, `session-ses_2.md`.
- Kept the 9 `__init__.py`, `notebooks/scratch/.gitkeep`, and the placeholder READMEs.
- Verified: targeted paths gone, kept paths present, `data/`/`.venv/`/`models/` untouched.

## Gate 2 — Git and hygiene (2026-10-23 → 2026-10-26)

- `git init` on `main`; `.gitignore` rewritten (data, warehouse, models, artifacts, secrets,
  venv, session exports) with `git check-ignore` proofs for each rule.
- BOMs stripped; notebook outputs cleared; hard-coded GCP project ID replaced by `GCP_PROJECT`;
  absolute `D:` paths removed from notebooks and reports; README repaired; placeholder purposes added.
- Secret scan of the staged index: no matches.
- **Committed 2026-10-26 as `667a91b`** — 46 files, no remote configured, no push.

## Gate 3 — reproducible environment (2026-10-26)

- Interpreter pinned to CPython **3.12.13** (`.python-version`), because BentoML 1.4.40
  does not declare Python 3.13 support and is a required component for Gate 9.
- `pyproject.toml` rewritten with exact `==` pins for every direct dependency; missing
  `pyarrow`, `pyiceberg[sql-sqlite]`, `google-cloud-bigquery`, `ipykernel`, `numpy`, `pydantic`
  added; stale dbt range (`1.9.x`) replaced with `dbt-core 1.12.6` + `dbt-duckdb 1.11.0`.
- `requirements.lock` records all 207 transitive packages of the verified environment.
- `tests/unit/test_environment.py` added (47 checks: interpreter, pins, imports, lock integrity).
- `duckdb` pinned to `1.5.6`; the 2.0.0 upgrade is deferred to Gate 4 (breaking Python API
  changes, DuckLake compatibility matrix does not list 2.0 yet).
- Verified: `pip check` clean, 47/47 tests pass, and a **fresh venv rebuilt from
  `requirements.lock` produces a byte-identical package set** and passes the same tests.

## Gate 4 — DuckLake verification (2026-10-26)

- Created `notebooks/02_ingest_schema_inspect.ipynb` (22 cells) combining raw schema
  inspection and DuckLake ingest, with reusable logic in `src/analytics_ml`.
- Refactored `ducklake_setup.py` (attach/create/metrics/reopen/idempotency/versions/
  run_verification/report) and `inspect_raw.py` (inspect/render/write functions).
- Created `tests/integration/test_ducklake.py` (6 tests: create, reopen in a subprocess,
  idempotency, schema, versions, read-only warehouse reconciliation, report hygiene).
- Verified against the real catalog: **903,653 rows**, **902,755 distinct**, **11,552**
  transaction sessions, dates **20160801 -> 20170801**, all 5 quarters match.
- Reopen in a fresh process returns the same counts and snapshot id **2**.
- Re-running the ingest is a no-op: no new rows, no new snapshot (3 snapshots before/after).
- Version record: DuckDB **1.5.6**, DuckLake extension build **ac7595b0**, catalog spec **1.0**.
- DuckLake 1.1 requires DuckDB >= 2.0.0, so the upgrade stays deferred; dbt-duckdb 1.11.0
  declares `duckdb>=1.0.0` with no upper bound but pins 1.5.5 in its `md` extra.
- Wrote `reports/ducklake_verification.md` (overall PASS).

## Next

Gate 5 - dbt transformations and data quality (after Gate 4 is committed and approved).
