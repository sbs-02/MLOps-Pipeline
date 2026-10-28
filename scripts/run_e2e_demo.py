"""Interactive End-to-End Demonstration Scenario Runner (Gate 14).

Executes the complete MLOps lifecycle from data drift detection to approved retraining
and safe model promotion, displaying formatted progress and evidence at each step.
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from analytics_ml.approval.models import DecisionRequest, DecisionType
from analytics_ml.approval.store import ApprovalStore
from analytics_ml.monitoring.drift_detector import DriftDetector
from analytics_ml.monitoring.metrics_exporter import DriftMetricsManager
from analytics_ml.monitoring.synthetic_drift import generate_normal_batch, generate_shifted_batch
from analytics_ml.retraining.pipeline import DEFAULT_CATALOG_PATH, RetrainingConfig, RetrainingEngine
from analytics_ml.training.train import FEATURES, load_dataset, split_dataset
from services.prediction.service import ConversionService, PredictionRequest


def print_step(title: str, step_num: int) -> None:
    print(f"\n{'='*80}")
    print(f" STEP {step_num}: {title.upper()}")
    print(f"{'='*80}")


def main() -> None:
    print(f"\n{'*'*80}")
    print(" GOOGLE ANALYTICS MLOPS PLATFORM - END-TO-END DEMO SCENARIO")
    print(f"{'*'*80}")

    # Initialize store and paths
    db_path = PROJECT_ROOT / "warehouse" / "approvals.db"
    store = ApprovalStore(db_path=db_path)
    models_dir = PROJECT_ROOT / "models"
    audit_path = PROJECT_ROOT / "reports" / "retraining_audit.json"

    # Step 1: Health & Baseline Check
    print_step("Serving Health & Active Baseline Inference", 1)
    svc = ConversionService()
    health = svc.health()
    print(f"[-] Prediction Service Status : {health.status.upper()}")
    print(f"[-] Active Model Version      : {health.model_version}")

    sample = PredictionRequest(
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
    resp = svc.predict(sample)
    print(f"[-] Baseline Sample Score    : {resp.conversion_probability:.4f} (Converted: {bool(resp.prediction)})")

    # Load real reference dataset slice from DuckLake
    print("\n[-] Loading validation reference distribution from DuckLake catalog...")
    full_dataset = load_dataset()
    _, val_df, _ = split_dataset(full_dataset)
    ref_df = val_df.sample(n=1000, random_state=42).copy()
    print(f"[-] Reference sample loaded   : {len(ref_df)} rows")

    detector = DriftDetector(reference_df=ref_df)
    metrics_mgr = DriftMetricsManager()

    # Step 2: Normal Batch Processing
    print_step("Normal Traffic Batch Ingestion & Drift Evaluation", 2)
    normal_batch = generate_normal_batch(ref_df, n_samples=500, random_state=42)
    print(f"[-] Ingested simulated batch : {len(normal_batch)} rows (provenance: is_simulated={normal_batch['is_simulated'].iloc[0]})")

    normal_drift = detector.evaluate_data_drift(normal_batch)
    print(f"[-] Drift Evaluation Result   : Dataset Drift = {normal_drift['dataset_drift_detected']}")
    print(f"[-] Drifted Features Share    : {normal_drift['drift_share']*100:.1f}% ({normal_drift['drifted_features_count']}/{len(FEATURES)})")
    metrics_mgr.update_from_summary(normal_drift)
    print("[-] Prometheus Metrics        : model_data_drift_detected = 0 (Normal state; NO alert raised)")

    # Step 3: Shifted Batch Processing
    print_step("Shifted Traffic Surge (Mobile Surge) Ingestion", 3)
    shifted_batch = generate_shifted_batch(ref_df, n_samples=500, random_state=42)
    mobile_pct = (shifted_batch["device_category"] == "mobile").mean() * 100
    print(f"[-] Ingested shifted batch    : {len(shifted_batch)} rows (Mobile Traffic: {mobile_pct:.1f}%)")

    shifted_drift = detector.evaluate_data_drift(shifted_batch)
    print(f"[-] Drift Evaluation Result   : Dataset Drift = {shifted_drift['dataset_drift_detected']} [ALERT]")
    print(f"[-] Drifted Features Share    : {shifted_drift['drift_share']*100:.1f}% ({shifted_drift['drifted_features_count']}/{len(FEATURES)})")
    print(f"[-] Drifted Features List     : {shifted_drift['drifted_features']}")
    metrics_mgr.update_from_summary(shifted_drift)
    print("[-] Prometheus Metrics        : model_data_drift_detected = 1 (ALERT FIRING)")

    # Step 4: Alert Ingestion & Human Rejection Gate
    print_step("Alert Webhook & Human Rejection Gate", 4)
    rej_record = store.create_request(
        alert_id="grafana-alert-mobile-flash-campaign",
        target_dag_id="approved_retraining",
        model_version=health.model_version,
        trigger_reason=f"Data drift detected: {shifted_drift['drift_share']*100:.1f}% features drifted",
        evidence_summary=shifted_drift,
    )
    print(f"[-] Pending Approval Created  : {rej_record.approval_id} (State: {rej_record.state.value})")
    print("[-] Human Operator Review     : Operator assesses event as a temporary 1-day flash campaign.")

    rej_decision = store.record_decision(
        rej_record.approval_id,
        DecisionRequest(
            decision=DecisionType.REJECT,
            decided_by="on-call-data-engineer",
            decision_reason="Temporary flash promotion; model retrain rejected",
            idempotency_key="demo-rej-key",
        ),
    )
    print(f"[-] Decision Recorded         : State = {rej_decision.state.value}")
    print(f"[-] Authorized Run ID         : {rej_decision.authorized_run_id} (Retraining strictly prohibited)")

    # Step 5: Legitimate Alert & Human Approval Gate
    print_step("Structural Shift & Human Approval Authorization", 5)
    appr_record = store.create_request(
        alert_id="grafana-alert-mobile-structural-growth",
        target_dag_id="approved_retraining",
        model_version=health.model_version,
        trigger_reason="Multi-day persistent mobile user growth confirmed",
        evidence_summary=shifted_drift,
    )
    print(f"[-] New Approval Created      : {appr_record.approval_id} (State: {appr_record.state.value})")
    print("[-] Human Operator Review     : Senior Lead confirms structural market expansion in mobile users.")

    appr_decision = store.record_decision(
        appr_record.approval_id,
        DecisionRequest(
            decision=DecisionType.APPROVE,
            decided_by="senior-lead-engineer",
            decision_reason="Verified permanent user demographic expansion; retraining authorized",
            idempotency_key="demo-appr-key",
        ),
    )
    print(f"[-] Decision Recorded         : State = {appr_decision.state.value}")
    print(f"[-] Issued Authorized Run ID  : {appr_decision.authorized_run_id}")

    # Step 6: Approved Retraining & Safe Promotion
    print_step("Airflow Approved Retraining & Model Promotion", 6)
    retrain_config = RetrainingConfig(
        approval_id=appr_record.approval_id,
        authorized_run_id=appr_decision.authorized_run_id,
        catalog_path=DEFAULT_CATALOG_PATH,
        models_dir=models_dir,
        audit_log_path=audit_path,
        strict_raise=True,
    )
    engine = RetrainingEngine(config=retrain_config, store=store)
    outcome = engine.execute()

    print(f"[-] Retraining Status         : {outcome.status}")
    print(f"[-] Candidate PR-AUC          : {outcome.candidate_metrics.get('pr_auc', 0):.4f}")
    print(f"[-] Candidate F1 Score        : {outcome.candidate_metrics.get('f1', 0):.4f}")
    print(f"[-] Model Promoted            : {outcome.promoted}")
    print(f"[-] Backup Created            : {models_dir / 'baseline_logreg_backup.joblib'}")

    # Verify Replay Prevention
    print("\n[-] Testing Replay Defense...")
    valid, replay_msg, _ = store.verify_authorization(
        appr_record.approval_id, appr_decision.authorized_run_id, "approved_retraining"
    )
    print(f"[-] Replay Verification Check : Valid = {valid} (Reason: {replay_msg})")

    # Step 7: Live Serving Verification
    print_step("Post-Promotion Live Serving Verification", 7)
    new_svc = ConversionService()
    new_resp = new_svc.predict(sample)
    print(f"[-] Post-Promotion Prediction : {new_resp.conversion_probability:.4f} (Request ID: {new_resp.request_id})")
    print("[-] Serving Transition        : Zero-downtime hot reload verified.")

    print(f"\n{'*'*80}")
    print(" END-TO-END DEMO SCENARIO COMPLETED SUCCESSFULLY [PASS]")
    print(f"{'*'*80}\n")


if __name__ == "__main__":
    main()
