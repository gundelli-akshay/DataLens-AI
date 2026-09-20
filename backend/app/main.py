"""
main.py - DataLens AI FastAPI application entry point.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health, upload, analyze, insights, documents
from app.core.config import settings

# --- App instance ---
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AI-Powered Data & Document Analysis API",
)

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Routers ---
app.include_router(health.router)
app.include_router(upload.router)
app.include_router(analyze.router)
app.include_router(insights.router)
app.include_router(documents.router)


# --- Root endpoint ---
@app.get("/", tags=["Root"])
def read_root():
    return {
        "app":         settings.app_name,
        "version":     settings.app_version,
        "status":      "running",
        "environment": settings.app_env,
        "docs":        "/docs",
    }
