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


def test_config_allows_vite_frontend_vars_and_forbids_misspelled_backend_vars() -> None:
    """Settings should filter out VITE_* variables from shared .env while rejecting misspelled backend keys."""
    from pydantic import ValidationError
    import backend.app.config as config_module

    # Legitimate frontend variables should be tolerated
    s = config_module.Settings(VITE_CUSTOM_KEY="http://localhost:5173", VITE_ANON_TOKEN="anon")
    assert s.app_env in ("development", "test", "production")

    # Misspelled backend variables MUST be rejected
    try:
        config_module.Settings(SUPABSE_URL_MISSPELLED="https://foo.supabase.co")
        assert False, "Should have raised ValidationError for misspelled setting"
    except ValidationError as e:
        assert any(err["type"] == "extra_forbidden" for err in e.errors())

