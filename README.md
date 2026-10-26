# Local Analytics-to-ML Drift Monitoring Platform

> **Non-production proof of concept.** This is a local-first data engineering and MLOps learning project. It is not intended for production deployment or exposure beyond localhost.

## Purpose

This project demonstrates an end-to-end pipeline that:
- Obtains a public Google Analytics sample dataset through a verified no-cost path
- Stores and transforms it with DuckDB/DuckLake (primary) and Apache Iceberg (interoperability demonstration)
- Builds a leakage-safe session-level purchase conversion dataset
- Trains a baseline scikit-learn model and serves predictions via BentoML (localhost only)
- Monitors data drift vs concept/model-quality drift with Prometheus and Grafana
- Enforces human approval before any retraining via a local approval interface, with Airflow executing only approved runs
- Supports historical reprocessing and clearly labeled simulated batches/drift

See CONTEXT.md for detailed principles and IMPLEMENTATION_GUIDE.md for the staged plan.

## Prerequisites (tested)
- Windows 11 with Docker Desktop + WSL2 recommended
- Python 3.12.x
- Docker Desktop with Docker Compose v2 (tested: Docker 29.8.0, Compose v5.5.1)
- WSL2 (tested: 2.7.10.0)
- Git (tested: 2.54.0.windows.1)

Resource notes (as detected):
- ~16 GB RAM, ~8 logical CPUs, ~71 GB free disk space (POC is CPU-friendly)


## Data provenance
Dataset source: bigquery-public-data.google_analytics_sample.ga_sessions_* (Google Analytics public sample). A direct static download is not guaranteed. Acquisition path, license/terms, retrieval date, checksums, and schema must be documented in Stage 1.

## Status
Stage 0 complete; Stage 1 complete; implementation follows approval gates per CONTEXT.md.


## Split strategy
Quarterly/yearly splits by session date/visitStartTime (to detect drift across periods). Session-level purchase conversion as target.


## Notebooks
Exploratory and reproducible workflows live in 
notebooks/ (e.g. 01_download_ga_sessions.ipynb). Outputs cleared before commit.


## Folder purpose
- config/: non-sensitive runtime configs (app, drift)
- data/: raw/interim/processed/simulated (gitignored; raw immutable)
- dags/: Airflow DAGs
- monitoring/: Prometheus/Grafana configs
- notebooks/: reproducible exploration/workflows (numbered)
- reports/: generated reports, provenance, plans (tracked)
- services/: prediction/approval services
- src/analytics_ml/: core modules (ingestion, lakehouse, features, training, monitoring, approval, common)
- tests/: unit/integration/e2e
- warehouse/: local DuckDB/DuckLake/catalogs (gitignored)

