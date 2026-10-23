-- ═══════════════════════════════════════════════════════════════════════════════
-- Inventory Reorder Planner — Synthetic Seed Data (TC1–TC4)
-- Phase 2 — Demo data only. NOT real inventory.
--
-- PREREQUISITES:
--   1. Run supabase/schema.sql first.
--   2. Execute this script via the Supabase SQL Editor (uses postgres role,
--      which bypasses RLS) OR via psql with service-role credentials.
--   3. The demo owner UUID (00000000-0000-0000-0000-000000000001) below seeds
--      the SHARED CATALOG only — products, supplier terms, analyses visible to
--      all authenticated users. Real registered users get their own request data
--      via seed_demo_data_for_user() (see schema.sql / SETUP.md).
-- ═══════════════════════════════════════════════════════════════════════════════

-- ── 0. Shared Catalog Owner row in auth.users ─────────────────────────────────
--
-- ⚠️  IMPORTANT: This row creates the shared demo catalog owner ONLY.
--     This row is NOT a real login account.  Direct auth.users insertion
--     CANNOT be used to create real registered accounts because:
--       - GoTrue requires a matching row in auth.identities with a bcrypt
--         password hash; inserting without it breaks email/password login.
--       - The NULL encrypted_password means this row cannot authenticate.
--
--  For real demo users (with working login), use:
--       SELECT public.seed_demo_data_for_user('<USER-UUID>');
--    after the user registers normally via the application sign-up page.
--    Their UUID is shown in Supabase Dashboard → Authentication → Users.
--
--  For approver/admin role assignment to a real user, see SETUP.md.
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO auth.users (
  id, instance_id, aud, role, email,
  encrypted_password, email_confirmed_at,
  created_at, updated_at,
  confirmation_token, recovery_token,
  email_change_token_new, email_change,
  raw_app_meta_data, raw_user_meta_data, is_super_admin
)
VALUES (
  '00000000-0000-0000-0000-000000000001',
  '00000000-0000-0000-0000-000000000000',
  'authenticated', 'authenticated',
  'demo-catalog-owner@internal.local',        -- Not a real login address
  NULL,                                       -- No password — not intended for auth login
  now(), now(), now(),
  '', '', '', '',
  '{"provider":"email","providers":["email"]}'::jsonb,
  '{"name":"Demo Catalog Owner (seed only)"}'::jsonb,
  false
)
ON CONFLICT (id) DO NOTHING;

-- Convenience: constant for the shared catalog owner UUID
DO $$ BEGIN
  PERFORM set_config('seed.demo_user_id',
    '00000000-0000-0000-0000-000000000001', true);
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Helper: wipe existing seed rows so the script is safe to re-run.
-- Uses explicit UUIDs — never touches rows owned by real users.
--
-- D3 fix: audit_events, approvals, and request_versions carry prevent_mutation()
-- triggers that block ALL DELETEs in production.  The trigger checks a
-- session-level GUC (app.seed_cleanup) and allows the DELETE only when it is
-- set to 'true'.  We set it here and RESET it immediately after the cleanup
-- block so the protection is restored for all subsequent statements.
-- ─────────────────────────────────────────────────────────────────────────────
SET app.seed_cleanup = 'true';   -- enable seed-only bypass on prevent_mutation()

DELETE FROM test_runs            WHERE user_id = '00000000-0000-0000-0000-000000000001';
DELETE FROM audit_events         WHERE user_id = '00000000-0000-0000-0000-000000000001';
DELETE FROM verification_results WHERE user_id = '00000000-0000-0000-0000-000000000001';
DELETE FROM approvals            WHERE user_id = '00000000-0000-0000-0000-000000000001';
DELETE FROM request_versions     WHERE user_id = '00000000-0000-0000-0000-000000000001';
DELETE FROM reorder_requests     WHERE user_id = '00000000-0000-0000-0000-000000000001';
DELETE FROM reorder_analyses     WHERE user_id = '00000000-0000-0000-0000-000000000001';
DELETE FROM source_evidence      WHERE user_id = '00000000-0000-0000-0000-000000000001';
DELETE FROM open_purchase_orders WHERE user_id = '00000000-0000-0000-0000-000000000001';
DELETE FROM sales_history        WHERE user_id = '00000000-0000-0000-0000-000000000001';
DELETE FROM supplier_terms       WHERE user_id = '00000000-0000-0000-0000-000000000001';
DELETE FROM products             WHERE user_id = '00000000-0000-0000-0000-000000000001';

