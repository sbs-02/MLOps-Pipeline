"""Smoke tests for the dbt project: debug, run, test against the DuckLake catalog."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import duckdb

REPO_ROOT = Path(__file__).resolve().parents[2]
DBT = REPO_ROOT / ".venv" / "Scripts" / "dbt.exe"
PROJECT_DIR = "dbt_project"
PROFILES_DIR = "."


def _run(*args: str, project: bool = True) -> subprocess.CompletedProcess[str]:
    command = [str(DBT), *args]
    if project:
        command += ["--project-dir", PROJECT_DIR, "--profiles-dir", PROFILES_DIR]
    return subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )


def test_dbt_version_reports_installed_versions() -> None:
    result = _run("--version", project=False)
    assert result.returncode == 0, result.stderr
    assert "1.12.6" in result.stdout
    assert "1.11.0" in result.stdout


def test_dbt_debug_connects_to_duckdb_and_ducklake() -> None:
    result = _run("debug")
    assert result.returncode == 0, result.stderr + result.stdout
    assert "All checks passed" in result.stdout


def test_dbt_run_builds_staging_view_in_ducklake() -> None:
    result = _run("run", "--select", "stg_ga_sessions")
    assert result.returncode == 0, result.stderr + result.stdout
    assert "PASS=1" in result.stdout


def test_dbt_test_passes_for_staging_model() -> None:
    result = _run("test", "--select", "stg_ga_sessions")
    assert result.returncode == 0, result.stderr + result.stdout
    assert "Completed successfully" in result.stdout


def test_staging_view_has_expected_row_count() -> None:
    con = duckdb.connect()
    try:
        con.execute("LOAD ducklake")
        con.execute("ATTACH 'ducklake:warehouse/ducklake/catalog.duckdb' AS dl (READ_ONLY)")
        count = con.execute("SELECT count(*) FROM dl.stg.stg_ga_sessions").fetchone()[0]
    finally:
        con.close()
    assert count == 903653
