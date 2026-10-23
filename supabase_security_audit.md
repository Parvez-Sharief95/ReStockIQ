# Supabase SQL Security Audit

**Scope:** `supabase/schema.sql`, `supabase/seed.sql`, `supabase/SETUP.md`
**Mode:** Read-only. No SQL executed, no database connected, no files modified.

> [!IMPORTANT]
> RLS policies can only be **fully validated** by live query testing with real JWTs against the actual Supabase project. Findings below are confirmed by static code analysis; risks marked **configuration-dependent** require live testing to confirm exploitability.

---

## Finding Index

| ID | Severity | Area | Short Description |
|----|----------|------|-------------------|
| F1 | 🔴 CRITICAL | `seed_demo_data_for_user` | Any authenticated user can call this via Supabase RPC |
| F2 | 🔴 CRITICAL | `seed_demo_data_for_user` | Repeated calls insert duplicate rows into 7 of 10 tables |
| F3 | 🟠 HIGH | `seed_demo_data_for_user` | No validation that `target_user_id` exists in `auth.users` |
| F4 | 🟠 HIGH | `products_select_authorized` | Hardcoded catalog UUID grants universal SELECT bypass |
| F5 | 🟠 HIGH | `seed.sql` cleanup bypass | `app.seed_cleanup` GUC persists for entire session, not transaction |
| F6 | 🟠 HIGH | `audit_events` in seed function | `ON CONFLICT DO NOTHING` on PK-only table inserts duplicates silently |
| F7 | 🟡 MEDIUM | `approvals` INSERT policy | Approver can approve their own request — no self-approval guard |
| F8 | 🟡 MEDIUM | `open_purchase_orders` INSERT | No cross-check that `product_id` / `supplier_terms_id` belong to the same user |
| F9 | 🟡 MEDIUM | `seed.sql` auth.users INSERT | `auth.identities` row missing; GoTrue internal state inconsistent |
| F10 | 🟡 MEDIUM | `seed.sql` re-run safety | All INSERTs after cleanup lack `ON CONFLICT (id) DO NOTHING` |
| F11 | 🟡 MEDIUM | `request_versions` INSERT policy | `version_number` not enforced as sequential; gap / forged versions allowed |
| F12 | 🟢 LOW | `audit_events.actor_id` | Column is NULLABLE; seed function inserts spoofed `actor_id` values |
| F13 | 🟢 LOW | All approver SELECT policies | Approver with no `tenant_id` sees ALL NULL-tenant records globally |
| F14 | 🟢 LOW | `SETUP.md` | `REVOKE EXECUTE` on seed function not documented; role revocation absent |

---

## Detailed Findings

### F1 — 🔴 CRITICAL: Any Authenticated User Can Call seed_demo_data_for_user via RPC

**File:** `schema.sql` lines 828–1017
**Function:** `public.seed_demo_data_for_user(target_user_id UUID)`

The function is `SECURITY DEFINER` in the `public` schema. In Supabase, all `public` functions are callable via the PostgREST RPC endpoint using any valid anon or authenticated JWT:

```http
POST https://<project>.supabase.co/rest/v1/rpc/seed_demo_data_for_user
Authorization: Bearer <any-valid-access-token>
{"target_user_id": "<victim-uuid>"}
```

The function runs as `postgres`, bypasses all RLS, and inserts TC1–TC4 data for **any target UUID** — including another real user's account.

**Exploit scenario:**
1. Attacker registers a legitimate account.
2. Attacker learns victim's UUID from audit events or approvals records (which leak `user_id`).
3. Attacker POSTs to `/rpc/seed_demo_data_for_user` with victim's UUID.
4. Spurious `draft` and `needs_review` requests appear in victim's queue.
5. If victim is an approver, the injected requests may surface in their approval queue.

