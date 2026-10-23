"""
test_runs.py — Official Acceptance Scenario Runner Endpoints (TC1–TC4)
Phase 8 Implementation
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any
import uuid

from fastapi import APIRouter, HTTPException, status

from backend.app.schemas.models import (
    AnalysisStatus,
    ApprovalAction,
    BudgetStatus,
    TestCaseId,
    TestRunRead,
    TestStatus,
)
from backend.app.services.agent_orchestrator import make_json_safe
from backend.app.services.backend_store import get_backend_store
from backend.app.services.calculation_engine import (
    CALCULATION_ENGINE_VERSION,
    evaluate_reorder,
)
from backend.app.services.source_adapter import (
    retrieve_reorder_context,
)

router = APIRouter()


def execute_scenario(case_id: str) -> TestRunRead:
    """Execute official test case through the end-to-end backend workflow."""
    store = get_backend_store()
    c_id = case_id.strip().upper()
    now = datetime.now(timezone.utc)
    today = date.today()

    sku_map = {
        "TC1": "SKU-001",
        "TC2": "SKU-002",
        "TC3": "SKU-003",
        "TC4": "SKU-004",
    }

    if c_id not in sku_map:
        raise ValueError(f"Unknown test case ID '{case_id}'. Must be TC1, TC2, TC3, or TC4.")

    sku = sku_map[c_id]
    budget_map = {
        "TC1": Decimal("500.00"),
        "TC2": Decimal("500.00"),
        "TC3": Decimal("500.00"),
        "TC4": Decimal("400.00"),
    }
    base_price_map = {
        "TC1": Decimal("10.00"),
        "TC2": Decimal("10.00"),
        "TC3": Decimal("10.00"),
        "TC4": Decimal("10.00"),
    }

    # 1. Source retrieval with provenance
    ctx = retrieve_reorder_context(sku=sku, adapter=store.adapter)
    if not ctx.is_valid:
        raise RuntimeError(f"Source context retrieval failed for {sku}: {'; '.join(ctx.issues)}")

    # 2. Pure deterministic calculation
    res = evaluate_reorder(
        product=ctx.product_data,
        supplier_terms=ctx.supplier_terms_data,
        sales_history=ctx.sales_history_data,
        open_orders=ctx.open_orders_data or [],
        budget_available=budget_map[c_id],
        baseline_unit_price=base_price_map[c_id],
        source_evidence_ids=ctx.evidence_ids,
        known_source_evidence_ids=set(store.adapter.evidence_store.keys()),
        as_of_date=today,
        snapshot_at=now,
    )
    analysis = res.analysis

    # 3. Expected results according to official requirements
    expected_results: dict[str, dict[str, Any]] = {
        "TC1": {
            "shortfall": 36,
            "proposed_quantity": 36,
            "pack_size": 1,
            "status": "ready",
            "estimated_cost": 360.0,
            "budget_status": "ok",
        },
        "TC2": {
            "shortfall": 31,
            "proposed_quantity": 36,
            "pack_size": 12,
            "pack_count": 3,
            "status": "ready",
            "estimated_cost": 360.0,
        },
        "TC3": {
            "shortfall": 12,
            "proposed_quantity": 12,
            "eligible_incoming": 24,
            "status": "ready",
            "estimated_cost": 120.0,
        },
        "TC4": {
            "shortfall": 36,
            "proposed_quantity": 36,
            "unit_price": 12.0,
            "estimated_cost": 432.0,
            "budget_status": "over_budget",
            "price_hike_detected": True,
            "status": "needs_review",
        },
    }

    exp = expected_results[c_id]
    passed = False
    evidence_notes: list[str] = [
        f"Calculation Engine Version: {CALCULATION_ENGINE_VERSION}",
        f"Source Evidence Count: {len(ctx.evidence_ids)} records verified",
    ]

    actual_result: dict[str, Any] = {
        "shortfall": int(analysis.net_shortfall),
        "proposed_quantity": int(analysis.proposed_order_quantity),
        "pack_size": analysis.pack_size,
        "status": analysis.analysis_status.value,
        "estimated_cost": float(analysis.estimated_cost),
        "budget_status": analysis.budget_status.value,
        "eligible_incoming": int(analysis.eligible_incoming_quantity),
        "price_hike_detected": res.price_hike_detected,
    }

    # Evaluate scenario specific assertions
    if c_id == "TC1":
        # Low stock, no incoming order -> correct reorder quantity
        req_created = False
        appr_recorded = False
        sub_executed = False
        ver_passed = False

        if (
            actual_result["shortfall"] == 36
            and actual_result["proposed_quantity"] == 36
            and actual_result["pack_size"] == 1
            and actual_result["status"] == "ready"
            and actual_result["estimated_cost"] == 360.0
        ):
            # Test full workflow: request -> approval -> simulated submission -> verification
            req, ver, _ = store.request_service.create_reorder_request(
                user_id="00000000-0000-0000-0000-000000000001",
                analysis_id=str(uuid.uuid4()),
                product_id=str(analysis.product_id),
                sku=sku,
                supplier_name="Acme Supplies",
                proposed_quantity=36,
                pack_count=36,
                pack_size=1,
                estimated_cost=360.0,
            )
            req_created = True

            appr, req = store.request_service.approve_or_reject_request(
                request_id=req.id,
                approver_id="00000000-0000-0000-0000-000000000002",
                action=ApprovalAction.APPROVED,
                target_version_number=1,
            )
            appr_recorded = True

            req, sub_res = store.request_service.submit_request(
                request_id=req.id,
                actor_id="00000000-0000-0000-0000-000000000001",
                simulated=True,
            )
            sub_executed = sub_res.get("success", False)

            verif, req = store.request_service.verify_submission_outcome(
                request_id=req.id,
                actual_sku="SKU-001",
                actual_quantity=36,
                actual_pack_size=1,
            )
            ver_passed = (verif.status.value == "verified")

            passed = req_created and appr_recorded and sub_executed and ver_passed
            evidence_notes.append(
                f"Full lifecycle validated: Request {req.id} created, approved, simulated ({sub_res.get('order_reference')}), verified."
            )

    elif c_id == "TC2":
        # Case of 12 pack rounding
        if (
            actual_result["shortfall"] == 31
            and actual_result["proposed_quantity"] == 36
            and actual_result["pack_size"] == 12
            and actual_result["status"] == "ready"
        ):
            # Test pack compliance in request service
            req, ver, _ = store.request_service.create_reorder_request(
                user_id="00000000-0000-0000-0000-000000000001",
                analysis_id=str(uuid.uuid4()),
                product_id=str(analysis.product_id),
                sku=sku,
                supplier_name="Bulk Co",
                proposed_quantity=36,
                pack_count=3,
                pack_size=12,
                estimated_cost=360.0,
            )
            appr, req = store.request_service.approve_or_reject_request(
                request_id=req.id,
                approver_id="00000000-0000-0000-0000-000000000002",
                action=ApprovalAction.APPROVED,
                target_version_number=1,
            )
            req, sub_res = store.request_service.submit_request(
                request_id=req.id,
                actor_id="00000000-0000-0000-0000-000000000001",
                simulated=True,
            )
            verif, req = store.request_service.verify_submission_outcome(
                request_id=req.id,
                actual_sku="SKU-002",
                actual_quantity=36,
                actual_pack_size=12,
            )
            passed = (verif.pack_size_check and verif.status.value == "verified")
            evidence_notes.append(
                f"Pack rounding validated: Shortfall 31 rounded to 3 cases of 12 (36 units). Outcome verified."
            )

    elif c_id == "TC3":
        # Existing open PO accounted for; avoids duplicate ordering
        if (
            actual_result["shortfall"] == 12
            and actual_result["proposed_quantity"] == 12
            and actual_result["eligible_incoming"] == 24
            and actual_result["status"] == "ready"
        ):
            passed = True
            evidence_notes.append(
                "Eligible incoming stock (24 units from PO-GAMMA-001) successfully accounted for. "
                "Net shortfall reduced from 36 to 12; double-ordering prevented."
            )

    elif c_id == "TC4":
        # 20% price hike requires budget review; cannot bypass approval
        if (
            actual_result["shortfall"] == 36
            and actual_result["proposed_quantity"] == 36
            and actual_result["estimated_cost"] == 432.0
            and actual_result["budget_status"] == "over_budget"
            and actual_result["status"] == "needs_review"
            and res.price_hike_detected
        ):
            passed = True
            evidence_notes.append(
                "20% price increase detected ($10 -> $12). Cost ($432.00) exceeds budget ($400.00). "
                "Status correctly flagged as 'needs_review'; approval cannot be bypassed."
            )

    test_run = TestRunRead(
        id=uuid.uuid4(),
        case_id=TestCaseId(c_id),
        description=f"Automated evaluation of scenario {c_id} against business rules.",
        input={
            "sku": sku,
            "stock": int(analysis.usable_available_stock),
            "lead_time_days": analysis.lead_time_days,
            "budget": float(budget_map[c_id]),
        },
        expected_result=exp,
        actual_result=actual_result,
        status=TestStatus.PASS if passed else TestStatus.FAIL,
        evidence="\n".join(evidence_notes),
        run_at=now,
        created_at=now,
    )

    store.test_runs[test_run.id] = test_run
    return test_run


@router.post("/run/{case_id}", summary="Run official acceptance test scenario (TC1–TC4)")
async def run_scenario_endpoint(case_id: str) -> dict[str, Any]:
    """Execute official scenario run with input, expected, actual, evidence, and pass/fail."""
    try:
        run = execute_scenario(case_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    return make_json_safe({
        "test_run": run,
        "is_synthetic": True,
        "source_type": "mock_source",
    })


@router.post("/run-all", summary="Run all official acceptance scenarios (TC1–TC4)")
async def run_all_scenarios_endpoint() -> dict[str, Any]:
    """Execute all four official acceptance scenarios."""
    results = []
    all_passed = True
    for case_id in ["TC1", "TC2", "TC3", "TC4"]:
        run = execute_scenario(case_id)
        results.append(run)
        if run.status != TestStatus.PASS:
            all_passed = False

    return make_json_safe({
        "total": len(results),
        "passed": sum(1 for r in results if r.status == TestStatus.PASS),
        "failed": sum(1 for r in results if r.status == TestStatus.FAIL),
        "all_passed": all_passed,
        "runs": results,
    })


@router.get("", summary="List past test runs")
async def list_test_runs() -> dict[str, Any]:
    """Retrieve all historical test runs."""
    store = get_backend_store()
    items = list(store.test_runs.values())
    return make_json_safe({
        "items": items,
        "total": len(items),
    })
