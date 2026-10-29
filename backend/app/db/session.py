"""
db/session.py - SQLAlchemy engine and session factory for DataLens AI.

Engine creation is LAZY (via get_engine()) so importing this module never
opens a database connection.  A Supabase/Supavisor blip at startup therefore
cannot crash Uvicorn before FastAPI has a chance to boot and serve the
Render health-check probe.

Public API
----------
get_engine()   : returns the singleton SQLAlchemy Engine (lazy, cached)
engine         : lazy proxy -- safe to import at module level
SessionLocal   : callable proxy -- returns a new Session on each call
Base           : declarative base for all ORM models
get_db()       : FastAPI dependency that yields a DB session
"""

import logging
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import settings

logger = logging.getLogger("datalens.db.session")

Base = declarative_base()


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def normalize_database_url(url) -> str:
    """
    Normalise and validate DATABASE_URL.

    Accepts postgresql:// or postgres:// (rewritten to postgresql://).
    Rejects empty, None, sqlite://, and any other scheme.
    """
    if not url or not str(url).strip():
        raise ValueError(
            "DATABASE_URL must be explicitly configured with a PostgreSQL "
            "connection string (postgresql://...)."
        )
    clean = str(url).strip()
    if clean.lower().startswith("sqlite"):
        raise ValueError(
            "SQLite is not supported. "
            "DATABASE_URL must be a PostgreSQL connection string (postgresql://...)."
        )
    if clean.startswith("postgres://"):
        return "postgresql://" + clean[len("postgres://"):]
    if not clean.startswith("postgresql://"):
        raise ValueError(
            f"Unsupported database scheme: '{clean}'. Only PostgreSQL is supported."
        )
    return clean


def check_db_dialect(url: str) -> None:
    """Raise RuntimeError if url is not a valid PostgreSQL connection string."""
    clean = (url or "").strip().lower()
    if not clean or clean.startswith("sqlite") or not clean.startswith(
        ("postgresql://", "postgres://")
    ):
        raise RuntimeError(
            "DATABASE_URL must be a PostgreSQL connection string (postgresql://...). "
            "SQLite is not supported."
        )


# kept for backward-compat
def check_production_db_dialect(url: str, is_production: bool = True) -> None:
    check_db_dialect(url)


def _engine_kwargs() -> dict:
    """
    Connection-pool settings tuned for Supabase Supavisor on Render free tier.

    pool_recycle=280  : slightly under Supavisor's 300-s idle timeout so
                        SQLAlchemy refreshes the connection first.
    pool_pre_ping     : silently discard stale/banned connections.
    pool_size=3       : low footprint for Render 512 MB free tier.
    connect_timeout=10: fail-fast TCP connect; prevents hanging the event loop.
    """
    return {
        "pool_pre_ping": True,
        "pool_recycle": 280,
        "pool_size": 3,
        "max_overflow": 5,
        "pool_timeout": 30,
        "connect_args": {"connect_timeout": 10},
    }


# ---------------------------------------------------------------------------
# Lazy engine -- built once, never at import time
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_engine():
    """
    Build and return the singleton SQLAlchemy Engine.

    Cached with lru_cache so the engine is created exactly once but ONLY
    when first called -- never at module-import time.
    """
    db_url = normalize_database_url(settings.database_url)
    check_db_dialect(db_url)
    safe = db_url.split("@")[-1] if "@" in db_url else db_url
    logger.info("Creating SQLAlchemy engine -> %s", safe)
    return create_engine(db_url, **_engine_kwargs())


# ---------------------------------------------------------------------------
# Lazy proxy objects -- safe to import at module level
# ---------------------------------------------------------------------------

class _LazyEngine:
    """
    Proxy that forwards attribute access and key method calls to the real
    SQLAlchemy Engine.  Importing 'engine' from this module is always safe
    and never opens a database connection.
    """
    def __getattr__(self, name: str):
        return getattr(get_engine(), name)

    def connect(self, *args, **kwargs):
        return get_engine().connect(*args, **kwargs)

    def begin(self, *args, **kwargs):
        return get_engine().begin(*args, **kwargs)

    def dispose(self, *args, **kwargs):
        return get_engine().dispose(*args, **kwargs)


def _make_session_factory():
    """Module-level factory builder (not an instance method) -- lru_cache-safe."""
    return sessionmaker(autocommit=False, autoflush=False, bind=get_engine())


# Use a plain module-level cache so lru_cache works correctly
_session_factory_cache = None


def _get_session_factory():
    global _session_factory_cache
    if _session_factory_cache is None:
        _session_factory_cache = _make_session_factory()
    return _session_factory_cache


class _LazySessionLocal:
    """Callable proxy: creates a new Session on each call."""
    def __call__(self):
        return _get_session_factory()()


# Public module-level singletons
engine = _LazyEngine()
SessionLocal = _LazySessionLocal()


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

def get_db():
    """Yield a SQLAlchemy session; always close after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
