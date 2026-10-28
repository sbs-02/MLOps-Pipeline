"""FastAPI control-plane approval service and local UI (Gate 12)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from analytics_ml.approval.models import ApprovalRecord, DecisionRequest, DecisionResponse
from analytics_ml.approval.store import ApprovalStore

logger = logging.getLogger("services.approval")

app = FastAPI(
    title="Local MLOps Approval Control Plane",
    description="Human governance API authorizing retraining DAG runs following Grafana drift alerts",
    version="1.0.0",
)

store = ApprovalStore()


class CreateApprovalPayload(BaseModel):
    alert_id: str
    target_dag_id: str = "approved_retraining"
    model_version: str = "baseline-logreg-v1"
    trigger_reason: str = "Data drift threshold exceeded"
    evidence_summary: dict[str, Any] = {}
    ttl_minutes: int = 60


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "approval_control_plane"}


@app.post("/approvals/requests", response_model=ApprovalRecord, status_code=status.HTTP_201_CREATED)
def create_approval_request(payload: CreateApprovalPayload) -> ApprovalRecord:
    """Create a new pending approval request (invoked by monitoring/alerting or test fixtures)."""
    try:
        return store.create_request(
            alert_id=payload.alert_id,
            target_dag_id=payload.target_dag_id,
            model_version=payload.model_version,
            trigger_reason=payload.trigger_reason,
            evidence_summary=payload.evidence_summary,
            ttl_minutes=payload.ttl_minutes,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/approvals/pending")
def list_pending(request: Request) -> Any:
    """List all pending approval requests (JSON for API, HTML dashboard for browsers)."""
    pending = store.list_pending()
    accept = request.headers.get("accept", "")

    if "text/html" in accept:
        rows_html = ""
        for rec in pending:
            rows_html += f"""
            <tr>
              <td><code>{rec.approval_id}</code></td>
              <td><code>{rec.alert_id}</code></td>
              <td><span style="color:#d97706; font-weight:bold;">{rec.state.value}</span></td>
              <td><code>{rec.target_dag_id}</code></td>
              <td>{rec.trigger_reason}</td>
              <td>{rec.expires_at_utc[:19]} UTC</td>
              <td>
                <form action="/approvals/{rec.approval_id}/decision" method="POST" style="display:inline;">
                  <input type="hidden" name="decision" value="approve">
                  <input type="hidden" name="decided_by" value="local-operator">
                  <input type="hidden" name="decision_reason" value="Approved via local web UI">
                  <input type="hidden" name="idempotency_key" value="{rec.approval_id}-approve">
                  <button type="submit" style="background-color:#16a34a; color:white; border:none; padding:6px 12px; border-radius:4px; cursor:pointer;">Approve</button>
                </form>
                <form action="/approvals/{rec.approval_id}/decision" method="POST" style="display:inline; margin-left:6px;">
                  <input type="hidden" name="decision" value="reject">
                  <input type="hidden" name="decided_by" value="local-operator">
                  <input type="hidden" name="decision_reason" value="Rejected via local web UI">
                  <input type="hidden" name="idempotency_key" value="{rec.approval_id}-reject">
                  <button type="submit" style="background-color:#dc2626; color:white; border:none; padding:6px 12px; border-radius:4px; cursor:pointer;">Reject</button>
                </form>
              </td>
            </tr>
            """

        if not rows_html:
            rows_html = "<tr><td colspan='7' style='text-align:center; padding:18px; color:#6b7280;'>No pending approval requests. Stack is healthy.</td></tr>"

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
          <title>MLOps Local Approval UI</title>
          <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; padding: 32px; }}
            h1 {{ color: #38bdf8; margin-bottom: 8px; }}
            p.sub {{ color: #94a3b8; margin-top: 0; margin-bottom: 24px; }}
            table {{ width: 100%; border-collapse: collapse; background: #1e293b; border-radius: 8px; overflow: hidden; }}
            th, td {{ padding: 12px 16px; text-align: left; border-bottom: 1px solid #334155; }}
            th {{ background: #0284c7; color: white; font-size: 14px; }}
            code {{ background: #0f172a; padding: 2px 6px; border-radius: 4px; color: #38bdf8; }}
          </style>
        </head>
        <body>
          <h1>MLOps Retraining Approval Console</h1>
          <p class="sub">Local control-plane interface authorizing Airflow retraining DAG execution.</p>
          <table>
            <thead>
              <tr>
                <th>Approval ID</th>
                <th>Alert ID</th>
                <th>State</th>
                <th>Target DAG</th>
                <th>Trigger Reason</th>
                <th>Expires</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {rows_html}
            </tbody>
          </table>
        </body>
        </html>
        """
        return HTMLResponse(content=html_content)

    return pending


@app.get("/approvals/{approval_id}", response_model=ApprovalRecord)
def get_approval_detail(approval_id: str) -> ApprovalRecord:
    rec = store.get_request(approval_id)
    if rec is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Approval request '{approval_id}' not found")
    return rec


@app.post("/approvals/{approval_id}/decision", response_model=DecisionResponse)
async def submit_decision(approval_id: str, request: Request) -> Any:
    """Record an approve or reject decision. Supports JSON API payloads and HTML form submissions."""
    content_type = request.headers.get("content-type", "")

    if "application/json" in content_type:
        body = await request.json()
        if "decision" in body and isinstance(body["decision"], str):
            body["decision"] = body["decision"].lower()
        req = DecisionRequest(**body)
    else:
        # Form submission from browser
        form = await request.form()
        req = DecisionRequest(
            decision=str(form.get("decision", "reject")),
            decided_by=str(form.get("decided_by", "anonymous")),
            decision_reason=str(form.get("decision_reason", "No reason provided")),
            idempotency_key=str(form.get("idempotency_key", f"{approval_id}-auto")),
        )

    try:
        decision_resp = store.record_decision(approval_id, req)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Approval request '{approval_id}' not found")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    accept = request.headers.get("accept", "")
    if "text/html" in accept and "application/json" not in content_type:
        color = "#16a34a" if decision_resp.decision.value == "approve" else "#dc2626"
        return HTMLResponse(
            f"""
            <!DOCTYPE html>
            <html>
            <head><title>Decision Recorded</title><style>body {{ font-family: sans-serif; background: #0f172a; color: white; padding: 40px; }} code {{ color: #38bdf8; }}</style></head>
            <body>
              <h1 style="color:{color};">Decision Recorded: {decision_resp.decision.value.upper()}</h1>
              <p>Approval ID: <code>{decision_resp.approval_id}</code></p>
              <p>State: <strong>{decision_resp.state.value}</strong></p>
              <p>Message: {decision_resp.message}</p>
              <p><a href="/approvals/pending" style="color:#38bdf8;">Return to Pending Approvals</a></p>
            </body>
            </html>
            """
        )

    return decision_resp
