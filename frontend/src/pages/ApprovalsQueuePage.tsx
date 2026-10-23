import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { dataService, getCurrentUser, ApiError } from '../services/dataService';
import { ReorderRequest } from '../types';

export const ApprovalsQueuePage: React.FC = () => {
  const [filter, setFilter] = useState<'pending' | 'all'>('pending');
  const [selectedReq, setSelectedReq] = useState<ReorderRequest | null>(null);
  const [modalMode, setModalMode] = useState<'approve' | 'reject' | 'modify' | null>(null);
  const [notes, setNotes] = useState<string>('');
  const [modifyQty, setModifyQty] = useState<number>(0);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);

  // Re-render trigger so the queue reflects backend mutations immediately.
  const [, forceUpdate] = useState(0);
  const refreshQueue = () => forceUpdate((n) => n + 1);

  // Supabase session may not be ready on mount; re-read on each render.
  const currentUser = getCurrentUser();
  const allRequests = dataService.getRequests();

  const requests = filter === 'pending'
    ? allRequests.filter((r) => r.status === 'pending_approval')
    : allRequests;

  const handleOpenModal = (req: ReorderRequest, mode: 'approve' | 'reject' | 'modify') => {
    setSelectedReq(req);
    setModalMode(mode);
    setNotes('');
    setModifyQty(req.proposed_quantity);
    setFeedback(null);
  };

  const handleCloseModal = () => {
    setSelectedReq(null);
    setModalMode(null);
    setNotes('');
    setFeedback(null);
  };

  const handleConfirmApproval = async () => {
    if (!selectedReq) return;
    setIsLoading(true);
    setFeedback(null);
    try {
      const latestVer = dataService.getLatestVersion(selectedReq.id);
      try {
        // Prefer async backend API
        await dataService.approveOrRejectApi(
          selectedReq.id,
          'approved',
          notes || 'Approved via Approval Queue',
          latestVer?.version_number
        );
      } catch (apiErr: unknown) {
        if (apiErr instanceof ApiError && apiErr.code === 'NETWORK_ERROR') {
          // Backend unreachable — fall back to local state with visible warning
          dataService.approveOrReject(
            selectedReq.id,
            'approved',
            notes || 'Approved via Approval Queue (offline)',
            latestVer?.version_number
          );
          setFeedback(
            `Backend unreachable. Approved locally only — changes will not persist until backend reconnects.`
          );
          setTimeout(() => { refreshQueue(); handleCloseModal(); }, 2000);
          return;
        }
        throw apiErr;
      }
      setFeedback(`Request approved (v${latestVer?.version_number}).`);
      refreshQueue();
      setTimeout(handleCloseModal, 1200);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Unknown error';
      setFeedback(`Error: ${msg}`);
    } finally {
      setIsLoading(false);
    }
  };

  const handleConfirmRejection = async () => {
    if (!selectedReq) return;
    setIsLoading(true);
    setFeedback(null);
    try {
      const latestVer = dataService.getLatestVersion(selectedReq.id);
      try {
        await dataService.approveOrRejectApi(
          selectedReq.id,
          'rejected',
          notes || 'Rejected by purchasing reviewer.',
          latestVer?.version_number
        );
      } catch (apiErr: unknown) {
        if (apiErr instanceof ApiError && apiErr.code === 'NETWORK_ERROR') {
          dataService.approveOrReject(
            selectedReq.id,
            'rejected',
            notes || 'Rejected by purchasing reviewer. (offline)',
            latestVer?.version_number
          );
          setFeedback(
            `Backend unreachable. Rejected locally only — changes will not persist until backend reconnects.`
          );
          setTimeout(() => { refreshQueue(); handleCloseModal(); }, 2000);
          return;
        }
        throw apiErr;
      }
      setFeedback(`Request rejected.`);
      refreshQueue();
      setTimeout(handleCloseModal, 1200);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Unknown error';
      setFeedback(`Error: ${msg}`);
    } finally {
      setIsLoading(false);
    }
  };

  const handleConfirmModification = () => {
    if (!selectedReq) return;
    try {
      const terms = dataService.getSupplierTerms(selectedReq.sku);
      const unitPrice = terms?.unit_price || 10.0;
      const packSize = selectedReq.pack_size;
      const newPacks = packSize > 1 ? Math.ceil(modifyQty / packSize) : modifyQty;
      const newCost = Math.round(modifyQty * unitPrice * 100) / 100;

      const { newVersion } = dataService.updateProposal(selectedReq.id, {
        proposedQuantity: modifyQty,
        packCount: newPacks,
        estimatedCost: newCost,
      });

      setFeedback(
        `Proposal updated to ${modifyQty} units. Created version v${newVersion.version_number}. Prior approvals invalidated per Rule S2.`
      );
      setTimeout(handleCloseModal, 1600);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to update proposal.';
      setFeedback(`Error: ${msg}`);
    }
  };

  return (
    <div className="fade-in">
      <div className="editorial-header">
        <div className="editorial-header-text">
          <h1>Human Review &amp; Approval Governance Queue</h1>
          <p>
            Authoritative gate for purchase orders. Consequential supplier submissions are blocked until approved by an authorized reviewer.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <button
            onClick={() => setFilter('pending')}
            className={`btn btn-sm ${filter === 'pending' ? 'btn-primary' : 'btn-outline'}`}
          >
            Pending Review ({allRequests.filter((r) => r.status === 'pending_approval').length})
          </button>
          <button
            onClick={() => setFilter('all')}
            className={`btn btn-sm ${filter === 'all' ? 'btn-primary' : 'btn-outline'}`}
          >
            All Requests ({allRequests.length})
          </button>
        </div>
      </div>

      {feedback && (
        <div className="badge badge-info" style={{ width: '100%', padding: '0.75rem', marginBottom: '1.25rem' }}>
          {feedback}
        </div>
      )}

      {/* Requests Queue Table */}
      <div className="card-editorial">
        <div className="table-container">
          <table className="table-editorial">
            <thead>
              <tr>
                <th>Request ID</th>
                <th>Target SKU</th>
                <th>Supplier</th>
                <th>Proposed Qty</th>
                <th>Packaging</th>
                <th>Est. Cost</th>
                <th>Version</th>
                <th>Status</th>
                <th style={{ textAlign: 'right' }}>Review Actions</th>
              </tr>
            </thead>
            <tbody>
              {requests.map((req) => {
                const latestVer = dataService.getLatestVersion(req.id);
                const auditTrail = dataService.getAuditTrail(req.id);
                const hasInvalidation = auditTrail.some((a) => a.event_type === 'version_invalidated');

                return (
                  <tr key={req.id}>
                    <td>
                      <Link to={`/requests/${req.id}`} className="mono" style={{ fontWeight: 700, color: 'var(--color-deep-aubergine)' }}>
                        {req.id.substring(0, 16)}...
                      </Link>
                    </td>
                    <td>
                      <span className="mono" style={{ fontWeight: 700 }}>
                        {req.sku}
                      </span>
                    </td>
                    <td>{req.supplier_name}</td>
                    <td>
                      <span className="mono" style={{ fontWeight: 700, fontSize: '0.95rem' }}>
                        {req.proposed_quantity}
                      </span>{' '}
                      units
                    </td>
                    <td>
                      <span className="mono">
                        {req.pack_count} {req.pack_size > 1 ? `cases (${req.pack_size}/cs)` : 'packs'}
                      </span>
                    </td>
                    <td>
                      <span className="mono">${req.estimated_cost.toFixed(2)}</span>
                    </td>
                    <td>
                      <span className="badge badge-neutral">v{latestVer?.version_number || 1}</span>
                      {hasInvalidation && (
                        <div style={{ fontSize: '0.68rem', color: '#8C6500', fontWeight: 700, marginTop: '2px' }}>
                          S2 Invalidated
                        </div>
                      )}
                    </td>
                    <td>
                      <span className={`badge badge-${req.status}`}>{req.status.replace('_', ' ')}</span>
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      <div style={{ display: 'inline-flex', gap: '0.4rem' }}>
                        {req.status === 'pending_approval' && (
                          <>
                            <button
                              onClick={() => handleOpenModal(req, 'approve')}
                              className="btn btn-sm btn-primary"
                              title="Grant human approval for this version"
                            >
                              Approve
                            </button>
                            <button
                              onClick={() => handleOpenModal(req, 'reject')}
                              className="btn btn-sm btn-outline"
                              title="Reject this reorder proposal"
                            >
                              Reject
                            </button>
                          </>
                        )}
                        <button
                          onClick={() => handleOpenModal(req, 'modify')}
                          className="btn btn-sm btn-outline"
                          title="Modify proposal parameters (increments version per Rule S2)"
                        >
                          Modify
                        </button>
                        <Link to={`/requests/${req.id}`} className="btn btn-sm btn-outline">
                          Audit &rarr;
                        </Link>
                      </div>
                    </td>
                  </tr>
                );
              })}
              {requests.length === 0 && (
                <tr>
                  <td colSpan={9} style={{ textAlign: 'center', padding: '3rem', color: 'var(--color-text-muted)' }}>
                    No requests currently pending human review.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Modal Dialog for Approve, Reject, or Modify */}
      {modalMode && selectedReq && (
        <div className="modal-overlay" role="dialog" aria-modal="true">
          <div className="modal-editorial">
            <div className="modal-header-editorial">
              <h3>
                {modalMode === 'approve' && 'Authorize Reorder Request'}
                {modalMode === 'reject' && 'Reject Reorder Request'}
                {modalMode === 'modify' && 'Modify Reorder Proposal (Rule S2)'}
              </h3>
              <button onClick={handleCloseModal} className="modal-close-btn" aria-label="Close modal">
                &times;
              </button>
            </div>

            <div className="modal-body-editorial">
              {feedback && (
                <div className="badge badge-info" style={{ width: '100%', padding: '0.65rem', marginBottom: '1rem' }}>
                  {feedback}
                </div>
              )}

              <div style={{ background: 'var(--color-lifted-silver)', padding: '0.85rem', borderRadius: 'var(--radius-md)', marginBottom: '1.25rem', fontSize: '0.85rem' }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
                  <div><strong>Target SKU:</strong> <span className="mono">{selectedReq.sku}</span></div>
                  <div><strong>Supplier:</strong> {selectedReq.supplier_name}</div>
                  <div><strong>Proposed Quantity:</strong> <span className="mono">{selectedReq.proposed_quantity}</span></div>
                  <div><strong>Estimated Cost:</strong> <span className="mono">${selectedReq.estimated_cost.toFixed(2)}</span></div>
                  <div><strong>Active Version:</strong> <span className="mono">v{dataService.getLatestVersion(selectedReq.id)?.version_number}</span></div>
                  <div><strong>Reviewer:</strong> {currentUser.name}</div>
                </div>
              </div>

              {modalMode === 'modify' ? (
                <div>
                  <div className="form-group">
                    <label className="form-label">Adjust Proposed Quantity (Units)</label>
                    <input
                      type="number"
                      className="form-input mono"
                      value={modifyQty}
                      min={1}
                      step={selectedReq.pack_size > 1 ? selectedReq.pack_size : 1}
                      onChange={(e) => setModifyQty(parseInt(e.target.value) || 0)}
                    />
                  </div>
                  <div style={{ fontSize: '0.8125rem', color: '#8C6500', background: 'var(--color-warning-bg)', padding: '0.65rem', borderRadius: '4px', border: '1px solid var(--color-warning-border)' }}>
                    <strong>Rule S2 Notice:</strong> Saving changes will increment the request to version <strong>v{(dataService.getLatestVersion(selectedReq.id)?.version_number || 1) + 1}</strong> and invalidate prior approvals. Re-approval will be required before submission.
                  </div>
                </div>
              ) : (
                <div className="form-group">
                  <label className="form-label">
                    {modalMode === 'approve' ? 'Approval Justification Notes (Optional)' : 'Rejection Reason (Mandatory)'}
                  </label>
                  <textarea
                    className="form-textarea"
                    rows={3}
                    placeholder={modalMode === 'approve' ? 'e.g. Approved within quarterly operating budget.' : 'e.g. Redundant stock, or cost exceeded acceptable threshold.'}
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                  />
                </div>
              )}
            </div>

            <div className="modal-footer-editorial">
              <button onClick={handleCloseModal} className="btn btn-outline">
                Cancel
              </button>
              {modalMode === 'approve' && (
                <button
                  onClick={handleConfirmApproval}
                  className="btn btn-primary"
                  disabled={isLoading}
                >
                  {isLoading ? 'Approving…' : 'Confirm Human Approval'}
                </button>
              )}
              {modalMode === 'reject' && (
                <button
                  onClick={handleConfirmRejection}
                  className="btn btn-danger"
                  disabled={isLoading}
                >
                  {isLoading ? 'Rejecting…' : 'Confirm Rejection'}
                </button>
              )}
              {modalMode === 'modify' && (
                <button onClick={handleConfirmModification} className="btn btn-accent">
                  Save Proposal &amp; Increment Version
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
