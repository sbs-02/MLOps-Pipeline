# Iceberg interoperability report

- Source parquet: `data/raw/ga_sessions/2017Q3.parquet`
- PyIceberg table: `raw.ga_sessions_interop`
- Metadata location: `warehouse/iceberg_interop/warehouse/raw/ga_sessions_interop/metadata/00001-c586f7aa-ca3f-481c-8ac2-1ba3052ef723.metadata.json`
- Catalog database: `warehouse/iceberg_interop/catalog.db`
- Warehouse path: `warehouse/iceberg_interop/warehouse`

## Source Arrow metrics

- Rows: **74,368**
- Date range: **20170701 -> 20170801**
- Transaction rows: **1,074**

## DuckDB `iceberg_scan` metrics

- Rows: **74,368**
- Date range: **20170701 -> 20170801**
- Transaction rows: **1,074**

## Verification

- Row-count match: **True**
- Transaction-row match: **True**
- Date-range match: **True**

## Notes

- DuckDB reads the Iceberg table directly from its metadata file.
- Direct `iceberg_scan` is read-only; DuckDB writes to Iceberg require an attached Iceberg REST catalog.
- This table contains a copy of 2017Q3 source rows for interoperability verification, not a replacement for the DuckLake raw table.
