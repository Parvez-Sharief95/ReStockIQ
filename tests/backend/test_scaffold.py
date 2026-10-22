"""
Smoke test — verifies the scaffold imports cleanly.
No external services or LLM calls are made.
"""
import sys
import os

# Allow imports from backend/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


def test_schemas_import() -> None:
    """Pydantic schema models should import without errors."""
    from backend.app.schemas.models import (  # noqa: F401
        Product,
        SupplierTerms,
        SalesHistory,
        OpenPurchaseOrder,
        SourceEvidence,
        ReorderAnalysis,
        ReorderRequest,
        RequestStatus,
        TestCaseId,
    )


def test_config_import() -> None:
    """Config module should load with empty env vars (development mode)."""
    import importlib
    import backend.app.config as config_module
    importlib.reload(config_module)
    settings = config_module.Settings()
    assert settings.app_env == "development"
