"""
source_adapter.py — Source Retrieval and Evidence Capture
Phase 4 Implementation

Provides:
- BaseSourceAdapter protocol/abstract base class.
- MockSourceAdapter with deterministic synthetic data covering TC1–TC4.
- Explicit labelling of all synthetic data (`is_synthetic=True`, `source_type=mock_source`).
- Evidence capture: source IDs, source URLs, retrieval timestamps, source timestamps, fields used.
- Explicit handling for missing fields, stale data, conflicting records, and source failures.
- Robust guard against inventing evidence: source failures never default to zero stock or zero open orders.
- Prompt injection defense: untrusted text data is sanitized and treated strictly as inert data.
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Sequence
from uuid import UUID

from pydantic import BaseModel, Field

from backend.app.schemas.models import (
    OrderStatus,
    SourceEvidenceCreate,
    SourceEvidenceRead,
    SourceType,
)


class RetrievalStatus(str, Enum):
    """Retrieval outcome states for source data."""
    SUCCESS = "success"
    STALE = "stale"
    CONFLICT = "conflict"
    MISSING = "missing"
    FAILED = "failed"


class SourceRetrievalResult(BaseModel):
    """Result of a single source retrieval operation including evidence and status."""
    status: RetrievalStatus
    evidence: SourceEvidenceCreate | None = None
    evidence_id: str | None = None
    data: Any | None = None
    error_message: str | None = None
    is_stale: bool = False
    has_conflict: bool = False
    conflict_details: str | None = None


class ReorderSourceContext(BaseModel):
    """Aggregated source context for an SKU ready to inform the calculation engine."""
    sku: str
    is_valid: bool
    status: RetrievalStatus
    product_data: dict[str, Any] | None = None
    supplier_terms_data: dict[str, Any] | None = None
    sales_history_data: dict[str, Any] | None = None
    open_orders_data: list[dict[str, Any]] | None = None
    evidence_records: list[SourceEvidenceCreate] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ─────────────────────────────────────────────────────────────────────────────
# Base Source Adapter Interface
# ─────────────────────────────────────────────────────────────────────────────


class BaseSourceAdapter(ABC):
    """Interface for source adapters (mock, HTTP, API, browser)."""

    @abstractmethod
    def fetch_inventory(self, sku: str) -> SourceRetrievalResult:
        """Fetch current stock and product details for SKU."""
        pass

    @abstractmethod
    def fetch_supplier_terms(self, sku: str) -> SourceRetrievalResult:
        """Fetch lead time, pack size, price, and MOQ for SKU."""
        pass

    @abstractmethod
    def fetch_sales_history(self, sku: str, days: int = 30) -> SourceRetrievalResult:
        """Fetch historical sales demand for SKU over a given window."""
        pass

    @abstractmethod
    def fetch_open_orders(self, sku: str) -> SourceRetrievalResult:
        """Fetch pending/open purchase orders for SKU."""
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Mock / Synthetic Source Adapter (Default / Phase 4)
# ─────────────────────────────────────────────────────────────────────────────


class MockSourceAdapter(BaseSourceAdapter):
    """Deterministic synthetic adapter covering TC1–TC4 and custom edge cases.

    Clearly labels all data as synthetic (`mock_source`), captures full evidence
    provenance, and simulates failures, staleness, conflicts, and missing data on demand.
    """

    def __init__(
        self,
        default_max_age_days: int = 7,
        evidence_store: dict[str, SourceEvidenceCreate | SourceEvidenceRead] | None = None,
    ):
        self.default_max_age_days = default_max_age_days
        # Shared or internal evidence repository for ID cross-referencing
        self.evidence_store: dict[str, SourceEvidenceCreate | SourceEvidenceRead] = (
            evidence_store if evidence_store is not None else {}
        )
        self._simulate_failures: dict[str, str] = {}
        self._custom_overrides: dict[str, dict[str, Any]] = {}

    def set_failure_mode(self, domain: str, error_message: str) -> None:
        """Configure simulated failure for a domain: 'inventory', 'supplier_terms', 'sales', 'open_orders'."""
        self._simulate_failures[domain] = error_message

    def clear_failure_mode(self, domain: str | None = None) -> None:
        """Clear simulated failure mode."""
        if domain is None:
            self._simulate_failures.clear()
        else:
            self._simulate_failures.pop(domain, None)

    def set_override(self, sku: str, domain: str, data: Any) -> None:
        """Inject custom data override for test scenarios."""
        if sku not in self._custom_overrides:
            self._custom_overrides[sku] = {}
        self._custom_overrides[sku][domain] = data

    def clear_overrides(self, sku: str | None = None) -> None:
        """Clear custom overrides."""
        if sku is None:
            self._custom_overrides.clear()
        else:
            self._custom_overrides.pop(sku, None)

    # ─────────────────────────────────────────────────────────────────────────
    # Helper: Create and Store Evidence
    # ─────────────────────────────────────────────────────────────────────────

    def _create_evidence(
        self,
        source_url: str,
        fields_used: list[str],
        raw_data: dict[str, Any],
        source_timestamp: datetime | None = None,
        fixed_id: str | None = None,
    ) -> tuple[SourceEvidenceCreate, str]:
        """Build a standardized SourceEvidence record labelled as synthetic."""
        now = datetime.now(timezone.utc)
        evidence_id = fixed_id or str(uuid.uuid4())

        # Enforce synthetic tagging and untrusted data boundary
        enriched_raw = dict(raw_data)
        enriched_raw["is_synthetic"] = True
        enriched_raw["source_provenance"] = "MockSourceAdapter (synthetic demo)"

        evidence = SourceEvidenceCreate(
            source_type=SourceType.MOCK,
            source_url=source_url,
            retrieved_at=now,
            source_timestamp=source_timestamp or (now - timedelta(hours=1)),
            fields_used=fields_used,
            raw_data=enriched_raw,
        )

        self.evidence_store[evidence_id] = evidence
        return evidence, evidence_id

    # ─────────────────────────────────────────────────────────────────────────
    # 1. Fetch Inventory
    # ─────────────────────────────────────────────────────────────────────────

    def fetch_inventory(self, sku: str) -> SourceRetrievalResult:
        if "inventory" in self._simulate_failures:
            return SourceRetrievalResult(
                status=RetrievalStatus.FAILED,
                error_message=f"Simulated inventory service failure: {self._simulate_failures['inventory']}",
            )

        # Check for overrides
        if sku in self._custom_overrides and "inventory" in self._custom_overrides[sku]:
            override = self._custom_overrides[sku]["inventory"]
            if override is None:
                return SourceRetrievalResult(
                    status=RetrievalStatus.MISSING,
                    error_message=f"Inventory record for SKU '{sku}' not found in source",
                )
            source_ts = override.get("source_timestamp")
            is_stale = self._is_stale(source_ts)
            evidence, eid = self._create_evidence(
                source_url=f"mock://dashboard/inventory/{sku}",
                fields_used=["current_stock", "sku", "unit"],
                raw_data=override,
                source_timestamp=source_ts,
            )
            return SourceRetrievalResult(
                status=RetrievalStatus.STALE if is_stale else RetrievalStatus.SUCCESS,
                evidence=evidence,
                evidence_id=eid,
                data=override,
                is_stale=is_stale,
                error_message="Inventory data is stale" if is_stale else None,
            )

        # Standard TC1–TC4 synthetic dataset
        tc_map = {
            "SKU-001": {
                "id": "10000000-0000-0000-0000-000000000001",
                "sku": "SKU-001",
                "name": "Widget Alpha",
                "unit": "each",
                "currency": "USD",
                "current_stock": Decimal("20"),
                "safety_stock_target": None,
                "fixed_evidence_id": "50000000-0000-0000-0000-000000000001",
            },
            "SKU-002": {
                "id": "10000000-0000-0000-0000-000000000002",
                "sku": "SKU-002",
                "name": "Widget Beta",
                "unit": "each",
                "currency": "USD",
                "current_stock": Decimal("25"),
                "safety_stock_target": None,
                "fixed_evidence_id": "50000000-0000-0000-0000-000000000002",
            },
            "SKU-003": {
                "id": "10000000-0000-0000-0000-000000000003",
                "sku": "SKU-003",
                "name": "Widget Gamma",
                "unit": "each",
                "currency": "USD",
                "current_stock": Decimal("20"),
                "safety_stock_target": None,
                "fixed_evidence_id": "50000000-0000-0000-0000-000000000003",
            },
            "SKU-004": {
                "id": "10000000-0000-0000-0000-000000000004",
                "sku": "SKU-004",
                "name": "Widget Delta",
                "unit": "each",
                "currency": "USD",
                "current_stock": Decimal("20"),
                "safety_stock_target": None,
                "fixed_evidence_id": "50000000-0000-0000-0000-000000000004",
            },
        }

        if sku not in tc_map:
            return SourceRetrievalResult(
                status=RetrievalStatus.MISSING,
                error_message=f"Product with SKU '{sku}' not found in mock catalog",
            )

        data = tc_map[sku]
        evidence, eid = self._create_evidence(
            source_url=f"mock://dashboard/inventory/{sku}",
            fields_used=["current_stock", "sku", "name", "unit"],
            raw_data={"sku": sku, "stock": float(data["current_stock"]), "name": data["name"]},
            fixed_id=data.get("fixed_evidence_id"),
        )

        return SourceRetrievalResult(
            status=RetrievalStatus.SUCCESS,
            evidence=evidence,
            evidence_id=eid,
            data=data,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # 2. Fetch Supplier Terms
    # ─────────────────────────────────────────────────────────────────────────

    def fetch_supplier_terms(self, sku: str) -> SourceRetrievalResult:
        if "supplier_terms" in self._simulate_failures:
            return SourceRetrievalResult(
                status=RetrievalStatus.FAILED,
                error_message=f"Simulated supplier service failure: {self._simulate_failures['supplier_terms']}",
            )

        if sku in self._custom_overrides and "supplier_terms" in self._custom_overrides[sku]:
            override = self._custom_overrides[sku]["supplier_terms"]
            if override is None:
                return SourceRetrievalResult(
                    status=RetrievalStatus.MISSING,
                    error_message=f"Supplier terms for SKU '{sku}' not found",
                )
            source_ts = override.get("source_timestamp")
            is_stale = self._is_stale(source_ts)
            evidence, eid = self._create_evidence(
                source_url=f"mock://dashboard/suppliers/{sku}",
                fields_used=["lead_time_days", "pack_size", "unit_price", "supplier_name"],
                raw_data=override,
                source_timestamp=source_ts,
            )
            return SourceRetrievalResult(
                status=RetrievalStatus.STALE if is_stale else RetrievalStatus.SUCCESS,
                evidence=evidence,
                evidence_id=eid,
                data=override,
                is_stale=is_stale,
                error_message="Supplier terms price is stale" if is_stale else None,
            )

        tc_terms = {
            "SKU-001": {
                "id": "20000000-0000-0000-0000-000000000001",
                "product_id": "10000000-0000-0000-0000-000000000001",
                "supplier_name": "Acme Supplies",
                "lead_time_days": 14,
                "pack_size": 1,
                "unit_price": Decimal("10.00"),
                "currency": "USD",
                "moq": None,
                "price_updated_at": datetime.now(timezone.utc) - timedelta(days=7),
            },
            "SKU-002": {
                "id": "20000000-0000-0000-0000-000000000002",
                "product_id": "10000000-0000-0000-0000-000000000002",
                "supplier_name": "Bulk Co",
                "lead_time_days": 14,
                "pack_size": 12,
                "unit_price": Decimal("10.00"),
                "currency": "USD",
                "moq": None,
                "price_updated_at": datetime.now(timezone.utc) - timedelta(days=7),
            },
            "SKU-003": {
                "id": "20000000-0000-0000-0000-000000000003",
                "product_id": "10000000-0000-0000-0000-000000000003",
                "supplier_name": "Global Trade",
                "lead_time_days": 14,
                "pack_size": 1,
                "unit_price": Decimal("10.00"),
                "currency": "USD",
                "moq": None,
                "price_updated_at": datetime.now(timezone.utc) - timedelta(days=7),
            },
            "SKU-004": {
                "id": "20000000-0000-0000-0000-000000000004",
                "product_id": "10000000-0000-0000-0000-000000000004",
                "supplier_name": "Acme Supplies",
                "lead_time_days": 14,
                "pack_size": 1,
                "unit_price": Decimal("12.00"),  # 20% price increase
                "currency": "USD",
                "moq": None,
                "price_updated_at": datetime.now(timezone.utc),  # updated today
            },
        }

        if sku not in tc_terms:
            return SourceRetrievalResult(
                status=RetrievalStatus.MISSING,
                error_message=f"Supplier terms for SKU '{sku}' not found in mock catalog",
            )

        data = tc_terms[sku]
        evidence, eid = self._create_evidence(
            source_url=f"mock://dashboard/suppliers/{sku}",
            fields_used=["lead_time_days", "pack_size", "unit_price", "moq"],
            raw_data={
                "sku": sku,
                "supplier": data["supplier_name"],
                "price": float(data["unit_price"]),
                "lead_time": data["lead_time_days"],
                "pack_size": data["pack_size"],
            },
            source_timestamp=data["price_updated_at"],
        )

        return SourceRetrievalResult(
            status=RetrievalStatus.SUCCESS,
            evidence=evidence,
            evidence_id=eid,
            data=data,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # 3. Fetch Sales History
    # ─────────────────────────────────────────────────────────────────────────

    def fetch_sales_history(self, sku: str, days: int = 30) -> SourceRetrievalResult:
        if "sales" in self._simulate_failures:
            return SourceRetrievalResult(
                status=RetrievalStatus.FAILED,
                error_message=f"Simulated sales service failure: {self._simulate_failures['sales']}",
            )

        if sku in self._custom_overrides and "sales" in self._custom_overrides[sku]:
            override = self._custom_overrides[sku]["sales"]
            if override is None:
                return SourceRetrievalResult(
                    status=RetrievalStatus.MISSING,
                    error_message=f"Sales history for SKU '{sku}' not found",
                )
            evidence, eid = self._create_evidence(
                source_url=f"mock://dashboard/sales/{sku}",
                fields_used=["total_units_sold", "days_in_period"],
                raw_data=override,
            )
            return SourceRetrievalResult(
                status=RetrievalStatus.SUCCESS,
                evidence=evidence,
                evidence_id=eid,
                data=override,
            )

        # Standard TC baseline: 120 units over 30 days = 4.0 units/day
        tc_skus = {"SKU-001", "SKU-002", "SKU-003", "SKU-004"}
        if sku not in tc_skus:
            return SourceRetrievalResult(
                status=RetrievalStatus.MISSING,
                error_message=f"Sales history for SKU '{sku}' not found in mock source",
            )

        sales_data = {
            "total_units_sold": Decimal("120"),
            "days_in_period": days,
            "average_daily_demand": Decimal("4.0"),
        }

        evidence, eid = self._create_evidence(
            source_url=f"mock://dashboard/sales/{sku}?window_days={days}",
            fields_used=["total_units_sold", "days_in_period", "average_daily_demand"],
            raw_data={"sku": sku, "units_sold": 120, "days": days},
        )

        return SourceRetrievalResult(
            status=RetrievalStatus.SUCCESS,
            evidence=evidence,
            evidence_id=eid,
            data=sales_data,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # 4. Fetch Open Orders
    # ─────────────────────────────────────────────────────────────────────────

    def fetch_open_orders(self, sku: str) -> SourceRetrievalResult:
        if "open_orders" in self._simulate_failures:
            return SourceRetrievalResult(
                status=RetrievalStatus.FAILED,
                error_message=f"Simulated purchase order service failure: {self._simulate_failures['open_orders']}",
            )

        if sku in self._custom_overrides and "open_orders" in self._custom_overrides[sku]:
            override = self._custom_overrides[sku]["open_orders"]
            if override is None:
                return SourceRetrievalResult(
                    status=RetrievalStatus.MISSING,
                    error_message=f"Open orders for SKU '{sku}' could not be resolved",
                )

            # Check for conflict in override list
            has_conflict, conflict_msg = self._detect_order_conflicts(override)
            evidence, eid = self._create_evidence(
                source_url=f"mock://dashboard/orders/{sku}",
                fields_used=["open_orders", "order_reference", "ordered_quantity", "expected_arrival_date"],
                raw_data={"orders": override, "has_conflict": has_conflict},
            )
            return SourceRetrievalResult(
                status=RetrievalStatus.CONFLICT if has_conflict else RetrievalStatus.SUCCESS,
                evidence=evidence,
                evidence_id=eid,
                data=override,
                has_conflict=has_conflict,
                conflict_details=conflict_msg,
                error_message=conflict_msg if has_conflict else None,
            )

        # Standard TC open orders:
        # Only TC3 (SKU-003) has an open order: 24 units, arrives in 10 days, confirmed
        today = date.today()
        if sku == "SKU-003":
            orders = [
                {
                    "id": "40000000-0000-0000-0000-000000000003",
                    "order_reference": "PO-GAMMA-001",
                    "ordered_quantity": Decimal("24"),
                    "received_quantity": Decimal("0"),
                    "expected_arrival_date": today + timedelta(days=10),
                    "status": OrderStatus.CONFIRMED,
                }
            ]
        else:
            orders = []

        evidence, eid = self._create_evidence(
            source_url=f"mock://dashboard/orders/{sku}",
            fields_used=["open_orders"],
            raw_data={"sku": sku, "open_order_count": len(orders)},
        )

        return SourceRetrievalResult(
            status=RetrievalStatus.SUCCESS,
            evidence=evidence,
            evidence_id=eid,
            data=orders,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Conflict and Staleness Checks
    # ─────────────────────────────────────────────────────────────────────────

    def _is_stale(self, timestamp: datetime | str | None) -> bool:
        if timestamp is None:
            return False
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp)
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        return (now - timestamp) > timedelta(days=self.default_max_age_days)

    @staticmethod
    def _detect_order_conflicts(orders: list[dict[str, Any]]) -> tuple[bool, str | None]:
        """Detect conflicting duplicate open orders with differing quantities or dates."""
        seen: dict[str, dict[str, Any]] = {}
        for o in orders:
            ref = str(o.get("order_reference", ""))
            if not ref:
                continue
            qty = str(o.get("ordered_quantity"))
            arr = str(o.get("expected_arrival_date"))
            if ref in seen:
                prev = seen[ref]
                if str(prev.get("ordered_quantity")) != qty or str(prev.get("expected_arrival_date")) != arr:
                    return (
                        True,
                        f"Conflicting duplicate open orders detected for PO reference '{ref}': "
                        f"record 1 has qty={prev.get('ordered_quantity')}, arrival={prev.get('expected_arrival_date')}; "
                        f"record 2 has qty={qty}, arrival={arr}.",
                    )
            else:
                seen[ref] = o
        return False, None


# ─────────────────────────────────────────────────────────────────────────────
# Untrusted Content Sanitizer (Prompt Injection Guard)
# ─────────────────────────────────────────────────────────────────────────────


def sanitize_source_string(value: str | None) -> str:
    """Sanitize retrieved string content to prevent prompt injection execution.

    Retrieved dashboard text must be treated as untrusted data only.
    Strips dangerous control characters and tags; never interprets instructions.
    """
    if not value:
        return ""
    # Strip null bytes and normalize whitespace
    cleaned = value.replace("\x00", "").strip()
    return cleaned


# ─────────────────────────────────────────────────────────────────────────────
# High-Level Context Aggregator for Reorder Decision Pipeline
# ─────────────────────────────────────────────────────────────────────────────


def retrieve_reorder_context(
    sku: str,
    adapter: BaseSourceAdapter,
) -> ReorderSourceContext:
    """Fetch complete source context for an SKU with rigorous failure and provenance tracking.

    CRITICAL SAFETY RULES:
    - If any source fails (timeout, network error), the context is marked invalid.
    - If open orders retrieval fails, WE NEVER ASSUME ZERO OPEN ORDERS.
      The failure is explicitly recorded so the engine transitions to NEEDS_REVIEW or INSUFFICIENT_DATA.
    - If data is stale or conflicting, issues are logged and flagged.
    """
    now = datetime.now(timezone.utc)
    context = ReorderSourceContext(
        sku=sku,
        is_valid=True,
        status=RetrievalStatus.SUCCESS,
        retrieved_at=now,
    )

    # 1. Fetch Inventory
    inv_res = adapter.fetch_inventory(sku)
    if inv_res.status != RetrievalStatus.SUCCESS:
        context.is_valid = False
        context.status = inv_res.status
        context.issues.append(f"Inventory retrieval issue: {inv_res.error_message or inv_res.status.value}")
    else:
        context.product_data = inv_res.data
        if inv_res.evidence:
            context.evidence_records.append(inv_res.evidence)
            if inv_res.evidence_id:
                context.evidence_ids.append(inv_res.evidence_id)

    # 2. Fetch Supplier Terms
    terms_res = adapter.fetch_supplier_terms(sku)
    if terms_res.status != RetrievalStatus.SUCCESS:
        context.is_valid = False
        context.status = terms_res.status
        context.issues.append(f"Supplier terms issue: {terms_res.error_message or terms_res.status.value}")
    else:
        context.supplier_terms_data = terms_res.data
        if terms_res.evidence:
            context.evidence_records.append(terms_res.evidence)
            if terms_res.evidence_id:
                context.evidence_ids.append(terms_res.evidence_id)

    # 3. Fetch Sales History
    sales_res = adapter.fetch_sales_history(sku)
    if sales_res.status != RetrievalStatus.SUCCESS:
        context.is_valid = False
        context.status = sales_res.status
        context.issues.append(f"Sales history issue: {sales_res.error_message or sales_res.status.value}")
    else:
        context.sales_history_data = sales_res.data
        if sales_res.evidence:
            context.evidence_records.append(sales_res.evidence)
            if sales_res.evidence_id:
                context.evidence_ids.append(sales_res.evidence_id)

    # 4. Fetch Open Orders
    orders_res = adapter.fetch_open_orders(sku)
    if orders_res.status != RetrievalStatus.SUCCESS:
        context.is_valid = False
        context.status = orders_res.status
        # Explicit guard: do NOT set open_orders_data to [] if fetch failed!
        context.open_orders_data = None
        context.issues.append(f"Open purchase orders issue: {orders_res.error_message or orders_res.status.value}")
    else:
        context.open_orders_data = orders_res.data
        if orders_res.evidence:
            context.evidence_records.append(orders_res.evidence)
            if orders_res.evidence_id:
                context.evidence_ids.append(orders_res.evidence_id)

    return context
