"""Domain models and schemas for the human approval workflow (Gate 12)."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ApprovalState(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class DecisionType(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"


class ApprovalRecord(BaseModel):
    """Persistent audit record for an approval request."""

    approval_id: str
    alert_id: str
    state: ApprovalState
    created_at_utc: str
    expires_at_utc: str
    target_dag_id: str
    model_version: str
    trigger_reason: str
    evidence_summary: dict[str, Any] = Field(default_factory=dict)
    decided_by: str | None = None
    decided_at_utc: str | None = None
    decision_reason: str | None = None
    idempotency_key: str | None = None
    authorized_run_id: str | None = None


class DecisionRequest(BaseModel):
    """Payload for submitting an approval or rejection decision."""

    decision: DecisionType
    decided_by: str = Field(..., min_length=1, description="Operator identifier submitting decision")
    decision_reason: str = Field(..., min_length=1, description="Audit justification for the decision")
    idempotency_key: str = Field(..., min_length=1, description="Unique key ensuring at-most-once execution")


class DecisionResponse(BaseModel):
    """Outcome payload following decision submission."""

    approval_id: str
    state: ApprovalState
    decision: DecisionType
    decided_by: str
    decided_at_utc: str
    authorized_run_id: str | None
    message: str
