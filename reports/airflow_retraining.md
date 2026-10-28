# Airflow Retraining Pipeline & Governance Specification (Gate 13)

## 1. Executive Summary

This document describes the design, authorization gate, and execution mechanics of the **Airflow retraining pipeline** (`approved_retraining`), implementing Stage 8 / Gate 13 of the local-first MLOps proof of concept.

In accordance with `CONTEXT.md` and `IMPLEMENTATION_GUIDE.md`:
- **No Automatic Retraining:** Firing Grafana drift alerts or webhook receipts never directly initiate retraining. Retraining requires explicit human authorization through the control-plane approval service.
- **Strict Single-Use Authorization:** The Airflow DAG extracts credentials from `dag_run.conf` (`approval_id` and `authorized_run_id`). Manual unauthenticated runs abort immediately before accessing data or compute. Each authorization token is atomically marked consumed to prevent replay attacks.
- **Candidate Evaluation Gate:** Retrained candidate models are evaluated against the validation partition. If PR-AUC or F1 drops below safety tolerances, the candidate is rejected and the current production model remains untouched.
- **Atomic Promotion & Instant Rollback:** When candidate criteria are satisfied, the active model is automatically backed up to `models/baseline_logreg_backup.joblib` prior to atomic overwriting, ensuring continuous serving availability and instant rollback recovery.

---

## 2. Retraining Pipeline Architecture

```text
[Grafana Alert / Drift Detector]
              │
              ▼
[Approval Service (Gate 12)]
      State: PENDING
              │
       (Human Review)
              │
              ├── Reject ──────────► No Retraining (Terminal State)
              │
              └── Approve ─────────► Generates `authorized_run_id`
                                              │
                                              ▼
                             [Airflow Trigger with Credentials]
                                              │
                                              ▼
                         [Task 1: verify_authorization]
                                  Checks approval state,
                                  run ID, and expiration
                                              │
                                              ▼
                         [Task 2: consume_authorization]
                                  Atomically marks token
                                  consumed in SQLite
                                              │
                                              ▼
                         [Task 3: validate_data_batch]
                                  Verifies DuckLake mart
                                  row count and schema
                                              │
                                              ▼
                         [Task 4: execute_retraining]
                                  Train candidate model
                                  Evaluate on validation set
                                              │
                                  Candidate passes gate?
                                    /                \
                                 Yes                  No
                                  │                    │
                                  ▼                    ▼
                           Promote Model         Keep Active Model
                           (Backup old)          (Log Rejection)
                                  \                    /
                                   \                  /
                                    ▼                ▼
                                  [Task 5: record_audit]
                                  Appends run metadata to
                                  `retraining_audit.json`
```

---

## 3. Security & Safety Invariants

### 3.1 Unapproved Manual Trigger Rejection
If an operator triggers `approved_retraining` manually from the Airflow UI or CLI without providing valid credentials:
```python
task_verify_authorization()
# Raises: PermissionError("Retraining DAG rejected: missing 'approval_id' or 'authorized_run_id' in dag_run.conf.")
```
The task immediately fails in Task 1 without loading data, running dbt, or touching models.

### 3.2 Replay Attack Prevention
Authorization tokens are single-use. When Task 2 executes:
```sql
INSERT INTO consumed_approvals (approval_id, authorized_run_id, consumed_at_utc)
VALUES (?, ?, ?);
```
Any subsequent attempt to trigger a retraining run with the same credentials fails with:
`PermissionError: Approval request 'appr-xxx' with run ID 'run-xxx' was already consumed`.

### 3.3 Concurrency & Resource Isolation
- `max_active_runs = 1`: Strictly forbids concurrent execution of retraining pipelines, preventing race conditions on DuckLake tables and model artifact storage.
- `schedule_interval = None`: The DAG is never scheduled periodically; it only runs upon authorized external trigger.
- `retries = 0`: Authorization failures are deterministic security failures and are never retried.

---

## 4. Candidate Model Quality Gate

Candidate models are fitted on the training partition and evaluated against the validation holdout (`2017Q2`). A candidate is promoted if and only if:

| Quality Gate Criterion | Threshold | Rationale |
| :--- | :--- | :--- |
| **Minimum PR-AUC** | $\ge 0.3500$ | Prevents promotion of models with collapsed precision on imbalanced positive class (prevalence ~1.5%). |
| **Minimum F1 Score** | $\ge 0.3000$ | Ensures balanced trade-off between recall and precision at default decision threshold. |
| **Maximum PR-AUC Degradation** | $\le 0.0500$ drop vs active baseline | Prevents regression against existing production model (`models/baseline_logreg.joblib`). |

If any criterion fails:
1. Candidate model is discarded.
2. Active production model remains in place.
3. Outcome status is recorded as `REJECTED_EVALUATION_FAILED`.
4. Detailed diagnostics are logged in `reports/retraining_audit.json`.

---

## 5. Artifact Lifecycle & Promotion Safeguards

When promotion occurs:
1. `models/baseline_logreg.joblib` $\rightarrow$ copied to `models/baseline_logreg_backup.joblib`.
2. Candidate pipeline serialized to `models/baseline_logreg.joblib`.
3. `models/metrics.json` updated with candidate validation metrics.
4. `models/model_metadata.json` updated with timestamp, authorization IDs, and candidate lineage.

Rollback procedure:
```python
engine.rollback_to_backup()
# Instantly restores models/baseline_logreg_backup.joblib -> models/baseline_logreg.joblib
```

---

## 6. Audit Trail Format (`reports/retraining_audit.json`)

Each execution appends an immutable JSON record:
```json
{
  "status": "SUCCESS_PROMOTED",
  "approval_id": "appr-a1b2c3d4e5f6",
  "authorized_run_id": "run-approved-1798368513",
  "promoted": true,
  "candidate_metrics": {
    "pr_auc": 0.4026,
    "roc_auc": 0.9838,
    "precision": 0.2278,
    "recall": 0.9691,
    "f1": 0.3688
  },
  "active_metrics": {
    "pr_auc": 0.4026,
    "f1": 0.3688
  },
  "message": "Candidate successfully promoted. Candidate meets all quality gates: PR-AUC 0.4026 (active: 0.4026), F1 0.3688 (min: 0.3000)",
  "executed_at_utc": "2026-10-27T05:25:00.000000+00:00"
}
```

---

## 7. Verification Summary

- **Unit Tests:**
  - `tests/unit/test_retraining_pipeline.py`: 6 tests passing (authorization rejection, replay defense, candidate gate, atomic backup, full run).
  - `tests/unit/test_retraining_dag.py`: 4 tests passing (DAG syntax/structure, unauthorized trigger rejection, credential verification, token consumption).
- **Integration Tests:**
  - `tests/integration/test_retraining_smoke.py`: End-to-end retraining cycle against 902,755-row DuckLake catalog, validating reject scenarios, approval execution, candidate promotion, and replay rejection.
