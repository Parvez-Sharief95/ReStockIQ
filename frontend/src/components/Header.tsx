import React, { useState, useEffect } from 'react';
import { NavLink, Link, useNavigate } from 'react-router-dom';
import { dataService } from '../services/dataService';
import { ReStockIQLogo } from './ReStockIQLogo';
import { useAuth } from '../context/useAuth';

export const Header: React.FC = () => {
  const { user, isAuthenticated, signOut, toggleDemoRole } = useAuth();
  const navigate = useNavigate();
  const [pendingCount, setPendingCount] = useState<number>(0);

  useEffect(() => {
    const updateStats = () => {
      const requests = dataService.getRequests();
      const pending = requests.filter((r) => r.status === 'pending_approval').length;
      setPendingCount(pending);
    };

    updateStats();
    const interval = setInterval(updateStats, 1000);
    return () => clearInterval(interval);
  }, []);

  const handleSignOut = async () => {
    await signOut();
    navigate('/auth');
  };

  return (
    <header className="header-editorial" role="banner">
      <div className="header-inner">
        <Link to="/" className="brand-section" aria-label="ReStockIQ Home">
          <ReStockIQLogo size={36} />
          <div>
            <h1 className="brand-title">
              ReStock<span className="brand-accent">IQ</span>
            </h1>
            <div className="brand-subtitle">Autonomous Reorder Intelligence</div>
          </div>
        </Link>

        <nav className="nav-links" aria-label="Main Navigation">
          <NavLink to="/" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`} end>
            Dashboard
          </NavLink>
          <NavLink to="/inventory" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
            SKU Inventory
          </NavLink>
          <NavLink to="/approvals" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
            Approval Queue
            {pendingCount > 0 && <span className="nav-badge">{pendingCount}</span>}
          </NavLink>
          <NavLink to="/requests" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
            Requests &amp; Audits
          </NavLink>
          <NavLink to="/test-scenarios" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
            Scenarios (TC1–TC4)
          </NavLink>
          <NavLink to="/auth" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
            Auth &amp; Access
          </NavLink>
        </nav>

        <div className="header-user-status">
          {isAuthenticated && user ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
              {user.is_demo ? (
                <button
                  onClick={toggleDemoRole}
                  className="user-role-badge"
                  title="Click to toggle between Planner and Approver roles"
                  style={{ cursor: 'pointer', background: 'rgba(255,255,255,0.1)' }}
                  id="header-demo-role-toggle"
                >
                  <span className="user-role-dot" />
                  <span>{user.name}</span>
                  <span style={{ opacity: 0.6, fontSize: '0.7rem' }}>Switch Role</span>
                </button>
              ) : (
                <Link
                  to="/auth"
                  className="user-role-badge"
                  title="Supabase Auth Verified Profile"
                  style={{ textDecoration: 'none', background: 'rgba(255,255,255,0.1)' }}
                  id="header-user-profile-link"
                >
                  <span className="user-role-dot" style={{ background: '#4caf50' }} />
                  <span>{user.name || user.email}</span>
                  <span
                    className="badge badge-warning"
                    style={{ fontSize: '0.65rem', padding: '2px 6px', textTransform: 'uppercase' }}
                  >
                    {user.role}
                  </span>
                </Link>
              )}

              <button
                onClick={handleSignOut}
                className="btn btn-sm btn-outline btn-logout"
                title="Sign out of ReStockIQ"
                id="header-logout-button"
                style={{
                  padding: '0.35rem 0.75rem',
                  fontSize: '0.8rem',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '0.35rem',
                  cursor: 'pointer',
                  color: 'var(--color-marigold, #ffb300)',
                  borderColor: 'rgba(255,255,255,0.25)',
                }}
              >
                Sign Out
              </button>
            </div>
          ) : (
            <Link
              to="/auth"
              className="btn btn-sm btn-primary btn-signin"
              title="Sign in or register"
              id="header-login-link"
              style={{
                padding: '0.4rem 0.9rem',
                fontSize: '0.85rem',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.4rem',
                fontWeight: 600,
                textDecoration: 'none',
              }}
            >
              Sign In
            </Link>
          )}
        </div>
      </div>
    </header>
  );
};
