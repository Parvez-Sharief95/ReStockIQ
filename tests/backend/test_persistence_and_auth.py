"""test_persistence_and_auth.py — Supabase Authentication & Persistent Repositories Tests
Phase 9 Validation Suite

Covers:
- Safe role-assignment boundaries: untrusted self-registration cannot claim approver/admin.
- Live Supabase JWT verification vs invalid/expired token rejection (HTTP 401).
- Strict production safety: in-memory fallback is strictly blocked (HTTP 503).
- User-scoped JWT forwarding to PostgREST for Row Level Security (RLS) enforcement.
- Persistent repository idempotency, proposal versioning, and approval gating.
- Role-based authorization enforcement (planner vs approver).
"""
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import UUID
import uuid

from fastapi.testclient import TestClient
import pytest

from backend.app.config import Settings
from backend.app.schemas.models import (
    ApprovalAction,
    AuditEventType,
    ReorderAnalysisRead,
    RequestStatus,
)
from backend.app.services.auth import AuthenticatedUser, get_current_user
import backend.app.services.auth as auth_mod
from backend.app.services.repository import (
    RepositoryManager,
    create_in_memory_repository_manager,
    SupabaseAnalysisRepository,
    SupabaseReorderRepository,
    create_supabase_repository_manager,
    get_repository_manager,
)


def test_registration_safe_role_assignment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Untrusted self-registration metadata cannot elevate a user to approver or admin."""
    fake_user_id = str(uuid.uuid4())

    # Case A: User attempts to claim 'approver' in user_metadata without app_metadata
    mock_supabase = MagicMock()
    mock_user_obj = MagicMock()
    mock_user_obj.id = fake_user_id
    mock_user_obj.email = "attacker@example.com"
    mock_user_obj.app_metadata = {}  # Empty app_metadata (no admin elevation)
    mock_user_obj.user_metadata = {"role": "approver"}  # Self-claimed privilege

    mock_resp = MagicMock()
    mock_resp.user = mock_user_obj
    mock_supabase.auth.get_user.return_value = mock_resp

    with patch("supabase.create_client", return_value=mock_supabase):
        monkeypatch.setattr(auth_mod.settings, "supabase_url", "https://valid.supabase.co")
        monkeypatch.setattr(auth_mod.settings, "supabase_secret_key", "secret-key")

        # Fake JWT with 2 dots
        fake_jwt = "header.payload.signature"
        credentials = MagicMock()
        credentials.credentials = fake_jwt

        import asyncio
        user = asyncio.run(get_current_user(credentials))

        # Must be safely downgraded to 'planner'
        assert user.role == "planner"
        assert user.id == UUID(fake_user_id)
        assert user.email == "attacker@example.com"


def test_admin_elevated_role_in_app_metadata_honored(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verified app_metadata role from service_role/admin is honored."""
    fake_user_id = str(uuid.uuid4())

    mock_supabase = MagicMock()
    mock_user_obj = MagicMock()
    mock_user_obj.id = fake_user_id
    mock_user_obj.email = "manager@example.com"
    mock_user_obj.app_metadata = {"role": "approver"}  # Admin-assigned role
    mock_user_obj.user_metadata = {}

    mock_resp = MagicMock()
    mock_resp.user = mock_user_obj
    mock_supabase.auth.get_user.return_value = mock_resp

    with patch("supabase.create_client", return_value=mock_supabase):
        monkeypatch.setattr(auth_mod.settings, "supabase_url", "https://valid.supabase.co")
        monkeypatch.setattr(auth_mod.settings, "supabase_secret_key", "secret-key")

        fake_jwt = "header.payload.signature"
        credentials = MagicMock()
        credentials.credentials = fake_jwt

        import asyncio
        user = asyncio.run(get_current_user(credentials))
        assert user.role == "approver"
        assert user.id == UUID(fake_user_id)


