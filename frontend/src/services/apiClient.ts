/**
 * apiClient.ts — Typed FastAPI REST Client
 * Phase 8 Implementation
 *
 * Provides:
 * - Typed API communication with the Python/FastAPI backend.
 * - Normalized error handling with ApiError (code, message, status).
 * - Explicit labelling of mock source provenance.
 * - Never silently substitutes mock data when an operation fails.
 */

import {
  ApprovalAction,
  AuditEvent,
  Product,
  ReorderAnalysis,
  ReorderRequest,
  RequestVersion,
  SupplierTerms,
  TestCaseId,
  TestRun,
  VerificationResult,
} from '../types';

export class ApiError extends Error {
  code: string;
  status: number;
  details?: Record<string, unknown> | null;

  constructor(message: string, code: string = 'API_ERROR', status: number = 500, details?: Record<string, unknown> | null) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

const API_BASE_URL = (import.meta as unknown as { env?: { VITE_API_BASE_URL?: string } }).env?.VITE_API_BASE_URL ?? '';

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {}),
  };

  try {
    const response = await fetch(url, {
      ...options,
      headers,
    });

    const isJson = response.headers.get('content-type')?.includes('application/json');
    const data = isJson ? await response.json() : await response.text();

    if (!response.ok) {
      const code = data?.code || `HTTP_${response.status}`;
      const message = data?.message || data?.detail || `Request to ${endpoint} failed with status ${response.status}`;
      throw new ApiError(message, code, response.status, data?.details);
    }

    return data as T;
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    const message = error instanceof Error ? error.message : 'Unknown network failure';
    throw new ApiError(message, 'NETWORK_ERROR', 0);
  }
}

export const apiClient = {
  // Health
  async getHealth(): Promise<{ status: string; service: string }> {
    return request('/api/health');
  },

  // Dashboard
  async getDashboard(): Promise<{
    metrics: {
      total_products: number;
      stockout_risks: number;
      pending_approvals: number;
      submitted_orders: number;
      total_requests: number;
    };
    source_type: string;
    is_synthetic: boolean;
  }> {
    return request('/api/dashboard');
  },

  // Inventory
  async getInventory(): Promise<{
    items: (Product & { supplier_terms?: SupplierTerms; open_orders_count?: number })[];
    total: number;
    source_type: string;
    is_synthetic: boolean;
  }> {
    return request('/api/inventory');
  },

  async getSkuDetails(sku: string): Promise<{
    product: Product & { supplier_terms?: SupplierTerms; open_orders?: unknown[] };
    source_type: string;
    is_synthetic: boolean;
  }> {
    return request(`/api/inventory/${encodeURIComponent(sku)}`);
  },

  // Reorder Analyses
  async evaluateAnalysis(payload: {
    sku: string;
    budget_available?: number | null;
    baseline_unit_price?: number | null;
    safety_stock_target?: number | null;
  }): Promise<{
    analysis: ReorderAnalysis;
    explanation: string;
    order_breakdown: Array<{ order_reference: string; eligible: boolean; reason: string }>;
    price_hike_detected: boolean;
    price_change_pct: number;
    evidence_ids: string[];
    is_synthetic: boolean;
    source_type: string;
  }> {
    return request('/api/analyses/evaluate', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  async getAnalyses(): Promise<{ items: ReorderAnalysis[]; total: number; source_type: string }> {
    return request('/api/analyses');
  },

  async getAnalysisById(id: string): Promise<{ analysis: ReorderAnalysis; source_type: string }> {
    return request(`/api/analyses/${encodeURIComponent(id)}`);
  },

  // Reorder Requests
  async createRequest(payload: {
    analysis_id: string;
    sku: string;
    product_id: string;
    supplier_name: string;
    proposed_quantity: number;
    pack_count: number;
    pack_size: number;
    estimated_cost: number;
    currency?: string;
    user_id?: string;
    idempotency_key?: string;
    actor_id?: string;
  }): Promise<{
    request: ReorderRequest;
    version: RequestVersion;
    is_duplicate: boolean;
    source_type: string;
  }> {
    return request('/api/requests', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  async getRequests(statusFilter?: string): Promise<{
    items: ReorderRequest[];
    total: number;
    source_type: string;
  }> {
    const endpoint = statusFilter ? `/api/requests?status=${encodeURIComponent(statusFilter)}` : '/api/requests';
    return request(endpoint);
  },

  async getRequestById(id: string): Promise<{
    request: ReorderRequest;
    latest_version: RequestVersion;
    source_type: string;
  }> {
    return request(`/api/requests/${encodeURIComponent(id)}`);
  },

  async getRequestVersions(id: string): Promise<{
    versions: RequestVersion[];
    total: number;
  }> {
    return request(`/api/requests/${encodeURIComponent(id)}/versions`);
  },

  async getRequestAudit(id: string): Promise<{
    events: AuditEvent[];
    total: number;
  }> {
    return request(`/api/requests/${encodeURIComponent(id)}/audit`);
  },

  async updateProposal(
    id: string,
    payload: {
      proposed_quantity?: number;
      pack_count?: number;
      pack_size?: number;
      estimated_cost?: number;
      supplier_name?: string;
      actor_id?: string;
      modification_reason?: string;
    }
  ): Promise<{
    request: ReorderRequest;
    new_version: RequestVersion;
    status: string;
  }> {
    return request(`/api/requests/${encodeURIComponent(id)}/proposal`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    });
  },

  // Approvals
  async recordApproval(payload: {
    request_id: string;
    action: ApprovalAction;
    target_version_number?: number | null;
    notes?: string | null;
    approver_id?: string | null;
  }): Promise<{
    approval: unknown;
    request: ReorderRequest;
    status: string;
  }> {
    return request('/api/approvals', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  // Submission (Simulated)
  async submitOrder(
    id: string,
    payload: {
      actor_id?: string;
      force_failure?: boolean;
      failure_reason?: string;
    } = {}
  ): Promise<{
    request: ReorderRequest;
    result: {
      success: boolean;
      status: string;
      simulated: boolean;
      order_reference?: string;
      error?: string;
    };
  }> {
    return request(`/api/requests/${encodeURIComponent(id)}/submit`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  // Verification
  async verifyOutcome(
    id: string,
    payload: {
      actual_sku: string;
      actual_quantity: number;
      actual_pack_size?: number;
      simulate_duplicate?: boolean;
      actor_id?: string;
    }
  ): Promise<{
    verification: VerificationResult;
    request: ReorderRequest;
  }> {
    return request(`/api/requests/${encodeURIComponent(id)}/verify`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  async getVerification(id: string): Promise<{
    verification: VerificationResult;
  }> {
    return request(`/api/requests/${encodeURIComponent(id)}/verification`);
  },

  // Acceptance Test Scenarios
  async runTestCase(caseId: TestCaseId): Promise<{
    test_run: TestRun;
    is_synthetic: boolean;
    source_type: string;
  }> {
    return request(`/api/test-runs/run/${encodeURIComponent(caseId)}`, {
      method: 'POST',
    });
  },

  async runAllTestCases(): Promise<{
    total: number;
    passed: number;
    failed: number;
    all_passed: boolean;
    runs: TestRun[];
  }> {
    return request('/api/test-runs/run-all', {
      method: 'POST',
    });
  },

  async getTestRuns(): Promise<{
    items: TestRun[];
    total: number;
  }> {
    return request('/api/test-runs');
  },
};
