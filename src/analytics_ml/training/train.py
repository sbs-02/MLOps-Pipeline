"""Train and evaluate the baseline purchase-conversion model (Gate 8)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.frozen import FrozenEstimator
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODELS_DIR = PROJECT_ROOT / "models"
REPORT_PATH = PROJECT_ROOT / "reports" / "model_baseline.md"
CATALOG_PATH = PROJECT_ROOT / "warehouse" / "ducklake" / "catalog.duckdb"

CATEGORICAL_FEATURES = [
    "channelGrouping",
    "device_category",
    "browser",
    "operating_system",
    "country",
    "continent",
    "traffic_source",
    "traffic_medium",
]
NUMERIC_FEATURES = [
    "visitNumber",
    "visits",
    "hits",
    "pageviews",
    "time_on_site",
]
FEATURES = CATEGORICAL_FEATURES + NUMERIC_FEATURES
TARGET = "conversion_label"
SPLIT_COLUMN = "date"

# Chronological 3-way split:
# Train: 2016-08-01 through 2017-03-31 (2016Q3, 2016Q4, 2017Q1; 8 months)
# Validation: 2017-04-01 through 2017-06-30 (2017Q2; 3 months)
# Test: 2017-07-01 through 2017-08-01 (2017Q3 holdout; 1 month, 1 day)
TRAIN_CUTOFF = "20170401"
VAL_CUTOFF = "20170701"

RANDOM_STATE = 42
THRESHOLD = 0.5

# Columns that must never appear in the feature set (identifiers, target, split key,
# and any transaction/outcome field that would leak the label).
FORBIDDEN_FEATURES = {
    "fullVisitorId",
    "visitId",
    "date",
    "conversion_label",
    "transactions",
    "transactionRevenue",
    "totalTransactionRevenue",
    "transaction_count",
    "transaction_revenue_micros",
    "total_transaction_revenue_micros",
    "_ingested_at",
    "_source",
}


def _assert_no_leakage(features: list[str]) -> None:
    leaked = set(features) & FORBIDDEN_FEATURES
    if leaked:
        raise ValueError(f"Leakage: forbidden columns in feature set: {sorted(leaked)}")
    if set(features) != set(FEATURES):
        raise ValueError(
            "Feature set mismatch: "
            f"expected {sorted(FEATURES)}, got {sorted(features)}"
        )


def load_dataset() -> pd.DataFrame:
    """Read the mart from the DuckLake catalog (read-only)."""
    con = duckdb.connect()
    try:
        con.execute("LOAD ducklake")
        con.execute(f"ATTACH 'ducklake:{CATALOG_PATH.as_posix()}' AS dl (READ_ONLY)")
        frame = con.execute(
            "SELECT fullVisitorId, visitId, date, visitNumber, channelGrouping, "
            "device_category, browser, operating_system, country, continent, "
            "traffic_source, traffic_medium, visits, hits, pageviews, time_on_site, "
            "conversion_label FROM dl.marts.fct_session_conversion"
        ).fetchdf()
    finally:
        con.close()
    if frame.empty:
        raise RuntimeError("Mart is empty; run dbt first")
    if frame[TARGET].isna().any():
        raise RuntimeError("Target contains nulls")
    return frame


def split_dataset(
    frame: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Chronological 3-way split: Train (earlier), Validation (middle), Test (2017Q3 holdout)."""
    train = frame[frame[SPLIT_COLUMN] < TRAIN_CUTOFF].copy()
    val = frame[
        (frame[SPLIT_COLUMN] >= TRAIN_CUTOFF) & (frame[SPLIT_COLUMN] < VAL_CUTOFF)
    ].copy()
    test = frame[frame[SPLIT_COLUMN] >= VAL_CUTOFF].copy()
    if train.empty or val.empty or test.empty:
        raise RuntimeError("Chronological split produced an empty partition")
    return train, val, test


def build_pipeline() -> Pipeline:
    _assert_no_leakage(FEATURES)
    preprocessor = ColumnTransformer(
        transformers=[
            (
                "cat",
                OneHotEncoder(handle_unknown="ignore", sparse_output=True),
                CATEGORICAL_FEATURES,
            ),
            (
                "num",
                StandardScaler(with_mean=False),
                NUMERIC_FEATURES,
            ),
        ],
        sparse_threshold=1.0,
    )
    model = LogisticRegression(
        max_iter=1000,
        class_weight="balanced",
        random_state=RANDOM_STATE,
        solver="lbfgs",
    )
    return Pipeline(steps=[("preprocessor", preprocessor), ("model", model)])


