"""dashboard.py — Dashboard Summary Metrics Endpoint
Phase 8 & 9 Implementation
"""
from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends

from backend.app.schemas.models import RequestStatus
from backend.app.services.agent_orchestrator import make_json_safe
from backend.app.services.repository import RepositoryManager, get_repository_manager

router = APIRouter()


@router.get("", summary="Get dashboard summary metrics")
async def get_dashboard_summary(
    repo: RepositoryManager = Depends(get_repository_manager),
) -> dict[str, Any]:
    """Retrieve operational metrics for dashboard overview."""
    products = repo.inventory.list_products()
    requests = repo.requests.list_requests()

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
        "source_type": "database" if repo.is_persistent else "mock_source",
        "is_synthetic": not repo.is_persistent,
        "note": "Metrics generated from persistent database." if repo.is_persistent else "Metrics generated from synthetic demo catalog (TC1–TC4).",
    })
