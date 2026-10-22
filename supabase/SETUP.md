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
| `SUPABASE_SECRET_KEY` | Settings → API → `service_role` (secret) | **Never expose to the browser** |
| `VITE_SUPABASE_URL` | Same as `SUPABASE_URL` | Used by the React frontend |
| `VITE_SUPABASE_PUBLISHABLE_KEY` | Settings → API → `anon` (public) | Safe for the browser |

---

## Step 2 — Apply the schema

1. Go to your Supabase project → **SQL Editor**.
2. Open `supabase/schema.sql` from this repository.
3. Paste the entire content and click **Run**.
4. The script is idempotent — safe to re-run if you need to update policies.

> **RLS note:** Row Level Security is enabled on all tables. Policies are
> ownership-based (`user_id = auth.uid()`). No table grants unrestricted
> access to all authenticated users.

---

## Step 3 — Load synthetic seed data

> Run with the `postgres` / service-role context only (not anon key).
> The SQL Editor in the Supabase dashboard uses the `postgres` role by default.

1. Open `supabase/seed.sql` in the SQL Editor.
2. Click **Run**.
3. The script:
   - Creates a demo auth user (`demo@example.com`, UUID `00000000-…-0001`)
   - Seeds TC1–TC4 products, suppliers, sales history, analyses and requests
   - Is safe to re-run (deletes and re-inserts demo rows only)

---

## Step 4 — Enable Email Auth (optional for demo)

1. **Authentication → Providers → Email** — confirm it is enabled.
2. You can sign up with the demo email `demo@example.com` via the frontend, or use any test account you create.

---

## Step 5 — Verify

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

Re-run `supabase/seed.sql` — it deletes and re-inserts all rows owned by the demo user without touching other users' data.

---

## Free-tier constraints

| Resource | Supabase Free Limit | This project |
|----------|-------------------|--------------|
| Database size | 500 MB | < 1 MB (seed only) |
| Auth users | Unlimited (for projects) | 1 demo user |
| API requests | 500 MB egress / month | Minimal |
| Row Level Security | Supported | Enabled on all 12 tables |

No paid Supabase features are used.
