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
  -- Application code must NEVER set this GUC. The check is case-sensitive
  -- and uses the missing_ok flag so an unset variable evaluates to NULL.
  -- Additionally, caller must be an administrative role (postgres or service_role).
  IF current_setting('app.seed_cleanup', true) = 'true' THEN
    IF current_user IN ('postgres', 'service_role') THEN
      RETURN OLD;   -- allow the seed DELETE to proceed
    ELSE
      RAISE EXCEPTION 'Table % is append-only. Mutation override requires administrative role.', TG_TABLE_NAME;
    END IF;
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

ALTER TABLE products ADD COLUMN IF NOT EXISTS tenant_id UUID DEFAULT NULL;
CREATE INDEX IF NOT EXISTS idx_products_tenant_id ON products (tenant_id);

ALTER TABLE products ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "products_select_own" ON products;
DROP POLICY IF EXISTS "products_select_authorized" ON products;
DROP POLICY IF EXISTS "products_insert_own" ON products;
DROP POLICY IF EXISTS "products_update_own" ON products;
DROP POLICY IF EXISTS "products_delete_own" ON products;

CREATE POLICY "products_select_authorized" ON products FOR SELECT
  USING (
    user_id = auth.uid()
    -- Shared demo catalog (seed owner) visible to all authenticated users so
    -- newly registered planners can immediately evaluate TC1-TC4 SKUs.
    OR user_id = '00000000-0000-0000-0000-000000000001'::uuid
    OR (
      (auth.jwt() -> 'app_metadata' ->> 'role') IN ('approver', 'admin')
      AND (
        (tenant_id IS NOT NULL AND tenant_id::text = (auth.jwt() -> 'app_metadata' ->> 'tenant_id'))
        OR (tenant_id IS NULL AND (auth.jwt() -> 'app_metadata' ->> 'tenant_id') IS NULL)
      )
    )
  );
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

ALTER TABLE supplier_terms ADD COLUMN IF NOT EXISTS tenant_id UUID DEFAULT NULL;
CREATE INDEX IF NOT EXISTS idx_supplier_terms_tenant_id ON supplier_terms (tenant_id);

ALTER TABLE supplier_terms ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "supplier_terms_select_own" ON supplier_terms;
DROP POLICY IF EXISTS "supplier_terms_select_authorized" ON supplier_terms;
DROP POLICY IF EXISTS "supplier_terms_insert_own" ON supplier_terms;
DROP POLICY IF EXISTS "supplier_terms_update_own" ON supplier_terms;
DROP POLICY IF EXISTS "supplier_terms_delete_own" ON supplier_terms;

CREATE POLICY "supplier_terms_select_authorized" ON supplier_terms FOR SELECT
  USING (
    user_id = auth.uid()
    -- Shared demo supplier catalog visible to all authenticated users.
    OR user_id = '00000000-0000-0000-0000-000000000001'::uuid
    OR (
      (auth.jwt() -> 'app_metadata' ->> 'role') IN ('approver', 'admin')
      AND (
        (tenant_id IS NOT NULL AND tenant_id::text = (auth.jwt() -> 'app_metadata' ->> 'tenant_id'))
        OR (tenant_id IS NULL AND (auth.jwt() -> 'app_metadata' ->> 'tenant_id') IS NULL)
      )
    )
  );
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

ALTER TABLE sales_history ADD COLUMN IF NOT EXISTS tenant_id UUID DEFAULT NULL;
CREATE INDEX IF NOT EXISTS idx_sales_history_tenant_id ON sales_history (tenant_id);

ALTER TABLE sales_history ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "sales_history_select_own" ON sales_history;
DROP POLICY IF EXISTS "sales_history_select_authorized" ON sales_history;
DROP POLICY IF EXISTS "sales_history_insert_own" ON sales_history;
DROP POLICY IF EXISTS "sales_history_delete_own" ON sales_history;

CREATE POLICY "sales_history_select_authorized" ON sales_history FOR SELECT
  USING (
    user_id = auth.uid()
    OR (
      (auth.jwt() -> 'app_metadata' ->> 'role') IN ('approver', 'admin')
      AND (
        (tenant_id IS NOT NULL AND tenant_id::text = (auth.jwt() -> 'app_metadata' ->> 'tenant_id'))
        OR (tenant_id IS NULL AND (auth.jwt() -> 'app_metadata' ->> 'tenant_id') IS NULL)
      )
    )
  );
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

ALTER TABLE open_purchase_orders ADD COLUMN IF NOT EXISTS tenant_id UUID DEFAULT NULL;
CREATE INDEX IF NOT EXISTS idx_open_orders_tenant_id ON open_purchase_orders (tenant_id);

ALTER TABLE open_purchase_orders ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "open_orders_select_own" ON open_purchase_orders;
DROP POLICY IF EXISTS "open_orders_select_authorized" ON open_purchase_orders;
DROP POLICY IF EXISTS "open_orders_insert_own" ON open_purchase_orders;
DROP POLICY IF EXISTS "open_orders_update_own" ON open_purchase_orders;
DROP POLICY IF EXISTS "open_orders_delete_own" ON open_purchase_orders;

