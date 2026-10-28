"""Unit tests for the approval-gated retraining engine (Gate 13)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from analytics_ml.approval.models import ApprovalState, DecisionRequest, DecisionType
from analytics_ml.approval.store import ApprovalStore
from analytics_ml.retraining.pipeline import (
    RetrainingConfig,
    RetrainingEngine,
    RetrainingOutcome,
)
from analytics_ml.training.train import FEATURES, TARGET


@pytest.fixture
def temp_store(tmp_path: Path) -> ApprovalStore:
    db_file = tmp_path / "test_approvals.db"
    return ApprovalStore(db_path=db_file)


@pytest.fixture
def approved_credentials(temp_store: ApprovalStore) -> tuple[str, str]:
    rec = temp_store.create_request(alert_id="alert-drift-001")
    resp = temp_store.record_decision(
        rec.approval_id,
        DecisionRequest(
            decision=DecisionType.APPROVE,
            decided_by="mlops-engineer",
            decision_reason="Valid mobile shift verified",
            idempotency_key="key-001",
        ),
    )
    assert resp.authorized_run_id is not None
    return rec.approval_id, resp.authorized_run_id


def test_verify_authorization_unapproved_rejected(temp_store: ApprovalStore) -> None:
    # 1. Non-existent approval
    config = RetrainingConfig(
        approval_id="nonexistent-id",
        authorized_run_id="run-dummy",
        strict_raise=True,
    )
    engine = RetrainingEngine(config=config, store=temp_store)
    with pytest.raises(PermissionError, match="not found"):
        engine.verify_authorization()

    # 2. PENDING approval
    pending_rec = temp_store.create_request(alert_id="alert-pending-01")
    config2 = RetrainingConfig(
        approval_id=pending_rec.approval_id,
        authorized_run_id="run-dummy",
        strict_raise=True,
    )
    engine2 = RetrainingEngine(config=config2, store=temp_store)
    with pytest.raises(PermissionError, match="not APPROVED"):
        engine2.verify_authorization()

    # 3. REJECTED approval
    rej_rec = temp_store.create_request(alert_id="alert-reject-01")
    temp_store.record_decision(
        rej_rec.approval_id,
        DecisionRequest(
            decision=DecisionType.REJECT,
            decided_by="lead",
            decision_reason="Spurious alert",
            idempotency_key="key-rej",
        ),
    )
    config3 = RetrainingConfig(
        approval_id=rej_rec.approval_id,
        authorized_run_id="run-dummy",
        strict_raise=True,
    )
    engine3 = RetrainingEngine(config=config3, store=temp_store)
    with pytest.raises(PermissionError, match="not APPROVED"):
        engine3.verify_authorization()


def test_verify_authorization_run_id_mismatch(
    temp_store: ApprovalStore, approved_credentials: tuple[str, str]
) -> None:
    approval_id, _ = approved_credentials
    config = RetrainingConfig(
        approval_id=approval_id,
        authorized_run_id="wrong-run-id",
        strict_raise=True,
    )
    engine = RetrainingEngine(config=config, store=temp_store)
    with pytest.raises(PermissionError, match="Authorized run ID mismatch"):
        engine.verify_authorization()


def test_verify_authorization_success_and_replay_prevention(
    temp_store: ApprovalStore, approved_credentials: tuple[str, str]
) -> None:
    approval_id, run_id = approved_credentials
    config = RetrainingConfig(
        approval_id=approval_id,
        authorized_run_id=run_id,
        strict_raise=True,
    )
    engine = RetrainingEngine(config=config, store=temp_store)

    # Initial check passes
    record = engine.verify_authorization()
    assert record.approval_id == approval_id

    # Consume token
    engine.consume_authorization()

    # Subsequent verification must fail because token was consumed
    with pytest.raises(PermissionError, match="already consumed"):
        engine.verify_authorization()

    # Subsequent consumption must also fail
    with pytest.raises(PermissionError, match="already consumed"):
        engine.consume_authorization()


def test_evaluate_candidate_quality_gate(tmp_path: Path) -> None:
    models_dir = tmp_path / "models"
    models_dir.mkdir(parents=True)
    with open(models_dir / "metrics.json", "w", encoding="utf-8") as f:
        json.dump({"pr_auc": 0.4000, "f1": 0.3600}, f)

    config = RetrainingConfig(
        approval_id="appr-1",
        authorized_run_id="run-1",
        models_dir=models_dir,
        min_pr_auc_threshold=0.35,
        min_f1_threshold=0.30,
        max_pr_auc_drop=0.05,
    )
    engine = RetrainingEngine(config=config)

    # Synthetic validation dataset
    n_samples = 200
    df = pd.DataFrame(
        {
            feat: np.random.randn(n_samples) if feat in [
                "visitNumber", "visits", "hits", "pageviews", "time_on_site"
            ] else ["desktop"] * n_samples
            for feat in FEATURES
        }
    )
    y = np.random.choice([0, 1], size=n_samples, p=[0.9, 0.1])
    df[TARGET] = y

    # Mock high-performing candidate pipeline
    mock_high_candidate = MagicMock()
    # High score mock
    mock_high_candidate.predict_proba.return_value = np.column_stack([1 - y, y])

    passed, c_metrics, a_metrics, reason = engine.evaluate_candidate(
        mock_high_candidate, df
    )
    assert passed is True
    assert c_metrics["pr_auc"] >= 0.35
    assert "meets all quality gates" in reason

    # Mock low-performing candidate pipeline (all zeros -> terrible PR-AUC)
    mock_low_candidate = MagicMock()
    mock_low_candidate.predict_proba.return_value = np.zeros((n_samples, 2))
    mock_low_candidate.predict_proba.return_value[:, 0] = 1.0

    passed_low, c_low_metrics, _, low_reason = engine.evaluate_candidate(
        mock_low_candidate, df
    )
    assert passed_low is False
    assert "below minimum threshold" in low_reason or "drop" in low_reason


def test_promote_candidate_atomic_backup(tmp_path: Path) -> None:
    models_dir = tmp_path / "models"
    models_dir.mkdir(parents=True)

    # Create fake active baseline model
    active_path = models_dir / "baseline_logreg.joblib"
    joblib.dump({"model": "original_v1"}, active_path)

    config = RetrainingConfig(
        approval_id="appr-backup",
        authorized_run_id="run-backup",
        models_dir=models_dir,
    )
    engine = RetrainingEngine(config=config)

    # Candidate pipeline
    candidate_pipe = Pipeline([("scaler", StandardScaler(with_mean=False))])
    candidate_metrics = {"pr_auc": 0.4200, "f1": 0.3800}

    engine.promote_candidate(candidate_pipe, candidate_metrics)

    # Verify backup was created
    backup_path = models_dir / "baseline_logreg_backup.joblib"
    assert backup_path.exists()
    old_model = joblib.load(backup_path)
    assert old_model == {"model": "original_v1"}

    # Verify new model was saved
    new_model = joblib.load(active_path)
    assert isinstance(new_model, Pipeline)

    # Verify metadata
    metadata = json.loads((models_dir / "model_metadata.json").read_text(encoding="utf-8"))
    assert metadata["authorized_by_approval_id"] == "appr-backup"
    assert metadata["candidate_pr_auc"] == 0.4200


def test_retraining_engine_full_execution_gate_pass(
    temp_store: ApprovalStore,
    approved_credentials: tuple[str, str],
    tmp_path: Path,
) -> None:
    approval_id, run_id = approved_credentials
    models_dir = tmp_path / "models"
    audit_path = tmp_path / "audit.json"

    config = RetrainingConfig(
        approval_id=approval_id,
        authorized_run_id=run_id,
        models_dir=models_dir,
        audit_log_path=audit_path,
        min_pr_auc_threshold=0.01,  # Low threshold to ensure synthetic test passes
        min_f1_threshold=0.01,
        max_pr_auc_drop=1.0,
        strict_raise=True,
    )
    engine = RetrainingEngine(config=config, store=temp_store)

    # Build synthetic test dataset with 3-way split dates
    dates = ["20160901"] * 60 + ["20170501"] * 20 + ["20170715"] * 20
    df = pd.DataFrame(
        {
            "fullVisitorId": [f"user_{i}" for i in range(100)],
            "visitId": list(range(100)),
            "date": dates,
            "channelGrouping": ["Organic Search"] * 100,
            "device_category": ["desktop"] * 100,
            "browser": ["Chrome"] * 100,
            "operating_system": ["Windows"] * 100,
            "country": ["United States"] * 100,
            "continent": ["Americas"] * 100,
            "traffic_source": ["google"] * 100,
            "traffic_medium": ["organic"] * 100,
            "visitNumber": [1] * 100,
            "visits": [1] * 100,
            "hits": [5] * 100,
            "pageviews": [4] * 100,
            "time_on_site": [120] * 100,
            TARGET: [1 if i % 5 == 0 else 0 for i in range(100)],
        }
    )

    outcome = engine.execute(dataset_frame=df)
    assert outcome.status == "SUCCESS_PROMOTED"
    assert outcome.promoted is True
    assert (models_dir / "baseline_logreg.joblib").exists()
    assert audit_path.exists()

    audit_records = json.loads(audit_path.read_text(encoding="utf-8"))
    assert len(audit_records) == 1
    assert audit_records[0]["approval_id"] == approval_id
    assert audit_records[0]["promoted"] is True
