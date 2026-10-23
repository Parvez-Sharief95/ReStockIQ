import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { dataService, apiClient, ApiError } from '../services/dataService';
import { TestCaseId, TestRun } from '../types';

export const ScenarioRunnerPage: React.FC = () => {
  const [testResults, setTestResults] = useState<Record<TestCaseId, TestRun | null>>({
    TC1: null,
    TC2: null,
    TC3: null,
    TC4: null,
  });
  const [runningCases, setRunningCases] = useState<Record<TestCaseId, boolean>>({
    TC1: false,
    TC2: false,
    TC3: false,
    TC4: false,
  });
  const [isRunningAll, setIsRunningAll] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [backendExecution, setBackendExecution] = useState<boolean | null>(null);

  const handleRunTestCase = async (caseId: TestCaseId) => {
    setRunningCases((prev) => ({ ...prev, [caseId]: true }));
    setErrorMessage(null);

    try {
      // Attempt live FastAPI backend execution first
      const res = await apiClient.runTestCase(caseId);
      setTestResults((prev) => ({ ...prev, [caseId]: res.test_run }));
      setBackendExecution(true);
    } catch (err: unknown) {
      if (err instanceof ApiError && err.code === 'NETWORK_ERROR') {
        // Local deterministic fallback when backend offline
        const localRes = dataService.runTestCase(caseId);
        setTestResults((prev) => ({ ...prev, [caseId]: localRes }));
        setBackendExecution(false);
      } else {
        const msg = err instanceof Error ? err.message : 'Unknown execution error';
        setErrorMessage(`Execution of ${caseId} failed: ${msg}`);
      }
    } finally {
      setRunningCases((prev) => ({ ...prev, [caseId]: false }));
    }
  };

  const handleRunAll = async () => {
    setIsRunningAll(true);
    setErrorMessage(null);

    try {
      const res = await apiClient.runAllTestCases();
      const newResults: Record<TestCaseId, TestRun | null> = { TC1: null, TC2: null, TC3: null, TC4: null };
      res.runs.forEach((r) => {
        newResults[r.case_id] = r;
      });
      setTestResults(newResults);
      setBackendExecution(true);
    } catch (err: unknown) {
      if (err instanceof ApiError && err.code === 'NETWORK_ERROR') {
        const tcIds: TestCaseId[] = ['TC1', 'TC2', 'TC3', 'TC4'];
        const newResults: Record<TestCaseId, TestRun | null> = { TC1: null, TC2: null, TC3: null, TC4: null };
        tcIds.forEach((id) => {
          newResults[id] = dataService.runTestCase(id);
        });
        setTestResults(newResults);
        setBackendExecution(false);
      } else {
        const msg = err instanceof Error ? err.message : 'Unknown execution error';
        setErrorMessage(`Execution failed: ${msg}`);
      }
    } finally {
      setIsRunningAll(false);
    }
  };

  const scenarios: {
    id: TestCaseId;
    sku: string;
    title: string;
    description: string;
    rule: string;
  }[] = [
    {
      id: 'TC1',
      sku: 'SKU-001',
      title: 'Standard Reorder Shortfall (Low Stock)',
      description: 'Stock = 20, Lead-Time Demand = 56, No open orders. Net Shortfall = 36.',
      rule: 'Rules C1, C3, C4: Shortfall formula max(0, LTD + Safety - Stock - Incoming)',
    },
    {
      id: 'TC2',
      sku: 'SKU-002',
      title: 'Case-Packaging / Pack-Size Rounding',
      description: 'Pack size = 12 units/case, Shortfall = 31 units. Rounded up to 3 cases (36 units).',
      rule: 'Rule C5: Pack size rounding pack_size * ceil(shortfall / pack_size)',
    },
    {
      id: 'TC3',
      sku: 'SKU-003',
      title: 'Incoming Purchase Order Covers Shortfall',
      description: 'Stock = 20, LTD = 56, Confirmed PO for 24 units arriving in 10 days. Net Shortfall = 12.',
      rule: 'Rule C2: Eligible incoming stock arriving within lead-time window; prevents double-ordering',
    },
    {
      id: 'TC4',
      sku: 'SKU-004',
      title: '20% Price Hike & Budget Overrun Review',
      description: 'Price raised from $10 to $12 (+20%), Budget = $400. Cost = $432 > $400. Status = needs_review.',
      rule: 'Rules C7, C8: Budget limit enforcement & 20% price increase flagging; requires human approval',
    },
  ];

  return (
    <div className="fade-in">
      <div className="editorial-header">
        <div className="editorial-header-text">
          <h1>Deterministic Test Scenario Harness (TC1–TC4)</h1>
          <p>
            Interactive execution of official hackathon acceptance scenarios through the FastAPI backend and deterministic Python calculation engine.
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          {backendExecution !== null && (
            <span
              className="badge"
              style={{
                background: backendExecution ? 'var(--color-lifted-silver)' : '#FFF3CD',
                color: backendExecution ? 'var(--color-deep-aubergine)' : '#856404',
                border: '1px solid var(--color-border)',
                padding: '0.4rem 0.75rem',
                fontSize: '0.75rem',
              }}
            >
              {backendExecution ? '⚡ FastAPI REST Engine' : '🧪 Client Deterministic Engine'}
            </span>
          )}
          <button onClick={handleRunAll} disabled={isRunningAll} className="btn btn-accent">
            <span>⚡</span> {isRunningAll ? 'Running Scenarios...' : 'Run All Scenarios'}
          </button>
        </div>
      </div>

      {errorMessage && (
        <div
          className="card-editorial"
          style={{
            borderColor: 'var(--color-danger)',
            background: 'rgba(217, 83, 79, 0.08)',
            marginBottom: '1.5rem',
            padding: '1rem',
          }}
        >
          <div style={{ color: 'var(--color-danger)', fontWeight: 700 }}>⚠️ {errorMessage}</div>
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
        {scenarios.map((sc) => {
          const result = testResults[sc.id];
          const isCaseRunning = runningCases[sc.id];

          return (
            <div key={sc.id} className="card-editorial">
              <div className="card-header-editorial">
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                  <span
                    className="mono"
                    style={{
                      fontSize: '1.1rem',
                      fontWeight: 800,
                      color: 'var(--color-marigold)',
                      background: 'var(--color-deepest-aubergine)',
                      padding: '0.2rem 0.6rem',
                      borderRadius: '4px',
                    }}
                  >
                    {sc.id}
                  </span>
                  <div>
                    <h3 style={{ fontSize: '1rem', margin: 0 }}>{sc.title}</h3>
                    <span className="mono text-muted" style={{ fontSize: '0.75rem' }}>
                      Target: {sc.sku} &bull; {sc.rule}
                    </span>
                  </div>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                  {result && (
                    <span
                      className={`badge ${result.status === 'pass' ? 'badge-success' : 'badge-danger'}`}
                      style={{ fontSize: '0.8rem', padding: '0.3rem 0.8rem' }}
                    >
                      {result.status === 'pass' ? '✅ PASSED' : '❌ FAILED'}
                    </span>
                  )}
                  <button
                    onClick={() => handleRunTestCase(sc.id)}
                    disabled={isCaseRunning || isRunningAll}
                    className="btn btn-sm btn-primary"
                  >
                    {isCaseRunning ? 'Evaluating...' : `Run ${sc.id}`}
                  </button>
                  <Link to={`/analysis/${sc.sku}`} className="btn btn-sm btn-outline">
                    View &rarr;
                  </Link>
                </div>
              </div>

              <div className="card-body-editorial">
                <p style={{ fontSize: '0.85rem', color: 'var(--color-text-secondary)', marginBottom: '1rem' }}>
                  {sc.description}
                </p>

                {result ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1rem' }}>
                      {/* Expected Values */}
                      <div
                        style={{
                          background: 'var(--color-lifted-silver)',
                          padding: '0.85rem',
                          borderRadius: 'var(--radius-md)',
                          border: '1px solid var(--color-border-light)',
                        }}
                      >
                        <div
                          style={{
                            fontSize: '0.75rem',
                            fontWeight: 700,
                            color: 'var(--color-text-secondary)',
                            textTransform: 'uppercase',
                            marginBottom: '0.4rem',
                          }}
                        >
                          Expected Benchmark Results
                        </div>
                        <pre className="mono" style={{ fontSize: '0.78rem', margin: 0, whiteSpace: 'pre-wrap' }}>
                          {JSON.stringify(result.expected_result, null, 2)}
                        </pre>
                      </div>

                      {/* Actual Evaluated Values */}
                      <div
                        style={{
                          background: 'var(--color-lifted-silver)',
                          padding: '0.85rem',
                          borderRadius: 'var(--radius-md)',
                          border: '1px solid var(--color-border-light)',
                        }}
                      >
                        <div
                          style={{
                            fontSize: '0.75rem',
                            fontWeight: 700,
                            color: 'var(--color-text-secondary)',
                            textTransform: 'uppercase',
                            marginBottom: '0.4rem',
                          }}
                        >
                          Actual Engine Outputs
                        </div>
                        <pre className="mono" style={{ fontSize: '0.78rem', margin: 0, whiteSpace: 'pre-wrap' }}>
                          {JSON.stringify(result.actual_result, null, 2)}
                        </pre>
                      </div>
                    </div>

                    {result.evidence && (
                      <div
                        style={{
                          background: 'var(--color-deepest-aubergine)',
                          color: 'var(--color-ice-silver)',
                          padding: '0.75rem 1rem',
                          borderRadius: 'var(--radius-sm)',
                          fontSize: '0.78rem',
                        }}
                      >
                        <strong style={{ color: 'var(--color-marigold)' }}>Evidence Provenance: </strong>
                        {result.evidence}
                      </div>
                    )}
                  </div>
                ) : (
                  <div
                    style={{
                      padding: '1.25rem',
                      textAlign: 'center',
                      background: 'var(--color-surface-hover)',
                      borderRadius: 'var(--radius-md)',
                      border: '1px dashed var(--color-border)',
                      fontSize: '0.85rem',
                      color: 'var(--color-text-muted)',
                    }}
                  >
                    Scenario pending execution. Click <strong>Run {sc.id}</strong> to evaluate through the deterministic calculation engine.
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
