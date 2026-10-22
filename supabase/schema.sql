-- ═══════════════════════════════════════════════════════════════════════════════
-- Inventory Reorder Planner — PostgreSQL Schema (Supabase)
-- Phase 2 — Complete implementation
--
-- Run this in the Supabase SQL Editor (or via psql with service-role creds).
-- The script is idempotent: safe to re-run.  Tables use IF NOT EXISTS; policies
-- are dropped and recreated so you can apply updates without errors.
--
-- Tables (12):
--   1. products              — SKU + inventory snapshot
--   2. supplier_terms        — lead time, pack size, unit price, MOQ
--   3. sales_history         — demand history windows
--   4. open_purchase_orders  — confirmed/open orders from suppliers
--   5. source_evidence       — retrieval provenance per analysis
--   6. reorder_analyses      — deterministic calculation outputs + input snapshot
--   7. reorder_requests      — proposed orders awaiting approval
--   8. request_versions      — immutable snapshots per request version
--   9. approvals             — approval / rejection records
--  10. verification_results  — post-submission independent verification
--  11. audit_events          — append-only lifecycle event log
--  12. test_runs             — TC1–TC4 scenario records
-- ═══════════════════════════════════════════════════════════════════════════════

-- ── Prerequisites ─────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ── Shared trigger: auto-update updated_at ────────────────────────────────────
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

-- ── Shared trigger: block mutations on append-only tables ─────────────────────
CREATE OR REPLACE FUNCTION prevent_mutation()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  -- ── Seed-only escape hatch ───────────────────────────────────────────────
  -- The seed script sets:  SET app.seed_cleanup = 'true';
  -- Application code must NEVER set this GUC.  The check is case-sensitive
  -- and uses the missing_ok flag so an unset variable evaluates to NULL
  -- (not 'true'), keeping the guard active in all normal operation.
  IF current_setting('app.seed_cleanup', true) = 'true' THEN
    RETURN OLD;   -- allow the seed DELETE to proceed
  END IF;
  -- ─────────────────────────────────────────────────────────────────────────
  RAISE EXCEPTION
    'Table % is append-only; UPDATE and DELETE are not permitted.',
    TG_TABLE_NAME;
END;
$$;

-- ═══════════════════════════════════════════════════════════════════════════════
-- 1. products
-- ═══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS products (
  id                   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id              UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  sku                  TEXT        NOT NULL,
  name                 TEXT        NOT NULL,
  unit                 TEXT        NOT NULL DEFAULT 'each',
  currency             CHAR(3)     NOT NULL DEFAULT 'USD',
  current_stock        NUMERIC(14,4) NOT NULL CHECK (current_stock >= 0),
  reorder_point        NUMERIC(14,4)           CHECK (reorder_point >= 0),
  safety_stock_target  NUMERIC(14,4)           CHECK (safety_stock_target >= 0),
  created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_product_user_sku UNIQUE (user_id, sku)
);

CREATE INDEX IF NOT EXISTS idx_products_user_id ON products (user_id);
CREATE INDEX IF NOT EXISTS idx_products_sku     ON products (sku);

DROP TRIGGER IF EXISTS trg_products_updated_at ON products;
CREATE TRIGGER trg_products_updated_at
  BEFORE UPDATE ON products
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

ALTER TABLE products ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "products_select_own" ON products;
DROP POLICY IF EXISTS "products_insert_own" ON products;
DROP POLICY IF EXISTS "products_update_own" ON products;
DROP POLICY IF EXISTS "products_delete_own" ON products;
CREATE POLICY "products_select_own" ON products FOR SELECT USING (user_id = auth.uid());
CREATE POLICY "products_insert_own" ON products FOR INSERT WITH CHECK (user_id = auth.uid());
CREATE POLICY "products_update_own" ON products FOR UPDATE
  USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());
CREATE POLICY "products_delete_own" ON products FOR DELETE USING (user_id = auth.uid());

