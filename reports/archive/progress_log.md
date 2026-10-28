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

## Gate 5 - dbt project setup + DuckLake attach proof (2026-10-26)

- Created `dbt_project/` with `dbt_project.yml`, staging source/model/schema, a
  `generate_schema_name` macro, and `macros/`.
- Created `profiles.yml.example` (tracked) and a local `profiles.yml` (Git-ignored).
- Attached the DuckLake catalog (`ducklake:warehouse/ducklake/catalog.duckdb`) to dbt
  with `is_ducklake: true`, read/write; models materialize into `ducklake.stg`.
- `dbt debug` passes (connection OK, DuckLake attach OK).
- `stg_ga_sessions` view builds with 903,653 rows; 3 `not_null` tests pass.
- Added `tests/integration/test_dbt_smoke.py` (5 tests, all green).
- Wrote `reports/dbt_debug.md`.

## Gate 6 - dbt model layers, tests and documentation (2026-10-26)

- Added `stg_transactions` (11,552 converting sessions), `int_session_behavior`
  (903,653 rows), and `fct_session_conversion` (902,755 deduplicated sessions).
- `fct_session_conversion` deduplicates 898 duplicate session keys and keeps
  prediction-time features only (no transaction/revenue leakage).
- 22 data tests pass, including reconciliation (mart rows == distinct raw keys),
  non-negative counts, label domain, and transaction-count positivity.
- Generated dbt docs locally (`dbt_project/target/catalog.json`, Git-ignored).
- Wrote `reports/dbt_docs.md`.

## Gate 7 - train the purchase-conversion baseline model (2026-10-26)

- Implemented `src/analytics_ml/training/train.py` (load, split, build, train, evaluate,
  save artifacts, write report) and `notebooks/04_train_baseline.ipynb`.
- Label: `conversion_label = totals.transactions IS NOT NULL` (1.28% prevalence).
- Time-based split: train 828,492 (10,462 positives), test 74,263 (1,067 positives).
- Baseline logistic regression (class_weight='balanced'): PR-AUC 0.4018, ROC-AUC 0.9844,
  precision 0.2216, recall 0.9738, F1 0.3610 at threshold 0.5.
- Artifacts saved to `models/` (Git-ignored); metrics report at `reports/model_baseline.md`.
- Added `tests/unit/test_training.py` (4) and `tests/integration/test_training_smoke.py` (1).
- Leakage check passes (no identifiers/target/split key/transaction fields in features).

## Gate 8 — Purchase-conversion model training and evaluation (2026-10-27)

- Created `reports/decision_log.md` recording Gates 0–5 decisions, label definition,
  duplicate session key deduplication, partial quarter limitations, and full feature table
  with "available at prediction time" classifications and leakage exclusions.
- Refactored `src/analytics_ml/training/train.py` to a 3-way chronological split:
  - Train: 2016-08-01 -> 2017-03-31 (`date < 20170401`; 632,648 rows, 7,476 positives, 1.1817% prevalence).
  - Validation: 2017-04-01 -> 2017-06-30 (`20170401 <= date < 20170701`; 195,844 rows, 2,986 positives, 1.5247% prevalence).
  - Test: 2017-07-01 -> 2017-08-01 (`date >= 20170701`; 74,263 rows, 1,067 positives, 1.4368% prevalence).
- Imbalance strategy: `class_weight='balanced'` in LogisticRegression baseline.
- Compared against `HistGradientBoostingClassifier` on the validation set (Val PR-AUC 0.4906 vs 0.3871).
  Retained Logistic Regression as default serving baseline for inference latency and simplicity.
- Evaluated probability calibration using `CalibratedClassifierCV` (sigmoid) with `FrozenEstimator`.
- Test set performance (threshold = 0.5): PR-AUC 0.4026, ROC-AUC 0.9838, Precision 0.2278, Recall 0.9691, F1 0.3688.
- Reproducibility verified: identical metrics produced across independent runs.
- Saved versioned artifacts to `models/` (Git-ignored): `baseline_logreg.joblib`, `feature_schema.json`,
  `feature_list.json`, `split_details.json`, `metrics.json`, `model_metadata.json`.
- Updated `reports/model_baseline.md`.
- Expanded unit and integration tests: 8 unit tests + 1 integration smoke test; full test suite passes (67 passed).

## Gate 9 — BentoML prediction API (2026-10-27)

- Implemented and finalized `services/prediction/service.py`:
  - `ConversionService` serving `models/baseline_logreg.joblib`.
  - Pydantic models `PredictionRequest` and `PredictionResponse` enforcing schema matching `models/feature_schema.json`.
  - Strict input validation: non-empty strings for categoricals, non-negative counts for hits/pageviews/time_on_site, `visitNumber >= 1`.
  - Correlation tracking via UUID4 `request_id` on every prediction.
  - Safe structured logging: latency in ms, predicted class, and probability recorded without logging raw sensitive payloads.
  - `health` endpoint reporting service readiness and active model version.
