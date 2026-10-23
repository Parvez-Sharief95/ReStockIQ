"""
inventory.py — Inventory and Catalog Endpoints
Phase 8 Implementation
"""
from __future__ import annotations

from typing import Any
from fastapi import APIRouter, HTTPException, status

from backend.app.services.agent_orchestrator import make_json_safe
from backend.app.services.backend_store import get_backend_store

router = APIRouter()


@router.get("", summary="Get inventory catalog with stock and supplier terms")
async def list_inventory() -> dict[str, Any]:
    """Retrieve all inventory items, supplier terms, and open order counts."""
    store = get_backend_store()
    products = store.get_products()
    return make_json_safe({
        "items": products,
        "total": len(products),
        "source_type": "mock_source",
        "is_synthetic": True,
        "note": "Synthetic demo data covering TC1–TC4. No live procurement connection.",
    })


@router.get("/{sku}", summary="Get product details, supplier terms, and open orders for SKU")
async def get_sku_details(sku: str) -> dict[str, Any]:
    """Retrieve full inventory details for a specific SKU."""
    store = get_backend_store()
    product = store.get_product(sku)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with SKU '{sku}' not found.",
        )
    return make_json_safe({
        "product": product,
        "source_type": "mock_source",
        "is_synthetic": True,
    })
