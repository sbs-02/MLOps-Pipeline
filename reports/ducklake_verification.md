# DuckLake verification (Gate 4)

Overall status: **PASS**

## Runtime versions

| Component | Value |
|---|---|
| DuckDB | `1.5.6` |
| DuckLake extension build | `ac7595b0` |
| DuckLake catalog spec | `1.0` |
| Current snapshot id | `2` |

Catalog: `warehouse/ducklake/catalog.duckdb` (ignored by Git).

## Reconciliation: raw Parquet vs DuckLake

| Metric | Raw Parquet | DuckLake | Match |
|---|---:|---:|---|
| `sessions` | 903,653 | 903,653 | yes |
| `distinct_sessions` | 902,755 | 902,755 | yes |
| `transaction_sessions` | 11,552 | 11,552 | yes |
| `first_day` | 20160801 | 20160801 | yes |
| `last_day` | 20170801 | 20170801 | yes |

## Per-quarter reconciliation

| Quarter | DuckLake sessions | Raw sessions | Match |
|---|---:|---:|---|
| 2016Q3 | 145,791 | 145,791 | yes |
| 2016Q4 | 290,602 | 290,602 | yes |
| 2017Q1 | 196,817 | 196,817 | yes |
| 2017Q2 | 196,075 | 196,075 | yes |
| 2017Q3 | 74,368 | 74,368 | yes |

## Persistence

- Table created during this run: **False**
- Fresh read-only connection sees: **903,653** rows, snapshot `2`

## Idempotency (re-running the ingest)

- `ensure_raw_table` created a table on the second run: **False**
- Before: rows=903,653, snapshot=2, snapshots=3
- After: rows=903,653, snapshot=2, snapshots=3
- No duplicate rows and no new snapshot: **yes**

## Notes and limitations

- Raw Parquet files are immutable inputs; the DuckLake table is a derived copy.
- `CREATE TABLE IF NOT EXISTS` is skipped when the table is present, so re-running the ingest is a no-op and does not append rows.
- The catalog stores an absolute `DATA_PATH` in its metadata. Re-attaching uses the stored value; relocating the repository requires re-attaching with an explicit `DATA_PATH` or rebuilding the catalog.
- DuckLake 1.1 requires DuckDB >= 2.0.0, so this POC stays on DuckDB 1.5.6 with DuckLake spec 1.0. The upgrade is deferred until dbt and the serving stack are validated against DuckDB 2.0.
- Time travel, snapshot expiry, merge and Iceberg interop are out of scope for this gate.
