# Drift and Model-Quality Monitoring Report (Gate 10)

Overall status: **PASS**

## 1. Monitoring Design & Semantics

- **Data Drift:** Evaluates changes in feature distributions $P(X)$ compared with the reference window (2016-08-01 through 2017-03-31; 632,648 sessions).
  - Continuous numerics: 2-sample Kolmogorov-Smirnov test (drift flag: $p < 0.05$) and Wasserstein distance.
  - Categoricals: Jensen-Shannon divergence (drift flag: distance $> 0.15$).
  - Dataset drift threshold: Declared when $\ge 30\%$ of features drift.
- **Concept Drift:** Evaluates degradation in input-target relationship $P(Y|X)$.
  - If labels are absent: Status is explicitly marked `labels_pending`.
  - If labels are observed: Evaluates F1 and PR-AUC; flags degradation if F1 drops by $> 15\%$ from baseline (0.3688).

## 2. Evaluation on 2017Q3 Historical Holdout (Real Data)

- Sample Size: 74,263 sessions
- Drifted Features: 8 / 13 (61.5%)
- Dataset Drift Detected: **True**
- Concept Drift Status: `evaluated`
- Test PR-AUC: 0.4026 | Test F1: 0.3688 (Baseline: 0.3688)
- Concept Degradation Flagged: **False**

### Feature-by-Feature Results (2017Q3 vs Reference)

| Feature | Type | Method | Metric Value | Drift Flag |
|---|---|---|---:|---|
| `visitNumber` | Numeric | kolmogorov_smirnov | KS stat: 0.0262, p: 6.4582e-40 | **YES** |
| `visits` | Numeric | kolmogorov_smirnov | KS stat: 0.0000, p: 1.0000e+00 | no |
| `hits` | Numeric | kolmogorov_smirnov | KS stat: 0.0154, p: 3.5991e-14 | **YES** |
| `pageviews` | Numeric | kolmogorov_smirnov | KS stat: 0.0175, p: 3.8568e-18 | **YES** |
| `time_on_site` | Numeric | kolmogorov_smirnov | KS stat: 0.0233, p: 6.7253e-32 | **YES** |
| `channelGrouping` | Categorical | jensen_shannon | JS dist: 0.1857 | **YES** |
| `device_category` | Categorical | jensen_shannon | JS dist: 0.1017 | no |
| `browser` | Categorical | jensen_shannon | JS dist: 0.0431 | no |
| `operating_system` | Categorical | jensen_shannon | JS dist: 0.1124 | no |
| `country` | Categorical | jensen_shannon | JS dist: 0.1542 | **YES** |
| `continent` | Categorical | jensen_shannon | JS dist: 0.0600 | no |
| `traffic_source` | Categorical | jensen_shannon | JS dist: 0.2879 | **YES** |
| `traffic_medium` | Categorical | jensen_shannon | JS dist: 0.2529 | **YES** |

## 3. Evaluation on Simulated Shifted Batch (Controlled Mobile Surge)

> **[NOTE]** The following batch was synthetically generated (`is_simulated = True`) to demonstrate alerting behavior under a sudden mobile traffic surge.

- Batch Size: 1,000 sessions
- Drifted Features Count: 9 / 13 (69.2%)
- Dataset Drift Detected: **True** (Threshold: 30.0%)
- Drifted Features: `hits, pageviews, time_on_site, channelGrouping, device_category, operating_system, country, traffic_source, traffic_medium`

### Delayed-Label Scenarios for Shifted Batch

1. **Pre-label Arrival State:** Status = `labels_pending`. Message: "Ground-truth conversion labels not yet observed; concept drift cannot be measured."
2. **Post-label Arrival State:** Status = `evaluated`. Batch F1 = 0.5455. F1 Drop Ratio = -47.9%. Concept Drift Detected = **False**.

## 4. Gate 11 Integration (Prometheus & Grafana Alerting)

- The outputs from `DriftDetector` will feed directly into Prometheus metrics:
  - `model_data_drift_detected` (gauge 0 or 1)
  - `model_drifted_features_count` (gauge)
  - `model_concept_drift_status` (gauge 0: pending, 1: healthy, 2: degraded)
  - `model_batch_f1_score` (gauge)
