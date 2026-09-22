"""
tests/test_step19_production_config.py - Tests for production deployment configuration.

Covers:
1. PostgreSQL URL normalization ('postgres://' -> 'postgresql://') and rejection of SQLite / unconfigured DB
2. PostgreSQL database engine connection pooling arguments
3. Production settings validation (warnings on default JWT secret & SQLite in production)
4. Public /auth/config endpoint behavior and secret-leak guards
5. PostgreSQL driver dependency check in requirements.txt
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import Settings, DEFAULT_DEV_JWT_SECRET
from app.db.session import normalize_database_url, get_engine_args


@pytest.fixture
def client():
    return TestClient(app)


def test_normalize_database_url():
    # Render, Neon, Supabase legacy URLs
    assert normalize_database_url("postgres://user:pass@host:5432/db") == "postgresql://user:pass@host:5432/db"
    # Modern standard URLs
    assert normalize_database_url("postgresql://user:pass@host:5432/db") == "postgresql://user:pass@host:5432/db"
    # SQLite URLs rejected
    with pytest.raises(ValueError) as exc_info:
        normalize_database_url("sqlite:///./datalens.db")
    assert "SQLite is not supported" in str(exc_info.value)

    # Null/empty string rejected
    with pytest.raises(ValueError) as exc_info_empty:
        normalize_database_url("")
    assert "must be explicitly configured" in str(exc_info_empty.value)

    with pytest.raises(ValueError) as exc_info_none:
        normalize_database_url(None)
    assert "must be explicitly configured" in str(exc_info_none.value)


def test_get_engine_args():
    # PostgreSQL pooling args
    pg_args = get_engine_args("postgresql://user:pass@host:5432/db")
    assert pg_args.get("pool_pre_ping") is True
    assert pg_args.get("pool_recycle") == 300
    assert pg_args.get("pool_size") == 5
    assert pg_args.get("max_overflow") == 10
    assert "connect_args" not in pg_args


def test_validate_production_settings_dev_mode():
    s = Settings(
        app_env="development",
        jwt_secret_key=DEFAULT_DEV_JWT_SECRET,
        database_url="postgresql://user:pass@host:5432/test",
    )
    warnings = s.validate_production_settings()
    assert len(warnings) == 0, "No warnings expected in development environment"


def test_validate_production_settings_production_warnings():
    # Production with defaults triggers errors
    s = Settings(
        app_env="production",
        jwt_secret_key=DEFAULT_DEV_JWT_SECRET,
        database_url="sqlite:///./datalens.db",
        supabase_url="",
        supabase_key="",
    )
    warnings = s.validate_production_settings()
    assert any("JWT_SECRET_KEY" in w for w in warnings)
    assert any("DATABASE_URL" in w for w in warnings)
    assert any("Supabase Storage" in w for w in warnings)

    # Production with complete secure settings has zero errors/warnings
    s_clean = Settings(
        app_env="production",
        jwt_secret_key="a-very-long-production-grade-secret-key-32-chars!",
        database_url="postgresql://user:pass@host:5432/db",
        supabase_url="https://xyzproject.supabase.co",
        supabase_key="mock-service-role-key-12345",
        groq_api_key="gsk_mock_production_groq_key_12345",
    )
    assert len(s_clean.validate_production_settings()) == 0


def test_auth_config_endpoint(client):
    res = client.get("/auth/config")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "google_client_id" in data
    assert "google_auth_enabled" in data
    assert isinstance(data["google_auth_enabled"], bool)

    # Security check: must NEVER expose secrets in auth config
    res_text = res.text.lower()
    assert "jwt_secret" not in res_text
    assert "groq_api_key" not in res_text
    assert "database_url" not in res_text


def test_requirements_includes_psycopg2():
    req_path = BACKEND_DIR / "requirements.txt"
    content = req_path.read_text(encoding="utf-8")
    assert "psycopg2-binary" in content
    assert not content.startswith("# psycopg2-binary")
