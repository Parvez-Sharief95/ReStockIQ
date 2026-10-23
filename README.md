# ReStockIQ — Autonomous Reorder Intelligence

> **Autonomous Reorder Intelligence**

Predict stockouts and prepare explainable purchase requests with deterministic precision, human governance, and zero over-ordering.

---

## Purpose

ReStockIQ collects inventory, sales history, lead time and budget data; forecasts demand during the lead-time window; subtracts eligible incoming stock; prepares reorder requests with mandatory human approval gates; simulates safe order execution; independently verifies results; and surfaces stockout risks in an accessible business dashboard.

---

## Architecture

```
frontend/          React 18 + Vite 5 + TypeScript (ReStockIQ UI) → Vercel (Hobby target)
backend/           Python 3.13 + FastAPI                         → Free-tier host / local demo
supabase/          PostgreSQL 12-table schema                    → Supabase Free tier (optional live sync)
```

**AI Strategy:** Gemini API (free tier) — bounded tool calling for workflow orchestration and human-auditable explanations only. **All arithmetic calculations are strictly pure, deterministic Python with Decimal precision.**

---

## Quick Start (Local)

### Prerequisites
- Python 3.11+ (Python 3.13.1 confirmed)
- Node.js 18+ (Node.js v22.14.0 confirmed)
- npm 10+ (npm 11.1.0 confirmed)

### 1. Configure Environment

```bash
cp .env.example .env
# Optional: fill in live Supabase or Gemini keys.
# The application operates 100% offline in deterministic synthetic demo mode when keys are omitted.
```

### 2. Backend (FastAPI)

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows PowerShell / cmd
# source .venv/bin/activate     # macOS/Linux
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000
```

- API Base URL: `http://localhost:8000`
- Interactive OpenAPI Docs: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/api/health`

### 3. Frontend (React + Vite)

```bash
cd frontend
npm install
npm run dev
```

- Web UI: `http://localhost:5173`
- Vite proxies `/api` calls directly to `http://localhost:8000`.

---

## Testing & Verification

### Run Backend Test Suite (118 Tests)

```bash
# From workspace root
backend\.venv\Scripts\pytest
```

- **Test Suite Result:** 118 passed in 2.78s
- **Coverage:**
  - `test_persistence_and_auth.py`: Safe role-assignment boundaries, live Supabase JWT verification, invalid/expired token rejection (401), production in-memory fallback prohibition (503), user-scoped JWT forwarding to PostgREST for RLS, and persistent repository idempotency
  - `test_acceptance_scenarios.py`: TC1, TC2, TC3, TC4 end-to-end scenarios + partial open order case + test-run runner endpoints
  - `test_api_integration.py`: Complete REST endpoints, error serialization, and Rule S2 proposal invalidation
  - `test_safety_and_failures.py`: Human approval gating, version integrity, anti-invention guard on failed source data, duplicate retries, secrets exclusion, 401 unauthenticated, 403 forbidden roles, 422 caller-supplied ID rejection, 200 approver identity binding, production demo token disabling
  - `test_decision_engine.py`: Pure arithmetic rules C1–C10, pack-size rounding, safety stock defaulting, budget checking
  - `test_source_adapter.py`: Mock source adapter, evidence provenance capture, staleness (>7d), and conflict detection
  - `test_request_service.py`: Request lifecycle, version snapshots, simulated order execution, outcome verification
  - `test_agent_orchestrator.py`: Bounded Gemini function calling, deterministic offline fallback, prompt injection defense
  - `test_scaffold.py`: Scaffold, Pydantic settings frontend variable filtering, and misspelled key validation

### Run Frontend Vitest Suite (22 Tests)

```bash
cd frontend
npm test -- --run
```

- **Test Suite Result:** 22 passed in 54ms
- **Coverage:** Supabase Auth client operations, safe default role assignment, session restoration, client data service calculation rules, approval invalidation, outcome verification, typed `apiClient` error parsing, and dynamic auth header injection.

