"""Integration smoke test for FastAPI approval service endpoints (Gate 12)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from services.approval.app import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_health_endpoint(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_approval_lifecycle_api_flow(client: TestClient) -> None:
    # 1. Create a pending request
    payload = {
        "alert_id": "test-alert-drift-42",
        "target_dag_id": "approved_retraining",
        "model_version": "baseline-logreg-v1",
        "trigger_reason": "Mobile surge detected",
        "evidence_summary": {"drift_share": 0.69},
        "ttl_minutes": 30,
    }
    create_resp = client.post("/approvals/requests", json=payload)
    assert create_resp.status_code == 201
    created_data = create_resp.json()
    approval_id = created_data["approval_id"]
    assert created_data["state"] == "PENDING"

    # 2. Verify it appears in pending list
    pending_resp = client.get("/approvals/pending", headers={"Accept": "application/json"})
    assert pending_resp.status_code == 200
    pending_ids = [r["approval_id"] for r in pending_resp.json()]
    assert approval_id in pending_ids

    # 3. Verify HTML dashboard renders
    html_resp = client.get("/approvals/pending", headers={"Accept": "text/html"})
    assert html_resp.status_code == 200
    assert "MLOps Retraining Approval Console" in html_resp.text
    assert approval_id in html_resp.text

    # 4. Detail endpoint
    detail_resp = client.get(f"/approvals/{approval_id}")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["approval_id"] == approval_id

    # 5. Submit Approve decision
    decide_payload = {
        "decision": "approve",
        "decided_by": "qa_engineer",
        "decision_reason": "Verified shift is valid marketing campaign",
        "idempotency_key": f"{approval_id}-idem-key-1",
    }
    decide_resp = client.post(
        f"/approvals/{approval_id}/decision",
        json=decide_payload,
        headers={"Content-Type": "application/json"},
    )
    assert decide_resp.status_code == 200
    decision_data = decide_resp.json()
    assert decision_data["state"] == "APPROVED"
    assert decision_data["authorized_run_id"] is not None
    assert decision_data["authorized_run_id"].startswith("run-approved-")

    # 6. Idempotent re-submission
    replay_resp = client.post(
        f"/approvals/{approval_id}/decision",
        json=decide_payload,
        headers={"Content-Type": "application/json"},
    )
    assert replay_resp.status_code == 200
    assert replay_resp.json()["authorized_run_id"] == decision_data["authorized_run_id"]

    # 7. Conflicting decision fails with 409 Conflict
    conflict_payload = {
        "decision": "reject",
        "decided_by": "other_operator",
        "decision_reason": "Trying to reject already approved",
        "idempotency_key": f"{approval_id}-conflict",
    }
    conflict_resp = client.post(
        f"/approvals/{approval_id}/decision",
        json=conflict_payload,
        headers={"Content-Type": "application/json"},
    )
    assert conflict_resp.status_code == 409


def test_nonexistent_approval_returns_404(client: TestClient) -> None:
    resp = client.get("/approvals/appr-doesnotexist")
    assert resp.status_code == 404
