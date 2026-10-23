# Supabase Setup Instructions

> **Demo data only.** This project uses synthetic data. No real inventory or supplier data is stored.

---

## Prerequisites

- A free [Supabase](https://supabase.com) account and project (Hobby / free tier)
- The Supabase project URL and API keys (available in **Project Settings → API**)

---

## Step 1 — Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in:

| Variable | Where to find it | Notes |
|----------|-----------------|-------|
| `SUPABASE_URL` | Settings → API → Project URL | e.g. `https://abcxyz.supabase.co` |
| `SUPABASE_SECRET_KEY` | Settings → API → `service_role` (secret) | **Backend only; never expose to the browser** |
| `SUPABASE_PUBLISHABLE_KEY` | Settings → API → `anon` (public) | Optional backend key for scoped user requests |
| `SUPABASE_JWT_SECRET` | Settings → API → JWT Settings → `JWT Secret` | Optional: enables fast local cryptographic verification (HS256) |
| `VITE_SUPABASE_URL` | Same as `SUPABASE_URL` | Used by the React frontend |
| `VITE_SUPABASE_PUBLISHABLE_KEY` | Settings → API → `anon` (public) | Safe for the browser |
| `REPOSITORY_BACKEND` | — | Set to `supabase` for production. Use `memory` only for intentional in-memory demo/test. Default `auto` falls back to `memory` if credentials are missing. |

---

## Step 2 — Configure Supabase Auth Settings

In your Supabase Dashboard:
1. **Email Confirmation:** Go to **Authentication → Providers → Email**.
   - *For Local Testing / Staging:* Disable **"Confirm email"** to allow newly registered users to sign in immediately without waiting for SMTP delivery.
   - *For Production:* Keep **"Confirm email"** enabled and configure a custom SMTP provider (Settings → Auth → SMTP Settings).
2. **JWT Secret:**
   - Go to **Project Settings → API → JWT Settings**.
   - Copy the **JWT Secret** and set it as `SUPABASE_JWT_SECRET` in your `.env`.
   - When set, FastAPI cryptographically verifies tokens locally (signature, expiration, audience, issuer) in <1ms without network calls.

---

## Step 3 — Apply the schema & RLS policies

1. Go to your Supabase project → **SQL Editor**.
2. Open `supabase/schema.sql` from this repository.
3. Paste the entire content and click **Run**.
4. The script is idempotent — safe to re-run whenever policies are updated.

> **RLS Architecture & Security Guarantees:**
> - Row Level Security is enabled on all 12 tables.
> - **`reorder_requests`:** Planners can only INSERT and UPDATE requests in `'pending_approval'` or `'draft'` status. Planners are strictly blocked at the RLS layer from self-transitioning requests to `'approved'` or `'submitted_or_simulated'`. Only users with `'approver'` or `'admin'` in `auth.jwt() -> 'app_metadata'` can approve or reject.
> - **`approvals`:** An approval record requires `approver_id = auth.uid()` AND an elevated role (`approver` or `admin`). An approval can only be inserted for a request in `'pending_approval'` status whose version matches `request_version_id`. Forged approvals are completely rejected by PostgreSQL RLS.
> - **`audit_events`:** Append-only (triggers block `UPDATE` and `DELETE`). `actor_id = auth.uid()` is enforced so audit actors cannot be spoofed.
> - **Strict Multi-Tenant Isolation:** All tables have `tenant_id` columns and indexes. Approver access is strictly scoped:
>   `((tenant_id IS NOT NULL AND tenant_id::text = (auth.jwt() -> 'app_metadata' ->> 'tenant_id')) OR (tenant_id IS NULL AND (auth.jwt() -> 'app_metadata' ->> 'tenant_id') IS NULL))`.
>   Lenient `OR tenant_id IS NULL` wildcards are eliminated, preventing cross-tenant leakage of unassigned data.

---

## Step 4 — Load synthetic seed data

> Run all SQL in the Supabase SQL Editor with the `postgres` / service-role context.
> The SQL Editor uses `postgres` role by default — this bypasses RLS intentionally.

### 4a. Load the shared demo catalog (seed.sql)

This seeds TC1–TC4 products, supplier terms, analyses, and related data under the
shared demo catalog owner (`00000000-0000-0000-0000-000000000001`).

1. Open `supabase/seed.sql` in the SQL Editor and click **Run**.
2. The script is safe to re-run — it deletes and re-inserts demo rows using a
   session-level bypass flag (`SET app.seed_cleanup = 'true'`).

> ⚠️ **Important:** The `auth.users` row inserted by `seed.sql` is a **shared
> catalog placeholder only** — not a real login account. It has `NULL`
> `encrypted_password` and no `auth.identities` row, so it **cannot authenticate
> via Supabase Auth**. Real registered users (below) will still see the shared
> TC1–TC4 products and supplier terms because the RLS policies include
> `OR user_id = '00000000-0000-0000-0000-000000000001'::uuid` on those tables.

### 4b. Provision demo data for real registered users

After a real user registers via the application sign-up page:

1. Find their UUID in **Dashboard → Authentication → Users**.
2. Run in SQL Editor:

```sql
SELECT public.seed_demo_data_for_user('<PASTE-USER-UUID-HERE>');
```

This creates TC1–TC4 products, analyses, reorder requests, versions, audit events,
and test runs owned by that specific user. The function is idempotent
(`ON CONFLICT DO NOTHING`) and safe to run multiple times.

3. The user can now log in, view the dashboard, and use the approval queue immediately.

---

## Step 5 — Configure User Roles & Permissions

Supabase Auth accounts default to the `planner` role upon self-registration. Privileged roles (`approver` or `admin`) must be assigned via server-controlled `app_metadata` to prevent privilege escalation.

### Assigning an Approver or Admin Role

Run this query in the Supabase **SQL Editor**:

```sql
-- Grant 'approver' role to a verified user
UPDATE auth.users
SET raw_app_meta_data = coalesce(raw_app_meta_data, '{}'::jsonb) || '{"role": "approver"}'::jsonb
WHERE email = 'approver@yourcompany.com';

-- Grant 'admin' role
UPDATE auth.users
SET raw_app_meta_data = coalesce(raw_app_meta_data, '{}'::jsonb) || '{"role": "admin"}'::jsonb
WHERE email = 'admin@yourcompany.com';
```

### Optional: Assigning a Tenant Scope

```sql
-- Scope an approver to a specific tenant UUID
UPDATE auth.users
SET raw_app_meta_data = coalesce(raw_app_meta_data, '{}'::jsonb) || '{"tenant_id": "11111111-1111-1111-1111-111111111111"}'::jsonb
WHERE email = 'approver@tenant1.com';
```

---

## Step 6 — Verify

Run this in the SQL Editor to confirm tables and row counts:

```sql
SELECT
  schemaname, tablename,
  (SELECT count(*) FROM information_schema.tables
   WHERE table_schema = 'public' AND table_name = t.tablename) AS exists
FROM (
  VALUES
    ('public','products'),('public','supplier_terms'),('public','sales_history'),
    ('public','open_purchase_orders'),('public','source_evidence'),
    ('public','reorder_analyses'),('public','reorder_requests'),
    ('public','request_versions'),('public','approvals'),
    ('public','verification_results'),('public','audit_events'),
    ('public','test_runs')
) AS t(schemaname, tablename);

-- Check seed counts (should be ≥4 for most tables)
SELECT 'products' AS tbl, count(*) FROM products
  WHERE user_id = '00000000-0000-0000-0000-000000000001'
UNION ALL
SELECT 'reorder_analyses', count(*) FROM reorder_analyses
  WHERE user_id = '00000000-0000-0000-0000-000000000001'
UNION ALL
SELECT 'test_runs', count(*) FROM test_runs
  WHERE user_id = '00000000-0000-0000-0000-000000000001';
```

Expected: 4 products, 4 analyses, 4 test_runs.

---

## Resetting demo data

Re-run `supabase/seed.sql` from the SQL Editor — it deletes and re-inserts all rows
owned by the shared catalog owner without touching real users' data.

To reset a specific real user's demo data:
```sql
-- Delete their data first (requires seed bypass flag)
SET app.seed_cleanup = 'true';
DELETE FROM reorder_requests WHERE user_id = '<USER-UUID>';
-- ... repeat for other tables as needed
RESET app.seed_cleanup;
-- Then re-seed:
SELECT public.seed_demo_data_for_user('<USER-UUID>');
```

---

## Free-tier constraints

| Resource | Supabase Free Limit | This project |
|----------|-------------------|--------------|
| Database size | 500 MB | < 1 MB (seed only) |
| Auth users | Unlimited (for projects) | 1 demo user |
| API requests | 500 MB egress / month | Minimal |
| Row Level Security | Supported | Enabled on all 12 tables |

No paid Supabase features are used.
