"""
test_decision_engine.py — Deterministic Decision Engine Unit Tests
Phase 3 Implementation

Tests cover:
1. Normal cases (TC1–TC4 scenarios)
2. Zero stock condition
3. Zero shortfall condition (no reorder)
4. Missing values & review states (C10)
5. Pack-size rounding boundary cases (C5)
6. Minimum Order Quantity (MOQ) enforcement
7. Late incoming stock handling (C2)
8. Cancelled / received order exclusions (C2, no double-counting)
9. Budget overruns & status handling (C7)
10. 20% price increase detection & review (C8)
11. Invalid / negative input handling (C9)
12. Evidence ID verification against existing source evidence store (A12 / D2)
13. Structured explanation generation
"""
import sys
import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest

# Ensure project root is in sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.app.schemas.models import (
    AnalysisStatus,
    BudgetStatus,
    OrderStatus,
)
from backend.app.services.calculation_engine import (
    CALCULATION_ENGINE_VERSION,
    calculate_cost,
    check_budget,
    compute_average_daily_demand,
    compute_net_shortfall,
    evaluate_reorder,
    forecast_lead_time_demand,
    round_to_pack_size,
    select_eligible_incoming,
    validate_evidence_ids,
    validate_inputs,
)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Normal Cases & TC1–TC4 Deterministic Scenarios
# ─────────────────────────────────────────────────────────────────────────────


def test_tc1_scenario_low_stock_no_incoming(base_product, base_supplier_terms, base_sales_history):
    """TC1: stock=20, sales=120/30d (4/d), lead_time=14d, unit_price=$10.

    Demand = 56, stock = 20, incoming = 0.
    Shortfall = 36. Pack size = 1 -> order 36 units. Cost = $360.
    Budget = $500 -> OK. Status = ready.
    """
    res = evaluate_reorder(
        product=base_product,
        supplier_terms=base_supplier_terms,
        sales_history=base_sales_history,
        budget_available=Decimal("500.00"),
        source_evidence_ids=["50000000-0000-0000-0000-000000000001"],
        known_source_evidence_ids={"50000000-0000-0000-0000-000000000001"},
    )

    analysis = res.analysis
    assert analysis.average_daily_demand == Decimal("4")
    assert analysis.lead_time_days == 14
    assert analysis.lead_time_demand == Decimal("56")
    assert analysis.usable_available_stock == Decimal("20")
    assert analysis.safety_stock_target == Decimal("0")
    assert analysis.input_snapshot.safety_stock_was_defaulted is True
    assert analysis.eligible_incoming_quantity == Decimal("0")
    assert analysis.net_shortfall == Decimal("36")
    assert analysis.proposed_order_quantity == Decimal("36")
    assert analysis.unit_price == Decimal("10.00")
    assert analysis.estimated_cost == Decimal("360.00")
    assert analysis.budget_status == BudgetStatus.OK
    assert analysis.analysis_status == AnalysisStatus.READY
    assert "### Reorder Analysis Explanation for SKU-001" in res.explanation


def test_tc2_scenario_case_only_supplier(base_product, base_supplier_terms, base_sales_history):
    """TC2: stock=25, pack_size=12, demand=56, incoming=0.

    Shortfall = 56 - 25 = 31.
    Pack size = 12 -> ceil(31/12)*12 = 3 * 12 = 36 units.
    Cost = 36 * $10 = $360. Budget = $500 -> OK. Status = ready.
    """
    prod = dict(base_product, current_stock=Decimal("25"), sku="SKU-002")
    terms = dict(base_supplier_terms, pack_size=12)

    res = evaluate_reorder(
        product=prod,
        supplier_terms=terms,
        sales_history=base_sales_history,
        budget_available=Decimal("500.00"),
    )

    analysis = res.analysis
    assert analysis.net_shortfall == Decimal("31")
    assert analysis.pack_size == 12
    assert analysis.proposed_order_quantity == Decimal("36")
    assert analysis.estimated_cost == Decimal("360.00")
    assert analysis.analysis_status == AnalysisStatus.READY


