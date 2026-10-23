import { describe, it, expect, vi, beforeEach } from 'vitest';
import { apiClient, ApiError } from '../services/apiClient';

describe('FastAPI API Client (Phase 8)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('ApiError carries code, status, message, and details', () => {
    const err = new ApiError('Consequential action blocked', 'CONSEQUENTIAL_ACTION_BLOCKED', 403, {
      request_id: '123',
    });
    expect(err.message).toBe('Consequential action blocked');
    expect(err.code).toBe('CONSEQUENTIAL_ACTION_BLOCKED');
    expect(err.status).toBe(403);
    expect(err.details).toEqual({ request_id: '123' });
    expect(err.name).toBe('ApiError');
  });

  it('parses structured API errors from failed responses', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 403,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({
        code: 'CONSEQUENTIAL_ACTION_BLOCKED',
        message: 'Human approval is mandatory before submission.',
        details: null,
      }),
    });

    await expect(apiClient.submitOrder('req-123')).rejects.toThrowError(
      'Human approval is mandatory before submission.'
    );
  });

  it('handles network failures as ApiError with NETWORK_ERROR code', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('Failed to fetch'));

    await expect(apiClient.getHealth()).rejects.toMatchObject({
      code: 'NETWORK_ERROR',
      status: 0,
    });
  });

  it('formats GET inventory request and returns parsed data', async () => {
    const mockInventory = {
      items: [{ sku: 'SKU-001', name: 'Widget Alpha', current_stock: 20 }],
      total: 1,
      source_type: 'mock_source',
      is_synthetic: true,
    };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => mockInventory,
    });

    const res = await apiClient.getInventory();
    expect(res.total).toBe(1);
    expect(res.items[0].sku).toBe('SKU-001');
    expect(res.source_type).toBe('mock_source');
    expect(res.is_synthetic).toBe(true);
  });

  it('formats POST analysis evaluation request', async () => {
    const mockAnalysis = {
      analysis: {
        id: 'ana-123',
        sku: 'SKU-001',
        net_shortfall: 36,
        proposed_order_quantity: 36,
        analysis_status: 'ready',
      },
      explanation: 'Analysis explanation',
      order_breakdown: [],
      price_hike_detected: false,
      price_change_pct: 0,
      evidence_ids: ['evi-1'],
      is_synthetic: true,
      source_type: 'mock_source',
    };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => mockAnalysis,
    });

    const res = await apiClient.evaluateAnalysis({ sku: 'SKU-001', budget_available: 500 });
    expect(res.analysis.proposed_order_quantity).toBe(36);
    expect(res.is_synthetic).toBe(true);
  });

  it('executes official acceptance test case runner via apiClient', async () => {
    const mockRun = {
      test_run: {
        id: 'run-1',
        case_id: 'TC1',
        description: 'TC1 evaluation',
        input: { sku: 'SKU-001' },
        expected_result: { shortfall: 36 },
        actual_result: { shortfall: 36 },
        status: 'pass',
        evidence: 'Verified',
        created_at: '2026-10-23T00:00:00Z',
      },
      is_synthetic: true,
      source_type: 'mock_source',
    };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => mockRun,
    });

    const res = await apiClient.runTestCase('TC1');
    expect(res.test_run.case_id).toBe('TC1');
    expect(res.test_run.status).toBe('pass');
    expect(res.is_synthetic).toBe(true);
  });
});
