import React from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { Header } from './components/Header';
import { SyntheticBanner } from './components/SyntheticBanner';
import { DashboardPage } from './pages/DashboardPage';
import { InventoryPage } from './pages/InventoryPage';
import { AnalysisView } from './pages/AnalysisView';
import { ApprovalsQueuePage } from './pages/ApprovalsQueuePage';
import { RequestDetailPage } from './pages/RequestDetailPage';
import { ScenarioRunnerPage } from './pages/ScenarioRunnerPage';
import { AuthPage } from './pages/AuthPage';
import { AuthProvider } from './context/AuthContext';
import { useAuth } from './context/useAuth';
import { ReStockIQLogo } from './components/ReStockIQLogo';

export const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isAuthenticated, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          minHeight: '60vh',
          gap: '1rem',
        }}
        id="app-auth-loading-spinner"
      >
        <ReStockIQLogo size={44} />
        <div style={{ color: 'var(--color-text-secondary)', fontSize: '0.9rem', fontWeight: 600 }}>
          Verifying security session...
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/auth" state={{ from: location }} replace />;
  }

  return <>{children}</>;
};

export const AppRoutes: React.FC = () => {
  return (
    <div className="app-shell">
      <Header />
      <SyntheticBanner />
      <main className="main-viewport" role="main">
        <Routes>
          <Route path="/auth" element={<AuthPage />} />
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <DashboardPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/inventory"
            element={
              <ProtectedRoute>
                <InventoryPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/analysis/:sku"
            element={
              <ProtectedRoute>
                <AnalysisView />
              </ProtectedRoute>
            }
          />
          <Route path="/analysis" element={<Navigate to="/inventory" replace />} />
          <Route
            path="/approvals"
            element={
              <ProtectedRoute>
                <ApprovalsQueuePage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/requests"
            element={
              <ProtectedRoute>
                <ApprovalsQueuePage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/requests/:id"
            element={
              <ProtectedRoute>
                <RequestDetailPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/test-scenarios"
            element={
              <ProtectedRoute>
                <ScenarioRunnerPage />
              </ProtectedRoute>
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
};

export const App: React.FC = () => {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  );
};

export default App;