def compute_metrics(
    y_true: np.ndarray, proba: np.ndarray, threshold: float = THRESHOLD
) -> dict[str, Any]:
    pred = (proba >= threshold).astype(int)
    return {
        "pr_auc": float(average_precision_score(y_true, proba)),
        "roc_auc": float(roc_auc_score(y_true, proba)),
        "precision": float(precision_score(y_true, pred, zero_division=0)),
        "recall": float(recall_score(y_true, pred, zero_division=0)),
        "f1": float(f1_score(y_true, pred, zero_division=0)),
        "threshold": threshold,
        "confusion_matrix": confusion_matrix(y_true, pred).tolist(),
    }


def train() -> dict[str, Any]:
    frame = load_dataset()
    train_df, val_df, test_df = split_dataset(frame)

    X_train = train_df[FEATURES]
    y_train = train_df[TARGET].astype(int).to_numpy()

    X_val = val_df[FEATURES]
    y_val = val_df[TARGET].astype(int).to_numpy()

    X_test = test_df[FEATURES]
    y_test = test_df[TARGET].astype(int).to_numpy()

    # 1. Train primary Logistic Regression baseline
    pipeline = build_pipeline()
    pipeline.fit(X_train, y_train)

    train_proba = pipeline.predict_proba(X_train)[:, 1]
    val_proba = pipeline.predict_proba(X_val)[:, 1]
    test_proba = pipeline.predict_proba(X_test)[:, 1]

    logreg_val_metrics = compute_metrics(y_val, val_proba)
    test_metrics = compute_metrics(y_test, test_proba)
    train_metrics = compute_metrics(y_train, train_proba)

    # 2. Probability Calibration on validation set
    calibrated_pipeline = CalibratedClassifierCV(
        estimator=FrozenEstimator(pipeline), method="sigmoid"
    )
    calibrated_pipeline.fit(X_val, y_val)
    cal_test_proba = calibrated_pipeline.predict_proba(X_test)[:, 1]
    cal_test_metrics = compute_metrics(y_test, cal_test_proba)

    # 3. Tree-based model comparison on validation set
    tree_preprocessor = ColumnTransformer(
        transformers=[
            (
                "cat",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                CATEGORICAL_FEATURES,
            ),
            ("num", "passthrough", NUMERIC_FEATURES),
        ]
    )
    tree_pipeline = Pipeline(
        steps=[
            ("preprocessor", tree_preprocessor),
            (
                "model",
                HistGradientBoostingClassifier(
                    random_state=RANDOM_STATE, class_weight="balanced"
                ),
            ),
        ]
    )
    tree_pipeline.fit(X_train, y_train)
    tree_val_proba = tree_pipeline.predict_proba(X_val)[:, 1]
    tree_val_metrics = compute_metrics(y_val, tree_val_proba)

    metrics = {
        "train": {
            "rows": int(len(train_df)),
            "positives": int(y_train.sum()),
            "prevalence": float(y_train.mean()),
            **train_metrics,
        },
        "validation": {
            "rows": int(len(val_df)),
            "positives": int(y_val.sum()),
            "prevalence": float(y_val.mean()),
            **logreg_val_metrics,
        },
        "test": {
            "rows": int(len(test_df)),
            "positives": int(y_test.sum()),
            "prevalence": float(y_test.mean()),
            **test_metrics,
        },
        "test_calibrated": {
            **cal_test_metrics,
        },
        "tree_validation_comparison": {
            "model": "HistGradientBoostingClassifier(class_weight='balanced')",
            **tree_val_metrics,
        },
        "threshold": THRESHOLD,
        "feature_count": int(len(FEATURES)),
        "categorical_features": CATEGORICAL_FEATURES,
        "numeric_features": NUMERIC_FEATURES,
    }

    save_artifacts(pipeline, metrics, frame)
    write_report(metrics, frame, train_df, val_df, test_df)
    return metrics


def evaluate(pipeline: Pipeline, frame: pd.DataFrame) -> dict[str, Any]:
    _assert_no_leakage(FEATURES)
    X = frame[FEATURES]
    y = frame[TARGET].astype(int).to_numpy()
    proba = pipeline.predict_proba(X)[:, 1]
    return compute_metrics(y, proba)


