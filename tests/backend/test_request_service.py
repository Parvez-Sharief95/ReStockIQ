"""
test_request_service.py — Reorder Requests, Approval, Idempotency & Verification Tests
Phase 5 Implementation

Tests cover:
1. Request lifecycle & immutable version creation
2. Idempotency protection & duplicate submission retries
3. Mandatory human approval gating (unapproved submissions blocked)
4. Approval tied to exact request version
5. Proposal changes after approval invalidate prior approval (Rule S2)
6. Rejected requests handling (blocks submission)
7. Simulated submission success & visible failure states
8. Independent verification matching (SKU, quantity, pack size, duplicates)
9. Independent verification mismatch detection & failure visibility
10. Chronological append-only audit trail logging
"""
import sys
import os
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

# Ensure project root is in sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.app.schemas.models import (
    ApprovalAction,
    AuditEventType,
    RequestStatus,
    VerificationStatus,
)
from backend.app.services.request_service import (
    RequestService,
    generate_idempotency_key,
)


@pytest.fixture
def service() -> RequestService:
    return RequestService()


@pytest.fixture
def user_id() -> UUID:
    return UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture
def approver_id() -> UUID:
    return UUID("00000000-0000-0000-0000-000000000002")


@pytest.fixture
def analysis_id() -> UUID:
    return UUID("60000000-0000-0000-0000-000000000001")


@pytest.fixture
def product_id() -> UUID:
    return UUID("10000000-0000-0000-0000-000000000001")


# ─────────────────────────────────────────────────────────────────────────────
# 1. Request Creation, Versioning, and Idempotency Retries
# ─────────────────────────────────────────────────────────────────────────────


def test_create_request_success(service, user_id, analysis_id, product_id):
    """Verify request is created in pending_approval with immutable version 1."""
    req, ver, is_dup = service.create_reorder_request(
        user_id=user_id,
        analysis_id=analysis_id,
        product_id=product_id,
        sku="SKU-001",
        supplier_name="Acme Supplies",
        proposed_quantity=Decimal("36"),
        pack_count=36,
        pack_size=1,
        estimated_cost=Decimal("360.00"),
    )

    assert is_dup is False
    assert req.status == RequestStatus.PENDING_APPROVAL
    assert req.sku == "SKU-001"
    assert req.proposed_quantity == Decimal("36")
    assert ver.version_number == 1
    assert ver.snapshot["proposed_quantity"] == "36"

    # Audit event logged
    audit = service.get_audit_trail(req.id)
    assert len(audit) == 1
    assert audit[0].event_type == AuditEventType.PROPOSED


def test_idempotency_protection_duplicate_retry(service, user_id, analysis_id, product_id):
    """Submitting duplicate request with same key returns existing request without duplicating."""
    stable_key = generate_idempotency_key(user_id, "SKU-001", analysis_id, version_number=1)

    # First attempt: creates request
    req1, ver1, is_dup1 = service.create_reorder_request(
        user_id=user_id,
        analysis_id=analysis_id,
        product_id=product_id,
        sku="SKU-001",
        supplier_name="Acme Supplies",
        proposed_quantity=Decimal("36"),
        pack_count=36,
        pack_size=1,
        estimated_cost=Decimal("360.00"),
        idempotency_key=stable_key,
    )
    assert is_dup1 is False

    # Second attempt with same key: idempotent hit
    req2, ver2, is_dup2 = service.create_reorder_request(
        user_id=user_id,
        analysis_id=analysis_id,
        product_id=product_id,
        sku="SKU-001",
        supplier_name="Acme Supplies",
        proposed_quantity=Decimal("36"),
        pack_count=36,
        pack_size=1,
        estimated_cost=Decimal("360.00"),
        idempotency_key=stable_key,
    )
    assert is_dup2 is True
    assert req1.id == req2.id
    assert ver1.id == ver2.id

    # Verify audit trail logs RETRY
    audit = service.get_audit_trail(req1.id)
    assert len(audit) == 2
    assert audit[0].event_type == AuditEventType.PROPOSED
    assert audit[1].event_type == AuditEventType.RETRY


# ─────────────────────────────────────────────────────────────────────────────
# 2. Mandatory Human Approval Gating
# ─────────────────────────────────────────────────────────────────────────────


def test_submission_blocked_without_approval(service, user_id, analysis_id, product_id):
    """Submitting a request that is still in pending_approval must be blocked."""
    req, _, _ = service.create_reorder_request(
        user_id=user_id,
        analysis_id=analysis_id,
        product_id=product_id,
        sku="SKU-001",
        supplier_name="Acme Supplies",
        proposed_quantity=Decimal("36"),
        pack_count=36,
        pack_size=1,
        estimated_cost=Decimal("360.00"),
    )

    with pytest.raises(PermissionError) as exc_info:
        service.submit_request(request_id=req.id, actor_id=user_id)

    assert "Human approval is mandatory" in str(exc_info.value)
    assert req.status == RequestStatus.PENDING_APPROVAL


