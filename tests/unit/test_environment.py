"""Environment reproducibility checks.

These tests assert that the running interpreter and the installed packages match
the versions pinned in ``pyproject.toml`` and recorded in ``requirements.lock``,
so that a rebuilt virtual environment can be compared against the verified one.

They are deliberately dependency-light: they only import modules that the
project already requires, and they never touch data/, warehouse/ or models/.
"""

from __future__ import annotations

import re
import sys
import tomllib
from importlib import import_module
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]

#: Packages pinned in pyproject.toml, mapped to their import name.
#: Distribution name -> import name (None means "do not import", e.g. tools).
PINNED_IMPORTS: dict[str, str] = {
    "duckdb": "duckdb",
    "pandas": "pandas",
    "numpy": "numpy",
    "pyarrow": "pyarrow",
    "pyiceberg": "pyiceberg",
    "google-cloud-bigquery": "google.cloud.bigquery",
    "scikit-learn": "sklearn",
    "pyyaml": "yaml",
    "ipykernel": "ipykernel",
    "pydantic": "pydantic",
    "fastapi": "fastapi",
    "uvicorn": "uvicorn",
    "prometheus-client": "prometheus_client",
    "evidently": "evidently",
    "bentoml": "bentoml",
    "dbt-core": "dbt",
    "dbt-duckdb": "dbt.adapters.duckdb",
    "pytest": "pytest",
}

PROJECT_MODULES = [
    "analytics_ml.ingestion.inspect_raw",
    "analytics_ml.lakehouse.ducklake_setup",
    "analytics_ml.lakehouse.iceberg_interop",
]


def _normalize(name: str) -> str:
    """Apply the PEP 503 name normalization used by pip."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _pyproject() -> dict:
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)


def _declared_pins() -> dict[str, str]:
    """Return {distribution: pinned_version} for every ``name==version`` entry."""
    project = _pyproject()["project"]
    requirements = list(project.get("dependencies", []))
    for extra in project.get("optional-dependencies", {}).values():
        requirements.extend(extra)

    pins: dict[str, str] = {}
    for requirement in requirements:
        base = requirement.split(";")[0].strip()
        base = base.split("[")[0].strip()
        if "==" not in base:
            continue
        name, pinned = base.split("==", 1)
        pins[_normalize(name)] = pinned.strip()
    return pins


def test_running_interpreter_matches_python_version_file() -> None:
    pinned = (PROJECT_ROOT / ".python-version").read_text(encoding="utf-8").strip()
    assert pinned, ".python-version is empty"
    assert sys.version.split()[0] == pinned, (
        f"running {sys.version.split()[0]} but .python-version pins {pinned}"
    )


def test_requires_python_allows_running_interpreter() -> None:
    requires_python = _pyproject()["project"]["requires-python"]
    major, minor = sys.version_info[:2]
    assert f">={major}.{minor}" in requires_python, (
        f"requires-python={requires_python!r} does not cover {major}.{minor}"
    )


def test_every_declared_dependency_is_pinned_exactly() -> None:
    project = _pyproject()["project"]
    requirements = list(project.get("dependencies", []))
    for extra in project.get("optional-dependencies", {}).values():
        requirements.extend(extra)

    unpinned = [req for req in requirements if "==" not in req]
    assert not unpinned, f"unpinned dependencies: {unpinned}"


@pytest.mark.parametrize("distribution,pinned", sorted(_declared_pins().items()))
def test_installed_version_matches_pin(distribution: str, pinned: str) -> None:
    try:
        installed = version(distribution)
    except PackageNotFoundError:  # pragma: no cover - failure path
        pytest.fail(f"{distribution} is declared but not installed")
    assert installed == pinned, f"{distribution}: installed {installed}, pinned {pinned}"


@pytest.mark.parametrize("distribution,module", sorted(PINNED_IMPORTS.items()))
def test_pinned_package_imports(distribution: str, module: str) -> None:
    import_module(module)


@pytest.mark.parametrize("module", PROJECT_MODULES)
def test_project_modules_import(module: str) -> None:
    import_module(module)


def test_duckdb_connects_in_memory() -> None:
    import duckdb

    with duckdb.connect(":memory:") as connection:
        assert connection.execute("SELECT 42").fetchone() == (42,)


def test_lockfile_has_no_absolute_paths() -> None:
    lock = PROJECT_ROOT / "requirements.lock"
    assert lock.is_file(), "requirements.lock is missing"
    text = lock.read_text(encoding="utf-8")
    # Composed at runtime so a repo-wide path scan does not flag this guard itself.
    forbidden = ("file" + ":///", "D" + ":\\", "D" + ":/")
    found = [token for token in forbidden if token in text]
    assert not found, f"lockfile contains absolute paths: {found}"


def test_lockfile_covers_every_pinned_dependency() -> None:
    lock_lines = (PROJECT_ROOT / "requirements.lock").read_text(encoding="utf-8").splitlines()
    locked = {
        _normalize(line.split("==")[0])
        for line in lock_lines
        if "==" in line and not line.startswith("#")
    }
    missing = sorted(set(_declared_pins()) - locked)
    assert not missing, f"declared but missing from requirements.lock: {missing}"
