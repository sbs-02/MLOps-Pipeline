"""Integration smoke test for drift monitoring pipeline (Gate 10)."""

from __future__ import annotations

from pathlib import Path

from analytics_ml.monitoring.drift_detector import REPORT_PATH, run_drift_pipeline


def test_drift_pipeline_smoke() -> None:
    summary = run_drift_pipeline()

    # 1. Report existence
    assert REPORT_PATH.exists()
    assert REPORT_PATH.stat().st_size > 500

    # 2. Holdout evaluation
    holdout = summary["holdout_2017Q3"]
    assert "data_drift" in holdout
    assert "concept_drift" in holdout
    assert holdout["data_drift"]["total_features"] == 13
    assert holdout["concept_drift"]["concept_drift_status"] == "evaluated"

    # 3. Simulated shifted batch
    shifted = summary["simulated_shifted_batch"]
    assert shifted["data_drift"]["dataset_drift_detected"] == True
    assert shifted["data_drift"]["drifted_features_count"] >= 3

    # 4. Delayed label semantics
    assert shifted["concept_drift_pending"]["concept_drift_status"] == "labels_pending"
    assert shifted["concept_drift_observed"]["concept_drift_status"] == "evaluated"
