# Environment record (Gate 3)

Verified on 2026-10-26. Regenerate this file only after an approved dependency change.

## Host

| Item | Value |
|---|---|
| OS | Windows 11 Pro (win_amd64) |
| Interpreter | CPython **3.12.13** (uv-managed build) |
| Virtualenv | `.venv/` (git-ignored) |
| Venv creator | uv 0.11.26 (`uv venv --python 3.12.13 --seed`) |
| pip | 26.2.2 |
| Build backend | setuptools 84.2.1 + wheel 0.48.0 |
| Package count | 207 distributions recorded in `requirements.lock` |

`python` on `PATH` is the system 3.12.10; the project must always be invoked through
`.\.venv\Scripts\python.exe`. `.python-version` pins 3.12.13 for uv.

## Why 3.12 and not 3.13

BentoML is a required component (Gate 9). BentoML 1.4.40 declares support for Python
3.9–3.12 only (PyPI classifiers, and its CI matrix at tag `v1.4.40` tests 3.9/3.11/3.12).
The previous `.venv` was 3.13.14, which no dependency officially supported for serving.
The environment was rebuilt on 3.12.13 so that every pinned dependency is officially
supported. Decision taken with user approval (Gate 3, D1 Option B).

## Direct dependencies

| Package | Pin | Notes |
|---|---|---|
| duckdb | 1.5.6 | 2.0.0 exists but is deferred (see below) |
| pandas | 3.0.6 | 3.1.0 released 2026-10-22; staying on the verified build |
| numpy | 2.5.4 | required by pandas ≥2.0.2 on 3.12 |
| pyarrow | 26.0.0 | parquet I/O |
| pyiceberg[sql-sqlite] | 0.12.0 | pulls SQLAlchemy 2.1.6 for `SqlCatalog` |
| google-cloud-bigquery | 3.46.1 | 3.46.2 available; acquisition is finished |
| scikit-learn | 1.9.1 | Gate 8 baseline |
| pyyaml | 6.0.3 | was declared but never installed before Gate 3 |
| ipykernel | 7.4.0 | notebook kernel |
| pydantic | 2.14.1 | shared by pyiceberg / fastapi / bentoml |
| dbt-core | 1.12.6 | pulls `dbt-core-experimental-parser` 2.0.8 |
| dbt-duckdb | 1.11.0 | upstream dev pins target dbt-core ≥1.12 |
| bentoml | 1.4.40 | Python 3.9–3.12 |
| evidently | 0.7.23 | pins plotly <6 (resolves 5.24.1) |
| prometheus-client | 0.26.0 | |
| fastapi | 0.162.0 | |
| uvicorn[standard] | 0.54.0 | |
| pytest / pytest-cov | 9.1.1 / 7.1.0 | |
| ruff / mypy / httpx | 0.17.2 / 2.4.0 / 0.28.1 | |

Notable transitives: scipy 1.18.1, statsmodels 0.15.0, litestar 2.25.0, starlette 1.10.0,
dbt-adapters 1.24.5, dbt-common 1.39.0, metricflow 0.213.0.

## Rebuild

```powershell
uv venv --python 3.12.13 --seed .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
.\.venv\Scripts\python.exe -m pytest tests/unit/test_environment.py -q
```

`requirements.lock` is platform-specific (Windows, cp312). On another OS, re-resolve
from `pyproject.toml` instead of reusing the lock.

## Verification performed

| Check | Command | Result |
|---|---|---|
| Interpreter | `.\.venv\Scripts\python.exe -VV` | `Python 3.12.13` |
| Dependency consistency | `python -m pip check` | `No broken requirements found.` |
| Environment tests | `python -m pytest tests/unit/test_environment.py -q` | 47 passed |
| dbt | `.\.venv\Scripts\dbt.exe --version` | Core 1.12.6, duckdb plugin 1.11.0 |
| BentoML | `python -m bentoml --version` | `1.4.40` |
| Lock fidelity | `pip freeze` vs `requirements.lock` | identical (207/207) |
| Fresh rebuild | new venv in `%TEMP%`, install lock + editable | identical set, 47 passed, `pip check` clean |

## Deferred and known limitations

- **DuckDB 2.0.0** (released 2026-10-21) is not used. Its Python client removes
  `execute().fetch_arrow_table()`, `.arrow()`, `.pl()` and `relation.fetchone()/fetchmany()`,
  and the DuckLake compatibility matrix lists DuckDB only up to 1.5.2. Upgrade is a
  Gate 4 decision with the existing catalog in scope.
- **Evidently 0.7.23 + pandas 3.0.6** is not a combination covered by upstream tests;
  the import is verified, full drift reports are exercised in Gate 10.
- **dbt-core 1.12.6** depends on a pre-release lineage package
  (`dbt-core-experimental-parser` 2.0.8). It is pinned in the lock.
- The lock does not carry hashes (`--require-hashes`). Adding hashes would need a
  separate approved change.
- A 2 MB leftover of the previous 3.13 venv remains at `.venv-stale-313/` because two
  orphaned Jupyter kernels still hold `python.exe` and native extensions open. It is
  locally excluded via `.git/info/exclude` and can be removed once those kernels exit.
