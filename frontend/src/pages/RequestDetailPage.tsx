import React, { useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { dataService, getCurrentUser } from '../services/dataService';
import { AuditTrailList } from '../components/AuditTrailList';

export const RequestDetailPage: React.FC = () => {
  const { id = '' } = useParams<{ id: string }>();
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [forceFailSubmission, setForceFailSubmission] = useState<boolean>(false);

  // Verification test controls
  const [actSku, setActSku] = useState<string>('');
  const [actQty, setActQty] = useState<number>(0);
  const [simulateDup, setSimulateDup] = useState<boolean>(false);

  const request = dataService.getRequestById(id);
  const versions = dataService.getVersions(id);
  const latestVer = dataService.getLatestVersion(id);
  const auditEvents = dataService.getAuditTrail(id);
  const verification = dataService.getVerificationResult(id);
  const currentUser = getCurrentUser();

  if (!request) {
    return (
      <div className="card-editorial" style={{ padding: '2rem', textAlign: 'center' }}>
        <h2>Request Not Found</h2>
        <p>No reorder request located with ID: <span className="mono">{id}</span></p>
        <Link to="/approvals" className="btn btn-primary">
          Return to Queue
        </Link>
      </div>
    );
  }

  // Stepper state calculation
  const isApproved = request.status === 'approved' || request.status === 'submitted_or_simulated' || request.status === 'verified';
  const isSubmitted = request.status === 'submitted_or_simulated' || request.status === 'verified';
  const isVerified = request.status === 'verified';

  const handleApprove = () => {
    try {
      dataService.approveOrReject(request.id, 'approved', 'Approved from detail audit view', latestVer?.version_number);
      setFeedback({ type: 'success', text: `Request approved for version v${latestVer?.version_number}.` });
    } catch (err: any) {
      setFeedback({ type: 'error', text: err.message });
    }
  };

  const handleSubmit = () => {
    try {
      const res = dataService.submitOrder(request.id, forceFailSubmission);
      if (res.success) {
        setFeedback({
          type: 'success',
          text: `Simulated order generated successfully: ${res.orderReference}`,
        });
        // Pre-fill verification form with intended values for convenience
        setActSku(request.sku);
        setActQty(request.proposed_quantity);
      } else {
        setFeedback({
          type: 'error',
          text: `Simulated order submission failed: ${res.error}. Request status marked as FAILED.`,
        });
      }
    } catch (err: any) {
      setFeedback({ type: 'error', text: err.message });
    }
  };

  const handleVerify = () => {
    try {
      const res = dataService.verifyOutcome(request.id, {
        actualSku: actSku || request.sku,
        actualQuantity: actQty || request.proposed_quantity,
        simulateDuplicate: simulateDup,
      });

      if (res.verification.status === 'verified') {
        setFeedback({ type: 'success', text: 'Independent verification PASSED: Actual matches intended parameters.' });
      } else {
        setFeedback({ type: 'error', text: 'Independent verification FAILED: Parameter mismatch detected.' });
      }
    } catch (err: any) {
      setFeedback({ type: 'error', text: err.message });
    }
  };

  return (
    <div className="fade-in">
      <div className="editorial-header">
        <div className="editorial-header-text">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem', marginBottom: '0.35rem' }}>
            <span className="mono" style={{ fontSize: '0.9rem', color: 'var(--color-text-muted)' }}>
              REQUEST #{request.id}
            </span>
            <span className={`badge badge-${request.status}`}>
              {request.status.replace('_', ' ')}
            </span>
          </div>
          <h1>Reorder Request &amp; Audit Trace</h1>
          <p>
            Immutable proposal versions, human approval credentials, simulated submission outcomes, and independent post-order verification.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <Link to="/approvals" className="btn btn-outline">
            &larr; Approvals Queue
          </Link>
          <Link to={`/analysis/${request.sku}`} className="btn btn-outline">
            View Calculation
          </Link>
        </div>
      </div>

      {feedback && (
        <div
          className={`badge ${feedback.type === 'success' ? 'badge-success' : 'badge-danger'}`}
          style={{ width: '100%', padding: '0.85rem', marginBottom: '1.5rem', fontSize: '0.85rem' }}
        >
          {feedback.text}
        </div>
      )}

      {/* Lifecycle Progress Stepper */}
      <div className="stepper" style={{ marginBottom: '2rem' }}>
        <div className="stepper-step completed">
          <div className="stepper-circle">1</div>
          <span className="stepper-label">Proposed (v{latestVer?.version_number})</span>
        </div>
        <div className={`stepper-step ${isApproved ? 'completed' : 'active'}`}>
          <div className="stepper-circle">2</div>
          <span className="stepper-label">Human Approved</span>
        </div>
        <div className={`stepper-step ${isSubmitted ? 'completed' : isApproved ? 'active' : ''}`}>
          <div className="stepper-circle">3</div>
          <span className="stepper-label">Simulated Submission</span>
        </div>
        <div className={`stepper-step ${isVerified ? 'completed' : isSubmitted ? 'active' : ''}`}>
          <div className="stepper-circle">4</div>
          <span className="stepper-label">Verified Outcome</span>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(350px, 1fr))', gap: '1.5rem', marginBottom: '2rem' }}>
        {/* Active Proposal Summary */}
        <div className="card-editorial">
          <div className="card-header-editorial">
            <h3>
              <span>📋</span> Current Proposal Details (v{latestVer?.version_number})
            </h3>
            <span className="badge badge-neutral">Active Snapshot</span>
          </div>
          <div className="card-body-editorial">
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', fontSize: '0.875rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--color-border-light)', paddingBottom: '0.4rem' }}>
                <span style={{ color: 'var(--color-text-secondary)' }}>Target SKU:</span>
                <span className="mono" style={{ fontWeight: 800, color: 'var(--color-deep-aubergine)' }}>{request.sku}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--color-border-light)', paddingBottom: '0.4rem' }}>
                <span style={{ color: 'var(--color-text-secondary)' }}>Supplier:</span>
                <span>{request.supplier_name}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--color-border-light)', paddingBottom: '0.4rem' }}>
                <span style={{ color: 'var(--color-text-secondary)' }}>Order Quantity:</span>
                <span className="mono" style={{ fontWeight: 800 }}>{request.proposed_quantity} units</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--color-border-light)', paddingBottom: '0.4rem' }}>
                <span style={{ color: 'var(--color-text-secondary)' }}>Pack Configuration:</span>
                <span className="mono">{request.pack_count} {request.pack_size > 1 ? `cases (${request.pack_size}/cs)` : 'individual packs'}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--color-border-light)', paddingBottom: '0.4rem' }}>
                <span style={{ color: 'var(--color-text-secondary)' }}>Estimated Cost:</span>
                <strong className="mono" style={{ fontSize: '1.05rem', color: 'var(--color-deep-aubergine)' }}>
                  ${request.estimated_cost.toFixed(2)} {request.currency}
                </strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--color-text-secondary)' }}>Idempotency Key:</span>
                <span className="mono" style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
                  {request.idempotency_key.substring(0, 18)}...
                </span>
              </div>
            </div>

            {/* Approval Action if still pending */}
            {request.status === 'pending_approval' && (
              <div style={{ marginTop: '1.25rem', paddingTop: '1rem', borderTop: '1px solid var(--color-border-light)' }}>
                <button onClick={handleApprove} className="btn btn-primary" style={{ width: '100%' }}>
                  <span>✅</span> Grant Human Approval (as {currentUser.name})
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Submission & Verification Controls */}
        <div className="card-editorial">
          <div className="card-header-editorial">
            <h3>
              <span>⚡</span> Consequential Submission &amp; Outcome Verification
            </h3>
            <span className="badge badge-warning">Human Guard Enforced</span>
          </div>
          <div className="card-body-editorial">
            {/* Submission Section */}
            <div style={{ marginBottom: '1.5rem', paddingBottom: '1.25rem', borderBottom: '1px solid var(--color-border-light)' }}>
              <div style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--color-deep-aubergine)', marginBottom: '0.5rem' }}>
                1. Supplier Order Transmission (Simulated)
              </div>

              {request.status === 'approved' ? (
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.85rem' }}>
                    <input
                      type="checkbox"
                      id="forceFail"
                      checked={forceFailSubmission}
                      onChange={(e) => setForceFailSubmission(e.target.checked)}
                    />
                    <label htmlFor="forceFail" style={{ fontSize: '0.8rem', color: 'var(--color-danger)' }}>
                      Simulate gateway failure (test visible error state)
                    </label>
                  </div>
                  <button onClick={handleSubmit} className="btn btn-accent" style={{ width: '100%' }}>
                    <span>🚀</span> Submit Order to Supplier (Simulated PO)
                  </button>
                </div>
              ) : request.status === 'submitted_or_simulated' || request.status === 'verified' ? (
                <div style={{ background: 'var(--color-info-bg)', padding: '0.75rem', borderRadius: 'var(--radius-md)', fontSize: '0.85rem' }}>
                  <div><strong>Status:</strong> Order Submitted (Simulated)</div>
                  <div className="mono" style={{ marginTop: '0.25rem' }}>
                    Reference: {auditEvents.find((a) => a.event_type === 'submitted')?.details?.order_reference as string || 'SIM-PO-DEMO'}
                  </div>
                </div>
              ) : (
                <div style={{ background: 'var(--color-danger-bg)', border: '1px solid var(--color-danger-border)', padding: '0.75rem', borderRadius: 'var(--radius-md)', fontSize: '0.8125rem', color: 'var(--color-danger)' }}>
                  🚫 <strong>Submission Blocked:</strong> Human approval is mandatory before any order can be submitted. Status is currently: <span className="mono">{request.status}</span>.
                </div>
              )}
            </div>

            {/* Independent Outcome Verification Section */}
            <div>
              <div style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--color-deep-aubergine)', marginBottom: '0.5rem' }}>
                2. Independent Outcome Verification
              </div>
              <p style={{ fontSize: '0.78rem', color: 'var(--color-text-secondary)', marginBottom: '0.75rem' }}>
                Verifies received PO outcome against intended SKU, quantity, pack constraints, and duplicate detection.
              </p>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem', marginBottom: '0.75rem' }}>
                <div>
                  <label className="form-label" style={{ fontSize: '0.75rem' }}>Received SKU</label>
                  <input
                    type="text"
                    className="form-input mono"
                    placeholder={request.sku}
                    value={actSku}
                    onChange={(e) => setActSku(e.target.value)}
                  />
                </div>
                <div>
                  <label className="form-label" style={{ fontSize: '0.75rem' }}>Received Quantity</label>
                  <input
                    type="number"
                    className="form-input mono"
                    placeholder={String(request.proposed_quantity)}
                    value={actQty || ''}
                    onChange={(e) => setActQty(parseInt(e.target.value) || 0)}
                  />
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
                <input
                  type="checkbox"
                  id="simulateDup"
                  checked={simulateDup}
                  onChange={(e) => setSimulateDup(e.target.checked)}
                />
                <label htmlFor="simulateDup" style={{ fontSize: '0.78rem', color: 'var(--color-text-secondary)' }}>
                  Simulate duplicate PO conflict (test mismatch detection)
                </label>
              </div>

              <button
                onClick={handleVerify}
                disabled={request.status !== 'submitted_or_simulated' && request.status !== 'verified'}
                className="btn btn-outline"
                style={{ width: '100%' }}
              >
                <span>🔍</span> Run Independent Verification Audit
              </button>

              {verification && (
                <div style={{ marginTop: '0.85rem', background: verification.status === 'verified' ? 'var(--color-success-bg)' : 'var(--color-danger-bg)', padding: '0.75rem', borderRadius: 'var(--radius-md)', fontSize: '0.78rem' }}>
                  <strong>Verification Outcome: {verification.status.toUpperCase()}</strong>
                  <pre className="mono" style={{ marginTop: '0.4rem', whiteSpace: 'pre-wrap', fontSize: '0.75rem' }}>
                    {verification.evidence}
                  </pre>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Immutable Request Versions & Chronological Audit Trail */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: '1.5rem' }}>
        {/* Version Snapshots */}
        <div className="card-editorial">
          <div className="card-header-editorial">
            <h3>
              <span>📜</span> Immutable Version Snapshots ({versions.length})
            </h3>
            <span className="badge badge-neutral">Rule S2 Enforced</span>
          </div>
          <div className="card-body-editorial">
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
              {versions.map((ver) => (
                <div
                  key={ver.id}
                  style={{
                    border: '1px solid var(--color-border-light)',
                    borderRadius: 'var(--radius-md)',
                    padding: '0.85rem',
                    background: ver.version_number === latestVer?.version_number ? 'var(--color-lifted-silver)' : 'var(--color-surface)',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.35rem' }}>
                    <span className="badge badge-neutral" style={{ fontWeight: 800 }}>
                      Version {ver.version_number}
                      {ver.version_number === latestVer?.version_number && ' (Active)'}
                    </span>
                    <span className="mono text-muted" style={{ fontSize: '0.75rem' }}>
                      {new Date(ver.created_at).toLocaleTimeString()}
                    </span>
                  </div>
                  <div style={{ fontSize: '0.8125rem', color: 'var(--color-text-secondary)' }}>
                    <div>Proposed: <strong className="mono">{ver.snapshot.proposed_quantity} units</strong> &bull; Cost: <span className="mono">${ver.snapshot.estimated_cost}</span></div>
                    <div>Packs: <span className="mono">{ver.snapshot.pack_count}</span> &bull; Pack size: <span className="mono">{ver.snapshot.pack_size}</span></div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Append-Only Audit Trail */}
        <div className="card-editorial">
          <div className="card-header-editorial">
            <h3>
              <span>⏱️</span> Chronological Audit Trail
            </h3>
            <span className="badge badge-info">{auditEvents.length} Events</span>
          </div>
          <div className="card-body-editorial">
            <AuditTrailList events={auditEvents} />
          </div>
        </div>
      </div>
    </div>
  );
};
