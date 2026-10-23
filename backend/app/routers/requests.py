"""
requests.py — Reorder Requests, Lifecycle, Approval Invalidation & Verification Endpoints
Phase 8 Implementation
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID
import uuid

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from backend.app.schemas.models import (
    AnalysisStatus,
    ApprovalAction,
    RequestStatus,
)
from backend.app.services.agent_orchestrator import make_json_safe
from backend.app.services.backend_store import get_backend_store

router = APIRouter()


# ── Request Models ────────────────────────────────────────────────────────────

class CreateReorderRequestPayload(BaseModel):
    analysis_id: str
    sku: str
    product_id: str
    supplier_name: str
    proposed_quantity: Decimal | float | int = Field(..., gt=0)
    pack_count: int = Field(..., ge=1)
    pack_size: int = Field(..., ge=1)
    estimated_cost: Decimal | float | int = Field(..., ge=0)
    currency: str = "USD"
    calculation_version: str = "1.0.0"
    user_id: str | None = None
    idempotency_key: str | None = None
    actor_id: str | None = None


class UpdateProposalPayload(BaseModel):
    proposed_quantity: Decimal | float | int | None = None
    pack_count: int | None = None
    pack_size: int | None = None
    estimated_cost: Decimal | float | int | None = None
    supplier_name: str | None = None
    currency: str | None = None
    actor_id: str | None = None
    modification_reason: str = "Proposal parameters updated by user"


class SubmitOrderPayload(BaseModel):
    actor_id: str | None = None
    force_failure: bool = False
    failure_reason: str | None = None


class VerifyOutcomePayload(BaseModel):
    actual_sku: str
    actual_quantity: Decimal | float | int
    actual_pack_size: int | None = None
    simulate_duplicate: bool = False
    existing_open_po_references: list[str] | None = None
    actor_id: str | None = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("", summary="Create a reorder request with idempotency protection", status_code=status.HTTP_201_CREATED)
async def create_request(payload: CreateReorderRequestPayload) -> dict[str, Any]:
    """Create a reorder request in pending_approval status.

    Safety Rules:
    - Rejects creation if analysis has insufficient data or failed evidence.
    - Idempotency protection: returns existing request on duplicate submission.
    """
    store = get_backend_store()

    # Safety Guard: Check source analysis validity
    try:
        a_uuid = UUID(payload.analysis_id)
        if a_uuid in store.analyses:
            analysis = store.analyses[a_uuid]
            if analysis.analysis_status == AnalysisStatus.INSUFFICIENT_DATA:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Cannot create purchase request: the referenced analysis has status "
                        f"'insufficient_data' ({analysis.status_reason or 'unresolved data issues'})."
                    ),
                )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid analysis_id UUID format: '{payload.analysis_id}'",
        )

    # Validate pack size compliance
    qty = Decimal(str(payload.proposed_quantity))
    if payload.pack_size > 1 and (qty % payload.pack_size != 0):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Proposed quantity ({qty}) must be a multiple of pack size ({payload.pack_size}).",
        )

    user_id = payload.user_id or "00000000-0000-0000-0000-000000000001"
    req, ver, is_dup = store.request_service.create_reorder_request(
        user_id=user_id,
        analysis_id=payload.analysis_id,
        product_id=payload.product_id,
        sku=payload.sku,
        supplier_name=payload.supplier_name,
        proposed_quantity=qty,
        pack_count=payload.pack_count,
        pack_size=payload.pack_size,
        estimated_cost=payload.estimated_cost,
        currency=payload.currency,
        calculation_version=payload.calculation_version,
        idempotency_key=payload.idempotency_key,
        actor_id=payload.actor_id or user_id,
    )

    return make_json_safe({
        "request": req,
        "version": ver,
        "is_duplicate": is_dup,
        "source_type": "mock_source",
    })


@router.get("", summary="List reorder requests")
async def list_requests(
    request_status: str | None = Query(None, alias="status", description="Filter by RequestStatus"),
) -> dict[str, Any]:
    """Retrieve all reorder requests, optionally filtered by status."""
    store = get_backend_store()
    reqs = list(store.request_service._requests.values())
    if request_status:
        reqs = [r for r in reqs if r.status.value == request_status.lower()]

    return make_json_safe({
        "items": reqs,
        "total": len(reqs),
        "source_type": "mock_source",
    })


@router.get("/{request_id}", summary="Get request details by ID")
async def get_request_by_id(request_id: str) -> dict[str, Any]:
    """Retrieve reorder request details, active version, and audit count."""
    store = get_backend_store()
    try:
        r_uuid = UUID(request_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid request UUID format")

    if r_uuid not in store.request_service._requests:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Request '{request_id}' not found")

    req = store.request_service._requests[r_uuid]
    ver = store.request_service.get_latest_version(r_uuid)
    return make_json_safe({
        "request": req,
        "latest_version": ver,
        "source_type": "mock_source",
    })


@router.get("/{request_id}/versions", summary="Get version history for request")
async def get_request_versions(request_id: str) -> dict[str, Any]:
    """Retrieve all immutable proposal versions for a request."""
    store = get_backend_store()
    try:
        r_uuid = UUID(request_id)
        versions = store.request_service.get_versions(r_uuid)
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    return make_json_safe({
        "versions": versions,
        "total": len(versions),
    })


@router.get("/{request_id}/audit", summary="Get append-only audit trail for request")
async def get_request_audit(request_id: str) -> dict[str, Any]:
    """Retrieve immutable chronological audit trail for a request."""
    store = get_backend_store()
    try:
        r_uuid = UUID(request_id)
        events = store.request_service.get_audit_trail(r_uuid)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid request UUID format")

    return make_json_safe({
        "events": events,
        "total": len(events),
    })


@router.patch("/{request_id}/proposal", summary="Update request proposal (Rule S2: invalidates approval)")
async def update_proposal(request_id: str, payload: UpdateProposalPayload) -> dict[str, Any]:
    """Modify proposal parameters, incrementing version and invalidating prior approval."""
    store = get_backend_store()
    try:
        r_uuid = UUID(request_id)
        actor = payload.actor_id or "00000000-0000-0000-0000-000000000001"
        req, new_ver = store.request_service.update_proposal(
            request_id=r_uuid,
            actor_id=actor,
            proposed_quantity=payload.proposed_quantity,
            pack_count=payload.pack_count,
            pack_size=payload.pack_size,
            estimated_cost=payload.estimated_cost,
            supplier_name=payload.supplier_name,
            currency=payload.currency,
            modification_reason=payload.modification_reason,
        )
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return make_json_safe({
        "request": req,
        "new_version": new_ver,
        "status": req.status,
    })


@router.post("/{request_id}/submit", summary="Simulated order submission (Requires human approval)")
async def submit_order(request_id: str, payload: SubmitOrderPayload) -> dict[str, Any]:
    """Submit purchase order in simulated mode.

    MANDATORY GATES:
    - Human approval must have been recorded on the current active version.
    - If unapproved or outdated, strictly blocks execution (403 Forbidden).
    """
    store = get_backend_store()
    try:
        r_uuid = UUID(request_id)
        actor = payload.actor_id or "00000000-0000-0000-0000-000000000001"
        req, result = store.request_service.submit_request(
            request_id=r_uuid,
            actor_id=actor,
            simulated=True,
            force_failure=payload.force_failure,
            failure_reason=payload.failure_reason,
        )
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

    return make_json_safe({
        "request": req,
        "result": result,
    })


@router.post("/{request_id}/verify", summary="Run independent outcome verification after submission")
async def verify_outcome(request_id: str, payload: VerifyOutcomePayload) -> dict[str, Any]:
    """Perform independent verification comparing actual outcome with intended request parameters."""
    store = get_backend_store()
    try:
        r_uuid = UUID(request_id)
        actor = payload.actor_id or "00000000-0000-0000-0000-000000000001"

        open_pos = payload.existing_open_po_references or []
        if payload.simulate_duplicate:
            open_pos = ["SIM-PO-EXISTING-CONFLICT", "SIM-PO-EXISTING-CONFLICT"]

        ver, req = store.request_service.verify_submission_outcome(
            request_id=r_uuid,
            actual_sku=payload.actual_sku,
            actual_quantity=payload.actual_quantity,
            actual_pack_size=payload.actual_pack_size,
            existing_open_po_references=open_pos,
            actor_id=actor,
        )
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    return make_json_safe({
        "verification": ver,
        "request": req,
    })


@router.get("/{request_id}/verification", summary="Get verification result for request")
async def get_verification(request_id: str) -> dict[str, Any]:
    """Retrieve independent outcome verification result for a request."""
    store = get_backend_store()
    try:
        r_uuid = UUID(request_id)
        ver = store.request_service.get_verification_result(r_uuid)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid request UUID format")

    if not ver:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No verification result found for request '{request_id}'",
        )

    return make_json_safe({
        "verification": ver,
    })
