"""
Pydantic v2 schemas — Inventory Reorder Planner
All data contracts shared by FastAPI endpoints and internal services.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# ─────────────────────────────────────────────────────────────────────────────
# Enumerations
# ─────────────────────────────────────────────────────────────────────────────


class OrderStatus(str, Enum):
    """Status values for open purchase orders from suppliers."""
    OPEN = "open"
    CONFIRMED = "confirmed"
    PARTIALLY_RECEIVED = "partially_received"
    RECEIVED = "received"
    CANCELLED = "cancelled"


class BudgetStatus(str, Enum):
    OK = "ok"
    OVER_BUDGET = "over_budget"
    NEEDS_REVIEW = "needs_review"
    UNKNOWN = "unknown"


class AnalysisStatus(str, Enum):
    READY = "ready"
    NEEDS_REVIEW = "needs_review"
    INSUFFICIENT_DATA = "insufficient_data"


class RequestStatus(str, Enum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    SUBMITTED_OR_SIMULATED = "submitted_or_simulated"
    VERIFIED = "verified"
    REJECTED = "rejected"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"


class ApprovalAction(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


class VerificationStatus(str, Enum):
    VERIFIED = "verified"
    PENDING = "pending"
    FAILED = "failed"


class SourceType(str, Enum):
    MOCK = "mock_source"
    API = "api"
    HTTP = "http"
    BROWSER = "browser"


class AuditEventType(str, Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUBMITTED = "submitted"
    RETRY = "retry"
    VERIFIED = "verified"
    FAILED = "failed"
    VERSION_INVALIDATED = "version_invalidated"


class TestCaseId(str, Enum):
    __test__ = False
    TC1 = "TC1"
    TC2 = "TC2"
    TC3 = "TC3"
    TC4 = "TC4"


class TestStatus(str, Enum):
    __test__ = False
    PASS = "pass"
    FAIL = "fail"
    PENDING = "pending"
    ERROR = "error"


# ─────────────────────────────────────────────────────────────────────────────
# Product / SKU
# ─────────────────────────────────────────────────────────────────────────────


class ProductBase(BaseModel):
    sku: str = Field(..., description="Unique stock-keeping unit identifier")
    name: str
    unit: str = Field("each", description="Unit of measure, e.g. 'each', 'kg', 'litre'")
    currency: str = Field("USD", description="ISO 4217 currency code")
    current_stock: Decimal = Field(..., ge=0, description="Current on-hand units")
    reorder_point: Decimal | None = Field(None, ge=0)
    safety_stock_target: Decimal | None = Field(
        None,
        ge=0,
        description="Explicit safety stock target. None = use 0 (disclosed in evidence).",
    )


class ProductCreate(ProductBase):
    pass


class ProductRead(ProductBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────────────
# Supplier Terms
# ─────────────────────────────────────────────────────────────────────────────


class SupplierTermsBase(BaseModel):
    product_id: UUID
    supplier_name: str
    lead_time_days: int = Field(..., gt=0, description="Days from order to expected delivery")
    pack_size: int = Field(1, ge=1, description="Units per case/pack; 1 = no case constraint")
    unit_price: Decimal = Field(..., gt=0, description="Price per single unit in `currency`")
    currency: str = Field("USD")
    moq: int | None = Field(None, ge=1, description="Minimum order quantity in units, if required")
    price_updated_at: datetime


class SupplierTermsCreate(SupplierTermsBase):
    pass


class SupplierTermsRead(SupplierTermsBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────────────
# Sales History / Demand Summary
# ─────────────────────────────────────────────────────────────────────────────


class SalesHistoryBase(BaseModel):
    product_id: UUID
    period_start: date
    period_end: date
    total_units_sold: Decimal = Field(..., ge=0)
    days_in_period: int = Field(..., gt=0)

    @field_validator("period_end")
    @classmethod
    def end_after_start(cls, v: date, info: Any) -> date:
        if "period_start" in info.data and v < info.data["period_start"]:
            raise ValueError("period_end must be >= period_start")
        return v


class SalesHistoryCreate(SalesHistoryBase):
    pass


class SalesHistoryRead(SalesHistoryBase):
    id: UUID
    average_daily_demand: Decimal  # computed column or derived
    created_at: datetime

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────────────
# Open Purchase Order
# ─────────────────────────────────────────────────────────────────────────────


class OpenPurchaseOrderBase(BaseModel):
    product_id: UUID
    supplier_terms_id: UUID
    ordered_quantity: Decimal = Field(..., gt=0)
    received_quantity: Decimal = Field(Decimal("0"), ge=0)
    expected_arrival_date: date
    status: OrderStatus
    order_reference: str = Field(..., description="Supplier PO reference number")


class OpenPurchaseOrderCreate(OpenPurchaseOrderBase):
    pass


class OpenPurchaseOrderRead(OpenPurchaseOrderBase):
    id: UUID
    remaining_quantity: Decimal  # ordered - received; computed
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────────────
# Source Evidence
# ─────────────────────────────────────────────────────────────────────────────


class SourceEvidenceBase(BaseModel):
    source_type: SourceType
    source_url: str | None = None
    retrieved_at: datetime
    source_timestamp: datetime | None = None
    fields_used: list[str] = Field(default_factory=list)
    raw_data: dict[str, Any] = Field(default_factory=dict)


class SourceEvidenceCreate(SourceEvidenceBase):
    pass


class SourceEvidenceRead(SourceEvidenceBase):
    id: UUID

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────────────
# Reorder Analysis + Calculation Evidence
# ─────────────────────────────────────────────────────────────────────────────


class AnalysisInputSnapshot(BaseModel):
    """Immutable snapshot of all inputs at the time of analysis.

    Stored alongside the result so calculations are reproducible.
    """
    product_id: str
    sku: str
    average_daily_demand: Decimal
    demand_window_days: int
    lead_time_days: int
    usable_available_stock: Decimal
    safety_stock_target: Decimal
    safety_stock_was_defaulted: bool = Field(
        False,
        description="True when safety_stock_target was defaulted to 0 (disclosed).",
    )
    eligible_incoming_quantity: Decimal
    incoming_order_ids: list[str]
    pack_size: int
    moq: int | None
    unit_price: Decimal
    currency: str
    budget_available: Decimal | None
    supplier_terms_id: str
    source_evidence_ids: list[str]
    snapshot_at: datetime


class ReorderAnalysisBase(BaseModel):
    product_id: UUID
    calculation_version: str = Field(
        ..., description="Semver or hash of the calculation engine that produced this result"
    )
    input_snapshot: AnalysisInputSnapshot

    # Outputs
    average_daily_demand: Decimal
    lead_time_days: int
    lead_time_demand: Decimal
    safety_stock_target: Decimal
    usable_available_stock: Decimal
    eligible_incoming_quantity: Decimal
    net_shortfall: Decimal = Field(..., ge=0)
    pack_size: int
    proposed_order_quantity: Decimal = Field(..., ge=0)
    unit_price: Decimal
    estimated_cost: Decimal = Field(..., ge=0)
    budget_available: Decimal | None
    budget_status: BudgetStatus
    analysis_status: AnalysisStatus
    status_reason: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class ReorderAnalysisCreate(ReorderAnalysisBase):
    pass


class ReorderAnalysisRead(ReorderAnalysisBase):
    id: UUID
    created_at: datetime

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────────────
# Reorder Request + Versioning
# ─────────────────────────────────────────────────────────────────────────────


class ReorderRequestBase(BaseModel):
    analysis_id: UUID
    product_id: UUID
    sku: str
    supplier_name: str
    proposed_quantity: Decimal = Field(..., ge=0)
    pack_count: int = Field(..., ge=0, description="Number of packs/cases ordered")
    pack_size: int = Field(..., ge=1)
    estimated_cost: Decimal = Field(..., ge=0)
    currency: str
    calculation_version: str


class ReorderRequestCreate(ReorderRequestBase):
    idempotency_key: str = Field(
        ..., description="Stable key derived from SKU + analysis snapshot hash. Must be unique."
    )


class ReorderRequestRead(ReorderRequestBase):
    id: UUID
    idempotency_key: str
    status: RequestStatus
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RequestVersionRead(BaseModel):
    id: UUID
    request_id: UUID
    version_number: int
    snapshot: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────────────
# Approval
# ─────────────────────────────────────────────────────────────────────────────


class ApprovalCreate(BaseModel):
    request_id: UUID
    request_version_id: UUID
    action: ApprovalAction
    notes: str | None = None


class ApprovalRead(ApprovalCreate):
    id: UUID
    approver_id: UUID
    timestamp: datetime

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────────────
# Verification
# ─────────────────────────────────────────────────────────────────────────────


class VerificationResultRead(BaseModel):
    id: UUID
    request_id: UUID
    intended_sku: str
    actual_sku: str
    sku_match: bool
    intended_quantity: Decimal
    actual_quantity: Decimal
    quantity_match: bool
    pack_size_check: bool
    duplicate_check: bool
    status: VerificationStatus
    evidence: str
    verified_at: datetime

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────────────
# Audit Events
# ─────────────────────────────────────────────────────────────────────────────


class AuditEventRead(BaseModel):
    id: UUID
    request_id: UUID
    event_type: AuditEventType
    actor_id: UUID | None
    details: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────────────
# Test Runs (TC1–TC4)
# ─────────────────────────────────────────────────────────────────────────────


class TestRunBase(BaseModel):
    case_id: TestCaseId
    description: str
    input: dict[str, Any]
    expected_result: dict[str, Any]


class TestRunCreate(TestRunBase):
    pass


class TestRunRead(TestRunBase):
    id: UUID
    actual_result: dict[str, Any] | None = None
    status: TestStatus = TestStatus.PENDING
    evidence: str | None = None
    run_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────────────
# API response wrappers
# ─────────────────────────────────────────────────────────────────────────────


class APIError(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class PaginatedResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[Any]


# ─────────────────────────────────────────────────────────────────────────────
# Canonical aliases (short names for router / test imports)
# ─────────────────────────────────────────────────────────────────────────────
Product = ProductRead
SupplierTerms = SupplierTermsRead
SalesHistory = SalesHistoryRead
OpenPurchaseOrder = OpenPurchaseOrderRead
SourceEvidence = SourceEvidenceRead
ReorderAnalysis = ReorderAnalysisRead
ReorderRequest = ReorderRequestRead