def test_tc3_scenario_incoming_order_covers_shortfall(base_product, base_supplier_terms, base_sales_history):
    """TC3: stock=20, demand=56, confirmed incoming order = 24 units arriving in 10d (<14d).

    Shortfall = 56 - 20 - 24 = 12 units.
    Proposed = 12 units. Cost = 12 * $10 = $120. Budget = $500 -> OK.
    """
    prod = dict(base_product, sku="SKU-003")
    today = date.today()
    open_orders = [
        {
            "id": "40000000-0000-0000-0000-000000000003",
            "order_reference": "PO-GAMMA-001",
            "ordered_quantity": Decimal("24"),
            "received_quantity": Decimal("0"),
            "expected_arrival_date": today + timedelta(days=10),
            "status": OrderStatus.CONFIRMED,
        }
    ]

    res = evaluate_reorder(
        product=prod,
        supplier_terms=base_supplier_terms,
        sales_history=base_sales_history,
        open_orders=open_orders,
        budget_available=Decimal("500.00"),
        as_of_date=today,
    )

    analysis = res.analysis
    assert analysis.eligible_incoming_quantity == Decimal("24")
    assert analysis.net_shortfall == Decimal("12")
    assert analysis.proposed_order_quantity == Decimal("12")
    assert analysis.estimated_cost == Decimal("120.00")
    assert analysis.analysis_status == AnalysisStatus.READY


def test_tc4_scenario_price_hike_and_budget_review(base_product, base_supplier_terms, base_sales_history):
    """TC4: price increases 20% ($10 -> $12). Shortfall = 36.

    New cost = 36 * $12 = $432.
    Budget available = $400.
    Cost exceeds budget ($432 > $400) -> OVER_BUDGET -> NEEDS_REVIEW.
    Price hike is flagged.
    """
    prod = dict(base_product, sku="SKU-004")
    terms = dict(base_supplier_terms, unit_price=Decimal("12.00"))

    res = evaluate_reorder(
        product=prod,
        supplier_terms=terms,
        sales_history=base_sales_history,
        budget_available=Decimal("400.00"),
        baseline_unit_price=Decimal("10.00"),
    )

    analysis = res.analysis
    assert analysis.proposed_order_quantity == Decimal("36")
    assert analysis.unit_price == Decimal("12.00")
    assert analysis.estimated_cost == Decimal("432.00")
    assert analysis.budget_status == BudgetStatus.OVER_BUDGET
    assert analysis.analysis_status == AnalysisStatus.NEEDS_REVIEW
    assert res.price_hike_detected is True
    assert res.price_change_pct == Decimal("0.20")
    assert "exceeds available budget" in analysis.status_reason


# ─────────────────────────────────────────────────────────────────────────────
# 2. Zero Stock Condition
# ─────────────────────────────────────────────────────────────────────────────


def test_zero_stock_condition(base_product, base_supplier_terms, base_sales_history):
    """When stock is 0 and safety stock is 10, requirement is demand + safety stock."""
    prod = dict(base_product, current_stock=Decimal("0"), safety_stock_target=Decimal("10"))
    res = evaluate_reorder(
        product=prod,
        supplier_terms=base_supplier_terms,
        sales_history=base_sales_history,
        budget_available=Decimal("1000.00"),
    )

    # demand = 56, safety = 10, stock = 0, incoming = 0 -> shortfall = 66
    assert res.analysis.net_shortfall == Decimal("66")
    assert res.analysis.proposed_order_quantity == Decimal("66")
    assert res.analysis.safety_stock_target == Decimal("10")
    assert res.analysis.input_snapshot.safety_stock_was_defaulted is False


# ─────────────────────────────────────────────────────────────────────────────
# 3. Zero Shortfall Condition (No Reorder)
# ─────────────────────────────────────────────────────────────────────────────


def test_zero_shortfall_condition(base_product, base_supplier_terms, base_sales_history):
    """When available stock (100) exceeds demand (56), shortfall is 0 and proposed is 0."""
    prod = dict(base_product, current_stock=Decimal("100"))
    res = evaluate_reorder(
        product=prod,
        supplier_terms=base_supplier_terms,
        sales_history=base_sales_history,
        budget_available=Decimal("500.00"),
    )

    analysis = res.analysis
    assert analysis.net_shortfall == Decimal("0")
    assert analysis.proposed_order_quantity == Decimal("0")
    assert analysis.estimated_cost == Decimal("0")
    assert analysis.analysis_status == AnalysisStatus.READY
    assert "No reorder needed" in analysis.status_reason


