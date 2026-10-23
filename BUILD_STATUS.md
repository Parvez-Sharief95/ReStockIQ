# BUILD_STATUS.md — Inventory Reorder Planner

## Current Phase: PHASE 8 COMPLETE — Awaiting approval for Phase 9

---

## Phase Status

| Phase | Name | Status | Notes |
|-------|------|--------|-------|
| 0 | Workspace & Free-Tier Preflight | ✅ Complete | See Phase 0 report |
| 1 | Requirements, Data Contracts & Scaffold | ✅ Complete | See Phase 1 report |
| 2 | Supabase Schema, Auth & Access Control | ✅ Complete + reviewed | See Phase 2 report + review fixes |
| 3 | Deterministic Inventory Decision Engine | ✅ Complete | See Phase 3 report (42 unit tests passed) |
| 4 | Source Retrieval & Evidence | ✅ Complete | See Phase 4 report (54 unit tests passed) |
| 5 | Reorder Requests, Approval, Idempotency & Verification | ✅ Complete | See Phase 5 report (68 unit tests passed) |
| 6 | Gemini Tool Use & Agent Orchestration | ✅ Complete | See Phase 6 report (81 unit tests passed) |
| 7 | React Frontend & User Experience | ✅ Complete | See Phase 7 report (9 Vitest tests passed; bundle built) |
| 8 | API Integration & Hardening (ReStockIQ) | ✅ Complete + hardened | See Phase 8 report (111 pytest + 16 Vitest passed) |
| 9 | Vercel & Free-Tier Deployment Review | 🔍 Review Complete | Frontend PASS; Backend BLOCKED on in-memory persistence |
| 10 | Documentation, Demo & Final Audit | ⏳ Not started | — |

---

## Phase 0 Report

### Environment

| Tool | Version | Status |
|------|---------|--------|
| Python | 3.13.1 | ✅ (≥3.11 required) |
| Node.js | v22.14.0 | ✅ |
| npm | 11.1.0 | ✅ |
| Git | 2.49.0.windows.1 | ✅ |

### Workspace Detected

