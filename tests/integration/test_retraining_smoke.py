"""Integration smoke test for approval-gated retraining against the DuckLake warehouse (Gate 13)."""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import pytest
from sklearn.pipeline import Pipeline

from analytics_ml.approval.models import DecisionRequest, DecisionType
from analytics_ml.approval.store import ApprovalStore
from analytics_ml.retraining.pipeline import (
    DEFAULT_CATALOG_PATH,
    RetrainingConfig,
    RetrainingEngine,
)


@pytest.mark.skipif(
    not DEFAULT_CATALOG_PATH.exists(),
    reason="DuckLake catalog warehouse/ducklake/catalog.duckdb not present",
)
def test_retraining_integration_smoke(tmp_path: Path) -> None:
    """Run an end-to-end retraining cycle against DuckLake with approval authorization."""
    # Isolated test store and directories
    db_file = tmp_path / "smoke_approvals.db"
    store = ApprovalStore(db_path=db_file)
    models_dir = tmp_path / "models"
    audit_path = tmp_path / "smoke_retraining_audit.json"

    # Step 1: Reject scenario — unapproved run MUST fail
    rej_req = store.create_request(alert_id="alert-smoke-01")
    store.record_decision(
        rej_req.approval_id,
        DecisionRequest(
            decision=DecisionType.REJECT,
            decided_by="senior-engineer",
            decision_reason="False alarm drift",
            idempotency_key="key-smoke-rej",
        ),
    )

    unapproved_config = RetrainingConfig(
        approval_id=rej_req.approval_id,
        authorized_run_id="fake-run-id",
        catalog_path=DEFAULT_CATALOG_PATH,
        models_dir=models_dir,
        audit_log_path=audit_path,
        strict_raise=True,
    )
    unapproved_engine = RetrainingEngine(config=unapproved_config, store=store)

    with pytest.raises(PermissionError, match="not APPROVED"):
        unapproved_engine.execute()

    assert not models_dir.exists()

    # Step 2: Approved scenario — valid run executes and promotes
    appr_req = store.create_request(alert_id="alert-smoke-02")
    decision_resp = store.record_decision(
        appr_req.approval_id,
        DecisionRequest(
            decision=DecisionType.APPROVE,
            decided_by="senior-engineer",
            decision_reason="Legitimate feature shift; retraining approved",
            idempotency_key="key-smoke-appr",
        ),
    )
    assert decision_resp.authorized_run_id is not None

    approved_config = RetrainingConfig(
        approval_id=appr_req.approval_id,
        authorized_run_id=decision_resp.authorized_run_id,
        catalog_path=DEFAULT_CATALOG_PATH,
        models_dir=models_dir,
        audit_log_path=audit_path,
        strict_raise=True,
    )
    approved_engine = RetrainingEngine(config=approved_config, store=store)

    # Validate batch quality directly first
    row_count = approved_engine.validate_batch_quality(min_rows=1000)
    assert row_count >= 900000

    # Execute full pipeline
    outcome = approved_engine.execute()
    assert outcome.status == "SUCCESS_PROMOTED"
    assert outcome.promoted is True
    assert outcome.approval_id == appr_req.approval_id
    assert outcome.authorized_run_id == decision_resp.authorized_run_id

    # Verify promoted model artifact exists and is loadable
    promoted_model_path = models_dir / "baseline_logreg.joblib"
    assert promoted_model_path.exists()
    loaded_pipe = joblib.load(promoted_model_path)
    assert isinstance(loaded_pipe, Pipeline)

    # Verify metrics and metadata
    metrics_path = models_dir / "metrics.json"
    assert metrics_path.exists()
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    assert "pr_auc" in metrics
    assert "f1" in metrics

    metadata_path = models_dir / "model_metadata.json"
    assert metadata_path.exists()
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["authorized_by_approval_id"] == appr_req.approval_id
    assert metadata["authorized_run_id"] == decision_resp.authorized_run_id

    # Verify audit log was recorded
    assert audit_path.exists()
    audit_data = json.loads(audit_path.read_text(encoding="utf-8"))
    # We had 1 rejected audit + 1 success audit
    assert len(audit_data) == 2
    assert audit_data[0]["status"] == "REJECTED_UNAUTHORIZED"
    assert audit_data[1]["status"] == "SUCCESS_PROMOTED"

    # Step 3: Replay prevention — running a second time with the same approved run ID fails
    replay_engine = RetrainingEngine(config=approved_config, store=store)
    with pytest.raises(PermissionError, match="already consumed"):
        replay_engine.execute()