def test_human_approval_success(service, user_id, approver_id, analysis_id, product_id):
    """Human approval records approver identity, timestamp, and version ID."""
    req, ver, _ = service.create_reorder_request(
        user_id=user_id,
        analysis_id=analysis_id,
        product_id=product_id,
        sku="SKU-001",
        supplier_name="Acme Supplies",
        proposed_quantity=Decimal("36"),
        pack_count=36,
        pack_size=1,
        estimated_cost=Decimal("360.00"),
    )

    appr, updated_req = service.approve_or_reject_request(
        request_id=req.id,
        approver_id=approver_id,
        action=ApprovalAction.APPROVED,
        target_version_number=1,
        notes="Reviewed and approved for purchase order.",
    )

    assert appr.action == ApprovalAction.APPROVED
    assert appr.approver_id == approver_id
    assert appr.request_version_id == ver.id
    assert updated_req.status == RequestStatus.APPROVED

    # Audit event logged
    audit = service.get_audit_trail(req.id)
    assert audit[-1].event_type == AuditEventType.APPROVED


def test_rejection_blocks_submission(service, user_id, approver_id, analysis_id, product_id):
    """Rejection sets status to REJECTED and strictly blocks submission."""
    req, _, _ = service.create_reorder_request(
        user_id=user_id,
        analysis_id=analysis_id,
        product_id=product_id,
        sku="SKU-001",
        supplier_name="Acme Supplies",
        proposed_quantity=Decimal("36"),
        pack_count=36,
        pack_size=1,
        estimated_cost=Decimal("360.00"),
    )

    appr, updated_req = service.approve_or_reject_request(
        request_id=req.id,
        approver_id=approver_id,
        action=ApprovalAction.REJECTED,
        notes="Over budget or redundant order.",
    )
    assert updated_req.status == RequestStatus.REJECTED

    with pytest.raises(PermissionError) as exc_info:
        service.submit_request(request_id=req.id, actor_id=user_id)

    assert "rejected" in str(exc_info.value).lower()


# ─────────────────────────────────────────────────────────────────────────────
# 3. Approval Invalidation When Proposal Changes (Rule S2)
# ─────────────────────────────────────────────────────────────────────────────


def test_proposal_change_invalidates_prior_approval(service, user_id, approver_id, analysis_id, product_id):
    """RULE S2: Any modification to proposal after approval invalidates approval.

    Workflow:
    1. Propose 36 units (v1).
    2. Approve v1.
    3. Modify to 48 units -> creates v2, resets status to PENDING_APPROVAL, logs VERSION_INVALIDATED.
    4. Attempting to submit v2 without re-approval must fail!
    5. Re-approving v2 enables submission.
    """
    req, ver1, _ = service.create_reorder_request(
        user_id=user_id,
        analysis_id=analysis_id,
        product_id=product_id,
        sku="SKU-001",
        supplier_name="Acme Supplies",
        proposed_quantity=Decimal("36"),
        pack_count=36,
        pack_size=1,
        estimated_cost=Decimal("360.00"),
    )

    # Step 2: Approve v1
    service.approve_or_reject_request(
        request_id=req.id,
        approver_id=approver_id,
        action=ApprovalAction.APPROVED,
        target_version_number=1,
    )
    assert req.status == RequestStatus.APPROVED

    # Step 3: Modify proposal to 48 units
    updated_req, ver2 = service.update_proposal(
        request_id=req.id,
        actor_id=user_id,
        proposed_quantity=Decimal("48"),
        pack_count=48,
        estimated_cost=Decimal("480.00"),
        modification_reason="Demand spike expected; raised quantity.",
    )

    assert ver2.version_number == 2
    assert updated_req.status == RequestStatus.PENDING_APPROVAL
    assert updated_req.proposed_quantity == Decimal("48")

    # Audit log records VERSION_INVALIDATED
    audit = service.get_audit_trail(req.id)
    invalidated_events = [e for e in audit if e.event_type == AuditEventType.VERSION_INVALIDATED]
    assert len(invalidated_events) == 1

    # Step 4: Submission blocked without re-approval
    with pytest.raises(PermissionError) as exc_info:
        service.submit_request(request_id=req.id, actor_id=user_id)
    assert "Human approval is mandatory" in str(exc_info.value)

    # Step 5: Re-approve v2
    service.approve_or_reject_request(
        request_id=req.id,
        approver_id=approver_id,
        action=ApprovalAction.APPROVED,
        target_version_number=2,
    )
    assert updated_req.status == RequestStatus.APPROVED

    # Now submission succeeds
    sub_req, payload = service.submit_request(request_id=req.id, actor_id=user_id)
    assert sub_req.status == RequestStatus.SUBMITTED_OR_SIMULATED
    assert payload["success"] is True