**Recommended fix:**
```sql
REVOKE EXECUTE ON FUNCTION public.seed_demo_data_for_user(UUID) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.seed_demo_data_for_user(UUID) FROM authenticated;
REVOKE EXECUTE ON FUNCTION public.seed_demo_data_for_user(UUID) FROM anon;
-- Only the postgres/service_role context (SQL Editor) should call this:
GRANT EXECUTE ON FUNCTION public.seed_demo_data_for_user(UUID) TO service_role;
```

---

### F2 — 🔴 CRITICAL: Repeated Calls Create Duplicate Records (Non-Idempotent)

**File:** `schema.sql` lines 868–1009

`gen_random_uuid()` is called fresh each invocation for `s1–s4`, `sh1–sh4`, `ev1–ev4`, `an1–an4`, `tr1–tr4`. The `ON CONFLICT DO NOTHING` on these tables fires only on primary-key conflict — but the PK is a new UUID each time, so it **never fires**:

| Table | `ON CONFLICT` | Unique constraint | 2nd call result |
|-------|--------------|-------------------|-----------------|
| `products` | `(user_id, sku)` | `UNIQUE (user_id, sku)` ✅ | Safe |
| `supplier_terms` | `DO NOTHING` | PK only | **New row every call** |
| `sales_history` | `DO NOTHING` | PK only | **New row every call — corrupts demand calc** |
| `open_purchase_orders` | `DO NOTHING` | PK only | **New row every call — inflates eligible_incoming** |
| `source_evidence` | `DO NOTHING` | PK only | **New row every call** |
| `reorder_analyses` | `DO NOTHING` | PK only | **New row every call** |
| `reorder_requests` | `(user_id, idempotency_key)` | `UNIQUE (user_id, idempotency_key)` ✅* | Partially safe* |
| `request_versions` | `DO NOTHING` | `UNIQUE (request_id, version_number)` ✅* | Partially safe* |
| `audit_events` | `DO NOTHING` | PK only | **New row every call** |
| `test_runs` | `DO NOTHING` | PK only | **New row every call** |

\* The idempotency key for requests is `'SKU-001-' || an1::text || '-v1'`. Because `an1` is a new UUID per call, the key changes — meaning **requests also get new rows on the second call** if the analysis insert was skipped.

**Recommended fixes** (unique constraints required first):
```sql
ALTER TABLE supplier_terms       ADD CONSTRAINT uq_supplier_terms_user_product   UNIQUE (user_id, product_id);
ALTER TABLE sales_history        ADD CONSTRAINT uq_sales_history_product_period  UNIQUE (user_id, product_id, period_start, period_end);
ALTER TABLE open_purchase_orders ADD CONSTRAINT uq_open_orders_user_ref          UNIQUE (user_id, order_reference);
ALTER TABLE test_runs            ADD CONSTRAINT uq_test_runs_user_case           UNIQUE (user_id, case_id);
ALTER TABLE audit_events         ADD COLUMN IF NOT EXISTS idempotency_key TEXT;
ALTER TABLE audit_events         ADD CONSTRAINT uq_audit_idempotency             UNIQUE (user_id, request_id, idempotency_key) WHERE idempotency_key IS NOT NULL;
```

The function must also re-fetch `an1–an4` after conflict (like it does for `p1–p4`) so request idempotency keys are stable.

---

### F3 — 🟠 HIGH: No Validation That target_user_id Exists

**File:** `schema.sql` line 868 (`BEGIN`)

The function accepts any UUID and immediately inserts rows with `user_id = target_user_id REFERENCES auth.users(id)`. If the UUID does not exist, a FK violation is thrown — but it is uncaught and surfaces as a cryptic PostgreSQL error. There is also no authorization check that the caller is permitted to provision data for that specific UUID.

**Recommended fix** (add at function start, after `BEGIN`):
```sql
IF NOT EXISTS (SELECT 1 FROM auth.users WHERE id = target_user_id) THEN
  RAISE EXCEPTION 'seed_demo_data_for_user: user % does not exist in auth.users', target_user_id;
END IF;
```

