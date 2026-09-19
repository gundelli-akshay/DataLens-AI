"""
main.py — DataLens AI FastAPI application entry point.

This file:
  - Creates the FastAPI app instance
  - Registers all routers
  - Defines the root GET / endpoint

To run:
    uvicorn app.main:app --reload
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health
from app.core.config import settings

# ─── App instance ─────────────────────────────────────────────
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AI-Powered Data & Document Analysis API",
)

# ─── CORS ─────────────────────────────────────────────────────
# Allows the React frontend (running on a different port) to call this API.
# In production, replace "*" with your actual frontend domain.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # tighten this in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Routers ──────────────────────────────────────────────────
app.include_router(health.router)


# ─── Root endpoint ────────────────────────────────────────────
@app.get("/", tags=["Root"])
def read_root():
    """
    Root endpoint — confirms the API is running.
    """
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "status": "running",
        "environment": settings.app_env,
        "docs": "/docs",
    }