-- ═══════════════════════════════════════════════════════════════════════════════
-- 2. supplier_terms
-- ═══════════════════════════════════════════════════════════════════════════════
-- D1 fix: product_id uses ON DELETE RESTRICT (not CASCADE).
-- Rationale: open_purchase_orders.supplier_terms_id also carries ON DELETE RESTRICT,
-- which means that if products cascaded into supplier_terms first, PostgreSQL would
-- then try to delete those supplier_terms rows but fail because open_purchase_orders
-- still holds a RESTRICT back-reference to them.  By making the parent FK RESTRICT
-- as well, product deletion is cleanly blocked when supplier terms (or open orders)
-- still exist.  Application code must delete in this explicit order:
--   1. Cancel / delete open_purchase_orders for the product.
--   2. Delete supplier_terms for the product.
--   3. Delete the product row itself.
CREATE TABLE IF NOT EXISTS supplier_terms (
  id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id           UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  product_id        UUID        NOT NULL REFERENCES products(id)   ON DELETE RESTRICT,
  supplier_name     TEXT        NOT NULL,
  lead_time_days    INT         NOT NULL CHECK (lead_time_days > 0),
  pack_size         INT         NOT NULL DEFAULT 1 CHECK (pack_size >= 1),
  unit_price        NUMERIC(14,4) NOT NULL CHECK (unit_price > 0),
  currency          CHAR(3)     NOT NULL DEFAULT 'USD',
  moq               INT                  CHECK (moq >= 1),          -- minimum order quantity
  price_updated_at  TIMESTAMPTZ NOT NULL,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_supplier_terms_product_id ON supplier_terms (product_id);
CREATE INDEX IF NOT EXISTS idx_supplier_terms_user_id   ON supplier_terms (user_id);

DROP TRIGGER IF EXISTS trg_supplier_terms_updated_at ON supplier_terms;
CREATE TRIGGER trg_supplier_terms_updated_at
  BEFORE UPDATE ON supplier_terms
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

ALTER TABLE supplier_terms ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "supplier_terms_select_own" ON supplier_terms;
DROP POLICY IF EXISTS "supplier_terms_insert_own" ON supplier_terms;
DROP POLICY IF EXISTS "supplier_terms_update_own" ON supplier_terms;
DROP POLICY IF EXISTS "supplier_terms_delete_own" ON supplier_terms;
CREATE POLICY "supplier_terms_select_own" ON supplier_terms FOR SELECT USING (user_id = auth.uid());
CREATE POLICY "supplier_terms_insert_own" ON supplier_terms FOR INSERT WITH CHECK (user_id = auth.uid());
CREATE POLICY "supplier_terms_update_own" ON supplier_terms FOR UPDATE
  USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());
CREATE POLICY "supplier_terms_delete_own" ON supplier_terms FOR DELETE USING (user_id = auth.uid());

-- ═══════════════════════════════════════════════════════════════════════════════
-- 3. sales_history
-- ═══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS sales_history (
  id                    UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id               UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  product_id            UUID        NOT NULL REFERENCES products(id)   ON DELETE CASCADE,
  period_start          DATE        NOT NULL,
  period_end            DATE        NOT NULL,
  total_units_sold      NUMERIC(14,4) NOT NULL CHECK (total_units_sold >= 0),
  days_in_period        INT         NOT NULL CHECK (days_in_period > 0),
  -- Computed column: average_daily_demand stored for query performance
  average_daily_demand  NUMERIC(14,6) GENERATED ALWAYS AS
    (total_units_sold / days_in_period) STORED,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT chk_sales_period CHECK (period_end >= period_start)
);

CREATE INDEX IF NOT EXISTS idx_sales_history_product_id ON sales_history (product_id);
CREATE INDEX IF NOT EXISTS idx_sales_history_period
  ON sales_history (product_id, period_start DESC, period_end DESC);

ALTER TABLE sales_history ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "sales_history_select_own" ON sales_history;
DROP POLICY IF EXISTS "sales_history_insert_own" ON sales_history;
DROP POLICY IF EXISTS "sales_history_delete_own" ON sales_history;
CREATE POLICY "sales_history_select_own" ON sales_history FOR SELECT USING (user_id = auth.uid());
CREATE POLICY "sales_history_insert_own" ON sales_history FOR INSERT WITH CHECK (user_id = auth.uid());
-- No UPDATE policy: historical records are replaced, not mutated.
CREATE POLICY "sales_history_delete_own" ON sales_history FOR DELETE USING (user_id = auth.uid());