RESET app.seed_cleanup;           -- restore immutability protection

-- ═══════════════════════════════════════════════════════════════════════════════
-- PRODUCTS (one per test case)
-- ═══════════════════════════════════════════════════════════════════════════════
-- TC1: Low stock, no incoming order
INSERT INTO products (id, user_id, sku, name, unit, currency, current_stock)
VALUES (
  '10000000-0000-0000-0000-000000000001',
  '00000000-0000-0000-0000-000000000001',
  'SKU-001', 'Widget Alpha', 'each', 'USD', 20
);

-- TC2: Same base scenario but supplier sells in cases of 12
INSERT INTO products (id, user_id, sku, name, unit, currency, current_stock)
VALUES (
  '10000000-0000-0000-0000-000000000002',
  '00000000-0000-0000-0000-000000000001',
  'SKU-002', 'Widget Beta', 'each', 'USD', 25
);

-- TC3: Pending incoming order covers part of shortfall
INSERT INTO products (id, user_id, sku, name, unit, currency, current_stock)
VALUES (
  '10000000-0000-0000-0000-000000000003',
  '00000000-0000-0000-0000-000000000001',
  'SKU-003', 'Widget Gamma', 'each', 'USD', 20
);

-- TC4: Same base as TC1 but price has just risen 20%; budget is $400
INSERT INTO products (id, user_id, sku, name, unit, currency, current_stock)
VALUES (
  '10000000-0000-0000-0000-000000000004',
  '00000000-0000-0000-0000-000000000001',
  'SKU-004', 'Widget Delta', 'each', 'USD', 20
);

-- ═══════════════════════════════════════════════════════════════════════════════
-- SUPPLIER TERMS
-- ═══════════════════════════════════════════════════════════════════════════════
-- TC1: pack_size=1, unit_price=$10.00
INSERT INTO supplier_terms
  (id, user_id, product_id, supplier_name, lead_time_days, pack_size, unit_price, currency, price_updated_at)
VALUES (
  '20000000-0000-0000-0000-000000000001',
  '00000000-0000-0000-0000-000000000001',
  '10000000-0000-0000-0000-000000000001',
  'Acme Supplies', 14, 1, 10.00, 'USD',
  now() - interval '7 days'
);

-- TC2: pack_size=12 (case-only supplier), unit_price=$10.00
INSERT INTO supplier_terms
  (id, user_id, product_id, supplier_name, lead_time_days, pack_size, unit_price, currency, price_updated_at)
VALUES (
  '20000000-0000-0000-0000-000000000002',
  '00000000-0000-0000-0000-000000000001',
  '10000000-0000-0000-0000-000000000002',
  'Bulk Co', 14, 12, 10.00, 'USD',
  now() - interval '7 days'
);

-- TC3: pack_size=1, unit_price=$10.00
INSERT INTO supplier_terms
  (id, user_id, product_id, supplier_name, lead_time_days, pack_size, unit_price, currency, price_updated_at)
VALUES (
  '20000000-0000-0000-0000-000000000003',
  '00000000-0000-0000-0000-000000000001',
  '10000000-0000-0000-0000-000000000003',
  'Global Trade', 14, 1, 10.00, 'USD',
  now() - interval '7 days'
);

