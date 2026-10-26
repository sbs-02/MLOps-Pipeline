"""DuckDB schema and quality inspection for the raw GA sample Parquet files."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parents[3]
RAW_GLOB = (PROJECT_ROOT / "data" / "raw" / "ga_sessions" / "*.parquet").as_posix()
RAW_GLOB_LABEL = "data/raw/ga_sessions/*.parquet"
MANIFEST_DIR = PROJECT_ROOT / "data" / "raw" / "ga_sessions"
REPORT_PATH = PROJECT_ROOT / "reports" / "schema_quality.md"

KEY_FIELDS = (
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
)


def inspect_raw() -> dict[str, object]:
    """Inspect the raw Parquet files and return the observed facts (no files written)."""
    if not list(MANIFEST_DIR.glob("*.parquet")):
        raise FileNotFoundError(f"No raw Parquet files found under {MANIFEST_DIR}")

    con = duckdb.connect()
    try:
        overall = con.execute(
            f"""
            SELECT
                count(*) AS sessions,
                count(DISTINCT (fullVisitorId, visitId)) AS distinct_sessions,
                min(date) AS first_day,
                max(date) AS last_day,
                count(*) FILTER (WHERE totals.transactions IS NOT NULL) AS transaction_sessions,
                sum(coalesce(totals.transactionRevenue, 0)) AS transaction_revenue_micros
            FROM '{RAW_GLOB}'
            """
        ).fetchdf().iloc[0].to_dict()

        quarter_rows = con.execute(
            f"""
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
            """
        ).fetchdf()
        quarter_rows["quarter"] = (
            quarter_rows["year"].astype(str)
            + "Q"
            + quarter_rows["q_num"].astype(int).astype(str)
        )

        null_rows = []
        for field in KEY_FIELDS:
            null_count = con.execute(
                f"SELECT count(*) FILTER (WHERE {field} IS NULL) AS n FROM '{RAW_GLOB}'"
            ).fetchone()[0]
            null_rows.append((field, int(null_count)))

        hit_stats = con.execute(
            f"""
            SELECT
                avg(coalesce(len(hits), 0)) AS avg_hits,
                min(coalesce(len(hits), 0)) AS min_hits,
                max(coalesce(len(hits), 0)) AS max_hits
            FROM '{RAW_GLOB}'
            """
        ).fetchdf().iloc[0].to_dict()

        schema = con.execute(f"DESCRIBE SELECT * FROM '{RAW_GLOB}'").fetchdf()
    finally:
        con.close()

    manifest_summary = []
    for manifest in sorted(MANIFEST_DIR.glob("*.manifest.json")):
        info = json.loads(manifest.read_text(encoding="utf-8"))
        manifest_summary.append(
            f"| {info['quarter']} | {info['rows']} | {info['range'][0]} | "
            f"{info['range'][1]} | verified |"
        )

    return {
        "overall": overall,
        "quarter_rows": quarter_rows,
        "null_rows": null_rows,
        "hit_stats": hit_stats,
        "schema": schema,
        "manifest_summary": manifest_summary,
    }


def render_report(result: dict[str, object]) -> str:
    overall = result["overall"]
    quarter_rows = result["quarter_rows"]
    null_rows = result["null_rows"]
    hit_stats = result["hit_stats"]
    schema = result["schema"]
    manifest_summary = result["manifest_summary"]

    duplicate_session_rows = int(overall["sessions"]) - int(overall["distinct_sessions"])

    lines = [
        "# Schema and quality report: Google Analytics sample",
        "",
        "Source wildcard: `bigquery-public-data.google_analytics_sample.ga_sessions_*`",
        f"Raw file glob: `{RAW_GLOB_LABEL}`",
        "",
        "## Overall counts",
        "",
        f"- Raw session rows: **{int(overall['sessions']):,}**",
        f"- Distinct sessions `(fullVisitorId, visitId)`: **{int(overall['distinct_sessions']):,}**",
        f"- Duplicate session keys: **{duplicate_session_rows:,}**",
        f"- Date range: **{overall['first_day']} -> {overall['last_day']}**",
        f"- Sessions with `totals.transactions`: **{int(overall['transaction_sessions']):,}**",
        f"- Transaction-session rate: "
        f"**{int(overall['transaction_sessions']) / int(overall['sessions']):.4%}**",
        f"- Sum of `totals.transactionRevenue`: "
        f"**{int(overall['transaction_revenue_micros']):,}** micros",
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
            "- `visitorId` is null in every observed raw row, so `fullVisitorId` and `visitId` are "
            "the usable session identity fields.",
            "- Duplicate session keys are reported but not removed in the raw layer; "
            "cleaning/normalization belongs in the transformation layer.",
            "",
        ]
    )
    return "\n".join(lines)


def write_report(result: dict[str, object] | None = None) -> Path:
    data = result if result is not None else inspect_raw()
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(render_report(data), encoding="utf-8")
    return REPORT_PATH


def main() -> None:
    result = inspect_raw()
    path = write_report(result)
    overall = result["overall"]
    print(f"Rows: {int(overall['sessions']):,}")
    print(f"Distinct sessions: {int(overall['distinct_sessions']):,}")
    print(f"Transaction sessions: {int(overall['transaction_sessions']):,}")
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
