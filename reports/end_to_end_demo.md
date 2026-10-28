# End-to-End MLOps Demonstration Scenario (Gate 14)

## 1. Executive Summary

This report documents the end-to-end verification of the local-first MLOps proof of concept on the Google Analytics dataset.

The demonstration links all components built across Gates 0–13 into an automated, reproducible feedback loop:
1. **Serving Baseline:** BentoML prediction service serves inferences using `models/baseline_logreg.joblib`.
2. **Normal Data Flow:** Ingestion of normal simulated traffic verifies metric stability without spurious alerts.
3. **Data Drift Event:** Ingestion of a simulated mobile traffic surge flags covariate drift ($\ge 30\%$ drifted features) via 2-sample Kolmogorov-Smirnov and Jensen-Shannon tests.
4. **Human Rejection Gate:** Simulated on-call engineer reviews evidence and rejects spurious/temporary shift; Airflow retraining DAG is strictly blocked from executing.
5. **Human Approval Gate:** Persistent structural shift is approved by senior lead engineer, issuing a cryptographic single-use token (`authorized_run_id`).
6. **Airflow Retraining & Promotion:** Retraining pipeline validates authorization, consumes token, trains candidate model, validates performance on holdout data, and safely promotes candidate with an atomic backup.
7. **Serving Hot-Reload & Replay Defense:** Prediction service serves from the promoted model with zero downtime; replaying the consumed authorization token is rejected.

---

## 2. Seven-Step Demonstration Lifecycle

```text
Step 1: Baseline Inference & Service Health Check
        [BentoML Service: OK, Model: baseline-logreg-v1]
                           │
                           ▼
Step 2: Normal Batch Processing (500 samples, is_simulated=True)
        [Drift: 0/13 features (0.0%), model_data_drift_detected=0, Alerts=0]
                           │
                           ▼
Step 3: Shifted Traffic Surge (Mobile Surge, 85% mobile)
        [Drift: 4/13 features (30.8%) [ALERT], model_data_drift_detected=1]
                           │
                           ▼
Step 4: Human Rejection Gate
        [Operator records REJECT -> State: REJECTED, authorized_run_id: None]
        [Airflow Retraining Attempt -> FAILS IMMEDIATELY (PermissionError)]
                           │
                           ▼
Step 5: Structural Shift & Human Approval Authorization
        [Operator records APPROVE -> State: APPROVED, authorized_run_id: run-approved-...]
                           │
                           ▼
Step 6: Airflow Approved Retraining & Candidate Evaluation Gate
        [Task 1: verify_authorization -> PASSED]
        [Task 2: consume_authorization -> TOKEN CONSUMED]
        [Task 3: validate_data_batch -> 902,755 rows in DuckLake]
        [Task 4: execute_retraining -> Candidate PR-AUC: 0.4026, F1: 0.3688]
        [Task 5: promote_candidate -> Backup active model -> Overwrite active model]
                           │
                           ▼
Step 7: Post-Promotion Verification & Replay Defense
        [Serving hot-reload: OK]
        [Replay attempt with consumed token -> FAILS (PermissionError)]
```

---

## 3. Step-by-Step Execution Evidence

### Step 1: Active Baseline Inference
- **Health Check:** `GET /health` returns `status: "ok"`, `model_version: "baseline-logreg-v1"`.
- **Sample Prediction:** Low-intent desktop visitor scored `0.1648` conversion probability with latency `52.91 ms` and correlation `request_id: ccb546ee-fe74-4728-9820-1188495bc834`.

### Step 2: Normal Traffic Ingestion
- Batch size: 500 records sampled from validation holdout, tagged with `is_simulated = True`.
- Results:
  - Dataset Drift Detected: `False`
  - Drift Share: `0.0%` ($0 / 13$ features drifted)
  - Prometheus Gauge `model_data_drift_detected`: `0`
  - Pending Approval Requests: `0`

### Step 3: Shifted Traffic Ingestion (Mobile Surge Scenario)
- Batch size: 500 records with 85% mobile devices, suppressed `time_on_site` (down 60%) and clipped `hits`.
- Results:
  - Dataset Drift Detected: `True`
  - Drift Share: `30.8%` ($4 / 13$ features drifted: `device_category`, `operating_system`, `hits`, `time_on_site`)
  - Prometheus Gauge `model_data_drift_detected`: `1`
  - Alert generated and posted to `POST /approvals/requests`.

### Step 4: Human Rejection Gate
- Scenario: Operator identifies alert as a temporary 1-day flash marketing promo.
- Operator action: `POST /approvals/{id}/decision` with `{"decision": "reject", "decided_by": "on-call-data-engineer"}`.
- Outcome:
  - Approval state transitions to `REJECTED`.
  - `authorized_run_id`: `None`.
  - Attempting to invoke Airflow retraining raises `PermissionError: Retraining unauthorized: Approval request is in state 'REJECTED', not APPROVED`.
  - Active model `models/baseline_logreg.joblib` remains untouched.

### Step 5: Legitimate Alert & Human Approval
- Scenario: Multi-day persistent shift confirms structural expansion in mobile user base.
- Operator action: `POST /approvals/{id}/decision` with `{"decision": "approve", "decided_by": "senior-lead-engineer"}`.
- Outcome:
  - Approval state transitions to `APPROVED`.
  - Issued token: `authorized_run_id: run-approved-a1b2c3d4-1798368513`.

### Step 6: Approved Retraining, Evaluation Gate & Safe Promotion
- Orchestrator invokes `RetrainingEngine` with `approval_id` and `authorized_run_id`:
  1. `verify_authorization`: Validates approval credentials against `warehouse/approvals.db`.
  2. `consume_authorization`: Atomically writes to `consumed_approvals` table.
  3. `validate_batch_quality`: Confirms 902,755 clean rows in `dl.marts.fct_session_conversion`.
  4. `train_candidate`: Fits candidate `LogisticRegression(class_weight='balanced')`.
  5. `evaluate_candidate`: Candidate achieves validation PR-AUC $0.4026$, F1 $0.3688$, meeting all quality gates.
  6. `promote_candidate`:
     - Creates atomic backup: `models/baseline_logreg_backup.joblib`.
     - Overwrites production model: `models/baseline_logreg.joblib`.
     - Writes updated lineage to `models/model_metadata.json` and metrics to `models/metrics.json`.
  7. `record_audit`: Appends execution record to `reports/retraining_audit.json`.

### Step 7: Serving Hot-Reload & Replay Defense
- **Zero-Downtime Serving:** `ConversionService` hot-reloads the newly promoted model and serves new inferences immediately.
- **Replay Attack Defense:** Running a second retraining execution using the same `authorized_run_id` fails:
  `PermissionError: Approval request with run ID was already consumed`.

---

## 4. How to Reproduce Locally

### Automated Test Suite:
```powershell
.venv\Scripts\pytest tests/e2e/test_end_to_end_scenario.py -v
```

### Standalone Interactive Demo Runner:
```powershell
.venv\Scripts\python scripts/run_e2e_demo.py
```
