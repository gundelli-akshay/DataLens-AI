from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import settings


def check_db_dialect(url: str):
    clean = (url or "").strip().lower()
    if not clean or clean.startswith("sqlite") or not clean.startswith(("postgresql://", "postgres://")):
        raise RuntimeError(
            "DATABASE_URL must be configured with a PostgreSQL connection string (postgresql://...). "
            "SQLite is not supported."
        )


def check_production_db_dialect(url: str, is_production: bool = True):
    check_db_dialect(url)


def normalize_database_url(url: str | None) -> str:
    """
    Normalize and validate DATABASE_URL for SQLAlchemy compatibility.
    Requires an explicitly configured PostgreSQL connection string ('postgresql://' or 'postgres://').
    SQLite and empty URLs are rejected.
    """
    if not url or not url.strip():
        raise ValueError(
            "DATABASE_URL must be explicitly configured with a PostgreSQL connection string (postgresql://...)."
        )
    clean = url.strip()
    if clean.lower().startswith("sqlite"):
        raise ValueError(
            "SQLite is not supported. DATABASE_URL must be a PostgreSQL connection string (postgresql://...)."
        )
    if clean.startswith("postgres://"):
        return "postgresql://" + clean[len("postgres://"):]
    if not clean.startswith("postgresql://"):
        raise ValueError(
            f"Unsupported database scheme in DATABASE_URL: '{clean}'. Only PostgreSQL is supported."
        )
    return clean


def get_engine_args(url: str) -> dict:
    """
    Return PostgreSQL engine connection options with connection pooling, recycling, and pre-ping.
    """
    return {
        "pool_pre_ping": True,
        "pool_recycle": 300,
        "pool_size": 5,
        "max_overflow": 10,
    }


normalized_database_url = normalize_database_url(settings.database_url)
check_db_dialect(normalized_database_url)
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
