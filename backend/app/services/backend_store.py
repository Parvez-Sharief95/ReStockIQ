"""
backend_store.py — Shared In-Memory Backend Store & Service Bridge
Phase 8 Implementation

Provides:
- Centralized singleton storage for products, supplier terms, sales history, open orders,
  analyses, requests, versions, approvals, audit events, verifications, and test runs.
- Initialized with deterministic TC1–TC4 data matching supabase/seed.sql.
- Explicitly tags synthetic data with source_type="mock_source" and is_synthetic=True.
- Does NOT claim live Supabase persistence unless verified against a real configured instance.
- Preserves the deterministic Python calculation engine as the sole source of arithmetic.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID
import uuid

from backend.app.config import settings
from backend.app.schemas.models import (
    AnalysisInputSnapshot,
    AnalysisStatus,
    BudgetStatus,
    OpenPurchaseOrderRead,
    OrderStatus,
    ProductRead,
    ReorderAnalysisRead,
    SupplierTermsRead,
    TestCaseId,
    TestRunRead,
    TestStatus,
)
from backend.app.services.calculation_engine import (
    CALCULATION_ENGINE_VERSION,
    evaluate_reorder,
)
from backend.app.services.request_service import RequestService
from backend.app.services.source_adapter import (
    MockSourceAdapter,
    RetrievalStatus,
    retrieve_reorder_context,
)


class BackendStore:
    """In-memory data store and service coordinator for FastAPI backend."""

    def __init__(self):
        self.adapter = MockSourceAdapter()
        self.request_service = RequestService()
        self.analyses: dict[UUID, ReorderAnalysisRead] = {}
        self.test_runs: dict[UUID, TestRunRead] = {}
        self._initialize_seed_data()

    def _initialize_seed_data(self) -> None:
        """Initialize in-memory store with TC1–TC4 synthetic data matching supabase/seed.sql."""
        now = datetime.now(timezone.utc)
        today = date.today()

        # Seed initial analyses for TC1–TC4 so they are immediately queryable
        skus = [
            ("SKU-001", Decimal("500.00"), Decimal("10.00")),
            ("SKU-002", Decimal("500.00"), Decimal("10.00")),
            ("SKU-003", Decimal("500.00"), Decimal("10.00")),
            ("SKU-004", Decimal("400.00"), Decimal("10.00")),
        ]

        for sku, budget, base_price in skus:
            ctx = retrieve_reorder_context(sku=sku, adapter=self.adapter)
            if ctx.is_valid and ctx.product_data and ctx.supplier_terms_data:
                res = evaluate_reorder(
                    product=ctx.product_data,
                    supplier_terms=ctx.supplier_terms_data,
                    sales_history=ctx.sales_history_data,
                    open_orders=ctx.open_orders_data or [],
                    budget_available=budget,
                    baseline_unit_price=base_price,
                    source_evidence_ids=ctx.evidence_ids,
                    known_source_evidence_ids=set(self.adapter.evidence_store.keys()),
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
                    status_reason=res.analysis.status_reason,
                    evidence_ids=res.analysis.evidence_ids,
                    created_at=now,
                )
                self.analyses[analysis_id] = analysis_read

    def reset(self) -> None:
        """Reset store to initial state (for clean test isolation)."""
        self.adapter = MockSourceAdapter()
        self.request_service = RequestService()
        self.analyses.clear()
        self.test_runs.clear()
        self._initialize_seed_data()

    def get_products(self) -> list[dict[str, Any]]:
        """Return list of products with supplier terms and stock metrics."""
        products = []
        for sku in ["SKU-001", "SKU-002", "SKU-003", "SKU-004"]:
            inv_res = self.adapter.fetch_inventory(sku)
            terms_res = self.adapter.fetch_supplier_terms(sku)
            orders_res = self.adapter.fetch_open_orders(sku)
            sales_res = self.adapter.fetch_sales_history(sku)

            if inv_res.data:
                prod = dict(inv_res.data)
                prod["supplier_terms"] = terms_res.data
                prod["open_orders_count"] = len(orders_res.data) if orders_res.data else 0
                prod["sales_history"] = sales_res.data
                prod["source_type"] = "mock_source"
                prod["is_synthetic"] = True
                products.append(prod)
        return products

    def get_product(self, sku: str) -> dict[str, Any] | None:
        """Return single product details by SKU."""
        sku_clean = sku.strip().upper()
        inv_res = self.adapter.fetch_inventory(sku_clean)
        if not inv_res.data:
            return None

        terms_res = self.adapter.fetch_supplier_terms(sku_clean)
        orders_res = self.adapter.fetch_open_orders(sku_clean)
        sales_res = self.adapter.fetch_sales_history(sku_clean)

        prod = dict(inv_res.data)
        prod["supplier_terms"] = terms_res.data
        prod["open_orders"] = orders_res.data or []
        prod["sales_history"] = sales_res.data
        prod["evidence_records"] = [
            inv_res.evidence,
            terms_res.evidence,
            orders_res.evidence,
            sales_res.evidence,
        ]
        prod["source_type"] = "mock_source"
        prod["is_synthetic"] = True
        return prod


# Singleton store instance
store = BackendStore()


def get_backend_store() -> BackendStore:
    return store
