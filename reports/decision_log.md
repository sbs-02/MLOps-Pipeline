# Project Decision Log

This log records the core architecture, data, and modeling decisions approved for the Local Analytics-to-ML Drift Monitoring Platform.

---

## Gate 0 — Inspection and Working Rules
- **Notebooks vs. `src/` Code:**
  - Exploratory and reproducible workflows belong in numbered notebooks under `notebooks/` (e.g. `01_download_ga_sessions.ipynb`, `02_ingest_schema_inspect.ipynb`).
  - Notebook cell outputs must always be cleared before committing to Git to prevent repository bloat and diff pollution.
  - All reusable logic required by downstream components (dbt, APIs, DAGs, testing) must live in `src/analytics_ml/`. Notebooks import from `src/` rather than containing standalone business logic.

---

## Gate 1 — Cleanup
- **Targeted Deletions:**
  - Removed exploratory scripts, zip archives, and unneeded placeholders while preserving package structure (`__init__.py`), `notebooks/scratch/.gitkeep`, and local directory skeletons.

---

## Gate 2 — Git and Repository Hygiene
- **Local-First & Secret Protection:**
  - Hard-coded GCP credentials, bucket names, and project IDs are forbidden. Configuration is read from environment variables (e.g. `GCP_PROJECT`).
  - `.gitignore` strictly excludes raw data (`data/`), local warehouse files (`warehouse/`), model artifacts (`models/`, `artifacts/`), virtual environments (`.venv/`), and local secrets (`.env`).
  - Repository enforces UTF-8 without BOM and consistent line endings (`.gitattributes`).

---

## Gate 3 — Reproducible Environment
- **Python Version:**
  - Python **3.12.13** pinned via `.python-version`. Python 3.13 was evaluated and deferred because BentoML 1.4.40 declares official support only for Python 3.9–3.12.
- **Dependency Pinning:**
  - Direct dependencies pinned with exact `==` in `pyproject.toml`.
  - All 207 transitive dependencies pinned in `requirements.lock`.
  - DuckDB pinned to `1.5.6`. DuckDB 2.0.0 is deferred because DuckLake 1.1 requires DuckDB >= 2.0.0 and introduces breaking Python API changes.
  - dbt Core pinned to `1.12.6` with `dbt-duckdb` `1.11.0`.

---

## Gate 4 — DuckLake Raw Layer Verification
- **Catalog Architecture:**
  - Primary analytical lakehouse is DuckLake (spec 1.0, extension build `ac7595b0`).
  - Catalog database stored locally at `warehouse/ducklake/catalog.duckdb` (git-ignored).
  - Raw Parquet files in `data/raw/ga_sessions/` are treated as immutable inputs; ingestion into DuckLake table `ducklake.raw.ga_sessions` is idempotent (`CREATE TABLE IF NOT EXISTS` with row-count reconciliation).

---

## Gate 5 — Data, Label, and Feature Decisions

### 1. Label Definition
- Target is session-level purchase conversion: `conversion_label = (totals.transactions IS NOT NULL)`.
- A session is positive if it resulted in at least 1 transaction (`totals.transactions >= 1`).
- In the raw dataset: 11,552 converting sessions out of 903,653 raw rows (1.2784%).
- In the deduplicated mart (`fct_session_conversion`): 11,529 converting sessions out of 902,755 distinct sessions (1.2771% / ~1.28%).

### 2. Handling Duplicate Session Keys
- 898 duplicate `(fullVisitorId, visitId)` pairs exist in the raw dataset.
- Resolution in `fct_session_conversion`: Deduplicate by partitioning on `(fullVisitorId, visitId)`, ordering by `hits DESC, visitStartTime ASC, _ingested_at ASC`, and retaining only `rn = 1`.

### 3. Handling Partial Quarters & Dataset Coverage
- The Google Analytics sample spans 1 year and 1 day: **2016-08-01 through 2017-08-01**.
- Partial quarters:
  - `2016Q3`: Starts 2016-08-01 (July 2016 is absent; 2 months only).
  - `2017Q3`: Ends 2017-08-01 (August 2 to September 30 absent; 32 days only).
- Limitations: Because the sample spans only one year, year-over-year (YoY) and same-quarter-last-year comparisons cannot be performed.

### 4. Chronological Split Design
- Random splitting is strictly prohibited because repeat visitors (`fullVisitorId`) and temporal auto-correlation create data leakage between train and test sets.
- 3-way chronological split:
  - **Train Period:** `date < 20170401` (2016Q3, 2016Q4, 2017Q1; 2016-08-01 to 2017-03-31; 8 months)
  - **Validation Period:** `20170401 <= date < 20170701` (2017Q2; 2017-04-01 to 2017-06-30; 3 months) — used for model selection, threshold tuning, and probability calibration.
  - **Test Period:** `date >= 20170701` (2017Q3 holdout; 2017-07-01 to 2017-08-01; 1 month, 1 day) — final unbiased holdout.

