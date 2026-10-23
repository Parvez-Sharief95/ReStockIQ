// TypeScript domain types — ReStockIQ
// Mirror the Pydantic schemas in backend/app/schemas/models.py
// ─────────────────────────────────────────────────────────────────────────────

// ── Enumerations ──────────────────────────────────────────────────────────────

export type OrderStatus =
  | 'open'
  | 'confirmed'
  | 'partially_received'
  | 'received'
  | 'cancelled';

export type BudgetStatus = 'ok' | 'over_budget' | 'needs_review' | 'unknown';

export type AnalysisStatus = 'ready' | 'needs_review' | 'insufficient_data';

export type RequestStatus =
  | 'draft'
  | 'pending_approval'
  | 'approved'
  | 'submitted_or_simulated'
  | 'verified'
  | 'rejected'
  | 'needs_review'
  | 'failed';

export type ApprovalAction = 'approved' | 'rejected';

export type VerificationStatus = 'verified' | 'pending' | 'failed';

export type SourceType = 'mock_source' | 'api' | 'http' | 'browser';

export type AuditEventType =
  | 'proposed'
  | 'approved'
  | 'rejected'
  | 'submitted'
  | 'retry'
  | 'verified'
  | 'failed'
  | 'version_invalidated';

export type TestCaseId = 'TC1' | 'TC2' | 'TC3' | 'TC4';

export type TestStatus = 'pass' | 'fail' | 'pending' | 'error';

// ── Product / SKU ─────────────────────────────────────────────────────────────

export interface Product {
  id: string; // UUID
  sku: string;
  name: string;
  unit: string;       // e.g. "each", "kg", "litre"
  currency: string;   // ISO 4217
  current_stock: number;
  reorder_point: number | null;
  safety_stock_target: number | null; // null → default 0, disclosed in evidence
  created_at: string; // ISO datetime
  updated_at: string;
}

export type ProductCreate = Omit<Product, 'id' | 'created_at' | 'updated_at'>;

// ── Supplier Terms ────────────────────────────────────────────────────────────

export interface SupplierTerms {
  id: string;
  product_id: string;
  supplier_name: string;
  lead_time_days: number;       // days from order to expected delivery
  pack_size: number;            // units per case; 1 = no case constraint
  unit_price: number;
  currency: string;
  moq: number | null;           // minimum order quantity in units
  price_updated_at: string;
  created_at: string;
  updated_at: string;
}

// ── Sales History / Demand Summary ────────────────────────────────────────────

export interface SalesHistory {
  id: string;
  product_id: string;
  period_start: string; // ISO date
  period_end: string;
  total_units_sold: number;
  days_in_period: number;
  average_daily_demand: number; // computed
  created_at: string;
}

// ── Open Purchase Order ───────────────────────────────────────────────────────

export interface OpenPurchaseOrder {
  id: string;
  product_id: string;
  supplier_terms_id: string;
  ordered_quantity: number;
  received_quantity: number;
  remaining_quantity: number; // ordered - received
  expected_arrival_date: string; // ISO date
  status: OrderStatus;
  order_reference: string;
  created_at: string;
  updated_at: string;
}

// ── Source Evidence ───────────────────────────────────────────────────────────

export interface SourceEvidence {
  id: string;
  source_type: SourceType;
  source_url: string | null;
  retrieved_at: string;
  source_timestamp: string | null;
  fields_used: string[];
  raw_data: Record<string, unknown>;
}

// ── Reorder Analysis ──────────────────────────────────────────────────────────

export interface AnalysisInputSnapshot {
  product_id: string;
  sku: string;
  average_daily_demand: number;
  demand_window_days: number;
  lead_time_days: number;
  usable_available_stock: number;
  safety_stock_target: number;
  safety_stock_was_defaulted: boolean;
  eligible_incoming_quantity: number;
  incoming_order_ids: string[];
  pack_size: number;
  moq: number | null;
  unit_price: number;
  currency: string;
  budget_available: number | null;
  supplier_terms_id: string;
  source_evidence_ids: string[];
  snapshot_at: string;
}

export interface ReorderAnalysis {
  id: string;
  product_id: string;
  calculation_version: string;
  input_snapshot: AnalysisInputSnapshot;

  // Calculation outputs
  average_daily_demand: number;
  lead_time_days: number;
  lead_time_demand: number;
  safety_stock_target: number;
  usable_available_stock: number;
  eligible_incoming_quantity: number;
  net_shortfall: number;
  pack_size: number;
  proposed_order_quantity: number;
  unit_price: number;
  estimated_cost: number;
  budget_available: number | null;
  budget_status: BudgetStatus;
  analysis_status: AnalysisStatus;
  status_reason: string | null;
  evidence_ids: string[];

  created_at: string;
}

// ── Reorder Request ───────────────────────────────────────────────────────────

export interface ReorderRequest {
  id: string;
  idempotency_key: string;
  analysis_id: string;
  product_id: string;
  sku: string;
  supplier_name: string;
  proposed_quantity: number;
  pack_count: number;
  pack_size: number;
  estimated_cost: number;
  currency: string;
  calculation_version: string;
  status: RequestStatus;
  created_at: string;
  updated_at: string;
}

export interface RequestVersion {
  id: string;
  request_id: string;
  version_number: number;
  snapshot: ReorderRequest;
  created_at: string;
}

// ── Approval ──────────────────────────────────────────────────────────────────

export interface Approval {
  id: string;
  request_id: string;
  request_version_id: string;
  approver_id: string;
  action: ApprovalAction;
  notes: string | null;
  timestamp: string;
}

// ── Verification ──────────────────────────────────────────────────────────────

export interface VerificationResult {
  id: string;
  request_id: string;
  intended_sku: string;
  actual_sku: string;
  sku_match: boolean;
  intended_quantity: number;
  actual_quantity: number;
  quantity_match: boolean;
  pack_size_check: boolean;
  duplicate_check: boolean;
  status: VerificationStatus;
  evidence: string;
  verified_at: string;
}

// ── Audit Events ──────────────────────────────────────────────────────────────

export interface AuditEvent {
  id: string;
  request_id: string;
  event_type: AuditEventType;
  actor_id: string | null;
  details: Record<string, unknown>;
  created_at: string;
}

// ── Test Runs (TC1–TC4) ───────────────────────────────────────────────────────

export interface TestRun {
  id: string;
  case_id: TestCaseId;
  description: string;
  input: Record<string, unknown>;
  expected_result: Record<string, unknown>;
  actual_result: Record<string, unknown> | null;
  status: TestStatus;
  evidence: string | null;
  run_at: string | null;
  created_at: string;
}

// ── Dashboard aggregates ──────────────────────────────────────────────────────

export interface StockoutRisk {
  product_id: string;
  sku: string;
  product_name: string;
  days_until_stockout: number | null; // null = already stocked out
  current_stock: number;
  average_daily_demand: number;
  analysis_status: AnalysisStatus;
}

export interface DashboardSummary {
  stockout_risks: StockoutRisk[];
  pending_approvals_count: number;
  recent_requests: ReorderRequest[];
}

// ── API error shape ───────────────────────────────────────────────────────────

export interface APIError {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}

export interface PaginatedResponse<T> {
  total: number;
  page: number;
  page_size: number;
  items: T[];
}

export interface AuthUser {
  id: string;
  email: string;
  name: string;
  role: 'planner' | 'approver' | 'auditor' | 'admin';
  is_demo?: boolean;
}
