import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { dataService } from '../services/dataService';
import { GuardrailsCard } from '../components/GuardrailsCard';
import { DepletionChart } from '../components/DepletionChart';

export const DashboardPage: React.FC = () => {
  const [selectedSku, setSelectedSku] = useState<string>('SKU-001');
  const [syncStatus, setSyncStatus] = useState<'loading' | 'live' | 'offline' | 'error'>('loading');
  const [syncError, setSyncError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setSyncStatus('loading');
    dataService.syncWithBackend().then((ok) => {
      if (cancelled) return;
      setSyncStatus(ok ? 'live' : 'offline');
    }).catch((err: unknown) => {
      if (cancelled) return;
      setSyncError(err instanceof Error ? err.message : 'Sync failed');
      setSyncStatus('error');
    });
    return () => { cancelled = true; };
  }, []);

  const products = dataService.getProducts();
  const requests = dataService.getRequests();

  // Compute metrics
  const activeSkus = products.length;
  const pendingApprovals = requests.filter((r) => r.status === 'pending_approval').length;
  const verifiedOrders = requests.filter((r) => r.status === 'verified').length;

  const currentProduct = dataService.getProductBySku(selectedSku) || products[0];
  const currentTerms = dataService.getSupplierTerms(selectedSku);
  const currentIncoming = dataService.getOpenOrders(selectedSku).reduce(
    (acc, o) => acc + (o.remaining_quantity || o.ordered_quantity),
    0
  );

  return (
    <div className="fade-in">
      <div className="editorial-header">
        <div className="editorial-header-text">
          <h1>ReStockIQ Operations Command</h1>
          <p>
            Autonomous inventory depletion monitoring, deterministic lead-time reordering, and human-governed approval queues.
          </p>
          {/* Backend sync status chip */}
          {syncStatus === 'loading' && (
            <span style={{ fontSize: '0.78rem', color: 'var(--color-text-muted)' }}>Syncing with backend…</span>
          )}
          {syncStatus === 'offline' && (
            <span style={{ fontSize: '0.78rem', color: 'var(--color-warning)', fontWeight: 700 }}>Offline Mode — Local Seed Data</span>
          )}
          {syncStatus === 'error' && (
            <span style={{ fontSize: '0.78rem', color: 'var(--color-danger)', fontWeight: 700 }}>Backend Error: {syncError}</span>
          )}
          {syncStatus === 'live' && (
            <span style={{ fontSize: '0.78rem', color: 'var(--color-success)', fontWeight: 700 }}>Live Data Connected</span>
          )}
        </div>
        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <Link to="/inventory" className="btn btn-outline">
            View All SKUs
          </Link>
          <Link to="/approvals" className="btn btn-accent">
            Review Queue ({pendingApprovals})
          </Link>
        </div>
      </div>

      {/* Governance & Policy Guardrails Banner */}
      <GuardrailsCard />

      {/* Operational Metrics Grid */}
      <div className="metrics-grid">
        <div className="metric-card">
          <div className="metric-label">Active SKUs Monitored</div>
          <div className="metric-value">{activeSkus}</div>
          <div className="metric-helper">TC1–TC4 synthetic evaluation set</div>
        </div>

        <div className="metric-card alert-card">
          <div className="metric-label">Pending Human Approvals</div>
          <div className="metric-value">{pendingApprovals}</div>
          <div className="metric-helper" style={{ color: 'var(--color-warning)' }}>
            Mandatory gate before supplier submission
          </div>
        </div>

        <div className="metric-card">
          <div className="metric-label">Incoming Open Orders</div>
          <div className="metric-value">40 <span style={{ fontSize: '1rem' }}>units</span></div>
          <div className="metric-helper">SKU-003 confirmed order active</div>
        </div>

        <div className="metric-card success-card">
          <div className="metric-label">Verified Order Outcomes</div>
          <div className="metric-value">{verifiedOrders}</div>
          <div className="metric-helper" style={{ color: 'var(--color-success)' }}>
            Independent audit match confirmed
          </div>
        </div>
      </div>

      {/* Stockout Forecast & 30-Day Depletion Trend */}
      <div className="card-editorial" style={{ marginBottom: '1.75rem' }}>
        <div className="card-header-editorial">
          <h3>Stockout Risk Forecast &amp; Depletion Trajectory</h3>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            {products.map((p) => (
              <button
                key={p.sku}
                onClick={() => setSelectedSku(p.sku)}
                className={`btn btn-sm ${selectedSku === p.sku ? 'btn-primary' : 'btn-outline'}`}
              >
                {p.sku}
              </button>
            ))}
          </div>
        </div>

        <div className="card-body-editorial">
          {currentProduct && currentTerms && (
            <DepletionChart
              product={currentProduct}
              supplierTerms={currentTerms}
              eligibleIncoming={currentIncoming}
            />
          )}

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '1rem', paddingTop: '1rem', borderTop: '1px solid var(--color-border-light)' }}>
            <div style={{ fontSize: '0.85rem', color: 'var(--color-text-secondary)' }}>
              Selected: <strong>{currentProduct.name}</strong> &bull; Current on-hand: <span className="mono">{currentProduct.current_stock} units</span>
            </div>
            <Link to={`/analysis/${currentProduct.sku}`} className="btn btn-sm btn-primary">
              Deep-Dive Calculation &rarr;
            </Link>
          </div>
        </div>
      </div>

      {/* Active SKUs Quick Reorder Evaluation Table */}
      <div className="card-editorial">
        <div className="card-header-editorial">
          <h3>Deterministic Reorder Status Snapshot</h3>
          <Link to="/inventory" className="btn btn-sm btn-outline">
            Full Inventory Table &rarr;
          </Link>
        </div>

        <div className="table-container">
          <table className="table-editorial">
            <thead>
              <tr>
                <th>SKU</th>
                <th>Product Description</th>
                <th>Stock</th>
                <th>Daily Demand</th>
                <th>Lead Time</th>
                <th>Pack Size</th>
                <th>Shortfall</th>
                <th>Proposed Qty</th>
                <th>Status</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {products.map((prod) => {
                const analysis = dataService.evaluateReorder(prod.sku);
                const terms = dataService.getSupplierTerms(prod.sku);

                return (
                  <tr key={prod.sku}>
                    <td>
                      <span className="mono" style={{ fontWeight: 700, color: 'var(--color-deep-aubergine)' }}>
                        {prod.sku}
                      </span>
                    </td>
                    <td>{prod.name}</td>
                    <td>
                      <span className="mono">{prod.current_stock}</span> {prod.unit}
                    </td>
                    <td>
                      <span className="mono">{analysis.average_daily_demand.toFixed(1)}/day</span>
                    </td>
                    <td>{terms?.lead_time_days} days</td>
                    <td>
                      <span className="mono">
                        {terms && terms.pack_size > 1 ? `${terms.pack_size} / case` : 'Individual'}
                      </span>
                    </td>
                    <td>
                      <span className="mono" style={{ fontWeight: 700 }}>
                        {analysis.net_shortfall}
                      </span>
                    </td>
                    <td>
                      <strong className="mono" style={{ color: 'var(--color-deep-aubergine)' }}>
                        {analysis.proposed_order_quantity}
                      </strong>
                    </td>
                    <td>
                      <span className={`badge badge-${analysis.analysis_status}`}>
                        {analysis.analysis_status}
                      </span>
                    </td>
                    <td>
                      <Link to={`/analysis/${prod.sku}`} className="btn btn-sm btn-outline">
                        Evaluate
                      </Link>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