---

### F4 — 🟠 HIGH: Hardcoded Demo Catalog UUID Grants Unconditional SELECT Bypass

**File:** `schema.sql` lines 91–104 (`products`), 156–168 (`supplier_terms`)

```sql
OR user_id = '00000000-0000-0000-0000-000000000001'::uuid
```

Any authenticated user reads **all rows owned by this UUID** without restriction. This is intentional for the demo catalog. The structural risk is:

1. If any real inventory data is accidentally inserted under this UUID, it becomes universally readable.
2. Any actor who can bypass the append-only trigger (see F5) and insert rows with this `user_id` could make those rows visible to all users.

**Configuration-dependent risk** — low in the current synthetic-only deployment.

**Recommended fix:** Replace the UUID bypass with an explicit `is_shared_catalog` boolean column:
```sql
ALTER TABLE products       ADD COLUMN IF NOT EXISTS is_shared_catalog BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE supplier_terms ADD COLUMN IF NOT EXISTS is_shared_catalog BOOLEAN NOT NULL DEFAULT false;
-- In SELECT policy: OR is_shared_catalog = true
-- In INSERT policy: WITH CHECK (NOT is_shared_catalog OR user_id = '...demo-uuid...')
```

---

### F5 — 🟠 HIGH: app.seed_cleanup GUC Is Session-Scoped, Not Transaction-Scoped

**File:** `schema.sql` lines 37–53; `seed.sql` lines 69, 84

```sql
SET app.seed_cleanup = 'true';   -- session-level (persists after COMMIT)
-- ... deletions ...
RESET app.seed_cleanup;           -- only reached if no exception thrown
```

`SET` (without `LOCAL`) persists for the **entire database session**. If any DELETE between lines 71–82 raises an exception (e.g., because `prevent_mutation()` fires for a different reason), the `RESET` on line 84 is never reached. The next query on the same pooled session can then DELETE from append-only tables unchallenged.

**Confirmed structural risk.** Exploitability depends on PgBouncer mode.

**Recommended fix:** Use `SET LOCAL` inside an explicit transaction:
```sql
BEGIN;
  SET LOCAL app.seed_cleanup = 'true';  -- expires at COMMIT/ROLLBACK automatically
  DELETE FROM test_runs            WHERE user_id = '00000000-0000-0000-0000-000000000001';
  -- ... all other deletes in dependency order ...
  DELETE FROM products             WHERE user_id = '00000000-0000-0000-0000-000000000001';
COMMIT;
```

---

### F6 — 🟠 HIGH: Duplicate audit_events Created on Every Function Call

**File:** `schema.sql` lines 972–982

Inside `seed_demo_data_for_user`, audit events are inserted with `gen_random_uuid()` as the ID and `ON CONFLICT DO NOTHING`. Since every call generates fresh UUIDs, the `ON CONFLICT` clause **never matches** and new rows are always inserted. A second call adds a second `proposed` event for each of rq1–rq4, a third call adds a third, etc. This directly pollutes the append-only audit trail for the user's requests.

The seed.sql file does not have this problem because it uses hardcoded UUIDs (`90000000-...`) and the cleanup block deletes them before re-inserting.

**Fix:** Add `idempotency_key` column (see F2) and use it in the function:
```sql
INSERT INTO audit_events (id, user_id, request_id, event_type, actor_id, details, idempotency_key)
VALUES (gen_random_uuid(), target_user_id, rq1, 'proposed', target_user_id, ..., 'seed-proposed-rq1')
ON CONFLICT (user_id, request_id, idempotency_key) DO NOTHING;
```

---

### F7 — 🟡 MEDIUM: Approver Can Approve Their Own Request

**File:** `schema.sql` lines 617–636 (`approvals_insert_approver`)

The INSERT policy correctly enforces approver identity and tenant scope, but is **missing a self-approval guard**:

