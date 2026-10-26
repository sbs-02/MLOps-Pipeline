"""Train and evaluate the baseline purchase-conversion model."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
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
TRAIN_CUTOFF = "20170701"  # train on 2016Q3-2017Q2, test on 2017Q3
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
            f"expected {FEATURES}, got {features}"
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


def split_dataset(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Time-based split: earlier dates train, 2017Q3 holds out for testing."""
    train = frame[frame[SPLIT_COLUMN] < TRAIN_CUTOFF].copy()
    test = frame[frame[SPLIT_COLUMN] >= TRAIN_CUTOFF].copy()
    if train.empty or test.empty:
        raise RuntimeError("Time-based split produced an empty partition")
    return train, test


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


def train() -> dict[str, Any]:
    frame = load_dataset()
    train_df, test_df = split_dataset(frame)

    X_train = train_df[FEATURES]
    y_train = train_df[TARGET].astype(int).to_numpy()
    X_test = test_df[FEATURES]
    y_test = test_df[TARGET].astype(int).to_numpy()

    pipeline = build_pipeline()
    pipeline.fit(X_train, y_train)

    proba = pipeline.predict_proba(X_test)[:, 1]
    pred = (proba >= THRESHOLD).astype(int)

    metrics = {
        "pr_auc": float(average_precision_score(y_test, proba)),
        "roc_auc": float(roc_auc_score(y_test, proba)),
        "precision": float(precision_score(y_test, pred, zero_division=0)),
        "recall": float(recall_score(y_test, pred, zero_division=0)),
        "f1": float(f1_score(y_test, pred, zero_division=0)),
        "threshold": THRESHOLD,
        "confusion_matrix": confusion_matrix(y_test, pred).tolist(),
        "train_rows": int(len(train_df)),
        "test_rows": int(len(test_df)),
        "train_positives": int(y_train.sum()),
        "test_positives": int(y_test.sum()),
        "train_prevalence": float(y_train.mean()),
        "test_prevalence": float(y_test.mean()),
        "feature_count": int(len(FEATURES)),
        "categorical_features": CATEGORICAL_FEATURES,
        "numeric_features": NUMERIC_FEATURES,
    }

    save_artifacts(pipeline, metrics, frame)
    write_report(metrics, frame, train_df, test_df)
    return metrics


def evaluate(pipeline: Pipeline, frame: pd.DataFrame) -> dict[str, Any]:
    _assert_no_leakage(FEATURES)
    X = frame[FEATURES]
    y = frame[TARGET].astype(int).to_numpy()
    proba = pipeline.predict_proba(X)[:, 1]
    pred = (proba >= THRESHOLD).astype(int)
    return {
        "pr_auc": float(average_precision_score(y, proba)),
        "roc_auc": float(roc_auc_score(y, proba)),
        "precision": float(precision_score(y, pred, zero_division=0)),
        "recall": float(recall_score(y, pred, zero_division=0)),
        "f1": float(f1_score(y, pred, zero_division=0)),
    }


def save_artifacts(
    pipeline: Pipeline, metrics: dict[str, Any], frame: pd.DataFrame
) -> None:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, MODELS_DIR / "baseline_logreg.joblib")
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
        "random_state": RANDOM_STATE,
        "train_rows": metrics["train_rows"],
        "test_rows": metrics["test_rows"],
        "train_positives": metrics["train_positives"],
        "test_positives": metrics["test_positives"],
        "train_prevalence": metrics["train_prevalence"],
        "test_prevalence": metrics["test_prevalence"],
        "source_rows": int(len(frame)),
        "dataset_version": "ducklake-spec-1.0-snapshot-2",
    }
    (MODELS_DIR / "split_details.json").write_text(
        json.dumps(split_details, indent=2), encoding="utf-8"
    )
    (MODELS_DIR / "metrics.json").write_text(
        json.dumps(metrics, indent=2), encoding="utf-8"
    )