-- TC4: pack_size=1, unit_price=$12.00 (was $10.00; 20% increase applied today)
--      budget_available=$400; new cost=36×$12=$432 → over budget → needs_review
INSERT INTO supplier_terms
  (id, user_id, product_id, supplier_name, lead_time_days, pack_size, unit_price, currency, price_updated_at)
VALUES (
  '20000000-0000-0000-0000-000000000004',
  '00000000-0000-0000-0000-000000000001',
  '10000000-0000-0000-0000-000000000004',
  'Acme Supplies', 14, 1, 12.00, 'USD',
  now()                               -- price updated TODAY (triggers budget review)
);

-- ═══════════════════════════════════════════════════════════════════════════════
-- SALES HISTORY  (30-day window ending yesterday; 120 units → 4 units/day)
-- ═══════════════════════════════════════════════════════════════════════════════
INSERT INTO sales_history
  (id, user_id, product_id, period_start, period_end, total_units_sold, days_in_period)
VALUES
  -- TC1
  ('30000000-0000-0000-0000-000000000001',
   '00000000-0000-0000-0000-000000000001',
   '10000000-0000-0000-0000-000000000001',
   current_date - interval '30 days', current_date - interval '1 day', 120, 30),
  -- TC2
  ('30000000-0000-0000-0000-000000000002',
   '00000000-0000-0000-0000-000000000001',
   '10000000-0000-0000-0000-000000000002',
   current_date - interval '30 days', current_date - interval '1 day', 120, 30),
  -- TC3
  ('30000000-0000-0000-0000-000000000003',
   '00000000-0000-0000-0000-000000000001',
   '10000000-0000-0000-0000-000000000003',
   current_date - interval '30 days', current_date - interval '1 day', 120, 30),
  -- TC4
  ('30000000-0000-0000-0000-000000000004',
   '00000000-0000-0000-0000-000000000001',
   '10000000-0000-0000-0000-000000000004',
   current_date - interval '30 days', current_date - interval '1 day', 120, 30);

-- ═══════════════════════════════════════════════════════════════════════════════
-- OPEN PURCHASE ORDERS
-- Only TC3 has an open order (24 units confirmed, arriving in 10 days).
-- TC1, TC2, TC4: no open orders → eligible_incoming_quantity = 0
-- ═══════════════════════════════════════════════════════════════════════════════
INSERT INTO open_purchase_orders
  (id, user_id, product_id, supplier_terms_id,
   ordered_quantity, received_quantity,
   expected_arrival_date, status, order_reference)
VALUES (
  '40000000-0000-0000-0000-000000000003',
  '00000000-0000-0000-0000-000000000001',
  '10000000-0000-0000-0000-000000000003',  -- Widget Gamma (TC3)
  '20000000-0000-0000-0000-000000000003',
  24, 0,                                   -- 24 ordered, 0 received
  current_date + interval '10 days',       -- arrives within 14-day lead time ✓
  'confirmed',                             -- status = confirmed → eligible
  'PO-GAMMA-001'
);

-- ═══════════════════════════════════════════════════════════════════════════════
-- SOURCE EVIDENCE  (one mock_source record per test case)
-- ═══════════════════════════════════════════════════════════════════════════════
INSERT INTO source_evidence
  (id, user_id, source_type, source_url, retrieved_at, source_timestamp, fields_used, raw_data)