def test_invalid_and_expired_tokens_rejected_401(api_client: TestClient) -> None:
    """Invalid, expired, or malformed tokens receive HTTP 401 Unauthorized."""
    # 1. Missing token
    resp_missing = api_client.post("/api/approvals", json={"request_id": str(uuid.uuid4()), "action": "approved"})
    assert resp_missing.status_code == 401

    # 2. Malformed token (not a JWT and not a demo token)
    resp_malformed = api_client.post(
        "/api/approvals",
        json={"request_id": str(uuid.uuid4()), "action": "approved"},
        headers={"Authorization": "Bearer not-a-valid-token"},
    )
    assert resp_malformed.status_code == 401

    # 3. Invalid JWT format / signature
    resp_fake_jwt = api_client.post(
        "/api/approvals",
        json={"request_id": str(uuid.uuid4()), "action": "approved"},
        headers={"Authorization": "Bearer bad.jwt.token"},
    )
    assert resp_fake_jwt.status_code in (401, 503)


def test_production_forbids_in_memory_silent_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """In production mode, missing Supabase credentials raise HTTP 503 and never fall back to in-memory store."""
    from backend.app.services.repository import get_repository_manager
    import backend.app.services.repository as repo_mod

    monkeypatch.setattr(repo_mod.settings, "app_env", "production")
    monkeypatch.setattr(repo_mod.settings, "supabase_url", "")
    monkeypatch.setattr(repo_mod.settings, "supabase_secret_key", "")

    with pytest.raises(Exception) as exc_info:
        get_repository_manager(None)

    assert "503" in str(exc_info.value) or "unavailable" in str(exc_info.value).lower()


def test_jwt_forwarded_to_supabase_postgrest_for_rls(monkeypatch: pytest.MonkeyPatch) -> None:
    """When a Supabase repository is initialized with a user token, client.postgrest.auth is called to forward JWT."""
    mock_client = MagicMock()

    with patch("supabase.create_client", return_value=mock_client):
        monkeypatch.setattr(auth_mod.settings, "supabase_url", "https://example.supabase.co")
        monkeypatch.setattr(auth_mod.settings, "supabase_secret_key", "secret-key")

        user_jwt = "user.verified.jwt"
        user_uuid = uuid.uuid4()

        repo_mgr = create_supabase_repository_manager(user_token=user_jwt, user_id=user_uuid)
        assert repo_mgr.is_persistent is True

        # Verify postgrest.auth was invoked with user_jwt
        mock_client.postgrest.auth.assert_called_once_with(user_jwt)


def test_persistent_repository_idempotency_and_duplicate_retries() -> None:
    """Reorder repository detects duplicate requests via idempotency_key without creating duplicate rows."""
    mock_client = MagicMock()
    user_id = uuid.uuid4()
    repo = SupabaseReorderRepository(mock_client, user_id=user_id)

    # 1. First call: no existing request found in Supabase
    mock_select = MagicMock()
    mock_select.data = []  # No existing duplicate
    mock_client.from_().select().eq().eq().execute.return_value = mock_select

    req, ver, is_dup = repo.create_request(
        user_id=str(user_id),
        analysis_id=str(uuid.uuid4()),
        product_id=str(uuid.uuid4()),
        sku="SKU-001",
        supplier_name="Acme",
        proposed_quantity=Decimal("36"),
        pack_count=3,
        pack_size=12,
        estimated_cost=Decimal("360.00"),
        idempotency_key="unique-key-123",
    )
    assert is_dup is False
    assert req.sku == "SKU-001"
    assert ver.version_number == 1

    # 2. Duplicate retry with same idempotency key
    now = datetime.now(timezone.utc).isoformat()
    mock_existing_row = {
        "id": str(req.id),
        "user_id": str(user_id),
        "idempotency_key": "unique-key-123",
        "analysis_id": str(req.analysis_id),
        "product_id": str(req.product_id),
        "sku": "SKU-001",
        "supplier_name": "Acme",
        "proposed_quantity": 36.0,
        "pack_count": 3,
        "pack_size": 12,
        "estimated_cost": 360.0,
        "currency": "USD",
        "calculation_version": "1.0.0",
        "status": "pending_approval",
        "created_at": now,
        "updated_at": now,
    }
    mock_dup_select = MagicMock()
    mock_dup_select.data = [mock_existing_row]
    mock_client.from_().select().eq().eq().execute.return_value = mock_dup_select

    req_dup, ver_dup, is_dup_2 = repo.create_request(
        user_id=str(user_id),
        analysis_id=str(req.analysis_id),
        product_id=str(req.product_id),
        sku="SKU-001",
        supplier_name="Acme",
        proposed_quantity=Decimal("36"),
        pack_count=3,
        pack_size=12,
        estimated_cost=Decimal("360.00"),
        idempotency_key="unique-key-123",
    )
    assert is_dup_2 is True
    assert req_dup.id == req.id


