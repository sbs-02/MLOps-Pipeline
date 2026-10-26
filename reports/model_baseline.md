# Baseline model report (Gate 7)

Overall status: **PASS**

## Label definition

- `conversion_label = totals.transactions IS NOT NULL` (session had >= 1 transaction).
- Inherited from `stg_ga_sessions` / `fct_session_conversion`; documented in `reports/schema_quality.md` and `dbt_project/models/staging/schema.yml`.

## Leakage control

Features are prediction-time only. Excluded: identifiers (`fullVisitorId`, `visitId`), the split key (`date`), the target (`conversion_label`), and all transaction/revenue fields (`transactions`, `transactionRevenue`, `totalTransactionRevenue`). Verified by `test_no_leakage_in_feature_list`.

## Split

- Strategy: time-based on `date` (train < `20170701`, test >= cutoff, i.e. 2017Q3 holdout).
- Train rows: 828,492 (positives 10,462, prevalence 1.2628%)
- Test rows: 74,263 (positives 1,067, prevalence 1.4368%)
- Source rows: 902,755; deduplicated keys: 902,755
- Random seed: 42

## Model

- Algorithm: LogisticRegression (lbfgs, max_iter=1000, class_weight='balanced').
- Preprocessing: OneHotEncoder(handle_unknown='ignore') for 8 categoricals; StandardScaler(with_mean=False) for 5 numerics; combined sparsely.
- Feature count: 13 (after one-hot expansion of country and traffic_source).

## Metrics (test set, threshold = 0.5)

| Metric | Value |
|---|---:|
| PR-AUC (average precision) | 0.4018 |
| ROC-AUC | 0.9844 |
| Precision | 0.2216 |
| Recall | 0.9738 |
| F1 | 0.3610 |

## Confusion matrix (threshold = 0.5)

| | Predicted 0 | Predicted 1 |
|---|---:|---:|
| Actual 0 | 69,546 | 3,650 |
| Actual 1 | 28 | 1,039 |

## Artifacts (Git-ignored under `models/`)

- `models/baseline_logreg.joblib` - full pipeline (preprocessing + model).
- `models/feature_list.json` - categorical + numeric feature names.
- `models/split_details.json` - split rule, counts, seed, dataset version.
- `models/metrics.json` - full metrics payload.

## Version record

- Dataset: DuckLake catalog spec 1.0, snapshot id 2, `fct_session_conversion` 902,755 rows.
- dbt manifest: Gate 6 (`f843135`).
- scikit-learn 1.9.1, joblib 1.6.0, Python 3.12.13, random_state 42.

## Limitations

- Historical sample (2016-08 to 2017-08); class prevalence ~1.3%.
- Country (222) and traffic_source (275) dominate the one-hot space; consider grouping rare levels before production use.
- Logistic regression baseline only; tree-based comparison deferred.
- No calibration applied; probabilities may need calibration downstream.