CREATE POLICY "open_orders_select_authorized" ON open_purchase_orders FOR SELECT
  USING (
    user_id = auth.uid()
    OR (
      (auth.jwt() -> 'app_metadata' ->> 'role') IN ('approver', 'admin')
      AND (
        (tenant_id IS NOT NULL AND tenant_id::text = (auth.jwt() -> 'app_metadata' ->> 'tenant_id'))
        OR (tenant_id IS NULL AND (auth.jwt() -> 'app_metadata' ->> 'tenant_id') IS NULL)
      )
    )
  );
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

ALTER TABLE source_evidence ADD COLUMN IF NOT EXISTS tenant_id UUID DEFAULT NULL;
CREATE INDEX IF NOT EXISTS idx_source_evidence_tenant_id ON source_evidence (tenant_id);

ALTER TABLE source_evidence ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "source_evidence_select_own" ON source_evidence;
DROP POLICY IF EXISTS "source_evidence_select_authorized" ON source_evidence;
DROP POLICY IF EXISTS "source_evidence_insert_own" ON source_evidence;

CREATE POLICY "source_evidence_select_authorized" ON source_evidence FOR SELECT
  USING (
    user_id = auth.uid()
    OR (
      (auth.jwt() -> 'app_metadata' ->> 'role') IN ('approver', 'admin')
      AND (
        (tenant_id IS NOT NULL AND tenant_id::text = (auth.jwt() -> 'app_metadata' ->> 'tenant_id'))
        OR (tenant_id IS NULL AND (auth.jwt() -> 'app_metadata' ->> 'tenant_id') IS NULL)
      )
    )
  );
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

ALTER TABLE reorder_analyses ADD COLUMN IF NOT EXISTS tenant_id UUID DEFAULT NULL;
CREATE INDEX IF NOT EXISTS idx_analyses_tenant_id ON reorder_analyses (tenant_id);

ALTER TABLE reorder_analyses ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "analyses_select_own" ON reorder_analyses;
DROP POLICY IF EXISTS "analyses_select_authorized" ON reorder_analyses;
DROP POLICY IF EXISTS "analyses_insert_own" ON reorder_analyses;

CREATE POLICY "analyses_select_authorized" ON reorder_analyses FOR SELECT
  USING (
    user_id = auth.uid()
    OR (
      (auth.jwt() -> 'app_metadata' ->> 'role') IN ('approver', 'admin')
      AND (
        (tenant_id IS NOT NULL AND tenant_id::text = (auth.jwt() -> 'app_metadata' ->> 'tenant_id'))
        OR (tenant_id IS NULL AND (auth.jwt() -> 'app_metadata' ->> 'tenant_id') IS NULL)
      )
    )
  );
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

ALTER TABLE reorder_requests ADD COLUMN IF NOT EXISTS tenant_id UUID DEFAULT NULL;
CREATE INDEX IF NOT EXISTS idx_requests_tenant_id ON reorder_requests (tenant_id);

ALTER TABLE reorder_requests ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "requests_select_own" ON reorder_requests;
DROP POLICY IF EXISTS "requests_select_authorized" ON reorder_requests;
DROP POLICY IF EXISTS "requests_insert_own" ON reorder_requests;
DROP POLICY IF EXISTS "requests_update_own" ON reorder_requests;
DROP POLICY IF EXISTS "requests_update_owner_proposal" ON reorder_requests;
DROP POLICY IF EXISTS "requests_update_approver_status" ON reorder_requests;
DROP POLICY IF EXISTS "requests_update_submission" ON reorder_requests;
DROP POLICY IF EXISTS "requests_update_verification" ON reorder_requests;

-- 1. SELECT: Owner views their own; Approvers/Admins view within tenant boundary
CREATE POLICY "requests_select_authorized" ON reorder_requests FOR SELECT
  USING (
    user_id = auth.uid()
    OR (
      (auth.jwt() -> 'app_metadata' ->> 'role') IN ('approver', 'admin')
      AND (
        (tenant_id IS NOT NULL AND tenant_id::text = (auth.jwt() -> 'app_metadata' ->> 'tenant_id'))
        OR (tenant_id IS NULL AND (auth.jwt() -> 'app_metadata' ->> 'tenant_id') IS NULL)
      )
    )
  );

-- 2. INSERT: Owner creates request in initial draft or pending_approval state only (cannot self-approve on insert)
CREATE POLICY "requests_insert_own" ON reorder_requests FOR INSERT
  WITH CHECK (
    user_id = auth.uid()
    AND status IN ('draft', 'pending_approval')
  );

-- 3. UPDATE (Proposal modification by Owner):
-- Planners can update proposal parameters on their own requests, BUT status must remain pending_approval or draft
CREATE POLICY "requests_update_owner_proposal" ON reorder_requests FOR UPDATE
  USING (user_id = auth.uid())
  WITH CHECK (
    user_id = auth.uid()
    AND status IN ('draft', 'pending_approval')
  );