-- ═══════════════════════════════════════════════════════════════════════════════
-- 4. open_purchase_orders
-- ═══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS open_purchase_orders (
  id                    UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id               UUID        NOT NULL REFERENCES auth.users(id)    ON DELETE CASCADE,
  product_id            UUID        NOT NULL REFERENCES products(id)       ON DELETE CASCADE,
  -- ON DELETE RESTRICT explicit (was implicit default): open orders block
  -- deletion of the supplier terms they reference.  See deletion-order note
  -- on the supplier_terms table definition above.
  supplier_terms_id     UUID        NOT NULL REFERENCES supplier_terms(id) ON DELETE RESTRICT,
  ordered_quantity      NUMERIC(14,4) NOT NULL CHECK (ordered_quantity > 0),
  received_quantity     NUMERIC(14,4) NOT NULL DEFAULT 0 CHECK (received_quantity >= 0),
  -- remaining_quantity is computed; never update it directly
  remaining_quantity    NUMERIC(14,4) GENERATED ALWAYS AS
    (ordered_quantity - received_quantity) STORED,
  expected_arrival_date DATE        NOT NULL,
  status                TEXT        NOT NULL
    CHECK (status IN ('open','confirmed','partially_received','received','cancelled')),
  order_reference       TEXT        NOT NULL,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT chk_received_lte_ordered CHECK (received_quantity <= ordered_quantity)
);

CREATE INDEX IF NOT EXISTS idx_open_orders_product_id ON open_purchase_orders (product_id);
CREATE INDEX IF NOT EXISTS idx_open_orders_status     ON open_purchase_orders (status);
CREATE INDEX IF NOT EXISTS idx_open_orders_arrival    ON open_purchase_orders (expected_arrival_date);

DROP TRIGGER IF EXISTS trg_open_orders_updated_at ON open_purchase_orders;
CREATE TRIGGER trg_open_orders_updated_at
  BEFORE UPDATE ON open_purchase_orders
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

ALTER TABLE open_purchase_orders ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "open_orders_select_own" ON open_purchase_orders;
DROP POLICY IF EXISTS "open_orders_insert_own" ON open_purchase_orders;
DROP POLICY IF EXISTS "open_orders_update_own" ON open_purchase_orders;
DROP POLICY IF EXISTS "open_orders_delete_own" ON open_purchase_orders;
CREATE POLICY "open_orders_select_own" ON open_purchase_orders FOR SELECT USING (user_id = auth.uid());
CREATE POLICY "open_orders_insert_own" ON open_purchase_orders FOR INSERT WITH CHECK (user_id = auth.uid());
CREATE POLICY "open_orders_update_own" ON open_purchase_orders FOR UPDATE
  USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());
CREATE POLICY "open_orders_delete_own" ON open_purchase_orders FOR DELETE USING (user_id = auth.uid());

-- ═══════════════════════════════════════════════════════════════════════════════
-- 5. source_evidence
-- ═══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS source_evidence (
  id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id          UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  source_type      TEXT        NOT NULL
    CHECK (source_type IN ('mock_source','api','http','browser')),
  source_url       TEXT,
  retrieved_at     TIMESTAMPTZ NOT NULL,
  source_timestamp TIMESTAMPTZ,
  fields_used      TEXT[]      NOT NULL DEFAULT '{}',
  raw_data         JSONB       NOT NULL DEFAULT '{}'
  -- No updated_at: evidence is immutable once created
);

CREATE INDEX IF NOT EXISTS idx_source_evidence_user_id     ON source_evidence (user_id);
CREATE INDEX IF NOT EXISTS idx_source_evidence_source_type ON source_evidence (source_type);

ALTER TABLE source_evidence ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "source_evidence_select_own" ON source_evidence;
DROP POLICY IF EXISTS "source_evidence_insert_own" ON source_evidence;
CREATE POLICY "source_evidence_select_own" ON source_evidence FOR SELECT USING (user_id = auth.uid());
CREATE POLICY "source_evidence_insert_own" ON source_evidence FOR INSERT WITH CHECK (user_id = auth.uid());
-- No UPDATE or DELETE: evidence records are immutable.

