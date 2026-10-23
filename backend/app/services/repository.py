"""repository.py — Data Repository Interfaces and Implementations
Phase 9 Real Persistence & Supabase Integration

Provides:
- Abstract Repository interfaces for Inventory, Analyses, Reorder Requests, and Test Runs.
- InMemoryRepositoryManager for ultra-fast, deterministic offline test execution (TC1–TC4).
- SupabaseRepositoryManager executing user-scoped SQL queries via PostgREST with forwarded JWT (RLS applied).
- Never falls back silently to in-memory store in production if Supabase is unavailable (fails safely & visibly).
- Strict secret isolation: client credentials are never returned or logged.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, datetime, timezone
from decimal import Decimal
import logging
from typing import Any, Sequence
from uuid import UUID
import uuid

from fastapi import Depends, HTTPException, status

from backend.app.config import settings
from backend.app.schemas.models import (
    AnalysisStatus,
    ApprovalAction,
    ApprovalRead,
    AuditEventRead,
    AuditEventType,
    OpenPurchaseOrderRead,
    ProductRead,
    ReorderAnalysisRead,
    ReorderRequestRead,
    RequestStatus,
    RequestVersionRead,
    SupplierTermsRead,
    TestRunRead,
    TestStatus,
    VerificationResultRead,
    VerificationStatus,
)
from backend.app.services.agent_orchestrator import make_json_safe
from backend.app.services.auth import AuthenticatedUser, get_current_user_optional
from backend.app.services.backend_store import BackendStore, get_backend_store
from backend.app.services.calculation_engine import (
    CALCULATION_ENGINE_VERSION,
    evaluate_reorder,
)
from backend.app.services.request_service import RequestService, generate_idempotency_key
from backend.app.services.source_adapter import MockSourceAdapter, retrieve_reorder_context

logger = logging.getLogger("inventory_reorder_planner.repository")


# ─────────────────────────────────────────────────────────────────────────────
# 1. Abstract Repository Interfaces
# ─────────────────────────────────────────────────────────────────────────────

class IInventoryRepository(ABC):
    @abstractmethod
    def list_products(self) -> list[dict[str, Any]]: ...

    @abstractmethod
    def get_product(self, sku: str) -> dict[str, Any] | None: ...


class IAnalysisRepository(ABC):
    @abstractmethod
    def save_analysis(self, analysis: ReorderAnalysisRead, user_id: UUID) -> ReorderAnalysisRead: ...

    @abstractmethod
    def get_analysis(self, analysis_id: UUID) -> ReorderAnalysisRead | None: ...

    @abstractmethod
    def list_analyses(self) -> list[ReorderAnalysisRead]: ...


class IReorderRepository(ABC):
    @abstractmethod
    def create_request(
        self,
        user_id: str,
        analysis_id: str,
        product_id: str,
        sku: str,
        supplier_name: str,
        proposed_quantity: Decimal,
        pack_count: int,
        pack_size: int,
        estimated_cost: Decimal,
        currency: str = "USD",
        calculation_version: str = "1.0.0",
        idempotency_key: str | None = None,
        actor_id: str | None = None,
    ) -> tuple[ReorderRequestRead, RequestVersionRead, bool]: ...

    @abstractmethod
    def get_request(self, request_id: UUID) -> ReorderRequestRead | None: ...

    @abstractmethod
    def list_requests(self, status: RequestStatus | None = None) -> list[ReorderRequestRead]: ...

    @abstractmethod
    def get_versions(self, request_id: UUID) -> list[RequestVersionRead]: ...

    @abstractmethod
    def get_latest_version(self, request_id: UUID) -> RequestVersionRead | None: ...

    @abstractmethod
    def get_audit_trail(self, request_id: UUID) -> list[AuditEventRead]: ...

    @abstractmethod
    def update_proposal(
        self,
        request_id: UUID,
        actor_id: str,
        proposed_quantity: Decimal | None = None,
        pack_count: int | None = None,
        pack_size: int | None = None,
        estimated_cost: Decimal | None = None,
        supplier_name: str | None = None,
        currency: str | None = None,
        modification_reason: str = "Proposal parameters updated by user",
    ) -> tuple[ReorderRequestRead, RequestVersionRead]: ...

    @abstractmethod
    def record_approval(
        self,
        request_id: UUID,
        approver_id: UUID,
        action: ApprovalAction,
        target_version_number: int | None = None,
        notes: str | None = None,
    ) -> tuple[ApprovalRead, ReorderRequestRead]: ...

    @abstractmethod
    def submit_request(
        self,
        request_id: UUID,
        actor_id: str,
        simulated: bool = True,
        force_failure: bool = False,
        failure_reason: str | None = None,
    ) -> tuple[ReorderRequestRead, dict[str, Any]]: ...

    @abstractmethod
    def verify_submission_outcome(
        self,
        request_id: UUID,
        actual_sku: str,
        actual_quantity: Decimal | float | int,
        actual_pack_size: int | None = None,
        existing_open_po_references: Sequence[str] | None = None,
        actor_id: str | None = None,
    ) -> tuple[VerificationResultRead, ReorderRequestRead]: ...

    @abstractmethod
    def get_verification(self, request_id: UUID) -> VerificationResultRead | None: ...

    @abstractmethod
    def get_approvals(self, request_id: UUID) -> list[ApprovalRead]: ...


class ITestRunRepository(ABC):
    @abstractmethod
    def save_test_run(self, test_run: TestRunRead, user_id: UUID) -> TestRunRead: ...

    @abstractmethod
    def list_test_runs(self) -> list[TestRunRead]: ...

    @abstractmethod
    def get_test_run(self, run_id: UUID) -> TestRunRead | None: ...


# ─────────────────────────────────────────────────────────────────────────────
# 2. In-Memory Repository Implementations (Deterministic Offline / Test Mode)
# ─────────────────────────────────────────────────────────────────────────────

class InMemoryInventoryRepository(IInventoryRepository):
    def __init__(self, store: BackendStore):
        self._store = store

    def list_products(self) -> list[dict[str, Any]]:
        return self._store.get_products()

    def get_product(self, sku: str) -> dict[str, Any] | None:
        return self._store.get_product(sku)


class InMemoryAnalysisRepository(IAnalysisRepository):
    def __init__(self, store: BackendStore):
        self._store = store

    def save_analysis(self, analysis: ReorderAnalysisRead, user_id: UUID) -> ReorderAnalysisRead:
        self._store.analyses[analysis.id] = analysis
        return analysis

    def get_analysis(self, analysis_id: UUID) -> ReorderAnalysisRead | None:
        return self._store.analyses.get(analysis_id)

    def list_analyses(self) -> list[ReorderAnalysisRead]:
        return list(self._store.analyses.values())


class InMemoryReorderRepository(IReorderRepository):
    def __init__(self, service: RequestService):
        self._service = service

    def create_request(
        self,
        user_id: str,
        analysis_id: str,
        product_id: str,
        sku: str,
        supplier_name: str,
        proposed_quantity: Decimal,
        pack_count: int,
        pack_size: int,
        estimated_cost: Decimal,
        currency: str = "USD",
        calculation_version: str = "1.0.0",
        idempotency_key: str | None = None,
        actor_id: str | None = None,
    ) -> tuple[ReorderRequestRead, RequestVersionRead, bool]:
        return self._service.create_reorder_request(
            user_id=user_id,
            analysis_id=analysis_id,
            product_id=product_id,
            sku=sku,
            supplier_name=supplier_name,
            proposed_quantity=proposed_quantity,
            pack_count=pack_count,
            pack_size=pack_size,
            estimated_cost=estimated_cost,
            currency=currency,
            calculation_version=calculation_version,
            idempotency_key=idempotency_key,
            actor_id=actor_id or user_id,
        )

    def get_request(self, request_id: UUID) -> ReorderRequestRead | None:
        return self._service._requests.get(request_id)

    def list_requests(self, status: RequestStatus | None = None) -> list[ReorderRequestRead]:
        reqs = list(self._service._requests.values())
        if status:
            return [r for r in reqs if r.status == status]
        return reqs

    def get_versions(self, request_id: UUID) -> list[RequestVersionRead]:
        return self._service.get_versions(request_id)

    def get_latest_version(self, request_id: UUID) -> RequestVersionRead | None:
        try:
            return self._service.get_latest_version(request_id)
        except KeyError:
            return None

    def get_audit_trail(self, request_id: UUID) -> list[AuditEventRead]:
        return self._service.get_audit_trail(request_id)

    def update_proposal(
        self,
        request_id: UUID,
        actor_id: str,
        proposed_quantity: Decimal | None = None,
        pack_count: int | None = None,
        pack_size: int | None = None,
        estimated_cost: Decimal | None = None,
        supplier_name: str | None = None,
        currency: str | None = None,
        modification_reason: str = "Proposal parameters updated by user",
    ) -> tuple[ReorderRequestRead, RequestVersionRead]:
        return self._service.update_proposal(
            request_id=request_id,
            actor_id=actor_id,
            proposed_quantity=proposed_quantity,
            pack_count=pack_count,
            pack_size=pack_size,
            estimated_cost=estimated_cost,
            supplier_name=supplier_name,
            currency=currency,
            modification_reason=modification_reason,
        )

    def record_approval(
        self,
        request_id: UUID,
        approver_id: UUID,
        action: ApprovalAction,
        target_version_number: int | None = None,
        notes: str | None = None,
    ) -> tuple[ApprovalRead, ReorderRequestRead]:
        return self._service.approve_or_reject_request(
            request_id=request_id,
            approver_id=approver_id,
            action=action,
            target_version_number=target_version_number,
            notes=notes,
        )

    def submit_request(
        self,
        request_id: UUID,
        actor_id: str,
        simulated: bool = True,
        force_failure: bool = False,
        failure_reason: str | None = None,
    ) -> tuple[ReorderRequestRead, dict[str, Any]]:
        return self._service.submit_request(
            request_id=request_id,
            actor_id=actor_id,
            simulated=simulated,
            force_failure=force_failure,
            failure_reason=failure_reason,
        )

    def verify_submission_outcome(
        self,
        request_id: UUID,
        actual_sku: str,
        actual_quantity: Decimal | float | int,
        actual_pack_size: int | None = None,
        existing_open_po_references: Sequence[str] | None = None,
        actor_id: str | None = None,
    ) -> tuple[VerificationResultRead, ReorderRequestRead]:
        return self._service.verify_submission_outcome(
            request_id=request_id,
            actual_sku=actual_sku,
            actual_quantity=actual_quantity,
            actual_pack_size=actual_pack_size,
            existing_open_po_references=existing_open_po_references,
            actor_id=actor_id,
        )

    def get_verification(self, request_id: UUID) -> VerificationResultRead | None:
        return self._service.get_verification_result(request_id)

    def get_approvals(self, request_id: UUID) -> list[ApprovalRead]:
        return self._service.get_approvals(request_id)


class InMemoryTestRunRepository(ITestRunRepository):
    def __init__(self, store: BackendStore):
        self._store = store

    def save_test_run(self, test_run: TestRunRead, user_id: UUID) -> TestRunRead:
        self._store.test_runs[test_run.id] = test_run
        return test_run

    def list_test_runs(self) -> list[TestRunRead]:
        return list(self._store.test_runs.values())

    def get_test_run(self, run_id: UUID) -> TestRunRead | None:
        return self._store.test_runs.get(run_id)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Supabase-Backed Repositories (Real Cloud / PostgreSQL Integration)
# ─────────────────────────────────────────────────────────────────────────────

class SupabaseInventoryRepository(IInventoryRepository):
    def __init__(self, client: Any):
        self._client = client

    def list_products(self) -> list[dict[str, Any]]:
        try:
            prod_res = self._client.from_("products").select("*").execute()
            products = prod_res.data or []
            terms_res = self._client.from_("supplier_terms").select("*").execute()
            terms_by_prod = {t["product_id"]: t for t in (terms_res.data or [])}

            orders_res = self._client.from_("open_purchase_orders").select("*").execute()
            orders_by_prod: dict[str, list[dict[str, Any]]] = {}
            for o in (orders_res.data or []):
                pid = o["product_id"]
                orders_by_prod.setdefault(pid, []).append(o)

            sales_res = self._client.from_("sales_history").select("*").execute()
            sales_by_prod = {s["product_id"]: s for s in (sales_res.data or [])}

            result = []
            for p in products:
                item = dict(p)
                pid = p["id"]
                item["supplier_terms"] = terms_by_prod.get(pid)
                item["open_orders_count"] = len(orders_by_prod.get(pid, []))
                item["sales_history"] = sales_by_prod.get(pid)
                item["source_type"] = "database"
                item["is_synthetic"] = False
                result.append(item)
            return result
        except Exception as e:
            logger.error("Supabase list_products query failed: %s", e)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Database query failed on products table: {str(e)}",
            )

    def get_product(self, sku: str) -> dict[str, Any] | None:
        try:
            prod_res = self._client.from_("products").select("*").eq("sku", sku.strip().upper()).execute()
            if not prod_res.data:
                return None
            prod = prod_res.data[0]
            pid = prod["id"]

            terms_res = self._client.from_("supplier_terms").select("*").eq("product_id", pid).execute()
            orders_res = self._client.from_("open_purchase_orders").select("*").eq("product_id", pid).execute()
            sales_res = self._client.from_("sales_history").select("*").eq("product_id", pid).execute()

            item = dict(prod)
            item["supplier_terms"] = terms_res.data[0] if terms_res.data else None
            item["open_orders"] = orders_res.data or []
            item["sales_history"] = sales_res.data[0] if sales_res.data else None
            item["source_type"] = "database"
            item["is_synthetic"] = False
            return item
        except Exception as e:
            logger.error("Supabase get_product query failed: %s", e)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Database query failed for SKU '{sku}': {str(e)}",
            )


class SupabaseAnalysisRepository(IAnalysisRepository):
    def __init__(self, client: Any):
        self._client = client

    def save_analysis(self, analysis: ReorderAnalysisRead, user_id: UUID) -> ReorderAnalysisRead:
        try:
            payload = {
                "id": str(analysis.id),
                "user_id": str(user_id),
                "product_id": str(analysis.product_id),
                "calculation_version": analysis.calculation_version,
                "input_snapshot": make_json_safe(analysis.input_snapshot),
                "average_daily_demand": float(analysis.average_daily_demand),
                "lead_time_days": analysis.lead_time_days,
                "lead_time_demand": float(analysis.lead_time_demand),
                "safety_stock_target": float(analysis.safety_stock_target),
                "usable_available_stock": float(analysis.usable_available_stock),
                "eligible_incoming_quantity": float(analysis.eligible_incoming_quantity),
                "net_shortfall": float(analysis.net_shortfall),
                "pack_size": analysis.pack_size,
                "proposed_order_quantity": float(analysis.proposed_order_quantity),
                "unit_price": float(analysis.unit_price),
                "estimated_cost": float(analysis.estimated_cost),
                "budget_available": float(analysis.budget_available) if analysis.budget_available is not None else None,
                "budget_status": analysis.budget_status.value,
                "analysis_status": analysis.analysis_status.value,
                "status_reason": analysis.status_reason,
                "evidence_ids": [str(eid) for eid in analysis.evidence_ids],
                "created_at": analysis.created_at.isoformat(),
            }
            self._client.from_("reorder_analyses").insert(payload).execute()
            return analysis
        except Exception as e:
            logger.error("Supabase save_analysis failed: %s", e)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to persist reorder analysis: {str(e)}",
            )

    def get_analysis(self, analysis_id: UUID) -> ReorderAnalysisRead | None:
        try:
            res = self._client.from_("reorder_analyses").select("*").eq("id", str(analysis_id)).execute()
            if not res.data:
                return None
            row = res.data[0]
            return ReorderAnalysisRead(
                id=UUID(row["id"]),
                product_id=UUID(row["product_id"]),
                calculation_version=row["calculation_version"],
                input_snapshot=row["input_snapshot"],
                average_daily_demand=Decimal(str(row["average_daily_demand"])),
                lead_time_days=int(row["lead_time_days"]),
                lead_time_demand=Decimal(str(row["lead_time_demand"])),
                safety_stock_target=Decimal(str(row["safety_stock_target"])),
                usable_available_stock=Decimal(str(row["usable_available_stock"])),
                eligible_incoming_quantity=Decimal(str(row["eligible_incoming_quantity"])),
                net_shortfall=Decimal(str(row["net_shortfall"])),
                pack_size=int(row["pack_size"]),
                proposed_order_quantity=Decimal(str(row["proposed_order_quantity"])),
                unit_price=Decimal(str(row["unit_price"])),
                estimated_cost=Decimal(str(row["estimated_cost"])),
                budget_available=Decimal(str(row["budget_available"])) if row.get("budget_available") is not None else None,
                budget_status=row["budget_status"],
                analysis_status=row["analysis_status"],
                status_reason=row.get("status_reason"),
                evidence_ids=[UUID(eid) for eid in row.get("evidence_ids", [])],
                created_at=datetime.fromisoformat(row["created_at"]),
            )
        except Exception as e:
            logger.error("Supabase get_analysis failed: %s", e)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to retrieve reorder analysis '{analysis_id}': {str(e)}",
            )

    def list_analyses(self) -> list[ReorderAnalysisRead]:
        try:
            res = self._client.from_("reorder_analyses").select("*").order("created_at", desc=True).execute()
            analyses = []
            for row in (res.data or []):
                analyses.append(
                    ReorderAnalysisRead(
                        id=UUID(row["id"]),
                        product_id=UUID(row["product_id"]),
                        calculation_version=row["calculation_version"],
                        input_snapshot=row["input_snapshot"],
                        average_daily_demand=Decimal(str(row["average_daily_demand"])),
                        lead_time_days=int(row["lead_time_days"]),
                        lead_time_demand=Decimal(str(row["lead_time_demand"])),
                        safety_stock_target=Decimal(str(row["safety_stock_target"])),
                        usable_available_stock=Decimal(str(row["usable_available_stock"])),
                        eligible_incoming_quantity=Decimal(str(row["eligible_incoming_quantity"])),
                        net_shortfall=Decimal(str(row["net_shortfall"])),
                        pack_size=int(row["pack_size"]),
                        proposed_order_quantity=Decimal(str(row["proposed_order_quantity"])),
                        unit_price=Decimal(str(row["unit_price"])),
                        estimated_cost=Decimal(str(row["estimated_cost"])),
                        budget_available=Decimal(str(row["budget_available"])) if row.get("budget_available") is not None else None,
                        budget_status=row["budget_status"],
                        analysis_status=row["analysis_status"],
                        status_reason=row.get("status_reason"),
                        evidence_ids=[UUID(eid) for eid in row.get("evidence_ids", [])],
                        created_at=datetime.fromisoformat(row["created_at"]),
                    )
                )
            return analyses
        except Exception as e:
            logger.error("Supabase list_analyses failed: %s", e)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to list analyses: {str(e)}",
            )


class SupabaseReorderRepository(IReorderRepository):
    def __init__(self, client: Any, user_id: UUID | None):
        self._client = client
        self._user_id = user_id

    def create_request(
        self,
        user_id: str,
        analysis_id: str,
        product_id: str,
        sku: str,
        supplier_name: str,
        proposed_quantity: Decimal,
        pack_count: int,
        pack_size: int,
        estimated_cost: Decimal,
        currency: str = "USD",
        calculation_version: str = "1.0.0",
        idempotency_key: str | None = None,
        actor_id: str | None = None,
    ) -> tuple[ReorderRequestRead, RequestVersionRead, bool]:
        u_id = user_id or str(self._user_id) or "00000000-0000-0000-0000-000000000001"
        key = idempotency_key or generate_idempotency_key(u_id, sku, analysis_id, 1)

        try:
            # 1. Check idempotency uniqueness
            existing_res = self._client.from_("reorder_requests").select("*").eq("user_id", u_id).eq("idempotency_key", key).execute()
            if existing_res.data:
                row = existing_res.data[0]
                req = self._parse_request_row(row)
                ver = self.get_latest_version(req.id) or self._create_dummy_version(req)
                return req, ver, True

            # 2. Insert new request
            new_id = uuid.uuid4()
            now = datetime.now(timezone.utc)
            req_payload = {
                "id": str(new_id),
                "user_id": u_id,
                "idempotency_key": key,
                "analysis_id": analysis_id,
                "product_id": product_id,
                "sku": sku,
                "supplier_name": supplier_name,
                "proposed_quantity": float(proposed_quantity),
                "pack_count": pack_count,
                "pack_size": pack_size,
                "estimated_cost": float(estimated_cost),
                "currency": currency,
                "calculation_version": calculation_version,
                "status": RequestStatus.PENDING_APPROVAL.value,
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
            }
            self._client.from_("reorder_requests").insert(req_payload).execute()

            # 3. Insert v1 request_versions snapshot
            ver_id = uuid.uuid4()
            ver_payload = {
                "id": str(ver_id),
                "user_id": u_id,
                "request_id": str(new_id),
                "version_number": 1,
                "snapshot": req_payload,
                "created_at": now.isoformat(),
            }
            self._client.from_("request_versions").insert(ver_payload).execute()

            # 4. Insert initial audit event
            audit_payload = {
                "id": str(uuid.uuid4()),
                "user_id": u_id,
                "request_id": str(new_id),
                "event_type": AuditEventType.PROPOSED.value,
                "actor_id": actor_id or u_id,
                "details": {
                    "sku": sku,
                    "quantity": float(proposed_quantity),
                    "pack_size": pack_size,
                    "estimated_cost": float(estimated_cost),
                    "idempotency_key": key,
                },
                "created_at": now.isoformat(),
            }
            self._client.from_("audit_events").insert(audit_payload).execute()

            req_read = ReorderRequestRead(
                id=new_id,
                analysis_id=UUID(analysis_id),
                product_id=UUID(product_id),
                sku=sku,
                supplier_name=supplier_name,
                proposed_quantity=proposed_quantity,
                pack_count=pack_count,
                pack_size=pack_size,
                estimated_cost=estimated_cost,
                currency=currency,
                calculation_version=calculation_version,
                status=RequestStatus.PENDING_APPROVAL,
                idempotency_key=key,
                user_id=UUID(u_id) if isinstance(u_id, str) else u_id,
                created_at=now,
                updated_at=now,
            )
            ver_read = RequestVersionRead(
                id=ver_id,
                request_id=new_id,
                version_number=1,
                snapshot=req_payload,
                created_at=now,
            )
            return req_read, ver_read, False
        except Exception as e:
            logger.error("Supabase create_request failed: %s", e)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to create reorder request in database: {str(e)}",
            )

    def get_request(self, request_id: UUID) -> ReorderRequestRead | None:
        try:
            res = self._client.from_("reorder_requests").select("*").eq("id", str(request_id)).execute()
            if not res.data:
                return None
            return self._parse_request_row(res.data[0])
        except Exception as e:
            logger.error("Supabase get_request failed: %s", e)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to retrieve request '{request_id}': {str(e)}",
            )

    def list_requests(self, status: RequestStatus | None = None) -> list[ReorderRequestRead]:
        try:
            query = self._client.from_("reorder_requests").select("*")
            if status:
                query = query.eq("status", status.value)
            res = query.order("created_at", desc=True).execute()
            return [self._parse_request_row(r) for r in (res.data or [])]
        except Exception as e:
            logger.error("Supabase list_requests failed: %s", e)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to list requests: {str(e)}",
            )

    def get_versions(self, request_id: UUID) -> list[RequestVersionRead]:
        try:
            res = self._client.from_("request_versions").select("*").eq("request_id", str(request_id)).order("version_number", desc=False).execute()
            return [
                RequestVersionRead(
                    id=UUID(r["id"]),
                    request_id=UUID(r["request_id"]),
                    version_number=r["version_number"],
                    snapshot=r["snapshot"],
                    created_at=datetime.fromisoformat(r["created_at"]),
                )
                for r in (res.data or [])
            ]
        except Exception as e:
            logger.error("Supabase get_versions failed: %s", e)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to get versions for request '{request_id}': {str(e)}",
            )

    def get_latest_version(self, request_id: UUID) -> RequestVersionRead | None:
        versions = self.get_versions(request_id)
        if not versions:
            return None
        return max(versions, key=lambda v: v.version_number)

    def get_audit_trail(self, request_id: UUID) -> list[AuditEventRead]:
        try:
            res = self._client.from_("audit_events").select("*").eq("request_id", str(request_id)).order("created_at", desc=False).execute()
            return [
                AuditEventRead(
                    id=UUID(r["id"]),
                    request_id=UUID(r["request_id"]),
                    event_type=AuditEventType(r["event_type"]),
                    actor_id=UUID(r["actor_id"]) if r.get("actor_id") else None,
                    details=r.get("details", {}),
                    created_at=datetime.fromisoformat(r["created_at"]),
                )
                for r in (res.data or [])
            ]
        except Exception as e:
            logger.error("Supabase get_audit_trail failed: %s", e)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to get audit trail for request '{request_id}': {str(e)}",
            )

    def update_proposal(
        self,
        request_id: UUID,
        actor_id: str,
        proposed_quantity: Decimal | None = None,
        pack_count: int | None = None,
        pack_size: int | None = None,
        estimated_cost: Decimal | None = None,
        supplier_name: str | None = None,
        currency: str | None = None,
        modification_reason: str = "Proposal parameters updated by user",
    ) -> tuple[ReorderRequestRead, RequestVersionRead]:
        req = self.get_request(request_id)
        if not req:
            raise KeyError(f"Request with ID '{request_id}' not found.")

        latest_ver = self.get_latest_version(request_id)
        current_ver_num = latest_ver.version_number if latest_ver else 1
        new_ver_num = current_ver_num + 1
        now = datetime.now(timezone.utc)

        new_qty = proposed_quantity if proposed_quantity is not None else req.proposed_quantity
        new_pack_size = pack_size if pack_size is not None else req.pack_size
        new_pack_count = pack_count if pack_count is not None else req.pack_count
        new_cost = estimated_cost if estimated_cost is not None else req.estimated_cost
        new_supplier = supplier_name if supplier_name is not None else req.supplier_name
        new_currency = currency if currency is not None else req.currency

        # Rule S2: modifying proposal resets status to pending_approval
        update_payload = {
            "proposed_quantity": float(new_qty),
            "pack_size": new_pack_size,
            "pack_count": new_pack_count,
            "estimated_cost": float(new_cost),
            "supplier_name": new_supplier,
            "currency": new_currency,
            "status": RequestStatus.PENDING_APPROVAL.value,
            "updated_at": now.isoformat(),
        }
        self._client.from_("reorder_requests").update(update_payload).eq("id", str(request_id)).execute()

        owner_id = str(req.user_id) if getattr(req, "user_id", None) else (str(self._user_id) or "00000000-0000-0000-0000-000000000001")
        new_ver_id = uuid.uuid4()
        ver_payload = {
            "id": str(new_ver_id),
            "user_id": owner_id,
            "request_id": str(request_id),
            "version_number": new_ver_num,
            "snapshot": update_payload,
            "created_at": now.isoformat(),
        }
        self._client.from_("request_versions").insert(ver_payload).execute()

        audit_payload = {
            "id": str(uuid.uuid4()),
            "user_id": owner_id,
            "request_id": str(request_id),
            "event_type": AuditEventType.VERSION_INVALIDATED.value,
            "actor_id": str(self._user_id) if self._user_id else (actor_id or owner_id),
            "details": {
                "prior_version": current_ver_num,
                "new_version": new_ver_num,
                "reason": modification_reason,
                "changes": {
                    "quantity": float(new_qty),
                    "pack_size": new_pack_size,
                    "estimated_cost": float(new_cost),
                },
            },
            "created_at": now.isoformat(),
        }
        self._client.from_("audit_events").insert(audit_payload).execute()

        updated_req = self.get_request(request_id)
        new_ver_read = RequestVersionRead(
            id=new_ver_id,
            request_id=request_id,
            version_number=new_ver_num,
            snapshot=ver_payload["snapshot"],
            created_at=now,
        )
        return updated_req or req, new_ver_read

    def record_approval(
        self,
        request_id: UUID,
        approver_id: UUID,
        action: ApprovalAction,
        target_version_number: int | None = None,
        notes: str | None = None,
    ) -> tuple[ApprovalRead, ReorderRequestRead]:
        req = self.get_request(request_id)
        if not req:
            raise KeyError(f"Request '{request_id}' not found.")

        latest_ver = self.get_latest_version(request_id)
        if not latest_ver:
            raise ValueError(f"Request '{request_id}' has no valid proposal version.")

        if target_version_number is not None and target_version_number != latest_ver.version_number:
            raise ValueError(
                f"Version mismatch: Target version {target_version_number} does not match current active version {latest_ver.version_number}."
            )

        now = datetime.now(timezone.utc)
        new_status = RequestStatus.APPROVED if action == ApprovalAction.APPROVED else RequestStatus.REJECTED
        owner_id = str(req.user_id) if getattr(req, "user_id", None) else (str(self._user_id) or str(approver_id))

        appr_id = uuid.uuid4()
        appr_payload = {
            "id": str(appr_id),
            "user_id": owner_id,
            "request_id": str(request_id),
            "request_version_id": str(latest_ver.id),
            "approver_id": str(approver_id),
            "action": action.value,
            "notes": notes,
            "timestamp": now.isoformat(),
        }
        self._client.from_("approvals").insert(appr_payload).execute()

        # Optimistic concurrency lock: only transition if status is pending_approval
        self._client.from_("reorder_requests").update({
            "status": new_status.value,
            "updated_at": now.isoformat(),
        }).eq("id", str(request_id)).eq("status", RequestStatus.PENDING_APPROVAL.value).execute()

        audit_type = AuditEventType.APPROVED if action == ApprovalAction.APPROVED else AuditEventType.REJECTED
        audit_payload = {
            "id": str(uuid.uuid4()),
            "user_id": owner_id,
            "request_id": str(request_id),
            "event_type": audit_type.value,
            "actor_id": str(approver_id),
            "details": {
                "action": action.value,
                "version_number": latest_ver.version_number,
                "notes": notes,
            },
            "created_at": now.isoformat(),
        }
        self._client.from_("audit_events").insert(audit_payload).execute()

        appr_read = ApprovalRead(
            id=appr_id,
            request_id=request_id,
            request_version_id=latest_ver.id,
            approver_id=approver_id,
            action=action,
            notes=notes,
            timestamp=now,
        )
        updated_req = self.get_request(request_id)
        return appr_read, updated_req or req

    def submit_request(
        self,
        request_id: UUID,
        actor_id: str,
        simulated: bool = True,
        force_failure: bool = False,
        failure_reason: str | None = None,
    ) -> tuple[ReorderRequestRead, dict[str, Any]]:
        req = self.get_request(request_id)
        if not req:
            raise KeyError(f"Request '{request_id}' not found.")

        if req.status != RequestStatus.APPROVED:
            raise PermissionError(
                f"Cannot submit request '{request_id}' in status '{req.status.value}'. Human approval is mandatory."
            )

        now = datetime.now(timezone.utc)
        if force_failure:
            new_status = RequestStatus.FAILED
            result = {
                "success": False,
                "error": failure_reason or "Supplier simulation rejected order payload",
                "simulated": True,
            }
            event_type = AuditEventType.FAILED
        else:
            new_status = RequestStatus.SUBMITTED_OR_SIMULATED
            result = {
                "success": True,
                "po_reference": f"SIM-PO-{str(request_id)[:8].upper()}",
                "simulated": True,
                "submitted_at": now.isoformat(),
            }
            event_type = AuditEventType.SUBMITTED

        owner_id = str(req.user_id) if getattr(req, "user_id", None) else (str(self._user_id) or actor_id)

        # Optimistic concurrency lock: only transition if status is approved
        self._client.from_("reorder_requests").update({
            "status": new_status.value,
            "updated_at": now.isoformat(),
        }).eq("id", str(request_id)).eq("status", RequestStatus.APPROVED.value).execute()

        audit_payload = {
            "id": str(uuid.uuid4()),
            "user_id": owner_id,
            "request_id": str(request_id),
            "event_type": event_type.value,
            "actor_id": str(self._user_id) if self._user_id else actor_id,
            "details": result,
            "created_at": now.isoformat(),
        }
        self._client.from_("audit_events").insert(audit_payload).execute()

        updated_req = self.get_request(request_id)
        return updated_req or req, result

    def verify_submission_outcome(
        self,
        request_id: UUID,
        actual_sku: str,
        actual_quantity: Decimal | float | int,
        actual_pack_size: int | None = None,
        existing_open_po_references: Sequence[str] | None = None,
        actor_id: str | None = None,
    ) -> tuple[VerificationResultRead, ReorderRequestRead]:
        req = self.get_request(request_id)
        if not req:
            raise KeyError(f"Request '{request_id}' not found.")

        act_qty = Decimal(str(actual_quantity))
        sku_match = actual_sku.strip().upper() == req.sku.strip().upper()
        qty_match = act_qty == req.proposed_quantity

        pack_size = actual_pack_size or req.pack_size
        pack_size_check = (act_qty % pack_size == 0) if pack_size > 1 else True

        open_refs = existing_open_po_references or []
        duplicate_check = len(open_refs) == len(set(open_refs))

        all_ok = sku_match and qty_match and pack_size_check and duplicate_check
        status_val = VerificationStatus.VERIFIED if all_ok else VerificationStatus.FAILED
        evidence_text = (
            "Verification passed: SKU, quantity, pack size, and PO uniqueness verified."
            if all_ok
            else f"Verification failed: sku_match={sku_match}, qty_match={qty_match}, pack_check={pack_size_check}, dup_check={duplicate_check}."
        )

        owner_id = str(req.user_id) if getattr(req, "user_id", None) else (str(self._user_id) or actor_id or "00000000-0000-0000-0000-000000000001")
        now = datetime.now(timezone.utc)
        ver_id = uuid.uuid4()
        ver_payload = {
            "id": str(ver_id),
            "user_id": owner_id,
            "request_id": str(request_id),
            "intended_sku": req.sku,
            "actual_sku": actual_sku,
            "sku_match": sku_match,
            "intended_quantity": float(req.proposed_quantity),
            "actual_quantity": float(act_qty),
            "quantity_match": qty_match,
            "pack_size_check": pack_size_check,
            "duplicate_check": duplicate_check,
            "status": status_val.value,
            "evidence": evidence_text,
            "verified_at": now.isoformat(),
        }
        self._client.from_("verification_results").insert(ver_payload).execute()

        new_req_status = RequestStatus.VERIFIED if all_ok else RequestStatus.FAILED
        self._client.from_("reorder_requests").update({
            "status": new_req_status.value,
            "updated_at": now.isoformat(),
        }).eq("id", str(request_id)).eq("status", RequestStatus.SUBMITTED_OR_SIMULATED.value).execute()

        audit_payload = {
            "id": str(uuid.uuid4()),
            "user_id": owner_id,
            "request_id": str(request_id),
            "event_type": AuditEventType.VERIFIED.value if all_ok else AuditEventType.FAILED.value,
            "actor_id": str(self._user_id) if self._user_id else (actor_id or owner_id),
            "details": ver_payload,
            "created_at": now.isoformat(),
        }
        self._client.from_("audit_events").insert(audit_payload).execute()

        ver_read = VerificationResultRead(
            id=ver_id,
            request_id=request_id,
            intended_sku=req.sku,
            actual_sku=actual_sku,
            sku_match=sku_match,
            intended_quantity=req.proposed_quantity,
            actual_quantity=act_qty,
            quantity_match=qty_match,
            pack_size_check=pack_size_check,
            duplicate_check=duplicate_check,
            status=status_val,
            evidence=evidence_text,
            verified_at=now,
        )
        updated_req = self.get_request(request_id)
        return ver_read, updated_req or req

    def get_verification(self, request_id: UUID) -> VerificationResultRead | None:
        try:
            res = self._client.from_("verification_results").select("*").eq("request_id", str(request_id)).execute()
            if not res.data:
                return None
            row = res.data[0]
            return VerificationResultRead(
                id=UUID(row["id"]),
                request_id=UUID(row["request_id"]),
                intended_sku=row["intended_sku"],
                actual_sku=row["actual_sku"],
                sku_match=row["sku_match"],
                intended_quantity=Decimal(str(row["intended_quantity"])),
                actual_quantity=Decimal(str(row["actual_quantity"])),
                quantity_match=row["quantity_match"],
                pack_size_check=row["pack_size_check"],
                duplicate_check=row["duplicate_check"],
                status=VerificationStatus(row["status"]),
                evidence=row["evidence"],
                verified_at=datetime.fromisoformat(row["verified_at"]),
            )
        except Exception as e:
            logger.error("Supabase get_verification failed: %s", e)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to get verification result: {str(e)}",
            )

    def get_approvals(self, request_id: UUID) -> list[ApprovalRead]:
        try:
            res = self._client.from_("approvals").select("*").eq("request_id", str(request_id)).order("timestamp", desc=False).execute()
            return [
                ApprovalRead(
                    id=UUID(r["id"]),
                    request_id=UUID(r["request_id"]),
                    request_version_id=UUID(r["request_version_id"]),
                    approver_id=UUID(r["approver_id"]),
                    action=ApprovalAction(r["action"]),
                    notes=r.get("notes"),
                    timestamp=datetime.fromisoformat(r["timestamp"]),
                )
                for r in (res.data or [])
            ]
        except Exception as e:
            logger.error("Supabase get_approvals failed: %s", e)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to get approvals: {str(e)}",
            )

    def _parse_request_row(self, row: dict[str, Any]) -> ReorderRequestRead:
        return ReorderRequestRead(
            id=UUID(row["id"]),
            analysis_id=UUID(row["analysis_id"]),
            product_id=UUID(row["product_id"]),
            sku=row["sku"],
            supplier_name=row["supplier_name"],
            proposed_quantity=Decimal(str(row["proposed_quantity"])),
            pack_count=int(row["pack_count"]),
            pack_size=int(row["pack_size"]),
            estimated_cost=Decimal(str(row["estimated_cost"])),
            currency=row["currency"],
            calculation_version=row["calculation_version"],
            status=RequestStatus(row["status"]),
            idempotency_key=row["idempotency_key"],
            user_id=UUID(row["user_id"]) if row.get("user_id") else None,
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def _create_dummy_version(self, req: ReorderRequestRead) -> RequestVersionRead:
        return RequestVersionRead(
            id=uuid.uuid4(),
            request_id=req.id,
            version_number=1,
            snapshot=req.model_dump(),
            created_at=req.created_at,
        )


class SupabaseTestRunRepository(ITestRunRepository):
    def __init__(self, client: Any, user_id: UUID | None):
        self._client = client
        self._user_id = user_id

    def save_test_run(self, test_run: TestRunRead, user_id: UUID) -> TestRunRead:
        try:
            payload = {
                "id": str(test_run.id),
                "user_id": str(user_id or self._user_id or "00000000-0000-0000-0000-000000000001"),
                "case_id": test_run.case_id.value,
                "description": test_run.description,
                "input": test_run.input,
                "expected_result": test_run.expected_result,
                "actual_result": test_run.actual_result,
                "status": test_run.status.value,
                "evidence": test_run.evidence,
                "run_at": test_run.run_at.isoformat() if test_run.run_at else None,
                "created_at": test_run.created_at.isoformat(),
            }
            self._client.from_("test_runs").insert(payload).execute()
            return test_run
        except Exception as e:
            logger.error("Supabase save_test_run failed: %s", e)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to persist test run: {str(e)}",
            )

    def list_test_runs(self) -> list[TestRunRead]:
        try:
            res = self._client.from_("test_runs").select("*").order("created_at", desc=True).execute()
            return [
                TestRunRead(
                    id=UUID(r["id"]),
                    case_id=r["case_id"],
                    description=r["description"],
                    input=r["input"],
                    expected_result=r["expected_result"],
                    actual_result=r.get("actual_result"),
                    status=TestStatus(r["status"]),
                    evidence=r.get("evidence"),
                    run_at=datetime.fromisoformat(r["run_at"]) if r.get("run_at") else None,
                    created_at=datetime.fromisoformat(r["created_at"]),
                )
                for r in (res.data or [])
            ]
        except Exception as e:
            logger.error("Supabase list_test_runs failed: %s", e)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to list test runs: {str(e)}",
            )

    def get_test_run(self, run_id: UUID) -> TestRunRead | None:
        try:
            res = self._client.from_("test_runs").select("*").eq("id", str(run_id)).execute()
            if not res.data:
                return None
            r = res.data[0]
            return TestRunRead(
                id=UUID(r["id"]),
                case_id=r["case_id"],
                description=r["description"],
                input=r["input"],
                expected_result=r["expected_result"],
                actual_result=r.get("actual_result"),
                status=TestStatus(r["status"]),
                evidence=r.get("evidence"),
                run_at=datetime.fromisoformat(r["run_at"]) if r.get("run_at") else None,
                created_at=datetime.fromisoformat(r["created_at"]),
            )
        except Exception as e:
            logger.error("Supabase get_test_run failed: %s", e)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to get test run '{run_id}': {str(e)}",
            )


# ─────────────────────────────────────────────────────────────────────────────
# 4. Repository Manager & Dependency Provider
# ─────────────────────────────────────────────────────────────────────────────

class RepositoryManager:
    """Unified container for all persistent repositories."""

    def __init__(
        self,
        inventory: IInventoryRepository,
        analyses: IAnalysisRepository,
        requests: IReorderRepository,
        test_runs: ITestRunRepository,
        adapter: MockSourceAdapter,
        is_persistent: bool = False,
    ):
        self.inventory = inventory
        self.analyses = analyses
        self.requests = requests
        self.test_runs = test_runs
        self.adapter = adapter
        self.is_persistent = is_persistent


def create_in_memory_repository_manager() -> RepositoryManager:
    """Create in-memory repository manager backed by BackendStore singleton."""
    store = get_backend_store()
    return RepositoryManager(
        inventory=InMemoryInventoryRepository(store),
        analyses=InMemoryAnalysisRepository(store),
        requests=InMemoryReorderRepository(store.request_service),
        test_runs=InMemoryTestRunRepository(store),
        adapter=store.adapter,
        is_persistent=False,
    )


def create_supabase_repository_manager(
    user_token: str | None = None,
    user_id: UUID | None = None,
) -> RepositoryManager:
    """Create Supabase repository manager with user token forwarded for RLS execution."""
    if not settings.supabase_url or not settings.supabase_secret_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Production persistence is unavailable: Supabase credentials are not configured.",
        )

    try:
        from supabase import create_client

        # RLS Protection Guard:
        # Base client is initialized with publishable key (anon) if available, or secret key.
        # If user_token is present, the PostgREST session is authenticated as that specific user.
        # If user_token is None, Authorization header is stripped so service_role can NEVER bypass RLS
        # for unauthenticated callers.
        base_key = settings.supabase_publishable_key or settings.supabase_secret_key
        client = create_client(settings.supabase_url, base_key)
        if user_token:
            client.postgrest.auth(user_token)
        elif not settings.supabase_publishable_key:
            client.postgrest.auth("")

        store = get_backend_store()
        return RepositoryManager(
            inventory=SupabaseInventoryRepository(client),
            analyses=SupabaseAnalysisRepository(client),
            requests=SupabaseReorderRepository(client, user_id),
            test_runs=SupabaseTestRunRepository(client, user_id),
            adapter=store.adapter,
            is_persistent=True,
        )
    except Exception as e:
        logger.error("Failed to initialize Supabase client: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to connect to Supabase database: {str(e)}",
        )


def get_repository_manager(
    user: AuthenticatedUser | None = Depends(get_current_user_optional),
) -> RepositoryManager:
    """FastAPI dependency injecting the appropriate repository manager.

    Safety rule:
    In production mode, in-memory storage fallback is STRICTLY FORBIDDEN.
    If Supabase is not configured or fails, it visibly raises HTTP 503.
    """
    is_production = settings.app_env.lower() == "production"

    if is_production or settings.repository_backend.lower() == "supabase":
        # Production or explicit supabase backend: Supabase persistence is mandatory
        return create_supabase_repository_manager(
            user_token=user.token if user else None,
            user_id=user.id if user else None,
        )

    # In 'auto' mode:
    if settings.repository_backend.lower() == "auto":
        if settings.supabase_url and (settings.supabase_secret_key or settings.supabase_publishable_key):
            return create_supabase_repository_manager(
                user_token=user.token if user else None,
                user_id=user.id if user else None,
            )
        return create_in_memory_repository_manager()

    # Default offline / testing mode:
    return create_in_memory_repository_manager()
