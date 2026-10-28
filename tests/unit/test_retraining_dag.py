"""Unit tests verifying the structure and authorization safeguards of the Airflow retraining DAG (Gate 13)."""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from analytics_ml.approval.models import DecisionRequest, DecisionType
from analytics_ml.approval.store import ApprovalStore
from dags.approved_retraining_dag import (
    task_consume_authorization,
    task_record_audit,
    task_verify_authorization,
)

DAG_PATH = Path(__file__).resolve().parents[2] / "dags" / "approved_retraining_dag.py"


def test_dag_file_syntax_and_structure() -> None:
    """Verify that approved_retraining_dag.py parses cleanly and enforces required DAG parameters."""
    assert DAG_PATH.exists()
    content = DAG_PATH.read_text(encoding="utf-8")
    tree = ast.parse(content)
    assert tree is not None

    # Check key security invariants in DAG definition
    assert 'dag_id="approved_retraining"' in content
    assert "schedule_interval=None" in content
    assert "max_active_runs=1" in content
    assert '"retries": 0' in content


def test_task_verify_authorization_rejects_missing_credentials() -> None:
    """Manual trigger without dag_run.conf must immediately fail with PermissionError."""
    # Empty context
    with pytest.raises(PermissionError, match="missing 'approval_id' or 'authorized_run_id'"):
        task_verify_authorization()

    # Empty dag_run context
    mock_context = {"dag_run": MagicMock(conf={})}
    with pytest.raises(PermissionError, match="missing 'approval_id' or 'authorized_run_id'"):
        task_verify_authorization(**mock_context)


def test_task_verify_authorization_valid_credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Task passes and returns auth metadata when presented with valid approval credentials."""
    db_file = tmp_path / "test_approvals.db"
    store = ApprovalStore(db_path=db_file)
    monkeypatch.setattr("dags.approved_retraining_dag.ApprovalStore", lambda: store)

    # Create and approve request
    rec = store.create_request(alert_id="alert-001")
    resp = store.record_decision(
        rec.approval_id,
        DecisionRequest(
            decision=DecisionType.APPROVE,
            decided_by="lead",
            decision_reason="Approved",
            idempotency_key="key-dag-1",
        ),
    )

    mock_context = {
        "dag_run": MagicMock(
            conf={
                "approval_id": rec.approval_id,
                "authorized_run_id": resp.authorized_run_id,
            }
        )
    }

    result = task_verify_authorization(**mock_context)
    assert result["approval_id"] == rec.approval_id
    assert result["authorized_run_id"] == resp.authorized_run_id
    assert result["target_dag_id"] == "approved_retraining"


def test_task_consume_authorization_marks_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Task consumes authorization token and subsequent calls fail."""
    db_file = tmp_path / "test_approvals.db"
    store = ApprovalStore(db_path=db_file)
    monkeypatch.setattr("dags.approved_retraining_dag.ApprovalStore", lambda: store)

    rec = store.create_request(alert_id="alert-002")
    resp = store.record_decision(
        rec.approval_id,
        DecisionRequest(
            decision=DecisionType.APPROVE,
            decided_by="lead",
            decision_reason="Approved",
            idempotency_key="key-dag-2",
        ),
    )

    mock_ti = MagicMock()
    mock_ti.xcom_pull.return_value = {
        "approval_id": rec.approval_id,
        "authorized_run_id": resp.authorized_run_id,
        "target_dag_id": "approved_retraining",
    }
    mock_context = {"ti": mock_ti}

    # Consume succeeds first time
    task_consume_authorization(**mock_context)

    # Second consumption fails
    with pytest.raises(PermissionError, match="Failed to consume authorization token"):
        task_consume_authorization(**mock_context)
