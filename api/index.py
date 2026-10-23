"""Vercel Serverless Function entry point for FastAPI backend."""
from __future__ import annotations

import sys
from pathlib import Path

# Add project root and backend directory to sys.path so backend imports work seamlessly
ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    from backend.app.main import app
except ImportError:
    from app.main import app  # type: ignore[no-redef]
