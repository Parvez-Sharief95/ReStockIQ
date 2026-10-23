"""
dashboard.py — Dashboard Summary Metrics Endpoint
Phase 8 Implementation
"""
from __future__ import annotations

from typing import Any
from fastapi import APIRouter

from backend.app.schemas.models import RequestStatus
from backend.app.services.agent_orchestrator import make_json_safe
from backend.app.services.backend_store import get_backend_store

router = APIRouter()


@router.get("", summary="Get dashboard summary metrics")
async def get_dashboard_summary() -> dict[str, Any]:
    """Retrieve operational metrics for dashboard overview."""
    store = get_backend_store()
    products = store.get_products()
    requests = list(store.request_service._requests.values())

    pending_approvals = [r for r in requests if r.status == RequestStatus.PENDING_APPROVAL]
    submitted_orders = [
        r for r in requests if r.status in (RequestStatus.SUBMITTED_OR_SIMULATED, RequestStatus.VERIFIED)
    ]

    # Calculate stockout risks
    stockout_risks = 0
    for p in products:
        stock = p.get("current_stock", 0)
        reorder_point = p.get("reorder_point", 40)
        if stock <= reorder_point:
            stockout_risks += 1

    return make_json_safe({
        "metrics": {
            "total_products": len(products),
            "stockout_risks": stockout_risks,
            "pending_approvals": len(pending_approvals),
            "submitted_orders": len(submitted_orders),
            "total_requests": len(requests),
        },
        "source_type": "mock_source",
        "is_synthetic": True,
        "note": "Metrics generated from synthetic demo catalog (TC1–TC4).",
    })
