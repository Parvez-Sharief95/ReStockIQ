"""Router stub — health check."""
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "inventory-reorder-planner"}