### Run Frontend Typecheck & Build

```bash
cd frontend
npm run build
```

- **Build Result:** Clean production bundle built with `tsc && vite build` in 2.23s (zero TypeScript or bundling errors).

---

## Official Acceptance Test Scenarios (TC1–TC4)

| Case | Scenario | Expected Result | Status |
|------|----------|-----------------|--------|
| **TC1** | Low stock, no incoming order | Net shortfall = 36 units. Proposes 36 units ($360.00). Request created, approved, simulated (`SIM-PO-...`), and verified. | ✅ PASS |
| **TC2** | Supplier sells in cases of 12 | Net shortfall = 31 units. Pack rounding rounds up to 3 cases (36 units). Pack divisibility verified. | ✅ PASS |
| **TC3** | Pending order exists | Confirmed order of 24 units arriving in 10d. Shortfall reduced from 36 to 12. Double-ordering prevented. | ✅ PASS |
| **TC4** | Supplier price increases by 20% | Price rises from $10 to $12. Cost ($432.00) exceeds budget ($400.00). Status = `needs_review`. Approval cannot be bypassed. | ✅ PASS |
| **Edge** | Partial open order (Rule 5) | Demand = 100, Stock = 20, Open PO = 30. Shortfall = 50. Shortage legitimately proposed and not suppressed. | ✅ PASS |

---

## Environment Variables

See [`.env.example`](./.env.example) for placeholder definitions. **Never commit real credentials to version control.**

| Variable | Where used | Visibility | Purpose |
|----------|------------|------------|---------|
| `APP_ENV` | Backend | Server only | `development` or `production` |
| `SUPABASE_URL` | Backend / Frontend | Server & Client | Supabase PostgreSQL project URL |
| `SUPABASE_SECRET_KEY` | Backend only | Server only | Service-role admin access (bypasses RLS for migrations/cleanup) |
| `GEMINI_API_KEY` | Backend only | Server only | Gemini API key for bounded orchestration/explanations |
| `CORS_ORIGINS` | Backend | Server only | Comma-separated allowed origins (e.g. `http://localhost:5173`) |
| `VITE_SUPABASE_URL` | Frontend | Browser bundle | Supabase project URL |
| `VITE_SUPABASE_PUBLISHABLE_KEY` | Frontend | Browser bundle | Supabase anon key for client-side Auth |
| `VITE_API_BASE_URL` | Frontend | Browser bundle | FastAPI base URL (defaults to `/api` proxy in dev) |

---

## Design System & Palette

- **Deep Aubergine (`#3A0F34`)**: Primary brand, navigation headers, titles, primary buttons.
- **Ice Silver (`#DDE3E8`)**: Page background, container surfaces, subtle dividing borders.
- **Marigold (`#EAAA00`)**: Cautionary highlights, approval emphasis, budget alerts, and key metric badges.

---

## Safety & Governance Principles

1. **Deterministic Calculations Only:** Arithmetic is never performed by an LLM.
2. **Mandatory Human Approval Gating:** Submissions without explicit human approval are blocked at the API layer (HTTP 403).
3. **Rule S2 Approval Invalidation:** Any change to proposal parameters after approval forces status back to `pending_approval` and increments the immutable version.
4. **Anti-Invention Guard:** Source retrieval failures never default to 0 stock or 0 open orders. Requests cannot be created from insufficient evidence.
5. **Separate Verification:** Outcome verification operates independently from submission, asserting SKU, quantity, pack size, and duplicate PO absence.
6. **Simulated Execution Default:** Real supplier procurement endpoints are isolated; safe mock reference tokens (`SIM-PO-...`) are emitted.
7. **Append-Only Audit Trail:** All lifecycle events (`proposed`, `approved`, `rejected`, `submitted`, `retry`, `version_invalidated`, `verified`, `failed`) are logged immutably.
