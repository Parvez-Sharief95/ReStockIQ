import React from 'react';

export const GuardrailsCard: React.FC = () => {
  return (
    <section className="guardrails-banner" aria-labelledby="guardrails-heading">
      <div className="guardrails-title" id="guardrails-heading">
        <span>🛡️</span>
        <span>Operational Governance &amp; Deterministic Guardrails</span>
      </div>
      <div className="guardrails-grid">
        <div className="guardrail-item">
          <h4>
            <span>⚙️</span> Zero LLM Arithmetic
          </h4>
          <p>
            Reorder shortfall, pack rounding, and cost calculations are 100% computed by pure Python / deterministic rules (C1–C10). LLMs are strictly forbidden from performing inventory arithmetic.
          </p>
        </div>

        <div className="guardrail-item">
          <h4>
            <span>⚖️</span> Mandatory Human Gate
          </h4>
          <p>
            The system cannot self-approve or transmit orders to suppliers. Human approval tied to the exact proposal version is an immutable prerequisite for order execution.
          </p>
        </div>

        <div className="guardrail-item">
          <h4>
            <span>🔒</span> Rule S2 &amp; Idempotency
          </h4>
          <p>
            Modifying a proposal after approval immediately invalidates that approval and increments the version. SHA-256 idempotency protects against duplicate retry storms.
          </p>
        </div>

        <div className="guardrail-item">
          <h4>
            <span>🔍</span> Outcome Verification
          </h4>
          <p>
            Actual supplier outcomes are independently compared against intended SKU, pack count, and delivery terms before a request can transition to verified.
          </p>
        </div>
      </div>
    </section>
  );
};