- Created `services/prediction/client.py` demonstrating sample low-intent and high-intent requests.
- Created automated test coverage:
  - `tests/unit/test_prediction_service.py` (6 unit tests: valid payload, empty string rejection, negative bounds rejection, missing field rejection, missing model error, predict and health).
  - `tests/integration/test_prediction_service_smoke.py` (integration test validating prediction against real model artifact).
- Wrote API specification and usage guide at `reports/prediction_api.md`.
- Verified: all 74 repository tests pass (`pytest -q`), `pip check` clean.

## Gate 10 — Drift and model-quality monitoring (2026-10-27)

- Implemented `src/analytics_ml/monitoring/drift_detector.py`:
  - Statistical data drift engine: 2-sample Kolmogorov-Smirnov test and Wasserstein distance for continuous features; Jensen-Shannon divergence for categoricals.
  - Dataset drift rule: declared when >= 30% of features exhibit drift.
  - Model quality / concept drift: evaluates F1 degradation (>15% drop from baseline 0.3688) when ground-truth labels are present; explicitly returns `concept_drift_status = "labels_pending"` when labels are absent or delayed.
- Implemented `src/analytics_ml/monitoring/synthetic_drift.py`:
  - Deterministic normal and shifted batch generation (mobile surge scenario: 85% mobile, suppressed time on site and hits).
  - Delayed-label stream generator simulating arrival of ground truth outcomes.
  - Mandatory provenance flag: all synthetic records strictly marked `is_simulated = True`.
- Updated `config/drift.yaml` with reference window, sample size requirements, and statistical thresholds.
- Created automated test coverage:
  - `tests/unit/test_drift_detector.py` (9 unit tests: numeric KS drift, categorical JS drift, identical distribution stability, shifted synthetic batch detection, concept drift pending state, concept drift evaluation, simulation flags).
  - `tests/integration/test_drift_smoke.py` (end-to-end drift pipeline execution against DuckLake reference data and holdout sets).
- Generated monitoring report at `reports/drift_monitoring.md`.
- Verified: all 84 repository tests pass (`pytest -q`), `pip check` clean.

## Gate 11 — Prometheus and Grafana (2026-10-27)

- Implemented `src/analytics_ml/monitoring/metrics_exporter.py`:
  - `DriftMetricsManager` registering gauges for `model_data_drift_detected`, `model_drift_share`, `model_drifted_features_count`, `model_feature_drift`, `model_concept_drift_status`, `model_batch_f1_score`, and `model_batch_pr_auc_score`.
  - Strictly enforced bounded cardinality (never visitor IDs, session IDs, or PII).
  - Populates gauges directly from `DriftDetector` output summaries and exports standard Prometheus exposition text.
- Configured Prometheus scrape job `drift_monitoring` in `monitoring/prometheus/prometheus.yml`.
- Created declarative Grafana dashboard at `monitoring/grafana/dashboards/drift_monitoring.json` with panels for drift status, gauge counts, per-feature breakdown table, and F1 performance.
- Created declarative Grafana alerting rules at `monitoring/grafana/provisioning/alerting/alert_rules.yaml` linking alerts to the local approval UI (`http://127.0.0.1:8000/approvals/pending`).
- Created automated tests:
  - `tests/unit/test_metrics_exporter.py` (4 unit tests: metric registry, bounded labels, data drift updates, evaluated concept drift updates).
  - `tests/integration/test_monitoring_stack_smoke.py` (4 integration tests: prometheus.yml syntax, dashboard JSON schema, alert rules YAML, docker-compose syntax).
- Generated monitoring guide at `reports/prometheus_grafana.md`.
- Verified: all 92 repository tests pass (`pytest -q`), `pip check` clean.

## Gate 12 — Approval API & local UI (2026-10-27)

- Implemented domain models in `src/analytics_ml/approval/models.py`:
  - `ApprovalState` (`PENDING`, `APPROVED`, `REJECTED`, `EXPIRED`).
  - `ApprovalRecord`, `DecisionRequest`, `DecisionResponse`.
- Implemented durable SQLite store in `src/analytics_ml/approval/store.py`:
  - Atomic transactions against `warehouse/approvals.db`.
  - Enforced valid state transitions (`PENDING` -> `APPROVED` / `REJECTED`).
  - Idempotent decision replay based on idempotency keys.
  - Expiration detection (default 24h).
  - DAG allowlist enforcement (`DAG_ALLOWLIST = {"approved_retraining"}`).
  - Generates secure `authorized_run_id` upon approval.
- Implemented FastAPI service and UI in `services/approval/app.py`:
  - `GET /health`: Health and schema status.
  - `GET /approvals/pending`: Pending requests (JSON API and responsive dark-mode HTML console).
  - `GET /approvals/{id}`: Detailed approval inspection.
  - `POST /approvals/{id}/decision`: Decision endpoint for approval/rejection.
  - `POST /approvals/requests`: Ingestion endpoint for drift alerts.
- Created automated test coverage:
  - `tests/unit/test_approval_service.py` (7 tests: creation, transitions, invalid transition error, idempotency, expiration, unknown DAG rejection, health).
  - `tests/integration/test_approval_service_smoke.py` (3 tests: health, pending flow + HTML UI, reject prevents approval).
