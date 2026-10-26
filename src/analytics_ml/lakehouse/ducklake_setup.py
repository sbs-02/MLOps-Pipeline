"""Create, reopen and verify a local DuckLake catalog from the immutable raw Parquet files."""

from __future__ import annotations

from pathlib import Path

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parents[3]
RAW_GLOB = (PROJECT_ROOT / "data" / "raw" / "ga_sessions" / "*.parquet").as_posix()
WAREHOUSE_DIR = PROJECT_ROOT / "warehouse" / "ducklake"
CATALOG_PATH = WAREHOUSE_DIR / "catalog.duckdb"
DATA_PATH = WAREHOUSE_DIR / "data"
REPORT_PATH = PROJECT_ROOT / "reports" / "ducklake_verification.md"

CATALOG_ALIAS = "ducklake"
TABLE = f"{CATALOG_ALIAS}.raw.ga_sessions"
SOURCE_TABLE = "bigquery-public-data.google_analytics_sample.ga_sessions_*"
SOURCE_PATH_LABEL = "data/raw/ga_sessions/*.parquet"

METRIC_NAMES = (
    "sessions",
    "distinct_sessions",
    "transaction_sessions",
    "first_day",
    "last_day",
)

# Expected raw-layer facts. Used for reconciliation, never to overwrite observations.
EXPECTED = {
    "sessions": 903_653,
    "distinct_sessions": 902_755,
    "transaction_sessions": 11_552,
    "first_day": "20160801",
    "last_day": "20170801",
}

_METRICS_SQL = """
    SELECT
        count(*) AS sessions,
        count(DISTINCT (fullVisitorId, visitId)) AS distinct_sessions,
        count(*) FILTER (WHERE totals.transactions IS NOT NULL) AS transaction_sessions,
        min(date) AS first_day,
        max(date) AS last_day
    FROM {relation}
"""

_QUARTER_SQL = """
    SELECT
        substr(date, 1, 4) AS year,
        CAST(floor((CAST(substr(date, 5, 2) AS INTEGER) - 1) / 3.0) AS INTEGER) + 1 AS q_num,
        count(*) AS sessions,
        count(DISTINCT (fullVisitorId, visitId)) AS distinct_sessions,
        count(*) FILTER (WHERE totals.transactions IS NOT NULL) AS transaction_sessions
    FROM {relation}
    GROUP BY 1, 2
    ORDER BY 1, 2
"""


def _format_metric(value: object) -> str:
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def load_extension(con: duckdb.DuckDBPyConnection) -> None:
    """Install (from the local extension cache) and load the DuckLake extension."""
    con.execute("INSTALL ducklake; LOAD ducklake;")


def attach(con: duckdb.DuckDBPyConnection, *, read_only: bool = False) -> None:
    """Attach the DuckLake catalog.

    ``DATA_PATH`` is only supplied when the catalog is being created. For an existing
    catalog the value stored in its own metadata is used, so the catalog is not
    re-coupled to the absolute path of the machine that created it.
    """
    catalog = CATALOG_PATH.as_posix()
    if read_only:
        con.execute(f"ATTACH 'ducklake:{catalog}' AS {CATALOG_ALIAS} (READ_ONLY)")
        return
    if CATALOG_PATH.exists():
        con.execute(f"ATTACH 'ducklake:{catalog}' AS {CATALOG_ALIAS}")
        return
    WAREHOUSE_DIR.mkdir(parents=True, exist_ok=True)
    DATA_PATH.mkdir(parents=True, exist_ok=True)
    con.execute(
        f"ATTACH 'ducklake:{catalog}' AS {CATALOG_ALIAS} "
        f"(DATA_PATH '{DATA_PATH.as_posix()}')"
    )


def _table_exists(con: duckdb.DuckDBPyConnection) -> bool:
    row = con.execute(
        """
        SELECT count(*)
        FROM duckdb_tables()
        WHERE database_name = ? AND schema_name = 'raw' AND table_name = 'ga_sessions'
        """,
        [CATALOG_ALIAS],
    ).fetchone()
    return bool(row and row[0])


