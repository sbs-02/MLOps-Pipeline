# Local-First Analytics-to-ML Drift Monitoring & Governance Platform

> **Proof of Concept.** A reproducible, local-first data engineering and MLOps platform demonstrating purchase-conversion prediction, covariate & concept drift monitoring, human-in-the-loop retraining governance, and automated Airflow orchestration on the public Google Analytics sample dataset (`bigquery-public-data.google_analytics_sample.ga_sessions_*`).

---

## 1. System Architecture

```text
[Google Analytics Public Sample (903,653 rows)]
                      │
                      ▼
[DuckLake Lakehouse (DuckDB 1.5.6 + DuckLake ac7595b0 Catalog)]
                      │
                      ▼
[dbt Transformation Layer (dbt-duckdb 1.11.0)]
  stg_ga_sessions ──► int_session_behavior ──► fct_session_conversion (902,755 deduplicated rows)
                                                      │
                      ┌───────────────────────────────┴───────────────────────────────┐
                      ▼                                                               ▼
            [Model Training & Serving]                                      [Continuous Monitoring]
         Logistic Regression Baseline                                     Statistical Drift Engine
         PR-AUC: 0.4026 | ROC-AUC: 0.9838                               KS Test & Jensen-Shannon Divergence
                      │                                                               │
                      ▼                                                               ▼
             [BentoML Prediction API]                                      [Prometheus Exporter]
             Local Port: 127.0.0.1:3001                                   Local Port: 127.0.0.1:8001
                      ▲                                                               │
                      │                                                               ▼
                      │                                                   [Grafana Alerting & Dashboard]
                      │                                                    Local Port: 127.0.0.1:3000
                      │                                                               │
                      │                                                    (Drift Detected Alert)
                      │                                                               │
                      │                                                               ▼
                      │                                                  [Human Approval Control Plane]
                      │                                                   FastAPI UI & Control Service
                      │                                                    Local Port: 127.0.0.1:8000
                      │                                                               │
                      │                                                    (Operator Human Review)
                      │                                                               │
                      │                                                  Approve ─────┴───── Reject
                      │                                                     │                   │
                      │                                          (Issues Run ID)         (Halt Pipeline)
                      │                                                     │
                      │                                                     ▼
                      └─────────────────────────────────────── [Airflow Retraining DAG]
                                                                `approved_retraining`
                                                                Local Port: 127.0.0.1:8080
                                                                Task 1: Verify Auth
                                                                Task 2: Consume Token
                                                                Task 3: Validate Mart
                                                                Task 4: Train Candidate
                                                                Task 5: Evaluate & Promote
```

---

## 2. Local Service Directory & Port Map

All services are strictly bound to `127.0.0.1` (localhost):

| Service | Port | Description | Health Endpoint |
| :--- | :--- | :--- | :--- |
| **Grafana Dashboard** | `127.0.0.1:3000` | Real-time drift telemetry & visual alert panels | `http://127.0.0.1:3000/api/health` |
| **BentoML Prediction API** | `127.0.0.1:3001` | Session conversion inference engine | `http://127.0.0.1:3001/health` |
| **Human Approval UI & API** | `127.0.0.1:8000` | Human governance console & decision endpoints | `http://127.0.0.1:8000/health` |
| **Drift Metrics Exporter** | `127.0.0.1:8001` | Prometheus metric exposition server | `http://127.0.0.1:8001/metrics` |
| **Airflow Webserver** | `127.0.0.1:8080` | Orchestration console for approved DAGs | `http://127.0.0.1:8080/health` |
| **Prometheus Server** | `127.0.0.1:9090` | Timeseries metrics aggregator & scraper | `http://127.0.0.1:9090/-/healthy` |

---

## 3. Quickstart & Verification

### Prerequisites
- Python 3.12.x (CPython 3.12.13 pinned in `.python-version`)
- Docker Desktop with Docker Compose v2 (optional for containerized Airflow/Prometheus/Grafana)
- Local virtual environment created from `pyproject.toml` / `requirements.lock`

### Installation
```powershell
# Clone and enter workspace
cd d:\MLOps

# Recreate verified virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dbt,ml-serving,monitoring,api,dev]"
```

### Run Full Test Suite (114 automated tests)
```powershell
.\.venv\Scripts\pytest -v
```

### Run End-to-End Demonstration Scenario
Walk through the entire 7-step lifecycle (baseline $\rightarrow$ normal batch $\rightarrow$ mobile surge $\rightarrow$ drift alert $\rightarrow$ operator rejection $\rightarrow$ operator approval $\rightarrow$ candidate retraining $\rightarrow$ safe promotion):
```powershell
.\.venv\Scripts\python scripts/run_e2e_demo.py
```

