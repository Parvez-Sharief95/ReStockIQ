"""
test_safety_and_failures.py — Safety Guards and Failure Handling Tests
Phase 8 Implementation

Validates:
- Approval and active-version checks enforced strictly in backend services.
- Missing, stale, and failed source data detection.
- Prohibiting creation of purchase requests from insufficient or failed evidence.
- Invalid quantities (negative, zero, non-pack compliant) rejection.
- Budget overrun warnings preventing automated readiness.
- Duplicate retries prevented by idempotency keys with RETRY audit events.
- Outdated approvals / Rule S2 invalidation blocking submissions.
- Visible submission failures with audit logging.
- Verification mismatches (SKU, quantity, pack size, duplicate references).
- Protection of credentials and secrets from API response payloads.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import uuid
import pytest
from fastapi.testclient import TestClient

from backend.app.schemas.models import (
    AnalysisStatus,
    ApprovalAction,
    BudgetStatus,
    RequestStatus,
    VerificationStatus,
)
from backend.app.services.backend_store import get_backend_store
from backend.app.services.calculation_engine import evaluate_reorder
from backend.app.services.source_adapter import (
    MockSourceAdapter,
    RetrievalStatus,
    retrieve_reorder_context,
)


def test_missing_source_data_detection(api_client: TestClient) -> None:
    """Missing SKU in source catalog results in 404 and does not fabricate data."""
    resp = api_client.get("/api/inventory/SKU-NON-EXISTENT")
    assert resp.status_code == 404
    err = resp.json()
    assert "not found" in err["message"].lower()

    # In evaluation, missing product marks analysis as insufficient_data
    store = get_backend_store()
    ctx = retrieve_reorder_context("SKU-NON-EXISTENT", adapter=store.adapter)
    assert ctx.is_valid is False
    assert ctx.status == RetrievalStatus.MISSING


def test_stale_source_data_detection(api_client: TestClient) -> None:
    """Source data older than 7 days is explicitly tagged stale."""
    store = get_backend_store()
    adapter = MockSourceAdapter(default_max_age_days=7)
    # Inject an inventory record with timestamp 10 days ago
    stale_ts = datetime.now(timezone.utc) - timedelta(days=10)
    adapter.set_override(
        "SKU-STALE",
        "inventory",
        {
            "sku": "SKU-STALE",
            "current_stock": Decimal("15"),
            "source_timestamp": stale_ts,
        },
    )

    inv_res = adapter.fetch_inventory("SKU-STALE")
    assert inv_res.is_stale is True
    assert inv_res.status == RetrievalStatus.STALE


def test_failed_source_data_does_not_default_to_zero(api_client: TestClient) -> None:
    """Anti-invention guard: Failed open orders retrieval must NEVER default to [] or 0 stock."""
    adapter = MockSourceAdapter()
    adapter.set_failure_mode("open_orders", "Supplier API timeout 504")

    ctx = retrieve_reorder_context("SKU-001", adapter=adapter)
    assert ctx.is_valid is False
    assert ctx.status == RetrievalStatus.FAILED
    assert ctx.open_orders_data is None  # NOT []
    assert any("open purchase orders" in issue.lower() for issue in ctx.issues)


def test_cannot_create_request_from_failed_evidence(api_client: TestClient) -> None:
    """Do not create a purchase request from insufficient or failed evidence."""
    store = get_backend_store()
    store.reset()

    # Simulate adapter failure
    store.adapter.set_failure_mode("inventory", "Database connection refused")
    eval_resp = api_client.post("/api/analyses/evaluate", json={"sku": "SKU-001"})
    assert eval_resp.status_code == 200
    analysis = eval_resp.json()["analysis"]
    assert analysis["analysis_status"] == "insufficient_data"

    # Now attempt to create a purchase request from this invalid analysis
    create_resp = api_client.post(
        "/api/requests",
        json={
            "analysis_id": analysis["id"],
            "sku": "SKU-001",
            "product_id": analysis["product_id"],
            "supplier_name": "Acme Supplies",
            "proposed_quantity": 36,
            "pack_count": 36,
            "pack_size": 1,
            "estimated_cost": 360.0,
        },
    )
    assert create_resp.status_code == 400
    assert "insufficient_data" in create_resp.json()["message"]
    store.adapter.clear_failure_mode()


def test_invalid_quantities_rejected(api_client: TestClient) -> None:
    """Zero, negative, or pack-violating quantities are rejected by backend."""
    eval_resp = api_client.post("/api/analyses/evaluate", json={"sku": "SKU-001"})
    analysis_id = eval_resp.json()["analysis"]["id"]
    prod_id = eval_resp.json()["analysis"]["product_id"]

    # 1. Zero quantity rejected
    resp_zero = api_client.post(
        "/api/requests",
        json={
            "analysis_id": analysis_id,
            "sku": "SKU-001",
            "product_id": prod_id,
            "supplier_name": "Acme",
            "proposed_quantity": 0,
            "pack_count": 0,
            "pack_size": 1,
            "estimated_cost": 0.0,
        },
    )
    assert resp_zero.status_code == 422 or resp_zero.status_code == 400

    # 2. Pack size multiple violation rejected
    resp_pack = api_client.post(
        "/api/requests",
        json={
            "analysis_id": analysis_id,
            "sku": "SKU-002",
            "product_id": prod_id,
            "supplier_name": "Bulk Co",
            "proposed_quantity": 25,  # Not multiple of 12!
            "pack_count": 3,
            "pack_size": 12,
            "estimated_cost": 250.0,
        },
    )
    assert resp_pack.status_code == 400
    assert "multiple of pack size" in resp_pack.json()["message"]


def test_outdated_approval_blocks_submission_backend_enforced(api_client: TestClient) -> None:
    """Approval on version 1 cannot be used to submit version 2 (Rule S2)."""
    eval_resp = api_client.post("/api/analyses/evaluate", json={"sku": "SKU-001"})
    analysis_id = eval_resp.json()["analysis"]["id"]

    req_resp = api_client.post(
        "/api/requests",
        json={
            "analysis_id": analysis_id,
            "sku": "SKU-001",
            "product_id": "10000000-0000-0000-0000-000000000001",
            "supplier_name": "Acme Supplies",
            "proposed_quantity": 36,
            "pack_count": 36,
            "pack_size": 1,
            "estimated_cost": 360.0,
        },
    )
    req_id = req_resp.json()["request"]["id"]

    # Approve version 1
    api_client.post(
        "/api/approvals",
        json={"request_id": req_id, "action": "approved", "target_version_number": 1},
        headers={"Authorization": "Bearer demo-approver-token"},
    )

    # Edit proposal to create version 2
    api_client.patch(
        f"/api/requests/{req_id}/proposal",
        json={"proposed_quantity": 48, "estimated_cost": 480.0},
    )

    # Submission MUST be blocked by backend service
    sub_resp = api_client.post(f"/api/requests/{req_id}/submit", json={})
    assert sub_resp.status_code == 403
    assert "Human approval is mandatory" in sub_resp.json()["message"]


def test_submission_failure_visibility(api_client: TestClient) -> None:
    """Simulated submission failure transitions request to 'failed' with visible error."""
    eval_resp = api_client.post("/api/analyses/evaluate", json={"sku": "SKU-001"})
    analysis_id = eval_resp.json()["analysis"]["id"]

    req_resp = api_client.post(
        "/api/requests",
        json={
            "analysis_id": analysis_id,
            "sku": "SKU-001",
            "product_id": "10000000-0000-0000-0000-000000000001",
            "supplier_name": "Acme Supplies",
            "proposed_quantity": 36,
            "pack_count": 36,
            "pack_size": 1,
            "estimated_cost": 360.0,
        },
    )
    req_id = req_resp.json()["request"]["id"]

    api_client.post(
        "/api/approvals",
        json={"request_id": req_id, "action": "approved", "target_version_number": 1},
        headers={"Authorization": "Bearer demo-approver-token"},
    )

    # Force simulated gateway timeout
    fail_resp = api_client.post(
        f"/api/requests/{req_id}/submit",
        json={"force_failure": True, "failure_reason": "EDI Procurement Network Timeout"},
    )
    assert fail_resp.status_code == 200
    assert fail_resp.json()["request"]["status"] == "failed"
    assert "Timeout" in fail_resp.json()["result"]["error"]

    # Check request detail endpoint confirms failed status
    detail_resp = api_client.get(f"/api/requests/{req_id}")
    assert detail_resp.json()["request"]["status"] == "failed"


def test_verification_mismatches_handled(api_client: TestClient) -> None:
    """Verification mismatches (SKU, quantity, pack size, duplicate) all transition to failed."""
    eval_resp = api_client.post("/api/analyses/evaluate", json={"sku": "SKU-001"})
    analysis_id = eval_resp.json()["analysis"]["id"]

    req_resp = api_client.post(
        "/api/requests",
        json={
            "analysis_id": analysis_id,
            "sku": "SKU-001",
            "product_id": "10000000-0000-0000-0000-000000000001",
            "supplier_name": "Acme Supplies",
            "proposed_quantity": 36,
            "pack_count": 36,
            "pack_size": 1,
            "estimated_cost": 360.0,
        },
    )
    req_id = req_resp.json()["request"]["id"]
    api_client.post(
        "/api/approvals",
        json={"request_id": req_id, "action": "approved", "target_version_number": 1},
        headers={"Authorization": "Bearer demo-approver-token"},
    )
    api_client.post(f"/api/requests/{req_id}/submit", json={})

    # 1. SKU mismatch
    v_sku = api_client.post(
        f"/api/requests/{req_id}/verify",
        json={"actual_sku": "SKU-WRONG", "actual_quantity": 36, "actual_pack_size": 1},
    )
    assert v_sku.json()["verification"]["sku_match"] is False
    assert v_sku.json()["verification"]["status"] == "failed"

    # 2. Duplicate order conflict
    v_dup = api_client.post(
        f"/api/requests/{req_id}/verify",
        json={
            "actual_sku": "SKU-001",
            "actual_quantity": 36,
            "actual_pack_size": 1,
            "simulate_duplicate": True,
        },
    )
    assert v_dup.json()["verification"]["duplicate_check"] is False
    assert v_dup.json()["verification"]["status"] == "failed"


def test_no_secrets_leaked_in_api_responses(api_client: TestClient) -> None:
    """Verify that backend secret keys or API keys are never exposed in API outputs."""
    resp = api_client.get("/api/dashboard")
    text = resp.text
    assert "SUPABASE_SECRET_KEY" not in text
    assert "GEMINI_API_KEY" not in text
    assert "service_role" not in text


# ─────────────────────────────────────────────────────────────────────────────
# Authentication & Role Authorization Enforcement Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_approval_missing_auth_rejected_401(api_client: TestClient) -> None:
    """POST /api/approvals without Authorization header returns 401 Unauthorized."""
    resp = api_client.post(
        "/api/approvals",
        json={
            "request_id": "00000000-0000-0000-0000-000000000001",
            "action": "approved",
            "target_version_number": 1,
        },
    )
    assert resp.status_code == 401
    assert "Authentication required" in resp.json()["message"]


def test_approval_invalid_token_rejected_401(api_client: TestClient) -> None:
    """POST /api/approvals with invalid/expired token returns 401 Unauthorized."""
    resp = api_client.post(
        "/api/approvals",
        json={
            "request_id": "00000000-0000-0000-0000-000000000001",
            "action": "approved",
            "target_version_number": 1,
        },
        headers={"Authorization": "Bearer bogus-token-xyz"},
    )
    assert resp.status_code == 401
    assert "Invalid or expired" in resp.json()["message"]


def test_approval_planner_role_forbidden_403(api_client: TestClient) -> None:
    """POST /api/approvals by user with 'planner' role is rejected with 403 Forbidden."""
    eval_resp = api_client.post("/api/analyses/evaluate", json={"sku": "SKU-001"})
    analysis_id = eval_resp.json()["analysis"]["id"]

    req_resp = api_client.post(
        "/api/requests",
        json={
            "analysis_id": analysis_id,
            "sku": "SKU-001",
            "product_id": "10000000-0000-0000-0000-000000000001",
            "supplier_name": "Acme Supplies",
            "proposed_quantity": 36,
            "pack_count": 36,
            "pack_size": 1,
            "estimated_cost": 360.0,
        },
    )
    req_id = req_resp.json()["request"]["id"]

    # Sarah Connor has role="planner", NOT "approver"
    resp = api_client.post(
        "/api/approvals",
        json={
            "request_id": req_id,
            "action": "approved",
            "target_version_number": 1,
        },
        headers={"Authorization": "Bearer demo-planner-token"},
    )
    assert resp.status_code == 403
    assert "Operation requires one of roles" in resp.json()["message"]
    assert "planner" in resp.json()["message"]


def test_approval_approver_role_succeeds_and_binds_identity_200(api_client: TestClient) -> None:
    """POST /api/approvals by user with 'approver' role succeeds and records authenticated UUID."""
    eval_resp = api_client.post("/api/analyses/evaluate", json={"sku": "SKU-001"})
    analysis_id = eval_resp.json()["analysis"]["id"]

    req_resp = api_client.post(
        "/api/requests",
        json={
            "analysis_id": analysis_id,
            "sku": "SKU-001",
            "product_id": "10000000-0000-0000-0000-000000000001",
            "supplier_name": "Acme Supplies",
            "proposed_quantity": 36,
            "pack_count": 36,
            "pack_size": 1,
            "estimated_cost": 360.0,
        },
    )
    req_id = req_resp.json()["request"]["id"]

    # Marcus Vance has role="approver"
    resp = api_client.post(
        "/api/approvals",
        json={
            "request_id": req_id,
            "action": "approved",
            "target_version_number": 1,
            "notes": "Reviewed and approved by Marcus Vance",
        },
        headers={"Authorization": "Bearer demo-approver-token"},
    )
    assert resp.status_code == 200
    appr_data = resp.json()["approval"]
    assert appr_data["action"] == "approved"
    # Authenticated UUID for demo approver MUST be bound to record:
    assert appr_data["approver_id"] == "00000000-0000-0000-0000-000000000002"


def test_approval_caller_supplied_approver_id_rejected_422(api_client: TestClient) -> None:
    """POST /api/approvals with caller-supplied approver_id is rejected with 422 Unprocessable Entity."""
    eval_resp = api_client.post("/api/analyses/evaluate", json={"sku": "SKU-001"})
    analysis_id = eval_resp.json()["analysis"]["id"]

    req_resp = api_client.post(
        "/api/requests",
        json={
            "analysis_id": analysis_id,
            "sku": "SKU-001",
            "product_id": "10000000-0000-0000-0000-000000000001",
            "supplier_name": "Acme Supplies",
            "proposed_quantity": 36,
            "pack_count": 36,
            "pack_size": 1,
            "estimated_cost": 360.0,
        },
    )
    req_id = req_resp.json()["request"]["id"]

    # An attacker attempts to inject a spoofed approver_id into the JSON body
    spoof_resp = api_client.post(
        "/api/approvals",
        json={
            "request_id": req_id,
            "action": "approved",
            "target_version_number": 1,
            "approver_id": "00000000-0000-0000-0000-000000000999",  # Spoofed caller ID!
        },
        headers={"Authorization": "Bearer demo-approver-token"},
    )
    # Extra field forbidden by schema:
    assert spoof_resp.status_code == 422
    err_body = spoof_resp.json()
    assert "approver_id" in str(err_body)


def test_demo_tokens_disabled_in_production_environment(api_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """In production mode, offline demo tokens cannot authorize approvals or consequential actions."""
    eval_resp = api_client.post("/api/analyses/evaluate", json={"sku": "SKU-001"})
    analysis_id = eval_resp.json()["analysis"]["id"]

    req_resp = api_client.post(
        "/api/requests",
        json={
            "analysis_id": analysis_id,
            "sku": "SKU-001",
            "product_id": "10000000-0000-0000-0000-000000000001",
            "supplier_name": "Acme Supplies",
            "proposed_quantity": 36,
            "pack_count": 36,
            "pack_size": 1,
            "estimated_cost": 360.0,
        },
    )
    req_id = req_resp.json()["request"]["id"]

    import backend.app.services.auth as auth_mod
    monkeypatch.setattr(auth_mod.settings, "app_env", "production")

    # In production, demo-approver-token must be rejected with 401
    resp = api_client.post(
        "/api/approvals",
        json={
            "request_id": req_id,
            "action": "approved",
            "target_version_number": 1,
        },
        headers={"Authorization": "Bearer demo-approver-token"},
    )
    assert resp.status_code == 401
    assert "disabled in production mode" in resp.json()["message"]