# ─────────────────────────────────────────────────────────────────────────────
# 4. Pack-Size Rounding Boundary Cases (C5)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "shortfall,pack_size,expected_units,expected_packs",
    [
        (Decimal("0"), 12, Decimal("0"), 0),
        (Decimal("1"), 12, Decimal("12"), 1),
        (Decimal("11"), 12, Decimal("12"), 1),
        (Decimal("12"), 12, Decimal("12"), 1),
        (Decimal("13"), 12, Decimal("24"), 2),
        (Decimal("24"), 12, Decimal("24"), 2),
        (Decimal("25"), 12, Decimal("36"), 3),
        (Decimal("31"), 12, Decimal("36"), 3),
        (Decimal("10"), 1, Decimal("10"), 10),
        (Decimal("7.5"), 1, Decimal("8"), 8),
    ],
)
def test_pack_size_rounding(shortfall, pack_size, expected_units, expected_packs):
    units, packs = round_to_pack_size(shortfall, pack_size)
    assert units == expected_units
    assert packs == expected_packs


# ─────────────────────────────────────────────────────────────────────────────
# 5. Minimum Order Quantity (MOQ) Enforcement
# ─────────────────────────────────────────────────────────────────────────────


def test_moq_enforcement_single_pack():
    """Shortfall is 5, MOQ is 20, pack_size is 1 -> proposed is 20."""
    units, packs = round_to_pack_size(net_shortfall=Decimal("5"), pack_size=1, moq=20)
    assert units == Decimal("20")
    assert packs == 20


def test_moq_enforcement_with_cases():
    """Shortfall is 5, MOQ is 20, pack_size is 6 -> proposed is 24 (4 cases of 6)."""
    units, packs = round_to_pack_size(net_shortfall=Decimal("5"), pack_size=6, moq=20)
    assert units == Decimal("24")
    assert packs == 4


def test_moq_not_exceeding_higher_shortfall():
    """Shortfall is 35, MOQ is 20, pack_size is 10 -> proposed is 40 (4 cases of 10)."""
    units, packs = round_to_pack_size(net_shortfall=Decimal("35"), pack_size=10, moq=20)
    assert units == Decimal("40")
    assert packs == 4


# ─────────────────────────────────────────────────────────────────────────────
# 6. Incoming Stock: Late, Cancelled, and Received Orders (C2)
# ─────────────────────────────────────────────────────────────────────────────


def test_late_incoming_order_excluded():
    """An open order expected after the lead-time window is not eligible."""
    today = date.today()
    lead_time_days = 14
    orders = [
        {
            "id": "po-1",
            "order_reference": "PO-LATE",
            "ordered_quantity": Decimal("50"),
            "received_quantity": Decimal("0"),
            "expected_arrival_date": today + timedelta(days=20),  # 20 > 14
            "status": OrderStatus.OPEN,
        }
    ]

    eligible_qty, eligible_ids, breakdown = select_eligible_incoming(
        open_orders=orders,
        lead_time_days=lead_time_days,
        as_of_date=today,
    )
    assert eligible_qty == Decimal("0")
    assert len(eligible_ids) == 0
    assert breakdown[0]["eligible"] is False
    assert "after lead-time cutoff" in breakdown[0]["reason"]


def test_cancelled_and_received_orders_excluded():
    """Cancelled and received orders must be excluded from eligible incoming stock."""
    today = date.today()
    orders = [
        {
            "id": "po-cancelled",
            "order_reference": "PO-CANCEL",
            "ordered_quantity": Decimal("30"),
            "received_quantity": Decimal("0"),
            "expected_arrival_date": today + timedelta(days=5),
            "status": OrderStatus.CANCELLED,
        },
        {
            "id": "po-received",
            "order_reference": "PO-REC",
            "ordered_quantity": Decimal("30"),
            "received_quantity": Decimal("30"),
            "expected_arrival_date": today + timedelta(days=5),
            "status": OrderStatus.RECEIVED,
        },
    ]

    eligible_qty, eligible_ids, breakdown = select_eligible_incoming(
        open_orders=orders,
        lead_time_days=14,
        as_of_date=today,
    )
    assert eligible_qty == Decimal("0")
    assert len(eligible_ids) == 0
    assert any("cancelled" in b["reason"].lower() for b in breakdown)
    assert any("already received" in b["reason"].lower() for b in breakdown)