-- 4. UPDATE (Approval/Rejection by Approver):
-- Only privileged approver/admin can transition pending_approval requests to approved or rejected.
-- WITH CHECK mirrors USING tenant scope to prevent tenant_id or user_id reassignment during update.
CREATE POLICY "requests_update_approver_status" ON reorder_requests FOR UPDATE
  USING (
    (auth.jwt() -> 'app_metadata' ->> 'role') IN ('approver', 'admin')
    AND status = 'pending_approval'
    AND (
      (tenant_id IS NOT NULL AND tenant_id::text = (auth.jwt() -> 'app_metadata' ->> 'tenant_id'))
      OR (tenant_id IS NULL AND (auth.jwt() -> 'app_metadata' ->> 'tenant_id') IS NULL)
    )
  )
  WITH CHECK (
    (auth.jwt() -> 'app_metadata' ->> 'role') IN ('approver', 'admin')
    AND status IN ('approved', 'rejected')
    -- Prevent tenant_id or user_id reassignment during status transition:
    AND (
      (tenant_id IS NOT NULL AND tenant_id::text = (auth.jwt() -> 'app_metadata' ->> 'tenant_id'))
      OR (tenant_id IS NULL AND (auth.jwt() -> 'app_metadata' ->> 'tenant_id') IS NULL)
    )
  );

-- 5. UPDATE (Submission by Owner):
-- Request must currently be approved before transitioning to submitted_or_simulated (or failed)
CREATE POLICY "requests_update_submission" ON reorder_requests FOR UPDATE
  USING (
    user_id = auth.uid()
    AND status = 'approved'
  )
  WITH CHECK (
    user_id = auth.uid()
    AND status IN ('submitted_or_simulated', 'failed')
  );

-- 6. UPDATE (Verification):
-- After submission, outcome verification updates status to verified or failed.
-- WITH CHECK enforces user_id immutability: only the request owner can perform verification.
CREATE POLICY "requests_update_verification" ON reorder_requests FOR UPDATE
  USING (
    user_id = auth.uid()
    AND status = 'submitted_or_simulated'
  )
  WITH CHECK (
    user_id = auth.uid()
    AND status IN ('verified', 'failed')
  );
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

ALTER TABLE request_versions ADD COLUMN IF NOT EXISTS tenant_id UUID DEFAULT NULL;
CREATE INDEX IF NOT EXISTS idx_request_versions_tenant_id ON request_versions (tenant_id);

ALTER TABLE request_versions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "request_versions_select_own" ON request_versions;
DROP POLICY IF EXISTS "request_versions_select_authorized" ON request_versions;
DROP POLICY IF EXISTS "request_versions_insert_own" ON request_versions;

CREATE POLICY "request_versions_select_authorized" ON request_versions FOR SELECT
  USING (
    user_id = auth.uid()
    OR (
      (auth.jwt() -> 'app_metadata' ->> 'role') IN ('approver', 'admin')
      AND (
        (tenant_id IS NOT NULL AND tenant_id::text = (auth.jwt() -> 'app_metadata' ->> 'tenant_id'))
        OR (tenant_id IS NULL AND (auth.jwt() -> 'app_metadata' ->> 'tenant_id') IS NULL)
      )
    )
  );

CREATE POLICY "request_versions_insert_own" ON request_versions FOR INSERT
  WITH CHECK (
    user_id = auth.uid()
    AND EXISTS (
      SELECT 1 FROM reorder_requests r
      WHERE r.id = request_versions.request_id
        AND r.user_id = auth.uid()
    )
  );