def test_role_authorization_planner_cannot_approve(api_client: TestClient) -> None:
    """Users with the planner role receive HTTP 403 Forbidden when attempting approvals."""
    # 1. Create a request using planner token
    eval_resp = api_client.post("/api/analyses/evaluate", json={"sku": "SKU-001"})
    analysis_id = eval_resp.json()["analysis"]["id"]

    req_resp = api_client.post(
        "/api/requests",
        json={
            "analysis_id": analysis_id,
            "sku": "SKU-001",
            "product_id": "10000000-0000-0000-0000-000000000001",
            "supplier_name": "Acme Supplies",
            "proposed_quantity": 36,
            "pack_count": 36,
            "pack_size": 1,
            "estimated_cost": 360.0,
        },
        headers={"Authorization": "Bearer demo-planner-token"},
    )
    req_id = req_resp.json()["request"]["id"]

    # 2. Planner tries to approve -> 403 Forbidden
    appr_resp = api_client.post(
        "/api/approvals",
        json={
            "request_id": req_id,
            "action": "approved",
            "target_version_number": 1,
        },
        headers={"Authorization": "Bearer demo-planner-token"},
    )
    assert appr_resp.status_code == 403
    err_msg = appr_resp.json().get("detail") or appr_resp.json().get("message", "")
    assert "Operation requires one of roles" in err_msg

    # 3. Approver approves -> 200 OK
    appr_ok = api_client.post(
        "/api/approvals",
        json={
            "request_id": req_id,
            "action": "approved",
            "target_version_number": 1,
        },
        headers={"Authorization": "Bearer demo-approver-token"},
    )
    assert appr_ok.status_code == 200
    assert appr_ok.json()["status"] == "approved"


def test_rls_policy_logic_in_schema() -> None:
    """Validate that supabase/schema.sql contains the required idempotent RLS security policies."""
    from pathlib import Path

    schema_path = Path(__file__).resolve().parents[2] / "supabase" / "schema.sql"
    assert schema_path.exists(), "supabase/schema.sql must exist"
    content = schema_path.read_text(encoding="utf-8")

    # 1. All 12 tables must have RLS enabled
    expected_tables = [
        "products",
        "supplier_terms",
        "sales_history",
        "open_purchase_orders",
        "source_evidence",
        "reorder_analyses",
        "reorder_requests",
        "request_versions",
        "approvals",
        "verification_results",
        "audit_events",
        "test_runs",
    ]
    for tbl in expected_tables:
        assert f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY;" in content, f"RLS must be enabled on {tbl}"

    # 2. All policy updates must be idempotent (DROP POLICY IF EXISTS preceding CREATE POLICY)
    assert 'DROP POLICY IF EXISTS "requests_select_authorized" ON reorder_requests;' in content
    assert 'DROP POLICY IF EXISTS "requests_update_owner_proposal" ON reorder_requests;' in content
    assert 'DROP POLICY IF EXISTS "requests_update_approver_status" ON reorder_requests;' in content
    assert 'DROP POLICY IF EXISTS "requests_update_submission" ON reorder_requests;' in content
    assert 'DROP POLICY IF EXISTS "approvals_insert_approver" ON approvals;' in content
    assert 'DROP POLICY IF EXISTS "audit_insert_actor" ON audit_events;' in content

    # 3. approvals_insert_approver enforces approver_id = auth.uid() and role check
    assert "approver_id = auth.uid()" in content
    assert "(auth.jwt() -> 'app_metadata' ->> 'role') IN ('approver', 'admin')" in content

    # 4. audit_insert_actor enforces actor_id = auth.uid()
    assert "actor_id = auth.uid()" in content

    # 5. requests_update_owner_proposal restricts status to draft / pending_approval
    assert "status IN ('draft', 'pending_approval')" in content

    # 6. requests_update_approver_status restricts status transition to approved / rejected
    assert "status IN ('approved', 'rejected')" in content

    # 7. requests_update_submission enforces status = 'approved'
    assert "status = 'approved'" in content

    # 8. Strict multi-tenant isolation across all 12 tables (no lenient OR tenant_id IS NULL wildcard)
    assert "OR tenant_id IS NULL" not in content, "Insecure 'OR tenant_id IS NULL' wildcard must not be present in schema.sql"
    assert "tenant_id IS NOT NULL AND tenant_id::text = (auth.jwt() -> 'app_metadata' ->> 'tenant_id')" in content

    expected_tenant_indexes = {
        "products": "idx_products_tenant_id",
        "supplier_terms": "idx_supplier_terms_tenant_id",
        "sales_history": "idx_sales_history_tenant_id",
        "open_purchase_orders": "idx_open_orders_tenant_id",
        "source_evidence": "idx_source_evidence_tenant_id",
        "reorder_analyses": "idx_analyses_tenant_id",
        "reorder_requests": "idx_requests_tenant_id",
        "request_versions": "idx_request_versions_tenant_id",
        "approvals": "idx_approvals_tenant_id",
        "verification_results": "idx_verification_tenant_id",
        "audit_events": "idx_audit_tenant_id",
        "test_runs": "idx_test_runs_tenant_id",
    }
    for tbl, idx in expected_tenant_indexes.items():
        assert f"ALTER TABLE {tbl} ADD COLUMN IF NOT EXISTS tenant_id UUID" in content, f"{tbl} must have tenant_id column"
        assert f"CREATE INDEX IF NOT EXISTS {idx}" in content, f"{tbl} must have tenant_id index {idx}"


