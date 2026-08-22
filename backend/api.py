"""
FinSight RegTech API Root Alias
Re-exports FastAPI application instance from src.api.main
"""
from src.api.main import app

__all__ = ["app"]