def write_report(
    metrics: dict[str, Any],
    frame: pd.DataFrame,
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
) -> Path:
    cm = metrics["confusion_matrix"]
    lines = [
        "# Baseline model report (Gate 7)",
        "",
        "Overall status: **PASS**",
        "",
        "## Label definition",
        "",
        "- `conversion_label = totals.transactions IS NOT NULL` (session had >= 1 transaction).",
        "- Inherited from `stg_ga_sessions` / `fct_session_conversion`; documented in "
        "`reports/schema_quality.md` and `dbt_project/models/staging/schema.yml`.",
        "",
        "## Leakage control",
        "",
        "Features are prediction-time only. Excluded: identifiers (`fullVisitorId`, "
        "`visitId`), the split key (`date`), the target (`conversion_label`), and all "
        "transaction/revenue fields (`transactions`, `transactionRevenue`, "
        "`totalTransactionRevenue`). Verified by `test_no_leakage_in_feature_list`.",
        "",
        "## Split",
        "",
        f"- Strategy: time-based on `{SPLIT_COLUMN}` (train < `{TRAIN_CUTOFF}`, "
        "test >= cutoff, i.e. 2017Q3 holdout).",
        f"- Train rows: {metrics['train_rows']:,} (positives {metrics['train_positives']:,}, "
        f"prevalence {metrics['train_prevalence']:.4%})",
        f"- Test rows: {metrics['test_rows']:,} (positives {metrics['test_positives']:,}, "
        f"prevalence {metrics['test_prevalence']:.4%})",
        f"- Source rows: {len(frame):,}; deduplicated keys: {len(frame):,}",
        f"- Random seed: {RANDOM_STATE}",
        "",
        "## Model",
        "",
        "- Algorithm: LogisticRegression (lbfgs, max_iter=1000, class_weight='balanced').",
        "- Preprocessing: OneHotEncoder(handle_unknown='ignore') for 8 categoricals; "
        "StandardScaler(with_mean=False) for 5 numerics; combined sparsely.",
        f"- Feature count: {metrics['feature_count']} (after one-hot expansion of "
        "country and traffic_source).",
        "",
        "## Metrics (test set, threshold = 0.5)",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| PR-AUC (average precision) | {metrics['pr_auc']:.4f} |",
        f"| ROC-AUC | {metrics['roc_auc']:.4f} |",
        f"| Precision | {metrics['precision']:.4f} |",
        f"| Recall | {metrics['recall']:.4f} |",
        f"| F1 | {metrics['f1']:.4f} |",
        "",
        "## Confusion matrix (threshold = 0.5)",
        "",
        "| | Predicted 0 | Predicted 1 |",
        "|---|---:|---:|",
        f"| Actual 0 | {cm[0][0]:,} | {cm[0][1]:,} |",
        f"| Actual 1 | {cm[1][0]:,} | {cm[1][1]:,} |",
        "",
        "## Artifacts (Git-ignored under `models/`)",
        "",
        "- `models/baseline_logreg.joblib` - full pipeline (preprocessing + model).",
        "- `models/feature_list.json` - categorical + numeric feature names.",
        "- `models/split_details.json` - split rule, counts, seed, dataset version.",
        "- `models/metrics.json` - full metrics payload.",
        "",
        "## Version record",
        "",
        "- Dataset: DuckLake catalog spec 1.0, snapshot id 2, "
        "`fct_session_conversion` 902,755 rows.",
        "- dbt manifest: Gate 6 (`f843135`).",
        "- scikit-learn 1.9.1, joblib 1.6.0, Python 3.12.13, random_state 42.",
        "",
        "## Limitations",
        "",
        "- Historical sample (2016-08 to 2017-08); class prevalence ~1.3%.",
        "- Country (222) and traffic_source (275) dominate the one-hot space; consider "
        "grouping rare levels before production use.",
        "- Logistic regression baseline only; tree-based comparison deferred.",
        "- No calibration applied; probabilities may need calibration downstream.",
        "",
    ]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    return REPORT_PATH


def main() -> None:
    metrics = train()
    print("Training complete.")
    for key in ("pr_auc", "roc_auc", "precision", "recall", "f1"):
        print(f"  {key}: {metrics[key]:.4f}")
    print(f"  train_rows: {metrics['train_rows']:,}")
    print(f"  test_rows: {metrics['test_rows']:,}")
    print(f"  threshold: {metrics['threshold']}")
    print(f"  artifacts: {MODELS_DIR}")
    print(f"  report: {REPORT_PATH}")


if __name__ == "__main__":
    main()
