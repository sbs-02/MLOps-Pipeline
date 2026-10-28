"""Integration smoke test: train and evaluate the baseline model end to end (Gate 8)."""

from __future__ import annotations

import json
from pathlib import Path

from analytics_ml.training import train as training


def test_training_produces_artifacts_and_report() -> None:
    metrics = training.train()

    # Verify all versioned artifacts were created
    assert (training.MODELS_DIR / "baseline_logreg.joblib").exists()
    assert (training.MODELS_DIR / "feature_schema.json").exists()
    assert (training.MODELS_DIR / "feature_list.json").exists()
    assert (training.MODELS_DIR / "split_details.json").exists()
    assert (training.MODELS_DIR / "metrics.json").exists()
    assert (training.MODELS_DIR / "model_metadata.json").exists()
    assert training.REPORT_PATH.exists()

    # Verify 3-way partition row counts
    assert metrics["train"]["rows"] > metrics["validation"]["rows"] > 0
    assert metrics["validation"]["rows"] > metrics["test"]["rows"] > 0
    assert metrics["train"]["positives"] > 0
    assert metrics["validation"]["positives"] > 0
    assert metrics["test"]["positives"] > 0

    # Verify test set metrics
    test_metrics = metrics["test"]
    assert test_metrics["pr_auc"] > 0.0
    assert test_metrics["roc_auc"] > 0.5
    assert 0.0 <= test_metrics["precision"] <= 1.0
    assert 0.0 <= test_metrics["recall"] <= 1.0
    assert 0.0 <= test_metrics["f1"] <= 1.0

    # Verify feature schema and leakage rules on persisted schema
    feature_schema = json.loads(
        (training.MODELS_DIR / "feature_schema.json").read_text(encoding="utf-8")
    )
    assert set(feature_schema["features"]) == set(training.FEATURES)
    assert set(feature_schema["features"]).isdisjoint(training.FORBIDDEN_FEATURES)

    # Verify split details
    split_details = json.loads(
        (training.MODELS_DIR / "split_details.json").read_text(encoding="utf-8")
    )
    assert split_details["train_rows"] == metrics["train"]["rows"]
    assert split_details["val_rows"] == metrics["validation"]["rows"]
    assert split_details["test_rows"] == metrics["test"]["rows"]