VALUES
  -- TC1
  ('50000000-0000-0000-0000-000000000001',
   '00000000-0000-0000-0000-000000000001',
   'mock_source', NULL, now(), now() - interval '1 hour',
   ARRAY['current_stock','average_daily_demand','lead_time_days','unit_price'],
   '{"note":"Synthetic data — TC1 (demo only)","sku":"SKU-001"}'::jsonb),
  -- TC2
  ('50000000-0000-0000-0000-000000000002',
   '00000000-0000-0000-0000-000000000001',
   'mock_source', NULL, now(), now() - interval '1 hour',
   ARRAY['current_stock','average_daily_demand','lead_time_days','unit_price','pack_size'],
   '{"note":"Synthetic data — TC2 (demo only)","sku":"SKU-002","pack_size":12}'::jsonb),
  -- TC3
  ('50000000-0000-0000-0000-000000000003',
   '00000000-0000-0000-0000-000000000001',
   'mock_source', NULL, now(), now() - interval '1 hour',
   ARRAY['current_stock','average_daily_demand','lead_time_days','unit_price','open_order_qty'],
   '{"note":"Synthetic data — TC3 (demo only)","sku":"SKU-003","open_po":"PO-GAMMA-001","eligible_incoming":24}'::jsonb),
  -- TC4
  ('50000000-0000-0000-0000-000000000004',
   '00000000-0000-0000-0000-000000000001',
   'mock_source', NULL, now(), now(),
   ARRAY['current_stock','average_daily_demand','lead_time_days','unit_price','budget_available'],
   '{"note":"Synthetic data — TC4 (demo only)","sku":"SKU-004","previous_price":10.00,"new_price":12.00,"price_change_pct":20,"budget":400.00}'::jsonb);

-- ═══════════════════════════════════════════════════════════════════════════════
-- REORDER ANALYSES
-- All calculations are deterministic; no LLM involvement.
--
-- Shared formula:
--   lead_time_demand = average_daily_demand × lead_time_days = 4 × 14 = 56
--   net_shortfall    = max(0, lead_time_demand + safety_stock - stock - eligible_incoming)
--   proposed_qty     = pack_size × ceil(shortfall / pack_size)
--   estimated_cost   = proposed_qty × unit_price
-- ═══════════════════════════════════════════════════════════════════════════════

-- ── TC1: No incoming order ────────────────────────────────────────────────────
-- shortfall = 56 + 0 - 20 - 0 = 36
-- proposed  = ceil(36/1)×1    = 36
-- cost      = 36 × $10        = $360.00   budget $500 → ok
INSERT INTO reorder_analyses (
  id, user_id, product_id, calculation_version, input_snapshot,
  average_daily_demand, lead_time_days, lead_time_demand,
  safety_stock_target, usable_available_stock, eligible_incoming_quantity,
  net_shortfall, pack_size, proposed_order_quantity,
  unit_price, estimated_cost, budget_available, budget_status,
  analysis_status, status_reason, evidence_ids
) VALUES (
  '60000000-0000-0000-0000-000000000001',
  '00000000-0000-0000-0000-000000000001',
  '10000000-0000-0000-0000-000000000001',
  '1.0.0',
  jsonb_build_object(
    'sku','SKU-001','product_id','10000000-0000-0000-0000-000000000001',
    'average_daily_demand',4,'demand_window_days',30,'lead_time_days',14,
    'usable_available_stock',20,'safety_stock_target',0,'safety_stock_was_defaulted',true,
    'eligible_incoming_quantity',0,'incoming_order_ids','[]'::jsonb,
    'pack_size',1,'moq',null,'unit_price',10.00,'currency','USD',
    'budget_available',500.00,'supplier_terms_id','20000000-0000-0000-0000-000000000001',
    'source_evidence_ids',jsonb_build_array('50000000-0000-0000-0000-000000000001'),
    'snapshot_at',now()
  ),
  4, 14, 56,
  0, 20, 0,
  36, 1, 36,
  10.00, 360.00, 500.00, 'ok',
  'ready', NULL,
  ARRAY['50000000-0000-0000-0000-000000000001']::uuid[]
);

