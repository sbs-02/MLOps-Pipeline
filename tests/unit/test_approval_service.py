"""Unit tests for the approval domain model, store, and state transitions (Gate 12)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from analytics_ml.approval.models import ApprovalState, DecisionRequest, DecisionType
from analytics_ml.approval.store import ApprovalStore


@pytest.fixture
def temp_store() -> ApprovalStore:
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_approvals.db"
        yield ApprovalStore(db_path=db_path)


def test_create_and_get_approval_request(temp_store: ApprovalStore) -> None:
    rec = temp_store.create_request(
        alert_id="alert-drift-001",
        target_dag_id="approved_retraining",
        model_version="baseline-logreg-v1",
        trigger_reason="Drift share > 30%",
        evidence_summary={"drift_share": 0.61},
    )

    assert rec.approval_id.startswith("appr-")
    assert rec.state == ApprovalState.PENDING
    assert rec.target_dag_id == "approved_retraining"

    fetched = temp_store.get_request(rec.approval_id)
    assert fetched is not None
    assert fetched.approval_id == rec.approval_id
    assert fetched.evidence_summary["drift_share"] == 0.61


def test_create_rejects_non_allowlisted_dag(temp_store: ApprovalStore) -> None:
    with pytest.raises(ValueError, match="not permitted"):
        temp_store.create_request(
            alert_id="alert-rogue-001",
            target_dag_id="arbitrary_unauthorized_dag",
        )


def test_approve_transition_generates_authorized_run_id(temp_store: ApprovalStore) -> None:
    rec = temp_store.create_request(alert_id="alert-data-drift")

    req = DecisionRequest(
        decision=DecisionType.APPROVE,
        decided_by="senior_engineer",
        decision_reason="Reviewed drift report and verified covariate shift",
        idempotency_key="key-001",
    )

    resp = temp_store.record_decision(rec.approval_id, req)
    assert resp.state == ApprovalState.APPROVED
    assert resp.authorized_run_id is not None
    assert resp.authorized_run_id.startswith("run-approved-")

    # Verify state in store
    updated = temp_store.get_request(rec.approval_id)
    assert updated.state == ApprovalState.APPROVED
    assert updated.authorized_run_id == resp.authorized_run_id


def test_reject_transition_prevents_run_authorization(temp_store: ApprovalStore) -> None:
    rec = temp_store.create_request(alert_id="alert-false-alarm")

    req = DecisionRequest(
        decision=DecisionType.REJECT,
        decided_by="senior_engineer",
        decision_reason="Transient anomaly due to scraping glitch",
        idempotency_key="key-002",
    )

    resp = temp_store.record_decision(rec.approval_id, req)
    assert resp.state == ApprovalState.REJECTED
    assert resp.authorized_run_id is None

    updated = temp_store.get_request(rec.approval_id)
    assert updated.state == ApprovalState.REJECTED
    assert updated.authorized_run_id is None


def test_idempotent_replay_returns_cached_decision(temp_store: ApprovalStore) -> None:
    rec = temp_store.create_request(alert_id="alert-drift-replay")
    req = DecisionRequest(
        decision=DecisionType.APPROVE,
        decided_by="operator",
        decision_reason="Approving",
        idempotency_key="replay-key-123",
    )

    resp1 = temp_store.record_decision(rec.approval_id, req)
    resp2 = temp_store.record_decision(rec.approval_id, req)

    assert resp1.authorized_run_id == resp2.authorized_run_id
    assert "Idempotent replay" in resp2.message


def test_conflicting_decision_on_finalized_request_fails(temp_store: ApprovalStore) -> None:
    rec = temp_store.create_request(alert_id="alert-drift-conflict")
    req_approve = DecisionRequest(
        decision=DecisionType.APPROVE,
        decided_by="operator1",
        decision_reason="First",
        idempotency_key="first-key",
    )
    temp_store.record_decision(rec.approval_id, req_approve)

    req_reject = DecisionRequest(
        decision=DecisionType.REJECT,
        decided_by="operator2",
        decision_reason="Second contradictory decision",
        idempotency_key="second-key",
    )

    with pytest.raises(ValueError, match="already in terminal state"):
        temp_store.record_decision(rec.approval_id, req_reject)


def test_expired_request_cannot_be_approved(temp_store: ApprovalStore) -> None:
    # TTL negative creates already expired request
    rec = temp_store.create_request(alert_id="alert-expired", ttl_minutes=-10)

    # get_request updates state to EXPIRED
    fetched = temp_store.get_request(rec.approval_id)
    assert fetched.state == ApprovalState.EXPIRED

    req = DecisionRequest(
        decision=DecisionType.APPROVE,
        decided_by="operator",
        decision_reason="Too late",
        idempotency_key="expired-key",
    )

    with pytest.raises(ValueError, match="has expired"):
        temp_store.record_decision(rec.approval_id, req)
