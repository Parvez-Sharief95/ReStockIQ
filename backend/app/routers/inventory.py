"""inventory.py — Inventory and Catalog Endpoints
Phase 8 & 9 Implementation
"""
from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.services.agent_orchestrator import make_json_safe
from backend.app.services.repository import RepositoryManager, get_repository_manager

router = APIRouter()


@router.get("", summary="Get inventory catalog with stock and supplier terms")
async def list_inventory(
    repo: RepositoryManager = Depends(get_repository_manager),
) -> dict[str, Any]:
    """Retrieve all inventory items, supplier terms, and open order counts."""
    products = repo.inventory.list_products()
    return make_json_safe({
        "items": products,
        "total": len(products),
        "source_type": "database" if repo.is_persistent else "mock_source",
        "is_synthetic": not repo.is_persistent,
        "note": "Live inventory from database." if repo.is_persistent else "Synthetic demo data covering TC1–TC4. No live procurement connection.",
    })


@router.get("/{sku}", summary="Get product details, supplier terms, and open orders for SKU")
async def get_sku_details(
    sku: str,
    repo: RepositoryManager = Depends(get_repository_manager),
) -> dict[str, Any]:
    """Retrieve full inventory details for a specific SKU."""
    product = repo.inventory.get_product(sku)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with SKU '{sku}' not found.",
        )
    return make_json_safe({
        "product": product,
        "source_type": "database" if repo.is_persistent else "mock_source",
        "is_synthetic": not repo.is_persistent,
    })
