"""End-to-End demonstration test covering the full MLOps lifecycle (Gate 14).

Flow:
1. Baseline Health: Prediction service inference & reference data inspection.
2. Normal Batch: Ingest synthetic normal traffic -> drift detector confirms stability -> no alert.
3. Shifted Batch: Ingest synthetic mobile surge -> drift detector flags drift -> alert posted to approval UI.
4. Human Rejection Gate: Operator reviews and rejects -> verify Airflow retraining DAG is blocked.
5. Human Approval Gate: Operator approves legitimate shift -> issues authorized_run_id.
6. Approved Retraining: Airflow pipeline runs -> consumes token -> trains candidate -> evaluates -> promotes with backup -> prevents replay.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import joblib
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from analytics_ml.approval.models import ApprovalState, DecisionRequest, DecisionType
from analytics_ml.approval.store import ApprovalStore
from analytics_ml.monitoring.drift_detector import DriftDetector
from analytics_ml.monitoring.metrics_exporter import DriftMetricsManager
from analytics_ml.monitoring.synthetic_drift import generate_normal_batch, generate_shifted_batch
from analytics_ml.retraining.pipeline import DEFAULT_CATALOG_PATH, RetrainingConfig, RetrainingEngine
from analytics_ml.training.train import FEATURES, TARGET, load_dataset, split_dataset
from dags.approved_retraining_dag import (
    task_consume_authorization,
    task_execute_retraining,
    task_record_audit,
    task_validate_data_batch,
    task_verify_authorization,
)
from services.approval.app import app
from services.prediction.service import ConversionService, PredictionRequest


@pytest.mark.skipif(
    not DEFAULT_CATALOG_PATH.exists(),
    reason="DuckLake catalog warehouse/ducklake/catalog.duckdb not present",
)
def test_end_to_end_mlops_scenario(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # -------------------------------------------------------------------------
    # Setup: Isolated Sandbox Environment
    # -------------------------------------------------------------------------
    db_file = tmp_path / "e2e_approvals.db"
    store = ApprovalStore(db_path=db_file)
    models_dir = tmp_path / "models"
    audit_file = tmp_path / "e2e_retraining_audit.json"

    # Patch approval service to use test store
    monkeypatch.setattr("services.approval.app.store", store)
    api_client = TestClient(app)

    # Load real reference dataset slice from DuckLake
    full_dataset = load_dataset()
    train_df, val_df, test_df = split_dataset(full_dataset)
    ref_df = val_df.sample(n=1000, random_state=42).copy()

    # Pre-populate isolated models directory with active production baseline
    models_dir.mkdir(parents=True, exist_ok=True)
    active_baseline_path = Path("models") / "baseline_logreg.joblib"
    if active_baseline_path.exists():
        import shutil
        shutil.copy2(active_baseline_path, models_dir / "baseline_logreg.joblib")
        if Path("models/metrics.json").exists():
            shutil.copy2("models/metrics.json", models_dir / "metrics.json")
    else:
        # Fallback build pipeline
        from analytics_ml.training.train import build_pipeline
        pipe = build_pipeline()
        pipe.fit(train_df[FEATURES][:1000], train_df[TARGET][:1000].astype(int))
        joblib.dump(pipe, models_dir / "baseline_logreg.joblib")
        (models_dir / "metrics.json").write_text(json.dumps({"pr_auc": 0.4026, "f1": 0.3688}))

    # =========================================================================
    # Step 1: Baseline Inference & Service Health Check
    # =========================================================================
    monkeypatch.setenv("MODEL_PATH", str(models_dir / "baseline_logreg.joblib"))
    serving_svc = ConversionService()
    health = serving_svc.health()
    assert health.status == "ok"
    assert health.model_version == "baseline-logreg-v1"

    sample_req = PredictionRequest(
        channelGrouping="Organic Search",
        device_category="desktop",
        browser="Chrome",
        operating_system="Windows",
        country="United States",
        continent="Americas",
        traffic_source="google",
        traffic_medium="organic",
        visitNumber=2,
        visits=1,
        hits=12,
        pageviews=8,
        time_on_site=240,
    )
    pred_resp = serving_svc.predict(sample_req)
    assert 0.0 <= pred_resp.conversion_probability <= 1.0
    assert pred_resp.prediction in (0, 1)

    # =========================================================================
    # Step 2: Normal Traffic Processing (No Drift Expected)
    # =========================================================================
    normal_batch = generate_normal_batch(ref_df, n_samples=500, random_state=42)
    assert normal_batch["is_simulated"].all()

    detector = DriftDetector(reference_df=ref_df)
    normal_drift = detector.evaluate_data_drift(normal_batch)
    assert normal_drift["dataset_drift_detected"] is False
    assert normal_drift["drift_share"] < 0.30

    metrics_mgr = DriftMetricsManager()
    metrics_mgr.update_from_summary(normal_drift)
    assert metrics_mgr.data_drift_detected.labels(model_version="baseline-logreg-v1")._value.get() == 0.0

    # Confirm approval service has 0 pending requests
    pending_resp = api_client.get("/approvals/pending")
    assert pending_resp.status_code == 200
    assert len(pending_resp.json()) == 0

    # =========================================================================
    # Step 3: Shifted Traffic Ingestion (Mobile Surge -> Data Drift Detected)
    # =========================================================================
    shifted_batch = generate_shifted_batch(ref_df, n_samples=500, random_state=42)
    assert shifted_batch["is_simulated"].all()
    assert (shifted_batch["device_category"] == "mobile").mean() > 0.70

    shifted_drift = detector.evaluate_data_drift(shifted_batch)
    assert shifted_drift["dataset_drift_detected"] is True
    assert shifted_drift["drift_share"] >= 0.30

    metrics_mgr.update_from_summary(shifted_drift)
    assert metrics_mgr.data_drift_detected.labels(model_version="baseline-logreg-v1")._value.get() == 1.0

    # Grafana alert triggers webhook to approval service
    alert_payload = {
        "alert_id": "grafana-alert-mobile-surge-001",
        "target_dag_id": "approved_retraining",
        "model_version": "baseline-logreg-v1",
        "trigger_reason": f"Data drift detected: {shifted_drift['drifted_features_count']}/{len(FEATURES)} features drifted ({shifted_drift['drift_share']*100:.1f}%)",
        "evidence_summary": {
            "drift_share": shifted_drift["drift_share"],
            "drifted_features": shifted_drift["drifted_features"],
            "sample_size": len(shifted_batch),
        },
    }
    create_resp = api_client.post("/approvals/requests", json=alert_payload)
    assert create_resp.status_code == 201
    rejected_approval_id = create_resp.json()["approval_id"]

    # =========================================================================
    # Step 4: Human Operator Rejection Gate
    # =========================================================================
    # Operator inspects console and rejects spurious / temporary promotion
    reject_payload = {
        "decision": "REJECT",
        "decided_by": "on-call-data-engineer",
        "decision_reason": "Identified as temporary 1-day flash marketing campaign; model update rejected",
        "idempotency_key": "idemp-rej-001",
    }
    decide_resp = api_client.post(
        f"/approvals/{rejected_approval_id}/decision", json=reject_payload
    )
    assert decide_resp.status_code == 200
    assert decide_resp.json()["state"] == "REJECTED"
    assert decide_resp.json()["authorized_run_id"] is None

    # Verify that attempting to run Airflow retraining with rejected request is strictly blocked
    unapproved_config = RetrainingConfig(
        approval_id=rejected_approval_id,
        authorized_run_id="fake-run-attempt",
        models_dir=models_dir,
        audit_log_path=audit_file,
        strict_raise=True,
    )
    unapproved_engine = RetrainingEngine(config=unapproved_config, store=store)
    with pytest.raises(PermissionError, match="not APPROVED"):
        unapproved_engine.verify_authorization()

    # Verify active production model has not been overwritten
    assert (models_dir / "baseline_logreg.joblib").exists()
    assert not (models_dir / "baseline_logreg_backup.joblib").exists()

    # =========================================================================
    # Step 5: Second Valid Alert & Human Approval Gate
    # =========================================================================
    # Persistent shift causes second legitimate approval request
    legit_alert_payload = {
        "alert_id": "grafana-alert-mobile-structural-002",
        "target_dag_id": "approved_retraining",
        "model_version": "baseline-logreg-v1",
        "trigger_reason": "Structural multi-day shift in mobile customer demographics verified",
        "evidence_summary": {
            "drift_share": shifted_drift["drift_share"],
            "drifted_features": shifted_drift["drifted_features"],
        },
    }
    create_legit_resp = api_client.post("/approvals/requests", json=legit_alert_payload)
    assert create_legit_resp.status_code == 201
    approved_approval_id = create_legit_resp.json()["approval_id"]

    approve_payload = {
        "decision": "APPROVE",
        "decided_by": "senior-lead-engineer",
        "decision_reason": "Confirmed structural business expansion in mobile; authorizing retraining DAG",
        "idempotency_key": "idemp-appr-002",
    }
    approve_resp = api_client.post(
        f"/approvals/{approved_approval_id}/decision", json=approve_payload
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["state"] == "APPROVED"
    authorized_run_id = approve_resp.json()["authorized_run_id"]
    assert authorized_run_id is not None

    # =========================================================================
    # Step 6: Airflow Approved Retraining Execution, Evaluation Gate & Promotion
    # =========================================================================
    retrain_config = RetrainingConfig(
        approval_id=approved_approval_id,
        authorized_run_id=authorized_run_id,
        catalog_path=DEFAULT_CATALOG_PATH,
        models_dir=models_dir,
        audit_log_path=audit_file,
        min_pr_auc_threshold=0.30,
        min_f1_threshold=0.25,
        max_pr_auc_drop=0.08,
        strict_raise=True,
    )
    engine = RetrainingEngine(config=retrain_config, store=store)

    # 6a. Execute full retraining engine
    outcome = engine.execute()
    assert outcome.status == "SUCCESS_PROMOTED"
    assert outcome.promoted is True
    assert outcome.candidate_metrics["pr_auc"] >= 0.30

    # 6b. Verify promotion safety invariants
    # 1. Backup model created
    assert (models_dir / "baseline_logreg_backup.joblib").exists()
    # 2. Promoted active model updated
    assert (models_dir / "baseline_logreg.joblib").exists()
    # 3. Model metadata updated with governance lineage
    metadata = json.loads((models_dir / "model_metadata.json").read_text(encoding="utf-8"))
    assert metadata["authorized_by_approval_id"] == approved_approval_id
    assert metadata["authorized_run_id"] == authorized_run_id

    # 6c. Verify Replay Prevention: second trigger with same token fails
    with pytest.raises(PermissionError, match="already consumed"):
        engine.execute()

    # 6d. Verify serving service seamlessly serves with newly promoted model
    reloaded_svc = ConversionService()
    post_promoted_pred = reloaded_svc.predict(sample_req)
    assert post_promoted_pred.conversion_probability >= 0.0

    # Clean up dependency overrides
    app.dependency_overrides.clear()
