"""Simulated batch generation for drift demonstration (Gate 10).

All generated datasets strictly include `is_simulated = True` per CONTEXT.md Principle 5.
"""

from __future__ import annotations

import uuid
from typing import Any

import numpy as np
import pandas as pd

from analytics_ml.training.train import CATEGORICAL_FEATURES, NUMERIC_FEATURES, FEATURES


def generate_normal_batch(source_df: pd.DataFrame, n_samples: int = 500, random_state: int = 42) -> pd.DataFrame:
    """Sample an unperturbed batch from historical holdout data, labeled as simulated."""
    sample = source_df.sample(n=min(n_samples, len(source_df)), random_state=random_state).copy()
    sample["is_simulated"] = True
    sample["simulation_type"] = "normal_baseline_sample"
    return sample


def generate_shifted_batch(source_df: pd.DataFrame, n_samples: int = 500, random_state: int = 42) -> pd.DataFrame:
    """Generate a controlled covariate shift batch (e.g. mobile traffic surge, engagement drop).

    Simulates:
    1. Severe shift in device_category (85% mobile, 10% desktop, 5% tablet).
    2. Shift in operating_system towards Android/iOS.
    3. Shift in time_on_site (reduced by 60%, representing quick mobile bounces).
    4. Shift in hits (concentrated near 1-2 hits).
    """
    rng = np.random.default_rng(random_state)
    sample = source_df.sample(n=min(n_samples, len(source_df)), random_state=random_state).copy()

    # 1. Perturb device_category
    devices = ["mobile", "desktop", "tablet"]
    device_probs = [0.85, 0.10, 0.05]
    sample["device_category"] = rng.choice(devices, size=len(sample), p=device_probs)

    # 2. Perturb operating system to match mobile shift
    mobile_os = ["Android", "iOS", "Windows Phone"]
    os_probs = [0.60, 0.35, 0.05]
    mask_mobile = sample["device_category"] == "mobile"
    sample.loc[mask_mobile, "operating_system"] = rng.choice(
        mobile_os, size=int(mask_mobile.sum()), p=os_probs
    )

    # 3. Perturb numeric engagement metrics
    sample["time_on_site"] = (sample["time_on_site"] * 0.4).astype(int)
    sample["hits"] = np.clip((sample["hits"] * 0.5).astype(int), 1, None)
    sample["pageviews"] = np.clip((sample["pageviews"] * 0.5).astype(int), 1, None)

    # 4. Mandatory provenance flags
    sample["is_simulated"] = True
    sample["simulation_type"] = "covariate_shift_mobile_surge"
    return sample


def generate_delayed_label_stream(
    predictions_df: pd.DataFrame,
    delay_hours_mean: float = 6.0,
    random_state: int = 42,
) -> pd.DataFrame:
    """Simulate an asynchronous delayed-label stream joining to earlier predictions."""
    rng = np.random.default_rng(random_state)
    n = len(predictions_df)

    delays = np.clip(rng.exponential(scale=delay_hours_mean, size=n), 0.1, 72.0)

    label_stream = pd.DataFrame(
        {
            "request_id": [str(uuid.uuid4()) for _ in range(n)],
            "prediction": predictions_df["prediction"].to_numpy() if "prediction" in predictions_df else rng.choice([0, 1], size=n, p=[0.98, 0.02]),
            "actual_label": predictions_df["conversion_label"].to_numpy() if "conversion_label" in predictions_df else rng.choice([0, 1], size=n, p=[0.985, 0.015]),
            "simulated_delay_hours": np.round(delays, 2),
            "is_simulated": True,
        }
    )
    return label_stream
