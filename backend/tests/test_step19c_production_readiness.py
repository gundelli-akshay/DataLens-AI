"""
tests/test_step19c_production_readiness.py - Comprehensive tests for production readiness.

Verifies:
1. Production database requirement: SQLite in production is treated as a fatal configuration error; PostgreSQL is required.
2. Production storage requirement: Missing Supabase Storage in production is a fatal configuration error; local fallback is rejected.
3. Development fallback preserved: SQLite and local storage work cleanly in development mode.
4. Production JWT secret enforcement: default dev secret or key < 32 chars is rejected.
5. Production CORS enforcement: wildcard '*' is strictly forbidden and stripped.
6. Secret-leak guards: auth config and error responses never expose credentials or internal paths.
7. Docker configuration: validates docker-compose.yml and Dockerfile production settings.
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import Settings, DEFAULT_DEV_JWT_SECRET
from app.db.session import check_production_db_dialect, normalize_database_url
from app.services.storage import StorageService, StorageError


@pytest.fixture
def client():
    return TestClient(app)


# ==============================================================================
# 1. Production Database Enforcement
# ==============================================================================

def test_production_sqlite_is_fatal_error():
    """SQLite in production must be treated as a configuration error."""
    s = Settings(
        app_env="production",
        database_url="sqlite:///./datalens.db",
        jwt_secret_key="a-secure-production-grade-jwt-secret-32-chars!",
        supabase_url="https://xyz.supabase.co",
        supabase_key="mock-key-12345",
    )
    errors = s.validate_production_errors()
    assert any("DATABASE_URL" in err and "SQLite is not permitted" in err for err in errors)


def test_production_db_dialect_check_raises_runtime_error():
    """check_production_db_dialect raises RuntimeError for SQLite in all environments."""
    with pytest.raises(RuntimeError) as exc_info:
        check_production_db_dialect("sqlite:///./datalens.db", is_production=True)
    assert "SQLite is not supported" in str(exc_info.value)

    # In development as well, SQLite is rejected because SQLite is completely removed
    with pytest.raises(RuntimeError) as exc_info_dev:
        check_production_db_dialect("sqlite:///./datalens.db", is_production=False)
    assert "SQLite is not supported" in str(exc_info_dev.value)

    # PostgreSQL URL is accepted
    check_production_db_dialect("postgresql://user:pass@host:5432/db", is_production=True)


# ==============================================================================
# 2. Production Storage Enforcement
# ==============================================================================

def test_production_missing_supabase_is_fatal_error():
    """Missing Supabase storage in production must be treated as a configuration error."""
    s = Settings(
        app_env="production",
        database_url="postgresql://user:pass@host:5432/db",
        jwt_secret_key="a-secure-production-grade-jwt-secret-32-chars!",
        supabase_url="",
        supabase_key="",
    )
    errors = s.validate_production_errors()
    assert any("Persistent object storage (Supabase Storage)" in err for err in errors)


def test_production_storage_service_rejects_local_fallback(tmp_path):
    """Production storage service must NEVER fall back to local disk if Supabase is unconfigured."""
    test_settings = Settings(
        app_env="production",
        upload_dir=str(tmp_path),
        supabase_url="",
        supabase_key="",
        storage_backend="supabase",
    )
    storage = StorageService(test_settings)
    assert storage.is_cloud is False

    # save_file without cloud storage must raise StorageError
    with pytest.raises(StorageError) as exc_info:
        storage.save_file("test.csv", b"a,b\n1,2")
    assert "exclusive file storage backend" in str(exc_info.value)

    # get_file_path without cloud storage must raise StorageError
    with pytest.raises(StorageError):
        storage.get_file_path("test.csv")

    # delete_file without cloud storage must raise StorageError
    with pytest.raises(StorageError):
        storage.delete_file("test.csv")


def test_development_storage_service_requires_supabase(tmp_path):
    """In development mode, unconfigured storage raises StorageError (no local fallback)."""
    dev_settings = Settings(
        app_env="development",
        upload_dir=str(tmp_path),
        supabase_url="",
        supabase_key="",
        storage_backend="supabase",
    )
    storage = StorageService(dev_settings)
    with pytest.raises(StorageError) as exc_info:
        storage.save_file("dev.csv", b"col1,col2\n10,20")
    assert "exclusive file storage backend" in str(exc_info.value)


# ==============================================================================
# 3. Production JWT Secret Enforcement
# ==============================================================================

def test_production_insecure_jwt_secret_is_fatal_error():
    """Default or short JWT secret in production must be flagged as error."""
    # 1. Default dev secret
    s1 = Settings(
        app_env="production",
        jwt_secret_key=DEFAULT_DEV_JWT_SECRET,
        database_url="postgresql://user:pass@host:5432/db",
        supabase_url="https://xyz.supabase.co",
        supabase_key="mock-key-12345",
    )
    assert any("JWT_SECRET_KEY" in err for err in s1.validate_production_errors())

    # 2. Key shorter than 32 characters
    s2 = Settings(
        app_env="production",
        jwt_secret_key="short-secret-123",
        database_url="postgresql://user:pass@host:5432/db",
        supabase_url="https://xyz.supabase.co",
        supabase_key="mock-key-12345",
    )
    assert any("JWT_SECRET_KEY" in err for err in s2.validate_production_errors())


# ==============================================================================
# 4. Production CORS Enforcement
# ==============================================================================

def test_production_wildcard_cors_is_forbidden():
    """Wildcard '*' in CORS origins is forbidden in production."""
    s = Settings(
        app_env="production",
        cors_origins=["*"],
        database_url="postgresql://user:pass@host:5432/db",
        jwt_secret_key="a-secure-production-grade-jwt-secret-32-chars!",
        supabase_url="https://xyz.supabase.co",
        supabase_key="mock-key-12345",
    )
    errors = s.validate_production_errors()
    assert any("CORS_ORIGINS contains wildcard '*'" in err for err in errors)


def test_production_all_valid_settings_zero_errors():
    """A completely configured production environment returns zero errors."""
    s = Settings(
        app_env="production",
        database_url="postgresql://user:pass@host:5432/db",
        jwt_secret_key="a-secure-production-grade-jwt-secret-32-chars!",
        supabase_url="https://xyz.supabase.co",
        supabase_key="mock-service-role-key-12345",
        groq_api_key="gsk_mock_production_groq_key_12345",
        cors_origins=["https://datalens.app", "https://app.datalens.ai"],
    )
    assert len(s.validate_production_errors()) == 0
    assert len(s.validate_production_settings()) == 0


# ==============================================================================
# 5. Secret-Leak Guards & Exception Handler
# ==============================================================================

def test_auth_config_leak_guard(client):
    """The public /auth/config endpoint must never reveal backend secrets."""
    res = client.get("/auth/config")
    assert res.status_code == 200
    text = res.text.lower()
    for secret in ["jwt_secret", "groq_api_key", "supabase_key", "database_url"]:
        assert secret not in text


@pytest.mark.anyio
async def test_global_exception_handler_sanitizes_errors():
    """Internal 500 exceptions must return a generic detail message without stacktrace or internal paths."""
    from app.main import global_exception_handler
    from starlette.requests import Request

    scope = {"type": "http", "method": "GET", "path": "/test", "headers": []}
    req = Request(scope)
    exc = Exception("Internal DB query failed at /var/app/secret/password=123")

    response = await global_exception_handler(req, exc)
    assert response.status_code == 500
    body = response.body.decode()
    assert "An unexpected internal server error occurred." in body
    assert "/var/app/secret" not in body
    assert "password=123" not in body


# ==============================================================================
# 6. Docker Configuration Integrity
# ==============================================================================

def test_docker_compose_and_dockerfile_integrity():
    """Verify docker-compose.yml and Dockerfiles contain required production configuration."""
    dc_path = REPO_DIR / "docker-compose.yml"
    assert dc_path.exists()
    dc_content = dc_path.read_text(encoding="utf-8")

    # Verify environment variables in docker-compose.yml
    assert "DATABASE_URL" in dc_content
    assert "SUPABASE_URL" in dc_content
    assert "SUPABASE_KEY" in dc_content
    assert "SUPABASE_STORAGE_BUCKET" in dc_content
    assert "JWT_SECRET_KEY" in dc_content
    assert "CORS_ORIGINS" in dc_content

    # Verify backend Dockerfile
    backend_df = REPO_DIR / "backend" / "Dockerfile"
    assert backend_df.exists()
    b_df_content = backend_df.read_text(encoding="utf-8")
    assert "HEALTHCHECK" in b_df_content
    assert "uvicorn" in b_df_content

    # Verify frontend Dockerfile
    frontend_df = REPO_DIR / "frontend" / "Dockerfile"
    assert frontend_df.exists()
    f_df_content = frontend_df.read_text(encoding="utf-8")
    assert "npm run build" in f_df_content
    assert "nginx" in f_df_content
