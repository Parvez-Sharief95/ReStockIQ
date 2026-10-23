import { describe, it, expect } from 'vitest';
import { dataService } from '../services/dataService';

describe('Frontend Data & Calculation Service (Phase 7)', () => {
  it('TC1: evaluates standard reorder shortfall accurately for SKU-001', () => {
    const analysis = dataService.evaluateReorder('SKU-001');
    expect(analysis.average_daily_demand).toBe(4.0);
    expect(analysis.lead_time_days).toBe(14);
    expect(analysis.lead_time_demand).toBe(56);
    expect(analysis.usable_available_stock).toBe(20);
    expect(analysis.eligible_incoming_quantity).toBe(0);
    expect(analysis.net_shortfall).toBe(36);
    expect(analysis.proposed_order_quantity).toBe(36);
    expect(analysis.estimated_cost).toBe(360.0);
    expect(analysis.analysis_status).toBe('ready');
  });

  it('TC2: rounds up to full case multiples for case-only suppliers (SKU-002)', () => {
    const analysis = dataService.evaluateReorder('SKU-002');
    expect(analysis.pack_size).toBe(12);
    expect(analysis.net_shortfall).toBe(36);
    expect(analysis.proposed_order_quantity).toBe(36);
    expect(analysis.proposed_order_quantity % 12).toBe(0);
    expect(analysis.estimated_cost).toBe(360.0);
  });

  it('TC3: recognizes eligible incoming purchase order and avoids shortfall (SKU-003)', () => {
    const analysis = dataService.evaluateReorder('SKU-003');
    expect(analysis.lead_time_demand).toBe(56);
    expect(analysis.usable_available_stock).toBe(20);
    expect(analysis.eligible_incoming_quantity).toBe(40);
    expect(analysis.net_shortfall).toBe(0);
    expect(analysis.proposed_order_quantity).toBe(0);
  });

  it('TC4: detects 20% price increase and flags budget overrun (SKU-004)', () => {
    const analysis = dataService.evaluateReorder('SKU-004');
    expect(analysis.unit_price).toBe(12.0);
    expect(analysis.proposed_order_quantity).toBe(36);
    expect(analysis.estimated_cost).toBe(432.0);
    expect(analysis.budget_available).toBe(400.0);
    expect(analysis.budget_status).toBe('over_budget');
    expect(analysis.analysis_status).toBe('needs_review');
  });

  it('enforces idempotency on duplicate request generation', () => {
    const analysis = dataService.evaluateReorder('SKU-001');
    const res1 = dataService.createRequest({
      sku: 'SKU-001',
      analysisId: analysis.id,
      proposedQuantity: 36,
      packCount: 36,
      packSize: 1,
      estimatedCost: 360.0,
      supplierName: 'Acme Supplies Co.',
    });
    expect(res1.request.id).toBeDefined();

    const res2 = dataService.createRequest({
      sku: 'SKU-001',
      analysisId: analysis.id,
      proposedQuantity: 36,
      packCount: 36,
      packSize: 1,
      estimatedCost: 360.0,
      supplierName: 'Acme Supplies Co.',
    });
    expect(res2.isDuplicate).toBe(true);
    expect(res2.request.id).toBe(res1.request.id);
  });

  it('blocks supplier order submission without mandatory human approval', () => {
    const analysis = dataService.evaluateReorder('SKU-002');
    const { request } = dataService.createRequest({
      sku: 'SKU-002',
      analysisId: analysis.id,
      proposedQuantity: 36,
      packCount: 3,
      packSize: 12,
      estimatedCost: 360.0,
      supplierName: 'PackCo Logistics Ltd.',
    });

    expect(request.status).toBe('pending_approval');
    expect(() => dataService.submitOrder(request.id)).toThrowError(/Mandatory human approval/);
  });

  it('Rule S2: invalidates prior approval when proposal parameters change', () => {
    const analysis = dataService.evaluateReorder('SKU-001');
    const { request } = dataService.createRequest({
      sku: 'SKU-001',
      analysisId: analysis.id,
      proposedQuantity: 36,
      packCount: 36,
      packSize: 1,
      estimatedCost: 360.0,
      supplierName: 'Acme Supplies Co.',
    });

    // 1. Grant approval for v1
    const latestVer = dataService.getLatestVersion(request.id)!;
    dataService.approveOrReject(request.id, 'approved', 'Looks good', latestVer.version_number);
    expect(request.status).toBe('approved');

    // 2. Modify proposal quantity to 48 -> creates v2 and resets status
    const { newVersion } = dataService.updateProposal(request.id, {
      proposedQuantity: 48,
      packCount: 48,
      estimatedCost: 480.0,
    });
    expect(newVersion.version_number).toBe(2);
    expect(request.status).toBe('pending_approval');

    // 3. Attempting to submit v2 without re-approval is blocked
    expect(() => dataService.submitOrder(request.id)).toThrowError(/Mandatory human approval/);

    // 4. Re-approving v2 allows submission
    dataService.approveOrReject(request.id, 'approved', 'Re-approved v2', 2);
    const subRes = dataService.submitOrder(request.id);
    expect(subRes.success).toBe(true);
    expect(subRes.orderReference).toMatch(/^SIM-PO-/);
  });

  it('independently verifies received outcome parameters', () => {
    const analysis = dataService.evaluateReorder('SKU-002');
    const { request } = dataService.createRequest({
      sku: 'SKU-002',
      analysisId: `${analysis.id}-verif-test`,
      proposedQuantity: 36,
      packCount: 3,
      packSize: 12,
      estimatedCost: 360.0,
      supplierName: 'PackCo Logistics Ltd.',
    });
    dataService.approveOrReject(request.id, 'approved');
    dataService.submitOrder(request.id);

    // 1. Valid outcome matches intended
    const verMatch = dataService.verifyOutcome(request.id, {
      actualSku: 'SKU-002',
      actualQuantity: 36,
    });
    expect(verMatch.verification.status).toBe('verified');
    expect(verMatch.request.status).toBe('verified');

    // 2. Mismatch in quantity fails verification
    const verMismatch = dataService.verifyOutcome(request.id, {
      actualSku: 'SKU-002',
      actualQuantity: 24, // Short delivery!
    });
    expect(verMismatch.verification.status).toBe('failed');
    expect(verMismatch.request.status).toBe('failed');
  });

  it('runs interactive test harness scenarios TC1–TC4', () => {
    const tc1 = dataService.runTestCase('TC1');
    expect(tc1.status).toBe('pass');

    const tc2 = dataService.runTestCase('TC2');
    expect(tc2.status).toBe('pass');

    const tc3 = dataService.runTestCase('TC3');
    expect(tc3.status).toBe('pass');

    const tc4 = dataService.runTestCase('TC4');
    expect(tc4.status).toBe('pass');
  });
});