def test_partially_received_order_only_counts_remaining():
    """Partially received order counts only the remaining (ordered - received) balance."""
    today = date.today()
    orders = [
        {
            "id": "po-partial",
            "order_reference": "PO-PARTIAL",
            "ordered_quantity": Decimal("50"),
            "received_quantity": Decimal("20"),  # 30 remaining
            "expected_arrival_date": today + timedelta(days=7),
            "status": OrderStatus.PARTIALLY_RECEIVED,
        }
    ]

    eligible_qty, eligible_ids, breakdown = select_eligible_incoming(
        open_orders=orders,
        lead_time_days=14,
        as_of_date=today,
    )
    assert eligible_qty == Decimal("30")
    assert eligible_ids == ["po-partial"]
    assert breakdown[0]["eligible"] is True


# ─────────────────────────────────────────────────────────────────────────────
# 7. Budget Overruns & Price Hike Rules (C7, C8)
# ─────────────────────────────────────────────────────────────────────────────


def test_budget_within_limit():
    status, reason, hike, _ = check_budget(estimated_cost=Decimal("150.00"), budget_available=Decimal("200.00"))
    assert status == BudgetStatus.OK
    assert hike is False
    assert "within available budget" in reason


def test_budget_overrun():
    status, reason, hike, _ = check_budget(estimated_cost=Decimal("250.00"), budget_available=Decimal("200.00"))
    assert status == BudgetStatus.OVER_BUDGET
    assert hike is False
    assert "exceeds available budget" in reason


def test_budget_unknown_when_unspecified():
    status, reason, hike, _ = check_budget(estimated_cost=Decimal("150.00"), budget_available=None)
    assert status == BudgetStatus.UNKNOWN
    assert "Budget not specified" in reason


def test_price_increase_20_percent_triggers_review():
    """Price increase of 25% ($8 to $10) triggers price_hike_detected."""
    status, reason, hike, pct = check_budget(
        estimated_cost=Decimal("100.00"),
        budget_available=Decimal("500.00"),
        baseline_unit_price=Decimal("8.00"),
        current_unit_price=Decimal("10.00"),
    )
    assert hike is True
    assert pct == Decimal("0.25")
    assert "increased by 25.0%" in reason


# ─────────────────────────────────────────────────────────────────────────────
# 8. Missing Values & Review States (C10)
# ─────────────────────────────────────────────────────────────────────────────


def test_missing_product_fails():
    is_valid, errors = validate_inputs(product=None, supplier_terms={"lead_time_days": 14, "unit_price": 10})
    assert is_valid is False
    assert "Product data is required" in errors[0]


def test_missing_lead_time_fails(base_product):
    terms = {"supplier_name": "Acme", "unit_price": Decimal("10.00")}  # missing lead_time_days
    is_valid, errors = validate_inputs(product=base_product, supplier_terms=terms, average_daily_demand=Decimal("4"))
    assert is_valid is False
    assert any("lead_time_days" in e for e in errors)


def test_missing_unit_price_fails(base_product):
    terms = {"supplier_name": "Acme", "lead_time_days": 14}  # missing unit_price
    is_valid, errors = validate_inputs(product=base_product, supplier_terms=terms, average_daily_demand=Decimal("4"))
    assert is_valid is False
    assert any("unit_price" in e for e in errors)


def test_missing_demand_data_fails(base_product, base_supplier_terms):
    is_valid, errors = validate_inputs(product=base_product, supplier_terms=base_supplier_terms)
    assert is_valid is False
    assert any("Demand data is missing" in e for e in errors)


def test_evaluate_reorder_returns_insufficient_data_on_missing_inputs(base_product):
    """When required inputs are missing, evaluate_reorder returns AnalysisStatus.INSUFFICIENT_DATA."""
    res = evaluate_reorder(product=base_product, supplier_terms=None)
    assert res.analysis.analysis_status == AnalysisStatus.INSUFFICIENT_DATA
    assert "Supplier terms are required" in res.analysis.status_reason


# ─────────────────────────────────────────────────────────────────────────────
# 9. Invalid & Negative Inputs (C9)
# ─────────────────────────────────────────────────────────────────────────────


def test_negative_stock_rejected(base_product, base_supplier_terms):
    bad_prod = dict(base_product, current_stock=Decimal("-5"))
    is_valid, errors = validate_inputs(
        product=bad_prod,
        supplier_terms=base_supplier_terms,
        average_daily_demand=Decimal("4"),
    )
    assert is_valid is False
    assert any("Current stock cannot be negative" in e for e in errors)


