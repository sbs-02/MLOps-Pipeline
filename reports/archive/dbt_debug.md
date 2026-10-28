# dbt debug report (Gate 5)

Overall status: **PASS**

## Versions

- dbt Core: **1.12.6** (up to date)
- dbt-duckdb: **1.11.0** (up to date)
- DuckDB (runtime): **1.5.6**
- Python: **3.12.13**

## Project

- Project dir: `dbt_project/`
- Profile: `mlops` (target `dev`)
- Main database: `warehouse/dbt.duckdb` (Git-ignored)
- Attached catalog: `ducklake:warehouse/ducklake/catalog.duckdb` as `ducklake` (`is_ducklake: true`, read/write)

## Attach proof

`dbt debug` reports `Connection test: OK connection ok` and `All checks passed!`.
The DuckLake catalog (spec 1.0, build `ac7595b0`) is attached read/write, so models can
materialize into it.

## Minimal model

- `models/staging/stg_ga_sessions.sql` -> `ducklake.stg.stg_ga_sessions` (view)
- Source: `ducklake.raw.ga_sessions` (903,653 rows)
- Result: `PASS=1` in 0.72 s; row count **903,653**.
- Tests: `not_null` on `fullVisitorId`, `visitId`, `date` -> `PASS=3`.

## Commands and outcomes

```text
dbt --version
  Core: 1.12.6 (up to date); duckdb plugin: 1.11.0 (up to date)

dbt debug --project-dir dbt_project --profiles-dir .
  Connection test: OK connection ok
  All checks passed!

dbt run --project-dir dbt_project --profiles-dir . --select stg_ga_sessions
  1 of 1 OK created sql view model ducklake.main...stg.stg_ga_sessions (0.24s)
  Completed successfully: PASS=1 WARN=0 ERROR=0

dbt test --project-dir dbt_project --profiles-dir . --select stg_ga_sessions
  3 of 3 PASS (0.14s each)
  Completed successfully: PASS=3 WARN=0 ERROR=0
```

## Notes and limitations

- `generate_schema_name` is overridden so `+schema: stg` lands in `ducklake.stg`
  instead of `ducklake.main_stg`.
- The `marts` config path is declared but unused until Gate 6 adds mart models.
- `profiles.yml` is Git-ignored; `profiles.yml.example` is the tracked template.
- dbt writes `target/`, `logs/`, `dbt_packages/` under `dbt_project/` (Git-ignored).
- DuckDB 2.0 / DuckLake 1.1 remain deferred (Gate 4 decision).
- Time travel, snapshot expiry, merge and Iceberg interop are out of scope for this gate.
