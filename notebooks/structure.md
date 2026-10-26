# Notebooks (directory structure)
- 01_download_ga_sessions.ipynb -> acquire raw data, record provenance (source, date, license, checksums), save to data/raw/
- 02_ingest_schema_inspect.ipynb -> inspect schema (nested/repeated), generate reports/schema_quality_*.md, create/verify the DuckLake raw table (idempotent), reconcile raw vs lake, record DuckDB/DuckLake versions
- 03_feature_prep_time_splits.ipynb -> build quarter/year based splits, label definition, leakage checks
- 04_train_baseline.ipynb -> baseline model training/evaluation (logistic regression, time-based split, metrics, artifacts)
- 05_drift_monitoring_setup.ipynb -> reference windows, drift configs
- others as needed, clearly named