### Start Services Individually
```powershell
# BentoML Prediction Service
.\.venv\Scripts\python -m bentoml serve services.prediction.service:ConversionService --port 3001 --host 127.0.0.1

# Approval Control-Plane Service & Web Console
.\.venv\Scripts\python -m uvicorn services.approval.app:app --host 127.0.0.1 --port 8000 --reload
```

---

## 4. Key Architectural Decisions

1. **Local Lakehouse (DuckDB + DuckLake + Iceberg):**
   - 903,653 raw records stored in DuckLake (`warehouse/ducklake/catalog.duckdb`) with zero cloud egress fees.
   - Clean dbt transformations produce 902,755 deduplicated session rows in `dl.marts.fct_session_conversion`.
2. **Leakage-Safe Chronological 3-Way Split:**
   - **Training:** 2016-08-01 to 2017-03-31 (632,648 rows, 7,476 positives, 1.18% prevalence).
   - **Validation:** 2017-04-01 to 2017-06-30 (195,844 rows, 2,986 positives, 1.52% prevalence).
   - **Test Holdout:** 2017-07-01 to 2017-08-01 (74,263 rows, 1,067 positives, 1.44% prevalence).
   - Strictly excluded post-prediction leakage fields (`transactions`, `transactionRevenue`, `totalTransactionRevenue`).
3. **Statistical Drift Detection Engine:**
   - Continuous features: Two-sample Kolmogorov-Smirnov test ($p < 0.05$) and Wasserstein distance.
   - Categorical features: Jensen-Shannon divergence ($D_{\text{JS}} > 0.15$).
   - Dataset drift declared when $\ge 30\%$ of features exhibit drift.
   - Concept drift evaluates F1 degradation ($>15\%$ drop) when ground truth labels are observed, or explicitly returns `labels_pending` when delayed.
4. **Human-in-the-Loop Governance:**
   - Alerts never trigger retraining automatically.
   - Control-plane SQLite database (`warehouse/approvals.db`) tracks state transitions: `PENDING` $\rightarrow$ `APPROVED` / `REJECTED` / `EXPIRED`.
   - Replay attack defense: approvals generate unique `authorized_run_id` tokens that are consumed upon execution.
5. **Airflow Retraining Safety:**
   - Retraining DAG `approved_retraining` validates approval authorization before running.
   - Candidate models must pass quality gates (PR-AUC $\ge 0.35$, F1 $\ge 0.30$, PR-AUC degradation $\le 0.05$).
   - Atomic rollback: active model is backed up to `baseline_logreg_backup.joblib` before promotion.

---

## 5. Repository Structure

```text
MLOps/
├── config/                 # Drift and application YAML configuration
├── dags/                   # Airflow DAGs (approved_retraining_dag.py)
├── data/                   # Raw, interim, and simulated data (git-ignored)
├── dbt_project/            # dbt transformation models, macros, and schema tests
├── models/                 # Model artifacts, schemas, and metadata (git-ignored)
├── monitoring/             # Prometheus scrapers, Grafana dashboards & alerting rules
├── notebooks/              # Numbered reproducible research notebooks
├── reports/                # Technical documentation reports and decision logs
├── scripts/                # Standalone demonstration runners (run_e2e_demo.py)
├── services/
│   ├── approval/           # FastAPI approval console and decision API
│   └── prediction/         # BentoML serving service and sample client
├── src/analytics_ml/
│   ├── approval/           # Approval data models and SQLite store
│   ├── monitoring/         # Drift detector, metrics exporter, synthetic batches
│   ├── retraining/         # Retraining engine, candidate evaluator, promotion
│   └── training/           # Baseline model training, 3-way split, calibration
├── tests/
│   ├── e2e/                # End-to-end full lifecycle demonstration tests
│   ├── integration/        # DuckLake, dbt, BentoML, and monitoring smoke tests
│   └── unit/               # Fast, isolated unit tests across all components
└── warehouse/              # Local DuckDB catalogs and SQLite DBs (git-ignored)
```

---

## 6. License & Provenance
- Dataset: Google Analytics Sample (`bigquery-public-data.google_analytics_sample.ga_sessions_*`).
- Intended strictly for local evaluation, educational data engineering, and MLOps demonstration.
# Environment record (Gate 3)

Verified on 2026-10-26. Regenerate this file only after an approved dependency change.

## Host

| Item | Value |
|---|---|
| OS | Windows 11 Pro (win_amd64) |
| Interpreter | CPython **3.12.13** (uv-managed build) |
| Virtualenv | `.venv/` (git-ignored) |
| Venv creator | uv 0.11.26 (`uv venv --python 3.12.13 --seed`) |
| pip | 26.2.2 |
| Build backend | setuptools 84.2.1 + wheel 0.48.0 |
| Package count | 207 distributions recorded in `requirements.lock` |

