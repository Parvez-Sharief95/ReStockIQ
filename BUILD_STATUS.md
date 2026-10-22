# BUILD_STATUS.md — Inventory Reorder Planner

## Current Phase: PHASE 6 COMPLETE — Awaiting approval for Phase 7

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
| 7 | React Frontend & User Experience | ⏳ Not started | — |
| 8 | API Integration & TC1–TC4 Acceptance Tests | ⏳ Not started | — |
| 9 | Vercel & Free-Tier Deployment Review | ⏳ Not started | — |
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

## Known Issues
_None at this stage._

## Next Approved Phase
_Phase 7 — React Frontend & User Experience (awaiting explicit user approval)._
