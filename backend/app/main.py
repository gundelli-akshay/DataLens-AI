"""
main.py - DataLens AI FastAPI application entry point.
"""

from contextlib import asynccontextmanager
import logging
import time
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import health, upload, analyze, insights, documents, auth
from app.core.config import settings, DEFAULT_DEV_JWT_SECRET
from app.db.session import engine, Base
from app.db import models

logger = logging.getLogger("datalens.main")

# Startup DB status tracked here so /health can surface it without crashing
_db_ready: bool = False
_db_error: str = ""


def init_db(target_engine=None):
    """Create database tables and run backward-compatibility column migrations."""
    db_engine = target_engine or engine
    Base.metadata.create_all(bind=db_engine)
    try:
        from sqlalchemy import inspect, text
        with db_engine.connect() as conn:
            inspector = inspect(db_engine)
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
            if "documents" in inspector.get_table_names():
                cols = [c["name"] for c in inspector.get_columns("documents")]
                if "ai_insights" not in cols:
                    conn.execute(text("ALTER TABLE documents ADD COLUMN ai_insights TEXT;"))
                    conn.commit()
    except Exception as exc:
        logger.warning("Database schema migration check warning: %s", exc)


def _try_init_db_with_retries(target_engine=None, retries: int = 5, delay: float = 5.0) -> bool:
    """
    Attempt init_db() up to etries times with delay seconds between attempts.
    Returns True on success, False on exhausted retries.
    Logs all failures but never raises so the process stays alive.
    """
    global _db_ready, _db_error
    for attempt in range(1, retries + 1):
        try:
            init_db(target_engine=target_engine)
            _db_ready = True
            _db_error = ""
            logger.info("Database initialised successfully (attempt %d/%d).", attempt, retries)
            return True
        except Exception as exc:
            _db_error = str(exc)
            logger.error(
                "Database init attempt %d/%d failed: %s",
                attempt, retries, exc,
                exc_info=(attempt == retries),
            )
            if attempt < retries:
                logger.info("Retrying database init in %.0f seconds ...", delay)
                time.sleep(delay)
    logger.critical(
        "All %d database init attempts failed. "
        "The API will start without database access. "
        "Authenticated endpoints will return 503 until the DB is reachable.",
        retries,
    )
    return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI application lifespan management for startup and shutdown events."""
    # Production safety validation
    for warning_msg in settings.validate_production_settings():
        logger.warning("PRODUCTION CONFIG WARNING: %s", warning_msg)
    if settings.is_production and settings.jwt_secret_key == DEFAULT_DEV_JWT_SECRET:
        logger.critical(
            "SECURITY ALERT: Running in production with default JWT secret key! "
            "Set a secure JWT_SECRET_KEY."
        )

    # Initialize database on startup — wrapped in retry+catch so a transient
    # Supabase pooler error never crashes Uvicorn (which would produce Exit status 3).
    import app.db.session as session_module
    _try_init_db_with_retries(target_engine=session_module.engine)

    yield


# --- App instance ---
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AI-Powered Data & Document Analysis API",
    lifespan=lifespan,
)

# expose DB status to health endpoint
app.state.db_ready = lambda: _db_ready
app.state.db_error = lambda: _db_error

# --- CORS ---
# In production, strictly disallow wildcard '*' origins
configured_origins = (
    [origin for origin in settings.cors_origins if origin != "*"]
    if settings.is_production
    else settings.cors_origins
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=configured_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=86400,
)

# --- Routers ---
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(upload.router)
app.include_router(analyze.router)
app.include_router(insights.router)
app.include_router(documents.router)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(
        "Unhandled exception processing %s %s: %s",
        request.method, request.url, exc,
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected internal server error occurred."},
    )

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
