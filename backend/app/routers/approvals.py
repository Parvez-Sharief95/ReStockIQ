"""
approvals.py — Human Approval Queue & Governance Endpoints
Phase 8 Implementation
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from backend.app.schemas.models import ApprovalAction
from backend.app.services.agent_orchestrator import make_json_safe
from backend.app.services.backend_store import get_backend_store

router = APIRouter()


class RecordApprovalPayload(BaseModel):
    request_id: str = Field(..., description="Target reorder request UUID")
    action: ApprovalAction = Field(..., description="'approved' or 'rejected'")
    target_version_number: int | None = Field(None, description="Proposal version number being approved")
    notes: str | None = Field(None, description="Auditor/approver justification notes")
    approver_id: str | None = Field(None, description="UUID of human approver")


@router.post("", summary="Record human approval or rejection tied to proposal version", status_code=status.HTTP_200_OK)
async def record_approval(payload: RecordApprovalPayload) -> dict[str, Any]:
    """Record human approval or rejection.

    Enforces that target_version_number matches the current active version.
    """
    store = get_backend_store()
    try:
        r_uuid = UUID(payload.request_id)
        appr_id = payload.approver_id or "00000000-0000-0000-0000-000000000002"

        appr, req = store.request_service.approve_or_reject_request(
            request_id=r_uuid,
            approver_id=appr_id,
            action=payload.action,
            target_version_number=payload.target_version_number,
            notes=payload.notes,
        )
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        # Version mismatch or invalid lifecycle transition
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    return make_json_safe({
        "approval": appr,
        "request": req,
        "status": req.status,
    })


@router.get("/{request_id}", summary="Get approvals for request")
async def get_request_approvals(request_id: str) -> dict[str, Any]:
    """Retrieve all approval records associated with a request."""
    store = get_backend_store()
    try:
        r_uuid = UUID(request_id)
        approvals = store.request_service.get_approvals(r_uuid)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid request UUID format")

    return make_json_safe({
        "approvals": approvals,
        "total": len(approvals),
    })
