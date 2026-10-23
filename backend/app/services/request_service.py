"""
request_service.py — Reorder Requests, Approval, Idempotency & Verification
Phase 5 Implementation

Provides:
- Complete request lifecycle state transitions:
  draft -> pending_approval -> approved -> submitted_or_simulated -> verified
  (plus rejected, needs_review, failed).
- Immutable request versioning (RequestVersion) with full snapshotting.
- Strict human approval gating tied to exact version ID.
- Automatic approval invalidation when proposal changes after approval.
- Idempotency protection against duplicate requests and retries via stable keys.
- Safe simulated order execution (never calls real supplier endpoints).
- Independent verification comparing actual vs intended SKU, quantity, pack size, and duplicates.
- Append-only audit trail logging for every lifecycle event.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Sequence
from uuid import UUID

from backend.app.schemas.models import (
    ApprovalAction,
    ApprovalCreate,
    ApprovalRead,
    AuditEventRead,
    AuditEventType,
    ReorderAnalysisCreate,
    ReorderRequestCreate,
    ReorderRequestRead,
    RequestStatus,
    RequestVersionRead,
    VerificationResultRead,
    VerificationStatus,
)


def generate_idempotency_key(
    user_id: str | UUID,
    sku: str,
    analysis_id: str | UUID,
    version_number: int = 1,
) -> str:
    """Generate a stable, deterministic idempotency key for a proposed reorder intent."""
    raw = f"{str(user_id)}:{sku.strip().upper()}:{str(analysis_id)}:v{version_number}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class RequestService:
    """In-memory service managing the full reorder request lifecycle with strict safety guards.

    Enforces all database constraints, version immutability, approval gating,
    and audit trail logging without requiring live Supabase credentials.
    """

    def __init__(self):
        # Repositories indexed by ID
        self._requests: dict[UUID, ReorderRequestRead] = {}
        self._versions: dict[UUID, list[RequestVersionRead]] = {}
        self._approvals: dict[UUID, list[ApprovalRead]] = {}
        self._verifications: dict[UUID, list[VerificationResultRead]] = {}
        self._audit_events: dict[UUID, list[AuditEventRead]] = {}
        # Idempotency index: (user_id_str, idempotency_key) -> request_id
        self._idempotency_index: dict[tuple[str, str], UUID] = {}

    # ─────────────────────────────────────────────────────────────────────────
    # 1. Audit Trail Logging (Append-Only)
    # ─────────────────────────────────────────────────────────────────────────

    def log_audit_event(
        self,
        request_id: UUID,
        event_type: AuditEventType,
        actor_id: UUID | None,
        details: dict[str, Any],
    ) -> AuditEventRead:
        """Append an immutable audit event to the request's audit log."""
        event = AuditEventRead(
            id=uuid.uuid4(),
            request_id=request_id,
            event_type=event_type,
            actor_id=actor_id,
            details=details,
            created_at=datetime.now(timezone.utc),
        )
        if request_id not in self._audit_events:
            self._audit_events[request_id] = []
        self._audit_events[request_id].append(event)
        return event

    def get_audit_trail(self, request_id: UUID) -> list[AuditEventRead]:
        """Retrieve the chronological audit events for a request."""
        return list(self._audit_events.get(request_id, []))

    # ─────────────────────────────────────────────────────────────────────────
    # 2. Request Creation & Idempotency Protection
    # ─────────────────────────────────────────────────────────────────────────

    def create_reorder_request(
        self,
        user_id: UUID | str,
        analysis_id: UUID | str,
        product_id: UUID | str,
        sku: str,
        supplier_name: str,
        proposed_quantity: Decimal | int | float,
        pack_count: int,
        pack_size: int,
        estimated_cost: Decimal | int | float,
        currency: str = "USD",
        calculation_version: str = "1.0.0",
        idempotency_key: str | None = None,
        initial_status: RequestStatus = RequestStatus.PENDING_APPROVAL,
        actor_id: UUID | str | None = None,
    ) -> tuple[ReorderRequestRead, RequestVersionRead, bool]:
        """Create a reorder request with idempotency protection.

        If a request with (user_id, idempotency_key) already exists:
        - Returns the existing request and its latest version.
        - Sets is_duplicate = True.
        - Records an AuditEventType.RETRY in the audit log.
        """
        u_id = UUID(str(user_id))
        a_id = UUID(str(analysis_id))
        p_id = UUID(str(product_id))
        act_id = UUID(str(actor_id)) if actor_id else u_id
        qty = Decimal(str(proposed_quantity))
        cost = Decimal(str(estimated_cost))

        key = idempotency_key or generate_idempotency_key(u_id, sku, a_id, version_number=1)
        lookup_key = (str(u_id), key)

        # Idempotency hit: return existing request
        if lookup_key in self._idempotency_index:
            existing_req_id = self._idempotency_index[lookup_key]
            existing_req = self._requests[existing_req_id]
            latest_version = self.get_latest_version(existing_req_id)

            self.log_audit_event(
                request_id=existing_req_id,
                event_type=AuditEventType.RETRY,
                actor_id=act_id,
                details={
                    "idempotency_key": key,
                    "action": "duplicate_submission_blocked",
                    "returned_existing_status": existing_req.status.value,
                },
            )
            return existing_req, latest_version, True

        # Create new request
        now = datetime.now(timezone.utc)
        req_id = uuid.uuid4()
        ver_id = uuid.uuid4()

        snapshot = {
            "request_id": str(req_id),
            "version_number": 1,
            "sku": sku,
            "product_id": str(p_id),
            "analysis_id": str(a_id),
            "supplier_name": supplier_name,
            "proposed_quantity": str(qty),
            "pack_count": pack_count,
            "pack_size": pack_size,
            "estimated_cost": str(cost),
            "currency": currency,
            "calculation_version": calculation_version,
            "snapshot_at": now.isoformat(),
        }

        req = ReorderRequestRead(
            id=req_id,
            idempotency_key=key,
            analysis_id=a_id,
            product_id=p_id,
            sku=sku,
            supplier_name=supplier_name,
            proposed_quantity=qty,
            pack_count=pack_count,
            pack_size=pack_size,
            estimated_cost=cost,
            currency=currency,
            calculation_version=calculation_version,
            status=initial_status,
            user_id=UUID(user_id) if isinstance(user_id, str) else user_id,
            created_at=now,
            updated_at=now,
        )

        ver = RequestVersionRead(
            id=ver_id,
            request_id=req_id,
            version_number=1,
            snapshot=snapshot,
            created_at=now,
        )

        self._requests[req_id] = req
        self._versions[req_id] = [ver]
        self._idempotency_index[lookup_key] = req_id

        self.log_audit_event(
            request_id=req_id,
            event_type=AuditEventType.PROPOSED,
            actor_id=act_id,
            details={
                "sku": sku,
                "proposed_quantity": str(qty),
                "pack_count": pack_count,
                "pack_size": pack_size,
                "estimated_cost": str(cost),
                "idempotency_key": key,
            },
        )

        return req, ver, False

    # ─────────────────────────────────────────────────────────────────────────
    # 3. Request Proposal Modification & Version Invalidation
    # ─────────────────────────────────────────────────────────────────────────

    def update_proposal(
        self,
        request_id: UUID | str,
        actor_id: UUID | str,
        proposed_quantity: Decimal | int | float | None = None,
        pack_count: int | None = None,
        pack_size: int | None = None,
        estimated_cost: Decimal | int | float | None = None,
        supplier_name: str | None = None,
        currency: str | None = None,
        modification_reason: str = "Proposal parameters updated",
    ) -> tuple[ReorderRequestRead, RequestVersionRead]:
        """Update a request's proposal, creating a new immutable version.

        RULE S2 / Playbook 398–400:
        Any change to SKU, quantity, price, supplier, or budget basis after approval
        INVALIDATES existing approval and forces the request back to pending_approval / needs_review.
        """
        req_id = UUID(str(request_id))
        act_id = UUID(str(actor_id))

        if req_id not in self._requests:
            raise KeyError(f"Reorder request '{req_id}' not found")

        req = self._requests[req_id]
        versions = self._versions[req_id]
        latest_ver = versions[-1]
        next_ver_number = latest_ver.version_number + 1
        now = datetime.now(timezone.utc)

        # Track what changed
        changes: dict[str, Any] = {}
        new_qty = req.proposed_quantity if proposed_quantity is None else Decimal(str(proposed_quantity))
        new_packs = req.pack_count if pack_count is None else pack_count
        new_size = req.pack_size if pack_size is None else pack_size
        new_cost = req.estimated_cost if estimated_cost is None else Decimal(str(estimated_cost))
        new_supplier = req.supplier_name if supplier_name is None else supplier_name
        new_currency = req.currency if currency is None else currency

        if new_qty != req.proposed_quantity:
            changes["proposed_quantity"] = {"old": str(req.proposed_quantity), "new": str(new_qty)}
        if new_packs != req.pack_count:
            changes["pack_count"] = {"old": req.pack_count, "new": new_packs}
        if new_size != req.pack_size:
            changes["pack_size"] = {"old": req.pack_size, "new": new_size}
        if new_cost != req.estimated_cost:
            changes["estimated_cost"] = {"old": str(req.estimated_cost), "new": str(new_cost)}
        if new_supplier != req.supplier_name:
            changes["supplier_name"] = {"old": req.supplier_name, "new": new_supplier}

        if not changes:
            # Nothing changed
            return req, latest_ver

        # Approval Invalidation Rule
        had_approval = req.status == RequestStatus.APPROVED or (req_id in self._approvals and len(self._approvals[req_id]) > 0)
        if had_approval:
            req.status = RequestStatus.PENDING_APPROVAL
            self.log_audit_event(
                request_id=req_id,
                event_type=AuditEventType.VERSION_INVALIDATED,
                actor_id=act_id,
                details={
                    "reason": modification_reason,
                    "previous_version": latest_ver.version_number,
                    "new_version": next_ver_number,
                    "changes": changes,
                    "message": "Proposal changed after approval; previous approval invalidated.",
                },
            )

        # Update request model
        req.proposed_quantity = new_qty
        req.pack_count = new_packs
        req.pack_size = new_size
        req.estimated_cost = new_cost
        req.supplier_name = new_supplier
        req.currency = new_currency
        req.updated_at = now

        # Create new immutable version
        new_ver_id = uuid.uuid4()
        snapshot = {
            "request_id": str(req_id),
            "version_number": next_ver_number,
            "sku": req.sku,
            "product_id": str(req.product_id),
            "analysis_id": str(req.analysis_id),
            "supplier_name": new_supplier,
            "proposed_quantity": str(new_qty),
            "pack_count": new_packs,
            "pack_size": new_size,
            "estimated_cost": str(new_cost),
            "currency": new_currency,
            "calculation_version": req.calculation_version,
            "changes_from_prior_version": changes,
            "snapshot_at": now.isoformat(),
        }

        new_ver = RequestVersionRead(
            id=new_ver_id,
            request_id=req_id,
            version_number=next_ver_number,
            snapshot=snapshot,
            created_at=now,
        )
        versions.append(new_ver)

        return req, new_ver

    # ─────────────────────────────────────────────────────────────────────────
    # 4. Human Approval Gating (Tied to Exact Version)
    # ─────────────────────────────────────────────────────────────────────────

    def approve_or_reject_request(
        self,
        request_id: UUID | str,
        approver_id: UUID | str,
        action: ApprovalAction,
        target_version_number: int | None = None,
        notes: str | None = None,
    ) -> tuple[ApprovalRead, ReorderRequestRead]:
        """Record human approval or rejection tied to the exact request version.

        Safety Checks:
        - Cannot approve a request that has already been submitted or verified.
        - If target_version_number is specified, it MUST match the latest active version.
        """
        req_id = UUID(str(request_id))
        appr_id = UUID(str(approver_id))

        if req_id not in self._requests:
            raise KeyError(f"Reorder request '{req_id}' not found")

        req = self._requests[req_id]
        if req.status in (RequestStatus.SUBMITTED_OR_SIMULATED, RequestStatus.VERIFIED):
            raise ValueError(f"Cannot approve request with status '{req.status.value}'")

        latest_ver = self.get_latest_version(req_id)
        if target_version_number is not None and target_version_number != latest_ver.version_number:
            raise ValueError(
                f"Version mismatch: Approval was submitted for version {target_version_number}, "
                f"but current active proposal is version {latest_ver.version_number}."
            )

        now = datetime.now(timezone.utc)
        appr_record = ApprovalRead(
            id=uuid.uuid4(),
            request_id=req_id,
            request_version_id=latest_ver.id,
            approver_id=appr_id,
            action=action,
            notes=notes,
            timestamp=now,
        )

        if req_id not in self._approvals:
            self._approvals[req_id] = []
        self._approvals[req_id].append(appr_record)

        if action == ApprovalAction.APPROVED:
            req.status = RequestStatus.APPROVED
            req.updated_at = now
            self.log_audit_event(
                request_id=req_id,
                event_type=AuditEventType.APPROVED,
                actor_id=appr_id,
                details={
                    "version_number": latest_ver.version_number,
                    "version_id": str(latest_ver.id),
                    "notes": notes,
                },
            )
        else:
            req.status = RequestStatus.REJECTED
            req.updated_at = now
            self.log_audit_event(
                request_id=req_id,
                event_type=AuditEventType.REJECTED,
                actor_id=appr_id,
                details={
                    "version_number": latest_ver.version_number,
                    "version_id": str(latest_ver.id),
                    "notes": notes,
                },
            )

        return appr_record, req

    # ─────────────────────────────────────────────────────────────────────────
    # 5. Simulated Order Submission (Approval Required)
    # ─────────────────────────────────────────────────────────────────────────

    def submit_request(
        self,
        request_id: UUID | str,
        actor_id: UUID | str,
        simulated: bool = True,
        force_failure: bool = False,
        failure_reason: str | None = None,
    ) -> tuple[ReorderRequestRead, dict[str, Any]]:
        """Submit a reorder request with mandatory human approval gating.

        MANDATORY GATES:
        - Request must have status = APPROVED.
        - Approval must match the current request version.
        - Defaults to simulated mode (records mock PO ID); never connects to live procurement.
        - If submission fails, marks status = FAILED and keeps failure visible.
        """
        req_id = UUID(str(request_id))
        act_id = UUID(str(actor_id))

        if req_id not in self._requests:
            raise KeyError(f"Reorder request '{req_id}' not found")

        req = self._requests[req_id]

        # Gate 1: Approval status
        if req.status != RequestStatus.APPROVED:
            raise PermissionError(
                f"Consequential action blocked: Request '{req_id}' has status '{req.status.value}'. "
                "Human approval is mandatory before submission."
            )

        # Gate 2: Approval version integrity
        latest_ver = self.get_latest_version(req_id)
        latest_appr = self.get_latest_approval(req_id)
        if latest_appr is None or latest_appr.action != ApprovalAction.APPROVED:
            raise PermissionError("Consequential action blocked: No valid approval record found.")

        if latest_appr.request_version_id != latest_ver.id:
            req.status = RequestStatus.NEEDS_REVIEW
            self.log_audit_event(
                request_id=req_id,
                event_type=AuditEventType.VERSION_INVALIDATED,
                actor_id=act_id,
                details={"reason": "Submission blocked: proposal modified after approval was granted."},
            )
            raise PermissionError("Consequential action blocked: Proposal changed after approval was granted.")

        now = datetime.now(timezone.utc)

        # Handle forced/simulated failure
        if force_failure:
            req.status = RequestStatus.FAILED
            req.updated_at = now
            reason = failure_reason or "Supplier submission gateway error (simulated timeout)"
            self.log_audit_event(
                request_id=req_id,
                event_type=AuditEventType.FAILED,
                actor_id=act_id,
                details={"simulated": simulated, "error": reason},
            )
            return req, {"success": False, "status": "failed", "error": reason}

        # Simulated submission success
        sim_po_ref = f"SIM-PO-{uuid.uuid4().hex[:8].upper()}"
        req.status = RequestStatus.SUBMITTED_OR_SIMULATED
        req.updated_at = now

        result_payload = {
            "success": True,
            "status": "submitted_or_simulated",
            "simulated": simulated,
            "order_reference": sim_po_ref,
            "submitted_at": now.isoformat(),
            "submitted_sku": req.sku,
            "submitted_quantity": str(req.proposed_quantity),
            "pack_count": req.pack_count,
            "estimated_cost": str(req.estimated_cost),
        }

        self.log_audit_event(
            request_id=req_id,
            event_type=AuditEventType.SUBMITTED,
            actor_id=act_id,
            details=result_payload,
        )

        return req, result_payload

    # ─────────────────────────────────────────────────────────────────────────
    # 6. Independent Outcome Verification
    # ─────────────────────────────────────────────────────────────────────────

    def verify_submission_outcome(
        self,
        request_id: UUID | str,
        actual_sku: str,
        actual_quantity: Decimal | int | float,
        actual_pack_size: int | None = None,
        existing_open_po_references: Sequence[str] | None = None,
        actor_id: UUID | str | None = None,
    ) -> tuple[VerificationResultRead, ReorderRequestRead]:
        """Perform independent verification comparing actual outcome with intended request.

        Independent checks:
        - intended SKU == actual SKU
        - intended quantity == actual quantity
        - pack size check (quantity is valid multiple of pack size)
        - duplicate check (order reference or intent not already duplicated)
        """
        req_id = UUID(str(request_id))
        act_id = UUID(str(actor_id)) if actor_id else None

        if req_id not in self._requests:
            raise KeyError(f"Reorder request '{req_id}' not found")

        req = self._requests[req_id]
        now = datetime.now(timezone.utc)
        act_qty = Decimal(str(actual_quantity))

        # 1. SKU check
        sku_match = (req.sku.strip().upper() == actual_sku.strip().upper())

        # 2. Quantity check
        quantity_match = (req.proposed_quantity == act_qty)

        # 3. Pack size check
        p_size = actual_pack_size or req.pack_size
        pack_size_check = True
        if p_size > 1 and act_qty > Decimal("0"):
            pack_size_check = (int(act_qty) % p_size == 0)

        # 4. Duplicate check
        duplicate_check = True
        if existing_open_po_references and len(existing_open_po_references) > 1:
            duplicate_check = False  # Multiple identical POs detected

        all_passed = sku_match and quantity_match and pack_size_check and duplicate_check

        # Evidence explanation
        notes: list[str] = []
        if not sku_match:
            notes.append(f"SKU mismatch: intended '{req.sku}' vs actual '{actual_sku}'")
        if not quantity_match:
            notes.append(f"Quantity mismatch: intended {req.proposed_quantity} vs actual {act_qty}")
        if not pack_size_check:
            notes.append(f"Pack size violation: actual quantity {act_qty} not divisible by pack size {p_size}")
        if not duplicate_check:
            notes.append("Duplicate check failed: duplicate PO reference detected in open orders")

        if all_passed:
            v_status = VerificationStatus.VERIFIED
            req.status = RequestStatus.VERIFIED
            evidence_str = (
                f"Verification successful: SKU matched ('{req.sku}'), "
                f"quantity matched ({req.proposed_quantity}), pack size valid ({p_size}), no duplicate PO."
            )
        else:
            v_status = VerificationStatus.FAILED
            req.status = RequestStatus.FAILED
            evidence_str = f"Verification failed: {'; '.join(notes)}"

        req.updated_at = now

        ver_result = VerificationResultRead(
            id=uuid.uuid4(),
            request_id=req_id,
            intended_sku=req.sku,
            actual_sku=actual_sku,
            sku_match=sku_match,
            intended_quantity=req.proposed_quantity,
            actual_quantity=act_qty,
            quantity_match=quantity_match,
            pack_size_check=pack_size_check,
            duplicate_check=duplicate_check,
            status=v_status,
            evidence=evidence_str,
            verified_at=now,
        )

        if req_id not in self._verifications:
            self._verifications[req_id] = []
        self._verifications[req_id].append(ver_result)

        event_type = AuditEventType.VERIFIED if all_passed else AuditEventType.FAILED
        self.log_audit_event(
            request_id=req_id,
            event_type=event_type,
            actor_id=act_id,
            details={
                "verification_status": v_status.value,
                "sku_match": sku_match,
                "quantity_match": quantity_match,
                "pack_size_check": pack_size_check,
                "duplicate_check": duplicate_check,
                "evidence": evidence_str,
            },
        )

        return ver_result, req

    # ─────────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────────

    def get_request(self, request_id: UUID | str) -> ReorderRequestRead | None:
        return self._requests.get(UUID(str(request_id)))

    def get_latest_version(self, request_id: UUID | str) -> RequestVersionRead:
        req_id = UUID(str(request_id))
        versions = self._versions.get(req_id, [])
        if not versions:
            raise KeyError(f"No versions found for request '{req_id}'")
        return versions[-1]

    def get_versions(self, request_id: UUID | str) -> list[RequestVersionRead]:
        return list(self._versions.get(UUID(str(request_id)), []))

    def get_latest_approval(self, request_id: UUID | str) -> ApprovalRead | None:
        approvals = self._approvals.get(UUID(str(request_id)), [])
        return approvals[-1] if approvals else None

    def get_latest_verification(self, request_id: UUID | str) -> VerificationResultRead | None:
        verifications = self._verifications.get(UUID(str(request_id)), [])
        return verifications[-1] if verifications else None
