"""
Shared pytest fixtures — Phase 8.
Provides deterministic test data matching TC1–TC4 synthetic scenarios,
plus FastAPI TestClient fixture for integration testing.
"""
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi.testclient import TestClient
import pytest

from backend.app.main import app
from backend.app.services.backend_store import get_backend_store


@pytest.fixture
def sample_product_id() -> str:
    return "10000000-0000-0000-0000-000000000001"


@pytest.fixture
def sample_supplier_terms_id() -> str:
    return "20000000-0000-0000-0000-000000000001"


@pytest.fixture
def sample_evidence_id() -> str:
    return "50000000-0000-0000-0000-000000000001"


@pytest.fixture
def base_product() -> dict[str, Any]:
    return {
        "id": "10000000-0000-0000-0000-000000000001",
        "sku": "SKU-001",
        "name": "Widget Alpha",
        "unit": "each",
        "currency": "USD",
        "current_stock": Decimal("20"),
        "safety_stock_target": None,  # Will test defaulting to 0
    }


@pytest.fixture
def base_supplier_terms() -> dict[str, Any]:
    return {
        "id": "20000000-0000-0000-0000-000000000001",
        "product_id": "10000000-0000-0000-0000-000000000001",
        "supplier_name": "Acme Supplies",
        "lead_time_days": 14,
        "pack_size": 1,
        "unit_price": Decimal("10.00"),
        "currency": "USD",
        "moq": None,
        "price_updated_at": datetime.now(timezone.utc),
    }


@pytest.fixture
def base_sales_history() -> dict[str, Any]:
    return {
        "total_units_sold": Decimal("120"),
        "days_in_period": 30,  # 120 / 30 = 4.0 units/day
    }


@pytest.fixture
def api_client() -> TestClient:
    """FastAPI TestClient with fresh store state."""
    store = get_backend_store()
    store.reset()
    client = TestClient(app)
    return client
