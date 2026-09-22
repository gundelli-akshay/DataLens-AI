"""
conftest.py - Pytest fixtures and test isolation harness for backend test suite.

Ensures strict test hermeticity and safety:
1. Complete Database Isolation:
   - Automated tests run against an isolated in-memory SQLite database (using StaticPool for thread-safety with TestClient).
   - Tests NEVER read, write, or alter the live Supabase production PostgreSQL database.
   - Production code (app/core/config.py, app/db/session.py) remains 100% PostgreSQL-only.
2. Complete Storage Isolation:
   - Global storage_service methods are routed to an ephemeral test directory during test execution.
   - Tests NEVER upload, modify, or delete objects from the live Supabase Storage bucket ('datalens-files').
3. Gemini API Isolation:
   - By default, keeps gemini_api_key empty in unit tests to prevent quota consumption,
     ensuring deterministic execution of Groq and error-fallback tests.
"""

import sys
import tempfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.models import Base
from app.db.session import get_db
import app.db.session as session_module
from app.services.storage import storage_service
from app.main import app


# ------------------------------------------------------------------------------
# 1. Isolated In-Memory Test Database Setup
# ------------------------------------------------------------------------------

TEST_DATABASE_URL = "sqlite:///:memory:"
test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

# Create all schema tables on test_engine immediately
Base.metadata.create_all(bind=test_engine)


def default_override_get_db():
    """Yield an isolated DB session bound to the in-memory test database."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def dynamic_session_local(*args, **kwargs):
    """
    If a test module defines its own get_db override (e.g. test_user_menu_and_dashboard),
    route calls to that active override so that SessionLocal and get_db share the exact same session/engine.
    Otherwise, return a session bound to TestingSessionLocal.
    """
    override = app.dependency_overrides.get(get_db)
    if override and override is not default_override_get_db:
        gen = override()
        return next(gen)
    return TestingSessionLocal(*args, **kwargs)


# Patch session_module immediately upon conftest import
session_module.SessionLocal = dynamic_session_local
session_module.engine = test_engine


@pytest.fixture(autouse=True)
def isolate_test_database(monkeypatch):
    """
    Autouse fixture ensuring that EVERY test uses an isolated in-memory test database,
    and that SessionLocal and get_db are consistently redirected away from production PostgreSQL.
    """
    Base.metadata.create_all(bind=test_engine)
    if get_db not in app.dependency_overrides:
        app.dependency_overrides[get_db] = default_override_get_db
    monkeypatch.setattr(session_module, "SessionLocal", dynamic_session_local)
    monkeypatch.setattr(session_module, "engine", test_engine)
    yield
    # If the test did not set a custom override or cleared it, restore default_override_get_db
    if get_db not in app.dependency_overrides:
        app.dependency_overrides[get_db] = default_override_get_db


# ------------------------------------------------------------------------------
# 2. Ephemeral Storage Isolation
# ------------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolate_storage_service_in_tests(tmp_path_factory):
    """
    Ensure automated tests save and read files exclusively from an ephemeral temporary
    test directory, completely preventing any uploads or deletes to the real
    Supabase Storage bucket ('datalens-files').
    """
    test_storage_dir = tmp_path_factory.mktemp("test_uploads")

    orig_save = storage_service.save_file
    orig_get_path = storage_service.get_file_path
    orig_get_bytes = storage_service.get_file_bytes
    orig_delete = storage_service.delete_file
    orig_exists = storage_service.file_exists
    orig_upload_dir = settings.upload_dir
    orig_storage_upload_dir = storage_service.settings.upload_dir

    # Point upload directories to ephemeral test directory so tests never touch data/uploads
    settings.upload_dir = str(test_storage_dir)
    storage_service.settings.upload_dir = str(test_storage_dir)

    def mock_save_file(saved_filename: str, content: bytes, content_type: str = "application/octet-stream") -> str:
        p = test_storage_dir / saved_filename
        p.write_bytes(content)
        return saved_filename

    def mock_get_file_path(saved_filename: str) -> Path:
        p = test_storage_dir / saved_filename
        if p.exists() and p.is_file():
            return p
        # Fallback to local upload_dir_path if present
        local_p = storage_service.settings.upload_dir_path / saved_filename
        if local_p.exists() and local_p.is_file():
            return local_p
        raise FileNotFoundError(f"File not found in test storage: {saved_filename}")

    def mock_get_file_bytes(saved_filename: str) -> bytes:
        p = mock_get_file_path(saved_filename)
        if p.exists() and p.is_file():
            return p.read_bytes()
        raise FileNotFoundError(f"File not found in test storage: {saved_filename}")

    def mock_delete_file(saved_filename: str) -> bool:
        p1 = test_storage_dir / saved_filename
        if p1.exists() and p1.is_file():
            p1.unlink()
        p2 = storage_service.settings.upload_dir_path / saved_filename
        if p2.exists() and p2.is_file():
            try:
                p2.unlink()
            except Exception:
                pass
        return True

    def mock_file_exists(saved_filename: str) -> bool:
        p1 = test_storage_dir / saved_filename
        if p1.exists() and p1.is_file():
            return True
        p2 = storage_service.settings.upload_dir_path / saved_filename
        return p2.exists() and p2.is_file()

    storage_service.save_file = mock_save_file
    storage_service.get_file_path = mock_get_file_path
    storage_service.get_file_bytes = mock_get_file_bytes
    storage_service.delete_file = mock_delete_file
    storage_service.file_exists = mock_file_exists

    yield

    storage_service.save_file = orig_save
    storage_service.get_file_path = orig_get_path
    storage_service.get_file_bytes = orig_get_bytes
    storage_service.delete_file = orig_delete
    storage_service.file_exists = orig_exists
    settings.upload_dir = orig_upload_dir
    storage_service.settings.upload_dir = orig_storage_upload_dir


# ------------------------------------------------------------------------------
# 3. LLM / Gemini API Isolation
# ------------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolate_gemini_in_unit_tests(monkeypatch):
    """
    By default in unit tests, keep gemini_api_key empty so that unit tests
    remain hermetic, do not consume live Gemini quota, and allow Groq-fallback
    and error-handling tests to execute deterministically.
    """
    monkeypatch.setattr(settings, "gemini_api_key", "")