-- ═══════════════════════════════════════════════════════════════════════════════
-- 6. reorder_analyses
-- ═══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS reorder_analyses (
  id                        UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id                   UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  product_id                UUID        NOT NULL REFERENCES products(id)   ON DELETE CASCADE,
  calculation_version       TEXT        NOT NULL,
  -- Full input snapshot for reproducibility
  input_snapshot            JSONB       NOT NULL,
  average_daily_demand      NUMERIC(14,6) NOT NULL CHECK (average_daily_demand >= 0),
  lead_time_days            INT         NOT NULL CHECK (lead_time_days > 0),
  lead_time_demand          NUMERIC(14,4) NOT NULL CHECK (lead_time_demand >= 0),
  safety_stock_target       NUMERIC(14,4) NOT NULL CHECK (safety_stock_target >= 0),
  usable_available_stock    NUMERIC(14,4) NOT NULL CHECK (usable_available_stock >= 0),
  eligible_incoming_quantity NUMERIC(14,4) NOT NULL CHECK (eligible_incoming_quantity >= 0),
  net_shortfall             NUMERIC(14,4) NOT NULL CHECK (net_shortfall >= 0),
  pack_size                 INT         NOT NULL CHECK (pack_size >= 1),
  proposed_order_quantity   NUMERIC(14,4) NOT NULL CHECK (proposed_order_quantity >= 0),
  unit_price                NUMERIC(14,4) NOT NULL CHECK (unit_price > 0),
  estimated_cost            NUMERIC(14,4) NOT NULL CHECK (estimated_cost >= 0),
  budget_available          NUMERIC(14,4),
  budget_status             TEXT        NOT NULL
    CHECK (budget_status IN ('ok','over_budget','needs_review','unknown')),
  analysis_status           TEXT        NOT NULL
    CHECK (analysis_status IN ('ready','needs_review','insufficient_data')),
  status_reason             TEXT,
  evidence_ids              UUID[]      NOT NULL DEFAULT '{}',
  created_at                TIMESTAMPTZ NOT NULL DEFAULT now()
  -- No updated_at: analyses are immutable; create a new analysis instead.
);

CREATE INDEX IF NOT EXISTS idx_analyses_product_id ON reorder_analyses (product_id);
CREATE INDEX IF NOT EXISTS idx_analyses_user_id    ON reorder_analyses (user_id);
CREATE INDEX IF NOT EXISTS idx_analyses_status     ON reorder_analyses (analysis_status);

ALTER TABLE reorder_analyses ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "analyses_select_own" ON reorder_analyses;
DROP POLICY IF EXISTS "analyses_insert_own" ON reorder_analyses;
CREATE POLICY "analyses_select_own" ON reorder_analyses FOR SELECT USING (user_id = auth.uid());
CREATE POLICY "analyses_insert_own" ON reorder_analyses FOR INSERT WITH CHECK (user_id = auth.uid());
-- No UPDATE or DELETE: analyses are immutable.

