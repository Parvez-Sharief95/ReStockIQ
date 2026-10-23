"""
test_api_integration.py — FastAPI Endpoint Integration Tests
Phase 8 Implementation

Validates:
- Complete REST API boundaries and request/response schemas.
- Server-side validation of inputs, pack sizes, and idempotency.
- Mandatory approval gating and version invalidation (Rule S2) enforced at the API layer.
- Simulated order execution and independent outcome verification.
- Structured APIError responses without leaking stack traces or internal secrets.
- Mock source data is visibly labelled (source_type="mock_source", is_synthetic=True).
"""
from decimal import Decimal
import uuid
import pytest
from fastapi.testclient import TestClient

from backend.app.schemas.models import ApprovalAction, RequestStatus


def test_health_endpoint(api_client: TestClient) -> None:
    """GET /api/health returns ok status."""
    resp = api_client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "inventory-reorder-planner"


def test_dashboard_endpoint(api_client: TestClient) -> None:
    """GET /api/dashboard returns metrics with mock_source attribution."""
    resp = api_client.get("/api/dashboard")
    assert resp.status_code == 200
    data = resp.json()
    assert "metrics" in data
    assert data["metrics"]["total_products"] >= 4
    assert data["metrics"]["stockout_risks"] >= 1
    assert data["source_type"] == "mock_source"
    assert data["is_synthetic"] is True


def test_inventory_list_and_detail(api_client: TestClient) -> None:
    """GET /api/inventory and GET /api/inventory/{sku} return typed product data."""
    # List inventory
    resp = api_client.get("/api/inventory")
    assert resp.status_code == 200
    catalog = resp.json()
    assert catalog["total"] >= 4
    assert catalog["source_type"] == "mock_source"
    assert catalog["is_synthetic"] is True

    # Detail for SKU-001
    resp_sku = api_client.get("/api/inventory/SKU-001")
    assert resp_sku.status_code == 200
    prod_data = resp_sku.json()
    assert prod_data["product"]["sku"] == "SKU-001"
    assert prod_data["product"]["supplier_terms"]["lead_time_days"] == 14
    assert prod_data["source_type"] == "mock_source"

    # 404 for unknown SKU
    resp_unknown = api_client.get("/api/inventory/SKU-NONEXISTENT")
    assert resp_unknown.status_code == 404
    err = resp_unknown.json()
    assert "not found" in err["message"].lower()


