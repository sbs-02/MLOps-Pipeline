"""Durable SQLite storage and state machine for human approvals (Gate 12)."""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Generator

from analytics_ml.approval.models import ApprovalRecord, ApprovalState, DecisionRequest, DecisionResponse, DecisionType

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DB_PATH = PROJECT_ROOT / "warehouse" / "approvals.db"

DAG_ALLOWLIST = {"approved_retraining"}


class ApprovalStore:
    """Thread-safe SQLite store governing approval state transitions and idempotency."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path is not None else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS approvals (
                    approval_id TEXT PRIMARY KEY,
                    alert_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    expires_at_utc TEXT NOT NULL,
                    target_dag_id TEXT NOT NULL,
                    model_version TEXT NOT NULL,
                    trigger_reason TEXT NOT NULL,
                    evidence_summary_json TEXT NOT NULL,
                    decided_by TEXT,
                    decided_at_utc TEXT,
                    decision_reason TEXT,
                    idempotency_key TEXT,
                    authorized_run_id TEXT
                );
                CREATE TABLE IF NOT EXISTS consumed_approvals (
                    approval_id TEXT NOT NULL,
                    authorized_run_id TEXT NOT NULL,
                    consumed_at_utc TEXT NOT NULL,
                    PRIMARY KEY (approval_id, authorized_run_id)
                );
                """
            )
            conn.commit()

    def create_request(
        self,
        alert_id: str,
        target_dag_id: str = "approved_retraining",
        model_version: str = "baseline-logreg-v1",
        trigger_reason: str = "Data drift threshold exceeded",
        evidence_summary: dict[str, Any] | None = None,
        ttl_minutes: int = 60,
    ) -> ApprovalRecord:
        """Create a new PENDING approval request with an expiration timestamp."""
        if target_dag_id not in DAG_ALLOWLIST:
            raise ValueError(f"Target DAG '{target_dag_id}' not permitted. Allowlist: {sorted(DAG_ALLOWLIST)}")

        now = datetime.now(timezone.utc)
        expires = now + timedelta(minutes=ttl_minutes)
        approval_id = f"appr-{uuid.uuid4().hex[:12]}"

        record = ApprovalRecord(
            approval_id=approval_id,
            alert_id=alert_id,
            state=ApprovalState.PENDING,
            created_at_utc=now.isoformat(),
            expires_at_utc=expires.isoformat(),
            target_dag_id=target_dag_id,
            model_version=model_version,
            trigger_reason=trigger_reason,
            evidence_summary=evidence_summary or {},
        )

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO approvals (
                    approval_id, alert_id, state, created_at_utc, expires_at_utc,
                    target_dag_id, model_version, trigger_reason, evidence_summary_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.approval_id,
                    record.alert_id,
                    record.state.value,
                    record.created_at_utc,
                    record.expires_at_utc,
                    record.target_dag_id,
                    record.model_version,
                    record.trigger_reason,
                    json.dumps(record.evidence_summary),
                ),
            )
            conn.commit()

        return record

    def get_request(self, approval_id: str) -> ApprovalRecord | None:
        """Retrieve an approval record by ID, automatically evaluating expiration."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM approvals WHERE approval_id = ?", (approval_id,)
            ).fetchone()

        if row is None:
            return None

        record = self._row_to_record(row)

        # Check expiration for PENDING requests
        if record.state == ApprovalState.PENDING:
            expires_at = datetime.fromisoformat(record.expires_at_utc)
            if datetime.now(timezone.utc) > expires_at:
                with self._get_connection() as conn:
                    conn.execute(
                        "UPDATE approvals SET state = ? WHERE approval_id = ?",
                        (ApprovalState.EXPIRED.value, approval_id),
                    )
                    conn.commit()
                record.state = ApprovalState.EXPIRED

        return record

    def list_pending(self) -> list[ApprovalRecord]:
        """Return all active, unexpired pending requests."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM approvals WHERE state = ? ORDER BY created_at_utc DESC",
                (ApprovalState.PENDING.value,),
            ).fetchall()

        results: list[ApprovalRecord] = []
        for r in rows:
            rec = self.get_request(r["approval_id"])
            if rec and rec.state == ApprovalState.PENDING:
                results.append(rec)
        return results

    def record_decision(
        self, approval_id: str, request: DecisionRequest
    ) -> DecisionResponse:
        """Atomically transition a PENDING request to APPROVED or REJECTED with idempotency protection."""
        record = self.get_request(approval_id)
        if record is None:
            raise KeyError(f"Approval request '{approval_id}' not found")

        # Idempotency check: if already finalized with same idempotency_key, return cached result
        if record.state in (ApprovalState.APPROVED, ApprovalState.REJECTED):
            if record.idempotency_key == request.idempotency_key:
                decision_type = DecisionType.APPROVE if record.state == ApprovalState.APPROVED else DecisionType.REJECT
                return DecisionResponse(
                    approval_id=record.approval_id,
                    state=record.state,
                    decision=decision_type,
                    decided_by=record.decided_by or "unknown",
                    decided_at_utc=record.decided_at_utc or "",
                    authorized_run_id=record.authorized_run_id,
                    message="Idempotent replay: decision already recorded.",
                )
            raise ValueError(
                f"Cannot decide request '{approval_id}': already in terminal state '{record.state.value}'"
            )

        if record.state == ApprovalState.EXPIRED:
            raise ValueError(f"Cannot decide request '{approval_id}': request has expired")

        now = datetime.now(timezone.utc).isoformat()
        if request.decision == DecisionType.APPROVE:
            new_state = ApprovalState.APPROVED
            authorized_run_id = f"run-approved-{uuid.uuid4().hex[:8]}-{int(datetime.now().timestamp())}"
            msg = f"Retraining authorized for DAG '{record.target_dag_id}'. Run ID: {authorized_run_id}"
        else:
            new_state = ApprovalState.REJECTED
            authorized_run_id = None
            msg = "Retraining request explicitly rejected. No orchestrator run authorized."

        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE approvals SET
                    state = ?,
                    decided_by = ?,
                    decided_at_utc = ?,
                    decision_reason = ?,
                    idempotency_key = ?,
                    authorized_run_id = ?
                WHERE approval_id = ? AND state = ?
                """,
                (
                    new_state.value,
                    request.decided_by,
                    now,
                    request.decision_reason,
                    request.idempotency_key,
                    authorized_run_id,
                    approval_id,
                    ApprovalState.PENDING.value,
                ),
            )
            conn.commit()

        return DecisionResponse(
            approval_id=approval_id,
            state=new_state,
            decision=request.decision,
            decided_by=request.decided_by,
            decided_at_utc=now,
            authorized_run_id=authorized_run_id,
            message=msg,
        )

    def verify_authorization(
        self,
        approval_id: str,
        authorized_run_id: str,
        target_dag_id: str = "approved_retraining",
    ) -> tuple[bool, str, ApprovalRecord | None]:
        """Verify whether an approval is valid and authorized for execution without consuming it."""
        record = self.get_request(approval_id)
        if record is None:
            return False, f"Approval request '{approval_id}' not found", None

        if record.state != ApprovalState.APPROVED:
            return False, f"Approval request '{approval_id}' is in state '{record.state.value}', not APPROVED", record

        if record.target_dag_id != target_dag_id:
            return (
                False,
                f"Approval request target DAG '{record.target_dag_id}' does not match target DAG '{target_dag_id}'",
                record,
            )

        if record.authorized_run_id != authorized_run_id:
            return (
                False,
                f"Authorized run ID mismatch: expected '{record.authorized_run_id}', got '{authorized_run_id}'",
                record,
            )

        # Check if already consumed
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT consumed_at_utc FROM consumed_approvals WHERE approval_id = ? AND authorized_run_id = ?",
                (approval_id, authorized_run_id),
            ).fetchone()

        if row is not None:
            return (
                False,
                f"Approval request '{approval_id}' with run ID '{authorized_run_id}' was already consumed at {row['consumed_at_utc']}",
                record,
            )

        return True, "Authorization is valid and unconsumed", record

    def consume_authorization(
        self,
        approval_id: str,
        authorized_run_id: str,
        target_dag_id: str = "approved_retraining",
    ) -> tuple[bool, str, ApprovalRecord | None]:
        """Verify and atomically mark an authorization token as consumed to prevent replay."""
        valid, msg, record = self.verify_authorization(approval_id, authorized_run_id, target_dag_id)
        if not valid or record is None:
            return False, msg, record

        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            try:
                conn.execute(
                    "INSERT INTO consumed_approvals (approval_id, authorized_run_id, consumed_at_utc) VALUES (?, ?, ?)",
                    (approval_id, authorized_run_id, now),
                )
                conn.commit()
            except sqlite3.IntegrityError:
                return (
                    False,
                    f"Approval request '{approval_id}' with run ID '{authorized_run_id}' was consumed concurrently",
                    record,
                )

        return True, f"Authorization verified and consumed at {now}", record

    def _row_to_record(self, row: sqlite3.Row) -> ApprovalRecord:
        return ApprovalRecord(
            approval_id=row["approval_id"],
            alert_id=row["alert_id"],
            state=ApprovalState(row["state"]),
            created_at_utc=row["created_at_utc"],
            expires_at_utc=row["expires_at_utc"],
            target_dag_id=row["target_dag_id"],
            model_version=row["model_version"],
            trigger_reason=row["trigger_reason"],
            evidence_summary=json.loads(row["evidence_summary_json"]),
            decided_by=row["decided_by"],
            decided_at_utc=row["decided_at_utc"],
            decision_reason=row["decision_reason"],
            idempotency_key=row["idempotency_key"],
            authorized_run_id=row["authorized_run_id"],
        )
