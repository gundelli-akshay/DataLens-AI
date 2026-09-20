from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import settings


def normalize_database_url(url: str | None) -> str:
    """
    Normalize DATABASE_URL for SQLAlchemy compatibility.
    Fixes legacy 'postgres://' schemes provided by some cloud providers (Render, Neon, Supabase)
    to SQLAlchemy's expected 'postgresql://'.
    """
    if not url or not url.strip():
        return "sqlite:///./datalens.db"
    clean = url.strip()
    if clean.startswith("postgres://"):
        return "postgresql://" + clean[len("postgres://"):]
    return clean


def get_engine_args(url: str) -> dict:
    """
    Return engine connection options optimized for the database dialect.
    - SQLite: disables thread check for local file-based testing.
    - PostgreSQL/others: enables connection pre-ping, connection recycling, and pooling.
    """
    if url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    return {
        "pool_pre_ping": True,
        "pool_recycle": 300,
        "pool_size": 5,
        "max_overflow": 10,
    }


normalized_database_url = normalize_database_url(settings.database_url)
engine = create_engine(
    normalized_database_url,
    **get_engine_args(normalized_database_url)
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