### 5. Feature Schema & Leakage Rules

| Field Name | Source Column | Available at Prediction Time? | Justification / Leakage Policy |
|---|---|---|---|
| `channelGrouping` | `channelGrouping` | **Yes** | Known upon session arrival (Organic Search, Direct, Referral, etc.). |
| `device_category` | `device.deviceCategory` | **Yes** | Extracted from HTTP User-Agent header at session start. |
| `browser` | `device.browser` | **Yes** | Extracted from HTTP User-Agent header at session start. |
| `operating_system` | `device.operatingSystem` | **Yes** | Extracted from HTTP User-Agent header at session start. |
| `country` | `geoNetwork.country` | **Yes** | Resolved from client IP geolocation on first request. |
| `continent` | `geoNetwork.continent` | **Yes** | Resolved from client IP geolocation on first request. |
| `traffic_source` | `trafficSource.source` | **Yes** | Known from HTTP referer or inbound campaign UTM parameters. |
| `traffic_medium` | `trafficSource.medium` | **Yes** | Known from inbound campaign UTM parameters / classification. |
| `visitNumber` | `visitNumber` | **Yes** | Sequence counter of visits for this cookie (prior visits + 1). |
| `visits` | `totals.visits` | **Yes** | Session flag (constant 1 for valid sessions). |
| `hits` | `totals.hits` | **Yes** | Cumulative interaction count during the session. |
| `pageviews` | `totals.pageviews` | **Yes** | Cumulative pageviews during the session. |
| `time_on_site` | `totals.timeOnSite` | **Yes** | Session engagement time up to prediction point (0 if null). |
| `conversion_label` | Derived target | **No (Target)** | **Excluded from features.** The ground truth label being predicted. |
| `fullVisitorId` | `fullVisitorId` | **No (Identifier)** | **Excluded.** High-cardinality visitor identifier; causes memorization. |
| `visitId` | `visitId` | **No (Identifier)** | **Excluded.** Ephemeral session timestamp identifier. |
| `date` | `date` | **No (Split key)** | **Excluded from features.** Used solely for chronological partitioning. |
| `transactions` | `totals.transactions` | **No (Target Leakage)** | **Excluded.** Directly leaks the transaction outcome. |
| `transactionRevenue` | `totals.transactionRevenue` | **No (Target Leakage)** | **Excluded.** Directly leaks purchase revenue. |
| `totalTransactionRevenue`| `totals.totalTransactionRevenue` | **No (Target Leakage)** | **Excluded.** Directly leaks purchase revenue. |
| `transaction_count` | `stg_transactions` | **No (Target Leakage)** | **Excluded.** Derived transaction counter. |
| `transaction_revenue_micros` | `stg_transactions` | **No (Target Leakage)** | **Excluded.** Derived revenue field. |
| `_ingested_at` | Metadata | **No (Metadata)** | **Excluded.** Ingestion pipeline timestamp. |
| `_source` | Metadata | **No (Metadata)** | **Excluded.** Ingestion source identifier. |

---

## Gate 6 — Iceberg Interoperability Demo
- **Interoperability Path:**
  - Demonstrated via PyIceberg writing a subset (2017Q3, 74,368 rows) to SQLite catalog (`warehouse/iceberg_interop/catalog.db`) and verifying DuckDB reads via `iceberg_scan()`.
  - DuckDB `iceberg_scan` is read-only; writes to Iceberg require an external Iceberg REST catalog.
  - Iceberg serves as an interoperability demo; DuckLake is the primary analytical store.

---

## Gate 7 — dbt Transformation Layer
- **Connection to DuckLake:**
  - dbt connects via `dbt-duckdb` (`profiles.yml`), targeting `warehouse/dbt.duckdb`, with `extensions: ['ducklake']` and an attached catalog `ducklake:warehouse/ducklake/catalog.duckdb` (`is_ducklake: true`, read/write).
  - Models:
    - Staging views: `stg_ga_sessions`, `stg_transactions` in `ducklake.stg`.
    - Intermediate views: `int_session_behavior` in `ducklake.intermediate`.
    - Marts table: `fct_session_conversion` in `ducklake.marts` (902,755 deduplicated rows).
  - 22 data tests passing (uniqueness, referential integrity, non-negative counts, reconciliation).
