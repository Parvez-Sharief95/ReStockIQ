"""auth.py — Authentication & Role-Based Authorization Dependencies.
Phase 8 Security Hardening.

Provides:
- AuthenticatedUser Pydantic model with UUID identity, email, and role.
- Supabase Auth JWT token extraction & verification.
- Deterministic test/demo token support for offline verification without network calls.
- Role-based authorization dependencies (e.g. require_approver).
- Rejection of caller-supplied approver identities (approver_id derived strictly from authenticated token).
"""
from datetime import datetime, timezone
import logging
from typing import Any
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

try:
    from backend.app.config import settings
except ImportError:
    from app.config import settings

logger = logging.getLogger("inventory_reorder_planner.auth")

security_bearer = HTTPBearer(auto_error=False)


class AuthenticatedUser(BaseModel):
    """Domain model for verified authenticated user."""

    id: UUID = Field(..., description="Unique user UUID matching auth.uid()")
    email: str = Field(..., description="Authenticated user email")
    role: str = Field(..., description="Access control role: 'approver' | 'planner' | 'auditor' | 'admin'")
    token: str | None = Field(None, description="Raw Bearer JWT token forwarded for RLS execution")


# Deterministic demo and testing identities matching DECISIONS.md & frontend DEMO_USERS
DEMO_IDENTITIES: dict[str, dict[str, Any]] = {
    "demo-approver-token": {
        "id": UUID("00000000-0000-0000-0000-000000000002"),
        "email": "demo-approver@inventory.local",
        "role": "approver",
    },
    "demo-planner-token": {
        "id": UUID("00000000-0000-0000-0000-000000000001"),
        "email": "demo-planner@inventory.local",
        "role": "planner",
    },
    "demo-auditor-token": {
        "id": UUID("00000000-0000-0000-0000-000000000003"),
        "email": "demo-auditor@inventory.local",
        "role": "auditor",
    },
}


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Security(security_bearer),
) -> AuthenticatedUser:
    """Validate Bearer token from Authorization header and return verified AuthenticatedUser.

    Rejection behavior:
    - Missing token -> HTTP 401 Unauthorized
    - Malformed / unrecognized token -> HTTP 401 Unauthorized
    """
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Missing Bearer token in Authorization header.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    raw_token = credentials.credentials.strip()
    is_production = settings.app_env.lower() == "production"

    # 1. In production, demo and test tokens are STRICTLY DISABLED
    if is_production and (raw_token in DEMO_IDENTITIES or raw_token.startswith("test-user:")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Demo authentication tokens are strictly disabled in production mode. A verified Supabase Auth session token is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 2. In non-production (development / test), allow deterministic demo identities
    if not is_production:
        if raw_token in DEMO_IDENTITIES:
            data = DEMO_IDENTITIES[raw_token]
            return AuthenticatedUser(id=data["id"], email=data["email"], role=data["role"], token=raw_token)

        if raw_token.startswith("test-user:"):
            parts = raw_token.split(":")
            if len(parts) == 3:
                try:
                    u_id = UUID(parts[1])
                    role = parts[2]
                    return AuthenticatedUser(
                        id=u_id,
                        email=f"{role}-{str(u_id)[:8]}@test.local",
                        role=role,
                        token=raw_token,
                    )
                except ValueError:
                    pass

    # 3. Verify Supabase live JWT if token appears to be a JWT
    if raw_token.count(".") == 2:
        # Pre-check claims (expiry, audience, issuer) using PyJWT decode
        try:
            unverified_claims = jwt.decode(raw_token, options={"verify_signature": False})
        except Exception:
            unverified_claims = None

        if unverified_claims:
            # Validate expiration
            exp = unverified_claims.get("exp")
            if exp is not None:
                exp_dt = datetime.fromtimestamp(exp, timezone.utc)
                if exp_dt < datetime.now(timezone.utc):
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Authentication token has expired.",
                        headers={"WWW-Authenticate": "Bearer"},
                    )

            # Validate audience
            aud = unverified_claims.get("aud")
            if aud is not None and aud != "authenticated":
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token audience claim.",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            # Validate issuer if Supabase URL configured
            iss = unverified_claims.get("iss")
            if iss and settings.supabase_url:
                expected_prefix = settings.supabase_url.rstrip("/")
                if not iss.startswith(expected_prefix):
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Invalid token issuer claim.",
                        headers={"WWW-Authenticate": "Bearer"},
                    )

        # Cryptographic Verification Option A: Local JWT Secret (HS256)
        if settings.supabase_jwt_secret:
            try:
                verified_payload = jwt.decode(
                    raw_token,
                    key=settings.supabase_jwt_secret,
                    algorithms=["HS256"],
                    audience="authenticated",
                )
                sub = verified_payload.get("sub")
                if not sub:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Missing subject claim in token.",
                        headers={"WWW-Authenticate": "Bearer"},
                    )
                user_id = UUID(sub)
                email = verified_payload.get("email") or "user@supabase.local"
                app_meta = verified_payload.get("app_metadata", {})
                user_meta = verified_payload.get("user_metadata", {})

                # Safe Role Governance: Privileged roles MUST come from app_metadata
                app_role = app_meta.get("role")
                if app_role in ("approver", "admin", "planner", "auditor"):
                    role = app_role
                else:
                    user_meta_role = user_meta.get("role")
                    role = user_meta_role if user_meta_role in ("planner", "auditor") else "planner"

                return AuthenticatedUser(id=user_id, email=email, role=role, token=raw_token)
            except jwt.ExpiredSignatureError:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication token has expired.",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            except jwt.InvalidTokenError as e:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=f"Cryptographic token verification failed: {str(e)}",
                    headers={"WWW-Authenticate": "Bearer"},
                )

        # Cryptographic Verification Option B: Official Supabase Auth Service API
        if not settings.supabase_url or not settings.supabase_secret_key:
            if is_production:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Production authentication is unavailable: Supabase credentials are not configured.",
                )
        else:
            try:
                from supabase import create_client

                supabase = create_client(settings.supabase_url, settings.supabase_secret_key)
                user_resp = supabase.auth.get_user(raw_token)
                if user_resp and user_resp.user:
                    u = user_resp.user
                    user_id = UUID(u.id)
                    email = u.email or "user@supabase.local"

                    # Safe Role Governance:
                    # Privileged roles ('approver', 'admin') MUST originate from app_metadata (service_role managed).
                    # Any self-assigned 'approver' or 'admin' claim in user_metadata is safely downgraded to 'planner'.
                    app_role = (u.app_metadata or {}).get("role")
                    if app_role in ("approver", "admin", "planner", "auditor"):
                        role = app_role
                    else:
                        user_meta_role = (u.user_metadata or {}).get("role")
                        if user_meta_role in ("planner", "auditor"):
                            role = user_meta_role
                        else:
                            role = "planner"

                    return AuthenticatedUser(id=user_id, email=email, role=role, token=raw_token)
            except Exception as e:
                logger.warning("Supabase auth verification failed: %s", e)
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired authentication token.",
                    headers={"WWW-Authenticate": "Bearer"},
                )

    # If neither valid demo token (dev only) nor verified Supabase token matches:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication token.",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Security(security_bearer),
) -> AuthenticatedUser | None:
    """Return AuthenticatedUser if valid token is provided, or None if omitted."""
    if credentials is None or not credentials.credentials:
        return None
    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None


def require_role(allowed_roles: list[str] | str):
    """Authorization dependency factory enforcing required role(s)."""
    roles = [allowed_roles] if isinstance(allowed_roles, str) else allowed_roles

    async def role_checker(
        current_user: AuthenticatedUser = Depends(get_current_user),
    ) -> AuthenticatedUser:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access forbidden: Operation requires one of roles {roles}. Current authenticated user role is '{current_user.role}'.",
            )
        return current_user

    return role_checker


# Specialized dependencies
require_approver = require_role(["approver", "admin"])
require_planner = require_role(["planner", "approver", "admin"])