-- ── TC2: Case-only supplier (pack_size=12) ────────────────────────────────────
-- shortfall = 56 + 0 - 25 - 0 = 31
-- proposed  = ceil(31/12)×12  = 3×12 = 36
-- cost      = 36 × $10        = $360.00   budget $500 → ok
INSERT INTO reorder_analyses (
  id, user_id, product_id, calculation_version, input_snapshot,
  average_daily_demand, lead_time_days, lead_time_demand,
  safety_stock_target, usable_available_stock, eligible_incoming_quantity,
  net_shortfall, pack_size, proposed_order_quantity,
  unit_price, estimated_cost, budget_available, budget_status,
  analysis_status, status_reason, evidence_ids
) VALUES (
  '60000000-0000-0000-0000-000000000002',
  '00000000-0000-0000-0000-000000000001',
  '10000000-0000-0000-0000-000000000002',
  '1.0.0',
  jsonb_build_object(
    'sku','SKU-002','product_id','10000000-0000-0000-0000-000000000002',
    'average_daily_demand',4,'demand_window_days',30,'lead_time_days',14,
    'usable_available_stock',25,'safety_stock_target',0,'safety_stock_was_defaulted',true,
    'eligible_incoming_quantity',0,'incoming_order_ids','[]'::jsonb,
    'pack_size',12,'moq',null,'unit_price',10.00,'currency','USD',
    'budget_available',500.00,'supplier_terms_id','20000000-0000-0000-0000-000000000002',
    'source_evidence_ids',jsonb_build_array('50000000-0000-0000-0000-000000000002'),
    'snapshot_at',now()
  ),
  4, 14, 56,
  0, 25, 0,
  31, 12, 36,          -- 31 raw shortfall → rounded up to 36 (3 cases × 12)
  10.00, 360.00, 500.00, 'ok',
  'ready', NULL,
  ARRAY['50000000-0000-0000-0000-000000000002']::uuid[]
);

-- ── TC3: Pending incoming order (24 units confirmed, arriving in 10 days) ─────
-- shortfall = 56 + 0 - 20 - 24 = 12
-- proposed  = ceil(12/1)×1    = 12
-- cost      = 12 × $10        = $120.00   budget $500 → ok
INSERT INTO reorder_analyses (
  id, user_id, product_id, calculation_version, input_snapshot,
  average_daily_demand, lead_time_days, lead_time_demand,
  safety_stock_target, usable_available_stock, eligible_incoming_quantity,
  net_shortfall, pack_size, proposed_order_quantity,
  unit_price, estimated_cost, budget_available, budget_status,
  analysis_status, status_reason, evidence_ids
) VALUES (
  '60000000-0000-0000-0000-000000000003',
  '00000000-0000-0000-0000-000000000001',
  '10000000-0000-0000-0000-000000000003',
  '1.0.0',
  jsonb_build_object(
    'sku','SKU-003','product_id','10000000-0000-0000-0000-000000000003',
    'average_daily_demand',4,'demand_window_days',30,'lead_time_days',14,
    'usable_available_stock',20,'safety_stock_target',0,'safety_stock_was_defaulted',true,
    'eligible_incoming_quantity',24,
    'incoming_order_ids',jsonb_build_array('40000000-0000-0000-0000-000000000003'),
    'pack_size',1,'moq',null,'unit_price',10.00,'currency','USD',
    'budget_available',500.00,'supplier_terms_id','20000000-0000-0000-0000-000000000003',
    'source_evidence_ids',jsonb_build_array('50000000-0000-0000-0000-000000000003'),
    'snapshot_at',now()
  ),
  4, 14, 56,
  0, 20, 24,
  12, 1, 12,           -- incoming order covers 24 of the 36 raw shortfall
  10.00, 120.00, 500.00, 'ok',
  'ready', NULL,
  ARRAY['50000000-0000-0000-0000-000000000003']::uuid[]
);