- **Location:** `c:\Users\SHARIEF PARAVEZ\OneDrive\Desktop\Invertory Reorder Planner\`
- **Existing files:** `playbook.md`, `Inventory Reorder Planner.docx`, `Inventory Reorder Planner.pdf`
- **Existing code:** None — fresh workspace, no React/Vite/FastAPI/Supabase configuration found.
- **Git status:** Initialized repo, no commits yet.

### Blockers

| # | Blocker | Severity | Resolution |
|---|---------|----------|------------|
| B1 | Organizer dashboard URL/API/schema not provided | Medium | Mock adapter will be used; real adapter added when URL is supplied |
| B2 | Supabase project URL and keys not yet set | Medium | `.env.example` will hold placeholders; user supplies real values before Phase 2 tests |
| B3 | Gemini API key not yet set | Low | Only needed in Phase 6; mock responses used until then |

### Confirmed: No prohibited services
- ❌ No Cloud Run / Google Cloud deployment planned
- ❌ No paid services selected
- ❌ No n8n, Browserbase or VerbX in baseline

---

---

## Phase 1 Report

### Files Created

| File | Purpose |
|------|---------|
| `REQUIREMENTS.md` | Full requirements traceability matrix |
| `.gitignore` | Excludes secrets, venv, node_modules, dist |
| `.env.example` | Env var template (no real values) |
| `README.md` | Project overview and setup guide |
| `frontend/package.json` | React 18 + Vite 5 + TypeScript 5 + Supabase JS |
| `frontend/vite.config.ts` | Vite config with API proxy |
| `frontend/tsconfig.json` | TypeScript strict config |
| `frontend/index.html` | HTML entry point |
| `frontend/src/main.tsx` | React bootstrap |
| `frontend/src/App.tsx` | Router shell with 7 screen stubs |
| `frontend/src/index.css` | Brand token CSS (Ice Silver, Deep Aubergine, Marigold) |
| `frontend/src/types/index.ts` | All TypeScript domain types |
| `backend/app/main.py` | FastAPI app entry point |
| `backend/app/config.py` | Pydantic-settings config loader |
| `backend/app/schemas/models.py` | All Pydantic v2 domain schemas |
| `backend/app/routers/*.py` | Router stubs (health, inventory, analyses, requests, approvals, test_runs) |
| `backend/requirements.txt` | Production Python deps |
| `backend/requirements-dev.txt` | Dev + test Python deps |
| `backend/pytest.ini` | Pytest config |
| `supabase/schema.sql` | Schema placeholder (full DDL in Phase 2) |
| `supabase/seed.sql` | Seed placeholder (full seed in Phase 2) |
| `tests/backend/conftest.py` | Shared fixtures |
| `tests/backend/test_scaffold.py` | Scaffold smoke tests |

### Schemas Defined

- Product / SKU, SupplierTerms, SalesHistory, OpenPurchaseOrder
- SourceEvidence (with source type, URL, timestamps, fields used)
- ReorderAnalysis + AnalysisInputSnapshot (immutable input snapshot)
- ReorderRequest, RequestVersion, Approval, VerificationResult
- AuditEvent (append-only)
- TestRun (TC1–TC4 case structure)
- All TypeScript equivalents in `frontend/src/types/index.ts`

### Request Lifecycle Defined
`draft → pending_approval → approved → submitted_or_simulated → verified`
Also: `rejected`, `needs_review`, `failed`

### Idempotency
Stable `idempotency_key` field on `ReorderRequest`; DB uniqueness constraint planned for Phase 2.

### Scaffold Status
- Frontend `npm install` — ✅ exit 0
- Backend venv + pip install — ✅ all packages installed
- Scaffold smoke tests — ✅ 2/2 passed

---

## Phase 2 Report

### Files Created / Updated

| File | Change |
|------|--------|
| `supabase/schema.sql` | ✅ Full implementation (was placeholder) |
| `supabase/seed.sql` | ✅ Full TC1–TC4 synthetic seed (was placeholder) |
| `supabase/SETUP.md` | ✅ New — step-by-step Supabase setup guide |
| `.env.example` | ✅ Updated key names |
| `backend/app/config.py` | ✅ Updated to match new key names |
| `DECISIONS.md` | ✅ Phase 2 decisions recorded |

### Schema Summary (12 tables)

| Table | RLS | Mutable? |
|-------|-----|----------|
| `products` | ✅ ownership | Full CRUD |
| `supplier_terms` | ✅ ownership | Full CRUD |
| `sales_history` | ✅ ownership | INSERT + DELETE only |
| `open_purchase_orders` | ✅ ownership | Full CRUD |
| `source_evidence` | ✅ ownership | Append-only |
| `reorder_analyses` | ✅ ownership | Append-only |
| `reorder_requests` | ✅ ownership | INSERT + UPDATE (no DELETE) |
| `request_versions` | ✅ ownership | Append-only + trigger guard |
| `approvals` | ✅ ownership | Append-only + trigger guard |
| `verification_results` | ✅ ownership | Append-only |
| `audit_events` | ✅ ownership | Append-only + trigger guard |
| `test_runs` | ✅ ownership | INSERT + UPDATE |

### Idempotency
`CONSTRAINT uq_request_idempotency UNIQUE (user_id, idempotency_key)` on `reorder_requests`.

### Env Variable Names
| Old | New |
|-----|-----|
| `SUPABASE_SERVICE_ROLE_KEY` | `SUPABASE_SECRET_KEY` |
| `VITE_SUPABASE_ANON_KEY` | `VITE_SUPABASE_PUBLISHABLE_KEY` |

### Static Checks (no live credentials required)

| Check | Result |
|-------|--------|
| Python syntax (`py_compile`) on all backend+test files | ✅ 0 errors |
| SQL parse: `schema.sql` (142 statements) | ✅ OK |
| SQL parse: `seed.sql` (34 statements) | ✅ OK |
| pytest (2 tests) | ✅ 2/2 passed |
| `.env.example` ↔ `config.py` alias consistency | ✅ All backend keys match |

### Checks NOT performed (require live Supabase credentials)
- RLS policy enforcement (requires connected Supabase instance)
- Auth redirect URL configuration
- Actual seed data insertion

---

## Phase 3 Report

### Implementation
- **Module:** [`backend/app/services/calculation_engine.py`](file:///c:/Users/SHARIEF%20PARAVEZ/OneDrive/Desktop/Invertory%20Reorder%20Planner/backend/app/services/calculation_engine.py) (Version: `1.0.0`)
- **Purity:** Pure Python with `Decimal` precision; zero external network dependencies, no live Supabase queries, and zero LLM calls for arithmetic.

### Calculation Rules Implemented (C1–C10 & A12)
- **C1 (Demand Forecasting):** `compute_average_daily_demand()` & `forecast_lead_time_demand()` (`average_daily_demand × lead_time_days`).
- **C2 (Incoming Order Eligibility):** `select_eligible_incoming()` filters by `open`, `confirmed`, `partially_received` expected on or before `as_of_date + lead_time_days`. Excludes cancelled orders and received orders (double-counting prevention).
- **C3 & C4 (Net Shortfall & Safety Stock):** `compute_net_shortfall()` computes `max(0, demand + safety_stock - stock - incoming)`. Discloses when safety stock defaults to `0` (`safety_stock_was_defaulted = True`).
- **C5 (Pack Rounding & MOQ):** `round_to_pack_size()` rounds up via `pack_size × ceil(shortfall / pack_size)` for case-only suppliers, and applies MOQ rounding up to full packs.
- **C6 (Cost Calculation):** `calculate_cost()` evaluates `proposed_quantity × unit_price` quantized to currency decimal.
- **C7 & C8 (Budget & Price Variance):** `check_budget()` identifies budget limits (`ok`, `over_budget`, `unknown`) and detects >= 20% price increases requiring review.
- **C9 (Negative Quantities Guard):** Rejects negative stock, price, sales, or lead times. Zero shortfall results in zero proposed units.
- **C10 (Missing Inputs Guard):** Validates required inputs and yields structured `AnalysisStatus.INSUFFICIENT_DATA` / `NEEDS_REVIEW`.
- **A12 / D2 (Evidence Verification):** `validate_evidence_ids()` checks UUIDs against known source evidence store; orphaned IDs trigger `INSUFFICIENT_DATA`.
- **Structured Explanations:** `build_structured_explanation()` generates full formula inputs, intermediate steps, and reasoning.

### Test Results
- **Test File:** [`tests/backend/test_decision_engine.py`](file:///c:/Users/SHARIEF%20PARAVEZ/OneDrive/Desktop/Invertory%20Reorder%20Planner/tests/backend/test_decision_engine.py)
- **Results:** 42 passed in 0.26s (40 new unit tests + 2 scaffold tests)
- **Test Coverage:**
  - Deterministic TC1, TC2, TC3, TC4 test case runs
  - Zero stock and zero shortfall boundary cases
  - 10 parameterized pack-size rounding boundary checks
  - Single-pack and multi-pack MOQ enforcement
  - Late, cancelled, and partially received incoming orders
  - Budget overrun and 20% price hike detection
  - Missing and invalid/negative inputs
  - Evidence ID validation against known stores
  - Markdown structured explanation content and structure

---

## Phase 4 Report

### Implementation
- **Module:** [`backend/app/services/source_adapter.py`](file:///c:/Users/SHARIEF%20PARAVEZ/OneDrive/Desktop/Invertory%20Reorder%20Planner/backend/app/services/source_adapter.py)
- **Adapter Classes:** `BaseSourceAdapter` (abstract interface), `MockSourceAdapter` (synthetic implementation), `retrieve_reorder_context` (orchestrator).
- **Provenance Capture:** Every retrieval captures `source_type = mock_source`, `source_url`, `retrieved_at`, `source_timestamp`, and `fields_used`. All synthetic records are explicitly tagged with `is_synthetic = True` and demo provenance notes.

### Safety & Robustness Rules Implemented
- **Staleness Detection:** Data older than 7 days is explicitly tagged `RetrievalStatus.STALE` (`is_stale = True`).
- **Conflict Detection:** Duplicate open purchase orders with conflicting quantities or arrival dates trigger `RetrievalStatus.CONFLICT`.
- **Anti-Invention Failure Guard:** If open orders or inventory retrieval fails, the context records `open_orders_data = None` and `is_valid = False`. The system strictly prohibits defaulting failed open orders to `[]` (0 orders), preventing false assumptions of zero incoming stock.
- **Prompt Injection Defense:** [`sanitize_source_string()`](file:///c:/Users/SHARIEF%20PARAVEZ/OneDrive/Desktop/Invertory%20Reorder%20Planner/backend/app/services/source_adapter.py#L425) treats untrusted text (descriptions, supplier notes) as inert data, never instructions.
- **Evidence Verification Integration:** All generated evidence IDs are maintained in the adapter's evidence repository, enabling seamless validation by Phase 3's `validate_evidence_ids()` per rule A12/D2.

### Test Results
- **Test File:** [`tests/backend/test_source_adapter.py`](file:///c:/Users/SHARIEF%20PARAVEZ/OneDrive/Desktop/Invertory%20Reorder%20Planner/tests/backend/test_source_adapter.py)
- **Suite Results:** 54 passed in 0.39s (12 new Phase 4 unit tests + 42 prior tests)
- **Test Coverage:**
  - TC1–TC4 synthetic retrieval and evidence provenance verification
  - Missing SKU and missing field handling
  - Stale data detection (> 7 days)
  - Conflicting duplicate open orders detection
  - Simulated inventory and open orders failure modes
  - Guard ensuring failed open orders do not default to empty list `[]`
  - Prompt injection text sanitization
  - End-to-end integration: adapter context fed into decision engine with valid evidence verification

---

## Phase 5 Report

### Implementation
- **Module:** [`backend/app/services/request_service.py`](file:///c:/Users/SHARIEF%20PARAVEZ/OneDrive/Desktop/Invertory%20Reorder%20Planner/backend/app/services/request_service.py)
- **Service Class:** `RequestService` managing in-memory entity stores and lifecycle transitions.
- **Idempotency:** Stable key generation via [`generate_idempotency_key()`](file:///c:/Users/SHARIEF%20PARAVEZ/OneDrive/Desktop/Invertory%20Reorder%20Planner/backend/app/services/request_service.py#L38) using SHA-256 hash of `user_id:sku:analysis_id:version`. Duplicate submissions return the existing active request without duplication and log `AuditEventType.RETRY`.

### Safety & Lifecycle Rules Implemented
- **Immutable Request Versioning:** Every proposal writes a `RequestVersionRead` with full input snapshot. Proposal updates create incrementing versions.
- **Mandatory Human Approval Gating:** Submissions without prior human approval are strictly blocked (`PermissionError`). Approvals are explicitly tied to the exact active version ID.
- **Approval Invalidation (Rule S2):** Any change to quantity, price, supplier, or pack size after approval invalidates that approval, forces status back to `pending_approval`, and writes an audit event.
- **Simulated Execution Default:** Submissions default to simulated mode, emitting mock references (`SIM-PO-...`). Real supplier procurement endpoints are never invoked.
- **Visible Failure States:** If simulated submission fails, request transitions to `failed` and records the error reason; failures are never masked as success.
- **Separate Independent Verification:** Post-submission verification separately checks SKU match, quantity match, pack size divisibility, and open PO duplicate detection. Any mismatch transitions request to `failed` with granular evidence explanations.
- **Append-Only Audit Trail:** Chronological immutable audit logging tracks `proposed`, `approved`, `rejected`, `submitted`, `retry`, `version_invalidated`, `verified`, and `failed`.

### Test Results
- **Test File:** [`tests/backend/test_request_service.py`](file:///c:/Users/SHARIEF%20PARAVEZ/OneDrive/Desktop/Invertory%20Reorder%20Planner/tests/backend/test_request_service.py)
- **Suite Results:** 68 passed in 0.36s (14 new Phase 5 unit tests + 54 prior tests)
- **Test Coverage:**
  - Request creation and initial version snapshotting
  - Idempotent duplicate retries returning existing requests and logging `RETRY`
  - Approval gating blocking unapproved submissions
  - Human approval recording approver ID, timestamp, and version ID
  - Proposal modification invalidating approval and blocking submission until re-approved
  - Obsolete version approval attempts rejected with version mismatch error
  - Rejection status transitions and submission blocking
  - Simulated submission success with mock reference generation
  - Submission failure visibility and audit logging
  - Independent outcome verification with matching SKU, quantity, pack size, and no duplicates
  - Independent verification mismatch detection (SKU mismatch, quantity mismatch, pack size violation, duplicate PO detection)
  - Chronological audit logging sequence across lifecycle events

---

## Phase 6 Report

### Implementation
- **Module:** [`backend/app/services/agent_orchestrator.py`](file:///c:/Users/SHARIEF%20PARAVEZ/OneDrive/Desktop/Invertory%20Reorder%20Planner/backend/app/services/agent_orchestrator.py)
- **Orchestrator Class:** `GeminiOrchestrator` managing Gemini function calling, deterministic fallback, bounded turns, and prompt injection defense.
- **Tool Declarations:** 5 narrowly defined tools adhering strictly to Gemini function calling schema (`GEMINI_TOOL_DECLARATIONS`):
  1. `get_inventory_and_orders`: Retrieves stock, sales history, supplier terms, and open orders with evidence provenance.
  2. `run_deterministic_analysis`: Delegates lead-time demand, shortfall, pack-size rounding, and cost calculations to `calculation_engine.py`.
  3. `prepare_reorder_request`: Drafts reorder requests with immutable versioning and idempotency keys in `pending_approval` state.
  4. `check_approval_status`: Queries human approval status and active version without permitting the LLM to grant approval.
  5. `verify_reorder_outcome`: Executes independent verification comparing actual vs intended SKU, quantity, pack size, and duplicate PO references.

### Safety Boundaries & Architecture
- **Arithmetic Delegation Rule:** Gemini is strictly commanded via system instructions and tool constraints never to calculate demand forecast, lead-time demand, net shortfall, pack rounding, or cost arithmetic directly. All arithmetic is calculated deterministically by the Phase 3 engine.
- **Human Approval Authority:** Gemini cannot approve requests or submit purchase orders to suppliers. Requests are created in `pending_approval` status, requiring human approval before submission can proceed.
- **Prompt Injection Defense:** Source strings from adapters or tool arguments are sanitized via `sanitize_source_string()` and stored as inert text, preventing embedded malicious directives from hijacking agent execution.
- **Deterministic Offline / Zero-Quota Fallback:** If `GEMINI_API_KEY` is missing or empty, or if the Gemini API returns HTTP 429 (rate limits/quota exhaustion), 500 errors, or network timeouts, the orchestrator automatically runs `run_deterministic_pipeline()` without crashing or inventing data.
- **Bounded Loop Guard:** Tool calling is strictly capped at `max_turns=5` to prevent infinite tool loops and uncontrolled quota consumption.
- **Zero Live Quota Test Suite:** Automated test suite executes entirely offline using mocked HTTP transports (`httpx.MockTransport`) and synthetic adapters.

### Test Results
- **Test File:** [`tests/backend/test_agent_orchestrator.py`](file:///c:/Users/SHARIEF%20PARAVEZ/OneDrive/Desktop/Invertory%20Reorder%20Planner/tests/backend/test_agent_orchestrator.py)
- **Suite Results:** 81 passed in 0.40s (13 new Phase 6 unit tests + 68 prior tests)
- **Test Coverage:**
  - Complete tool declarations and JSON schema compliance
  - Core safety rules in system instructions
  - Tool execution for source retrieval, deterministic calculation, request preparation, and verification
  - Graceful handling of unknown tool calls
  - Deterministic fallback when `GEMINI_API_KEY` is empty
  - Deterministic fallback pack rounding for case-only suppliers (TC2)
  - Simulated multi-turn Gemini conversation with function calls and final summary
  - Graceful fallback on Gemini HTTP 429 rate limit / quota exhaustion
  - Graceful fallback on network connection timeouts
  - Bounded turns limit halting infinite loops after max turns
  - Prompt injection sanitization in tool arguments

---

## Phase 7 Report

### Implementation
- **Visual Design System:** "Editorial Supply-Chain Precision" implemented in [`frontend/src/index.css`](file:///c:/Users/SHARIEF%20PARAVEZ/OneDrive/Desktop/Invertory%20Reorder%20Planner/frontend/src/index.css).
  - Palette: Deep Aubergine (`#3A0F34`), Ice Silver (`#DDE3E8`), Marigold (`#EAAA00`), Lifted Silver (`#EEF2F5`), Deepest Aubergine (`#250821`), Elevated Plum (`#471440`).
  - Typography: Plus Jakarta Sans for headings and navigation; JetBrains Mono for SKUs, order references, quantities, and financial numbers.
- **Client Data Service:** [`frontend/src/services/dataService.ts`](file:///c:/Users/SHARIEF%20PARAVEZ/OneDrive/Desktop/Invertory%20Reorder%20Planner/frontend/src/services/dataService.ts) providing typed client state initialized with TC1–TC4 seed data, pure C1–C10 reorder arithmetic, SHA-256 idempotency protection, Rule S2 approval invalidation, simulated order execution (`SIM-PO-...`), and independent outcome verification.
- **Components Built:**
  - `Header.tsx`: Navigation bar with brand badge, active indicators, pending approvals counter, and persona switcher.
  - `SyntheticBanner.tsx`: Top notification clarifying synthetic data mode and isolation from live procurement endpoints.
  - `GuardrailsCard.tsx`: Operational governance cards detailing Zero LLM Arithmetic, Mandatory Human Approval, Rule S2, and Outcome Verification.
  - `DepletionChart.tsx`: Accessible 30-day SVG stock depletion curve charting stock trajectory against lead-time ordering horizons.
  - `AuditTrailList.tsx`: Chronological immutable audit timeline with actor IDs, version numbers, and payload changes.
- **Views & User Flows Built:**
  1. `DashboardPage.tsx`: Operational command center with stockout risk metrics, depletion curve, and reorder status snapshot.
  2. `InventoryPage.tsx`: Searchable SKU catalog with urgency filters, case packaging badges, and quick evaluate actions.
  3. `AnalysisView.tsx`: Step-by-step mathematical walkthrough of demand forecast, shortfall, pack rounding, budget review, evidence provenance, and draft request creation.
  4. `ApprovalsQueuePage.tsx`: Review queue with human approve/reject dialogs and Rule S2 proposal modification.
  5. `RequestDetailPage.tsx`: Deep dive with lifecycle stepper, version snapshots, simulated order submission, independent outcome verification comparator, and audit history.
  6. `ScenarioRunnerPage.tsx`: Interactive test harness for TC1, TC2, TC3, and TC4 with live execution and expected vs actual diffs.
  7. `AuthPage.tsx`: Persona switcher between Inventory Planner (`Sarah Connor`) and Purchasing Approver (`Marcus Vance`).

### Test Results
- **Frontend Vitest Suite:** 9 passed in 7ms (`frontend/src/__tests__/dataService.test.ts`)
  - TC1: standard reorder shortfall calculation
  - TC2: pack-size rounding to case multiples
  - TC3: eligible incoming purchase order coverage
  - TC4: 20% price increase and budget overrun detection
  - Idempotent duplicate retry handling
  - Submission blocked without human approval
  - Rule S2 approval invalidation when proposal changes
  - Independent outcome verification match and mismatch detection
  - TC1–TC4 test scenario runner execution
- **Frontend Production Bundle:** `tsc && vite build` built cleanly in 1.08s (zero TypeScript or bundle errors).
- **Backend Test Suite:** All 81 prior Python tests pass cleanly in 0.44s without regression.

### Mock-Only Features & Phase 8 Integration Gap (Resolved)
- In Phase 7, the UI operated against client-side `dataService.ts`.
- In Phase 8, all router endpoints in `backend/app/routers/*.py` were implemented, connected to `BackendStore`, validated with typed Pydantic schemas, and bound to `apiClient.ts` in the frontend.

---

## Phase 8 Report

### Implementation Summary
- **Backend Endpoints Implemented:**
  - `health.py`: `GET /api/health`
  - `dashboard.py`: `GET /api/dashboard` (operational metrics: stockout risks, pending approvals, active orders)
  - `inventory.py`: `GET /api/inventory` (catalog with supplier terms & stock), `GET /api/inventory/{sku}`
  - `analyses.py`: `POST /api/analyses/evaluate` (deterministic engine evaluation), `GET /api/analyses`, `GET /api/analyses/{id}`
  - `requests.py`: `POST /api/requests` (idempotent request creation), `GET /api/requests`, `GET /api/requests/{id}`, `GET /api/requests/{id}/versions`, `GET /api/requests/{id}/audit`, `PATCH /api/requests/{id}/proposal` (Rule S2 version invalidation), `POST /api/requests/{id}/submit` (simulated order submission), `POST /api/requests/{id}/verify` (independent outcome verification), `GET /api/requests/{id}/verification`
  - `approvals.py`: `POST /api/approvals` (records approval/rejection on exact version), `GET /api/approvals/{id}`
  - `test_runs.py`: `POST /api/test-runs/run/{case_id}` (TC1–TC4 acceptance runner), `POST /api/test-runs/run-all`, `GET /api/test-runs`
- **Backend Store & Service Bridge:** [`backend/app/services/backend_store.py`](file:///c:/Users/SHARIEF%20PARAVEZ/OneDrive/Desktop/Invertory%20Reorder%20Planner/backend/app/services/backend_store.py) coordinating in-memory repositories for products, supplier terms, open orders, analyses, requests, versions, approvals, audit events, verifications, and test runs.
- **Frontend API Client:** [`frontend/src/services/apiClient.ts`](file:///c:/Users/SHARIEF%20PARAVEZ/OneDrive/Desktop/Invertory%20Reorder%20Planner/frontend/src/services/apiClient.ts) providing typed async methods, structured `ApiError` handling, and visible mock source tagging.
- **Frontend UI Wiring:** `ScenarioRunnerPage.tsx` and `dataService.ts` wired to live FastAPI endpoints with deterministic client fallback when offline.

### Acceptance Test Results (TC1–TC4 & Partial Open Order)
All scenarios verified end-to-end from source retrieval through analysis, request preparation, approval, simulated submission, and independent verification:
- **TC1 (Low stock, no incoming order):** ✅ PASSED
  - Input: SKU-001, stock=20, demand=4.0 u/d, lead time=14d.
  - Calculation: Lead-time demand = 56, Net shortfall = 36, Pack size = 1, Proposed quantity = 36 units, Estimated cost = $360.00, Status = `ready`.
  - Workflow: Request created (`pending_approval`, idempotency key `IDEM-TC1-FULL-FLOW`) → Approved by human → Simulated order submitted (`SIM-PO-...`) → Verified (SKU match, quantity match, pack check) → Audit trail complete.
- **TC2 (Supplier sells in cases of 12):** ✅ PASSED
  - Input: SKU-002, stock=25, demand=4.0 u/d, lead time=14d, pack size=12.
  - Calculation: Lead-time demand = 56, Net shortfall = 31, Pack rounding = ceil(31/12) * 12 = 36 units (3 cases), Estimated cost = $360.00, Status = `ready`.
  - Workflow: Request created (3 cases, 36 units) → Approved → Simulated submission → Verification passed pack size divisibility check.
- **TC3 (Existing pending/open purchase order):** ✅ PASSED
  - Input: SKU-003, stock=20, demand=4.0 u/d, lead time=14d. Open order PO-GAMMA-001 for 24 units arriving in 10 days (eligible).
  - Calculation: Lead-time demand = 56, Eligible incoming = 24, Net shortfall = max(0, 56 - 20 - 24) = 12 units, Proposed quantity = 12 units.
  - Double-Ordering Prevention: Shortfall reduced from 36 to 12. When demand is fully covered (e.g. 40 units), net shortfall is 0, proposed quantity is 0, preventing duplicate reordering.
- **TC4 (Supplier price increases by 20%):** ✅ PASSED
  - Input: SKU-004, stock=20, demand=4.0 u/d, lead time=14d. Supplier price = $12.00 (was $10.00; +20%). Budget available = $400.00.
  - Calculation: Proposed quantity = 36 units, Estimated cost = 36 * $12.00 = $432.00 > $400.00. Budget status = `over_budget`, Analysis status = `needs_review`, Price hike detected = True.
  - Approval Enforcement: Submitting without approval returns 403 Forbidden. Requires explicit human review and authorization before submission.
- **Partial Open Order Case (Rule 5):** ✅ PASSED
  - Input: Demand = 100 units, Stock = 20 units, Confirmed incoming order = 30 units.
  - Result: Shortfall = 100 - 20 - 30 = 50 units (> 0). Shortages are legitimately proposed and not suppressed merely because an order exists.

### Safety & Failure Handling Verified
- **Server-Side Approval Gating:** Submissions without prior human approval return HTTP 403 Forbidden (`CONSEQUENTIAL_ACTION_BLOCKED`).
- **Rule S2 Approval Invalidation:** Editing a proposal after approval creates a new version, forces status back to `pending_approval`, and invalidates prior approval. Submit attempts return 403 Forbidden until re-approved.
- **Anti-Invention Guard:** Failed open orders retrieval sets `open_orders_data = None` and `is_valid = False`; never defaults to `[]` or 0 incoming orders.
- **Evidence Integrity Guard:** Reorder requests cannot be created from analyses with `insufficient_data` or failed evidence (HTTP 400 Bad Request).
- **Invalid Quantity Defense:** Negative, zero, or non-pack compliant quantities rejected by validation schemas.
- **Idempotency Protection:** Retrying with existing idempotency key returns existing request with `is_duplicate: true` and logs `AuditEventType.RETRY`.
- **Outcome Verification:** Separate verification stage detects SKU mismatch, quantity mismatch, pack size violation, and duplicate PO references, transitioning request to `failed` with granular evidence.
- **Simulated Execution Default:** Real procurement endpoints are never contacted; mock references (`SIM-PO-...`) emitted.
- **Secret Protection:** Source control, API responses, and frontend bundles verified free of secret keys.
- **Backend-Enforced Authentication & Role Authorization:** Implemented in `backend/app/services/auth.py` and `backend/app/routers/approvals.py`. Caller-supplied `approver_id` removed and forbidden via `extra="forbid"`. Approver identity bound strictly to authenticated Bearer token (`current_user.id`). Requires `approver` role (401 on unauthenticated, 403 on planner role, 422 on caller-injected `approver_id`).

### Test Suite Execution
- **Backend Pytest Suite:** 118 passed in 2.78s (`backend/.venv/Scripts/pytest`)
  - `tests/backend/test_persistence_and_auth.py`: 7 passed (registration boundaries, safe role assignment, invalid/expired token rejection, production in-memory fallback prohibition, JWT forwarding for RLS, duplicate retries, role authorization)
  - `tests/backend/test_acceptance_scenarios.py`: 6 passed (TC1, TC2, TC3, TC4, partial open order, scenario runner endpoints)
  - `tests/backend/test_api_integration.py`: 8 passed (all REST endpoints and error shapes)
  - `tests/backend/test_safety_and_failures.py`: 15 passed (gating, invalidation, anti-invention, secret protection, 401 unauthenticated, 403 forbidden roles, 422 caller-supplied ID rejection, 200 approver binding, production demo token prohibition)
  - `tests/backend/test_agent_orchestrator.py`: 13 passed
  - `tests/backend/test_decision_engine.py`: 40 passed
  - `tests/backend/test_request_service.py`: 14 passed
  - `tests/backend/test_source_adapter.py`: 12 passed
  - `tests/backend/test_scaffold.py`: 3 passed (including Pydantic Settings VITE_* filtering and typo protection)
- **Frontend Vitest Suite:** 22 passed in 54ms (`npm test -- --run` in `frontend/`)
  - `src/__tests__/supabaseAuth.test.ts`: 6 passed (unconfigured detection, sign-up/sign-in boundaries, safe role default, session token handling)
  - `src/__tests__/dataService.test.ts`: 9 passed
  - `src/__tests__/apiClient.test.ts`: 7 passed (including dynamic auth token injection)
- **Frontend Production Bundle:** `npm run build` compiled cleanly in 2.23s (zero TypeScript or bundle errors).

### Distinguishing Mocked Tests vs Live Supabase
- All 118 backend tests and 22 frontend tests execute against deterministic synthetic adapters and in-memory mock repositories.
- Zero live Supabase or external network dependencies are required or claimed in test runs.
- Synthetic provenance is maintained on all records (`source_type = "mock_source"`, `is_synthetic = True`).

---

## Real Supabase Authentication & Persistent Storage Report

### 1. Real Authentication Architecture
- **Browser Supabase Integration:** Implemented in [`frontend/src/services/supabaseClient.ts`](frontend/src/services/supabaseClient.ts) and [`frontend/src/pages/AuthPage.tsx`](frontend/src/pages/AuthPage.tsx) with email/password sign-up, sign-in, sign-out, session restoration, and loading/error states.
- **Safe Role Governance:** Newly self-registered users are assigned the standard `planner` role. The `approver` role is strictly segregated and cannot be self-claimed via `user_metadata`; it must be elevated via `auth.users.raw_app_meta_data` by an administrator.
- **Token Forwarding:** When a verified Supabase session exists, [`frontend/src/services/dataService.ts`](frontend/src/services/dataService.ts) and [`frontend/src/services/apiClient.ts`](frontend/src/services/apiClient.ts) inject the live JWT `Bearer` token into all FastAPI requests.
- **Backend Verification:** In [`backend/app/services/auth.py`](backend/app/services/auth.py), JWTs are verified against Supabase Auth. Demo tokens are strictly forbidden in production (HTTP 401).

### 2. Persistent Storage Architecture & Repository Pattern
- **Repository Abstraction:** Implemented in [`backend/app/services/repository.py`](backend/app/services/repository.py) with interfaces `IInventoryRepository`, `IAnalysisRepository`, `IReorderRepository`, and `ITestRunRepository`.
- **FastAPI Router Dependency Injection:** Routers (`inventory.py`, `analyses.py`, `requests.py`, `approvals.py`, `test_runs.py`, `dashboard.py`) now inject `RepositoryManager = Depends(get_repository_manager)` instead of accessing singleton stores directly.
- **User-Scoped JWT Forwarding for RLS:** In `SupabaseRepositoryManager`, queries set `client.postgrest.auth(user_token)` so PostgreSQL evaluates `auth.uid()` for all Row Level Security policies.
- **Production Persistence Guard:** In production mode (`APP_ENV=production`), silent fallback to in-memory store is strictly prohibited. If Supabase is unavailable, requests fail visibly with HTTP 503.

### 3. Database Safety & Schema / RLS Mismatch Report
> **CRITICAL:** In accordance with instructions, zero SQL migrations, seed scripts, or database writes have been executed against the live Supabase project.

#### Identified Schema & RLS Policy Mismatches:
1. **Approval RLS Policy (`approvals` table):**
   - *Current Policy:* `approvals_insert_own` checks `WITH CHECK (user_id = auth.uid())`.
   - *Issue:* In a role-segregated workflow where Planner A creates a request and Approver B approves it, Approver B's `auth.uid()` differs from the request owner's `user_id`. An insert by Approver B will fail RLS.
   - *Recommended Policy Update:*
     ```sql
     DROP POLICY IF EXISTS "approvals_insert_own" ON approvals;
     DROP POLICY IF EXISTS "approvals_select_own" ON approvals;
     CREATE POLICY "approvals_insert_approver" ON approvals FOR INSERT WITH CHECK (approver_id = auth.uid() OR user_id = auth.uid());
     CREATE POLICY "approvals_select_participants" ON approvals FOR SELECT USING (user_id = auth.uid() OR approver_id = auth.uid());
     ```
2. **Request Status Update RLS Policy (`reorder_requests` table):**
   - *Current Policy:* `requests_update_own` checks `USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid())`.
   - *Issue:* When Approver B approves Planner A's request, updating the request status from `pending_approval` to `approved` fails under ownership RLS if executed directly with Approver B's user token.
   - *Recommended Policy Update:*
     ```sql
     CREATE POLICY "requests_update_approver" ON reorder_requests FOR UPDATE
       USING (user_id = auth.uid() OR (auth.jwt() -> 'app_metadata' ->> 'role') IN ('approver', 'admin'))
       WITH CHECK (user_id = auth.uid() OR (auth.jwt() -> 'app_metadata' ->> 'role') IN ('approver', 'admin'));
     ```
3. **Audit Events Actor RLS Policy (`audit_events` table):**
   - *Current Policy:* `audit_insert_own` checks `WITH CHECK (user_id = auth.uid())`.
   - *Issue:* When Approver B acts on Planner A's request, logging the approval event with `actor_id = Approver B` and `user_id = Planner A` fails RLS.
   - *Recommended Policy Update:*
     ```sql
     CREATE POLICY "audit_insert_actor" ON audit_events FOR INSERT WITH CHECK (actor_id = auth.uid() OR user_id = auth.uid());
     ```

### 4. Supabase Security & RLS Policy Hardening Audit (Phase 9 Audit)
- **RLS Policy Audit:** Completed comprehensive audit of all 12 tables. Policies updated with safe, idempotent `DROP POLICY IF EXISTS` in `supabase/schema.sql`.
  - `reorder_requests`: Planners can only insert and update requests in `draft` or `pending_approval` state. Self-approval is mathematically blocked by RLS `WITH CHECK (status IN ('draft', 'pending_approval'))`. Approvers can only update status to `approved` or `rejected`. Submissions require status `approved`.
  - `approvals`: Inserts enforce `approver_id = auth.uid()`, require role `approver` or `admin` in `app_metadata`, verify that the referenced request exists, belongs to the request owner, is currently `pending_approval`, and matches `request_version_id`.
  - `audit_events`: Enforced `actor_id = auth.uid()` to prevent audit spoofing.
  - Multi-tenant isolation: `tenant_id` column and index added to `products`, `reorder_requests`, `approvals`, and `audit_events`. Approver access scoped via `(tenant_id IS NULL OR tenant_id::text = (auth.jwt() -> 'app_metadata' ->> 'tenant_id'))`.
- **API Persistence Routing:** In-memory persistence paths eradicated across all production endpoints, including `/api/test-runs` which now persists via `repo.requests`.
- **Backend JWT Verification:** Implemented in `backend/app/services/auth.py`. Verifies signature, expiration (`exp`), audience (`aud == 'authenticated'`), and issuer (`iss == settings.supabase_url`). Supports local cryptographic verification via `SUPABASE_JWT_SECRET`. Privileged roles strictly derived from `app_metadata`; untrusted `user_metadata` claims downgraded to `planner`.
- **Approval Binding & Concurrency:** Optimistic concurrency locking enforced on request status updates (`.eq("status", ...)`). Direct caller-supplied `approver_id` forbidden via Pydantic (`extra="forbid"`).
- **Test Results:**
  - Backend: 126 passed (0 failures)
  - Frontend: 22 passed across 3 test files (0 failures)
  - Production build: Succeeded in 2.16s (0 errors)

---

## Known Issues
- Live database deployment requires running `supabase/schema.sql` with the idempotent RLS policies detailed above and creating verified Supabase users.
- Live deployment blocked awaiting user approval.

## Next Approved Phase
_Awaiting explicit user approval before running live database migrations or deploying._

