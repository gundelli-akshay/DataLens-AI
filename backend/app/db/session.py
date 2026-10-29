"""
db/session.py - SQLAlchemy engine and session factory for DataLens AI.

Engine creation is LAZY (deferred until first use via _get_engine()) so that:
  - A Supabase / Supavisor blip at container startup never causes an
    import-time exception that kills Uvicorn before FastAPI even boots.
  - The lifespan retry logic in main.py gets a chance to run.

Public API
----------
engine        : SQLAlchemy Engine  (lazy proxy — safe to import at module level)
SessionLocal  : callable that returns a new DB session (also lazy)
Base          : declarative base for all ORM models
get_db()      : FastAPI dependency that yields a DB session
"""

import logging
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session

from app.core.config import settings

logger = logging.getLogger("datalens.db.session")

Base = declarative_base()


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def normalize_database_url(url: str | None) -> str:
    """
    Normalise and validate DATABASE_URL for SQLAlchemy compatibility.

    Accepts:
      postgresql://...  (already correct)
      postgres://...    (old Heroku-style; rewritten to postgresql://)

    Rejects empty, None, sqlite://, or any other scheme.
    """
    if not url or not url.strip():
        raise ValueError(
            "DATABASE_URL must be explicitly configured with a PostgreSQL "
            "connection string (postgresql://...)."
        )
    clean = url.strip()
    if clean.lower().startswith("sqlite"):
        raise ValueError(
            "SQLite is not supported. DATABASE_URL must be a PostgreSQL "
            "connection string (postgresql://...)."
        )
    if clean.startswith("postgres://"):
        return "postgresql://" + clean[len("postgres://"):]
    if not clean.startswith("postgresql://"):
        raise ValueError(
            f"Unsupported database scheme in DATABASE_URL: '{clean}'. "
            "Only PostgreSQL is supported."
        )
    return clean


def check_db_dialect(url: str) -> None:
    """Raise if url is not a PostgreSQL connection string."""
    clean = (url or "").strip().lower()
    if not clean or clean.startswith("sqlite") or not clean.startswith(
        ("postgresql://", "postgres://")
    ):
        raise RuntimeError(
            "DATABASE_URL must be configured with a PostgreSQL connection "
            "string (postgresql://...). SQLite is not supported."
        )


# kept for backward-compat with any callers that import it
def check_production_db_dialect(url: str, is_production: bool = True) -> None:
    check_db_dialect(url)


def _engine_kwargs() -> dict:
    """
    SQLAlchemy engine keyword arguments tuned for Supabase Supavisor
    (transaction-mode pooler) running on Render free tier.
    """
    return {
        "pool_pre_ping": True,       # discard stale / banned connections silently
        "pool_recycle": 280,         # just under Supavisor's 300-s idle timeout
        "pool_size": 3,              # conservative for 512 MB Render free tier
        "max_overflow": 5,           # allow short burst beyond pool_size
        "pool_timeout": 30,          # give up waiting for a pool slot after 30 s
        "connect_args": {
            "connect_timeout": 10,   # TCP connect timeout — fail fast
        },
    }


# ---------------------------------------------------------------------------
# Lazy engine — built once on first call, NEVER at import time
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _get_engine():
    """
    Build and cache the SQLAlchemy engine.

    Deferred so an import of session.py never triggers a live DB connection,
    meaning a Supabase pooler blip on startup cannot crash the container
    before FastAPI and the lifespan retry logic have a chance to run.
    """
    db_url = normalize_database_url(settings.database_url)
    check_db_dialect(db_url)
    # Log only the host part to avoid leaking credentials
    safe_url = db_url.split("@")[-1] if "@" in db_url else db_url
    logger.info("Creating SQLAlchemy engine → %s", safe_url)
    return create_engine(db_url, **_engine_kwargs())


# ---------------------------------------------------------------------------
# Lazy proxy objects — safe to import at module level
# ---------------------------------------------------------------------------

class _LazyEngine:
    """
    Thin proxy that forwards every attribute access / call to the real
    SQLAlchemy Engine, constructing it on the first access.

    This lets ``from app.db.session import engine`` work at import time
    without triggering a DB connection.
    """
    def __getattr__(self, name: str):
        return getattr(_get_engine(), name)

    def connect(self, *args, **kwargs):
        return _get_engine().connect(*args, **kwargs)

    def begin(self, *args, **kwargs):
        return _get_engine().begin(*args, **kwargs)

    def dispose(self, *args, **kwargs):
        return _get_engine().dispose(*args, **kwargs)


class _LazySessionLocal:
    """
    Callable proxy for sessionmaker.  Calling it returns a real Session
    bound to the lazy engine.  The factory is built on first call.
    """
    @lru_cache(maxsize=1)
    def _factory(self):
        return sessionmaker(autocommit=False, autoflush=False, bind=_get_engine())

    def __call__(self) -> Session:
        return self._factory()()


# Public singletons — import these everywhere
engine = _LazyEngine()
SessionLocal = _LazySessionLocal()


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

def get_db():
    """Yield a SQLAlchemy session; always close it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