-- ── TC4: 20% price increase → budget review ───────────────────────────────────
-- shortfall = 56 + 0 - 20 - 0 = 36
-- proposed  = 36
-- OLD cost  = 36 × $10.00 = $360.00  (would have been ok)
-- NEW cost  = 36 × $12.00 = $432.00  > budget $400 → over_budget → needs_review
INSERT INTO reorder_analyses (
  id, user_id, product_id, calculation_version, input_snapshot,
  average_daily_demand, lead_time_days, lead_time_demand,
  safety_stock_target, usable_available_stock, eligible_incoming_quantity,
  net_shortfall, pack_size, proposed_order_quantity,
  unit_price, estimated_cost, budget_available, budget_status,
  analysis_status, status_reason, evidence_ids
) VALUES (
  '60000000-0000-0000-0000-000000000004',
  '00000000-0000-0000-0000-000000000001',
  '10000000-0000-0000-0000-000000000004',
  '1.0.0',
  jsonb_build_object(
    'sku','SKU-004','product_id','10000000-0000-0000-0000-000000000004',
    'average_daily_demand',4,'demand_window_days',30,'lead_time_days',14,
    'usable_available_stock',20,'safety_stock_target',0,'safety_stock_was_defaulted',true,
    'eligible_incoming_quantity',0,'incoming_order_ids','[]'::jsonb,
    'pack_size',1,'moq',null,
    'unit_price',12.00,'previous_unit_price',10.00,'price_change_pct',20,
    'currency','USD',
    'budget_available',400.00,'supplier_terms_id','20000000-0000-0000-0000-000000000004',
    'source_evidence_ids',jsonb_build_array('50000000-0000-0000-0000-000000000004'),
    'snapshot_at',now()
  ),
  4, 14, 56,
  0, 20, 0,
  36, 1, 36,
  12.00, 432.00, 400.00, 'over_budget',    -- $432 > $400 → budget review
  'needs_review',
  'Supplier price increased 20% (from $10.00 to $12.00). Estimated cost $432.00 exceeds budget $400.00. Budget review required before approval.',
  ARRAY['50000000-0000-0000-0000-000000000004']::uuid[]
);

-- ═══════════════════════════════════════════════════════════════════════════════
-- REORDER REQUESTS  (draft state — awaiting approval in the demo)
-- ═══════════════════════════════════════════════════════════════════════════════
INSERT INTO reorder_requests (
  id, user_id, idempotency_key,
  analysis_id, product_id, sku, supplier_name,
  proposed_quantity, pack_count, pack_size,
  estimated_cost, currency, calculation_version, status
) VALUES
  -- TC1
  ('70000000-0000-0000-0000-000000000001',
   '00000000-0000-0000-0000-000000000001',
   'SKU-001-60000000-0000-0000-0000-000000000001-v1',
   '60000000-0000-0000-0000-000000000001',
   '10000000-0000-0000-0000-000000000001',
   'SKU-001','Acme Supplies', 36, 36, 1, 360.00, 'USD','1.0.0','draft'),
  -- TC2
  ('70000000-0000-0000-0000-000000000002',
   '00000000-0000-0000-0000-000000000001',
   'SKU-002-60000000-0000-0000-0000-000000000002-v1',
   '60000000-0000-0000-0000-000000000002',
   '10000000-0000-0000-0000-000000000002',
   'SKU-002','Bulk Co', 36, 3, 12, 360.00, 'USD','1.0.0','draft'),
  -- TC3
  ('70000000-0000-0000-0000-000000000003',
   '00000000-0000-0000-0000-000000000001',
   'SKU-003-60000000-0000-0000-0000-000000000003-v1',
   '60000000-0000-0000-0000-000000000003',
   '10000000-0000-0000-0000-000000000003',
   'SKU-003','Global Trade', 12, 12, 1, 120.00, 'USD','1.0.0','draft'),
  -- TC4  (needs_review — price increase requires budget approval)
  ('70000000-0000-0000-0000-000000000004',
   '00000000-0000-0000-0000-000000000001',
   'SKU-004-60000000-0000-0000-0000-000000000004-v1',
   '60000000-0000-0000-0000-000000000004',
   '10000000-0000-0000-0000-000000000004',
   'SKU-004','Acme Supplies', 36, 36, 1, 432.00, 'USD','1.0.0','needs_review');