| Check | Status |
|-------|--------|
| `approver_id = auth.uid()` | ✅ |
| Approver/admin role from `app_metadata` | ✅ |
| Request is in `pending_approval` status | ✅ |
| Request belongs to `approvals.user_id` | ✅ |
| Tenant scope matches | ✅ |
| `request_version_id` belongs to the request | ✅ |
| **`approver_id ≠ approvals.user_id`** | ❌ Missing |

An admin who also submits requests can approve their own requests. In a 4-eyes governance requirement, this entirely defeats the separation of duties.

**Recommended fix:**
```sql
-- Add one line to the WITH CHECK of approvals_insert_approver:
AND approver_id <> approvals.user_id
```

---

### F8 — 🟡 MEDIUM: Cross-User product_id / supplier_terms_id Injection into open_purchase_orders

**File:** `schema.sql` lines 275–278 (`open_orders_insert_own`)

The INSERT policy only checks `user_id = auth.uid()`. It does not verify that `product_id` or `supplier_terms_id` belong to the same user. A planner who discovers another user's `product_id` (e.g., from a shared catalog UUID or a disclosed UUID) can:

```sql
INSERT INTO open_purchase_orders (user_id, product_id, supplier_terms_id, ...)
VALUES (auth.uid(), <victim-product-id>, <victim-supplier-terms-id>, 9999, ...);
```

This succeeds (FK constraint only checks row existence, not ownership) and inflates the victim product's `eligible_incoming_quantity` — corrupting the TC3 calculation.

**Recommended fix:**
```sql
CREATE POLICY "open_orders_insert_own" ON open_purchase_orders FOR INSERT
  WITH CHECK (
    user_id = auth.uid()
    AND EXISTS (SELECT 1 FROM products p
                WHERE p.id = open_purchase_orders.product_id AND p.user_id = auth.uid())
    AND EXISTS (SELECT 1 FROM supplier_terms st
                WHERE st.id = open_purchase_orders.supplier_terms_id AND st.user_id = auth.uid())
  );
```

Apply the same fix to `open_orders_update_own`. The same gap exists in `analyses_insert_own` (`reorder_analyses.product_id`) and `requests_insert_own` (`reorder_requests.product_id`, `analysis_id`).

---

### F9 — 🟡 MEDIUM: auth.users INSERT Creates Incomplete GoTrue Record

**File:** `seed.sql` lines 31–51

The seed inserts a row in `auth.users` with `encrypted_password = NULL` and no corresponding row in `auth.identities`. GoTrue requires a matching `auth.identities` row for email/password authentication. This row cannot log in — confirmed and documented. However:

1. **GoTrue internal state inconsistency:** `aud = 'authenticated'` with no identity may trigger unexpected behavior in some GoTrue versions when listing users via the Admin API.
2. **Email delivery risk:** If an operator triggers a password reset via the Supabase Dashboard for `demo-catalog-owner@internal.local`, GoTrue may attempt email delivery.
3. **Future GoTrue versions:** Automatic email confirmation checks may fail on this row.

**Configuration-dependent risk.** The row is documented as non-functional. Lowest-risk fix is to remove the `auth.users` INSERT and replace the `user_id REFERENCES auth.users(id)` FK on catalog tables with a FK to a `public.catalog_owners` lookup table — a significant schema change deferred for Phase 10+.

---

### F10 — 🟡 MEDIUM: seed.sql Is Not Truly Re-Runnable If Cleanup Fails

**File:** `seed.sql` lines 90–531

Every INSERT in `seed.sql` after the cleanup block uses hardcoded UUIDs with **no `ON CONFLICT` clause**. If the cleanup block fails partway through (e.g., `prevent_mutation()` throws for an unexpected reason), the subsequent INSERTs will fail with primary key violations and abort the script.

The script header (line 6) states it is "safe to re-run" — this is conditionally true only if the cleanup block completes successfully.