- Generated specification report at `reports/approval_service.md`.
- Verified: all 102 repository tests pass (`pytest -q`), `pip check` clean.

## Gate 13 — Airflow Retraining Pipeline & Governance (2026-10-27)

- Implemented `src/analytics_ml/retraining/pipeline.py`:
  - `RetrainingConfig`: Governs execution parameters, thresholds (min PR-AUC 0.35, min F1 0.30, max drop 0.05), and paths.
  - `RetrainingEngine`: Encapsulates authorization checking, token consumption, DuckLake mart row count verification, candidate training, evaluation against active model, and safe promotion with atomic backup (`models/baseline_logreg_backup.joblib`).
  - Added `consumed_approvals` table in `ApprovalStore` (`warehouse/approvals.db`) and methods `verify_authorization` and `consume_authorization` to ensure single-use tokens and prevent replay attacks.
- Implemented Airflow DAG in `dags/approved_retraining_dag.py`:
  - Enforced `dag_id="approved_retraining"`, `schedule_interval=None`, `max_active_runs=1`, and `retries=0`.
  - Task sequence: `verify_authorization` -> `consume_authorization` -> `validate_data_batch` -> `execute_retraining` -> `record_audit`.
  - Rejects any manual trigger lacking valid human approval credentials.
- Created automated test coverage:
  - `tests/unit/test_retraining_pipeline.py` (6 unit tests: unapproved/pending/rejected rejection, run ID mismatch, replay prevention via token consumption, candidate gate pass/fail evaluation, atomic backup on promotion, full engine execution).
  - `tests/unit/test_retraining_dag.py` (4 unit tests: DAG AST/syntax and invariant checks, unapproved manual trigger rejection, credential verification, token consumption).
  - `tests/integration/test_retraining_smoke.py` (1 integration test executing the complete retraining flow against the 902,755-row DuckLake catalog, validating reject scenarios, approval execution, candidate promotion, and replay rejection).
- Generated specification report at `reports/airflow_retraining.md`.
- Verified: all 113 repository tests pass (`pytest -q`), `pip check` clean.

## Gate 14 — End-to-End Demonstration Scenario (2026-10-27)

- Implemented automated end-to-end integration scenario in `tests/e2e/test_end_to_end_scenario.py`:
  - Verified 7 lifecycle stages in a sandboxed, isolated environment:
    1. Active baseline prediction and health verification via `ConversionService`.
    2. Ingestion of normal simulated batch (`is_simulated = True`) confirming zero drift and zero false alerts.
    3. Ingestion of shifted mobile-surge traffic batch triggering covariate drift on 5 features (`hits`, `pageviews`, `time_on_site`, `device_category`, `operating_system`) and alerting.
    4. Human rejection gate: simulated operator records `REJECT`, preventing unauthorized Airflow execution (`PermissionError`).
    5. Human approval gate: persistent shift approved, issuing single-use `authorized_run_id`.
    6. Airflow retraining pipeline execution: validates authorization, consumes token, trains candidate, passes quality gate, backs up active model (`models/baseline_logreg_backup.joblib`), promotes candidate model, and logs audit record.
    7. Replay defense check (re-using consumed token strictly blocked) and post-promotion zero-downtime serving verification.
- Implemented standalone demonstration script in `scripts/run_e2e_demo.py` providing rich terminal walkthrough of the full pipeline for stakeholders and evaluators.
- Generated demonstration report at `reports/end_to_end_demo.md`.
- Verified: `scripts/run_e2e_demo.py` passes end-to-end; all 114 tests pass (`pytest -q`), `pip check` clean.

## Gate 15 — Final Handover & Repository Polish (2026-10-27)

- Upgraded `README.md`:
  - Complete ASCII architecture diagram detailing data flow and governance loops.
  - Comprehensive service directory and port map (`127.0.0.1:3000` through `9090`).
  - Clear quickstart, installation, and testing instructions.
  - Architectural decision summaries (DuckLake, 3-way split, drift engine, human governance, Airflow safety).
- Finalized repository hygiene and security:
  - Verified `.gitignore` ignores all database files (`warehouse/`), model binaries (`models/`), raw data (`data/`), and runtime audit trails (`reports/retraining_audit.json`).
  - Executed secret scan across the repository: zero secrets, keys, or credentials detected.
  - Verified `pip check` clean.
- Generated final handover report at `reports/final_handover.md`:
  - Gate-by-gate delivery scorecard for all 16 gates (Gate 0 through 15).
  - Metric scorecard: PR-AUC 0.4026, ROC-AUC 0.9838, Recall 0.9691, F1 0.3688.
  - Production evolution recommendations (distributed Lakehouse, feature store, Kubernetes deployment, IAM/SSO).
- Verified: all 114 tests pass (`pytest -v`), 100% green.

## Project Status

**COMPLETE.** All 16 gates (Gate 0 through Gate 15) successfully implemented, tested, verified, and documented.