-- ═══════════════════════════════════════════════════════════════════════════════
-- REQUEST VERSIONS  (version 1 snapshot for each request)
-- ═══════════════════════════════════════════════════════════════════════════════
INSERT INTO request_versions (id, user_id, request_id, version_number, snapshot)
VALUES
  ('80000000-0000-0000-0000-000000000001',
   '00000000-0000-0000-0000-000000000001',
   '70000000-0000-0000-0000-000000000001', 1,
   '{"sku":"SKU-001","proposed_quantity":36,"pack_count":36,"pack_size":1,"estimated_cost":360.00,"currency":"USD","supplier_name":"Acme Supplies","status":"draft","calculation_version":"1.0.0"}'::jsonb),

  ('80000000-0000-0000-0000-000000000002',
   '00000000-0000-0000-0000-000000000001',
   '70000000-0000-0000-0000-000000000002', 1,
   '{"sku":"SKU-002","proposed_quantity":36,"pack_count":3,"pack_size":12,"estimated_cost":360.00,"currency":"USD","supplier_name":"Bulk Co","status":"draft","calculation_version":"1.0.0"}'::jsonb),

  ('80000000-0000-0000-0000-000000000003',
   '00000000-0000-0000-0000-000000000001',
   '70000000-0000-0000-0000-000000000003', 1,
   '{"sku":"SKU-003","proposed_quantity":12,"pack_count":12,"pack_size":1,"estimated_cost":120.00,"currency":"USD","supplier_name":"Global Trade","status":"draft","calculation_version":"1.0.0"}'::jsonb),

  ('80000000-0000-0000-0000-000000000004',
   '00000000-0000-0000-0000-000000000001',
   '70000000-0000-0000-0000-000000000004', 1,
   '{"sku":"SKU-004","proposed_quantity":36,"pack_count":36,"pack_size":1,"estimated_cost":432.00,"currency":"USD","supplier_name":"Acme Supplies","status":"needs_review","calculation_version":"1.0.0","price_change_note":"Unit price increased 20% from $10.00 to $12.00. Budget review required."}'::jsonb);

-- ═══════════════════════════════════════════════════════════════════════════════
-- AUDIT EVENTS  (initial 'proposed' event for each request)
-- ═══════════════════════════════════════════════════════════════════════════════
INSERT INTO audit_events (id, user_id, request_id, event_type, actor_id, details)
VALUES
  ('90000000-0000-0000-0000-000000000001',
   '00000000-0000-0000-0000-000000000001',
   '70000000-0000-0000-0000-000000000001',
   'proposed', '00000000-0000-0000-0000-000000000001',
   '{"version":1,"sku":"SKU-001","proposed_quantity":36,"note":"TC1 — Low stock, no incoming order"}'::jsonb),

  ('90000000-0000-0000-0000-000000000002',
   '00000000-0000-0000-0000-000000000001',
   '70000000-0000-0000-0000-000000000002',
   'proposed', '00000000-0000-0000-0000-000000000001',
   '{"version":1,"sku":"SKU-002","proposed_quantity":36,"pack_count":3,"pack_size":12,"note":"TC2 — Case-only supplier; 31 raw shortfall rounded to 36 (3 cases × 12)"}'::jsonb),

  ('90000000-0000-0000-0000-000000000003',
   '00000000-0000-0000-0000-000000000001',
   '70000000-0000-0000-0000-000000000003',
   'proposed', '00000000-0000-0000-0000-000000000001',
   '{"version":1,"sku":"SKU-003","proposed_quantity":12,"eligible_incoming":24,"note":"TC3 — 24 units in confirmed open order (PO-GAMMA-001) subtracted from 36 raw shortfall"}'::jsonb),

  ('90000000-0000-0000-0000-000000000004',
   '00000000-0000-0000-0000-000000000001',
   '70000000-0000-0000-0000-000000000004',
   'proposed', '00000000-0000-0000-0000-000000000001',
   '{"version":1,"sku":"SKU-004","proposed_quantity":36,"estimated_cost":432.00,"budget":400.00,"price_change_pct":20,"note":"TC4 — 20% price rise; new cost $432 exceeds budget $400; status set to needs_review"}'::jsonb);

