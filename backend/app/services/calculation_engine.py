"""
calculation_engine.py — Deterministic Inventory Decision Engine
Phase 3 Implementation

Pure Python calculations for inventory reorder planning.
Strictly deterministic — zero external dependencies, no LLM calls, no live DB calls.
Implements all C1–C10 calculation rules, input validation, evidence ID checks (A12),
pack-size rounding, MOQ handling, budget analysis, and structured explanations.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Sequence
from uuid import UUID

from pydantic import BaseModel, Field

from backend.app.schemas.models import (
    AnalysisInputSnapshot,
    AnalysisStatus,
    BudgetStatus,
    OpenPurchaseOrderBase,
    OpenPurchaseOrderRead,
    OrderStatus,
    ProductBase,
    ProductRead,
    ReorderAnalysisCreate,
    SalesHistoryBase,
    SalesHistoryRead,
    SupplierTermsBase,
    SupplierTermsRead,
)

CALCULATION_ENGINE_VERSION: str = "1.0.0"
PRICE_INCREASE_THRESHOLD_PCT: Decimal = Decimal("0.20")  # 20% price hike triggers review


class ReorderEvaluationResult(BaseModel):
    """Container for analysis output, structured explanation, and audit details."""
    analysis: ReorderAnalysisCreate
    explanation: str
    price_hike_detected: bool = False
    price_change_pct: Decimal = Decimal("0")
    order_breakdown: list[dict[str, Any]] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# C1: Demand Forecasting & Average Daily Demand
# ─────────────────────────────────────────────────────────────────────────────


def compute_average_daily_demand(
    total_units_sold: Decimal | int | float,
    days_in_period: int,
) -> Decimal:
    """Compute average daily demand over an explicitly selected window (C1).

    Args:
        total_units_sold: Total units sold in the period (>= 0).
        days_in_period: Duration of period in days (> 0).

    Returns:
        Average daily demand as Decimal.
    """
    total = Decimal(str(total_units_sold))
    if days_in_period <= 0:
        raise ValueError(f"days_in_period must be > 0, got {days_in_period}")
    if total < Decimal("0"):
        raise ValueError(f"total_units_sold cannot be negative, got {total}")

    return total / Decimal(days_in_period)


def forecast_lead_time_demand(
    average_daily_demand: Decimal | int | float,
    lead_time_days: int,
) -> Decimal:
    """Forecast lead-time demand: average_daily_demand * lead_time_days (C1).

    Args:
        average_daily_demand: Demand rate per day (>= 0).
        lead_time_days: Supplier lead time in calendar days (> 0).

    Returns:
        Lead-time demand as Decimal.
    """
    daily = Decimal(str(average_daily_demand))
    if daily < Decimal("0"):
        raise ValueError(f"average_daily_demand cannot be negative, got {daily}")
    if lead_time_days <= 0:
        raise ValueError(f"lead_time_days must be > 0, got {lead_time_days}")

    return daily * Decimal(lead_time_days)


# ─────────────────────────────────────────────────────────────────────────────
# C2: Eligible Incoming Purchase Orders
# ─────────────────────────────────────────────────────────────────────────────


def select_eligible_incoming(
    open_orders: Sequence[OpenPurchaseOrderBase | OpenPurchaseOrderRead | dict[str, Any]],
    lead_time_days: int,
    as_of_date: date | None = None,
) -> tuple[Decimal, list[str], list[dict[str, Any]]]:
    """Select eligible incoming quantities within the lead-time window (C2).

    Rules:
    - Only confirmed/open/partially_received orders expected to arrive in time.
    - Exclude cancelled orders.
    - Exclude received orders (already counted in on-hand inventory to prevent double-counting).
    - Exclude orders arriving after (as_of_date + lead_time_days).
    - Remaining quantity = max(0, ordered_quantity - received_quantity).

    Returns:
        (total_eligible_qty, eligible_order_ids, order_breakdown)
    """
    if as_of_date is None:
        as_of_date = date.today()

    cutoff_date = as_of_date + timedelta(days=lead_time_days)
    total_eligible = Decimal("0")
    eligible_ids: list[str] = []
    breakdown: list[dict[str, Any]] = []

    for order in open_orders:
        # Handle dict or model
        if isinstance(order, dict):
            order_id = str(order.get("id", order.get("order_reference", "unknown")))
            raw_status = order.get("status", "")
            ord_qty = Decimal(str(order.get("ordered_quantity", 0)))
            rec_qty = Decimal(str(order.get("received_quantity", 0)))
            arr_date = order.get("expected_arrival_date")
            ref = str(order.get("order_reference", ""))
        else:
            order_id = str(getattr(order, "id", order.order_reference))
            raw_status = order.status
            ord_qty = Decimal(str(order.ordered_quantity))
            rec_qty = Decimal(str(order.received_quantity))
            arr_date = order.expected_arrival_date
            ref = order.order_reference

        if hasattr(raw_status, "value"):
            status = str(raw_status.value).lower()
        else:
            val = str(raw_status).strip()
            if "." in val:
                val = val.split(".")[-1]
            status = val.lower()

        if isinstance(arr_date, str):
            arr_date = date.fromisoformat(arr_date)

        remaining_qty = max(Decimal("0"), ord_qty - rec_qty)

        # Check status
        if status in ("cancelled", OrderStatus.CANCELLED.value):
            breakdown.append({
                "order_id": order_id,
                "order_reference": ref,
                "eligible": False,
                "quantity": Decimal("0"),
                "reason": "Order cancelled",
            })
            continue

        if status in ("received", OrderStatus.RECEIVED.value):
            breakdown.append({
                "order_id": order_id,
                "order_reference": ref,
                "eligible": False,
                "quantity": Decimal("0"),
                "reason": "Order already received (included in on-hand stock)",
            })
            continue

        if status not in (
            OrderStatus.OPEN.value,
            OrderStatus.CONFIRMED.value,
            OrderStatus.PARTIALLY_RECEIVED.value,
            "open",
            "confirmed",
            "partially_received",
        ):
            breakdown.append({
                "order_id": order_id,
                "order_reference": ref,
                "eligible": False,
                "quantity": Decimal("0"),
                "reason": f"Status '{status}' not eligible",
            })
            continue

        if remaining_qty <= Decimal("0"):
            breakdown.append({
                "order_id": order_id,
                "order_reference": ref,
                "eligible": False,
                "quantity": Decimal("0"),
                "reason": "Remaining quantity is 0",
            })
            continue

        # Check arrival window
        if arr_date is None or arr_date > cutoff_date:
            breakdown.append({
                "order_id": order_id,
                "order_reference": ref,
                "eligible": False,
                "quantity": Decimal("0"),
                "remaining_quantity": remaining_qty,
                "expected_arrival_date": str(arr_date),
                "cutoff_date": str(cutoff_date),
                "reason": f"Expected arrival {arr_date} is after lead-time cutoff {cutoff_date}",
            })
            continue

        # Order is eligible
        total_eligible += remaining_qty
        eligible_ids.append(order_id)
        breakdown.append({
            "order_id": order_id,
            "order_reference": ref,
            "eligible": True,
            "quantity": remaining_qty,
            "expected_arrival_date": str(arr_date),
            "cutoff_date": str(cutoff_date),
            "reason": f"Eligible: arrives {arr_date} within demand window",
        })

    return total_eligible, eligible_ids, breakdown


# ─────────────────────────────────────────────────────────────────────────────
# C3 & C4: Net Shortfall Calculation & Safety Stock Defaulting
# ─────────────────────────────────────────────────────────────────────────────


def compute_net_shortfall(
    lead_time_demand: Decimal | int | float,
    usable_available_stock: Decimal | int | float,
    eligible_incoming_quantity: Decimal | int | float,
    safety_stock_target: Decimal | int | float | None = None,
) -> tuple[Decimal, Decimal, bool]:
    """Compute net shortfall with safety stock target (C3, C4).

    Formula:
      net_shortfall = max(0, lead_time_demand + safety_stock - stock - incoming)

    If safety_stock_target is None, it defaults to 0 and was_defaulted is set to True (C4).

    Returns:
        (net_shortfall, effective_safety_stock, safety_stock_was_defaulted)
    """
    ltd = Decimal(str(lead_time_demand))
    stock = Decimal(str(usable_available_stock))
    incoming = Decimal(str(eligible_incoming_quantity))

    if safety_stock_target is None:
        eff_safety_stock = Decimal("0")
        was_defaulted = True
    else:
        eff_safety_stock = Decimal(str(safety_stock_target))
        was_defaulted = False

    raw_requirement = ltd + eff_safety_stock - stock - incoming
    net_shortfall = max(Decimal("0"), raw_requirement)

    return net_shortfall, eff_safety_stock, was_defaulted


# ─────────────────────────────────────────────────────────────────────────────
# C5: Pack-Size Rounding & Minimum Order Quantity (MOQ)
# ─────────────────────────────────────────────────────────────────────────────


def round_to_pack_size(
    net_shortfall: Decimal | int | float,
    pack_size: int = 1,
    moq: int | None = None,
) -> tuple[Decimal, int]:
    """Round net shortfall to whole supplier packs and apply MOQ (C5).

    Formula for case-only suppliers:
      order_units = pack_size * ceil(shortfall / pack_size)
    If shortfall <= 0:
      order_units = 0, pack_count = 0.
    If MOQ is set:
      order_units is raised to meet MOQ, rounding up to full pack_size multiples.

    Returns:
        (proposed_order_quantity, pack_count)
    """
    shortfall = Decimal(str(net_shortfall))
    if shortfall <= Decimal("0"):
        return Decimal("0"), 0

    if pack_size < 1:
        raise ValueError(f"pack_size must be >= 1, got {pack_size}")

    if pack_size == 1:
        # Standard unit order
        raw_units = int(math.ceil(float(shortfall)))
        proposed_units = Decimal(raw_units)
        pack_count = raw_units
    else:
        # Case / pack order: pack_size * ceil(shortfall / pack_size)
        packs = int(math.ceil(float(shortfall) / float(pack_size)))
        pack_count = max(1, packs)
        proposed_units = Decimal(pack_count * pack_size)

    # Apply MOQ if configured
    if moq is not None and moq > 0:
        if proposed_units < Decimal(moq):
            if pack_size > 1:
                moq_packs = int(math.ceil(float(moq) / float(pack_size)))
                pack_count = moq_packs
                proposed_units = Decimal(moq_packs * pack_size)
            else:
                proposed_units = Decimal(moq)
                pack_count = moq

    return proposed_units, pack_count


# ─────────────────────────────────────────────────────────────────────────────
# C6: Cost Calculation
# ─────────────────────────────────────────────────────────────────────────────


def calculate_cost(
    proposed_order_quantity: Decimal | int | float,
    unit_price: Decimal | int | float,
) -> Decimal:
    """Calculate estimated cost = proposed_order_quantity * unit_price (C6)."""
    qty = Decimal(str(proposed_order_quantity))
    price = Decimal(str(unit_price))

    if qty < Decimal("0"):
        raise ValueError(f"proposed_order_quantity cannot be negative, got {qty}")
    if price < Decimal("0"):
        raise ValueError(f"unit_price cannot be negative, got {price}")

    cost = qty * price
    return cost.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ─────────────────────────────────────────────────────────────────────────────
# C7 & C8: Budget Check & Price Variance (20% hike)
# ─────────────────────────────────────────────────────────────────────────────


def check_budget(
    estimated_cost: Decimal | int | float,
    budget_available: Decimal | int | float | None,
    baseline_unit_price: Decimal | int | float | None = None,
    current_unit_price: Decimal | int | float | None = None,
) -> tuple[BudgetStatus, str, bool, Decimal]:
    """Check budget availability and detect >= 20% price increases (C7, C8).

    Returns:
        (budget_status, reason, price_hike_detected, price_change_pct)
    """
    cost = Decimal(str(estimated_cost))
    budget = Decimal(str(budget_available)) if budget_available is not None else None

    # Detect price increase (C8)
    price_hike_detected = False
    price_change_pct = Decimal("0")
    price_notes: list[str] = []

    if baseline_unit_price is not None and current_unit_price is not None:
        base_p = Decimal(str(baseline_unit_price))
        curr_p = Decimal(str(current_unit_price))
        if base_p > Decimal("0"):
            price_change_pct = (curr_p - base_p) / base_p
            if price_change_pct >= PRICE_INCREASE_THRESHOLD_PCT:
                price_hike_detected = True
                pct_str = (price_change_pct * 100).quantize(Decimal("0.1"))
                price_notes.append(
                    f"Supplier price increased by {pct_str}% (from {base_p} to {curr_p})."
                )

    # Budget check
    if budget is None:
        status = BudgetStatus.UNKNOWN
        reason = "Budget not specified; manual budget review recommended."
    elif cost > budget:
        status = BudgetStatus.OVER_BUDGET
        reason = f"Estimated cost ({cost}) exceeds available budget ({budget})."
    else:
        status = BudgetStatus.OK
        reason = f"Estimated cost ({cost}) is within available budget ({budget})."

    if price_notes:
        reason = f"{reason} {' '.join(price_notes)}"

    return status, reason, price_hike_detected, price_change_pct


# ─────────────────────────────────────────────────────────────────────────────
# A12 / D2: Evidence ID Validation Against Known Source Store
# ─────────────────────────────────────────────────────────────────────────────


def validate_evidence_ids(
    evidence_ids: Sequence[str | UUID],
    known_source_evidence_ids: set[str | UUID] | Sequence[str | UUID] | None,
) -> tuple[bool, list[str]]:
    """Validate evidence IDs against existing source_evidence records (A12 / D2).

    PostgreSQL UUID[] columns cannot enforce DB-level foreign keys.
    If any referenced ID does not exist in the source evidence store,
    the analysis must be flagged as insufficient_data.

    Returns:
        (is_valid, list_of_error_reasons)
    """
    if not evidence_ids:
        return True, []

    if known_source_evidence_ids is None:
        # If no store is provided for validation, cannot verify
        return True, []

    known_set = {str(eid).lower() for eid in known_source_evidence_ids}
    missing_ids: list[str] = []

    for eid in evidence_ids:
        if str(eid).lower() not in known_set:
            missing_ids.append(str(eid))

    if missing_ids:
        errors = [f"Referenced evidence ID {mid} not found in source_evidence store" for mid in missing_ids]
        return False, errors

    return True, []


# ─────────────────────────────────────────────────────────────────────────────
# C9 & C10: Input Validation
# ─────────────────────────────────────────────────────────────────────────────


def validate_inputs(
    product: ProductBase | ProductRead | dict[str, Any] | None,
    supplier_terms: SupplierTermsBase | SupplierTermsRead | dict[str, Any] | None,
    average_daily_demand: Decimal | int | float | None = None,
    sales_history: SalesHistoryBase | SalesHistoryRead | dict[str, Any] | None = None,
) -> tuple[bool, list[str]]:
    """Validate required inputs, nonnegative quantities, and valid ranges (C9, C10).

    Returns:
        (is_valid, error_reasons)
    """
    errors: list[str] = []

    # 1. Product check
    if product is None:
        errors.append("Product data is required")
        return False, errors

    if isinstance(product, dict):
        sku = product.get("sku")
        current_stock = product.get("current_stock")
        safety_stock = product.get("safety_stock_target")
    else:
        sku = product.sku
        current_stock = product.current_stock
        safety_stock = product.safety_stock_target

    if not sku:
        errors.append("Product SKU is required")
    if current_stock is None:
        errors.append("Current stock is required")
    elif Decimal(str(current_stock)) < Decimal("0"):
        errors.append(f"Current stock cannot be negative (got {current_stock})")

    if safety_stock is not None and Decimal(str(safety_stock)) < Decimal("0"):
        errors.append(f"Safety stock target cannot be negative (got {safety_stock})")

    # 2. Supplier terms check
    if supplier_terms is None:
        errors.append("Supplier terms are required")
        return False, errors

    if isinstance(supplier_terms, dict):
        lead_time = supplier_terms.get("lead_time_days")
        pack_size = supplier_terms.get("pack_size", 1)
        unit_price = supplier_terms.get("unit_price")
        moq = supplier_terms.get("moq")
    else:
        lead_time = supplier_terms.lead_time_days
        pack_size = supplier_terms.pack_size
        unit_price = supplier_terms.unit_price
        moq = supplier_terms.moq

    if lead_time is None:
        errors.append("Supplier lead time (lead_time_days) is required")
    elif int(lead_time) <= 0:
        errors.append(f"lead_time_days must be > 0 (got {lead_time})")

    if pack_size is not None and int(pack_size) < 1:
        errors.append(f"pack_size must be >= 1 (got {pack_size})")

    if unit_price is None:
        errors.append("Supplier unit_price is required")
    elif Decimal(str(unit_price)) <= Decimal("0"):
        errors.append(f"unit_price must be > 0 (got {unit_price})")

    if moq is not None and int(moq) < 1:
        errors.append(f"moq must be >= 1 (got {moq})")

    # 3. Demand check
    if average_daily_demand is not None:
        if Decimal(str(average_daily_demand)) < Decimal("0"):
            errors.append(f"average_daily_demand cannot be negative (got {average_daily_demand})")
    elif sales_history is not None:
        if isinstance(sales_history, dict):
            sold = sales_history.get("total_units_sold")
            days = sales_history.get("days_in_period")
        else:
            sold = sales_history.total_units_sold
            days = sales_history.days_in_period

        if sold is None or days is None:
            errors.append("Sales history must include total_units_sold and days_in_period")
        else:
            if Decimal(str(sold)) < Decimal("0"):
                errors.append(f"Sales history units sold cannot be negative (got {sold})")
            if int(days) <= 0:
                errors.append(f"Sales history days_in_period must be > 0 (got {days})")
    else:
        errors.append("Demand data is missing: either average_daily_demand or sales_history is required")

    return len(errors) == 0, errors


# ─────────────────────────────────────────────────────────────────────────────
# Structured Explanation Generator
# ─────────────────────────────────────────────────────────────────────────────


def build_structured_explanation(
    sku: str,
    average_daily_demand: Decimal,
    lead_time_days: int,
    lead_time_demand: Decimal,
    usable_available_stock: Decimal,
    safety_stock_target: Decimal,
    safety_stock_was_defaulted: bool,
    eligible_incoming_quantity: Decimal,
    net_shortfall: Decimal,
    pack_size: int,
    proposed_order_quantity: Decimal,
    unit_price: Decimal,
    estimated_cost: Decimal,
    budget_available: Decimal | None,
    budget_status: BudgetStatus,
    analysis_status: AnalysisStatus,
    price_hike_detected: bool,
    price_change_pct: Decimal,
    order_breakdown: list[dict[str, Any]],
    status_reason: str | None = None,
) -> str:
    """Format a comprehensive, human-auditable calculation explanation."""
    lines: list[str] = [
        f"### Reorder Analysis Explanation for {sku}",
        f"- **Calculation Engine Version:** {CALCULATION_ENGINE_VERSION}",
        "",
        "#### 1. Demand Forecast",
        f"- Average Daily Demand: `{average_daily_demand}` units/day",
        f"- Supplier Lead Time: `{lead_time_days}` days",
        f"- Lead-Time Demand = {average_daily_demand} × {lead_time_days} = `{lead_time_demand}` units",
        "",
        "#### 2. Stock and Incoming Orders",
        f"- Usable Available Stock: `{usable_available_stock}` units",
    ]

    if safety_stock_was_defaulted:
        lines.append(
            "- Safety Stock Target: `0` units (None configured; defaulted to 0 per system policy)"
        )
    else:
        lines.append(f"- Safety Stock Target: `{safety_stock_target}` units (explicitly configured)")

    lines.append(f"- Eligible Incoming Orders: `{eligible_incoming_quantity}` units")
    if order_breakdown:
        for ob in order_breakdown:
            ref = ob.get("order_reference", "PO")
            status = "Eligible" if ob.get("eligible") else "Excluded"
            lines.append(f"  - [{ref}] {status}: {ob.get('reason')}")
    else:
        lines.append("  - (No open purchase orders found)")

    lines.extend([
        "",
        "#### 3. Net Shortfall Calculation",
        f"- Formula: max(0, {lead_time_demand} (demand) + {safety_stock_target} (safety) - {usable_available_stock} (stock) - {eligible_incoming_quantity} (incoming))",
        f"- Net Shortfall: `{net_shortfall}` units",
        "",
        "#### 4. Packaging and Proposed Order",
        f"- Supplier Pack Size: `{pack_size}` units/pack",
    ])

    if pack_size > 1 and net_shortfall > Decimal("0"):
        packs = int(math.ceil(float(net_shortfall) / float(pack_size)))
        lines.append(
            f"- Pack Rounding: ceil({net_shortfall} / {pack_size}) = {packs} packs → `{proposed_order_quantity}` units"
        )
    elif net_shortfall <= Decimal("0"):
        lines.append("- Net shortfall is zero; no reorder proposed (0 units).")
    else:
        lines.append(f"- Proposed Quantity: `{proposed_order_quantity}` units")

    lines.extend([
        "",
        "#### 5. Cost and Budget Review",
        f"- Unit Price: `${unit_price}`",
        f"- Estimated Cost = {proposed_order_quantity} × ${unit_price} = `${estimated_cost}`",
    ])

    if budget_available is not None:
        lines.append(f"- Budget Available: `${budget_available}`")
        lines.append(f"- Budget Status: `{budget_status.value}`")
    else:
        lines.append("- Budget Available: None specified")

    if price_hike_detected:
        lines.append(
            f"- **Notice:** Significant supplier price increase of `{(price_change_pct * 100):.1f}%` detected. Budget review required."
        )

    lines.extend([
        "",
        f"#### 6. Final Status: `{analysis_status.value}`",
    ])
    if status_reason:
        lines.append(f"- Reason: {status_reason}")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Main Decision Engine Orchestrator
# ─────────────────────────────────────────────────────────────────────────────


def evaluate_reorder(
    product: ProductBase | ProductRead | dict[str, Any] | None,
    supplier_terms: SupplierTermsBase | SupplierTermsRead | dict[str, Any] | None,
    sales_history: SalesHistoryBase | SalesHistoryRead | dict[str, Any] | None = None,
    average_daily_demand: Decimal | int | float | None = None,
    demand_window_days: int = 30,
    open_orders: Sequence[OpenPurchaseOrderBase | OpenPurchaseOrderRead | dict[str, Any]] | None = None,
    budget_available: Decimal | int | float | None = None,
    baseline_unit_price: Decimal | int | float | None = None,
    source_evidence_ids: Sequence[str | UUID] | None = None,
    known_source_evidence_ids: set[str | UUID] | Sequence[str | UUID] | None = None,
    as_of_date: date | None = None,
    snapshot_at: datetime | None = None,
) -> ReorderEvaluationResult:
    """Run complete deterministic reorder decision evaluation (Phase 3).

    Fully compliant with C1–C10, A12 evidence verification, and TC1–TC4 test suites.
    """
    if as_of_date is None:
        as_of_date = date.today()
    if snapshot_at is None:
        snapshot_at = datetime.now(timezone.utc)
    if open_orders is None:
        open_orders = []
    if source_evidence_ids is None:
        source_evidence_ids = []

    # 1. Input validation (C9, C10)
    is_valid, validation_errors = validate_inputs(
        product=product,
        supplier_terms=supplier_terms,
        average_daily_demand=average_daily_demand,
        sales_history=sales_history,
    )

    # 2. Evidence verification (A12 / D2)
    evidence_valid, evidence_errors = validate_evidence_ids(
        evidence_ids=source_evidence_ids,
        known_source_evidence_ids=known_source_evidence_ids,
    )

    # If critical validation fails or evidence is orphaned, return early with INSUFFICIENT_DATA
    if not is_valid or not evidence_valid:
        all_errors = validation_errors + evidence_errors
        reason = "; ".join(all_errors)

        prod_id = "00000000-0000-0000-0000-000000000000"
        sku = "UNKNOWN"
        usable_stock = Decimal("0")
        safety_stock = Decimal("0")
        if product is not None:
            if isinstance(product, dict):
                prod_id = str(product.get("id", prod_id))
                sku = str(product.get("sku", sku))
                usable_stock = Decimal(str(product.get("current_stock", 0) or 0))
            else:
                prod_id = str(getattr(product, "id", prod_id))
                sku = product.sku
                usable_stock = Decimal(str(product.current_stock or 0))

        lead_time = 14
        pack_size = 1
        moq = None
        unit_price = Decimal("10.00")
        currency = "USD"
        terms_id = "00000000-0000-0000-0000-000000000000"
        if supplier_terms is not None:
            if isinstance(supplier_terms, dict):
                lead_time = int(supplier_terms.get("lead_time_days", 14) or 14)
                pack_size = int(supplier_terms.get("pack_size", 1) or 1)
                moq = supplier_terms.get("moq")
                unit_price = Decimal(str(supplier_terms.get("unit_price", 10.00) or 10.00))
                currency = str(supplier_terms.get("currency", "USD"))
                terms_id = str(supplier_terms.get("id", terms_id))
            else:
                lead_time = supplier_terms.lead_time_days or 14
                pack_size = supplier_terms.pack_size or 1
                moq = supplier_terms.moq
                unit_price = Decimal(str(supplier_terms.unit_price or 10.00))
                currency = supplier_terms.currency or "USD"
                terms_id = str(getattr(supplier_terms, "id", terms_id))

        snapshot = AnalysisInputSnapshot(
            product_id=prod_id,
            sku=sku,
            average_daily_demand=Decimal("0"),
            demand_window_days=demand_window_days,
            lead_time_days=lead_time,
            usable_available_stock=usable_stock,
            safety_stock_target=safety_stock,
            safety_stock_was_defaulted=True,
            eligible_incoming_quantity=Decimal("0"),
            incoming_order_ids=[],
            pack_size=pack_size,
            moq=moq,
            unit_price=unit_price,
            currency=currency,
            budget_available=Decimal(str(budget_available)) if budget_available is not None else None,
            supplier_terms_id=terms_id,
            source_evidence_ids=[str(e) for e in source_evidence_ids],
            snapshot_at=snapshot_at,
        )

        analysis = ReorderAnalysisCreate(
            product_id=UUID(prod_id),
            calculation_version=CALCULATION_ENGINE_VERSION,
            input_snapshot=snapshot,
            average_daily_demand=Decimal("0"),
            lead_time_days=lead_time,
            lead_time_demand=Decimal("0"),
            safety_stock_target=Decimal("0"),
            usable_available_stock=usable_stock,
            eligible_incoming_quantity=Decimal("0"),
            net_shortfall=Decimal("0"),
            pack_size=pack_size,
            proposed_order_quantity=Decimal("0"),
            unit_price=unit_price,
            estimated_cost=Decimal("0"),
            budget_available=Decimal(str(budget_available)) if budget_available is not None else None,
            budget_status=BudgetStatus.UNKNOWN,
            analysis_status=AnalysisStatus.INSUFFICIENT_DATA,
            status_reason=reason,
            evidence_ids=[str(e) for e in source_evidence_ids],
        )

        explanation = f"### Reorder Analysis Failed\n- **Status:** `{AnalysisStatus.INSUFFICIENT_DATA.value}`\n- **Reason:** {reason}"
        return ReorderEvaluationResult(
            analysis=analysis,
            explanation=explanation,
            price_hike_detected=False,
            price_change_pct=Decimal("0"),
            order_breakdown=[],
        )

    # 3. Extract core inputs
    if isinstance(product, dict):
        prod_id = str(product.get("id", "00000000-0000-0000-0000-000000000000"))
        sku = str(product.get("sku", "UNKNOWN"))
        usable_stock = Decimal(str(product.get("current_stock", 0)))
        raw_safety_stock = product.get("safety_stock_target")
        currency = str(product.get("currency", "USD"))
    else:
        prod_id = str(getattr(product, "id", "00000000-0000-0000-0000-000000000000"))
        sku = product.sku
        usable_stock = Decimal(str(product.current_stock))
        raw_safety_stock = product.safety_stock_target
        currency = product.currency

    if isinstance(supplier_terms, dict):
        terms_id = str(supplier_terms.get("id", "00000000-0000-0000-0000-000000000000"))
        lead_time = int(supplier_terms.get("lead_time_days"))
        pack_size = int(supplier_terms.get("pack_size", 1))
        unit_price = Decimal(str(supplier_terms.get("unit_price")))
        moq = supplier_terms.get("moq")
    else:
        terms_id = str(getattr(supplier_terms, "id", "00000000-0000-0000-0000-000000000000"))
        lead_time = supplier_terms.lead_time_days
        pack_size = supplier_terms.pack_size
        unit_price = Decimal(str(supplier_terms.unit_price))
        moq = supplier_terms.moq

    # 4. Compute daily demand (C1)
    if average_daily_demand is not None:
        daily_demand = Decimal(str(average_daily_demand))
    else:
        assert sales_history is not None
        if isinstance(sales_history, dict):
            sold = sales_history["total_units_sold"]
            days = sales_history["days_in_period"]
        else:
            sold = sales_history.total_units_sold
            days = sales_history.days_in_period
        daily_demand = compute_average_daily_demand(sold, days)
        demand_window_days = int(days)

    # 5. Forecast lead-time demand (C1)
    ltd = forecast_lead_time_demand(daily_demand, lead_time)

    # 6. Select eligible incoming orders (C2)
    eligible_incoming, incoming_ids, order_breakdown = select_eligible_incoming(
        open_orders=open_orders,
        lead_time_days=lead_time,
        as_of_date=as_of_date,
    )

    # 7. Compute net shortfall & safety stock (C3, C4)
    net_shortfall, eff_safety_stock, was_defaulted = compute_net_shortfall(
        lead_time_demand=ltd,
        usable_available_stock=usable_stock,
        eligible_incoming_quantity=eligible_incoming,
        safety_stock_target=raw_safety_stock,
    )

    # 8. Pack-size rounding & MOQ (C5)
    proposed_order_qty, _ = round_to_pack_size(
        net_shortfall=net_shortfall,
        pack_size=pack_size,
        moq=moq,
    )

    # 9. Cost calculation (C6)
    estimated_cost = calculate_cost(proposed_order_qty, unit_price)

    # 10. Budget and price hike check (C7, C8)
    budget_val = Decimal(str(budget_available)) if budget_available is not None else None
    budget_stat, budget_reason, price_hike_detected, price_change_pct = check_budget(
        estimated_cost=estimated_cost,
        budget_available=budget_val,
        baseline_unit_price=baseline_unit_price,
        current_unit_price=unit_price,
    )

    # 11. Determine Analysis Status
    # C8: For 20% price increase, recalculate cost and request budget review if over budget or policy review
    status_reason: str | None = None
    if budget_stat == BudgetStatus.OVER_BUDGET:
        analysis_status = AnalysisStatus.NEEDS_REVIEW
        status_reason = budget_reason
    elif price_hike_detected:
        analysis_status = AnalysisStatus.NEEDS_REVIEW
        status_reason = f"Budget review requested: {budget_reason}"
    elif proposed_order_qty == Decimal("0"):
        analysis_status = AnalysisStatus.READY
        status_reason = "No reorder needed; current stock and incoming orders cover lead-time demand."
    else:
        analysis_status = AnalysisStatus.READY
        status_reason = None

    # 12. Create Input Snapshot
    snapshot = AnalysisInputSnapshot(
        product_id=prod_id,
        sku=sku,
        average_daily_demand=daily_demand,
        demand_window_days=demand_window_days,
        lead_time_days=lead_time,
        usable_available_stock=usable_stock,
        safety_stock_target=eff_safety_stock,
        safety_stock_was_defaulted=was_defaulted,
        eligible_incoming_quantity=eligible_incoming,
        incoming_order_ids=incoming_ids,
        pack_size=pack_size,
        moq=moq,
        unit_price=unit_price,
        currency=currency,
        budget_available=budget_val,
        supplier_terms_id=terms_id,
        source_evidence_ids=[str(e) for e in source_evidence_ids],
        snapshot_at=snapshot_at,
    )

    # 13. Create ReorderAnalysisCreate
    analysis = ReorderAnalysisCreate(
        product_id=UUID(prod_id),
        calculation_version=CALCULATION_ENGINE_VERSION,
        input_snapshot=snapshot,
        average_daily_demand=daily_demand,
        lead_time_days=lead_time,
        lead_time_demand=ltd,
        safety_stock_target=eff_safety_stock,
        usable_available_stock=usable_stock,
        eligible_incoming_quantity=eligible_incoming,
        net_shortfall=net_shortfall,
        pack_size=pack_size,
        proposed_order_quantity=proposed_order_qty,
        unit_price=unit_price,
        estimated_cost=estimated_cost,
        budget_available=budget_val,
        budget_status=budget_stat,
        analysis_status=analysis_status,
        status_reason=status_reason,
        evidence_ids=[str(e) for e in source_evidence_ids],
    )

    # 14. Structured Explanation
    explanation = build_structured_explanation(
        sku=sku,
        average_daily_demand=daily_demand,
        lead_time_days=lead_time,
        lead_time_demand=ltd,
        usable_available_stock=usable_stock,
        safety_stock_target=eff_safety_stock,
        safety_stock_was_defaulted=was_defaulted,
        eligible_incoming_quantity=eligible_incoming,
        net_shortfall=net_shortfall,
        pack_size=pack_size,
        proposed_order_quantity=proposed_order_qty,
        unit_price=unit_price,
        estimated_cost=estimated_cost,
        budget_available=budget_val,
        budget_status=budget_stat,
        analysis_status=analysis_status,
        price_hike_detected=price_hike_detected,
        price_change_pct=price_change_pct,
        order_breakdown=order_breakdown,
        status_reason=status_reason,
    )

    return ReorderEvaluationResult(
        analysis=analysis,
        explanation=explanation,
        price_hike_detected=price_hike_detected,
        price_change_pct=price_change_pct,
        order_breakdown=order_breakdown,
    )
