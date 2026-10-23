import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { dataService } from '../services/dataService';

export const InventoryPage: React.FC = () => {
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [filterMode, setFilterMode] = useState<'all' | 'reorder_needed' | 'adequate' | 'review'>('all');

  const products = dataService.getProducts();

  const filtered = products.filter((p) => {
    const terms = dataService.getSupplierTerms(p.sku);
    const analysis = dataService.evaluateReorder(p.sku);

    const matchesSearch =
      p.sku.toLowerCase().includes(searchTerm.toLowerCase()) ||
      p.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (terms?.supplier_name.toLowerCase().includes(searchTerm.toLowerCase()) ?? false);

    if (!matchesSearch) return false;

    if (filterMode === 'reorder_needed') {
      return analysis.proposed_order_quantity > 0;
    }
    if (filterMode === 'adequate') {
      return analysis.proposed_order_quantity === 0;
    }
    if (filterMode === 'review') {
      return analysis.analysis_status === 'needs_review';
    }

    return true;
  });

  return (
    <div className="fade-in">
      <div className="editorial-header">
        <div className="editorial-header-text">
          <h1>SKU Inventory &amp; Supplier Catalog</h1>
          <p>
            Monitor stock levels, lead-time horizons, case-packaging constraints, and deterministic shortfall evaluations across all managed SKUs.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <Link to="/test-scenarios" className="btn btn-outline">
            Run Test Cases (TC1–TC4)
          </Link>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div
        className="card-editorial"
        style={{
          padding: '1rem 1.25rem',
          marginBottom: '1.5rem',
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '1rem',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flex: 1, minWidth: '280px' }}>
          <input
            type="text"
            className="form-input"
            placeholder="Search by SKU, product name, or supplier..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <span style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--color-text-secondary)' }}>
            Filter:
          </span>
          <button
            onClick={() => setFilterMode('all')}
            className={`btn btn-sm ${filterMode === 'all' ? 'btn-primary' : 'btn-outline'}`}
          >
            All SKUs ({products.length})
          </button>
          <button
            onClick={() => setFilterMode('reorder_needed')}
            className={`btn btn-sm ${filterMode === 'reorder_needed' ? 'btn-primary' : 'btn-outline'}`}
          >
            Order Needed
          </button>
          <button
            onClick={() => setFilterMode('adequate')}
            className={`btn btn-sm ${filterMode === 'adequate' ? 'btn-primary' : 'btn-outline'}`}
          >
            Adequate Stock
          </button>
          <button
            onClick={() => setFilterMode('review')}
            className={`btn btn-sm ${filterMode === 'review' ? 'btn-primary' : 'btn-outline'}`}
          >
            Needs Review
          </button>
        </div>
      </div>

      {/* Inventory Table */}
      <div className="card-editorial">
        <div className="table-container">
          <table className="table-editorial">
            <thead>
              <tr>
                <th>SKU</th>
                <th>Product Description</th>
                <th>Supplier Terms</th>
                <th>Current Stock</th>
                <th>Packaging</th>
                <th>Shortfall</th>
                <th>Proposed Order</th>
                <th>Est. Cost</th>
                <th>Status</th>
                <th style={{ textAlign: 'right' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((prod) => {
                const terms = dataService.getSupplierTerms(prod.sku);
                const analysis = dataService.evaluateReorder(prod.sku);

                return (
                  <tr key={prod.sku}>
                    <td>
                      <span className="mono" style={{ fontWeight: 700, color: 'var(--color-deep-aubergine)' }}>
                        {prod.sku}
                      </span>
                    </td>
                    <td>
                      <div>
                        <strong>{prod.name}</strong>
                        <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
                          Safety stock target: {prod.safety_stock_target ?? 0} {prod.unit}
                        </div>
                      </div>
                    </td>
                    <td>
                      <div>
                        <div>{terms?.supplier_name}</div>
                        <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
                          Lead time: {terms?.lead_time_days}d &bull; ${terms?.unit_price.toFixed(2)} / {prod.unit}
                        </div>
                      </div>
                    </td>
                    <td>
                      <span className="mono" style={{ fontSize: '0.95rem', fontWeight: 700 }}>
                        {prod.current_stock}
                      </span>{' '}
                      {prod.unit}
                    </td>
                    <td>
                      <span className="mono">
                        {terms && terms.pack_size > 1 ? (
                          <span className="badge badge-neutral">{terms.pack_size} units / case</span>
                        ) : (
                          'Single (1:1)'
                        )}
                      </span>
                    </td>
                    <td>
                      <span
                        className="mono"
                        style={{
                          fontWeight: 700,
                          color: analysis.net_shortfall > 0 ? 'var(--color-danger)' : 'var(--color-text-primary)',
                        }}
                      >
                        {analysis.net_shortfall}
                      </span>
                    </td>
                    <td>
                      <strong className="mono" style={{ fontSize: '1rem', color: 'var(--color-deep-aubergine)' }}>
                        {analysis.proposed_order_quantity}
                      </strong>
                    </td>
                    <td>
                      <span className="mono">${analysis.estimated_cost.toFixed(2)}</span>
                    </td>
                    <td>
                      <span className={`badge badge-${analysis.analysis_status}`}>
                        {analysis.analysis_status}
                      </span>
                      {analysis.budget_status === 'over_budget' && (
                        <div style={{ fontSize: '0.72rem', color: 'var(--color-danger)', fontWeight: 700, marginTop: '2px' }}>
                          Over Budget
                        </div>
                      )}
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      <Link to={`/analysis/${prod.sku}`} className="btn btn-sm btn-primary">
                        Analyze
                      </Link>
                    </td>
                  </tr>
                );
              })}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={10} style={{ textAlign: 'center', padding: '2.5rem', color: 'var(--color-text-muted)' }}>
                    No SKUs matched the current search or filter criteria.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