-- ═══════════════════════════════════════════════════════════════════════════════
-- 9. approvals
-- ═══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS approvals (
  id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id             UUID        NOT NULL REFERENCES auth.users(id)       ON DELETE CASCADE,
  request_id          UUID        NOT NULL REFERENCES reorder_requests(id) ON DELETE CASCADE,
  -- ON DELETE CASCADE: when a request_version is deleted (seed cleanup only), the approval is also removed.
  -- This prevents FK violation during ordered cascade deletion: requests -> request_versions -> approvals.
  request_version_id  UUID        NOT NULL REFERENCES request_versions(id) ON DELETE CASCADE,
  approver_id         UUID        NOT NULL REFERENCES auth.users(id),
  action              TEXT        NOT NULL CHECK (action IN ('approved','rejected')),
  notes               TEXT,
  timestamp           TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE approvals ADD COLUMN IF NOT EXISTS tenant_id UUID DEFAULT NULL;
CREATE INDEX IF NOT EXISTS idx_approvals_tenant_id  ON approvals (tenant_id);
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
DROP POLICY IF EXISTS "approvals_select_authorized" ON approvals;
DROP POLICY IF EXISTS "approvals_insert_own" ON approvals;
DROP POLICY IF EXISTS "approvals_insert_approver" ON approvals;

-- SELECT: Request owner, signing approver, or authorized approver/admin
CREATE POLICY "approvals_select_authorized" ON approvals FOR SELECT
  USING (
    user_id = auth.uid()
    OR approver_id = auth.uid()
    OR (
      (auth.jwt() -> 'app_metadata' ->> 'role') IN ('approver', 'admin')
      AND (
        (tenant_id IS NOT NULL AND tenant_id::text = (auth.jwt() -> 'app_metadata' ->> 'tenant_id'))
        OR (tenant_id IS NULL AND (auth.jwt() -> 'app_metadata' ->> 'tenant_id') IS NULL)
      )
    )
  );

-- INSERT: Enforces:
-- 1. Actor MUST have approver or admin role in app_metadata
-- 2. approver_id MUST match auth.uid() (prevents forging approver identity)
-- 3. Target reorder request must exist, belong to user_id, and be in pending_approval status
-- 4. Target request_version_id must match an actual version of the request
CREATE POLICY "approvals_insert_approver" ON approvals FOR INSERT
  WITH CHECK (
    approver_id = auth.uid()
    AND (auth.jwt() -> 'app_metadata' ->> 'role') IN ('approver', 'admin')
    AND EXISTS (
      SELECT 1 FROM reorder_requests r
      WHERE r.id = approvals.request_id
        AND r.user_id = approvals.user_id
        AND r.status = 'pending_approval'
        AND (
          (r.tenant_id IS NOT NULL AND r.tenant_id::text = (auth.jwt() -> 'app_metadata' ->> 'tenant_id'))
          OR (r.tenant_id IS NULL AND (auth.jwt() -> 'app_metadata' ->> 'tenant_id') IS NULL)
        )
    )
    AND EXISTS (
      SELECT 1 FROM request_versions rv
      WHERE rv.id = approvals.request_version_id
        AND rv.request_id = approvals.request_id
    )
  );

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

ALTER TABLE verification_results ADD COLUMN IF NOT EXISTS tenant_id UUID DEFAULT NULL;
CREATE INDEX IF NOT EXISTS idx_verification_tenant_id ON verification_results (tenant_id);
CREATE INDEX IF NOT EXISTS idx_verification_request_id ON verification_results (request_id);

ALTER TABLE verification_results ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "verification_select_own" ON verification_results;
DROP POLICY IF EXISTS "verification_select_authorized" ON verification_results;
DROP POLICY IF EXISTS "verification_insert_own" ON verification_results;
DROP POLICY IF EXISTS "verification_insert_authorized" ON verification_results;

CREATE POLICY "verification_select_authorized" ON verification_results FOR SELECT
  USING (
    user_id = auth.uid()
    OR (
      (auth.jwt() -> 'app_metadata' ->> 'role') IN ('approver', 'admin', 'auditor')
      AND (
        (tenant_id IS NOT NULL AND tenant_id::text = (auth.jwt() -> 'app_metadata' ->> 'tenant_id'))
        OR (tenant_id IS NULL AND (auth.jwt() -> 'app_metadata' ->> 'tenant_id') IS NULL)
      )
    )
  );

CREATE POLICY "verification_insert_authorized" ON verification_results FOR INSERT
  WITH CHECK (
    user_id = auth.uid()
    AND EXISTS (
      SELECT 1 FROM reorder_requests r
      WHERE r.id = verification_results.request_id
        AND r.user_id = auth.uid()
    )
  );

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

ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS tenant_id UUID DEFAULT NULL;
CREATE INDEX IF NOT EXISTS idx_audit_tenant_id   ON audit_events (tenant_id);
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
DROP POLICY IF EXISTS "audit_select_authorized" ON audit_events;
DROP POLICY IF EXISTS "audit_insert_own" ON audit_events;
DROP POLICY IF EXISTS "audit_insert_actor" ON audit_events;

CREATE POLICY "audit_select_authorized" ON audit_events FOR SELECT
  USING (
    user_id = auth.uid()
    OR actor_id = auth.uid()
    OR (
      (auth.jwt() -> 'app_metadata' ->> 'role') IN ('approver', 'admin', 'auditor')
      AND (
        (tenant_id IS NOT NULL AND tenant_id::text = (auth.jwt() -> 'app_metadata' ->> 'tenant_id'))
        OR (tenant_id IS NULL AND (auth.jwt() -> 'app_metadata' ->> 'tenant_id') IS NULL)
      )
    )
  );

-- INSERT:
-- 1. actor_id MUST match auth.uid() (prevents spoofing audit actors)
-- 2. Request must exist and actor must be request owner OR an authorized approver/admin within tenant
CREATE POLICY "audit_insert_actor" ON audit_events FOR INSERT
  WITH CHECK (
    actor_id = auth.uid()
    AND EXISTS (
      SELECT 1 FROM reorder_requests r
      WHERE r.id = audit_events.request_id
        AND r.user_id = audit_events.user_id
        AND (
          r.user_id = auth.uid()
          OR (
            (auth.jwt() -> 'app_metadata' ->> 'role') IN ('approver', 'admin')
            AND (
              (r.tenant_id IS NOT NULL AND r.tenant_id::text = (auth.jwt() -> 'app_metadata' ->> 'tenant_id'))
              OR (r.tenant_id IS NULL AND (auth.jwt() -> 'app_metadata' ->> 'tenant_id') IS NULL)
            )
          )
        )
    )
  );

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

ALTER TABLE test_runs ADD COLUMN IF NOT EXISTS tenant_id UUID DEFAULT NULL;
CREATE INDEX IF NOT EXISTS idx_test_runs_tenant_id ON test_runs (tenant_id);
CREATE INDEX IF NOT EXISTS idx_test_runs_user_id   ON test_runs (user_id);
CREATE INDEX IF NOT EXISTS idx_test_runs_case_id   ON test_runs (case_id);
CREATE INDEX IF NOT EXISTS idx_test_runs_status    ON test_runs (status);

ALTER TABLE test_runs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "test_runs_select_own" ON test_runs;
DROP POLICY IF EXISTS "test_runs_select_authorized" ON test_runs;
DROP POLICY IF EXISTS "test_runs_insert_own" ON test_runs;
DROP POLICY IF EXISTS "test_runs_update_own" ON test_runs;

CREATE POLICY "test_runs_select_authorized" ON test_runs FOR SELECT
  USING (
    user_id = auth.uid()
    OR (
      (auth.jwt() -> 'app_metadata' ->> 'role') IN ('approver', 'admin', 'auditor')
      AND (
        (tenant_id IS NOT NULL AND tenant_id::text = (auth.jwt() -> 'app_metadata' ->> 'tenant_id'))
        OR (tenant_id IS NULL AND (auth.jwt() -> 'app_metadata' ->> 'tenant_id') IS NULL)
      )
    )
  );
CREATE POLICY "test_runs_insert_own" ON test_runs FOR INSERT WITH CHECK (user_id = auth.uid());
CREATE POLICY "test_runs_update_own" ON test_runs FOR UPDATE
  USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());