def ensure_raw_table(con: duckdb.DuckDBPyConnection) -> bool:
    """Create the raw table if it is missing. Returns True when this call created it."""
    con.execute(f"CREATE SCHEMA IF NOT EXISTS {CATALOG_ALIAS}.raw")
    if _table_exists(con):
        return False
    con.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE} AS
        SELECT
            *,
            current_timestamp AS _ingested_at,
            '{SOURCE_TABLE}' AS _source,
            '{SOURCE_PATH_LABEL}' AS _source_path
        FROM read_parquet('{RAW_GLOB}')
        """
    )
    con.execute("CHECKPOINT")
    return True


def _metrics(con: duckdb.DuckDBPyConnection, relation: str) -> dict[str, object]:
    row = con.execute(_METRICS_SQL.format(relation=relation)).fetchdf().iloc[0].to_dict()
    return {
        "sessions": int(row["sessions"]),
        "distinct_sessions": int(row["distinct_sessions"]),
        "transaction_sessions": int(row["transaction_sessions"]),
        "first_day": str(row["first_day"]),
        "last_day": str(row["last_day"]),
    }


def raw_metrics(con: duckdb.DuckDBPyConnection) -> dict[str, object]:
    """Session metrics read from the DuckLake raw table."""
    return _metrics(con, TABLE)


def raw_parquet_metrics(con: duckdb.DuckDBPyConnection) -> dict[str, object]:
    """Session metrics read directly from the immutable raw Parquet files."""
    return _metrics(con, f"read_parquet('{RAW_GLOB}')")


def quarter_metrics(
    con: duckdb.DuckDBPyConnection, *, source: str = "lake"
) -> list[dict[str, object]]:
    """Per-quarter session metrics from the lake (``lake``) or the raw files (``raw``)."""
    relation = TABLE if source == "lake" else f"read_parquet('{RAW_GLOB}')"
    frame = con.execute(_QUARTER_SQL.format(relation=relation)).fetchdf()
    rows: list[dict[str, object]] = []
    for _, row in frame.iterrows():
        rows.append(
            {
                "quarter": f"{row['year']}Q{int(row['q_num'])}",
                "sessions": int(row["sessions"]),
                "distinct_sessions": int(row["distinct_sessions"]),
                "transaction_sessions": int(row["transaction_sessions"]),
            }
        )
    return rows


def snapshot_id(con: duckdb.DuckDBPyConnection) -> int:
    row = con.execute(f"SELECT id FROM ducklake_current_snapshot('{CATALOG_ALIAS}')").fetchone()
    return int(row[0]) if row else -1


def snapshot_count(con: duckdb.DuckDBPyConnection) -> int:
    row = con.execute(f"SELECT count(*) FROM ducklake_snapshots('{CATALOG_ALIAS}')").fetchone()
    return int(row[0]) if row else 0


def runtime_versions(con: duckdb.DuckDBPyConnection) -> dict[str, str]:
    """Record the exact DuckDB build and DuckLake catalog specification version."""
    extension = con.execute(
        "SELECT extension_version FROM duckdb_extensions() "
        "WHERE extension_name = 'ducklake'"
    ).fetchone()
    try:
        spec = con.execute(
            f"SELECT value FROM __ducklake_metadata_{CATALOG_ALIAS}.ducklake_metadata "
            "WHERE key = 'version'"
        ).fetchone()
    except duckdb.Error:
        spec = None
    return {
        "duckdb": duckdb.__version__,
        "ducklake_extension_build": str(extension[0]) if extension else "unknown",
        "catalog_spec_version": str(spec[0]) if spec else "unknown",
    }


def verify_reopen() -> dict[str, object]:
    """Read the table through a brand-new, read-only connection (persistence check)."""
    con = duckdb.connect()
    try:
        load_extension(con)
        attach(con, read_only=True)
        metrics = raw_metrics(con)
        metrics["snapshot_id"] = snapshot_id(con)
        return metrics
    finally:
        con.close()


def _reconcile(
    raw: dict[str, object], lake: dict[str, object]
) -> list[dict[str, object]]:
    rows = []
    for name in METRIC_NAMES:
        rows.append(
            {
                "metric": name,
                "raw_parquet": raw[name],
                "ducklake": lake[name],
                "match": raw[name] == lake[name],
            }
        )
    return rows


def run_verification(*, check_idempotency: bool = True) -> dict[str, object]:
    """Run the full Gate 4 verification and return the observed evidence."""
    con = duckdb.connect()
    try:
        load_extension(con)
        attach(con)
        created_now = ensure_raw_table(con)
        versions = runtime_versions(con)
        lake = raw_metrics(con)
        raw = raw_parquet_metrics(con)
        lake_quarters = quarter_metrics(con, source="lake")
        raw_quarters = quarter_metrics(con, source="raw")
        before = {
            "sessions": lake["sessions"],
            "snapshot_id": snapshot_id(con),
            "snapshot_count": snapshot_count(con),
        }
        if check_idempotency:
            created_again = ensure_raw_table(con)
            after = {
                "sessions": raw_metrics(con)["sessions"],
                "snapshot_id": snapshot_id(con),
                "snapshot_count": snapshot_count(con),
            }
        else:
            created_again = None
            after = dict(before)
    finally:
        con.close()

    reopened = verify_reopen()
    reconciliation = _reconcile(raw, lake)
    quarters_match = lake_quarters == raw_quarters
    matches_expected = all(lake[name] == EXPECTED[name] for name in METRIC_NAMES)

    return {
        "versions": versions,
        "created_now": created_now,
        "created_again": created_again,
        "lake": lake,
        "raw": raw,
        "reopened": reopened,
        "reconciliation": reconciliation,
        "quarters": [
            {**lq, "raw_sessions": rq["sessions"], "match": lq == rq}
            for lq, rq in zip(lake_quarters, raw_quarters, strict=True)
        ],
        "quarters_match": quarters_match,
        "idempotency": {
            "before": before,
            "after": after,
            "ok": before == after and created_again is False,
        },
        "matches_expected": matches_expected,
        "ok": (
            all(row["match"] for row in reconciliation)
            and quarters_match
            and reopened["sessions"] == lake["sessions"]
            and (before == after if check_idempotency else True)
        ),
        "catalog_path": CATALOG_PATH.relative_to(PROJECT_ROOT).as_posix()
        if CATALOG_PATH.is_relative_to(PROJECT_ROOT)
        else CATALOG_PATH.name,
    }


def render_verification_report(result: dict[str, object]) -> str:
    versions = result["versions"]
    lake = result["lake"]
    reopened = result["reopened"]
    idem = result["idempotency"]
    status = "PASS" if result["ok"] else "FAIL"

    lines = [
        "# DuckLake verification (Gate 4)",
        "",
        f"Overall status: **{status}**",
        "",
        "## Runtime versions",
        "",
        "| Component | Value |",
        "|---|---|",
        f"| DuckDB | `{versions['duckdb']}` |",
        f"| DuckLake extension build | `{versions['ducklake_extension_build']}` |",
        f"| DuckLake catalog spec | `{versions['catalog_spec_version']}` |",
        f"| Current snapshot id | `{reopened['snapshot_id']}` |",
        "",
        f"Catalog: `{result['catalog_path']}` (ignored by Git).",
        "",
        "## Reconciliation: raw Parquet vs DuckLake",
        "",
        "| Metric | Raw Parquet | DuckLake | Match |",
        "|---|---:|---:|---|",
    ]
    for row in result["reconciliation"]:
        lines.append(
            f"| `{row['metric']}` | {_format_metric(row['raw_parquet'])} | "
            f"{_format_metric(row['ducklake'])} | {'yes' if row['match'] else '**NO**'} |"
        )

    lines.extend(
        [
            "",
            "## Per-quarter reconciliation",
            "",
            "| Quarter | DuckLake sessions | Raw sessions | Match |",
            "|---|---:|---:|---|",
        ]
    )
    for row in result["quarters"]:
        lines.append(
            f"| {row['quarter']} | {row['sessions']:,} | {row['raw_sessions']:,} | "
            f"{'yes' if row['match'] else '**NO**'} |"
        )

    lines.extend(
        [
            "",
            "## Persistence",
            "",
            f"- Table created during this run: **{result['created_now']}**",
            f"- Fresh read-only connection sees: **{reopened['sessions']:,}** rows, "
            f"snapshot `{reopened['snapshot_id']}`",
            "",
            "## Idempotency (re-running the ingest)",
            "",
            f"- `ensure_raw_table` created a table on the second run: **{result['created_again']}**",
            f"- Before: rows={idem['before']['sessions']:,}, "
            f"snapshot={idem['before']['snapshot_id']}, "
            f"snapshots={idem['before']['snapshot_count']}",
            f"- After: rows={idem['after']['sessions']:,}, "
            f"snapshot={idem['after']['snapshot_id']}, "
            f"snapshots={idem['after']['snapshot_count']}",
            f"- No duplicate rows and no new snapshot: **{'yes' if idem['ok'] else 'NO'}**",
            "",
            "## Notes and limitations",
            "",
            "- Raw Parquet files are immutable inputs; the DuckLake table is a derived copy.",
            "- `CREATE TABLE IF NOT EXISTS` is skipped when the table is present, so re-running "
            "the ingest is a no-op and does not append rows.",
            "- The catalog stores an absolute `DATA_PATH` in its metadata. Re-attaching uses the "
            "stored value; relocating the repository requires re-attaching with an explicit "
            "`DATA_PATH` or rebuilding the catalog.",
            "- DuckLake 1.1 requires DuckDB >= 2.0.0, so this POC stays on DuckDB 1.5.6 with "
            "DuckLake spec 1.0. The upgrade is deferred until dbt and the serving stack are "
            "validated against DuckDB 2.0.",
            "- Time travel, snapshot expiry, merge and Iceberg interop are out of scope for this gate.",
            "",
        ]
    )
    return "\n".join(lines)


def write_verification_report(result: dict[str, object] | None = None) -> Path:
    data = result if result is not None else run_verification()
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(render_verification_report(data), encoding="utf-8")
    return REPORT_PATH


# Backwards-compatible wrappers kept for the module's original public surface.
def create_or_load_table() -> dict[str, object]:
    con = duckdb.connect()
    try:
        load_extension(con)
        attach(con)
        ensure_raw_table(con)
        return raw_metrics(con)
    finally:
        con.close()


def verify_persistence() -> dict[str, object]:
    return verify_reopen()


def main() -> None:
    result = run_verification()
    path = write_verification_report(result)
    versions = result["versions"]
    lake = result["lake"]
    print("DuckLake raw table:")
    print(f"  sessions={lake['sessions']:,}")
    print(f"  distinct_sessions={lake['distinct_sessions']:,}")
    print(f"  transaction_sessions={lake['transaction_sessions']:,}")
    print(f"  first_day={lake['first_day']}")
    print(f"  last_day={lake['last_day']}")
    print("Persistence verification:")
    print(f"  sessions={result['reopened']['sessions']:,}")
    print(f"  snapshot_id={result['reopened']['snapshot_id']}")
    print("Idempotency:")
    print(f"  re-run created table: {result['created_again']}")
    print(f"  unchanged: {result['idempotency']['ok']}")
    print("Versions:")
    for key, value in versions.items():
        print(f"  {key}={value}")
    print(f"Overall: {'PASS' if result['ok'] else 'FAIL'}")
    print(f"Catalog: {CATALOG_PATH}")
    print(f"Data path: {DATA_PATH}")
    print(f"Report: {path}")


if __name__ == "__main__":
    main()