**Recommended fix:** Add `ON CONFLICT (id) DO NOTHING` to every INSERT in the file:
```sql
INSERT INTO products (id, ...) VALUES ('10000000-...', ...) ON CONFLICT (id) DO NOTHING;
```

---

### F11 — 🟡 MEDIUM: request_versions INSERT Policy Does Not Enforce Sequential version_number

**File:** `schema.sql` lines 554–562 (`request_versions_insert_own`)

The policy verifies ownership but not that `version_number = max(existing) + 1`. A planner can insert version 9999 directly via the PostgREST REST API (`/rest/v1/request_versions`), creating a gap in the version sequence. An approver could then approve "version 2" while the planner has a version 9999 snapshot waiting — leading to approval of a stale or forged version.

**Recommended fix:**
```sql
-- Add to request_versions_insert_own WITH CHECK:
AND version_number = (
  SELECT COALESCE(MAX(rv2.version_number), 0) + 1
  FROM request_versions rv2 WHERE rv2.request_id = request_versions.request_id
)
```

---

### F12 — 🟢 LOW: audit_events.actor_id Is Nullable; Seed Function Spoofs actor_id

**File:** `schema.sql` lines 702, 972–981

```sql
actor_id    UUID   REFERENCES auth.users(id),  -- nullable
```

The INSERT policy requires `actor_id = auth.uid()`, preventing `NULL` inserts via the API. However, `seed_demo_data_for_user` runs SECURITY DEFINER, bypassing RLS, and inserts audit events with `actor_id = target_user_id` — not the actual caller. This means all seed-provisioned audit events have a **spoofed actor identity** in the audit trail.

**Recommended fix:**
- Change column to `NOT NULL`.
- In the seed function, use a distinguished system UUID (e.g., `'00000000-0000-0000-0000-000000000000'`) as actor and add a `source TEXT DEFAULT 'application'` column to distinguish seeded vs. real events.

---

### F13 — 🟢 LOW: NULL tenant_id Approver Has Global Read Access to All Records

**File:** `schema.sql` lines 97–103 and equivalent in all 12 tables

Every approver SELECT policy contains:
```sql
OR (tenant_id IS NULL AND (auth.jwt() -> 'app_metadata' ->> 'tenant_id') IS NULL)
```

An approver granted the `approver` role in `app_metadata` **without an explicit `tenant_id`** matches this branch and can read **every row where `tenant_id IS NULL`** — which is every row by default (the column defaults to `NULL`). This is a global cross-user read, not scoped to the approver's own records.

**Configuration-dependent:** Low risk in this single-tenant demo. Critical risk in any real multi-tenant deployment.

**Recommended fix:** Require non-null `tenant_id` for approver scoping, or auto-assign a system `tenant_id` on INSERT via a trigger.

---

### F14 — 🟢 LOW: SETUP.md Gaps — REVOKE EXECUTE and Role Revocation Undocumented

**File:** `supabase/SETUP.md` (role assignment section)

1. `REVOKE EXECUTE ON FUNCTION public.seed_demo_data_for_user FROM PUBLIC` is **not documented** anywhere. Per F1, this is a CRITICAL omission.
2. Role revocation SQL (undoing the `UPDATE auth.users SET raw_app_meta_data = ...`) is not shown.
3. The GoTrue Admin API (`updateUserById`) is not mentioned as a safer alternative to raw SQL (avoids accidentally overwriting `app_metadata` fields if the existing value is `NULL`).
4. No step shows how to audit which users currently have elevated `approver` or `admin` roles.

**Recommended additions:**
```sql
-- Audit current role assignments:
SELECT id, email, raw_app_meta_data->>'role' AS role
FROM auth.users
WHERE raw_app_meta_data->>'role' IN ('approver', 'admin');

-- Revoke a role:
UPDATE auth.users
SET raw_app_meta_data = raw_app_meta_data - 'role'
WHERE id = '<user-uuid>';
```

---

## Idempotency Analysis: seed_demo_data_for_user