-- ═══════════════════════════════════════════════════════════════════════════════
-- TEST RUN FIXTURES  (TC1–TC4 — status=pending until backend runs them)
-- ═══════════════════════════════════════════════════════════════════════════════
INSERT INTO test_runs
  (id, user_id, case_id, description, input, expected_result, actual_result, status)
VALUES
  -- TC1
  ('a0000000-0000-0000-0000-000000000001',
   '00000000-0000-0000-0000-000000000001',
   'TC1',
   'Low stock with no incoming order → correct reorder quantity',
   '{"sku":"SKU-001","current_stock":20,"average_daily_demand":4,"lead_time_days":14,"safety_stock_target":0,"eligible_incoming_quantity":0,"pack_size":1,"unit_price":10.00,"budget_available":500.00}'::jsonb,
   '{"net_shortfall":36,"proposed_order_quantity":36,"estimated_cost":360.00,"budget_status":"ok","analysis_status":"ready"}'::jsonb,
   NULL, 'pending'),

  -- TC2
  ('a0000000-0000-0000-0000-000000000002',
   '00000000-0000-0000-0000-000000000001',
   'TC2',
   'Supplier sells in cases of 12 → quantity rounded up to whole cases',
   '{"sku":"SKU-002","current_stock":25,"average_daily_demand":4,"lead_time_days":14,"safety_stock_target":0,"eligible_incoming_quantity":0,"pack_size":12,"unit_price":10.00,"budget_available":500.00}'::jsonb,
   '{"net_shortfall":31,"proposed_order_quantity":36,"pack_count":3,"estimated_cost":360.00,"budget_status":"ok","analysis_status":"ready","note":"Raw shortfall 31 rounded up to 36 (3 cases × 12)"}'::jsonb,
   NULL, 'pending'),

  -- TC3
  ('a0000000-0000-0000-0000-000000000003',
   '00000000-0000-0000-0000-000000000001',
   'TC3',
   'Pending confirmed order (24 units) → eligible incoming subtracted; no duplicate for covered amount',
   '{"sku":"SKU-003","current_stock":20,"average_daily_demand":4,"lead_time_days":14,"safety_stock_target":0,"eligible_incoming_quantity":24,"open_order_status":"confirmed","open_order_arrival_days":10,"pack_size":1,"unit_price":10.00,"budget_available":500.00}'::jsonb,
   '{"net_shortfall":12,"proposed_order_quantity":12,"estimated_cost":120.00,"budget_status":"ok","analysis_status":"ready","eligible_incoming_quantity":24}'::jsonb,
   NULL, 'pending'),

  -- TC4
  ('a0000000-0000-0000-0000-000000000004',
   '00000000-0000-0000-0000-000000000001',
   'TC4',
   'Supplier price rises 20% ($10→$12) → cost recalculated, budget review requested',
   '{"sku":"SKU-004","current_stock":20,"average_daily_demand":4,"lead_time_days":14,"safety_stock_target":0,"eligible_incoming_quantity":0,"pack_size":1,"unit_price":12.00,"previous_unit_price":10.00,"price_change_pct":20,"budget_available":400.00}'::jsonb,
   '{"net_shortfall":36,"proposed_order_quantity":36,"estimated_cost":432.00,"budget_status":"over_budget","analysis_status":"needs_review","note":"Cost $432 exceeds budget $400; budget review required; price change visible in evidence"}'::jsonb,
   NULL, 'pending');

-- ═══════════════════════════════════════════════════════════════════════════════
-- Seed complete.
-- All data is labelled DEMO / SYNTHETIC.
-- Records are owned by demo user: 00000000-0000-0000-0000-000000000001
-- ═══════════════════════════════════════════════════════════════════════════════
