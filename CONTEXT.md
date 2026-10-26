# CONTEXT.md

## Project identity

**Working title:** Local Analytics-to-ML Drift Monitoring Platform  
**Owner role:** Associate Software Engineer at Ycotek  
**Primary environment:** Windows with Docker Desktop and WSL2 recommended  
**Implementation assistant:** OpenCode  
**Project type:** Local-first, open-source data engineering and MLOps proof of concept

This file is the persistent project context for OpenCode. Read it before inspecting or changing the repository. `IMPLEMENTATION_GUIDE.md` contains the staged implementation plan and acceptance criteria.

## Mission

Build a reproducible, local-first platform that obtains the public Google Analytics sample dataset, stores and transforms it using DuckDB/DuckLake and Apache Iceberg, creates a leakage-safe purchase-conversion ML dataset, trains and serves a model locally, monitors data drift and model/concept drift, and orchestrates approved retraining with Airflow.

The user has approved these requirements:

- Windows development environment; Docker Desktop is available.
- Include both DuckLake and Apache Iceberg, with clearly explained roles and a tested interoperability path.
- Investigate both static public downloads and other legitimate no-cost acquisition paths. Avoid paid GCP usage.
- Initial ML use case: session-level purchase conversion prediction.
- Recommend a practical monitoring design that distinguishes data drift from concept drift.
- Manual approval begins from a Grafana alert and is performed through a local approval interface.
- Run the platform locally where feasible.
- Prefer open-source tools and libraries with licenses checked.
- OpenCode should use a hybrid workflow: inspect and plan, explain decisions, implement approved stages, test, report, and request approval before consequential changes.
- Demonstrate both historical reprocessing and clearly labeled simulated incoming batches/drift.
- Build both a model prediction API and an approval/orchestration API or integration.

## Core principles

1. **Local-first, no paid GCP dependency.** Do not run BigQuery queries, create cloud resources, or assume GCP credentials are available. Do not use a cloud service if a local/open-source option is adequate.
2. **Evidence before claims.** Never claim a dataset was downloaded, an API is running, a test passed, a license was verified, or a service is compatible without checking.
3. **Incremental implementation.** Inspect the existing repository first. Preserve useful work. Do not overwrite or delete user files without asking.
4. **Approval gates.** Present a short plan before each major stage. Ask before destructive actions, broad dependency upgrades, significant architecture changes, or model promotion/deployment. After each stage, run appropriate tests and report exact outcomes.
5. **No fake production claims.** This is a local proof of concept, not a production-ready system. Label simulated data and simulated drift clearly.
6. **Security by default.** Never commit secrets, credentials, tokens, `.env` files, local datasets, model artifacts, or private logs. Bind local services to localhost unless there is an explicitly approved reason otherwise. Do not expose unauthenticated control endpoints to a network.
7. **Reproducibility.** Pin compatible dependencies, record tool versions, keep setup commands in documentation, use deterministic seeds where applicable, and make pipeline tasks idempotent.
8. **Keep scope lean.** Do not add a frontend framework, a model registry, Kubernetes, a cloud service, or a second orchestrator unless there is a demonstrated need and the user approves.
9. **Open source and licensing.** Prefer actively maintained open-source software. Check each direct dependency's license and relevant transitive dependencies. Record licenses and links in a dependency/license inventory. Do not assume a product's entire ecosystem or hosted service is open source merely because its library is.
10. **Use current documentation.** API shapes, package compatibility, and project defaults change. Verify against official documentation for the versions actually selected.

## Approved conceptual architecture

```text
Verified public sample source / approved no-cost export
                     |
                     v
         Local source files (raw, immutable)
                     |
                     v
      DuckDB ingestion and schema inspection
                     |
                     v
    DuckLake primary local analytical lakehouse
                     |
                     +---- Iceberg interoperability proof
                     |     (separate table/catalog path;
                     |      prove read/write requirements)
                     v
       dbt SQL transformations and tests
       staging -> intermediate -> feature model
                     |
                     v
   Leakage-safe session conversion training set
                     |
                     v
       scikit-learn baseline and evaluation
                     |
                     v
            Versioned model artifact
                     |
                     v
        BentoML local prediction HTTP API
                     |
          prediction/event/label records
                     |
                     v
       Drift and model-quality evaluation
                     |
              metrics export
                     v
            Prometheus -> Grafana
                     |
               drift alert
                     v
      Local approval UI / protected API
                     |
        explicit, auditable authorization
                     |
                     v
          Airflow approved DAG run
                     |
       ingest -> transform -> train candidate
                     |
       validate candidate vs current model
                     |
         pass: promote; fail: keep old model
```

