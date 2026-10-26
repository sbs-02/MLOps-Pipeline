"""Unit tests for training helpers (no data loading, no model fitting)."""

from __future__ import annotations

import pandas as pd

from analytics_ml.training import train as training


def test_no_leakage_in_feature_list() -> None:
    assert set(training.FEATURES).isdisjoint(training.FORBIDDEN_FEATURES)
    assert training.FEATURES == training.CATEGORICAL_FEATURES + training.NUMERIC_FEATURES


def test_build_pipeline_constructs() -> None:
    pipeline = training.build_pipeline()
    assert "preprocessor" in pipeline.named_steps
    assert "model" in pipeline.named_steps


def test_split_is_time_based() -> None:
    frame = pd.DataFrame(
        {
            "date": ["20170101", "20170601", "20170701", "20170801"],
            training.TARGET: [0, 1, 0, 1],
        }
    )
    # Add the feature columns the splitter does not need.
    for col in training.FEATURES:
        frame[col] = 0 if col in training.NUMERIC_FEATURES else "x"
    train_df, test_df = training.split_dataset(frame)
    assert not train_df.empty and not test_df.empty
    assert (train_df["date"] < training.TRAIN_CUTOFF).all()
    assert (test_df["date"] >= training.TRAIN_CUTOFF).all()


def test_leakage_forbidden_set_covers_outcome_fields() -> None:
    for forbidden in ("conversion_label", "transactions", "transactionRevenue", "fullVisitorId"):
        assert forbidden in training.FORBIDDEN_FEATURES