def test_approve_obsolete_version_rejected(service, user_id, approver_id, analysis_id, product_id):
    """Approving an obsolete version number raises version mismatch error."""
    req, _, _ = service.create_reorder_request(
        user_id=user_id,
        analysis_id=analysis_id,
        product_id=product_id,
        sku="SKU-001",
        supplier_name="Acme Supplies",
        proposed_quantity=Decimal("36"),
        pack_count=36,
        pack_size=1,
        estimated_cost=Decimal("360.00"),
    )
    # Update to v2
    service.update_proposal(request_id=req.id, actor_id=user_id, proposed_quantity=Decimal("48"))

    # Attempting to approve v1 when v2 is active
    with pytest.raises(ValueError) as exc_info:
        service.approve_or_reject_request(
            request_id=req.id,
            approver_id=approver_id,
            action=ApprovalAction.APPROVED,
            target_version_number=1,  # Obsolete!
        )
    assert "Version mismatch" in str(exc_info.value)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Simulated Submission & Visible Failure States
# ─────────────────────────────────────────────────────────────────────────────


def test_simulated_submission_success(service, user_id, approver_id, analysis_id, product_id):
    """Simulated submission emits a mock PO reference and logs SUBMITTED."""
    req, _, _ = service.create_reorder_request(
        user_id=user_id,
        analysis_id=analysis_id,
        product_id=product_id,
        sku="SKU-001",
        supplier_name="Acme Supplies",
        proposed_quantity=Decimal("36"),
        pack_count=36,
        pack_size=1,
        estimated_cost=Decimal("360.00"),
    )
    service.approve_or_reject_request(req.id, approver_id, ApprovalAction.APPROVED)

    submitted_req, payload = service.submit_request(req.id, actor_id=user_id, simulated=True)
    assert submitted_req.status == RequestStatus.SUBMITTED_OR_SIMULATED
    assert payload["simulated"] is True
    assert payload["order_reference"].startswith("SIM-PO-")


def test_submission_failure_is_visible(service, user_id, approver_id, analysis_id, product_id):
    """Simulated failure marks status FAILED, retains error reason, and logs FAILED."""
    req, _, _ = service.create_reorder_request(
        user_id=user_id,
        analysis_id=analysis_id,
        product_id=product_id,
        sku="SKU-001",
        supplier_name="Acme Supplies",
        proposed_quantity=Decimal("36"),
        pack_count=36,
        pack_size=1,
        estimated_cost=Decimal("360.00"),
    )
    service.approve_or_reject_request(req.id, approver_id, ApprovalAction.APPROVED)

    failed_req, payload = service.submit_request(
        req.id,
        actor_id=user_id,
        force_failure=True,
        failure_reason="Supplier EDI timeout after 3 retries",
    )
    assert failed_req.status == RequestStatus.FAILED
    assert payload["success"] is False
    assert "Supplier EDI timeout" in payload["error"]

    # Audit log records FAILED
    audit = service.get_audit_trail(req.id)
    assert audit[-1].event_type == AuditEventType.FAILED


# ─────────────────────────────────────────────────────────────────────────────
# 5. Independent Verification Matching & Mismatches
# ─────────────────────────────────────────────────────────────────────────────


def test_verification_success(service, user_id, approver_id, analysis_id, product_id):
    """Successful verification confirms SKU, quantity, pack size, and no duplicates."""
    req, _, _ = service.create_reorder_request(
        user_id=user_id,
        analysis_id=analysis_id,
        product_id=product_id,
        sku="SKU-001",
        supplier_name="Acme Supplies",
        proposed_quantity=Decimal("36"),
        pack_count=36,
        pack_size=1,
        estimated_cost=Decimal("360.00"),
    )
    service.approve_or_reject_request(req.id, approver_id, ApprovalAction.APPROVED)
    service.submit_request(req.id, actor_id=user_id)

    # Independent verification
    ver_res, updated_req = service.verify_submission_outcome(
        request_id=req.id,
        actual_sku="SKU-001",
        actual_quantity=Decimal("36"),
        actual_pack_size=1,
        existing_open_po_references=["SIM-PO-1234"],
    )

    assert ver_res.status == VerificationStatus.VERIFIED
    assert ver_res.sku_match is True
    assert ver_res.quantity_match is True
    assert ver_res.pack_size_check is True
    assert ver_res.duplicate_check is True
    assert updated_req.status == RequestStatus.VERIFIED
    assert "Verification successful" in ver_res.evidence