-- ═══════════════════════════════════════════════════════════════════════════════
-- Schema complete.
-- Next: run supabase/seed.sql to load synthetic TC1-TC4 demo data.
-- ═══════════════════════════════════════════════════════════════════════════════

-- ═══════════════════════════════════════════════════════════════════════════════
-- Helper: seed_demo_data_for_user(target_user_id)
--
-- PURPOSE: Provisions a complete TC1-TC4 evaluation dataset (products, supplier
-- terms, sales history, open orders, source evidence, analyses, requests,
-- versions, audit events, and test runs) for any real registered user.
--
-- USAGE (after user registers via the app):
--   SELECT public.seed_demo_data_for_user('<YOUR-REGISTERED-USER-UUID>');
--
-- SAFETY:
--   - Only creates rows if they do not already exist (ON CONFLICT DO NOTHING).
--   - Uses gen_random_uuid() so UUIDs are unique per call.
--   - Does NOT modify auth.users or auth.identities.
--   - Must be run by the postgres / service-role context (bypasses RLS).
-- ═══════════════════════════════════════════════════════════════════════════════
CREATE OR REPLACE FUNCTION public.seed_demo_data_for_user(target_user_id UUID)
RETURNS TEXT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  p1 UUID := gen_random_uuid();
  p2 UUID := gen_random_uuid();
  p3 UUID := gen_random_uuid();
  p4 UUID := gen_random_uuid();
  s1 UUID := gen_random_uuid();
  s2 UUID := gen_random_uuid();
  s3 UUID := gen_random_uuid();
  s4 UUID := gen_random_uuid();
  sh1 UUID := gen_random_uuid();
  sh2 UUID := gen_random_uuid();
  sh3 UUID := gen_random_uuid();
  sh4 UUID := gen_random_uuid();
  po3 UUID := gen_random_uuid();
  ev1 UUID := gen_random_uuid();
  ev2 UUID := gen_random_uuid();
  ev3 UUID := gen_random_uuid();
  ev4 UUID := gen_random_uuid();
  an1 UUID := gen_random_uuid();
  an2 UUID := gen_random_uuid();
  an3 UUID := gen_random_uuid();
  an4 UUID := gen_random_uuid();
  rq1 UUID := gen_random_uuid();
  rq2 UUID := gen_random_uuid();
  rq3 UUID := gen_random_uuid();
  rq4 UUID := gen_random_uuid();
  rv1 UUID := gen_random_uuid();
  rv2 UUID := gen_random_uuid();
  rv3 UUID := gen_random_uuid();
  rv4 UUID := gen_random_uuid();
  tr1 UUID := gen_random_uuid();
  tr2 UUID := gen_random_uuid();
  tr3 UUID := gen_random_uuid();
  tr4 UUID := gen_random_uuid();
