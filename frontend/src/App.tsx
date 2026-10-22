import { BrowserRouter, Routes, Route } from 'react-router-dom';

/**
 * App root — routes are stubbed here and implemented in Phase 7.
 * Each route corresponds to a main screen from the playbook.
 */
function App() {
  return (
    <BrowserRouter>
      <div className="app-shell">
        <Routes>
          {/* Screen 1: Auth */}
          <Route path="/auth" element={<Placeholder label="Sign In / Sign Up" />} />
          {/* Screen 2: Dashboard */}
          <Route path="/" element={<Placeholder label="Dashboard — Stockout Risks & Pending Approvals" />} />
          {/* Screen 3: Inventory */}
          <Route path="/inventory" element={<Placeholder label="Inventory — SKUs, Stock, Suppliers" />} />
          {/* Screen 4: Reorder Analysis */}
          <Route path="/analysis/:id" element={<Placeholder label="Reorder Analysis — Forecast & Evidence" />} />
          {/* Screen 5: Approval Queue */}
          <Route path="/approvals" element={<Placeholder label="Approval Queue" />} />
          {/* Screen 6: Request Detail / History */}
          <Route path="/requests/:id" element={<Placeholder label="Request Detail & Audit History" />} />
          {/* Screen 7: TC1–TC4 Test Scenarios */}
          <Route path="/test-scenarios" element={<Placeholder label="Test Scenarios — TC1 to TC4" />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}

function Placeholder({ label }: { label: string }) {
  return (
    <div className="page-placeholder">
      <span>🏗 <strong>{label}</strong> — implemented in Phase 7</span>
    </div>
  );
}

export default App;