## Technology direction (provisional until compatibility checks pass)

- **Python:** application, ingestion, evaluation, and API integration code.
- **DuckDB:** local analytical SQL engine.
- **DuckLake:** primary local lakehouse/table-management path.
- **Apache Iceberg:** separate interoperability/format-validation path. Do not assume DuckLake and Iceberg are the same format.
- **dbt:** SQL transformation models, lineage and data tests. Prefer a compatible dbt Core + `dbt-duckdb` combination unless official compatibility research demonstrates a better suitable choice. Do not mix the dbt Fusion engine and adapters without verifying support.
- **scikit-learn:** initial interpretable baseline classifier.
- **BentoML:** model packaging and local prediction service.
- **Evidently or another verified open-source library:** candidate for drift and model-quality reports. Verify license, APIs, metric semantics, and Prometheus integration.
- **Prometheus:** metrics scraping/storage.
- **Grafana OSS:** dashboards, alert rules, contact points and alert links.
- **Apache Airflow:** DAG scheduling and execution in Docker Compose for local development.
- **FastAPI:** only if a separate approval/control API is needed. BentoML serves the prediction API; avoid duplicating that responsibility.
- **pytest:** automated tests.
- **Docker Desktop + WSL2:** local multi-service environment, subject to machine capability.

These are proposed components, not a promise that every current version is compatible. OpenCode must select and pin a tested version matrix before implementation.

## Data and ML assumptions

The source requested is `bigquery-public-data.google_analytics_sample.ga_sessions_*`. It is a public BigQuery sample, but public visibility does not mean that a direct wildcard-table file download exists. First investigate official Google sample documentation, static mirrors or archives, and other legitimate no-cost paths. Verify provenance, licensing/terms, schema, date coverage, completeness and checksums where possible. Do not silently substitute a different dataset. If a BigQuery export is the only viable route, explain the access and cost implications and ask before using it.

The initial target is **session-level purchase conversion**. Define the label from transaction evidence actually present in the sample schema. Inspect the data before writing assumptions. Features must be available at prediction time. Exclude direct label fields, post-conversion fields, and other leakage sources from model inputs. Split by time or visitor/session grouping where appropriate; justify the chosen split and assess repeat-visitor leakage. Document class imbalance and choose suitable metrics, including precision, recall, PR-AUC and ROC-AUC where appropriate.

Retention and revenue prediction are not the initial objective. They can be discussed as future extensions only after checking whether the source supports valid labels.

## Drift semantics

- **Data drift:** changes in input-feature distributions compared with a defined reference/training period. Drift is a signal, not proof that the model is worse.
- **Concept drift:** changes in the relationship between features and target. Reliable evidence normally requires observed ground-truth outcomes over time and model-quality evaluation.
- Track predictions with timestamps and stable record/session identifiers where appropriate, then join later labels when available.
- If labels are absent or delayed, report concept drift as unmeasurable or pending rather than claiming it was detected. Prediction-distribution change alone is not confirmed concept drift.
- Define thresholds from validation/baseline analysis and document false-positive trade-offs; do not select arbitrary thresholds without explanation.
- Simulated drift and synthetic batches must be labeled as simulated in dashboards, logs, reports and demos.

## Human approval and control-plane rules

Grafana alerts must not themselves trigger retraining. Alert acknowledgment is not approval. Opening a link or receiving a webhook is not approval.

The preferred flow is:

1. Monitoring produces an alert with a unique alert/event identifier and evidence.
2. Grafana provides a link to a local approval page.
3. The page displays alert details, target environment, candidate action, current model version, and a clear approve/reject choice.
4. The approval API validates the decision, records who/what approved it, timestamp, alert ID, reason, expiry and state, and prevents duplicate/replayed approvals.
5. Only an explicitly approved, valid, unexpired request can authorize the intended Airflow DAG run.
6. Airflow executes an idempotent run with a unique run/approval reference.
7. The candidate model is evaluated before promotion. Failure leaves the currently serving model unchanged.
8. Approval and run history are auditable.

