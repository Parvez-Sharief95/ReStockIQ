"""FastAPI application entry point."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import health, inventory, analyses, requests, approvals, test_runs

app = FastAPI(
    title="Inventory Reorder Planner API",
    description="Backend for the Inventory Reorder Planner hackathon project.",
    version="0.1.0",
    docs_url="/docs" if settings.app_env == "development" else None,
    redoc_url="/redoc" if settings.app_env == "development" else None,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(inventory.router, prefix="/api/inventory", tags=["inventory"])
app.include_router(analyses.router, prefix="/api/analyses", tags=["analyses"])
app.include_router(requests.router, prefix="/api/requests", tags=["requests"])
app.include_router(approvals.router, prefix="/api/approvals", tags=["approvals"])
app.include_router(test_runs.router, prefix="/api/test-runs", tags=["test-runs"])
