"""
test_acceptance_scenarios.py — Official Acceptance Test Scenarios (TC1–TC4)
Phase 8 Implementation

Validates all four official acceptance scenarios end-to-end:
- TC1: Low stock, no incoming order -> correct reorder quantity.
- TC2: Supplier sells in cases of 12 -> correct unit/case conversion and pack rounding.
- TC3: Existing pending/open purchase order -> account for eligible incoming stock and prevent duplicate ordering.
- TC4: Supplier price increases by 20% -> flag budget review when applicable; do not bypass approval.
- Partial open order edge case: Legitimate shortages not suppressed merely because an order exists.
- Acceptance runner API endpoints: POST /api/test-runs/run/{case_id} and POST /api/test-runs/run-all.
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import uuid
import pytest
from fastapi.testclient import TestClient

from backend.app.schemas.models import (
    ApprovalAction,
    OrderStatus,
    RequestStatus,
    TestStatus,
)
from backend.app.services.backend_store import get_backend_store
from backend.app.services.calculation_engine import evaluate_reorder
from backend.app.services.source_adapter import retrieve_reorder_context


def test_tc1_acceptance_end_to_end(api_client: TestClient) -> None:
    """TC1: Low stock with no incoming order -> correct reorder quantity.

    Full lifecycle:
    Source retrieval -> deterministic analysis -> request preparation ->
    human approval -> simulated submission -> outcome verification.
    """
    store = get_backend_store()
    store.reset()

    # 1. Source retrieval & analysis
    eval_resp = api_client.post(
        "/api/analyses/evaluate",
        json={"sku": "SKU-001", "budget_available": 500.0, "baseline_unit_price": 10.0},
    )
    assert eval_resp.status_code == 200
    eval_data = eval_resp.json()
    analysis = eval_data["analysis"]

    # Assert calculations (deterministic arithmetic)
    assert analysis["average_daily_demand"] == 4
    assert analysis["lead_time_days"] == 14
    assert analysis["lead_time_demand"] == 56
    assert analysis["usable_available_stock"] == 20
    assert analysis["eligible_incoming_quantity"] == 0
    assert analysis["net_shortfall"] == 36
    assert analysis["pack_size"] == 1
    assert analysis["proposed_order_quantity"] == 36
    assert analysis["estimated_cost"] == 360.0
    assert analysis["budget_status"] == "ok"
    assert analysis["analysis_status"] == "ready"

    # Assert provenance & synthetic labelling
    assert eval_data["source_type"] == "mock_source"
    assert eval_data["is_synthetic"] is True
    assert len(eval_data["evidence_ids"]) >= 1

    # 2. Request preparation
    req_resp = api_client.post(
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
            "idempotency_key": "IDEM-TC1-FULL-FLOW",
        },
    )
    assert req_resp.status_code == 201
    req = req_resp.json()["request"]
    assert req["status"] == "pending_approval"
    req_id = req["id"]

    # 3. Human approval
    appr_resp = api_client.post(
        "/api/approvals",
        json={
            "request_id": req_id,
            "action": "approved",
            "target_version_number": 1,
            "notes": "TC1 approved by authorized purchaser",
        },
    )
    assert appr_resp.status_code == 200
    assert appr_resp.json()["request"]["status"] == "approved"

    # 4. Simulated order submission
    sub_resp = api_client.post(f"/api/requests/{req_id}/submit", json={})
    assert sub_resp.status_code == 200
    sub_data = sub_resp.json()
    assert sub_data["request"]["status"] == "submitted_or_simulated"
    order_ref = sub_data["result"]["order_reference"]
    assert order_ref.startswith("SIM-PO-")

    # 5. Independent verification
    ver_resp = api_client.post(
        f"/api/requests/{req_id}/verify",
        json={
            "actual_sku": "SKU-001",
            "actual_quantity": 36,
            "actual_pack_size": 1,
        },
    )
    assert ver_resp.status_code == 200
    ver_data = ver_resp.json()
    assert ver_data["verification"]["status"] == "verified"
    assert ver_data["verification"]["sku_match"] is True
    assert ver_data["verification"]["quantity_match"] is True
    assert ver_data["verification"]["pack_size_check"] is True
    assert ver_data["request"]["status"] == "verified"

    # 6. Audit trail completeness
    audit_resp = api_client.get(f"/api/requests/{req_id}/audit")
    assert audit_resp.status_code == 200
    events = [e["event_type"] for e in audit_resp.json()["events"]]
    assert events == ["proposed", "approved", "submitted", "verified"]


def test_tc2_acceptance_case_rounding(api_client: TestClient) -> None:
    """TC2: Supplier sells in cases of 12 -> correct unit/case conversion and pack rounding.

    Shortfall: 31 units (Demand 56 - Stock 25).
    Pack rounding: ceil(31 / 12) = 3 cases = 36 units.
    Cost: 36 * $10.00 = $360.00.
    """
    store = get_backend_store()
    store.reset()

    # 1. Source retrieval & analysis
    eval_resp = api_client.post(
        "/api/analyses/evaluate",
        json={"sku": "SKU-002", "budget_available": 500.0, "baseline_unit_price": 10.0},
    )
    assert eval_resp.status_code == 200
    analysis = eval_resp.json()["analysis"]

    assert analysis["lead_time_demand"] == 56
    assert analysis["usable_available_stock"] == 25
    assert analysis["net_shortfall"] == 31
    assert analysis["pack_size"] == 12
    # Converted to whole cases: 3 cases * 12 = 36 units
    assert analysis["proposed_order_quantity"] == 36
    assert analysis["estimated_cost"] == 360.0
    assert analysis["analysis_status"] == "ready"

    # 2. Prepare request with pack count
    req_resp = api_client.post(
        "/api/requests",
        json={
            "analysis_id": analysis["id"],
            "sku": "SKU-002",
            "product_id": analysis["product_id"],
            "supplier_name": "Bulk Co",
            "proposed_quantity": 36,
            "pack_count": 3,
            "pack_size": 12,
            "estimated_cost": 360.0,
            "idempotency_key": "IDEM-TC2-CASE-ROUNDING",
        },
    )
    assert req_resp.status_code == 201
    req_id = req_resp.json()["request"]["id"]

    # 3. Approve and submit
    api_client.post(
        "/api/approvals",
        json={"request_id": req_id, "action": "approved", "target_version_number": 1},
    )
    sub_resp = api_client.post(f"/api/requests/{req_id}/submit", json={})
    assert sub_resp.status_code == 200

    # 4. Verify outcome checking pack divisibility
    ver_resp = api_client.post(
        f"/api/requests/{req_id}/verify",
        json={
            "actual_sku": "SKU-002",
            "actual_quantity": 36,
            "actual_pack_size": 12,
        },
    )
    assert ver_resp.status_code == 200
    assert ver_resp.json()["verification"]["pack_size_check"] is True
    assert ver_resp.json()["verification"]["status"] == "verified"


def test_tc3_acceptance_open_purchase_order(api_client: TestClient) -> None:
    """TC3: Existing pending/open purchase order -> account for incoming stock and prevent duplicate ordering.

    Demand: 56 units. Stock: 20 units.
    Eligible incoming order: 24 units arriving in 10 days (within 14-day lead-time window).
    Net shortfall: max(0, 56 - 20 - 24) = 12 units.
    Double-ordering prevented: does not propose 36 units.
    """
    store = get_backend_store()
    store.reset()

    eval_resp = api_client.post(
        "/api/analyses/evaluate",
        json={"sku": "SKU-003", "budget_available": 500.0, "baseline_unit_price": 10.0},
    )
    assert eval_resp.status_code == 200
    data = eval_resp.json()
    analysis = data["analysis"]

    assert analysis["lead_time_demand"] == 56
    assert analysis["usable_available_stock"] == 20
    assert analysis["eligible_incoming_quantity"] == 24
    assert analysis["net_shortfall"] == 12
    assert analysis["proposed_order_quantity"] == 12
    assert analysis["estimated_cost"] == 120.0
    assert analysis["analysis_status"] == "ready"

    # Breakdown confirms PO-GAMMA-001 is included
    breakdown = data["order_breakdown"]
    assert len(breakdown) == 1
    assert breakdown[0]["order_reference"] == "PO-GAMMA-001"
    assert breakdown[0]["eligible"] is True

    # Duplicate ordering prevention when demand is fully covered
    # If open PO had 40 units:
    ctx = retrieve_reorder_context("SKU-003", adapter=store.adapter)
    full_cover_orders = [
        {
            "id": "40000000-0000-0000-0000-000000000099",
            "order_reference": "PO-GAMMA-COVER-ALL",
            "ordered_quantity": Decimal("40"),
            "received_quantity": Decimal("0"),
            "expected_arrival_date": date.today() + timedelta(days=5),
            "status": OrderStatus.CONFIRMED,
        }
    ]
    res_covered = evaluate_reorder(
        product=ctx.product_data,
        supplier_terms=ctx.supplier_terms_data,
        sales_history=ctx.sales_history_data,
        open_orders=full_cover_orders,
        budget_available=Decimal("500.00"),
    )
    # Demand 56 - Stock 20 - Incoming 40 = -4 -> Shortfall = 0
    assert res_covered.analysis.net_shortfall == Decimal("0")
    assert res_covered.analysis.proposed_order_quantity == Decimal("0")


def test_tc4_acceptance_price_increase_budget_review(api_client: TestClient) -> None:
    """TC4: Supplier price increases by 20% -> flag budget review; do not bypass approval.

    Price increased from $10.00 to $12.00 (+20%).
    Proposed units: 36.
    Estimated cost: 36 * $12.00 = $432.00.
    Available budget: $400.00.
    Over budget -> status = needs_review.
    Cannot bypass human approval.
    """
    store = get_backend_store()
    store.reset()

    eval_resp = api_client.post(
        "/api/analyses/evaluate",
        json={
            "sku": "SKU-004",
            "budget_available": 400.0,
            "baseline_unit_price": 10.0,
        },
    )
    assert eval_resp.status_code == 200
    data = eval_resp.json()
    analysis = data["analysis"]

    assert analysis["unit_price"] == 12.0
    assert analysis["estimated_cost"] == 432.0
    assert analysis["budget_status"] == "over_budget"
    assert analysis["analysis_status"] == "needs_review"
    assert data["price_hike_detected"] is True

    # Request requires explicit human review and approval
    req_resp = api_client.post(
        "/api/requests",
        json={
            "analysis_id": analysis["id"],
            "sku": "SKU-004",
            "product_id": analysis["product_id"],
            "supplier_name": "Acme Supplies",
            "proposed_quantity": 36,
            "pack_count": 36,
            "pack_size": 1,
            "estimated_cost": 432.0,
            "idempotency_key": "IDEM-TC4-PRICE-HIKE",
        },
    )
    assert req_resp.status_code == 201
    req_id = req_resp.json()["request"]["id"]

    # Submission strictly blocked without explicit approval
    sub_blocked = api_client.post(f"/api/requests/{req_id}/submit", json={})
    assert sub_blocked.status_code == 403

    # Approver explicitly reviews and approves budget overrun
    appr_resp = api_client.post(
        "/api/approvals",
        json={
            "request_id": req_id,
            "action": "approved",
            "target_version_number": 1,
            "notes": "Budget increase of $32.00 authorized due to essential component price rise.",
        },
    )
    assert appr_resp.status_code == 200
    assert appr_resp.json()["request"]["status"] == "approved"

    # Submission now allowed
    sub_resp = api_client.post(f"/api/requests/{req_id}/submit", json={})
    assert sub_resp.status_code == 200
    assert sub_resp.json()["request"]["status"] == "submitted_or_simulated"


def test_partial_open_order_does_not_suppress_shortage(api_client: TestClient) -> None:
    """Requirement 5: Partial open orders must not suppress legitimate shortages.

    Demand: 100 units. Available stock: 20 units.
    Existing open order: 30 units confirmed.
    Net shortfall must be 100 - 20 - 30 = 50 units (NOT 0).
    Shortage must be legitimately proposed.
    """
    from backend.app.services.calculation_engine import evaluate_reorder

    product = {
        "id": "10000000-0000-0000-0000-000000000099",
        "sku": "SKU-PARTIAL",
        "name": "Partial PO Widget",
        "current_stock": Decimal("20"),
    }
    supplier_terms = {
        "id": "20000000-0000-0000-0000-000000000099",
        "product_id": "10000000-0000-0000-0000-000000000099",
        "supplier_name": "Acme",
        "lead_time_days": 10,
        "pack_size": 1,
        "unit_price": Decimal("5.00"),
    }
    open_orders = [
        {
            "id": "40000000-0000-0000-0000-000000000099",
            "order_reference": "PO-PARTIAL-001",
            "ordered_quantity": Decimal("30"),
            "received_quantity": Decimal("0"),
            "expected_arrival_date": date.today() + timedelta(days=5),
            "status": OrderStatus.CONFIRMED,
        }
    ]

    res = evaluate_reorder(
        product=product,
        supplier_terms=supplier_terms,
        average_daily_demand=Decimal("10"),  # 10/d * 10d = 100 lead-time demand
        open_orders=open_orders,
    )

    # Assert that shortage is 100 - 20 - 30 = 50 units
    assert res.analysis.lead_time_demand == Decimal("100")
    assert res.analysis.eligible_incoming_quantity == Decimal("30")
    assert res.analysis.usable_available_stock == Decimal("20")
    assert res.analysis.net_shortfall == Decimal("50")
    assert res.analysis.proposed_order_quantity == Decimal("50")
    # Shortage was NOT suppressed!
    assert res.analysis.proposed_order_quantity > Decimal("0")


def test_test_runs_endpoints(api_client: TestClient) -> None:
    """POST /api/test-runs/run/{case_id} and POST /api/test-runs/run-all execute and pass."""
    # Test individual scenario runner
    for case_id in ["TC1", "TC2", "TC3", "TC4"]:
        resp = api_client.post(f"/api/test-runs/run/{case_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["test_run"]["case_id"] == case_id
        assert data["test_run"]["status"] == "pass"
        assert data["is_synthetic"] is True

    # Test run-all
    resp_all = api_client.post("/api/test-runs/run-all")
    assert resp_all.status_code == 200
    data_all = resp_all.json()
    assert data_all["total"] == 4
    assert data_all["passed"] == 4
    assert data_all["failed"] == 0
    assert data_all["all_passed"] is True