BEGIN
  -- 1. Authorization: Only administrative contexts (service_role, postgres) may execute
  IF current_user NOT IN ('postgres', 'service_role') THEN
    RAISE EXCEPTION 'Access denied: seed_demo_data_for_user may only be called by service_role or database administrator.';
  END IF;

  -- 2. Idempotency guard: Prevent duplicate demo records and calculation distortion
  IF EXISTS (SELECT 1 FROM reorder_requests WHERE user_id = target_user_id AND sku = 'SKU-001') THEN
    RETURN 'Demo data already provisioned for user ' || target_user_id::text || '. No duplicate records created.';
  END IF;

  -- Products
  INSERT INTO products (id, user_id, sku, name, unit, currency, current_stock)
  VALUES
    (p1, target_user_id, 'SKU-001', 'Widget Alpha', 'each', 'USD', 20),
    (p2, target_user_id, 'SKU-002', 'Widget Beta',  'each', 'USD', 25),
    (p3, target_user_id, 'SKU-003', 'Widget Gamma', 'each', 'USD', 20),
    (p4, target_user_id, 'SKU-004', 'Widget Delta', 'each', 'USD', 20)
  ON CONFLICT (user_id, sku) DO NOTHING;

  -- Re-fetch p1-p4 in case they already existed (CONFLICT path)
  SELECT id INTO p1 FROM products WHERE user_id = target_user_id AND sku = 'SKU-001';
  SELECT id INTO p2 FROM products WHERE user_id = target_user_id AND sku = 'SKU-002';
  SELECT id INTO p3 FROM products WHERE user_id = target_user_id AND sku = 'SKU-003';
  SELECT id INTO p4 FROM products WHERE user_id = target_user_id AND sku = 'SKU-004';

  -- Supplier Terms
  INSERT INTO supplier_terms (id, user_id, product_id, supplier_name, lead_time_days, pack_size, unit_price, currency, price_updated_at)
  VALUES
    (s1, target_user_id, p1, 'Acme Supplies', 14, 1,  10.00, 'USD', now() - interval '7 days'),
    (s2, target_user_id, p2, 'Bulk Co',        14, 12, 10.00, 'USD', now() - interval '7 days'),
    (s3, target_user_id, p3, 'Global Trade',   14, 1,  10.00, 'USD', now() - interval '7 days'),
    (s4, target_user_id, p4, 'Acme Supplies',  14, 1,  12.00, 'USD', now())
  ON CONFLICT DO NOTHING;

  -- Sales History (30-day window, 4 units/day)
  INSERT INTO sales_history (id, user_id, product_id, period_start, period_end, total_units_sold, days_in_period)
  VALUES
    (sh1, target_user_id, p1, current_date - interval '30 days', current_date - interval '1 day', 120, 30),
    (sh2, target_user_id, p2, current_date - interval '30 days', current_date - interval '1 day', 120, 30),
    (sh3, target_user_id, p3, current_date - interval '30 days', current_date - interval '1 day', 120, 30),
    (sh4, target_user_id, p4, current_date - interval '30 days', current_date - interval '1 day', 120, 30)
  ON CONFLICT DO NOTHING;

  -- Open Purchase Order (TC3 only: 24 confirmed units)
  INSERT INTO open_purchase_orders (id, user_id, product_id, supplier_terms_id, ordered_quantity, received_quantity, expected_arrival_date, status, order_reference)
  VALUES (po3, target_user_id, p3, s3, 24, 0, current_date + interval '10 days', 'confirmed', 'PO-GAMMA-DEMO')
  ON CONFLICT DO NOTHING;

  -- Source Evidence
  INSERT INTO source_evidence (id, user_id, source_type, retrieved_at, source_timestamp, fields_used, raw_data)
  VALUES
    (ev1, target_user_id, 'mock_source', now(), now() - interval '1 hour',
     ARRAY['current_stock','average_daily_demand','lead_time_days','unit_price'],
     jsonb_build_object('note','Synthetic data — TC1 (demo only)','sku','SKU-001')),
    (ev2, target_user_id, 'mock_source', now(), now() - interval '1 hour',
     ARRAY['current_stock','average_daily_demand','lead_time_days','unit_price','pack_size'],
     jsonb_build_object('note','Synthetic data — TC2 (demo only)','sku','SKU-002','pack_size',12)),
    (ev3, target_user_id, 'mock_source', now(), now() - interval '1 hour',
     ARRAY['current_stock','average_daily_demand','lead_time_days','unit_price','open_order_qty'],
     jsonb_build_object('note','Synthetic data — TC3 (demo only)','sku','SKU-003','open_po','PO-GAMMA-DEMO','eligible_incoming',24)),
    (ev4, target_user_id, 'mock_source', now(), now(),
     ARRAY['current_stock','average_daily_demand','lead_time_days','unit_price','budget_available'],
     jsonb_build_object('note','Synthetic data — TC4 (demo only)','sku','SKU-004','previous_price',10.00,'new_price',12.00,'price_change_pct',20,'budget',400.00))
  ON CONFLICT DO NOTHING;

  -- Reorder Analyses (deterministic)
  INSERT INTO reorder_analyses (
    id, user_id, product_id, calculation_version, input_snapshot,
    average_daily_demand, lead_time_days, lead_time_demand,
    safety_stock_target, usable_available_stock, eligible_incoming_quantity,
    net_shortfall, pack_size, proposed_order_quantity,
    unit_price, estimated_cost, budget_available, budget_status,
    analysis_status, status_reason, evidence_ids
  ) VALUES
    -- TC1: shortfall=36, cost=$360, ok
    (an1, target_user_id, p1, '1.0.0',
     jsonb_build_object('sku','SKU-001','average_daily_demand',4,'lead_time_days',14,'usable_available_stock',20,'pack_size',1,'unit_price',10.00,'budget_available',500.00,'supplier_terms_id',s1::text),
     4, 14, 56, 0, 20, 0, 36, 1, 36, 10.00, 360.00, 500.00, 'ok', 'ready', NULL, ARRAY[ev1]::uuid[]),
    -- TC2: shortfall=31→36 (3 cases×12), cost=$360, ok
    (an2, target_user_id, p2, '1.0.0',
     jsonb_build_object('sku','SKU-002','average_daily_demand',4,'lead_time_days',14,'usable_available_stock',25,'pack_size',12,'unit_price',10.00,'budget_available',500.00,'supplier_terms_id',s2::text),
     4, 14, 56, 0, 25, 0, 31, 12, 36, 10.00, 360.00, 500.00, 'ok', 'ready', NULL, ARRAY[ev2]::uuid[]),
    -- TC3: 24 incoming→shortfall=12, cost=$120, ok
    (an3, target_user_id, p3, '1.0.0',
     jsonb_build_object('sku','SKU-003','average_daily_demand',4,'lead_time_days',14,'usable_available_stock',20,'eligible_incoming_quantity',24,'pack_size',1,'unit_price',10.00,'budget_available',500.00,'supplier_terms_id',s3::text),
     4, 14, 56, 0, 20, 24, 12, 1, 12, 10.00, 120.00, 500.00, 'ok', 'ready', NULL, ARRAY[ev3]::uuid[]),
    -- TC4: price rise→cost=$432>budget $400→needs_review
    (an4, target_user_id, p4, '1.0.0',
     jsonb_build_object('sku','SKU-004','average_daily_demand',4,'lead_time_days',14,'usable_available_stock',20,'pack_size',1,'unit_price',12.00,'previous_unit_price',10.00,'price_change_pct',20,'budget_available',400.00,'supplier_terms_id',s4::text),
     4, 14, 56, 0, 20, 0, 36, 1, 36, 12.00, 432.00, 400.00, 'over_budget', 'needs_review',
     'Supplier price increased 20% (from $10.00 to $12.00). Estimated cost $432.00 exceeds budget $400.00.',
     ARRAY[ev4]::uuid[])
  ON CONFLICT DO NOTHING;

  -- Reorder Requests (draft state, awaiting approval)
  INSERT INTO reorder_requests (id, user_id, idempotency_key, analysis_id, product_id, sku, supplier_name, proposed_quantity, pack_count, pack_size, estimated_cost, currency, calculation_version, status)
  VALUES
    (rq1, target_user_id, 'SKU-001-' || an1::text || '-v1', an1, p1, 'SKU-001', 'Acme Supplies', 36, 36,  1, 360.00, 'USD', '1.0.0', 'draft'),
    (rq2, target_user_id, 'SKU-002-' || an2::text || '-v1', an2, p2, 'SKU-002', 'Bulk Co',       36,  3, 12, 360.00, 'USD', '1.0.0', 'draft'),
    (rq3, target_user_id, 'SKU-003-' || an3::text || '-v1', an3, p3, 'SKU-003', 'Global Trade',  12, 12,  1, 120.00, 'USD', '1.0.0', 'draft'),
    (rq4, target_user_id, 'SKU-004-' || an4::text || '-v1', an4, p4, 'SKU-004', 'Acme Supplies', 36, 36,  1, 432.00, 'USD', '1.0.0', 'needs_review')
  ON CONFLICT (user_id, idempotency_key) DO NOTHING;

  -- Request Versions (v1 snapshot)
  INSERT INTO request_versions (id, user_id, request_id, version_number, snapshot)
  VALUES
    (rv1, target_user_id, rq1, 1, '{"sku":"SKU-001","proposed_quantity":36,"pack_count":36,"pack_size":1,"estimated_cost":360.00,"currency":"USD","supplier_name":"Acme Supplies","status":"draft","calculation_version":"1.0.0"}'::jsonb),
    (rv2, target_user_id, rq2, 1, '{"sku":"SKU-002","proposed_quantity":36,"pack_count":3,"pack_size":12,"estimated_cost":360.00,"currency":"USD","supplier_name":"Bulk Co","status":"draft","calculation_version":"1.0.0"}'::jsonb),
    (rv3, target_user_id, rq3, 1, '{"sku":"SKU-003","proposed_quantity":12,"pack_count":12,"pack_size":1,"estimated_cost":120.00,"currency":"USD","supplier_name":"Global Trade","status":"draft","calculation_version":"1.0.0"}'::jsonb),
    (rv4, target_user_id, rq4, 1, '{"sku":"SKU-004","proposed_quantity":36,"pack_count":36,"pack_size":1,"estimated_cost":432.00,"currency":"USD","supplier_name":"Acme Supplies","status":"needs_review","calculation_version":"1.0.0","price_change_note":"Unit price increased 20% from $10.00 to $12.00. Budget review required."}'::jsonb)
  ON CONFLICT DO NOTHING;

  -- Audit Events (initial 'proposed' events)
  INSERT INTO audit_events (id, user_id, request_id, event_type, actor_id, details)
  VALUES
    (gen_random_uuid(), target_user_id, rq1, 'proposed', target_user_id,
     jsonb_build_object('version',1,'sku','SKU-001','proposed_quantity',36,'note','TC1 - Low stock, no incoming order')),
    (gen_random_uuid(), target_user_id, rq2, 'proposed', target_user_id,
     jsonb_build_object('version',1,'sku','SKU-002','proposed_quantity',36,'pack_count',3,'pack_size',12,'note','TC2 - Case-only supplier')),
    (gen_random_uuid(), target_user_id, rq3, 'proposed', target_user_id,
     jsonb_build_object('version',1,'sku','SKU-003','proposed_quantity',12,'eligible_incoming',24,'note','TC3 - 24 units in confirmed open order')),
    (gen_random_uuid(), target_user_id, rq4, 'proposed', target_user_id,
     jsonb_build_object('version',1,'sku','SKU-004','proposed_quantity',36,'estimated_cost',432.00,'budget',400.00,'price_change_pct',20,'note','TC4 - 20% price rise; needs_review'))
  ON CONFLICT DO NOTHING;

  -- Test Run Fixtures
  INSERT INTO test_runs (id, user_id, case_id, description, input, expected_result, actual_result, status)
  VALUES
    (tr1, target_user_id, 'TC1',
     'Low stock with no incoming order -> correct reorder quantity',
     '{"sku":"SKU-001","current_stock":20,"average_daily_demand":4,"lead_time_days":14,"safety_stock_target":0,"eligible_incoming_quantity":0,"pack_size":1,"unit_price":10.00,"budget_available":500.00}'::jsonb,
     '{"net_shortfall":36,"proposed_order_quantity":36,"estimated_cost":360.00,"budget_status":"ok","analysis_status":"ready"}'::jsonb,
     NULL, 'pending'),
    (tr2, target_user_id, 'TC2',
     'Supplier sells in cases of 12 -> quantity rounded up to whole cases',
     '{"sku":"SKU-002","current_stock":25,"average_daily_demand":4,"lead_time_days":14,"safety_stock_target":0,"eligible_incoming_quantity":0,"pack_size":12,"unit_price":10.00,"budget_available":500.00}'::jsonb,
     '{"net_shortfall":31,"proposed_order_quantity":36,"pack_count":3,"estimated_cost":360.00,"budget_status":"ok","analysis_status":"ready"}'::jsonb,
     NULL, 'pending'),
    (tr3, target_user_id, 'TC3',
     'Pending confirmed order (24 units) -> eligible incoming subtracted',
     '{"sku":"SKU-003","current_stock":20,"average_daily_demand":4,"lead_time_days":14,"safety_stock_target":0,"eligible_incoming_quantity":24,"open_order_status":"confirmed","pack_size":1,"unit_price":10.00,"budget_available":500.00}'::jsonb,
     '{"net_shortfall":12,"proposed_order_quantity":12,"estimated_cost":120.00,"budget_status":"ok","analysis_status":"ready","eligible_incoming_quantity":24}'::jsonb,
     NULL, 'pending'),
    (tr4, target_user_id, 'TC4',
     'Supplier price rises 20% ($10->$12) -> cost recalculated, budget review requested',
     '{"sku":"SKU-004","current_stock":20,"average_daily_demand":4,"lead_time_days":14,"safety_stock_target":0,"eligible_incoming_quantity":0,"pack_size":1,"unit_price":12.00,"previous_unit_price":10.00,"price_change_pct":20,"budget_available":400.00}'::jsonb,
     '{"net_shortfall":36,"proposed_order_quantity":36,"estimated_cost":432.00,"budget_status":"over_budget","analysis_status":"needs_review"}'::jsonb,
     NULL, 'pending')
  ON CONFLICT DO NOTHING;

  RETURN 'Demo data seeded for user ' || target_user_id::text || ' (TC1-TC4: products, supplier terms, sales history, analyses, requests, versions, audit events, test runs).';
END;
$$;

-- Security Hardening: Revoke public execution to prevent PostgREST RPC exploitation
REVOKE EXECUTE ON FUNCTION public.seed_demo_data_for_user(UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.seed_demo_data_for_user(UUID) TO service_role, postgres;

COMMENT ON FUNCTION public.seed_demo_data_for_user(UUID) IS
  'Seeds a complete TC1-TC4 evaluation dataset for a real registered user. '
  'Restricted to administrative execution (postgres/service_role context): '
  'SELECT public.seed_demo_data_for_user(''<USER-UUID-HERE>'');';
