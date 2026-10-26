"""DuckLake integration tests: hermetic catalog lifecycle plus read-only warehouse checks."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import duckdb
import pytest

from analytics_ml.lakehouse import ducklake_setup as dl

RAW_DIR = dl.PROJECT_ROOT / "data" / "raw" / "ga_sessions"
SLICE_ROWS = 5_000


@pytest.fixture()
def hermetic_catalog(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the module at a temp catalog seeded from a small slice of the raw files."""
    sources = sorted(RAW_DIR.glob("*.parquet"))
    if not sources:
        pytest.skip("raw Parquet files are not available")

    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    slice_path = raw_dir / "slice.parquet"
    con = duckdb.connect()
    try:
        con.execute(
            f"COPY (SELECT * FROM read_parquet('{sources[0].as_posix()}') LIMIT {SLICE_ROWS}) "
            f"TO '{slice_path.as_posix()}' (FORMAT PARQUET)"
        )
    finally:
        con.close()

    warehouse = tmp_path / "warehouse"
    monkeypatch.setattr(dl, "WAREHOUSE_DIR", warehouse)
    monkeypatch.setattr(dl, "CATALOG_PATH", warehouse / "catalog.duckdb")
    monkeypatch.setattr(dl, "DATA_PATH", warehouse / "data")
    monkeypatch.setattr(dl, "RAW_GLOB", (raw_dir / "*.parquet").as_posix())
    return warehouse


def _connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    dl.load_extension(con)
    return con


def test_create_query_and_reopen_in_new_process(hermetic_catalog: Path) -> None:
    con = _connect()
    try:
        dl.attach(con)
        assert dl.ensure_raw_table(con) is True
        metrics = dl.raw_metrics(con)
        assert metrics["sessions"] == SLICE_ROWS
        assert metrics["distinct_sessions"] <= SLICE_ROWS
        assert dl.snapshot_count(con) >= 1
    finally:
        con.close()

    assert dl.CATALOG_PATH.exists()

    script = (
        "import sys\n"
        "import duckdb\n"
        "con = duckdb.connect()\n"
        "con.execute('INSTALL ducklake; LOAD ducklake;')\n"
        "con.execute(f\"ATTACH 'ducklake:{sys.argv[1]}' AS dl (READ_ONLY)\")\n"
        "print(con.execute('SELECT count(*) FROM dl.raw.ga_sessions').fetchone()[0])\n"
        "con.close()\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script, str(dl.CATALOG_PATH)],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == str(SLICE_ROWS)


def test_rerun_does_not_duplicate_rows(hermetic_catalog: Path) -> None:
    con = _connect()
    try:
        dl.attach(con)
        assert dl.ensure_raw_table(con) is True
        before = {
            "sessions": dl.raw_metrics(con)["sessions"],
            "snapshot_id": dl.snapshot_id(con),
            "snapshot_count": dl.snapshot_count(con),
        }

        assert dl.ensure_raw_table(con) is False
        after = {
            "sessions": dl.raw_metrics(con)["sessions"],
            "snapshot_id": dl.snapshot_id(con),
            "snapshot_count": dl.snapshot_count(con),
        }
    finally:
        con.close()

    assert after == before
    assert after["sessions"] == SLICE_ROWS


def test_schema_matches_source_plus_metadata_columns(hermetic_catalog: Path) -> None:
    con = _connect()
    try:
        dl.attach(con)
        dl.ensure_raw_table(con)
        lake_columns = [row[0] for row in con.execute(f"DESCRIBE {dl.TABLE}").fetchall()]
        raw_columns = [
            row[0]
            for row in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{dl.RAW_GLOB}')").fetchall()
        ]
    finally:
        con.close()

    assert lake_columns[: len(raw_columns)] == raw_columns
    assert lake_columns[len(raw_columns) :] == ["_ingested_at", "_source", "_source_path"]


def test_runtime_versions_are_recorded(hermetic_catalog: Path) -> None:
    con = _connect()
    try:
        dl.attach(con)
        dl.ensure_raw_table(con)
        versions = dl.runtime_versions(con)
    finally:
        con.close()

    assert versions["duckdb"] == duckdb.__version__
    assert versions["ducklake_extension_build"] not in ("", "unknown")
    assert versions["catalog_spec_version"] == "1.0"


@pytest.mark.skipif(
    not dl.CATALOG_PATH.exists(), reason="DuckLake warehouse catalog has not been built"
)
def test_warehouse_reconciles_with_raw_parquet() -> None:
    con = _connect()
    try:
        dl.attach(con, read_only=True)
        lake = dl.raw_metrics(con)
        raw = dl.raw_parquet_metrics(con)
        lake_quarters = dl.quarter_metrics(con, source="lake")
        raw_quarters = dl.quarter_metrics(con, source="raw")
        current_snapshot = dl.snapshot_id(con)
    finally:
        con.close()

    assert lake == raw
    assert lake == dl.EXPECTED
    assert lake_quarters == raw_quarters
    assert len(lake_quarters) == 5

    reopened = dl.verify_reopen()
    assert reopened["sessions"] == lake["sessions"]
    assert reopened["snapshot_id"] == current_snapshot


@pytest.mark.skipif(
    not dl.CATALOG_PATH.exists(), reason="DuckLake warehouse catalog has not been built"
)
def test_verification_report_has_no_absolute_paths() -> None:
    result = dl.run_verification()
    report = dl.render_verification_report(result)

    assert result["ok"] is True
    assert "D:\\" not in report
    assert "D:/" not in report
    assert "PASS" in report
