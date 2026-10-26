# Schema/structure notes (from GA sample reference)
Target: bigquery-public-data.google_analytics_sample.ga_sessions_*
Key points from docs: nested fields (totals, trafficSource, device, geoNetwork, customDimensions, hits, fullVisitorId, visitId, visitNumber, visitStartTime, date).
Labels: transactions/transactionRevenue in totals or hits may indicate purchase; need session-level conversion label (any transaction in session?).
Quarter/year split feasible by date (YYYYMMDD) or visitStartTime.
