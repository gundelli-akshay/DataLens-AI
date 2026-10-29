"""
main.py - DataLens AI FastAPI application entry point.

Startup philosophy
------------------
Uvicorn MUST answer Render health-check probes within a few seconds of
booting.  We therefore do NOT block startup on a live DB connection.

  1. A background asyncio task (_db_init_loop) retries DB init every
     RETRY_INTERVAL_S seconds until it succeeds.
  2. lifespan yields immediately so Uvicorn starts serving right away.
  3. /health always returns HTTP 200; the JSON body carries the DB status.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import health, upload, analyze, insights, documents, auth
from app.core.config import settings, DEFAULT_DEV_JWT_SECRET
from app.db.session import Base, get_engine
from app.db import models  # noqa: F401  -- registers ORM models with Base

logger = logging.getLogger("datalens.main")

_db_ready: bool = False
_db_error: str = ""
RETRY_INTERVAL_S: int = 15


# ---------------------------------------------------------------------------
# DB init helpers
# ---------------------------------------------------------------------------

def _run_init_db(engine) -> None:
    """Create tables + lightweight schema migrations. Runs in a thread."""
    from sqlalchemy import inspect, text

    Base.metadata.create_all(bind=engine)

    with engine.connect() as conn:
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        for table, column in [
            ("documents", "user_id"),
            ("chat_messages", "user_id"),
            ("documents", "ai_insights"),
        ]:
            if table in tables:
                existing = [c["name"] for c in inspector.get_columns(table)]
                if column not in existing:
                    dtype = "TEXT" if column == "ai_insights" else "INTEGER"
                    conn.execute(
                        text(f"ALTER TABLE {table} ADD COLUMN {column} {dtype};")
                    )
                    conn.commit()
                    logger.info("Migration: added column %s.%s", table, column)


async def _db_init_loop() -> None:
    """
    Background coroutine: attempts DB init, retries on failure.
    Sets global _db_ready/error. Never raises -- errors are only logged.
    """
    global _db_ready, _db_error
    attempt = 0
    while True:
        attempt += 1
        try:
            engine = get_engine()
            # Run blocking DB call in a thread; event loop stays free.
            await asyncio.to_thread(_run_init_db, engine)
            _db_ready = True
            _db_error = ""
            logger.info("Database initialised (attempt %d).", attempt)
            return  # success -- stop retrying
        except Exception as exc:
            _db_error = str(exc)
            logger.error(
                "DB init attempt %d failed: %s -- retry in %ds",
                attempt,
                exc,
                RETRY_INTERVAL_S,
            )
            await asyncio.sleep(RETRY_INTERVAL_S)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Start DB-init background task, then yield immediately so Uvicorn can
    accept connections (including Render health-check probes) right away.
    """
    for msg in settings.validate_production_settings():
        logger.warning("PRODUCTION CONFIG WARNING: %s", msg)
    if settings.is_production and settings.jwt_secret_key == DEFAULT_DEV_JWT_SECRET:
        logger.critical(
            "SECURITY ALERT: Running in production with default JWT secret key! "
            "Set a secure JWT_SECRET_KEY environment variable."
        )

    task = asyncio.create_task(_db_init_loop())
    yield  # server is live here immediately
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AI-Powered Data and Document Analysis API",
    lifespan=lifespan,
)

app.state.db_ready = lambda: _db_ready
app.state.db_error = lambda: _db_error

configured_origins = (
    [o for o in settings.cors_origins if o != "*"]
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

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(upload.router)
app.include_router(analyze.router)
app.include_router(insights.router)
app.include_router(documents.router)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(
        "Unhandled exception %s %s: %s",
        request.method,
        request.url,
        exc,
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected internal server error occurred."},
    )


@app.get("/", tags=["Root"])
def read_root():
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "status": "running",
        "environment": settings.app_env,
        "docs": "/docs",
    }