def test_verification_sku_mismatch(service, user_id, approver_id, analysis_id, product_id):
    """SKU mismatch fails verification and transitions request to FAILED."""
    req, _, _ = service.create_reorder_request(
        user_id=user_id,
        analysis_id=analysis_id,
        product_id=product_id,
        sku="SKU-001",
        supplier_name="Acme Supplies",
        proposed_quantity=Decimal("36"),
        pack_count=36,
        pack_size=1,
        estimated_cost=Decimal("360.00"),
    )
    service.approve_or_reject_request(req.id, approver_id, ApprovalAction.APPROVED)
    service.submit_request(req.id, actor_id=user_id)

    ver_res, updated_req = service.verify_submission_outcome(
        request_id=req.id,
        actual_sku="SKU-WRONG-999",  # Mismatch!
        actual_quantity=Decimal("36"),
    )

    assert ver_res.status == VerificationStatus.FAILED
    assert ver_res.sku_match is False
    assert updated_req.status == RequestStatus.FAILED
    assert "SKU mismatch" in ver_res.evidence


def test_verification_quantity_mismatch(service, user_id, approver_id, analysis_id, product_id):
    """Quantity mismatch fails verification and transitions request to FAILED."""
    req, _, _ = service.create_reorder_request(
        user_id=user_id,
        analysis_id=analysis_id,
        product_id=product_id,
        sku="SKU-001",
        supplier_name="Acme Supplies",
        proposed_quantity=Decimal("36"),
        pack_count=36,
        pack_size=1,
        estimated_cost=Decimal("360.00"),
    )
    service.approve_or_reject_request(req.id, approver_id, ApprovalAction.APPROVED)
    service.submit_request(req.id, actor_id=user_id)

    ver_res, updated_req = service.verify_submission_outcome(
        request_id=req.id,
        actual_sku="SKU-001",
        actual_quantity=Decimal("24"),  # Mismatch: intended 36!
    )

    assert ver_res.status == VerificationStatus.FAILED
    assert ver_res.quantity_match is False
    assert updated_req.status == RequestStatus.FAILED
    assert "Quantity mismatch" in ver_res.evidence


def test_verification_pack_size_mismatch(service, user_id, approver_id, analysis_id, product_id):
    """Quantity violating pack size divisibility fails verification."""
    req, _, _ = service.create_reorder_request(
        user_id=user_id,
        analysis_id=analysis_id,
        product_id=product_id,
        sku="SKU-002",
        supplier_name="Bulk Co",
        proposed_quantity=Decimal("36"),
        pack_count=3,
        pack_size=12,
        estimated_cost=Decimal("360.00"),
    )
    service.approve_or_reject_request(req.id, approver_id, ApprovalAction.APPROVED)
    service.submit_request(req.id, actor_id=user_id)

    # Actual outcome was 35 units (not divisible by case size 12)
    ver_res, updated_req = service.verify_submission_outcome(
        request_id=req.id,
        actual_sku="SKU-002",
        actual_quantity=Decimal("35"),
        actual_pack_size=12,
    )

    assert ver_res.status == VerificationStatus.FAILED
    assert ver_res.pack_size_check is False
    assert updated_req.status == RequestStatus.FAILED
    assert "Pack size violation" in ver_res.evidence


def test_verification_duplicate_detected(service, user_id, approver_id, analysis_id, product_id):
    """Duplicate open PO references detected during verification trigger FAILED status."""
    req, _, _ = service.create_reorder_request(
        user_id=user_id,
        analysis_id=analysis_id,
        product_id=product_id,
        sku="SKU-001",
        supplier_name="Acme Supplies",
        proposed_quantity=Decimal("36"),
        pack_count=36,
        pack_size=1,
        estimated_cost=Decimal("360.00"),
    )
    service.approve_or_reject_request(req.id, approver_id, ApprovalAction.APPROVED)
    service.submit_request(req.id, actor_id=user_id)

    ver_res, updated_req = service.verify_submission_outcome(
        request_id=req.id,
        actual_sku="SKU-001",
        actual_quantity=Decimal("36"),
        existing_open_po_references=["PO-1", "PO-1"],  # Duplicate PO detected
    )

    assert ver_res.status == VerificationStatus.FAILED
    assert ver_res.duplicate_check is False
    assert updated_req.status == RequestStatus.FAILED
    assert "Duplicate check failed" in ver_res.evidence