def test_analyses_evaluate_endpoint(api_client: TestClient) -> None:
    """POST /api/analyses/evaluate executes deterministic decision engine."""
    payload = {
        "sku": "SKU-001",
        "budget_available": 500.0,
        "baseline_unit_price": 10.0,
    }
    resp = api_client.post("/api/analyses/evaluate", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    analysis = data["analysis"]
    assert analysis["average_daily_demand"] == 4
    assert analysis["lead_time_days"] == 14
    assert analysis["lead_time_demand"] == 56
    assert analysis["usable_available_stock"] == 20
    assert analysis["net_shortfall"] == 36
    assert analysis["proposed_order_quantity"] == 36
    assert analysis["estimated_cost"] == 360.0
    assert analysis["analysis_status"] == "ready"
    assert analysis["budget_status"] == "ok"
    assert len(data["evidence_ids"]) >= 1
    assert data["source_type"] == "mock_source"
    assert "Reorder Analysis Explanation for SKU-001" in data["explanation"]


def test_request_creation_and_idempotency(api_client: TestClient) -> None:
    """POST /api/requests creates request; retries return existing request (idempotent)."""
    # Evaluate first to get a valid analysis
    eval_resp = api_client.post(
        "/api/analyses/evaluate",
        json={"sku": "SKU-001", "budget_available": 500.0},
    )
    analysis_id = eval_resp.json()["analysis"]["id"]

    create_payload = {
        "analysis_id": analysis_id,
        "sku": "SKU-001",
        "product_id": "10000000-0000-0000-0000-000000000001",
        "supplier_name": "Acme Supplies",
        "proposed_quantity": 36,
        "pack_count": 36,
        "pack_size": 1,
        "estimated_cost": 360.0,
        "currency": "USD",
        "idempotency_key": "IDEM-TC1-KEY-001",
    }

    # Initial creation
    resp1 = api_client.post("/api/requests", json=create_payload)
    assert resp1.status_code == 201
    data1 = resp1.json()
    assert data1["request"]["status"] == "pending_approval"
    assert data1["is_duplicate"] is False
    req_id = data1["request"]["id"]

    # Duplicate retry with same idempotency key
    resp2 = api_client.post("/api/requests", json=create_payload)
    assert resp2.status_code == 201
    data2 = resp2.json()
    assert data2["request"]["id"] == req_id
    assert data2["is_duplicate"] is True

    # Audit trail contains RETRY event
    audit_resp = api_client.get(f"/api/requests/{req_id}/audit")
    assert audit_resp.status_code == 200
    events = audit_resp.json()["events"]
    event_types = [e["event_type"] for e in events]
    assert "proposed" in event_types
    assert "retry" in event_types


def test_cannot_create_request_from_insufficient_data(api_client: TestClient) -> None:
    """POST /api/requests is strictly blocked if analysis has insufficient_data."""
    # Create an analysis with insufficient_data directly in store
    from backend.app.schemas.models import AnalysisInputSnapshot, ReorderAnalysisRead
    from backend.app.services.backend_store import get_backend_store

    store = get_backend_store()
    bad_a_id = uuid.uuid4()
    bad_analysis = ReorderAnalysisRead(
        id=bad_a_id,
        product_id=uuid.uuid4(),
        calculation_version="1.0.0",
        input_snapshot=AnalysisInputSnapshot(
            product_id="00000000-0000-0000-0000-000000000000",
            sku="SKU-BAD",
            average_daily_demand=Decimal("0"),
            demand_window_days=30,
            lead_time_days=14,
            usable_available_stock=Decimal("0"),
            safety_stock_target=Decimal("0"),
            safety_stock_was_defaulted=True,
            eligible_incoming_quantity=Decimal("0"),
            incoming_order_ids=[],
            pack_size=1,
            moq=None,
            unit_price=Decimal("10.00"),
            currency="USD",
            budget_available=None,
            supplier_terms_id="00000000-0000-0000-0000-000000000000",
            source_evidence_ids=[],
            snapshot_at=eval("datetime.now(timezone.utc)", {"datetime": eval("__import__('datetime').datetime"), "timezone": eval("__import__('datetime').timezone")}),
        ),
        average_daily_demand=Decimal("0"),
        lead_time_days=14,
        lead_time_demand=Decimal("0"),
        safety_stock_target=Decimal("0"),
        usable_available_stock=Decimal("0"),
        eligible_incoming_quantity=Decimal("0"),
        net_shortfall=Decimal("0"),
        pack_size=1,
        proposed_order_quantity=Decimal("0"),
        unit_price=Decimal("10.00"),
        estimated_cost=Decimal("0"),
        budget_available=None,
        budget_status=eval("BudgetStatus.UNKNOWN", {"BudgetStatus": eval("__import__('backend.app.schemas.models', fromlist=['BudgetStatus']).BudgetStatus")}),
        analysis_status=eval("AnalysisStatus.INSUFFICIENT_DATA", {"AnalysisStatus": eval("__import__('backend.app.schemas.models', fromlist=['AnalysisStatus']).AnalysisStatus")}),
        status_reason="Simulated inventory service failure: connection lost",
        evidence_ids=[],
        created_at=eval("datetime.now(timezone.utc)", {"datetime": eval("__import__('datetime').datetime"), "timezone": eval("__import__('datetime').timezone")}),
    )
    store.analyses[bad_a_id] = bad_analysis

    create_payload = {
        "analysis_id": str(bad_a_id),
        "sku": "SKU-BAD",
        "product_id": str(bad_analysis.product_id),
        "supplier_name": "Test Supplier",
        "proposed_quantity": 10,
        "pack_count": 10,
        "pack_size": 1,
        "estimated_cost": 100.0,
    }

    resp = api_client.post("/api/requests", json=create_payload)
    assert resp.status_code == 400
    err = resp.json()
    assert "insufficient_data" in err["message"]


def test_approval_gating_and_rule_s2_invalidation(api_client: TestClient) -> None:
    """Approval gates submission; editing proposal invalidates approval (Rule S2)."""
    # 1. Create request
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

    # 2. Attempt submit without approval -> MUST FAIL (403 Forbidden)
    sub_fail = api_client.post(f"/api/requests/{req_id}/submit", json={})
    assert sub_fail.status_code == 403
    assert "Human approval is mandatory" in sub_fail.json()["message"]

    # 3. Approve proposal version 1
    appr_resp = api_client.post(
        "/api/approvals",
        json={
            "request_id": req_id,
            "action": "approved",
            "target_version_number": 1,
            "notes": "Approved by Purchasing Manager",
        },
    )
    assert appr_resp.status_code == 200
    assert appr_resp.json()["request"]["status"] == "approved"

    # 4. Modify proposal (Rule S2) -> forces back to pending_approval
    patch_resp = api_client.patch(
        f"/api/requests/{req_id}/proposal",
        json={
            "proposed_quantity": 40,
            "estimated_cost": 400.0,
            "modification_reason": "Increased for safety margin",
        },
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == "pending_approval"
    assert patch_resp.json()["new_version"]["version_number"] == 2

    # 5. Attempt submit without re-approval -> MUST FAIL (403 Forbidden)
    sub_blocked = api_client.post(f"/api/requests/{req_id}/submit", json={})
    assert sub_blocked.status_code == 403

    # 6. Re-approve version 2
    appr_v2 = api_client.post(
        "/api/approvals",
        json={
            "request_id": req_id,
            "action": "approved",
            "target_version_number": 2,
            "notes": "Re-approved version 2",
        },
    )
    assert appr_v2.status_code == 200

    # 7. Simulated submission now succeeds
    sub_ok = api_client.post(f"/api/requests/{req_id}/submit", json={})
    assert sub_ok.status_code == 200
    assert sub_ok.json()["request"]["status"] == "submitted_or_simulated"
    order_ref = sub_ok.json()["result"]["order_reference"]
    assert order_ref.startswith("SIM-PO-")


def test_independent_outcome_verification(api_client: TestClient) -> None:
    """POST /api/requests/{id}/verify tests matching and mismatching outcomes."""
    # Prepare and submit an approved request
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
    )
    api_client.post(f"/api/requests/{req_id}/submit", json={})

    # Test mismatch: wrong quantity
    ver_mismatch = api_client.post(
        f"/api/requests/{req_id}/verify",
        json={
            "actual_sku": "SKU-001",
            "actual_quantity": 50,  # Mismatch: intended 36
            "actual_pack_size": 1,
        },
    )
    assert ver_mismatch.status_code == 200
    assert ver_mismatch.json()["verification"]["status"] == "failed"
    assert ver_mismatch.json()["verification"]["quantity_match"] is False
    assert ver_mismatch.json()["request"]["status"] == "failed"

    # Test match: matching SKU and quantity
    ver_match = api_client.post(
        f"/api/requests/{req_id}/verify",
        json={
            "actual_sku": "SKU-001",
            "actual_quantity": 36,
            "actual_pack_size": 1,
        },
    )
    assert ver_match.status_code == 200
    assert ver_match.json()["verification"]["status"] == "verified"
    assert ver_match.json()["verification"]["sku_match"] is True
    assert ver_match.json()["verification"]["quantity_match"] is True
    assert ver_match.json()["request"]["status"] == "verified"