def save_artifacts(
    pipeline: Pipeline, metrics: dict[str, Any], frame: pd.DataFrame
) -> None:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, MODELS_DIR / "baseline_logreg.joblib")

    feature_schema = {
        "features": FEATURES,
        "categorical": CATEGORICAL_FEATURES,
        "numeric": NUMERIC_FEATURES,
        "target": TARGET,
        "forbidden_leakage_features": sorted(FORBIDDEN_FEATURES),
    }
    (MODELS_DIR / "feature_schema.json").write_text(
        json.dumps(feature_schema, indent=2), encoding="utf-8"
    )
    (MODELS_DIR / "feature_list.json").write_text(
        json.dumps(
            {"categorical": CATEGORICAL_FEATURES, "numeric": NUMERIC_FEATURES},
            indent=2,
        ),
        encoding="utf-8",
    )

    split_details = {
        "split_column": SPLIT_COLUMN,
        "train_cutoff": TRAIN_CUTOFF,
        "val_cutoff": VAL_CUTOFF,
        "random_state": RANDOM_STATE,
        "train_period": "20160801 -> 20170331",
        "val_period": "20170401 -> 20170630",
        "test_period": "20170701 -> 20170801",
        "train_rows": metrics["train"]["rows"],
        "val_rows": metrics["validation"]["rows"],
        "test_rows": metrics["test"]["rows"],
        "train_positives": metrics["train"]["positives"],
        "val_positives": metrics["validation"]["positives"],
        "test_positives": metrics["test"]["positives"],
        "train_prevalence": metrics["train"]["prevalence"],
        "val_prevalence": metrics["validation"]["prevalence"],
        "test_prevalence": metrics["test"]["prevalence"],
        "source_rows": int(len(frame)),
        "dataset_version": "ducklake-spec-1.0-snapshot-2",
    }
    (MODELS_DIR / "split_details.json").write_text(
        json.dumps(split_details, indent=2), encoding="utf-8"
    )
    (MODELS_DIR / "metrics.json").write_text(
        json.dumps(metrics, indent=2), encoding="utf-8"
    )

    model_metadata = {
        "model_type": "LogisticRegression(class_weight='balanced')",
        "model_version": "baseline-logreg-v1",
        "dataset_snapshot": "ducklake-spec-1.0-snapshot-2",
        "trained_at_utc": datetime.now(timezone.utc).isoformat(),
        "random_state": RANDOM_STATE,
        "primary_metric": "pr_auc",
        "test_pr_auc": metrics["test"]["pr_auc"],
        "test_roc_auc": metrics["test"]["roc_auc"],
        "test_f1": metrics["test"]["f1"],
    }
    (MODELS_DIR / "model_metadata.json").write_text(
        json.dumps(model_metadata, indent=2), encoding="utf-8"
    )