For a single-user local POC, explain the limitations of local authentication. Do not describe a shared-secret URL as strong identity verification. Keep the API bound to localhost, use a random local secret or appropriate session protection where justified, validate request origin/CSRF where browser forms are used, and never expose the endpoint externally. Use Airflow's supported API for the selected version, or a documented Airflow task/sensor pattern; do not invent endpoints. If Grafana's built-in links and notification capabilities cannot provide a safe approval UX alone, implement the local approval page/API as the explicit decision point.

## API requirements

### Prediction API (required; served by BentoML)

Define and document a versioned request/response schema. Expected conceptual endpoints:

- `POST /predict` (or the actual route generated by the selected BentoML version): validate session features and return conversion probability, predicted class, model version and request/correlation ID.
- Health/readiness endpoint(s) supported by the chosen BentoML setup.
- Input validation, stable output schema, useful 4xx/5xx errors, bounded request size, structured logs and tests.
- Do not log raw sensitive payloads unnecessarily. Do not claim the probability is calibrated unless calibration is evaluated.

### Approval/control API (required, implementation choice)

A small FastAPI service may implement routes such as:

- `GET /approvals/{approval_id}`: show the pending request details in the local UI.
- `POST /approvals/{approval_id}/decision`: accept an explicit approve/reject decision with validation.
- A protected internal operation to authorize or trigger the supported Airflow operation after approval.

These are conceptual route names, not mandated API contracts. Define the exact schema and authentication approach in the implementation plan. Do not create an open endpoint that lets arbitrary callers trigger arbitrary DAGs. Use an allowlist of DAG IDs and validated parameters. Never store secrets in the database in plaintext if avoidable.

## Operational requirements

- Use `.env.example` with placeholders; `.env` stays ignored.
- Include `.gitignore` for data, logs, secrets, local DB/catalog files, model artifacts, cache, and generated reports as appropriate.
- Include a clear `docker compose config`/health-check validation step.
- Persist only required local state in documented volumes.
- Provide cleanup instructions that distinguish safe generated artifacts from user data.
- Add resource notes for RAM, disk, CPU, and Docker Desktop/WSL2.
- Include a dependency/license inventory with official links.
- Include a model card or concise model report: purpose, dataset provenance, label definition, features, split, metrics, limitations and intended non-production use.

## Definition of done

The project is not complete until:

- The dataset source and its provenance are documented, or a blocker is clearly explained.
- Ingestion is repeatable and schema/row-count checks pass.
- DuckLake works locally and the chosen Iceberg interoperability operations have passing tests and documented limitations.
- dbt builds and its data tests pass on the local sample.
- The conversion label and feature list are documented and leakage checks exist.
- Training/evaluation is reproducible and metrics are saved.
- BentoML serves a working prediction endpoint and API tests pass.
- Data drift is demonstrated against a reference dataset.
- Concept/model-quality monitoring is tested with delayed labels or explicitly reported as unavailable where ground truth is not present.
- Prometheus scrapes the intended metrics and Grafana displays dashboards and raises a test alert.
- A Grafana alert leads to a local approval interface.
- Rejecting an approval causes no retraining; approving a valid request authorizes only the intended Airflow run.
- Candidate failure does not replace the current model.
- The entire local setup, tests, shutdown and cleanup are documented.
- No secrets or private runtime artifacts are committed.

## OpenCode interaction protocol

At the start:
1. List and inspect repository files and Git status.
2. Read this file and `IMPLEMENTATION_GUIDE.md`.
3. Report the detected environment and any missing prerequisites.
4. Present the plan for the next stage and wait for approval before consequential changes.

For each stage:
1. State goal, files to change, commands to run, risks and acceptance criteria.
2. Implement only the approved stage.
3. Run relevant tests and inspect results.
4. Summarize files changed, commands run, pass/fail results, limitations and next step.
5. Ask whether to proceed.

Never fabricate command output or tests. If a command fails, report the real error and diagnose it. Do not ask the user to approve every trivial line-level edit, but do ask before destructive or high-impact actions. Do not generate extra documentation or files beyond the agreed scope unless the user approves.


## Note on temporal splits (user request)
For this POC, model training, evaluation, and drift detection will be organized by quarters and years (split by session date/visitStartTime). This enables detecting drift between quarters/years and comparing performance across periods.