-- ═══════════════════════════════════════════════════════════════════════════════
-- 7. reorder_requests
-- ═══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS reorder_requests (
  id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id             UUID        NOT NULL REFERENCES auth.users(id)        ON DELETE CASCADE,
  -- idempotency_key: stable hash of (user_id + SKU + analysis_id + version).
  -- Unique per user; prevents duplicate submissions on retries.
  idempotency_key     TEXT        NOT NULL,
  analysis_id         UUID        NOT NULL REFERENCES reorder_analyses(id),
  product_id          UUID        NOT NULL REFERENCES products(id),
  sku                 TEXT        NOT NULL,
  supplier_name       TEXT        NOT NULL,
  proposed_quantity   NUMERIC(14,4) NOT NULL CHECK (proposed_quantity >= 0),
  pack_count          INT         NOT NULL CHECK (pack_count >= 0),
  pack_size           INT         NOT NULL CHECK (pack_size >= 1),
  estimated_cost      NUMERIC(14,4) NOT NULL CHECK (estimated_cost >= 0),
  currency            CHAR(3)     NOT NULL DEFAULT 'USD',
  calculation_version TEXT        NOT NULL,
  status              TEXT        NOT NULL DEFAULT 'draft'
    CHECK (status IN (
      'draft','pending_approval','approved',
      'submitted_or_simulated','verified',
      'rejected','needs_review','failed'
    )),
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  -- Idempotency: one active request per user per intent key
  CONSTRAINT uq_request_idempotency UNIQUE (user_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_requests_user_id     ON reorder_requests (user_id);
CREATE INDEX IF NOT EXISTS idx_requests_status      ON reorder_requests (status);
CREATE INDEX IF NOT EXISTS idx_requests_product_id  ON reorder_requests (product_id);
CREATE INDEX IF NOT EXISTS idx_requests_idempotency ON reorder_requests (idempotency_key);

DROP TRIGGER IF EXISTS trg_requests_updated_at ON reorder_requests;
CREATE TRIGGER trg_requests_updated_at
  BEFORE UPDATE ON reorder_requests
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

ALTER TABLE reorder_requests ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "requests_select_own" ON reorder_requests;
DROP POLICY IF EXISTS "requests_insert_own" ON reorder_requests;
DROP POLICY IF EXISTS "requests_update_own" ON reorder_requests;
CREATE POLICY "requests_select_own" ON reorder_requests FOR SELECT USING (user_id = auth.uid());
CREATE POLICY "requests_insert_own" ON reorder_requests FOR INSERT WITH CHECK (user_id = auth.uid());
CREATE POLICY "requests_update_own" ON reorder_requests FOR UPDATE
  USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());
-- No DELETE: requests are retained for audit purposes.

-- ═══════════════════════════════════════════════════════════════════════════════
-- 8. request_versions
--    Immutable snapshot written every time a request proposal changes.
--    Approval references a specific version; change → new version → re-approval.
-- ═══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS request_versions (
  id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id        UUID        NOT NULL REFERENCES auth.users(id)        ON DELETE CASCADE,
  request_id     UUID        NOT NULL REFERENCES reorder_requests(id)  ON DELETE CASCADE,
  version_number INT         NOT NULL CHECK (version_number >= 1),
  snapshot       JSONB       NOT NULL,   -- full request state at time of version
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_request_version UNIQUE (request_id, version_number)
);

CREATE INDEX IF NOT EXISTS idx_request_versions_request_id ON request_versions (request_id);

DROP TRIGGER IF EXISTS trg_request_versions_no_update ON request_versions;
DROP TRIGGER IF EXISTS trg_request_versions_no_delete ON request_versions;
CREATE TRIGGER trg_request_versions_no_update
  BEFORE UPDATE ON request_versions FOR EACH ROW EXECUTE FUNCTION prevent_mutation();
CREATE TRIGGER trg_request_versions_no_delete
  BEFORE DELETE ON request_versions FOR EACH ROW EXECUTE FUNCTION prevent_mutation();

ALTER TABLE request_versions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "request_versions_select_own" ON request_versions;
DROP POLICY IF EXISTS "request_versions_insert_own" ON request_versions;
CREATE POLICY "request_versions_select_own" ON request_versions FOR SELECT USING (user_id = auth.uid());
CREATE POLICY "request_versions_insert_own" ON request_versions FOR INSERT WITH CHECK (user_id = auth.uid());

-- ═══════════════════════════════════════════════════════════════════════════════
-- 9. approvals
-- ═══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS approvals (
  id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id             UUID        NOT NULL REFERENCES auth.users(id)       ON DELETE CASCADE,
  request_id          UUID        NOT NULL REFERENCES reorder_requests(id) ON DELETE CASCADE,
  request_version_id  UUID        NOT NULL REFERENCES request_versions(id),
  approver_id         UUID        NOT NULL REFERENCES auth.users(id),
  action              TEXT        NOT NULL CHECK (action IN ('approved','rejected')),
  notes               TEXT,
  timestamp           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_approvals_request_id ON approvals (request_id);
CREATE INDEX IF NOT EXISTS idx_approvals_approver   ON approvals (approver_id);

DROP TRIGGER IF EXISTS trg_approvals_no_update ON approvals;
DROP TRIGGER IF EXISTS trg_approvals_no_delete ON approvals;
CREATE TRIGGER trg_approvals_no_update
  BEFORE UPDATE ON approvals FOR EACH ROW EXECUTE FUNCTION prevent_mutation();
CREATE TRIGGER trg_approvals_no_delete
  BEFORE DELETE ON approvals FOR EACH ROW EXECUTE FUNCTION prevent_mutation();

ALTER TABLE approvals ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "approvals_select_own" ON approvals;
DROP POLICY IF EXISTS "approvals_insert_own" ON approvals;
-- user_id here = owner of the request (requester).
-- The approver_id identifies who acted; they may or may not be the owner.
-- In this single-user demo, user_id = auth.uid() covers both roles.
CREATE POLICY "approvals_select_own" ON approvals FOR SELECT USING (user_id = auth.uid());
CREATE POLICY "approvals_insert_own" ON approvals FOR INSERT WITH CHECK (user_id = auth.uid());

-- ═══════════════════════════════════════════════════════════════════════════════
-- 10. verification_results
-- ═══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS verification_results (
  id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id           UUID        NOT NULL REFERENCES auth.users(id)       ON DELETE CASCADE,
  request_id        UUID        NOT NULL REFERENCES reorder_requests(id) ON DELETE CASCADE,
  intended_sku      TEXT        NOT NULL,
  actual_sku        TEXT        NOT NULL,
  sku_match         BOOLEAN     NOT NULL,
  intended_quantity NUMERIC(14,4) NOT NULL,
  actual_quantity   NUMERIC(14,4) NOT NULL,
  quantity_match    BOOLEAN     NOT NULL,
  pack_size_check   BOOLEAN     NOT NULL,
  duplicate_check   BOOLEAN     NOT NULL,
  status            TEXT        NOT NULL CHECK (status IN ('verified','pending','failed')),
  evidence          TEXT        NOT NULL DEFAULT '',
  verified_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_verification_request_id ON verification_results (request_id);

ALTER TABLE verification_results ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "verification_select_own" ON verification_results;
DROP POLICY IF EXISTS "verification_insert_own" ON verification_results;
CREATE POLICY "verification_select_own" ON verification_results FOR SELECT USING (user_id = auth.uid());
CREATE POLICY "verification_insert_own" ON verification_results FOR INSERT WITH CHECK (user_id = auth.uid());

-- ═══════════════════════════════════════════════════════════════════════════════
-- 11. audit_events  (APPEND-ONLY — triggers block UPDATE and DELETE)
-- ═══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS audit_events (
  id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID        NOT NULL REFERENCES auth.users(id)       ON DELETE CASCADE,
  request_id  UUID        NOT NULL REFERENCES reorder_requests(id) ON DELETE CASCADE,
  event_type  TEXT        NOT NULL
    CHECK (event_type IN (
      'proposed','approved','rejected','submitted',
      'retry','verified','failed','version_invalidated'
    )),
  actor_id    UUID        REFERENCES auth.users(id),
  details     JSONB       NOT NULL DEFAULT '{}',
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_request_id  ON audit_events (request_id);
CREATE INDEX IF NOT EXISTS idx_audit_event_type  ON audit_events (event_type);
CREATE INDEX IF NOT EXISTS idx_audit_created_at  ON audit_events (created_at DESC);

DROP TRIGGER IF EXISTS trg_audit_no_update ON audit_events;
DROP TRIGGER IF EXISTS trg_audit_no_delete ON audit_events;
CREATE TRIGGER trg_audit_no_update
  BEFORE UPDATE ON audit_events FOR EACH ROW EXECUTE FUNCTION prevent_mutation();
CREATE TRIGGER trg_audit_no_delete
  BEFORE DELETE ON audit_events FOR EACH ROW EXECUTE FUNCTION prevent_mutation();

ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "audit_select_own" ON audit_events;
DROP POLICY IF EXISTS "audit_insert_own" ON audit_events;
CREATE POLICY "audit_select_own" ON audit_events FOR SELECT USING (user_id = auth.uid());
CREATE POLICY "audit_insert_own" ON audit_events FOR INSERT WITH CHECK (user_id = auth.uid());
-- No UPDATE or DELETE policies → blocked at both trigger and RLS layer.

-- ═══════════════════════════════════════════════════════════════════════════════
-- 12. test_runs  (TC1–TC4 scenario records)
-- ═══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS test_runs (
  id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  case_id         TEXT        NOT NULL CHECK (case_id IN ('TC1','TC2','TC3','TC4')),
  description     TEXT        NOT NULL,
  input           JSONB       NOT NULL,
  expected_result JSONB       NOT NULL,
  actual_result   JSONB,
  status          TEXT        NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pass','fail','pending','error')),
  evidence        TEXT,
  run_at          TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_test_runs_user_id ON test_runs (user_id);
CREATE INDEX IF NOT EXISTS idx_test_runs_case_id ON test_runs (case_id);
CREATE INDEX IF NOT EXISTS idx_test_runs_status  ON test_runs (status);

ALTER TABLE test_runs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "test_runs_select_own" ON test_runs;
DROP POLICY IF EXISTS "test_runs_insert_own" ON test_runs;
DROP POLICY IF EXISTS "test_runs_update_own" ON test_runs;
CREATE POLICY "test_runs_select_own" ON test_runs FOR SELECT USING (user_id = auth.uid());
CREATE POLICY "test_runs_insert_own" ON test_runs FOR INSERT WITH CHECK (user_id = auth.uid());
CREATE POLICY "test_runs_update_own" ON test_runs FOR UPDATE
  USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());

-- ═══════════════════════════════════════════════════════════════════════════════
-- Schema complete.
-- Next: run supabase/seed.sql to load synthetic TC1–TC4 demo data.
-- ═══════════════════════════════════════════════════════════════════════════════
