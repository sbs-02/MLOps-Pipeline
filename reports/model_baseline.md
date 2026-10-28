# Baseline Model Report (Gate 8)

Overall status: **PASS**

## Intended Use

Session-level purchase-conversion prediction for the Google Analytics sample. Intended for local demonstration, offline baseline comparison, and drift-monitoring proof of concept. Non-production use only.

## Label Definition & Timing

- `conversion_label = (totals.transactions IS NOT NULL)` (session resulted in >= 1 transaction).
- All features represent information available up to or at the prediction point.
- Documented in `reports/decision_log.md` and `reports/schema_quality.md`.

## Leakage Control

Features are prediction-time only. Explicitly forbidden and excluded: identifiers (`fullVisitorId`, `visitId`), the split key (`date`), the target (`conversion_label`), and all transaction/revenue fields (`transactions`, `transactionRevenue`, `totalTransactionRevenue`). Verified by automated unit tests in `tests/unit/test_training.py`.

## Chronological Split Design (3-Way)

- **Strategy:** Strictly time-based partition on `date`.
- **Train Period:** 2016-08-01 -> 2017-03-31 (`date < 20170401`; 2016Q3, 2016Q4, 2017Q1) — 632,648 rows, 7,476 positives, prevalence 1.1817%.
- **Validation Period:** 2017-04-01 -> 2017-06-30 (`20170401 <= date < 20170701`; 2017Q2) — 195,844 rows, 2,986 positives, prevalence 1.5247%.
- **Test Period:** 2017-07-01 -> 2017-08-01 (`date >= 20170701`; 2017Q3 holdout) — 74,263 rows, 1,067 positives, prevalence 1.4368%.
- **Total Mart Rows:** 902,755 (deduplicated).
- **Random Seed:** 42.

## Model Comparison (Validation Set)

| Model | Val PR-AUC | Val ROC-AUC | Val Precision | Val Recall | Val F1 |
|---|---:|---:|---:|---:|---:|
| Logistic Regression (balanced) | 0.3871 | 0.9818 | 0.2338 | 0.9545 | 0.3756 |
| HistGradientBoosting (balanced) | 0.4906 | 0.9880 | 0.2551 | 0.9632 | 0.4034 |

*Decision:* Logistic Regression is selected as the primary serving model for its interpretability, lightweight artifact size, and fast inference latency in BentoML.

## Test Set Performance (Threshold = 0.5)

| Metric | Uncalibrated Value | Calibrated Value (Sigmoid) |
|---|---:|---:|
| PR-AUC (Average Precision) | 0.4026 | 0.4026 |
| ROC-AUC | 0.9838 | 0.9838 |
| Precision | 0.2278 | 0.4729 |
| Recall | 0.9691 | 0.2455 |
| F1 | 0.3688 | 0.3233 |

## Confusion Matrix (Test Set, Threshold = 0.5)

| | Predicted 0 | Predicted 1 |
|---|---:|---:|
| Actual 0 | 69,690 | 3,506 |
| Actual 1 | 33 | 1,034 |

## Saved Artifacts (Git-ignored under `models/`)

- `models/baseline_logreg.joblib`: Complete fitted scikit-learn Pipeline (preprocessing + Logistic Regression).
- `models/feature_schema.json`: Complete feature schema including allowed and forbidden columns.
- `models/feature_list.json`: Categorical and numeric feature lists.
- `models/split_details.json`: Exact chronological cutoffs, row counts, positives, and prevalence.
- `models/metrics.json`: Detailed evaluation metrics across train, validation, and test splits.
- `models/model_metadata.json`: Model version, training timestamp (UTC), dataset snapshot, and random seed.

## Limitations

1. **Historical Static Sample:** The dataset covers exactly 1 year and 1 day (August 2016 to August 2017).
2. **Partial Quarters:** 2016Q3 is missing July 2016; 2017Q3 contains only 32 days. Year-over-year or seasonal same-quarter comparisons are not possible.
3. **High Imbalance:** Only ~1.28% prevalence. Cost-weighted models prioritize recall; probability calibration should be used when interpreting probabilities directly.
4. **No Live Feedback:** Live labels are unavailable; simulated incoming batches and delayed labels must be used for drift demonstration in later gates.
