# DECISIONS.md — Inventory Reorder Planner

## Stack Decisions (Fixed by Playbook)

| Concern | Choice | Reason |
|---------|--------|--------|
| Frontend | React + Vite + TypeScript | Specified by playbook |
| Backend | Python + FastAPI | Specified by playbook |
| Database/Auth | Supabase (PostgreSQL + Supabase Auth) | Specified by playbook; free tier |
| AI/LLM | Gemini API (free tier) | Specified by playbook |
| Frontend hosting | Vercel Hobby (free) | Specified by playbook; subject to eligibility check in Phase 9 |
| Styling | Vanilla CSS with fixed palette | Playbook-specified: Ice Silver #DDE3E8, Deep Aubergine #3A0F34, Marigold #EAAA00 |

## Implementation Assumptions

| # | Assumption | Recorded |
|---|-----------|---------|
| A1 | No organizer dashboard URL/API has been provided; a mock/synthetic adapter will be used and clearly labelled `mock_source`. | Phase 0 |
| A2 | Supabase credentials will be supplied by the user before Phase 2 integration tests; placeholders used in `.env.example`. | Phase 0 |
| A3 | Purchase order submission defaults to simulated/mock mode until the user and organizer explicitly authorize a real endpoint. | Phase 0 |
| A4 | Safety stock target defaults to zero if not configured; this assumption is disclosed in the UI and calculation evidence. | Phase 0 |
| A5 | Incoming orders are only counted as "eligible" if their status is confirmed/open AND the expected arrival date falls within the lead-time demand window. | Phase 0 |
| A6 | Backend deployment target (FastAPI on Vercel vs. local demo) will be confirmed during Phase 9 after checking current Vercel Python runtime limits. | Phase 0 |
| A7 | `user_id = auth.uid()` ownership model used for all RLS policies. For a multi-user production system this would be replaced by an `organization_id` team model. Disclosed in DECISIONS.md. | Phase 2 |
| A8 | Demo seed data is seeded with a fixed UUID user (`00000000-…-0001`). Real users must be created via Supabase Auth; the demo UUID is for local testing only. | Phase 2 |
| A9 | `audit_events` and `request_versions` are append-only enforced at two layers: (1) database trigger blocks UPDATE/DELETE; (2) no UPDATE/DELETE RLS policies exist. | Phase 2 |
| A10 | `reorder_analyses` and `source_evidence` are also immutable once written. New analysis = new row; never overwrite. | Phase 2 |
| A11 | **D1 fix:** `supplier_terms.product_id` uses `ON DELETE RESTRICT` (not CASCADE). Deleting a product is blocked while supplier terms exist. Required deletion order: (1) cancel/delete open orders, (2) delete supplier terms, (3) delete product. This prevents a PostgreSQL cascade-ordering failure where the products→supplier_terms CASCADE fired before the products→open_purchase_orders CASCADE, causing the RESTRICT on open_purchase_orders.supplier_terms_id to abort the transaction. | Phase 2 review |
| A12 | **D2 — known limitation:** `reorder_analyses.evidence_ids` is a `UUID[]` column. PostgreSQL does not support FK constraints on array elements, so referential integrity to `source_evidence` cannot be enforced at the DB layer. The Phase 3 calculation engine **must** validate every UUID in `evidence_ids` against the `source_evidence` table before reading or returning analysis results. An invalid/orphaned UUID must cause the analysis to be marked `insufficient_data`. | Phase 2 review |
| A13 | **Calculation Engine Purity:** Implemented in `backend/app/services/calculation_engine.py` (version `1.0.0`). Strictly deterministic pure Python with `Decimal` precision. No external network dependencies, no live database queries, and zero LLM calls for arithmetic. | Phase 3 |
| A14 | **Incoming Order Eligibility & Double-Counting Guard:** Orders are eligible only if status is `open`, `confirmed`, or `partially_received`, and `expected_arrival_date <= as_of_date + lead_time_days`. Orders marked `received` are excluded because their units are already present in on-hand stock (preventing double counting); `cancelled` orders are excluded. | Phase 3 |
| A15 | **Packaging & MOQ Rule:** For case-only suppliers (`pack_size > 1`), order quantity rounds up via `pack_size * ceil(shortfall / pack_size)`. If MOQ is configured and exceeds raw pack rounding, order units are raised to meet MOQ, rounding up to the next full pack multiple. | Phase 3 |
| A16 | **Evidence Validation Enforcement (A12):** Implemented in `validate_evidence_ids()`. Any orphaned or missing UUID in `evidence_ids` sets `analysis_status = insufficient_data` with descriptive `status_reason`. | Phase 3 |
| A17 | **Source Adapter & Synthetic Provenance:** Implemented in `backend/app/services/source_adapter.py`. All synthetic mock data is explicitly tagged with `source_type = mock_source`, `is_synthetic = True`, and comprehensive evidence provenance (`source_url`, `retrieved_at`, `source_timestamp`, `fields_used`). | Phase 4 |
| A18 | **Staleness & Conflict Detection:** Data timestamps older than 7 days trigger `RetrievalStatus.STALE`. Duplicate open PO references with mismatched quantities or arrival dates trigger `RetrievalStatus.CONFLICT`. | Phase 4 |
| A19 | **Failure Safety / Anti-Invention Guard:** If open orders or inventory retrieval fails, the system never defaults to zero stock or zero incoming orders (`open_orders_data = None`). Failures mark the retrieval context invalid, forcing `insufficient_data` or `needs_review` downstream to prevent catastrophic over-ordering. | Phase 4 |
| A20 | **Prompt Injection Resilience:** Untrusted source text (product descriptions, supplier notes) is sanitized and stored strictly as literal data in `raw_data`; instructions inside source fields are never executed. | Phase 4 |
| A21 | **Request Service & Version Immutability:** Implemented in `backend/app/services/request_service.py`. Enforces immutable versioning (`RequestVersion`), stable SHA-256 idempotency keys, and strict human approval gating. | Phase 5 |
| A22 | **Approval Invalidation (Rule S2):** Any proposal modification after approval invalidates that approval, creates a new version, resets status to `pending_approval`, and records an audit event. Submitting without re-approval is blocked. | Phase 5 |
| A23 | **Simulated Submission Safe Mode:** Defaults to simulated execution (`SIM-PO-...`). Submission requires status `approved` and active approval on the exact current version. Live supplier order endpoints are never contacted. | Phase 5 |
| A24 | **Independent Outcome Verification:** Separate verification stage tests actual vs intended SKU, quantity, pack size divisibility, and duplicate PO references. Any failure marks request and verification as `failed`. | Phase 5 |
| A25 | **Append-Only Audit Trail:** Chronological immutable audit logging captures `proposed`, `approved`, `rejected`, `submitted`, `retry`, `version_invalidated`, `verified`, and `failed` events. | Phase 5 |