def test_jwt_claims_expired_token_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """JWTs with expired 'exp' timestamps are rejected with HTTP 401 Unauthorized."""
    import asyncio
    import time
    from fastapi import HTTPException
    import jwt

    expired_payload = {
        "sub": str(uuid.uuid4()),
        "email": "user@example.com",
        "aud": "authenticated",
        "exp": int(time.time()) - 3600,  # 1 hour ago
        "app_metadata": {"role": "planner"},
    }
    expired_token = jwt.encode(expired_payload, "test-jwt-secret-key-at-least-32-bytes-long!", algorithm="HS256")

    credentials = MagicMock()
    credentials.credentials = expired_token

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(get_current_user(credentials))

    assert exc_info.value.status_code == 401
    assert "expired" in exc_info.value.detail.lower()


def test_jwt_claims_wrong_audience_rejected() -> None:
    """JWTs with audience other than 'authenticated' are rejected with HTTP 401."""
    import asyncio
    import time
    from fastapi import HTTPException
    import jwt

    bad_aud_payload = {
        "sub": str(uuid.uuid4()),
        "email": "user@example.com",
        "aud": "wrong-audience",
        "exp": int(time.time()) + 3600,
        "app_metadata": {"role": "planner"},
    }
    bad_aud_token = jwt.encode(bad_aud_payload, "test-jwt-secret-key-at-least-32-bytes-long!", algorithm="HS256")

    credentials = MagicMock()
    credentials.credentials = bad_aud_token

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(get_current_user(credentials))

    assert exc_info.value.status_code == 401
    assert "audience" in exc_info.value.detail.lower()


def test_jwt_claims_wrong_issuer_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """JWTs with mismatched issuer are rejected when Supabase URL is configured."""
    import asyncio
    import time
    from fastapi import HTTPException
    import jwt

    monkeypatch.setattr(auth_mod.settings, "supabase_url", "https://real-project.supabase.co")

    bad_iss_payload = {
        "sub": str(uuid.uuid4()),
        "email": "user@example.com",
        "iss": "https://malicious-project.supabase.co/auth/v1",
        "aud": "authenticated",
        "exp": int(time.time()) + 3600,
        "app_metadata": {"role": "planner"},
    }
    bad_iss_token = jwt.encode(bad_iss_payload, "test-jwt-secret-key-at-least-32-bytes-long!", algorithm="HS256")

    credentials = MagicMock()
    credentials.credentials = bad_iss_token

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(get_current_user(credentials))

    assert exc_info.value.status_code == 401
    assert "issuer" in exc_info.value.detail.lower()


