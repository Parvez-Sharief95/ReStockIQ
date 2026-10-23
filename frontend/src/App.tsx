import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Header } from './components/Header';
import { SyntheticBanner } from './components/SyntheticBanner';
import { DashboardPage } from './pages/DashboardPage';
import { InventoryPage } from './pages/InventoryPage';
import { AnalysisView } from './pages/AnalysisView';
import { ApprovalsQueuePage } from './pages/ApprovalsQueuePage';
import { RequestDetailPage } from './pages/RequestDetailPage';
import { ScenarioRunnerPage } from './pages/ScenarioRunnerPage';
import { AuthPage } from './pages/AuthPage';

export const App: React.FC = () => {
  return (
    <BrowserRouter>
      <div className="app-shell">
        <Header />
        <SyntheticBanner />
        <main className="main-viewport" role="main">
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/inventory" element={<InventoryPage />} />
            <Route path="/analysis/:sku" element={<AnalysisView />} />
            <Route path="/analysis" element={<Navigate to="/inventory" replace />} />
            <Route path="/approvals" element={<ApprovalsQueuePage />} />
            <Route path="/requests" element={<ApprovalsQueuePage />} />
            <Route path="/requests/:id" element={<RequestDetailPage />} />
            <Route path="/test-scenarios" element={<ScenarioRunnerPage />} />
            <Route path="/auth" element={<AuthPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
};

export default App;