## Env Variable Naming (Phase 2 decision)

| Old name | New name | Reason |
|----------|----------|--------|
| `SUPABASE_SERVICE_ROLE_KEY` | `SUPABASE_SECRET_KEY` | Shorter; matches Supabase dashboard terminology ("secret") |
| `VITE_SUPABASE_ANON_KEY` | `VITE_SUPABASE_PUBLISHABLE_KEY` | Explicit that this key is browser-publishable |

## RLS Policy Design (Phase 2 decision)

- All 12 tables have RLS enabled.
- Policies are ownership-based: `user_id = auth.uid()`. No policy grants unrestricted access to all authenticated users.
- `audit_events`, `approvals`, `request_versions`, `source_evidence`, `reorder_analyses`: INSERT + SELECT only (immutable after creation).
- `sales_history`: INSERT + SELECT + DELETE only (replaced, never mutated).
- Append-only tables additionally have DB-level triggers (`prevent_mutation`) so even superuser queries get a guard.
- **D3 fix:** `prevent_mutation()` checks the session GUC `app.seed_cleanup`. When set to `'true'`, the trigger allows DELETE (seed cleanup only). Application code must never set this GUC. The GUC is set and RESET within the seed script's cleanup block.

## Open Questions

| # | Question | Status |
|---|---------|--------|
| Q1 | Will the organizer provide a dashboard URL or API schema? | ❓ Open |
| Q2 | Is Supabase Auth (sign-in/sign-up) required for the demo scope, or is a single demo user sufficient? | ❓ Open |
| Q3 | What currency should be used for pricing in the seed data? | ✅ Resolved — defaulting to USD |
