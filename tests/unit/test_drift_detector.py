"""Unit tests for statistical data drift and concept drift detection (Gate 10)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from analytics_ml.monitoring.drift_detector import (
    DriftDetector,
    calculate_categorical_drift,
    calculate_numeric_drift,
)
from analytics_ml.monitoring.synthetic_drift import (
    generate_delayed_label_stream,
    generate_normal_batch,
    generate_shifted_batch,
)
from analytics_ml.training.train import CATEGORICAL_FEATURES, NUMERIC_FEATURES, FEATURES


def create_synthetic_reference(n: int = 200, random_state: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(random_state)
    data: dict[str, Any] = {}
    for col in NUMERIC_FEATURES:
        data[col] = rng.integers(1, 100, size=n)
    for col in CATEGORICAL_FEATURES:
        data[col] = rng.choice(["A", "B", "C"], size=n, p=[0.6, 0.3, 0.1])
    return pd.DataFrame(data)


def test_numeric_drift_identical_distributions() -> None:
    vals = np.array([10, 20, 30, 40, 50, 60, 70, 80, 90, 100])
    res = calculate_numeric_drift(vals, vals)
    assert not res["drift_detected"]
    assert res["p_value"] > 0.9
    assert np.isclose(res["wasserstein_distance"], 0.0)


def test_numeric_drift_shifted_distribution() -> None:
    rng = np.random.default_rng(42)
    ref = rng.normal(loc=10.0, scale=2.0, size=500)
    cur = rng.normal(loc=50.0, scale=2.0, size=500)
    res = calculate_numeric_drift(ref, cur)
    assert res["drift_detected"]
    assert res["p_value"] < 0.001
    assert res["wasserstein_distance"] > 30.0


def test_categorical_drift_identical_frequencies() -> None:
    s = pd.Series(["desktop", "mobile", "desktop", "desktop", "tablet"])
    res = calculate_categorical_drift(s, s)
    assert not res["drift_detected"]
    assert np.isclose(res["distance"], 0.0, atol=1e-4)


def test_categorical_drift_shifted_frequencies() -> None:
    ref = pd.Series(["desktop"] * 90 + ["mobile"] * 10)
    cur = pd.Series(["desktop"] * 5 + ["mobile"] * 95)
    res = calculate_categorical_drift(ref, cur)
    assert res["drift_detected"]
    assert res["distance"] > res["threshold"]


def test_detector_no_drift_on_identical_reference() -> None:
    ref_df = create_synthetic_reference(200)
    detector = DriftDetector(reference_df=ref_df)
    res = detector.evaluate_data_drift(ref_df)
    assert not res["dataset_drift_detected"]
    assert res["drifted_features_count"] == 0
    assert res["drift_share"] == 0.0


def test_detector_detects_shifted_synthetic_batch() -> None:
    ref_df = create_synthetic_reference(500)
    detector = DriftDetector(reference_df=ref_df)
    shifted_df = generate_shifted_batch(ref_df, n_samples=500, random_state=42)
    res = detector.evaluate_data_drift(shifted_df)

    assert res["drifted_features_count"] > 0
    # device_category and numeric features should drift
    assert "device_category" in res["drifted_features"] or "time_on_site" in res["drifted_features"]


def test_concept_drift_pending_when_labels_missing() -> None:
    ref_df = create_synthetic_reference(100)
    detector = DriftDetector(reference_df=ref_df)
    proba = np.array([0.1, 0.2, 0.8, 0.9])
    res = detector.evaluate_concept_drift(y_true=None, proba=proba)

    assert res["concept_drift_status"] == "labels_pending"
    assert not res["concept_drift_detected"]
    assert "not yet observed" in res["message"]


def test_concept_drift_evaluated_when_labels_present() -> None:
    ref_df = create_synthetic_reference(100)
    detector = DriftDetector(reference_df=ref_df)
    y_true = np.array([0, 0, 1, 1, 0, 1, 0, 1, 0, 0])
    proba = np.array([0.1, 0.2, 0.8, 0.9, 0.3, 0.85, 0.05, 0.95, 0.2, 0.1])
    res = detector.evaluate_concept_drift(y_true=y_true, proba=proba)

    assert res["concept_drift_status"] == "evaluated"
    assert res["batch_f1"] > 0.8
    assert res["observed_samples"] == 10


def test_synthetic_batches_marked_is_simulated() -> None:
    ref_df = create_synthetic_reference(50)
    normal_b = generate_normal_batch(ref_df, n_samples=30)
    shifted_b = generate_shifted_batch(ref_df, n_samples=30)
    delayed_labels = generate_delayed_label_stream(ref_df)

    assert (normal_b["is_simulated"] == True).all()
    assert (shifted_b["is_simulated"] == True).all()
    assert (delayed_labels["is_simulated"] == True).all()
