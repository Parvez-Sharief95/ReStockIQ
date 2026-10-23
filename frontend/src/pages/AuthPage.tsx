import React, { useState } from 'react';
import { getCurrentUser, setCurrentUser, DEMO_USERS, DemoUser } from '../services/dataService';

export const AuthPage: React.FC = () => {
  const [activeUser, setActiveUser] = useState<DemoUser>(getCurrentUser());
  const [feedback, setFeedback] = useState<string | null>(null);

  const handleSelectUser = (u: DemoUser) => {
    setCurrentUser(u);
    setActiveUser(u);
    setFeedback(`Active session switched to ${u.name}.`);
    setTimeout(() => setFeedback(null), 2500);
  };

  return (
    <div className="fade-in" style={{ maxWidth: '800px', margin: '0 auto' }}>
      <div className="editorial-header">
        <div className="editorial-header-text">
          <h1>Identity, Governance &amp; Role Access</h1>
          <p>
            Role-based access control and Supabase Auth integration. Human approval authorities are segregated from inventory planning.
          </p>
        </div>
      </div>

      {feedback && (
        <div className="badge badge-success" style={{ width: '100%', padding: '0.85rem', marginBottom: '1.25rem' }}>
          {feedback}
        </div>
      )}

      {/* Active User Status Card */}
      <div className="card-editorial" style={{ marginBottom: '1.75rem' }}>
        <div className="card-header-editorial">
          <h3>
            <span>👤</span> Active Session Profile
          </h3>
          <span className="badge badge-success">Authenticated</span>
        </div>
        <div className="card-body-editorial">
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', fontSize: '0.875rem' }}>
            <div>
              <div style={{ color: 'var(--color-text-secondary)', fontSize: '0.78rem', fontWeight: 700 }}>USER NAME</div>
              <div style={{ fontSize: '1.05rem', fontWeight: 800, color: 'var(--color-deep-aubergine)', marginTop: '2px' }}>
                {activeUser.name}
              </div>
            </div>
            <div>
              <div style={{ color: 'var(--color-text-secondary)', fontSize: '0.78rem', fontWeight: 700 }}>EMAIL IDENTITY</div>
              <div className="mono" style={{ fontSize: '0.95rem', marginTop: '2px' }}>
                {activeUser.email}
              </div>
            </div>
            <div>
              <div style={{ color: 'var(--color-text-secondary)', fontSize: '0.78rem', fontWeight: 700 }}>AUTHENTICATED ROLE</div>
              <div style={{ marginTop: '2px' }}>
                <span className={`badge ${activeUser.role === 'approver' ? 'badge-warning' : 'badge-info'}`}>
                  {activeUser.role.toUpperCase()}
                </span>
              </div>
            </div>
            <div>
              <div style={{ color: 'var(--color-text-secondary)', fontSize: '0.78rem', fontWeight: 700 }}>USER UUID</div>
              <div className="mono" style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', marginTop: '2px' }}>
                {activeUser.id}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Switch Demo Role */}
      <div className="card-editorial" style={{ marginBottom: '1.75rem' }}>
        <div className="card-header-editorial">
          <h3>
            <span>👥</span> Switch Persona (Demo Testing Mode)
          </h3>
          <span className="badge badge-neutral">RLS Compatibility</span>
        </div>
        <div className="card-body-editorial">
          <p style={{ fontSize: '0.85rem', color: 'var(--color-text-secondary)', marginBottom: '1.25rem' }}>
            In production, user authentication is managed through Supabase Auth (email/password or magic links). For this offline demo, switch personas to test approval gating:
          </p>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '1rem' }}>
            {DEMO_USERS.map((u) => {
              const isCurrent = u.id === activeUser.id;
              return (
                <div
                  key={u.id}
                  style={{
                    border: `2px solid ${isCurrent ? 'var(--color-marigold)' : 'var(--color-border)'}`,
                    borderRadius: 'var(--radius-md)',
                    padding: '1rem',
                    background: isCurrent ? 'var(--color-warning-bg)' : 'var(--color-surface)',
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'space-between',
                  }}
                >
                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <strong style={{ fontSize: '0.95rem' }}>{u.name}</strong>
                      <span className={`badge ${u.role === 'approver' ? 'badge-warning' : 'badge-info'}`}>
                        {u.role}
                      </span>
                    </div>
                    <div className="mono" style={{ fontSize: '0.78rem', color: 'var(--color-text-muted)', marginTop: '0.25rem' }}>
                      {u.email}
                    </div>
                    <p style={{ fontSize: '0.78rem', color: 'var(--color-text-secondary)', marginTop: '0.5rem' }}>
                      {u.role === 'planner'
                        ? 'Can create reorder drafts, run analyses, and adjust proposals.'
                        : 'Authorized purchasing manager; can grant immutable human approvals.'}
                    </p>
                  </div>

                  <button
                    onClick={() => handleSelectUser(u)}
                    disabled={isCurrent}
                    className={`btn btn-sm ${isCurrent ? 'btn-outline' : 'btn-primary'}`}
                    style={{ marginTop: '0.75rem' }}
                  >
                    {isCurrent ? 'Active Persona' : `Switch to ${u.role}`}
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
};