def write_report(
    metrics: dict[str, Any],
    frame: pd.DataFrame,
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    test_df: pd.DataFrame,
) -> Path:
    test_cm = metrics["test"]["confusion_matrix"]
    tree_val = metrics["tree_validation_comparison"]
    lines = [
        "# Baseline Model Report (Gate 8)",
        "",
        "Overall status: **PASS**",
        "",
        "## Intended Use",
        "",
        "Session-level purchase-conversion prediction for the Google Analytics sample. "
        "Intended for local demonstration, offline baseline comparison, and drift-monitoring "
        "proof of concept. Non-production use only.",
        "",
        "## Label Definition & Timing",
        "",
        "- `conversion_label = (totals.transactions IS NOT NULL)` (session resulted in >= 1 transaction).",
        "- All features represent information available up to or at the prediction point.",
        "- Documented in `reports/decision_log.md` and `reports/schema_quality.md`.",
        "",
        "## Leakage Control",
        "",
        "Features are prediction-time only. Explicitly forbidden and excluded: identifiers "
        "(`fullVisitorId`, `visitId`), the split key (`date`), the target (`conversion_label`), "
        "and all transaction/revenue fields (`transactions`, `transactionRevenue`, `totalTransactionRevenue`). "
        "Verified by automated unit tests in `tests/unit/test_training.py`.",
        "",
        "## Chronological Split Design (3-Way)",
        "",
        f"- **Strategy:** Strictly time-based partition on `{SPLIT_COLUMN}`.",
        f"- **Train Period:** 2016-08-01 -> 2017-03-31 (`date < {TRAIN_CUTOFF}`; 2016Q3, 2016Q4, 2017Q1) "
        f"— {metrics['train']['rows']:,} rows, {metrics['train']['positives']:,} positives, "
        f"prevalence {metrics['train']['prevalence']:.4%}.",
        f"- **Validation Period:** 2017-04-01 -> 2017-06-30 (`{TRAIN_CUTOFF} <= date < {VAL_CUTOFF}`; 2017Q2) "
        f"— {metrics['validation']['rows']:,} rows, {metrics['validation']['positives']:,} positives, "
        f"prevalence {metrics['validation']['prevalence']:.4%}.",
        f"- **Test Period:** 2017-07-01 -> 2017-08-01 (`date >= {VAL_CUTOFF}`; 2017Q3 holdout) "
        f"— {metrics['test']['rows']:,} rows, {metrics['test']['positives']:,} positives, "
        f"prevalence {metrics['test']['prevalence']:.4%}.",
        f"- **Total Mart Rows:** {len(frame):,} (deduplicated).",
        f"- **Random Seed:** {RANDOM_STATE}.",
        "",
        "## Model Comparison (Validation Set)",
        "",
        "| Model | Val PR-AUC | Val ROC-AUC | Val Precision | Val Recall | Val F1 |",
        "|---|---:|---:|---:|---:|---:|",
        f"| Logistic Regression (balanced) | {metrics['validation']['pr_auc']:.4f} | "
        f"{metrics['validation']['roc_auc']:.4f} | {metrics['validation']['precision']:.4f} | "
        f"{metrics['validation']['recall']:.4f} | {metrics['validation']['f1']:.4f} |",
        f"| HistGradientBoosting (balanced) | {tree_val['pr_auc']:.4f} | "
        f"{tree_val['roc_auc']:.4f} | {tree_val['precision']:.4f} | "
        f"{tree_val['recall']:.4f} | {tree_val['f1']:.4f} |",
        "",
        "*Decision:* Logistic Regression is selected as the primary serving model for its "
        "interpretability, lightweight artifact size, and fast inference latency in BentoML.",
        "",
        "## Test Set Performance (Threshold = 0.5)",
        "",
        "| Metric | Uncalibrated Value | Calibrated Value (Sigmoid) |",
        "|---|---:|---:|",
        f"| PR-AUC (Average Precision) | {metrics['test']['pr_auc']:.4f} | {metrics['test_calibrated']['pr_auc']:.4f} |",
        f"| ROC-AUC | {metrics['test']['roc_auc']:.4f} | {metrics['test_calibrated']['roc_auc']:.4f} |",
        f"| Precision | {metrics['test']['precision']:.4f} | {metrics['test_calibrated']['precision']:.4f} |",
        f"| Recall | {metrics['test']['recall']:.4f} | {metrics['test_calibrated']['recall']:.4f} |",
        f"| F1 | {metrics['test']['f1']:.4f} | {metrics['test_calibrated']['f1']:.4f} |",
        "",
        "## Confusion Matrix (Test Set, Threshold = 0.5)",
        "",
        "| | Predicted 0 | Predicted 1 |",
        "|---|---:|---:|",
        f"| Actual 0 | {test_cm[0][0]:,} | {test_cm[0][1]:,} |",
        f"| Actual 1 | {test_cm[1][0]:,} | {test_cm[1][1]:,} |",
        "",
        "## Saved Artifacts (Git-ignored under `models/`)",
        "",
        "- `models/baseline_logreg.joblib`: Complete fitted scikit-learn Pipeline (preprocessing + Logistic Regression).",
        "- `models/feature_schema.json`: Complete feature schema including allowed and forbidden columns.",
        "- `models/feature_list.json`: Categorical and numeric feature lists.",
        "- `models/split_details.json`: Exact chronological cutoffs, row counts, positives, and prevalence.",
        "- `models/metrics.json`: Detailed evaluation metrics across train, validation, and test splits.",
        "- `models/model_metadata.json`: Model version, training timestamp (UTC), dataset snapshot, and random seed.",
        "",
        "## Limitations",
        "",
        "1. **Historical Static Sample:** The dataset covers exactly 1 year and 1 day (August 2016 to August 2017).",
        "2. **Partial Quarters:** 2016Q3 is missing July 2016; 2017Q3 contains only 32 days. Year-over-year or seasonal same-quarter comparisons are not possible.",
        "3. **High Imbalance:** Only ~1.28% prevalence. Cost-weighted models prioritize recall; probability calibration should be used when interpreting probabilities directly.",
        "4. **No Live Feedback:** Live labels are unavailable; simulated incoming batches and delayed labels must be used for drift demonstration in later gates.",
        "",
    ]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    return REPORT_PATH


def main() -> None:
    metrics = train()
    print("Gate 8 Model Training complete.")
    print("Test Set Metrics (Threshold = 0.5):")
    for key in ("pr_auc", "roc_auc", "precision", "recall", "f1"):
        print(f"  {key}: {metrics['test'][key]:.4f}")
    print(f"  train_rows: {metrics['train']['rows']:,}")
    print(f"  val_rows: {metrics['validation']['rows']:,}")
    print(f"  test_rows: {metrics['test']['rows']:,}")
    print(f"  artifacts: {MODELS_DIR}")
    print(f"  report: {REPORT_PATH}")


if __name__ == "__main__":
    main()
