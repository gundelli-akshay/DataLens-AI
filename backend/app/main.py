"""
main.py - DataLens AI FastAPI application entry point.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health, upload, analyze, insights, documents, auth
from app.core.config import settings

from app.db.session import engine, Base
from app.db import models

# Create database tables
Base.metadata.create_all(bind=engine)

# Backward-compatibility column migration for existing tables
try:
    from sqlalchemy import inspect, text
    with engine.connect() as conn:
        inspector = inspect(engine)
        if "documents" in inspector.get_table_names():
            cols = [c["name"] for c in inspector.get_columns("documents")]
            if "user_id" not in cols:
                conn.execute(text("ALTER TABLE documents ADD COLUMN user_id INTEGER;"))
                conn.commit()
        if "chat_messages" in inspector.get_table_names():
            cols = [c["name"] for c in inspector.get_columns("chat_messages")]
            if "user_id" not in cols:
                conn.execute(text("ALTER TABLE chat_messages ADD COLUMN user_id INTEGER;"))
                conn.commit()
except Exception:
    pass


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
app.include_router(auth.router)
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
