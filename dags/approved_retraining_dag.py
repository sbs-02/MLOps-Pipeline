"""Airflow DAG governing approved retraining of the conversion model (Gate 13).

This DAG executes ONLY when authorized by a human operator through the local approval
control plane. Direct or manual unauthenticated triggers are strictly rejected.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Attempt importing Airflow primitives; gracefully provide fallbacks if not installed in local venv
try:
    from airflow import DAG
    from airflow.operators.python import PythonOperator
    AIRFLOW_AVAILABLE = True
except ImportError:
    AIRFLOW_AVAILABLE = False
    DAG = Any  # type: ignore[misc,assignment]
    PythonOperator = Any  # type: ignore[misc,assignment]

# Imports are deferred to task runtime so the DAG can be parsed even when the
# analytics_ml package is not installed in the Airflow container image.

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def task_verify_authorization(**context: Any) -> dict[str, Any]:
    """Task 1: Verify human approval and active authorization token.
    
    Extracts approval credentials from dag_run.conf.
    If credentials are missing, expired, or invalid, aborts execution immediately.
    """
    from analytics_ml.approval.store import ApprovalStore

    dag_run = context.get("dag_run")
    conf = getattr(dag_run, "conf", {}) or {}

    approval_id = conf.get("approval_id")
    authorized_run_id = conf.get("authorized_run_id")

    if not approval_id or not authorized_run_id:
        raise PermissionError(
            "Retraining DAG rejected: missing 'approval_id' or 'authorized_run_id' in dag_run.conf. "
            "Retraining cannot be triggered without explicit human approval from the control-plane UI."
        )

    store = ApprovalStore()
    valid, msg, record = store.verify_authorization(
        approval_id=approval_id,
        authorized_run_id=authorized_run_id,
        target_dag_id="approved_retraining",
    )
    if not valid or record is None:
        raise PermissionError(f"Retraining unauthorized: {msg}")

    logger.info("Retraining authorization verified for approval %s (run ID %s)", approval_id, authorized_run_id)
    return {
        "approval_id": approval_id,
        "authorized_run_id": authorized_run_id,
        "target_dag_id": "approved_retraining",
    }


def task_consume_authorization(**context: Any) -> None:
    """Task 2: Atomically consume authorization token so it cannot be re-used."""
    from analytics_ml.approval.store import ApprovalStore

    ti = context.get("ti")
    auth_data = ti.xcom_pull(task_ids="verify_authorization") if ti else None
    if not auth_data:
        raise ValueError("Missing authorization context from verification task")

    store = ApprovalStore()
    valid, msg, _ = store.consume_authorization(
        approval_id=auth_data["approval_id"],
        authorized_run_id=auth_data["authorized_run_id"],
        target_dag_id=auth_data["target_dag_id"],
    )
    if not valid:
        raise PermissionError(f"Failed to consume authorization token: {msg}")
    logger.info("Authorization token marked consumed at %s", datetime.now(timezone.utc).isoformat())


def task_validate_data_batch(**context: Any) -> int:
    """Task 3: Validate DuckLake mart table exists and meets row count threshold."""
    from analytics_ml.retraining.pipeline import RetrainingConfig, RetrainingEngine

    config = RetrainingConfig(approval_id="precheck", authorized_run_id="precheck", strict_raise=True)
    engine = RetrainingEngine(config=config)
    row_count = engine.validate_batch_quality(min_rows=1000)
    logger.info("DuckLake mart table validated with %d rows", row_count)
    return row_count


def task_execute_retraining(**context: Any) -> dict[str, Any]:
    """Task 4: Execute candidate model training, evaluation, and safe promotion."""
    from analytics_ml.approval.store import ApprovalStore
    from analytics_ml.retraining.pipeline import (
        DEFAULT_AUDIT_LOG_PATH,
        DEFAULT_CATALOG_PATH,
        DEFAULT_MODELS_DIR,
        RetrainingConfig,
        RetrainingEngine,
    )

    ti = context.get("ti")
    auth_data = ti.xcom_pull(task_ids="verify_authorization") if ti else None
    if not auth_data:
        raise ValueError("Missing authorization credentials")

    config = RetrainingConfig(
        approval_id=auth_data["approval_id"],
        authorized_run_id=auth_data["authorized_run_id"],
        target_dag_id="approved_retraining",
        catalog_path=DEFAULT_CATALOG_PATH,
        models_dir=DEFAULT_MODELS_DIR,
        audit_log_path=DEFAULT_AUDIT_LOG_PATH,
        strict_raise=True,
    )
    # The authorization was already consumed in Task 2, so bypass re-consumption in execute by mocking/passing store
    store = ApprovalStore()
    engine = RetrainingEngine(config=config, store=store)

    # Load dataset and execute training and evaluation
    from analytics_ml.training.train import load_dataset, split_dataset
    dataset_frame = load_dataset()
    train_df, val_df, _ = split_dataset(dataset_frame)

    candidate = engine.train_candidate(train_df)
    passed, candidate_metrics, active_metrics, reason = engine.evaluate_candidate(candidate, val_df)

    if passed:
        engine.promote_candidate(candidate, candidate_metrics)
        status = "SUCCESS_PROMOTED"
        promoted = True
        logger.info("Candidate model promoted successfully: %s", reason)
    else:
        status = "REJECTED_EVALUATION_FAILED"
        promoted = False
        logger.warning("Candidate model rejected by evaluation gate: %s. Active model preserved.", reason)

    outcome_data = {
        "status": status,
        "approval_id": config.approval_id,
        "authorized_run_id": config.authorized_run_id,
        "promoted": promoted,
        "candidate_metrics": candidate_metrics,
        "active_metrics": active_metrics,
        "message": reason,
        "executed_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    return outcome_data


def task_record_audit(**context: Any) -> None:
    """Task 5: Persist retraining audit record."""
    ti = context.get("ti")
    outcome_data = ti.xcom_pull(task_ids="execute_retraining") if ti else None
    if not outcome_data:
        logger.warning("No retraining outcome data found to record in audit")
        return

    from analytics_ml.retraining.pipeline import RetrainingConfig, RetrainingEngine, RetrainingOutcome
    outcome = RetrainingOutcome(**outcome_data)
    config = RetrainingConfig(approval_id="audit", authorized_run_id="audit")
    engine = RetrainingEngine(config=config)
    engine.record_audit(outcome)
    logger.info("Retraining audit recorded with status %s", outcome.status)


# Construct DAG if Airflow is present in the environment
if AIRFLOW_AVAILABLE:
    default_args = {
        "owner": "mlops-platform",
        "depends_on_past": False,
        "email_on_failure": False,
        "email_on_retry": False,
        "retries": 0,  # Never retry authorization failures
    }

    dag = DAG(
        dag_id="approved_retraining",
        default_args=default_args,
        description="Approval-gated ML model retraining and promotion pipeline",
        schedule_interval=None,  # Strictly triggered on approved demand, never on schedule
        start_date=datetime(2026, 1, 1),
        catchup=False,
        max_active_runs=1,
        tags=["mlops", "retraining", "governance"],
    )

    t1 = PythonOperator(
        task_id="verify_authorization",
        python_callable=task_verify_authorization,
        dag=dag,
    )

    t2 = PythonOperator(
        task_id="consume_authorization",
        python_callable=task_consume_authorization,
        dag=dag,
    )

    t3 = PythonOperator(
        task_id="validate_data_batch",
        python_callable=task_validate_data_batch,
        dag=dag,
    )

    t4 = PythonOperator(
        task_id="execute_retraining",
        python_callable=task_execute_retraining,
        dag=dag,
    )

    t5 = PythonOperator(
        task_id="record_audit",
        python_callable=task_record_audit,
        dag=dag,
    )

    t1 >> t2 >> t3 >> t4 >> t5
else:
    dag = None  # type: ignore[assignment]