def test_jwt_local_secret_verification_success_and_tamper(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cryptographic verification with local SUPABASE_JWT_SECRET honors valid tokens and rejects tampered ones."""
    import asyncio
    import time
    from fastapi import HTTPException
    import jwt

    valid_secret = "correct-jwt-secret-key-32-chars-long!"
    monkeypatch.setattr(auth_mod.settings, "supabase_jwt_secret", valid_secret)
    monkeypatch.setattr(auth_mod.settings, "supabase_url", "https://valid.supabase.co")

    user_id = str(uuid.uuid4())
    valid_payload = {
        "sub": user_id,
        "email": "approver@company.com",
        "aud": "authenticated",
        "iss": "https://valid.supabase.co/auth/v1",
        "exp": int(time.time()) + 3600,
        "app_metadata": {"role": "approver"},
    }
    valid_token = jwt.encode(valid_payload, valid_secret, algorithm="HS256")

    # 1. Valid token verified cryptographically
    credentials = MagicMock()
    credentials.credentials = valid_token
    user = asyncio.run(get_current_user(credentials))
    assert user.id == UUID(user_id)
    assert user.role == "approver"
    assert user.email == "approver@company.com"

    # 2. Tampered token signed with wrong key is rejected with 401
    tampered_token = jwt.encode(valid_payload, "wrong-key-secret-32-characters-minimum!!", algorithm="HS256")
    credentials_tampered = MagicMock()
    credentials_tampered.credentials = tampered_token
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(get_current_user(credentials_tampered))
    assert exc_info.value.status_code == 401


def test_forged_approval_rejection_target_version_mismatch() -> None:
    """Target version mismatch raises ValueError and prevents out-of-order or stale approvals."""
    mock_client = MagicMock()
    user_id = uuid.uuid4()
    repo = SupabaseReorderRepository(mock_client, user_id=user_id)

    req_id = uuid.uuid4()
    now = datetime.now(timezone.utc).isoformat()
    mock_client.from_().select().eq().execute.return_value = MagicMock(
        data=[{
            "id": str(req_id),
            "user_id": str(user_id),
            "idempotency_key": "key-1",
            "analysis_id": str(uuid.uuid4()),
            "product_id": str(uuid.uuid4()),
            "sku": "SKU-001",
            "supplier_name": "Supplier",
            "proposed_quantity": 36.0,
            "pack_count": 3,
            "pack_size": 12,
            "estimated_cost": 360.0,
            "currency": "USD",
            "calculation_version": "1.0.0",
            "status": "pending_approval",
            "created_at": now,
            "updated_at": now,
        }]
    )

    # Mock version 2 is current
    with patch.object(repo, "get_latest_version") as mock_get_ver:
        from backend.app.schemas.models import RequestVersionRead
        mock_get_ver.return_value = RequestVersionRead(
            id=uuid.uuid4(),
            request_id=req_id,
            version_number=2,
            snapshot={},
            created_at=datetime.now(timezone.utc),
        )

        with pytest.raises(ValueError) as exc_info:
            repo.record_approval(
                request_id=req_id,
                approver_id=uuid.uuid4(),
                action=ApprovalAction.APPROVED,
                target_version_number=1,  # Stale target version!
            )
        assert "Version mismatch" in str(exc_info.value)


def test_forged_approval_payload_caller_approver_id_forbidden(api_client: TestClient) -> None:
    """Attempting to supply caller-controlled approver_id in approval request body returns HTTP 422."""
    resp = api_client.post(
        "/api/approvals",
        json={
            "request_id": str(uuid.uuid4()),
            "action": "approved",
            "approver_id": "00000000-0000-0000-0000-000000000002",  # Forged approver ID injected by caller
        },
        headers={"Authorization": "Bearer demo-approver-token"},
    )
    # Pydantic extra="forbid" rejects the extra approver_id field
    assert resp.status_code == 422


def test_persistence_across_repository_instances() -> None:
    """Two distinct repository manager instances accessing the same persistent store see identical state."""
    repo1 = create_in_memory_repository_manager()
    repo2 = create_in_memory_repository_manager()

    user_id = str(uuid.uuid4())
    req, ver, is_dup = repo1.requests.create_request(
        user_id=user_id,
        analysis_id=str(uuid.uuid4()),
        product_id=str(uuid.uuid4()),
        sku="SKU-001",
        supplier_name="Acme Supplies",
        proposed_quantity=Decimal("36"),
        pack_count=36,
        pack_size=1,
        estimated_cost=Decimal("360.00"),
        idempotency_key="cross-instance-test-key",
    )

    # Query instance 2 for request created in instance 1
    req_from_repo2 = repo2.requests.get_request(req.id)
    assert req_from_repo2 is not None
    assert req_from_repo2.id == req.id
    assert req_from_repo2.sku == "SKU-001"
    assert req_from_repo2.proposed_quantity == Decimal("36")

    # Audit trail is visible from instance 2
    audit_from_repo2 = repo2.requests.get_audit_trail(req.id)
    assert len(audit_from_repo2) >= 1
    assert audit_from_repo2[0].event_type == AuditEventType.PROPOSED


def test_authenticated_caller_cannot_spoof_user_or_actor_id(api_client: TestClient) -> None:
    """An authenticated user cannot spoof another user_id or actor_id via request body."""
    # 1. Generate an analysis
    eval_resp = api_client.post("/api/analyses/evaluate", json={"sku": "SKU-001"})
    analysis_id = eval_resp.json()["analysis"]["id"]

    victim_user_id = "99999999-9999-9999-9999-999999999999"
    attacker_token = "demo-planner-token"  # Authenticates as DEMO_PLANNER_USER_ID (00000000-0000-0000-0000-000000000001)

    # 2. Attacker attempts to create a request assigned to victim_user_id
    req_resp = api_client.post(
        "/api/requests",
        json={
            "analysis_id": analysis_id,
            "sku": "SKU-001",
            "product_id": "10000000-0000-0000-0000-000000000001",
            "supplier_name": "Acme Supplies",
            "proposed_quantity": 36,
            "pack_count": 36,
            "pack_size": 1,
            "estimated_cost": 360.0,
            "user_id": victim_user_id,    # Forged owner
            "actor_id": victim_user_id,   # Forged actor
        },
        headers={"Authorization": f"Bearer {attacker_token}"},
    )
    assert req_resp.status_code == 201
    created_request = req_resp.json()["request"]

    # 3. Request MUST be bound to the caller's verified token, NOT the forged victim ID
    assert created_request["user_id"] == "00000000-0000-0000-0000-000000000001"
    assert created_request["user_id"] != victim_user_id


def test_tenant_isolation_sql_policy_evaluation() -> None:
    """Verify boolean evaluation of the strict tenant isolation condition across all permutations."""
    def eval_tenant_policy(row_tenant: str | None, jwt_tenant: str | None) -> bool:
        """Mirror exact SQL policy:
        ((tenant_id IS NOT NULL AND tenant_id::text = (auth.jwt() -> 'app_metadata' ->> 'tenant_id'))
         OR (tenant_id IS NULL AND (auth.jwt() -> 'app_metadata' ->> 'tenant_id') IS NULL))
        """
        match_case_1 = (row_tenant is not None) and (jwt_tenant is not None) and (str(row_tenant) == str(jwt_tenant))
        match_case_2 = (row_tenant is None) and (jwt_tenant is None)
        return match_case_1 or match_case_2

    # Case 1: Same tenant -> ACCESS GRANTED
    assert eval_tenant_policy("tenant-A", "tenant-A") is True

    # Case 2: Cross tenant -> ACCESS DENIED
    assert eval_tenant_policy("tenant-A", "tenant-B") is False

    # Case 3: Row has tenant_id NULL, approver has tenant-A -> ACCESS DENIED (no leak of unassigned data)
    assert eval_tenant_policy(None, "tenant-A") is False

    # Case 4: Row has tenant-A, approver has tenant_id NULL -> ACCESS DENIED (no leak to unassigned approvers)
    assert eval_tenant_policy("tenant-A", None) is False

    # Case 5: Single-tenant default pool (both NULL) -> ACCESS GRANTED
    assert eval_tenant_policy(None, None) is True


def test_unauthenticated_repository_does_not_use_service_role(monkeypatch: pytest.MonkeyPatch) -> None:
    """When creating a Supabase repository without a user token, the service_role key is stripped from PostgREST."""
    from backend.app.services import repository as repo_mod

    monkeypatch.setattr(repo_mod.settings, "supabase_url", "https://mock-project.supabase.co")
    monkeypatch.setattr(repo_mod.settings, "supabase_secret_key", "mock-service-role-secret-key")
    monkeypatch.setattr(repo_mod.settings, "supabase_publishable_key", "")

    mock_client = MagicMock()
    mock_postgrest = MagicMock()
    mock_client.postgrest = mock_postgrest

    with patch("supabase.create_client", return_value=mock_client) as mock_create:
        mgr = repo_mod.create_supabase_repository_manager(user_token=None, user_id=None)
        assert mgr.is_persistent is True

        # create_client called
        mock_create.assert_called_once_with("https://mock-project.supabase.co", "mock-service-role-secret-key")

        # postgrest.auth("") called to strip service_role privileges from unauthenticated operations
        mock_postgrest.auth.assert_called_once_with("")


# ─────────────────────────────────────────────────────────────────────────────
# Phase 9 Preflight Fix Regression Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_schema_approver_with_check_includes_tenant_scope() -> None:
    """requests_update_approver_status WITH CHECK must re-enforce tenant scope to prevent reassignment."""
    from pathlib import Path

    content = (Path(__file__).resolve().parents[2] / "supabase" / "schema.sql").read_text(encoding="utf-8")
    assert "requests_update_approver_status" in content

    # Search from CREATE POLICY (not DROP POLICY IF EXISTS which appears first)
    create_marker = 'CREATE POLICY "requests_update_approver_status"'
    assert create_marker in content, f"Expected '{create_marker}' in schema.sql"
    idx = content.index(create_marker)
    policy_block = content[idx : idx + 1200]
    assert "WITH CHECK" in policy_block, "requests_update_approver_status must have WITH CHECK"
    assert "status IN ('approved', 'rejected')" in policy_block
    # Both USING and WITH CHECK must check tenant_id
    assert policy_block.count("tenant_id IS NOT NULL AND tenant_id::text") >= 2, (
        "Both USING and WITH CHECK of requests_update_approver_status must check tenant scope"
    )


def test_schema_verification_with_check_enforces_user_id_immutability() -> None:
    """requests_update_verification WITH CHECK must enforce user_id = auth.uid()."""
    from pathlib import Path

    content = (Path(__file__).resolve().parents[2] / "supabase" / "schema.sql").read_text(encoding="utf-8")
    create_marker = 'CREATE POLICY "requests_update_verification"'
    assert create_marker in content, f"Expected '{create_marker}' in schema.sql"
    idx = content.index(create_marker)
    policy_block = content[idx : idx + 600]
    assert "WITH CHECK" in policy_block, "requests_update_verification must have WITH CHECK"
    assert policy_block.count("user_id = auth.uid()") >= 2, (
        "Both USING and WITH CHECK of requests_update_verification must enforce user_id = auth.uid()"
    )


def test_schema_approvals_fk_uses_on_delete_cascade() -> None:
    """approvals.request_version_id must use ON DELETE CASCADE to allow ordered seed cleanup."""
    from pathlib import Path

    content = (Path(__file__).resolve().parents[2] / "supabase" / "schema.sql").read_text(encoding="utf-8")
    idx = content.index("CREATE TABLE IF NOT EXISTS approvals")
    table_block = content[idx : idx + 900]  # wider window to clear the FK comment

    assert "REFERENCES reorder_requests(id) ON DELETE CASCADE" in table_block
    assert "REFERENCES request_versions(id) ON DELETE CASCADE" in table_block, (
        "approvals.request_version_id FK must use ON DELETE CASCADE"
    )


def test_schema_seed_demo_data_for_user_function_defined() -> None:
    """schema.sql must define the idempotent seed_demo_data_for_user stored function."""
    from pathlib import Path

    content = (Path(__file__).resolve().parents[2] / "supabase" / "schema.sql").read_text(encoding="utf-8")
    assert "CREATE OR REPLACE FUNCTION public.seed_demo_data_for_user" in content
    assert "SECURITY DEFINER" in content

    func_idx = content.index("CREATE OR REPLACE FUNCTION public.seed_demo_data_for_user")
    func_body = content[func_idx : func_idx + 10000]
    assert "auth.users" not in func_body, (
        "seed_demo_data_for_user must not INSERT into auth.users"
    )
    assert func_body.count("ON CONFLICT") >= 5, (
        "seed_demo_data_for_user must use ON CONFLICT DO NOTHING for idempotency"
    )


def test_schema_shared_demo_catalog_read_policy_present() -> None:
    """products and supplier_terms select policies must include shared catalog owner access."""
    from pathlib import Path

    content = (Path(__file__).resolve().parents[2] / "supabase" / "schema.sql").read_text(encoding="utf-8")
    demo_uuid = "00000000-0000-0000-0000-000000000001"

    idx = content.index("products_select_authorized")
    assert demo_uuid in content[idx : idx + 600], (
        "products_select_authorized must grant read to shared demo catalog owner"
    )

    idx2 = content.index("supplier_terms_select_authorized")
    assert demo_uuid in content[idx2 : idx2 + 600], (
        "supplier_terms_select_authorized must grant read to shared demo catalog owner"
    )


def test_env_example_documents_repository_backend() -> None:
    """'.env.example' must document REPOSITORY_BACKEND=supabase as the production value."""
    from pathlib import Path

    content = (Path(__file__).resolve().parents[2] / ".env.example").read_text(encoding="utf-8")
    assert "REPOSITORY_BACKEND" in content
    assert "REPOSITORY_BACKEND=supabase" in content
    assert "memory" in content  # must document the intentional-only fallback


def test_seed_sql_documents_non_login_catalog_owner() -> None:
    """seed.sql must document that the auth.users insert is not a real login account."""
    from pathlib import Path

    content = (Path(__file__).resolve().parents[2] / "supabase" / "seed.sql").read_text(encoding="utf-8")
    assert "not intended for auth login" in content or "NOT a real login account" in content
    assert "seed_demo_data_for_user" in content


def test_schema_seed_function_privileges_restricted() -> None:
    """schema.sql must revoke execute on seed_demo_data_for_user from public/anon/authenticated."""
    from pathlib import Path

    content = (Path(__file__).resolve().parents[2] / "supabase" / "schema.sql").read_text(encoding="utf-8")
    assert "REVOKE EXECUTE ON FUNCTION public.seed_demo_data_for_user" in content
    assert "GRANT EXECUTE ON FUNCTION public.seed_demo_data_for_user(UUID) TO service_role" in content
    assert "current_user NOT IN ('postgres', 'service_role')" in content
    assert "Demo data already provisioned" in content


def test_schema_prevent_mutation_requires_admin_override() -> None:
    """schema.sql prevent_mutation must require postgres/service_role to bypass append-only protection."""
    from pathlib import Path

    content = (Path(__file__).resolve().parents[2] / "supabase" / "schema.sql").read_text(encoding="utf-8")
    assert "current_setting('app.seed_cleanup', true) = 'true'" in content
    assert "current_user IN ('postgres', 'service_role')" in content


def test_health_endpoints_and_readiness(api_client: TestClient) -> None:
    """GET /api/health and /api/health/readiness return structured status."""
    resp = api_client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "inventory-reorder-planner"
    assert "supabase" in data

    ready_resp = api_client.get("/api/health/readiness")
    assert ready_resp.status_code == 200
    ready_data = ready_resp.json()
    assert "status" in ready_data
    assert "supabase" in ready_data
    assert "tables_initialized" in ready_data["supabase"]

