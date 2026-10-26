# Stage 1 summary
- Confirmed target: bigquery-public-data.google_analytics_sample.ga_sessions_*
- Saved official ref: reports/ga_sample_ref.html
- Created provenance placeholder: reports/provenance.json (quarterly/yearly split noted)
- Investigated common static mirrors; no obvious direct no-cost bulk CSV for GA3 ga_sessions_* found. Need to confirm legitimacy of any mirror before downloading.
- Recommendation: if only BigQuery export is viable, document access/cost implications and request explicit approval before proceeding. Do not run BigQuery queries in this session.

## Split strategy (explicit)
Training/evaluation and monitoring will use quarter/year based splits of session data by date/visitStartTime to enable drift detection between quarters and years, as requested. Label is session-level purchase conversion derived from transaction evidence.

## Temporal splits
As requested, design splits by year/quarter using date/visitStartTime from source. This affects: reference windows, holdout by time, drift comparison across periods.
