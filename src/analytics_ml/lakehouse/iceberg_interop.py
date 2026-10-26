"""Create and verify a local Apache Iceberg table from immutable raw Parquet data."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pyarrow.parquet as pq
from pyiceberg.catalog.sql import SqlCatalog

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SOURCE_PARQUET = PROJECT_ROOT / "data" / "raw" / "ga_sessions" / "2017Q3.parquet"
INTEROP_DIR = PROJECT_ROOT / "warehouse" / "iceberg_interop"
CATALOG_DB = INTEROP_DIR / "catalog.db"
WAREHOUSE_DIR = INTEROP_DIR / "warehouse"
TABLE_IDENTIFIER = "raw.ga_sessions_interop"
REPORT_PATH = PROJECT_ROOT / "reports" / "iceberg_interop.md"


def main() -> None:
    if not SOURCE_PARQUET.exists():
        raise FileNotFoundError(f"Source parquet not found: {SOURCE_PARQUET}")

    INTEROP_DIR.mkdir(parents=True, exist_ok=True)
    WAREHOUSE_DIR.mkdir(parents=True, exist_ok=True)

    source_arrow = pq.read_table(SOURCE_PARQUET)
    print(f"Read {source_arrow.num_rows:,} source rows from {SOURCE_PARQUET.name}")

    catalog = SqlCatalog(
        "local",
        uri=f"sqlite:///{CATALOG_DB.as_posix()}",
        warehouse=str(WAREHOUSE_DIR),
    )
    try:
        catalog.create_namespace("raw")
    except Exception as exc:
        print(f"namespace ready (create skipped): {exc}")

    try:
        catalog.drop_table(TABLE_IDENTIFIER)
        print("dropped existing interop table")
    except Exception:
        pass

    table = catalog.create_table(
        TABLE_IDENTIFIER,
        schema=source_arrow.schema,
    )
    table.append(source_arrow)
    metadata_location = table.metadata_location
    print(f"created Iceberg table: {metadata_location}")

    # DuckDB read-only scan of the Iceberg metadata committed by PyIceberg.
    con = duckdb.connect()
    con.execute("INSTALL iceberg; LOAD iceberg;")
    duck_rows = con.execute(
        f"SELECT count(*) AS rows, min(date) AS first_day, max(date) AS last_day, "
        f"count(*) FILTER (WHERE totals.transactions IS NOT NULL) AS transaction_rows "
        f"FROM iceberg_scan('{metadata_location}')"
    ).fetchdf().iloc[0].to_dict()

    # Derive the same aggregates from the Arrow table as the comparison baseline.
    source_transaction_rows = source_arrow.column("totals").to_pylist()
    source_transaction_count = sum(
        1 for row in source_transaction_rows if row is not None and row.get("transactions") is not None
    )
    source_first_day = min(source_arrow.column("date").to_pylist())
    source_last_day = max(source_arrow.column("date").to_pylist())

    con.close()

    lines = [
        "# Iceberg interoperability report",
        "",
        f"- Source parquet: `{SOURCE_PARQUET.as_posix()}`",
        f"- PyIceberg table: `{TABLE_IDENTIFIER}`",
        f"- Metadata location: `{metadata_location}`",
        f"- Catalog database: `{CATALOG_DB.as_posix()}`",
        f"- Warehouse path: `{WAREHOUSE_DIR.as_posix()}`",
        "",
        "## Source Arrow metrics",
        "",
        f"- Rows: **{source_arrow.num_rows:,}**",
        f"- Date range: **{source_first_day} -> {source_last_day}**",
        f"- Transaction rows: **{source_transaction_count:,}**",
        "",
        "## DuckDB `iceberg_scan` metrics",
        "",
        f"- Rows: **{int(duck_rows['rows']):,}**",
        f"- Date range: **{duck_rows['first_day']} -> {duck_rows['last_day']}**",
        f"- Transaction rows: **{int(duck_rows['transaction_rows']):,}**",
        "",
        "## Verification",
        "",
        f"- Row-count match: **{source_arrow.num_rows == int(duck_rows['rows'])}**",
        f"- Transaction-row match: **{source_transaction_count == int(duck_rows['transaction_rows'])}**",
        f"- Date-range match: **{source_first_day == duck_rows['first_day'] and source_last_day == duck_rows['last_day']}**",
        "",
        "## Notes",
        "",
        "- DuckDB reads the Iceberg table directly from its metadata file.",
        "- Direct `iceberg_scan` is read-only; DuckDB writes to Iceberg require an attached Iceberg REST catalog.",
        "- This table contains a copy of 2017Q3 source rows for interoperability verification, not a replacement for the DuckLake raw table.",
    ]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {REPORT_PATH}")


if __name__ == "__main__":
    main()
