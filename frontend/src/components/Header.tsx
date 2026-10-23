import React, { useState, useEffect } from 'react';
import { NavLink, Link } from 'react-router-dom';
import { getCurrentUser, setCurrentUser, DEMO_USERS, dataService, DemoUser } from '../services/dataService';

export const Header: React.FC = () => {
  const [user, setUser] = useState<DemoUser>(getCurrentUser());
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

  const handleUserToggle = () => {
    const nextUser = user.role === 'planner' ? DEMO_USERS[1] : DEMO_USERS[0];
    setCurrentUser(nextUser);
    setUser(nextUser);
  };

  return (
    <header className="header-editorial" role="banner">
      <div className="header-inner">
        <Link to="/" className="brand-section">
          <div className="brand-symbol">IRP</div>
          <div>
            <h1 className="brand-title">Inventory Reorder Planner</h1>
            <div className="brand-subtitle">Autonomous Analysis &bull; Human Governance</div>
          </div>
        </Link>

        <nav className="nav-links" aria-label="Main Navigation">
          <NavLink to="/" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`} end>
            <span>📊</span> Dashboard
          </NavLink>
          <NavLink to="/inventory" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
            <span>📦</span> SKU Inventory
          </NavLink>
          <NavLink to="/approvals" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
            <span>⚖️</span> Approval Queue
            {pendingCount > 0 && <span className="nav-badge">{pendingCount}</span>}
          </NavLink>
          <NavLink to="/requests" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
            <span>📜</span> Requests &amp; Audits
          </NavLink>
          <NavLink to="/test-scenarios" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
            <span>🧪</span> Scenarios (TC1–TC4)
          </NavLink>
        </nav>

        <div className="header-user-status">
          <button
            onClick={handleUserToggle}
            className="user-role-badge"
            title="Click to toggle between Planner and Approver roles"
            style={{ cursor: 'pointer', background: 'rgba(255,255,255,0.1)' }}
          >
            <span className="user-role-dot" />
            <span>{user.name}</span>
            <span style={{ opacity: 0.6, fontSize: '0.7rem' }}>⇄ Switch</span>
          </button>
        </div>
      </div>
    </header>
  );
};