`python` on `PATH` is the system 3.12.10; the project must always be invoked through
`.\.venv\Scripts\python.exe`. `.python-version` pins 3.12.13 for uv.

## Why 3.12 and not 3.13

BentoML is a required component (Gate 9). BentoML 1.4.40 declares support for Python
3.9–3.12 only (PyPI classifiers, and its CI matrix at tag `v1.4.40` tests 3.9/3.11/3.12).
The previous `.venv` was 3.13.14, which no dependency officially supported for serving.
The environment was rebuilt on 3.12.13 so that every pinned dependency is officially
supported. Decision taken with user approval (Gate 3, D1 Option B).

## Direct dependencies

| Package | Pin | Notes |
|---|---|---|
| duckdb | 1.5.6 | 2.0.0 exists but is deferred (see below) |
| pandas | 3.0.6 | 3.1.0 released 2026-10-22; staying on the verified build |
| numpy | 2.5.4 | required by pandas ≥2.0.2 on 3.12 |
| pyarrow | 26.0.0 | parquet I/O |
| pyiceberg[sql-sqlite] | 0.12.0 | pulls SQLAlchemy 2.1.6 for `SqlCatalog` |
| google-cloud-bigquery | 3.46.1 | 3.46.2 available; acquisition is finished |
| scikit-learn | 1.9.1 | Gate 8 baseline |
| pyyaml | 6.0.3 | was declared but never installed before Gate 3 |
| ipykernel | 7.4.0 | notebook kernel |
| pydantic | 2.14.1 | shared by pyiceberg / fastapi / bentoml |
| dbt-core | 1.12.6 | pulls `dbt-core-experimental-parser` 2.0.8 |
| dbt-duckdb | 1.11.0 | upstream dev pins target dbt-core ≥1.12 |
| bentoml | 1.4.40 | Python 3.9–3.12 |
| evidently | 0.7.23 | pins plotly <6 (resolves 5.24.1) |
| prometheus-client | 0.26.0 | |
| fastapi | 0.162.0 | |
| uvicorn[standard] | 0.54.0 | |
| pytest / pytest-cov | 9.1.1 / 7.1.0 | |
| ruff / mypy / httpx | 0.17.2 / 2.4.0 / 0.28.1 | |

Notable transitives: scipy 1.18.1, statsmodels 0.15.0, litestar 2.25.0, starlette 1.10.0,
dbt-adapters 1.24.5, dbt-common 1.39.0, metricflow 0.213.0.

## Rebuild

```powershell
uv venv --python 3.12.13 --seed .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
.\.venv\Scripts\python.exe -m pytest tests/unit/test_environment.py -q
```

`requirements.lock` is platform-specific (Windows, cp312). On another OS, re-resolve
from `pyproject.toml` instead of reusing the lock.

## Verification performed

| Check | Command | Result |
|---|---|---|
| Interpreter | `.\.venv\Scripts\python.exe -VV` | `Python 3.12.13` |
| Dependency consistency | `python -m pip check` | `No broken requirements found.` |
| Environment tests | `python -m pytest tests/unit/test_environment.py -q` | 47 passed |
| dbt | `.\.venv\Scripts\dbt.exe --version` | Core 1.12.6, duckdb plugin 1.11.0 |
| BentoML | `python -m bentoml --version` | `1.4.40` |
| Lock fidelity | `pip freeze` vs `requirements.lock` | identical (207/207) |
| Fresh rebuild | new venv in `%TEMP%`, install lock + editable | identical set, 47 passed, `pip check` clean |

## Deferred and known limitations

- **DuckDB 2.0.0** (released 2026-10-21) is not used. Its Python client removes
  `execute().fetch_arrow_table()`, `.arrow()`, `.pl()` and `relation.fetchone()/fetchmany()`,
  and the DuckLake compatibility matrix lists DuckDB only up to 1.5.2. Upgrade is a
  Gate 4 decision with the existing catalog in scope.
- **Evidently 0.7.23 + pandas 3.0.6** is not a combination covered by upstream tests;
  the import is verified, full drift reports are exercised in Gate 10.
- **dbt-core 1.12.6** depends on a pre-release lineage package
  (`dbt-core-experimental-parser` 2.0.8). It is pinned in the lock.
- The lock does not carry hashes (`--require-hashes`). Adding hashes would need a
  separate approved change.
- A 2 MB leftover of the previous 3.13 venv remains at `.venv-stale-313/` because two
  orphaned Jupyter kernels still hold `python.exe` and native extensions open. It is
  locally excluded via `.git/info/exclude` and can be removed once those kernels exit.

