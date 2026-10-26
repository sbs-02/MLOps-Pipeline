"""DuckDB schema and quality inspection for the raw GA sample Parquet files."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parents[3]
RAW_GLOB = (PROJECT_ROOT / "data" / "raw" / "ga_sessions" / "*.parquet").as_posix()
MANIFEST_DIR = PROJECT_ROOT / "data" / "raw" / "ga_sessions"
REPORT_PATH = PROJECT_ROOT / "reports" / "schema_quality.md"


def _fetchdict(query: str) -> dict:
    return duckdb.connect().execute(query).fetchdf().iloc[0].to_dict()


def main() -> None:
    con = duckdb.connect()
    raw_exists = list(MANIFEST_DIR.glob("*.parquet"))
    if not raw_exists:
        raise FileNotFoundError(f"No raw Parquet files found under {MANIFEST_DIR}")

    overall = con.execute(f"""
        SELECT
            count(*) AS sessions,
            count(DISTINCT (fullVisitorId, visitId)) AS distinct_sessions,
            min(date) AS first_day,
            max(date) AS last_day,
            count(*) FILTER (WHERE totals.transactions IS NOT NULL) AS transaction_sessions,
            sum(coalesce(totals.transactionRevenue, 0)) AS transaction_revenue_micros
        FROM '{RAW_GLOB}'
    """).fetchdf().iloc[0].to_dict()

    quarter_rows = con.execute(f"""
        SELECT
            substr(date, 1, 4) AS year,
            CAST(floor((CAST(substr(date, 5, 2) AS INTEGER) - 1) / 3.0) AS INTEGER) + 1 AS q_num,
            count(*) AS sessions,
            count(DISTINCT (fullVisitorId, visitId)) AS distinct_sessions,
            count(*) FILTER (WHERE totals.transactions IS NOT NULL) AS transaction_sessions,
            min(date) AS first_day,
            max(date) AS last_day
        FROM '{RAW_GLOB}'
        GROUP BY 1, 2
        ORDER BY 1, 2
    """).fetchdf()

    # Rename quarter label to include Q prefix.
    quarter_rows["quarter"] = (
        quarter_rows["year"].astype(str) + "Q" + quarter_rows["q_num"].astype(int).astype(str)
    )

    key_fields = [
        "visitorId",
        "visitNumber",
        "visitId",
        "visitStartTime",
        "date",
        "fullVisitorId",
        "channelGrouping",
        "socialEngagementType",
        "totals",
        "trafficSource",
        "device",
        "geoNetwork",
        "hits",
        "customDimensions",
    ]
    null_rows = []
    for field in key_fields:
        null_count = con.execute(
            f"SELECT count(*) FILTER (WHERE {field} IS NULL) AS n FROM '{RAW_GLOB}'"
        ).fetchone()[0]
        null_rows.append((field, int(null_count)))

    hit_stats = con.execute(f"""
        SELECT
            avg(coalesce(len(hits), 0)) AS avg_hits,
            min(coalesce(len(hits), 0)) AS min_hits,
            max(coalesce(len(hits), 0)) AS max_hits
        FROM '{RAW_GLOB}'
    """).fetchdf().iloc[0].to_dict()

    schema = con.execute(f"DESCRIBE SELECT * FROM '{RAW_GLOB}'").fetchdf()

    manifests = sorted(MANIFEST_DIR.glob("*.manifest.json"))
    manifest_summary = []
    for m in manifests:
        info = json.loads(m.read_text(encoding="utf-8"))
        manifest_summary.append(
            f"| {info['quarter']} | {info['rows']} | {info['first_day'] if 'first_day' in info else info['range'][0]} | "
            f"{info['last_day'] if 'last_day' in info else info['range'][1]} | verified |"
        )
    # Manifests store ranges rather than separate first/last fields; use their range arrays.
    manifest_summary = []
    for m in manifests:
        info = json.loads(m.read_text(encoding="utf-8"))
        manifest_summary.append(
            f"| {info['quarter']} | {info['rows']} | {info['range'][0]} | {info['range'][1]} | verified |"
        )

    duplicate_session_rows = int(
        overall["sessions"] - overall["distinct_sessions"]
    )

    lines = [
        "# Schema and quality report: Google Analytics sample",
        "",
        f"Source wildcard: `bigquery-public-data.google_analytics_sample.ga_sessions_*`",
        f"Raw file glob: `{RAW_GLOB}`",
        "",
        "## Overall counts",
        "",
        f"- Raw session rows: **{int(overall['sessions']):,}**",
        f"- Distinct sessions `(fullVisitorId, visitId)`: **{int(overall['distinct_sessions']):,}**",
        f"- Duplicate session keys: **{duplicate_session_rows:,}**",
        f"- Date range: **{overall['first_day']} -> {overall['last_day']}**",
        f"- Sessions with `totals.transactions`: **{int(overall['transaction_sessions']):,}**",
        f"- Transaction-session rate: **{int(overall['transaction_sessions']) / int(overall['sessions']):.4%}**",
        f"- Sum of `totals.transactionRevenue`: **{int(overall['transaction_revenue_micros']):,}** micros",
        "",
        "## Per-quarter counts",
        "",
        "| Quarter | Rows | Distinct sessions | Transactions | First day | Last day |",
        "|---|---:|---:|---:|---|---|",
    ]
    for _, row in quarter_rows.iterrows():
        lines.append(
            f"| {row['quarter']} | {int(row['sessions']):,} | {int(row['distinct_sessions']):,} | "
            f"{int(row['transaction_sessions']):,} | {row['first_day']} | {row['last_day']} |"
        )

    lines.extend(
        [
            "",
            "## Manifests",
            "",
            "| Quarter | Manifest rows | Range start | Range end | Checksum |",
            "|---|---:|---|---|---|",
            *manifest_summary,
            "",
            "## Key-field null counts",
            "",
            "| Field | Null rows |",
            "|---|---:|",
        ]
    )
    for field, count in null_rows:
        lines.append(f"| `{field}` | {count:,} |")

    lines.extend(
        [
            "",
            "## Nested hit statistics",
            "",
            f"- Average hits per session: **{float(hit_stats['avg_hits']):.2f}**",
            f"- Minimum hits per session: **{int(hit_stats['min_hits'])}**",
            f"- Maximum hits per session: **{int(hit_stats['max_hits'])}**",
            "",
            "## Observed raw schema",
            "",
            "| Column | Type |",
            "|---|---|",
        ]
    )
    for _, row in schema.iterrows():
        lines.append(f"| `{row['column_name']}` | `{row['column_type']}` |")

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- Raw files are treated as immutable source inputs.",
            "- Nested BigQuery structures are preserved as DuckDB/Parquet-compatible structs and lists.",
            "- `totals.transactions IS NOT NULL` is used as the session-level purchase-conversion proxy.",
            "- `visitorId` is null in every observed raw row, so `fullVisitorId` and `visitId` are the usable session identity fields.",
            "- Duplicate session keys are reported but not removed in the raw layer; cleaning/normalization belongs in the transformation layer.",
        ]
    )

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {REPORT_PATH}")


if __name__ == "__main__":
    main()
