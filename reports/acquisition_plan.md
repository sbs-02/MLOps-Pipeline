# Dataset acquisition plan (approved Stage 1)
Priority order (no paid GCP):
1. Find official static export or well-documented mirror matching the exact ga_sessions_* schema.
2. Record: source URL, publisher, retrieval date, license/terms, file format/compression, checksums, date range, session count.
3. If none found, document fallback: BigQuery export path + access/cost implications + explicit approval required before use.
4. After download (raw), inspect schema, nested/repeated (hits, products, transactions), define session-level conversion label using transaction evidence, confirm features available at prediction time. Design quarter/year based splits.
5. Persist immutable raw in data/raw/, write 
reports/schema_quality_*.md and 
reports/provenance.json.

- Notebook location: notebooks/01_download_ga_sessions.ipynb (download and document provenance).


- After you download to data/raw/, run 02_ingest_schema_inspect.ipynb to generate schema_quality report and update provenance.json.

