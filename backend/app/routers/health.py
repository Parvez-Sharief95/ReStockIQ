"""health.py — Health and Readiness Check Endpoints."""
from __future__ import annotations

import logging
from typing import Any
from fastapi import APIRouter

try:
    from backend.app.config import settings
except ImportError:
    from app.config import settings

logger = logging.getLogger("inventory_reorder_planner.health")
router = APIRouter()


def inspect_supabase_status() -> dict[str, Any]:
    """Inspect Supabase connectivity and schema readiness safely without exposing credentials."""
    if not settings.supabase_url:
        return {
            "configured": False,
            "connected": False,
            "tables_initialized": False,
            "message": "SUPABASE_URL is not configured.",
        }

    key = settings.supabase_secret_key or settings.supabase_publishable_key
    if not key:
        return {
            "configured": False,
            "connected": False,
            "tables_initialized": False,
            "message": "Neither SUPABASE_SECRET_KEY nor SUPABASE_PUBLISHABLE_KEY is configured.",
        }

    try:
        from supabase import create_client
        client = create_client(settings.supabase_url, key)
        # Attempt to query products table
        client.from_("products").select("id").limit(1).execute()
        return {
            "configured": True,
            "connected": True,
            "tables_initialized": True,
            "message": "Connected to Supabase project and public tables are verified.",
        }
    except Exception as e:
        err_msg = str(e)
        if "PGRST205" in err_msg or "Could not find the table" in err_msg:
            return {
                "configured": True,
                "connected": True,
                "tables_initialized": False,
                "message": "Connected to Supabase project successfully, but database schema is not yet initialized. Please execute supabase/schema.sql in the Supabase SQL Editor.",
            }
        logger.warning("Supabase connection check error: %s", err_msg)
        return {
            "configured": True,
            "connected": False,
            "tables_initialized": False,
            "message": f"Connection check failed: {err_msg[:200]}",
        }


@router.get("/health", summary="Basic API health check")
async def health() -> dict[str, Any]:
    """Returns basic service health. Compatible with automated health pingers."""
    is_configured = bool(settings.supabase_url and (settings.supabase_secret_key or settings.supabase_publishable_key))
    return {
        "status": "ok",
        "service": "inventory-reorder-planner",
        "app_env": settings.app_env,
        "repository_backend": settings.repository_backend,
        "supabase": {
            "configured": is_configured,
        },
    }


@router.get("/health/readiness", summary="Comprehensive backend & Supabase readiness check")
async def readiness() -> dict[str, Any]:
    """Performs real connectivity verification against Supabase and returns structured status."""
    supa_status = inspect_supabase_status()
    is_persistent = settings.repository_backend.lower() in ("supabase", "auto") and settings.app_env.lower() == "production"
    
    # Ready if memory mode or (supabase mode AND tables are verified)
    if settings.repository_backend.lower() == "supabase":
        is_ready = supa_status["connected"] and supa_status["tables_initialized"]
    else:
        is_ready = True

    return {
        "status": "ready" if is_ready else "degraded",
        "service": "inventory-reorder-planner",
        "repository_backend": settings.repository_backend,
        "app_env": settings.app_env,
        "supabase": supa_status,
    }
