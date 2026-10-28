# Prometheus & Grafana Monitoring Guide (Gate 11)

Technical guide for metrics scraping, Grafana dashboards, and drift alerting rules.

---

## 1. Metrics Architecture & Cardinality Control

All metrics are exposed via standard Prometheus text format (`prometheus_client`) and enforce **bounded cardinality**:
- **Allowed label dimensions:** `model_version`, `feature`, `method`, `status`.
- **Forbidden dimensions:** Any unique identifier (`fullVisitorId`, `visitId`, request payload, raw URLs, PII).

### Exported Metrics Summary

| Metric Name | Type | Labels | Description |
|---|---|---|---|
| `model_data_drift_detected` | Gauge | `model_version` | 1 if overall dataset data drift is detected (drift share >= 30%), 0 otherwise. |
| `model_drift_share` | Gauge | `model_version` | Ratio of features exhibiting statistical drift [0.0, 1.0]. |
| `model_drifted_features_count` | Gauge | `model_version` | Count of individual features with statistically significant drift ($p < 0.05$ or $JS > 0.15$). |
| `model_feature_drift` | Gauge | `feature`, `method`, `model_version` | Binary flag (1 = drifted, 0 = stable) for each individual feature. |
| `model_concept_drift_status` | Gauge | `model_version` | 0 = `labels_pending`, 1 = `evaluated_healthy`, 2 = `evaluated_degraded`. |
| `model_batch_f1_score` | Gauge | `model_version` | F1 score evaluated on observed ground-truth labels. |
| `model_batch_pr_auc_score` | Gauge | `model_version` | PR-AUC (average precision) evaluated on observed ground-truth labels. |
| `model_prediction_requests_total` | Counter | `model_version`, `status` | Cumulative inference requests served. |
| `model_prediction_latency_seconds` | Summary | `model_version` | Request latency distribution in seconds. |

---

## 2. Declarative Provisioning

### 2.1. Prometheus Scraping (`monitoring/prometheus/prometheus.yml`)
- Scrapes Prometheus internal metrics on `127.0.0.1:9090`.
- Scrapes prediction service on `127.0.0.1:3001` (or `host.docker.internal:3001`).
- Scrapes drift metrics exporter on `127.0.0.1:8001` (or `host.docker.internal:8001`).
- Scrapes approval service on `127.0.0.1:8000` (or `host.docker.internal:8000`).

### 2.2. Grafana Dashboard (`monitoring/grafana/dashboards/drift_monitoring.json`)
Auto-loaded upon Grafana startup from `/var/lib/grafana/dashboards`:
- **Data Drift Status Panel:** Stat panel showing red `DRIFT DETECTED` or green `NO DRIFT`.
- **Drifted Features Count & Share Panels:** Visual gauges with yellow and red threshold indicators.
- **Per-Feature Drift Table:** Displays individual feature drift status and statistical test methods.
- **Concept Drift & Performance Panels:** Tracks `model_concept_drift_status` (Pending/Healthy/Degraded) and batch F1 score.

### 2.3. Alert Rules (`monitoring/grafana/provisioning/alerting/alert_rules.yaml`)
- **`ModelDataDriftAlert`:** Firing when `model_data_drift_detected == 1` for 30s.
- **`ModelConceptDriftAlert`:** Firing when `model_concept_drift_status == 2` for 30s.
- **Human Approval Bridge:** Alert annotations include a direct link to the local approval UI:
  `http://127.0.0.1:8000/approvals/pending?alert_id=alert-data-drift-detected`.
- Alert firing **does not automatically trigger retraining**; it requires explicit human review and authorization through the approval interface.

---

## 3. Running Locally

### 3.1. Test Metrics Exporter Output
```powershell
.\.venv\Scripts\python.exe -m analytics_ml.monitoring.metrics_exporter
```

### 3.2. Start Prometheus & Grafana via Docker Compose
```powershell
docker compose up -d prometheus grafana
```
- Prometheus UI: [http://127.0.0.1:9090](http://127.0.0.1:9090)
- Grafana UI: [http://127.0.0.1:3000](http://127.0.0.1:3000) (Default user: `admin`, password: `admin`)
