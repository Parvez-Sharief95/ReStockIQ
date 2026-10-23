"""approvals.py — Human Approval Queue & Governance Endpoints
Phase 8 & 9 Implementation
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from backend.app.schemas.models import ApprovalAction
from backend.app.services.agent_orchestrator import make_json_safe
from backend.app.services.auth import AuthenticatedUser, require_approver
from backend.app.services.repository import RepositoryManager, get_repository_manager

router = APIRouter()


class RecordApprovalPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(..., description="Target reorder request UUID")
    action: ApprovalAction = Field(..., description="'approved' or 'rejected'")
    target_version_number: int | None = Field(None, description="Proposal version number being approved")
    notes: str | None = Field(None, description="Auditor/approver justification notes")


@router.post("", summary="Record human approval or rejection tied to proposal version", status_code=status.HTTP_200_OK)
async def record_approval(
    payload: RecordApprovalPayload,
    current_user: AuthenticatedUser = Depends(require_approver),
    repo: RepositoryManager = Depends(get_repository_manager),
) -> dict[str, Any]:
    """Record human approval or rejection.

    Enforces:
    - Caller must be an authenticated user with 'approver' or 'admin' role.
    - Approver identity is derived strictly from the authenticated token (never trusted from payload).
    - target_version_number matches the current active version.
    """
    try:
        r_uuid = UUID(payload.request_id)
        appr, req = repo.requests.record_approval(
            request_id=r_uuid,
            approver_id=current_user.id,
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
async def get_request_approvals(
    request_id: str,
    repo: RepositoryManager = Depends(get_repository_manager),
) -> dict[str, Any]:
    """Retrieve all approval records associated with a request."""
    try:
        r_uuid = UUID(request_id)
        approvals = repo.requests.get_approvals(r_uuid)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid request UUID format")

    return make_json_safe({
        "approvals": approvals,
        "total": len(approvals),
    })
