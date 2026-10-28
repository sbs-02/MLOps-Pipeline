"""Unit tests for training module, leakage rules, and artifact inference (Gate 8)."""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest

from analytics_ml.training import train as training


def test_no_leakage_in_feature_list() -> None:
    """Features must be completely disjoint from forbidden leakage fields."""
    assert set(training.FEATURES).isdisjoint(training.FORBIDDEN_FEATURES)
    assert training.FEATURES == training.CATEGORICAL_FEATURES + training.NUMERIC_FEATURES


def test_assert_no_leakage_raises_on_forbidden_fields() -> None:
    """Leakage check must raise ValueError if any forbidden field is passed."""
    for forbidden in (
        "conversion_label",
        "transactions",
        "transactionRevenue",
        "totalTransactionRevenue",
        "fullVisitorId",
        "visitId",
        "date",
        "_ingested_at",
    ):
        with pytest.raises(ValueError, match="forbidden columns"):
            training._assert_no_leakage(training.FEATURES + [forbidden])


def test_assert_no_leakage_raises_on_feature_mismatch() -> None:
    """Leakage check must raise ValueError if features are missing."""
    with pytest.raises(ValueError, match="Feature set mismatch"):
        training._assert_no_leakage(training.CATEGORICAL_FEATURES)


def test_build_pipeline_constructs() -> None:
    """Pipeline must assemble preprocessor and logistic regression model steps."""
    pipeline = training.build_pipeline()
    assert "preprocessor" in pipeline.named_steps
    assert "model" in pipeline.named_steps


def test_label_construction_logic() -> None:
    """Label construction: transactions >= 1 is positive (1), null is negative (0)."""
    raw_data = pd.DataFrame(
        {
            "transactions": [None, 1, 3, None, 0],
        }
    )
    # Replicate dbt staging logic: totals.transactions is not null and totals.transactions > 0
    label = (raw_data["transactions"].notna() & (raw_data["transactions"] > 0)).astype(int)
    assert list(label) == [0, 1, 1, 0, 0]


def test_split_is_three_way_chronological() -> None:
    """Split must partition chronologically into train, validation, and test."""
    frame = pd.DataFrame(
        {
            "date": [
                "20160815",  # Train (< 20170401)
                "20161201",  # Train (< 20170401)
                "20170331",  # Train (< 20170401)
                "20170415",  # Validation (>= 20170401 and < 20170701)
                "20170630",  # Validation (>= 20170401 and < 20170701)
                "20170701",  # Test (>= 20170701)
                "20170801",  # Test (>= 20170701)
            ],
            training.TARGET: [0, 1, 0, 1, 0, 1, 0],
        }
    )
    for col in training.FEATURES:
        frame[col] = 0 if col in training.NUMERIC_FEATURES else "unknown"

    train_df, val_df, test_df = training.split_dataset(frame)

    assert len(train_df) == 3
    assert len(val_df) == 2
    assert len(test_df) == 2

    assert (train_df["date"] < training.TRAIN_CUTOFF).all()
    assert (
        (val_df["date"] >= training.TRAIN_CUTOFF) & (val_df["date"] < training.VAL_CUTOFF)
    ).all()
    assert (test_df["date"] >= training.VAL_CUTOFF).all()


def test_leakage_forbidden_set_covers_all_identities_and_outcomes() -> None:
    """Forbidden set must include identifiers, outcomes, timestamps, and target."""
    required_forbidden = {
        "conversion_label",
        "transactions",
        "transactionRevenue",
        "totalTransactionRevenue",
        "fullVisitorId",
        "visitId",
        "date",
        "_ingested_at",
        "_source",
    }
    assert required_forbidden.issubset(training.FORBIDDEN_FEATURES)


def test_artifact_reload_and_prediction() -> None:
    """Reloading the trained model artifact from disk must successfully predict a sample."""
    artifact_path = training.MODELS_DIR / "baseline_logreg.joblib"
    if not artifact_path.exists():
        pytest.skip("Model artifact not yet generated; skipping reload test.")

    pipeline = joblib.load(artifact_path)

    sample_request = pd.DataFrame(
        [
            {
                "channelGrouping": "Organic Search",
                "device_category": "desktop",
                "browser": "Chrome",
                "operating_system": "Windows",
                "country": "United States",
                "continent": "Americas",
                "traffic_source": "google",
                "traffic_medium": "organic",
                "visitNumber": 1,
                "visits": 1,
                "hits": 5,
                "pageviews": 4,
                "time_on_site": 120,
            }
        ]
    )

    proba = pipeline.predict_proba(sample_request)
    assert proba.shape == (1, 2)
    assert 0.0 <= proba[0, 0] <= 1.0
    assert 0.0 <= proba[0, 1] <= 1.0
    assert np.isclose(proba[0, 0] + proba[0, 1], 1.0)
