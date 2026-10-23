import React from 'react';
import { AuditEvent } from '../types';

interface AuditTrailListProps {
  events: AuditEvent[];
}

export const AuditTrailList: React.FC<AuditTrailListProps> = ({ events }) => {
  if (events.length === 0) {
    return (
      <div style={{ padding: '1rem', color: 'var(--color-text-muted)', fontSize: '0.85rem' }}>
        No audit events recorded yet for this request.
      </div>
    );
  }

  // Sort chronological ascending
  const sorted = [...events].sort(
    (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
  );

  const getEventBadgeClass = (type: string) => {
    switch (type) {
      case 'approved':
      case 'verified':
        return 'badge-success';
      case 'rejected':
      case 'failed':
        return 'badge-danger';
      case 'submitted':
        return 'badge-info';
      case 'version_invalidated':
      case 'retry':
        return 'badge-warning';
      default:
        return 'badge-neutral';
    }
  };

  return (
    <div className="audit-timeline" aria-label="Chronological Audit Timeline">
      {sorted.map((ev) => (
        <div key={ev.id} className={`audit-node event-${ev.event_type}`}>
          <div className="audit-card">
            <div className="audit-header">
              <span className={`badge ${getEventBadgeClass(ev.event_type)}`}>
                {ev.event_type.replace('_', ' ')}
              </span>
              <span className="mono" style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
                {new Date(ev.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
              </span>
            </div>

            <div style={{ fontSize: '0.8125rem', marginTop: '0.35rem' }}>
              {ev.details && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.2rem' }}>
                  {Object.entries(ev.details).map(([k, v]) => (
                    <div key={k} style={{ display: 'flex', gap: '0.4rem', color: 'var(--color-text-secondary)' }}>
                      <strong style={{ textTransform: 'capitalize' }}>{k.replace('_', ' ')}:</strong>
                      <span className="mono" style={{ wordBreak: 'break-all' }}>
                        {typeof v === 'object' ? JSON.stringify(v) : String(v)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {ev.actor_id && (
              <div style={{ fontSize: '0.72rem', color: 'var(--color-text-muted)', marginTop: '0.35rem' }}>
                Actor ID: <span className="mono">{ev.actor_id.substring(0, 8)}...</span>
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
};
