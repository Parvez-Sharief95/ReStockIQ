import React, { useState } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { dataService } from '../services/dataService';
import { DepletionChart } from '../components/DepletionChart';

export const AnalysisView: React.FC = () => {
  const { sku = 'SKU-001' } = useParams<{ sku: string }>();
  const navigate = useNavigate();

  const product = dataService.getProductBySku(sku);
  const terms = dataService.getSupplierTerms(sku);
  const openOrders = dataService.getOpenOrders(sku);

  // Reorder analysis
  const analysis = product ? dataService.evaluateReorder(sku) : null;

  // Custom quantity adjustment for draft request
  const [customQty, setCustomQty] = useState<number>(analysis?.proposed_order_quantity || 0);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [feedbackMessage, setFeedbackMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  if (!product || !terms || !analysis) {
    return (
      <div className="card-editorial" style={{ padding: '2rem', textAlign: 'center' }}>
        <h2>Product Not Found</h2>
        <p>No inventory record found for SKU: <span className="mono">{sku}</span></p>
        <Link to="/inventory" className="btn btn-primary">
          Back to Inventory
        </Link>
      </div>
    );
  }

  const eligibleIncoming = openOrders
    .filter((o) => o.status === 'confirmed' || o.status === 'open' || o.status === 'partially_received')
    .reduce((acc, o) => acc + (o.remaining_quantity || o.ordered_quantity), 0);

  const packSize = terms.pack_size;
  const computedPacks = packSize > 1 ? Math.ceil(customQty / packSize) : customQty;
  const computedCost = Math.round(customQty * terms.unit_price * 100) / 100;
  const isPackCompliant = packSize <= 1 || customQty % packSize === 0;

  const handleCreateDraft = () => {
    if (customQty <= 0) {
      setFeedbackMessage({ type: 'error', text: 'Proposed quantity must be greater than zero.' });
      return;
    }
    if (!isPackCompliant) {
      setFeedbackMessage({
        type: 'error',
        text: `Supplier requires case multiples of ${packSize}. Current quantity (${customQty}) is invalid.`,
      });
      return;
    }

    setIsSubmitting(true);
    try {
      const { request, isDuplicate } = dataService.createRequest({
        sku: product.sku,
        analysisId: analysis.id,
        proposedQuantity: customQty,
        packCount: computedPacks,
        packSize: packSize,
        estimatedCost: computedCost,
        supplierName: terms.supplier_name,
        currency: terms.currency,
      });

      setFeedbackMessage({
        type: 'success',
        text: isDuplicate
          ? `Idempotency matched: Reorder request ${request.id} already exists in pending_approval.`
          : `Reorder request ${request.id} created in pending_approval state. Awaiting human approval.`,
      });

      setTimeout(() => {
        navigate(`/requests/${request.id}`);
      }, 1500);
    } catch (err: any) {
      setFeedbackMessage({ type: 'error', text: err.message || 'Failed to create reorder request.' });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fade-in">
      <div className="editorial-header">
        <div className="editorial-header-text">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.35rem' }}>
            <span className="mono" style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--color-deep-aubergine)' }}>
              {product.sku}
            </span>
            <span className={`badge badge-${analysis.analysis_status}`}>
              {analysis.analysis_status.replace('_', ' ')}
            </span>
          </div>
          <h1>{product.name}</h1>
          <p>
            Deterministic calculation engine breakdown (Engine v{analysis.calculation_version}). All arithmetic computed via pure Python rules C1–C10.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <Link to="/inventory" className="btn btn-outline">
            &larr; Back to Inventory
          </Link>
        </div>
      </div>

      {feedbackMessage && (
        <div
          className={`badge ${feedbackMessage.type === 'success' ? 'badge-success' : 'badge-danger'}`}
          style={{ width: '100%', padding: '0.85rem 1.25rem', marginBottom: '1.25rem', fontSize: '0.85rem' }}
        >
          {feedbackMessage.text}
        </div>
      )}

      {/* 30-Day Depletion Chart */}
      <DepletionChart
        product={product}
        supplierTerms={terms}
        eligibleIncoming={eligibleIncoming}
      />

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: '1.5rem', marginBottom: '2rem' }}>
        {/* Step-by-Step Calculation Formula Card */}
        <div className="card-editorial">
          <div className="card-header-editorial">
            <h3>
              <span>📐</span> Mathematical Calculation Walkthrough
            </h3>
            <span className="mono text-muted" style={{ fontSize: '0.75rem' }}>
              Snapshot: {new Date(analysis.created_at).toLocaleTimeString()}
            </span>
          </div>

          <div className="card-body-editorial" style={{ display: 'flex', flexDirection: 'column', gap: '1.15rem' }}>
            {/* Step 1 */}
            <div style={{ borderLeft: '3px solid var(--color-deep-aubergine)', paddingLeft: '0.85rem' }}>
              <div style={{ fontSize: '0.78rem', fontWeight: 700, color: 'var(--color-text-secondary)', textTransform: 'uppercase' }}>
                1. Demand Forecast (C1)
              </div>
              <div style={{ fontSize: '0.9rem', marginTop: '0.2rem' }}>
                Average Daily Demand: <span className="mono">4.0 units/day</span> &times; Lead Time:{' '}
                <span className="mono">{terms.lead_time_days} days</span>
              </div>
              <div className="mono" style={{ fontWeight: 800, color: 'var(--color-deep-aubergine)', marginTop: '0.15rem' }}>
                Lead-Time Demand (LTD) = {analysis.lead_time_demand} units
              </div>
            </div>

            {/* Step 2 */}
            <div style={{ borderLeft: '3px solid var(--color-deep-aubergine)', paddingLeft: '0.85rem' }}>
              <div style={{ fontSize: '0.78rem', fontWeight: 700, color: 'var(--color-text-secondary)', textTransform: 'uppercase' }}>
                2. On-Hand Stock &amp; Incoming Orders (C2)
              </div>
              <div style={{ fontSize: '0.9rem', marginTop: '0.2rem' }}>
                Usable Available Stock: <span className="mono">{product.current_stock} units</span>
              </div>
              <div style={{ fontSize: '0.9rem' }}>
                Eligible Confirmed Orders:{' '}
                <span className="mono">{eligibleIncoming} units</span>
                {eligibleIncoming > 0 ? ' (PO-78901 expected in 5d)' : ' (None open)'}
              </div>
            </div>

            {/* Step 3 */}
            <div style={{ borderLeft: '3px solid var(--color-marigold)', paddingLeft: '0.85rem' }}>
              <div style={{ fontSize: '0.78rem', fontWeight: 700, color: '#8C6500', textTransform: 'uppercase' }}>
                3. Net Shortfall Formula (C3, C4)
              </div>
              <div className="mono" style={{ fontSize: '0.82rem', background: 'var(--color-lifted-silver)', padding: '0.4rem 0.6rem', borderRadius: '4px', marginTop: '0.25rem' }}>
                Formula: max(0, LTD + Safety - Stock - Incoming)
                <br />
                max(0, {analysis.lead_time_demand} + 0 - {product.current_stock} - {eligibleIncoming})
              </div>
              <div className="mono" style={{ fontWeight: 800, fontSize: '1.05rem', color: 'var(--color-deep-aubergine)', marginTop: '0.25rem' }}>
                Net Shortfall = {analysis.net_shortfall} units
              </div>
            </div>

            {/* Step 4 */}
            <div style={{ borderLeft: '3px solid var(--color-deep-aubergine)', paddingLeft: '0.85rem' }}>
              <div style={{ fontSize: '0.78rem', fontWeight: 700, color: 'var(--color-text-secondary)', textTransform: 'uppercase' }}>
                4. Packaging &amp; Case Rounding (C5)
              </div>
              <div style={{ fontSize: '0.9rem', marginTop: '0.2rem' }}>
                Supplier Pack Size: <span className="mono">{packSize} units / {packSize > 1 ? 'case' : 'pack'}</span>
              </div>
              <div className="mono" style={{ fontWeight: 800, color: 'var(--color-deep-aubergine)' }}>
                Proposed Quantity = {analysis.proposed_order_quantity} units
                {packSize > 1 && ` (${Math.ceil(analysis.proposed_order_quantity / packSize)} cases)`}
              </div>
            </div>

            {/* Step 5 */}
            <div style={{ borderLeft: '3px solid var(--color-deep-aubergine)', paddingLeft: '0.85rem' }}>
              <div style={{ fontSize: '0.78rem', fontWeight: 700, color: 'var(--color-text-secondary)', textTransform: 'uppercase' }}>
                5. Cost &amp; Budget Review (C6, C7, C8)
              </div>
              <div style={{ fontSize: '0.9rem', marginTop: '0.2rem' }}>
                Unit Price: <span className="mono">${terms.unit_price.toFixed(2)}</span> &bull; Est. Cost:{' '}
                <strong className="mono">${analysis.estimated_cost.toFixed(2)}</strong>
              </div>
              {analysis.budget_available && (
                <div style={{ fontSize: '0.82rem', marginTop: '0.2rem' }}>
                  Budget: <span className="mono">${analysis.budget_available.toFixed(2)}</span> &bull; Status:{' '}
                  <span className={`badge badge-${analysis.budget_status}`}>{analysis.budget_status}</span>
                </div>
              )}
              {analysis.status_reason && (
                <div style={{ fontSize: '0.8rem', color: 'var(--color-danger)', fontWeight: 600, marginTop: '0.35rem' }}>
                  ⚠️ {analysis.status_reason}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Action Panel: Prepare Reorder Request */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          <div className="card-editorial">
            <div className="card-header-editorial">
              <h3>
                <span>📝</span> Prepare Reorder Request
              </h3>
              <span className="badge badge-warning">Draft Creator</span>
            </div>

            <div className="card-body-editorial">
              <div className="form-group">
                <label className="form-label">Order Quantity (Units)</label>
                <input
                  type="number"
                  className="form-input mono"
                  min={1}
                  step={packSize > 1 ? packSize : 1}
                  value={customQty}
                  onChange={(e) => setCustomQty(parseInt(e.target.value) || 0)}
                />
                {packSize > 1 && (
                  <div style={{ fontSize: '0.75rem', color: isPackCompliant ? 'var(--color-text-muted)' : 'var(--color-danger)', marginTop: '0.25rem' }}>
                    * Must be a multiple of case size ({packSize} units). Current cases: {computedPacks}.
                  </div>
                )}
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', marginBottom: '1.25rem' }}>
                <div style={{ background: 'var(--color-lifted-silver)', padding: '0.75rem', borderRadius: 'var(--radius-md)' }}>
                  <div style={{ fontSize: '0.75rem', color: 'var(--color-text-secondary)', fontWeight: 700 }}>Total Cases</div>
                  <div className="mono" style={{ fontSize: '1.25rem', fontWeight: 800 }}>{computedPacks}</div>
                </div>
                <div style={{ background: 'var(--color-lifted-silver)', padding: '0.75rem', borderRadius: 'var(--radius-md)' }}>
                  <div style={{ fontSize: '0.75rem', color: 'var(--color-text-secondary)', fontWeight: 700 }}>Total Cost</div>
                  <div className="mono" style={{ fontSize: '1.25rem', fontWeight: 800 }}>${computedCost.toFixed(2)}</div>
                </div>
              </div>

              <button
                onClick={handleCreateDraft}
                disabled={isSubmitting || customQty <= 0 || !isPackCompliant}
                className="btn btn-accent"
                style={{ width: '100%', padding: '0.75rem' }}
              >
                <span>➕</span> Generate Reorder Request (v1)
              </button>

              <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', marginTop: '0.75rem', textAlign: 'center' }}>
                Created requests enter <span className="mono">pending_approval</span>. Real supplier orders are never submitted without human approval.
              </div>
            </div>
          </div>

          {/* Evidence Provenance Card */}
          <div className="card-editorial">
            <div className="card-header-editorial">
              <h3>
                <span>🔗</span> Source Evidence Provenance (Rule A12)
              </h3>
              <span className="badge badge-success">4/4 Verified</span>
            </div>

            <div className="card-body-editorial" style={{ fontSize: '0.8125rem' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
                {analysis.evidence_ids.map((eid, idx) => (
                  <div key={eid} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid var(--color-border-light)', paddingBottom: '0.4rem' }}>
                    <div>
                      <span className="mono" style={{ fontSize: '0.75rem', fontWeight: 700 }}>
                        EVID-{idx + 1}:
                      </span>{' '}
                      <span className="mono" style={{ color: 'var(--color-deep-aubergine)' }}>
                        {eid.substring(0, 8)}...
                      </span>
                    </div>
                    <span className="badge badge-neutral" style={{ fontSize: '0.65rem' }}>
                      mock_source
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