def test_negative_price_rejected(base_product, base_supplier_terms):
    bad_terms = dict(base_supplier_terms, unit_price=Decimal("-10.00"))
    is_valid, errors = validate_inputs(
        product=base_product,
        supplier_terms=bad_terms,
        average_daily_demand=Decimal("4"),
    )
    assert is_valid is False
    assert any("unit_price must be > 0" in e for e in errors)


def test_zero_or_negative_lead_time_rejected(base_product, base_supplier_terms):
    bad_terms = dict(base_supplier_terms, lead_time_days=0)
    is_valid, errors = validate_inputs(
        product=base_product,
        supplier_terms=bad_terms,
        average_daily_demand=Decimal("4"),
    )
    assert is_valid is False
    assert any("lead_time_days must be > 0" in e for e in errors)


def test_negative_sales_history_rejected(base_product, base_supplier_terms):
    bad_sales = {"total_units_sold": Decimal("-10"), "days_in_period": 30}
    is_valid, errors = validate_inputs(
        product=base_product,
        supplier_terms=base_supplier_terms,
        sales_history=bad_sales,
    )
    assert is_valid is False
    assert any("cannot be negative" in e for e in errors)


def test_zero_days_in_sales_period_rejected(base_product, base_supplier_terms):
    bad_sales = {"total_units_sold": Decimal("100"), "days_in_period": 0}
    is_valid, errors = validate_inputs(
        product=base_product,
        supplier_terms=base_supplier_terms,
        sales_history=bad_sales,
    )
    assert is_valid is False
    assert any("days_in_period must be > 0" in e for e in errors)


# ─────────────────────────────────────────────────────────────────────────────
# 10. Evidence ID Validation Against Known Store (A12 / D2)
# ─────────────────────────────────────────────────────────────────────────────


def test_valid_evidence_ids_pass():
    known = {"50000000-0000-0000-0000-000000000001", "50000000-0000-0000-0000-000000000002"}
    is_valid, errors = validate_evidence_ids(
        evidence_ids=["50000000-0000-0000-0000-000000000001"],
        known_source_evidence_ids=known,
    )
    assert is_valid is True
    assert len(errors) == 0


def test_orphaned_evidence_id_fails_per_a12():
    """A12: An orphaned/invalid evidence ID must fail validation."""
    known = {"50000000-0000-0000-0000-000000000001"}
    is_valid, errors = validate_evidence_ids(
        evidence_ids=["99999999-9999-9999-9999-999999999999"],
        known_source_evidence_ids=known,
    )
    assert is_valid is False
    assert "99999999-9999-9999-9999-999999999999" in errors[0]
    assert "not found in source_evidence store" in errors[0]


def test_evaluate_reorder_marks_insufficient_data_on_orphaned_evidence(base_product, base_supplier_terms, base_sales_history):
    """evaluate_reorder must flag INSUFFICIENT_DATA when evidence ID is orphaned."""
    res = evaluate_reorder(
        product=base_product,
        supplier_terms=base_supplier_terms,
        sales_history=base_sales_history,
        source_evidence_ids=["99999999-9999-9999-9999-999999999999"],
        known_source_evidence_ids={"50000000-0000-0000-0000-000000000001"},
    )
    assert res.analysis.analysis_status == AnalysisStatus.INSUFFICIENT_DATA
    assert "not found in source_evidence store" in res.analysis.status_reason


# ─────────────────────────────────────────────────────────────────────────────
# 11. Structured Explanation Contents
# ─────────────────────────────────────────────────────────────────────────────


def test_structured_explanation_contains_all_sections(base_product, base_supplier_terms, base_sales_history):
    res = evaluate_reorder(
        product=base_product,
        supplier_terms=base_supplier_terms,
        sales_history=base_sales_history,
        budget_available=Decimal("500.00"),
    )
    exp = res.explanation
    assert "### Reorder Analysis Explanation for SKU-001" in exp
    assert f"- **Calculation Engine Version:** {CALCULATION_ENGINE_VERSION}" in exp
    assert "#### 1. Demand Forecast" in exp
    assert "#### 2. Stock and Incoming Orders" in exp
    assert "#### 3. Net Shortfall Calculation" in exp
    assert "#### 4. Packaging and Proposed Order" in exp
    assert "#### 5. Cost and Budget Review" in exp
    assert "#### 6. Final Status: `ready`" in exp
