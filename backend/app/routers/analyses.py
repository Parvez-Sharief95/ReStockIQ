"""
analyses.py — Reorder Analysis Endpoints
Phase 8 Implementation
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID
import uuid

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from backend.app.schemas.models import (
    AnalysisStatus,
    BudgetStatus,
    ReorderAnalysisRead,
)
from backend.app.services.agent_orchestrator import make_json_safe
from backend.app.services.backend_store import get_backend_store
from backend.app.services.calculation_engine import (
    CALCULATION_ENGINE_VERSION,
    build_structured_explanation,
    evaluate_reorder,
)
from backend.app.services.source_adapter import (
    RetrievalStatus,
    retrieve_reorder_context,
)

router = APIRouter()


class EvaluateAnalysisRequest(BaseModel):
    sku: str = Field(..., description="SKU identifier to evaluate")
    budget_available: Decimal | float | None = Field(None, ge=0)
    baseline_unit_price: Decimal | float | None = Field(None, ge=0)
    safety_stock_target: Decimal | float | None = Field(None, ge=0)


@router.post("/evaluate", summary="Run deterministic reorder evaluation for SKU")
async def evaluate_sku_analysis(req: EvaluateAnalysisRequest) -> dict[str, Any]:
    """Execute complete deterministic reorder decision evaluation for a SKU."""
    store = get_backend_store()
    sku_clean = req.sku.strip().upper()

    # 1. Source retrieval with evidence capture
    ctx = retrieve_reorder_context(sku=sku_clean, adapter=store.adapter)

    # 2. Safety guard: Do not invent missing or failed data
    if not ctx.is_valid and ctx.status == RetrievalStatus.FAILED:
        # Source retrieval explicitly failed
        status_reason = f"Source retrieval failed: {'; '.join(ctx.issues)}"
    else:
        status_reason = None

    # 3. Deterministic calculation engine
    today = date.today()
    now = datetime.now(timezone.utc)

    # If safety stock was provided in request, override product's target
    prod_data = dict(ctx.product_data) if ctx.product_data else None
    if prod_data and req.safety_stock_target is not None:
        prod_data["safety_stock_target"] = Decimal(str(req.safety_stock_target))

    res = evaluate_reorder(
        product=prod_data,
        supplier_terms=ctx.supplier_terms_data,
        sales_history=ctx.sales_history_data,
        open_orders=ctx.open_orders_data or [],
        budget_available=req.budget_available,
        baseline_unit_price=req.baseline_unit_price,
        source_evidence_ids=ctx.evidence_ids,
        known_source_evidence_ids=set(store.adapter.evidence_store.keys()),
        as_of_date=today,
        snapshot_at=now,
    )

    analysis_id = uuid.uuid4()
    analysis_read = ReorderAnalysisRead(
        id=analysis_id,
        product_id=res.analysis.product_id,
        calculation_version=res.analysis.calculation_version,
        input_snapshot=res.analysis.input_snapshot,
        average_daily_demand=res.analysis.average_daily_demand,
        lead_time_days=res.analysis.lead_time_days,
        lead_time_demand=res.analysis.lead_time_demand,
        safety_stock_target=res.analysis.safety_stock_target,
        usable_available_stock=res.analysis.usable_available_stock,
        eligible_incoming_quantity=res.analysis.eligible_incoming_quantity,
        net_shortfall=res.analysis.net_shortfall,
        pack_size=res.analysis.pack_size,
        proposed_order_quantity=res.analysis.proposed_order_quantity,
        unit_price=res.analysis.unit_price,
        estimated_cost=res.analysis.estimated_cost,
        budget_available=res.analysis.budget_available,
        budget_status=res.analysis.budget_status,
        analysis_status=res.analysis.analysis_status,
        status_reason=res.analysis.status_reason or status_reason,
        evidence_ids=res.analysis.evidence_ids,
        created_at=now,
    )

    store.analyses[analysis_id] = analysis_read

    return make_json_safe({
        "analysis": analysis_read,
        "explanation": res.explanation,
        "order_breakdown": res.order_breakdown,
        "price_hike_detected": res.price_hike_detected,
        "price_change_pct": res.price_change_pct,
        "evidence_ids": ctx.evidence_ids,
        "is_synthetic": True,
        "source_type": "mock_source",
    })


@router.get("/evaluate/{sku}", summary="Quick GET evaluation for SKU")
async def evaluate_sku_get(
    sku: str,
    budget: float | None = Query(None, description="Available budget"),
) -> dict[str, Any]:
    """Convenience endpoint to evaluate reorder for SKU via GET."""
    req = EvaluateAnalysisRequest(
        sku=sku,
        budget_available=budget,
    )
    return await evaluate_sku_analysis(req)


@router.get("", summary="List recent reorder analyses")
async def list_analyses() -> dict[str, Any]:
    """Retrieve all stored reorder analyses."""
    store = get_backend_store()
    items = list(store.analyses.values())
    return make_json_safe({
        "items": items,
        "total": len(items),
        "source_type": "mock_source",
    })


@router.get("/{analysis_id}", summary="Get analysis details by ID")
async def get_analysis_by_id(analysis_id: str) -> dict[str, Any]:
    """Retrieve a single reorder analysis by UUID."""
    store = get_backend_store()
    try:
        a_id = UUID(analysis_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid UUID format: '{analysis_id}'",
        )

    if a_id not in store.analyses:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis '{analysis_id}' not found.",
        )

    analysis = store.analyses[a_id]
    return make_json_safe({
        "analysis": analysis,
        "source_type": "mock_source",
    })
