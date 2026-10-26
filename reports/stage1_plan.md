# Stage 1 - Dataset acquisition & verification
Goal: Find legitimate no-cost source for bigquery-public-data.google_analytics_sample.ga_sessions_*, verify provenance/licensing/terms, inspect schema/date coverage, document and acquire locally (if possible without paid GCP queries).

Order:
1. Check official GA sample docs (https://support.google.com/analytics/answer/3437719) and related public references.
2. Search for static public export/mirror (archive.org, Kaggle-like or academic mirrors) with clear terms. Record publisher, dates, checksums.
3. If only BigQuery export viable, explicitly document access/cost implications and request approval before proceeding.
4. Inspect file formats/compression, schema (nested/repeated), date ranges, session counts, transaction fields. 
5. Preserve raw immutable; write schema report to 
reports/.
6. Update config with provenance; ensure no secrets/data committed.

Acceptance: provenance recorded, schema/row-quality report generated from observed data, ingestion repeatable.
