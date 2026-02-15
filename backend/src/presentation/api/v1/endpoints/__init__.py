"""
API V1 Endpoints Package
Exports routers used by main app
"""
# Only import modules that main.py actually uses
from .auth import router as auth_router
from .preferences_clean import router as preferences_router
from .jobs_clean import router as jobs_router

__all__ = [
    "auth_router",
    "preferences_router",
    "jobs_router"
]
