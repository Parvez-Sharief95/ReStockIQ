# REQUIREMENTS.md — Inventory Reorder Planner

Traceability: every official requirement mapped to a screen, backend function or test.

---

## 1. Core Task Requirements

| # | Requirement | Screen / Component | Backend Function | Test |
|---|-------------|-------------------|-----------------|------|
| R1 | Collect inventory, sales history, lead time and budget | Screen 3: Inventory | `POST /api/inventory`, `GET /api/inventory` | TC1, TC2, TC3, TC4 |
| R2 | Retrieve inventory and supplier order evidence | Screen 4: Reorder Analysis | `source_adapter.fetch_inventory()`, `source_adapter.fetch_open_orders()` | Unit: source adapter mock |
| R3 | Forecast demand during lead time | Screen 4 | `engine.forecast_lead_time_demand()` | Unit: TC1–TC4; edge: zero demand |
| R4 | Subtract eligible incoming stock from requirement | Screen 4 | `engine.select_eligible_incoming()` | TC3; edge: late/cancelled orders |
| R5 | Check SKU, pack size and open orders | Screen 4 | `engine.validate_inputs()`, `engine.round_to_pack_size()` | TC2; edge: MOQ |
| R6 | Prepare reorder requests for human approval | Screen 5: Approval Queue | `POST /api/requests` | Unit: request lifecycle |
| R7 | Require human approval before consequential action | Screen 5 | Approval gate middleware | Unit: approval gating |
| R8 | Verify the result after submission | Screen 6: Request Detail | `POST /api/requests/{id}/verify` | Unit: verification mismatch |
| R9 | Show stockout forecasts | Screen 2: Dashboard | `GET /api/dashboard/stockout-risks` | TC1 |
| R10 | Show proposed quantities | Screen 4, Screen 6 | `GET /api/analyses/{id}` | TC1, TC2, TC3 |
| R11 | Show request IDs | Screen 6 | All request endpoints | Unit: idempotency |

---

## 2. Calculation Rules

| # | Rule | Backend Function | Test |
|---|------|-----------------|------|
| C1 | Lead-time demand = avg daily demand × lead time days | `engine.forecast_lead_time_demand()` | Unit: various demand/lead-time combos |
| C2 | Eligible incoming: confirmed/open, arrival within window, no double-count | `engine.select_eligible_incoming()` | TC3; edge: partially received |
| C3 | Net shortfall = max(0, lead_time_demand + safety_stock - stock - eligible_incoming) | `engine.compute_net_shortfall()` | TC1, TC3; edge: zero shortfall |
| C4 | Safety stock defaults to 0 if not configured; disclosed in evidence | `engine.compute_net_shortfall()` | Unit: missing safety stock |
| C5 | Order units = pack_size × ceil(shortfall / pack_size) for case-only suppliers | `engine.round_to_pack_size()` | TC2 |
| C6 | Estimated cost = proposed_units × unit_price | `engine.calculate_cost()` | TC1, TC2 |
| C7 | Budget check before marking ready | `engine.check_budget()` | TC4 |
| C8 | 20% price increase → recalculate cost, request budget review | `engine.check_budget()` | TC4 |
| C9 | Negative quantities not allowed; zero shortfall = no reorder proposed | `engine.validate_inputs()` | Unit: negative/zero cases |
| C10 | Return `needs_review`/`insufficient_data` if required input is missing | `engine.validate_inputs()` | Unit: missing fields |

---

## 3. Request Lifecycle

| State | Transitions | Backend | Test |
|-------|------------|---------|------|
| `draft` | → `pending_approval` | `POST /api/requests` | Unit: lifecycle |
| `pending_approval` | → `approved` or `rejected` | `POST /api/requests/{id}/approve` | Unit: approval gate |
| `approved` | → `submitted_or_simulated` | `POST /api/requests/{id}/submit` | Unit: duplicate prevention |
| `submitted_or_simulated` | → `verified` or `failed` | `POST /api/requests/{id}/verify` | Unit: verification |
| Any | → `needs_review` | Triggered by validation | Unit: re-approval on change |
| Any | → `failed` | Triggered by error | Unit: failed state visible |

---

## 4. Safety & Idempotency

| # | Requirement | Backend | Test |
|---|-------------|---------|------|
| S1 | Stable idempotency key per request version | DB unique constraint on `idempotency_key` | Unit: duplicate submission |
| S2 | Re-approval required if proposal changes after approval | Version invalidation logic | Unit: version invalidation |
| S3 | Append-only audit log | `audit_events` table | Unit: audit event sequence |
| S4 | No real purchase submission without explicit authorization | Simulated mode default | Unit: mock order ID returned |
| S5 | Prompt injection in source data treated as data only | Source adapter validation | Manual review |

---

## 5. UI Screens → Backend Endpoints

| Screen | Route | Backend Endpoints |
|--------|-------|------------------|
| 1. Sign In / Sign Up | `/auth` | Supabase Auth (client-side) |
| 2. Dashboard | `/` | `GET /api/dashboard` |
| 3. Inventory | `/inventory` | `GET /api/inventory`, `GET /api/inventory/{id}` |
| 4. Reorder Analysis | `/analysis/{id}` | `GET /api/analyses/{id}`, `POST /api/analyses` |
| 5. Approval Queue | `/approvals` | `GET /api/requests?status=pending_approval`, `POST /api/requests/{id}/approve` |
| 6. Request Detail/History | `/requests/{id}` | `GET /api/requests/{id}`, `GET /api/requests/{id}/audit` |
| 7. Test Scenarios | `/test-scenarios` | `GET /api/test-runs`, `POST /api/test-runs/run` |

---

## 6. Test Scenario Specifications

| Case | Input | Expected | Test Location |
|------|-------|----------|---------------|
| TC1 | Low stock, no incoming order, 30-day sales=60 units, lead time=14d | Proposes reorder of shortfall qty (deterministic) | `tests/backend/test_tc1.py` |
| TC2 | Same as TC1 but supplier sells in cases of 12 | Proposed qty rounded up to nearest multiple of 12 | `tests/backend/test_tc2.py` |
| TC3 | Same as TC1 but confirmed incoming order covers 50% of shortfall | Reorder reduced by eligible incoming; no duplicate if fully covered | `tests/backend/test_tc3.py` |
| TC4 | TC1 scenario but supplier price increases 20% | Cost recalculated; budget review requested; price change visible | `tests/backend/test_tc4.py` |

---

## 7. Non-Functional

| # | Requirement | Implementation |
|---|-------------|----------------|
| NF1 | No paid services | Stack verified in Phase 0 |
| NF2 | Secrets excluded from VCS and frontend bundles | `.gitignore`, `.env.example`, backend-only keys |
| NF3 | Deterministic calculations — LLM not used for arithmetic | `calculation_engine.py` pure Python |
| NF4 | Mock mode when Gemini unavailable | `fallback_mode` in agent orchestration |
| NF5 | Responsive layout, keyboard accessible | CSS + React, Phase 7 |
| NF6 | Source evidence and timestamps stored | `source_evidence` table + Pydantic model |