| Table | ON CONFLICT | Safe on 2nd call? | Root cause |
|-------|------------|-------------------|------------|
| `products` | `(user_id, sku) DO NOTHING` + re-fetch | ✅ | Unique constraint + re-fetch |
| `supplier_terms` | `DO NOTHING` (PK only) | ❌ | New UUID `s1–s4` each call |
| `sales_history` | `DO NOTHING` (PK only) | ❌ | New UUID `sh1–sh4` each call |
| `open_purchase_orders` | `DO NOTHING` (PK only) | ❌ | New UUID `po3` each call |
| `source_evidence` | `DO NOTHING` (PK only) | ❌ | New UUID `ev1–ev4` each call |
| `reorder_analyses` | `DO NOTHING` (PK only) | ❌ | New UUID `an1–an4` each call |
| `reorder_requests` | `(user_id, idempotency_key)` | ❌* | Key contains `an1::text` which changes |
| `request_versions` | `DO NOTHING` (PK only) | ❌* | `rq1–rq4` changes when requests conflict |
| `audit_events` | `DO NOTHING` (PK only) | ❌ | New UUID per call, always inserts |
| `test_runs` | `DO NOTHING` (PK only) | ❌ | New UUID `tr1–tr4` each call |

---

## FK Cross-Ownership Analysis

| FK Relationship | User ownership cross-check in policy? |
|----------------|--------------------------------------|
| `open_purchase_orders.product_id → products.id` | ❌ Not checked |
| `open_purchase_orders.supplier_terms_id → supplier_terms.id` | ❌ Not checked |
| `reorder_analyses.product_id → products.id` | ❌ Not checked |
| `reorder_requests.analysis_id → reorder_analyses.id` | ❌ Not checked |
| `reorder_requests.product_id → products.id` | ❌ Not checked |
| `approvals.request_version_id → request_versions.id` | ✅ Lines 631–635 enforce `rv.request_id = approvals.request_id` |

---

## Prioritized Remediation Plan

| Priority | Finding | Minimal SQL Action |
|----------|---------|-------------------|
| 1 | **F1** | `REVOKE EXECUTE ON FUNCTION public.seed_demo_data_for_user(UUID) FROM PUBLIC, authenticated, anon;` |
| 2 | **F7** | Add `AND approver_id <> approvals.user_id` to `approvals_insert_approver` WITH CHECK |
| 3 | **F8** | Add `EXISTS` ownership sub-selects to `open_orders_insert_own` and `open_orders_update_own` |
| 4 | **F2** | Add unique constraints to `supplier_terms`, `sales_history`, `open_purchase_orders`, `test_runs`; add `idempotency_key` to `audit_events`; re-fetch `an1–an4` after conflict |
| 5 | **F5** | Wrap seed.sql cleanup block in `BEGIN; SET LOCAL app.seed_cleanup='true'; ... COMMIT;` |
| 6 | **F3** | Add existence check for `target_user_id` at top of function body |
| 7 | **F10** | Add `ON CONFLICT (id) DO NOTHING` to every INSERT in seed.sql |
| 8 | **F6** | Use `idempotency_key` in function audit event inserts |
| 9 | **F13** | Require non-null `tenant_id` for approver-scoped SELECT (or add INSERT trigger to auto-assign) |
| 10 | **F12** | Change `actor_id` to `NOT NULL`; use system UUID in seed function |
| 11 | **F11** | Add sequential `version_number` enforcement to `request_versions_insert_own` WITH CHECK |
| 12 | **F4** | Replace hardcoded UUID bypass with `is_shared_catalog BOOLEAN` column |
| 13 | **F14** | Add REVOKE, audit query, and role-revocation SQL to SETUP.md |
| 14 | **F9** | Evaluate removing `auth.users` INSERT from seed.sql (long-term architecture change) |

---

## SQL Test Cases to Validate Fixes

Run these **after fixes are applied** using user-role JWTs (not service_role). Do not run against production data.

