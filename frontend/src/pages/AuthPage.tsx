import React, { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { DEMO_USERS, DemoUser } from '../services/dataService';
import { ReStockIQLogo } from '../components/ReStockIQLogo';
import { useAuth } from '../context/useAuth';

export const AuthPage: React.FC = () => {
  const {
    user: activeUser,
    sessionToken,
    isConfigured,
    isAuthenticated,
    signIn,
    signUp,
    signOut,
    selectDemoUser,
  } = useAuth();

  const navigate = useNavigate();
  const location = useLocation();
  const returnUrl = (location.state as { from?: { pathname?: string } })?.from?.pathname || '/';

  // Form states
  const [authMode, setAuthMode] = useState<'signin' | 'signup'>('signin');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const handleSelectDemoPersona = (u: DemoUser) => {
    if (import.meta.env.PROD && isConfigured) {
      setErrorMsg(
        'Demo personas are disabled in production mode with Supabase. Please sign in or register with your verified Supabase credentials above.'
      );
      return;
    }
    selectDemoUser(u);
    setSuccessMsg(`Active session switched to ${u.name} (Local Demo Mode). Redirecting...`);
    setTimeout(() => {
      navigate(returnUrl);
    }, 600);
  };

  const handleSupabaseSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) {
      setErrorMsg('Please enter both email and password.');
      return;
    }
    setErrorMsg(null);
    setSuccessMsg(null);
    setLoading(true);

    try {
      if (authMode === 'signin') {
        const res = await signIn(email, password);
        if (!res.success) {
          setErrorMsg(res.error || 'Sign-in failed.');
        } else {
          setSuccessMsg('Authenticated successfully via Supabase Auth! Redirecting to dashboard...');
          setTimeout(() => {
            navigate(returnUrl);
          }, 600);
        }
      } else {
        const res = await signUp(email, password);
        if (!res.success) {
          setErrorMsg(res.error || 'Registration failed.');
        } else if (res.sessionCreated) {
          setSuccessMsg('Registration successful and session created! Redirecting to dashboard...');
          setTimeout(() => {
            navigate(returnUrl);
          }, 600);
        } else {
          setSuccessMsg(
            'Registration successful! If your Supabase project has email confirmation enabled, please check your inbox to confirm your account before logging in.'
          );
          setAuthMode('signin');
        }
      }
    } finally {
      setLoading(false);
    }
  };

  const handleSignOut = async () => {
    setLoading(true);
    await signOut();
    setLoading(false);
    setSuccessMsg('Signed out successfully.');
    setTimeout(() => setSuccessMsg(null), 3000);
  };

  return (
    <div className="fade-in" style={{ maxWidth: '800px', margin: '0 auto', padding: '1rem 0' }}>
      <div className="editorial-header">
        <div className="editorial-header-text">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem', marginBottom: '0.5rem' }}>
            <ReStockIQLogo size={28} />
            <span style={{ fontSize: '0.95rem', fontWeight: 700, color: 'var(--color-marigold)' }}>
              ReStockIQ Security &amp; Access
            </span>
          </div>
          <h1>Identity, Governance &amp; Role Access</h1>
          <p>
            Role-based access control and Supabase Auth integration. Consequential procurement approval authorities
            are strictly segregated from inventory planning.
          </p>
        </div>
      </div>

      {successMsg && (
        <div
          className="badge badge-success"
          id="auth-success-alert"
          style={{ width: '100%', padding: '0.85rem', marginBottom: '1.25rem', display: 'block', textAlign: 'left' }}
        >
          {successMsg}
        </div>
      )}

      {errorMsg && (
        <div
          className="badge badge-danger"
          id="auth-error-alert"
          style={{
            width: '100%',
            padding: '0.85rem',
            marginBottom: '1.25rem',
            display: 'block',
            textAlign: 'left',
            background: '#ffebee',
            color: '#c62828',
            border: '1px solid #ef9a9a',
          }}
        >
          {errorMsg}
        </div>
      )}

      {/* Active User Status Card */}
      {isAuthenticated && activeUser && (
        <div className="card-editorial" style={{ marginBottom: '1.75rem' }} id="active-session-card">
          <div className="card-header-editorial">
            <h3>Active Session Profile</h3>
            <span className={`badge ${activeUser.is_demo ? 'badge-neutral' : 'badge-success'}`}>
              {activeUser.is_demo ? 'Local Demo Persona' : 'Supabase Auth Verified'}
            </span>
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
                  <span
                    className={`badge ${
                      activeUser.role === 'approver' || activeUser.role === 'admin' ? 'badge-warning' : 'badge-info'
                    }`}
                  >
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

            <div
              style={{
                marginTop: '1.25rem',
                paddingTop: '1rem',
                borderTop: '1px solid var(--color-border)',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                flexWrap: 'wrap',
                gap: '0.75rem',
              }}
            >
              <div style={{ fontSize: '0.8rem', color: 'var(--color-text-secondary)' }}>
                Session:{' '}
                <span className="mono" style={{ fontSize: '0.72rem' }}>
                  {sessionToken ? `${sessionToken.slice(0, 16)}...` : activeUser.is_demo ? 'Local Demo Persona' : 'Active'}
                </span>
              </div>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <button
                  type="button"
                  onClick={() => navigate(returnUrl)}
                  className="btn btn-sm btn-primary"
                  id="auth-go-to-dashboard-btn"
                >
                  Proceed to Dashboard →
                </button>
                <button
                  type="button"
                  onClick={handleSignOut}
                  disabled={loading}
                  className="btn btn-sm btn-outline btn-logout"
                  id="auth-signout-btn"
                >
                  {loading ? 'Signing out...' : 'Sign Out'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Real Supabase Authentication Card */}
      <div className="card-editorial" style={{ marginBottom: '1.75rem' }} id="supabase-auth-card">
        <div className="card-header-editorial">
          <h3>Supabase Authentication</h3>
          <span className={`badge ${isConfigured ? 'badge-success' : 'badge-warning'}`}>
            {isConfigured ? 'Cloud Configured' : 'Offline / Unconfigured'}
          </span>
        </div>
        <div className="card-body-editorial">
          {!isConfigured ? (
            <div style={{ fontSize: '0.875rem', color: 'var(--color-text-secondary)' }}>
              <p style={{ marginBottom: '0.75rem' }}>
                Supabase URL or Publishable Key is not configured in this environment. To enable real cloud authentication:
              </p>
              <ol style={{ paddingLeft: '1.25rem', lineHeight: '1.6' }}>
                <li>
                  Set <code className="mono">VITE_SUPABASE_URL</code> and{' '}
                  <code className="mono">VITE_SUPABASE_PUBLISHABLE_KEY</code> in your environment.
                </li>
                <li>
                  Execute <code className="mono">supabase/schema.sql</code> in your Supabase project SQL Editor.
                </li>
              </ol>
              <p style={{ marginTop: '0.75rem' }}>
                You can continue evaluating ReStockIQ using the offline demo personas below.
              </p>
            </div>
          ) : (
            <div>
              {/* Tabs for Sign In vs Sign Up */}
              <div
                style={{
                  display: 'flex',
                  gap: '0.5rem',
                  marginBottom: '1.25rem',
                  borderBottom: '1px solid var(--color-border)',
                  paddingBottom: '0.5rem',
                }}
              >
                <button
                  type="button"
                  onClick={() => {
                    setAuthMode('signin');
                    setErrorMsg(null);
                  }}
                  className={`btn btn-sm ${authMode === 'signin' ? 'btn-primary' : 'btn-outline'}`}
                  id="tab-sign-in"
                >
                  Sign In
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setAuthMode('signup');
                    setErrorMsg(null);
                  }}
                  className={`btn btn-sm ${authMode === 'signup' ? 'btn-primary' : 'btn-outline'}`}
                  id="tab-sign-up"
                >
                  Create Account (Sign Up)
                </button>
              </div>

              <form onSubmit={handleSupabaseSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                <div>
                  <label
                    htmlFor="auth-email"
                    style={{
                      display: 'block',
                      fontSize: '0.8rem',
                      fontWeight: 700,
                      marginBottom: '0.25rem',
                      color: 'var(--color-text-secondary)',
                    }}
                  >
                    EMAIL ADDRESS
                  </label>
                  <input
                    id="auth-email"
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="user@example.com"
                    required
                    style={{
                      width: '100%',
                      padding: '0.65rem 0.85rem',
                      borderRadius: 'var(--radius-sm)',
                      border: '1px solid var(--color-border)',
                      fontSize: '0.9rem',
                    }}
                  />
                </div>

                <div>
                  <label
                    htmlFor="auth-password"
                    style={{
                      display: 'block',
                      fontSize: '0.8rem',
                      fontWeight: 700,
                      marginBottom: '0.25rem',
                      color: 'var(--color-text-secondary)',
                    }}
                  >
                    PASSWORD
                  </label>
                  <input
                    id="auth-password"
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••••••"
                    required
                    style={{
                      width: '100%',
                      padding: '0.65rem 0.85rem',
                      borderRadius: 'var(--radius-sm)',
                      border: '1px solid var(--color-border)',
                      fontSize: '0.9rem',
                    }}
                  />
                </div>

                {authMode === 'signup' && (
                  <div
                    style={{
                      fontSize: '0.78rem',
                      color: 'var(--color-text-secondary)',
                      background: 'var(--color-surface-elevated)',
                      padding: '0.75rem',
                      borderRadius: 'var(--radius-sm)',
                    }}
                  >
                    <strong>Role Governance Notice:</strong> Newly registered accounts are assigned the standard{' '}
                    <code className="mono">planner</code> role. Purchasing Approver authority (<code className="mono">approver</code>)
                    must be granted by an administrator via Supabase metadata.
                  </div>
                )}

                <button
                  type="submit"
                  disabled={loading}
                  className="btn btn-primary"
                  id="auth-submit-button"
                  style={{ alignSelf: 'flex-start', marginTop: '0.5rem' }}
                >
                  {loading
                    ? authMode === 'signin'
                      ? 'Authenticating...'
                      : 'Registering...'
                    : authMode === 'signin'
                    ? 'Sign In with Supabase'
                    : 'Create Planner Account'}
                </button>
              </form>
            </div>
          )}
        </div>
      </div>

      {/* Switch Demo Role (Offline Development / Testing Only) */}
      <div className="card-editorial" style={{ marginBottom: '1.75rem' }} id="local-testing-personas-card">
        <div className="card-header-editorial">
          <h3>Local Testing Personas (Offline / Development Only)</h3>
          <span className={`badge ${import.meta.env.PROD && isConfigured ? 'badge-warning' : 'badge-neutral'}`}>
            {import.meta.env.PROD && isConfigured ? 'Disabled in Production' : 'Offline Test Mode'}
          </span>
        </div>
        <div className="card-body-editorial">
          <p style={{ fontSize: '0.85rem', color: 'var(--color-text-secondary)', marginBottom: '1.25rem' }}>
            {import.meta.env.PROD && isConfigured
              ? 'Demo tokens are strictly rejected by the backend in production mode to protect live database integrity. To access the live system, please use the Supabase login/registration form above.'
              : 'In non-production environments, switch between these deterministic personas for offline evaluation:'}
          </p>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '1rem' }}>
            {DEMO_USERS.map((u) => {
              const isCurrent = activeUser?.is_demo && u.id === activeUser.id;
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
                    type="button"
                    onClick={() => handleSelectDemoPersona(u)}
                    disabled={Boolean(isCurrent)}
                    className={`btn btn-sm ${isCurrent ? 'btn-outline' : 'btn-primary'}`}
                    style={{ marginTop: '0.75rem' }}
                    id={`btn-select-persona-${u.role}`}
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
