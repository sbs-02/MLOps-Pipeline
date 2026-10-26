"""Integration smoke test: train the baseline end to end."""

from __future__ import annotations

import json
from pathlib import Path

from analytics_ml.training import train as training


def test_training_produces_artifacts_and_report() -> None:
    metrics = training.train()

    assert (training.MODELS_DIR / "baseline_logreg.joblib").exists()
    assert (training.MODELS_DIR / "feature_list.json").exists()
    assert (training.MODELS_DIR / "split_details.json").exists()
    assert (training.MODELS_DIR / "metrics.json").exists()
    assert training.REPORT_PATH.exists()

    assert metrics["pr_auc"] > 0.0
    assert 0.0 <= metrics["precision"] <= 1.0
    assert 0.0 <= metrics["recall"] <= 1.0
    assert metrics["train_rows"] > metrics["test_rows"] > 0
    assert metrics["train_positives"] > 0 and metrics["test_positives"] > 0

    feature_list = json.loads((training.MODELS_DIR / "feature_list.json").read_text())
    assert set(feature_list["categorical"] + feature_list["numeric"]) == set(training.FEATURES)

    # Leakage re-check on the persisted feature list.
    assert set(feature_list["categorical"] + feature_list["numeric"]).isdisjoint(
        training.FORBIDDEN_FEATURES
    )
