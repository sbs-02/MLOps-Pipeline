## Stage 1 investigation notes
- Official GA sample: https://support.google.com/analytics/answer/3437719 (BigQuery public dataset)
- Common mirrors: Kaggle has GA/GA4-related datasets; note provenance varies. Some Kaggle sets are derived from BigQuery sample; verify terms.
- Target: bigquery-public-data.google_analytics_sample.ga_sessions_* structure (UNNESTed hits/transactions). Prefer obtaining canonical structure if possible.
- Requirement: time-aware splits (quarters/years) for drift detection.

- Checked common direct links (no accessible static GA3 ga_sessions_* bulk CSV in obvious locations). GA sample is primarily BigQuery-based (GA3/GA4). 
- Plan: focus on documented no-cost paths. If no static export exists, explicitly document and request approval before any BigQuery export.

