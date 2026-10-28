# Approval Service & Control-Plane Guide (Gate 12)

Human governance and control-plane API built on **FastAPI**, mediating between Grafana drift alerts and Airflow retraining runs.

---

## 1. Governance Principles

1. **Explicit Human Authorization:** Grafana alerts never trigger retraining automatically. Acknowledging an alert or opening a webhook is not approval. Retraining requires a deliberate `POST` decision from an authorized human operator.
2. **Control-Plane vs Data-Plane Separation:**
   - **Data-Plane (BentoML, port 3001):** High-throughput, low-latency prediction serving.
   - **Control-Plane (FastAPI, port 8000):** Administrative approval management and orchestration trigger authorization.
3. **DAG Allowlist & Security:**
   - Arbitrary DAG triggering is strictly blocked. Only `approved_retraining` is allowlisted.
   - The service binds strictly to `127.0.0.1:8000` (localhost only).
4. **Idempotency & Replay Protection:**
   - Duplicate submissions with identical `idempotency_key` return the existing decision without re-triggering Airflow.
   - Once finalized (`APPROVED` or `REJECTED`), a request cannot be altered.

---

## 2. State Machine

```text
       [ Grafana Drift Alert ]
                  |
                  v
       +--------------------+
       |      PENDING       |
       +--------------------+
         /        |       \
(approve)         |        (reject)
       /     (TTL expires)   \
      v           |           v
+----------+      v      +----------+
| APPROVED |  +---------+| REJECTED |
+----------+  | EXPIRED |+----------+
              +---------+
```

---

## 3. Endpoints

### 3.1. Health Check
- **Route:** `GET /health`
- **Response:** `{"status": "ok", "service": "approval_control_plane"}`

### 3.2. List Pending Approvals
- **Route:** `GET /approvals/pending`
- **JSON API Response (`Accept: application/json`):** Array of pending `ApprovalRecord` objects.
- **HTML UI (`Accept: text/html`):** Dark-mode operator dashboard rendering table of pending alerts with deliberate "Approve" and "Reject" buttons.

### 3.3. Request Detail
- **Route:** `GET /approvals/{approval_id}`
- **Response:** Full `ApprovalRecord` including trigger reason, model version, evidence summary, and expiration timestamp.

### 3.4. Record Decision
- **Route:** `POST /approvals/{approval_id}/decision`
- **Payload (`application/json` or Form):**
  ```json
  {
    "decision": "approve",
    "decided_by": "lead_mlops_engineer",
    "decision_reason": "Verified mobile surge is legitimate promotion; authorizing retraining",
    "idempotency_key": "appr-123-decision-1"
  }
  ```
- **Response (200 OK):**
  ```json
  {
    "approval_id": "appr-123",
    "state": "APPROVED",
    "decision": "approve",
    "decided_by": "lead_mlops_engineer",
    "decided_at_utc": "2026-10-27T10:48:33Z",
    "authorized_run_id": "run-approved-a1b2c3d4-1798368513",
    "message": "Retraining authorized for DAG 'approved_retraining'. Run ID: run-approved-a1b2c3d4-1798368513"
  }
  ```

---

## 4. Local Startup Command

```powershell
.\.venv\Scripts\uvicorn.exe services.approval.app:app --host 127.0.0.1 --port 8000
```
- Web UI: [http://127.0.0.1:8000/approvals/pending](http://127.0.0.1:8000/approvals/pending)
- OpenAPI Documentation: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