```sql
-- TEST 1: seed function not callable by authenticated users (fix F1)
-- Via PostgREST with planner JWT:
-- POST /rest/v1/rpc/seed_demo_data_for_user {"target_user_id": "..."}
-- Expected: HTTP 403 — permission denied for function seed_demo_data_for_user

-- TEST 2: Self-approval blocked (fix F7)
-- Run as approver who also owns a pending_approval request:
INSERT INTO approvals (user_id, request_id, request_version_id, approver_id, action)
VALUES (auth.uid(), '<own-request-id>', '<version-id>', auth.uid(), 'approved');
-- Expected: ERROR: new row violates row-level security policy for table "approvals"

-- TEST 3: Cross-user open_purchase_orders injection blocked (fix F8)
-- Run as planner-A, using planner-B's product UUID:
INSERT INTO open_purchase_orders
  (user_id, product_id, supplier_terms_id, ordered_quantity, received_quantity,
   expected_arrival_date, status, order_reference)
VALUES (auth.uid(), '<planner-B-product-uuid>', '<planner-B-terms-uuid>',
        10, 0, current_date + 7, 'open', 'TEST-INJECT');
-- Expected (after fix): RLS violation; currently: may SUCCEED

-- TEST 4: seed function idempotency (fix F2)
-- Run twice in SQL Editor (postgres context):
SELECT public.seed_demo_data_for_user('<user-uuid>');
SELECT public.seed_demo_data_for_user('<user-uuid>');
SELECT count(*) FROM supplier_terms  WHERE user_id = '<user-uuid>';  -- Expected: 4 (not 8)
SELECT count(*) FROM sales_history   WHERE user_id = '<user-uuid>';  -- Expected: 4 (not 8)
SELECT count(*) FROM audit_events    WHERE user_id = '<user-uuid>';  -- Expected: 4 (not 8)

-- TEST 5: NULL-tenant approver read scope (fix F13)
-- Grant approver role to a user with no tenant_id, then:
SELECT count(*) FROM reorder_requests;
-- Expected (after fix): 0 rows; currently: ALL rows where tenant_id IS NULL

-- TEST 6: app.seed_cleanup cannot be abused by application sessions (fix F5)
-- As any role, set the GUC then try to delete:
SELECT set_config('app.seed_cleanup', 'true', false);
DELETE FROM audit_events WHERE id = '<any-id>';
-- Expected: trigger should still block if the transaction was not started with SET LOCAL
-- (behavior depends on PgBouncer mode — verify manually)

-- TEST 7: actor_id NOT NULL enforced (fix F12)
INSERT INTO audit_events (user_id, request_id, event_type, actor_id, details)
VALUES (auth.uid(), '<request-id>', 'proposed', NULL, '{}');
-- Expected (after fix): ERROR: null value in column "actor_id" violates not-null constraint

-- TEST 8: version_number must be sequential (fix F11)
-- As request owner, insert a gap version:
INSERT INTO request_versions (user_id, request_id, version_number, snapshot)
VALUES (auth.uid(), '<request-id>', 9999, '{}');
-- Expected (after fix): RLS policy violation
```

---

## Summary

> [!CAUTION]
> The database **cannot be declared secure** without live testing with real JWTs against the deployed Supabase project. The findings above are confirmed through static code analysis only.

The core lifecycle design (version-bound approvals, append-only audit trail, idempotent request creation via `idempotency_key`) is **architecturally sound**. The three most urgent confirmed issues are:

1. **F1** — `seed_demo_data_for_user` is an unauthenticated data-injection vector. Fix with a single `REVOKE EXECUTE` before any user traffic reaches the database.
2. **F2** — The function corrupts demand calculations on second call. Adding unique constraints + analysis re-fetches is required before the function can be considered safe to use.
3. **F7** — Any approver can approve their own requests. A single `AND approver_id <> approvals.user_id` line closes this gap.
