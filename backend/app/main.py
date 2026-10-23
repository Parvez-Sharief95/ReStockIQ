"""FastAPI application entry point — Phase 8 Integration."""
from __future__ import annotations

import logging
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

try:
    from app.config import settings
    from app.routers import (
        analyses,
        approvals,
        dashboard,
        health,
        inventory,
        requests,
        test_runs,
    )
except ImportError:
    from backend.app.config import settings
    from backend.app.routers import (
        analyses,
        approvals,
        dashboard,
        health,
        inventory,
        requests,
        test_runs,
    )

logger = logging.getLogger("inventory_reorder_planner")

app = FastAPI(
    title="ReStockIQ API",
    description="Backend for ReStockIQ — Autonomous Reorder Intelligence.",
    version="0.1.0",
    docs_url="/docs" if settings.app_env == "development" else None,
    redoc_url="/redoc" if settings.app_env == "development" else None,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=r"^https://.*\.vercel\.app$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Global Structured Error Handlers ──────────────────────────────────────────

@app.exception_handler(PermissionError)
async def permission_error_handler(request: Request, exc: PermissionError) -> JSONResponse:
    """Handle approval gating and unauthorized consequential actions."""
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={
            "code": "CONSEQUENTIAL_ACTION_BLOCKED",
            "message": str(exc),
            "details": None,
        },
    )


@app.exception_handler(KeyError)
async def key_error_handler(request: Request, exc: KeyError) -> JSONResponse:
    """Handle missing entity lookups."""
    # Strip quotes from exception string representation
    clean_msg = str(exc).strip("'\"")
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={
            "code": "ENTITY_NOT_FOUND",
            "message": clean_msg,
            "details": None,
        },
    )


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    """Handle business rule / validation failures."""
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "code": "INVALID_INPUT",
            "message": str(exc),
            "details": None,
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle Pydantic request schema validation errors."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "code": "VALIDATION_ERROR",
            "message": "Request payload failed schema validation.",
            "details": {"errors": exc.errors()},
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Normalize HTTPException to standard APIError structure."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": f"HTTP_{exc.status_code}",
            "message": exc.detail if isinstance(exc.detail, str) else "HTTP error",
            "details": exc.detail if not isinstance(exc.detail, str) else None,
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Prevent secrets or internal trace leakage in 500 responses."""
    logger.error("Unhandled server exception: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "code": "INTERNAL_SERVER_ERROR",
            "message": "An internal server error occurred. Please contact system administrator.",
            "details": None,
        },
    )


# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])
app.include_router(inventory.router, prefix="/api/inventory", tags=["inventory"])
app.include_router(analyses.router, prefix="/api/analyses", tags=["analyses"])
app.include_router(requests.router, prefix="/api/requests", tags=["requests"])
app.include_router(approvals.router, prefix="/api/approvals", tags=["approvals"])
app.include_router(test_runs.router, prefix="/api/test-runs", tags=["test-runs"])
