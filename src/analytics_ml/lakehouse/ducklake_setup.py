"""Create and verify a local DuckLake catalog from the immutable raw Parquet files."""

from __future__ import annotations

from pathlib import Path

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parents[3]
RAW_GLOB = (PROJECT_ROOT / "data" / "raw" / "ga_sessions" / "*.parquet").as_posix()
WAREHOUSE_DIR = PROJECT_ROOT / "warehouse" / "ducklake"
CATALOG_PATH = WAREHOUSE_DIR / "catalog.duckdb"
DATA_PATH = WAREHOUSE_DIR / "data"


def create_or_load_table() -> dict[str, object]:
    WAREHOUSE_DIR.mkdir(parents=True, exist_ok=True)
    DATA_PATH.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect()
    con.execute("INSTALL ducklake; LOAD ducklake;")
    con.execute(
        f"ATTACH 'ducklake:{CATALOG_PATH.as_posix()}' AS ducklake "
        f"(DATA_PATH '{DATA_PATH.as_posix()}')"
    )
    con.execute("CREATE SCHEMA IF NOT EXISTS ducklake.raw")

    # Idempotent: if the table already exists, this statement does nothing.
    con.execute(
        f"""
        CREATE TABLE IF NOT EXISTS ducklake.raw.ga_sessions AS
        SELECT
            *,
            current_timestamp AS _ingested_at,
            'bigquery-public-data.google_analytics_sample.ga_sessions_*' AS _source,
            'data/raw/ga_sessions/*.parquet' AS _source_path
        FROM read_parquet('{RAW_GLOB}')
        """
    )
    con.execute("CHECKPOINT")

    metrics = con.execute(
        """
        SELECT
            count(*) AS sessions,
            count(DISTINCT (fullVisitorId, visitId)) AS distinct_sessions,
            count(*) FILTER (WHERE totals.transactions IS NOT NULL) AS transaction_sessions,
            min(date) AS first_day,
            max(date) AS last_day
        FROM ducklake.raw.ga_sessions
        """
    ).fetchdf().iloc[0].to_dict()
    con.close()
    return metrics


def verify_persistence() -> dict[str, object]:
    con = duckdb.connect()
    con.execute("INSTALL ducklake; LOAD ducklake;")
    con.execute(
        f"ATTACH 'ducklake:{CATALOG_PATH.as_posix()}' AS ducklake "
        f"(DATA_PATH '{DATA_PATH.as_posix()}')"
    )
    metrics = con.execute(
        "SELECT count(*) AS sessions, min(date) AS first_day, max(date) AS last_day "
        "FROM ducklake.raw.ga_sessions"
    ).fetchdf().iloc[0].to_dict()
    con.close()
    return metrics


def main() -> None:
    metrics = create_or_load_table()
    verification = verify_persistence()
    print("DuckLake raw table:")
    print(f"  sessions={int(metrics['sessions']):,}")
    print(f"  distinct_sessions={int(metrics['distinct_sessions']):,}")
    print(f"  transaction_sessions={int(metrics['transaction_sessions']):,}")
    print(f"  first_day={metrics['first_day']}")
    print(f"  last_day={metrics['last_day']}")
    print("Persistence verification:")
    print(f"  sessions={int(verification['sessions']):,}")
    print(f"  first_day={verification['first_day']}")
    print(f"  last_day={verification['last_day']}")
    print(f"Catalog: {CATALOG_PATH}")
    print(f"Data path: {DATA_PATH}")


if __name__ == "__main__":
    main()
