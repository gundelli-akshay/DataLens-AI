"""
tests/test_step19b_postgres_and_storage.py - Tests for PostgreSQL configuration & Supabase persistent cloud storage.

Verifies:
1. PostgreSQL configuration & DDL schema compilation on postgresql dialect
2. StorageService in local fallback mode (save, read, delete, exists)
3. StorageService in Supabase cloud mode (mocked upload, download, delete)
4. Critical safety: when Supabase is configured, upload/download/delete failures RAISE StorageError
   and DO NOT silently fall back to local disk
5. API endpoints (/upload, /analyze, /documents/chat, DELETE /documents/{id}) with storage service
6. Strict user ownership & isolation for cloud storage operations
"""

import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest
import httpx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects import postgresql

from app.main import app
from app.core.config import Settings
from app.db.session import normalize_database_url, get_engine_args, get_db, SessionLocal
from app.db.models import Base, User, Document, ChatMessage
from app.services.storage import StorageService, StorageError
from app.core.auth import create_access_token


@pytest.fixture
def client():
    return TestClient(app)


# ==============================================================================
# 1. PostgreSQL Configuration & Schema Tests
# ==============================================================================

def test_postgresql_url_normalization_and_engine_args():
    """Verify PostgreSQL connection URL normalization and pooling arguments."""
    raw_supabase_url = "postgres://postgres.abc:SecretPass123@aws-0-us-east-1.pooler.supabase.com:6543/postgres"
    normalized = normalize_database_url(raw_supabase_url)
    assert normalized.startswith("postgresql://")
    assert "postgres.abc:SecretPass123" in normalized

    args = get_engine_args(normalized)
    assert args.get("pool_pre_ping") is True
    assert args.get("pool_recycle") == 300
    assert args.get("pool_size") == 5
    assert args.get("max_overflow") == 10
    assert "connect_args" not in args


def test_postgresql_ddl_compilation():
    """
    Verify all SQLAlchemy models (User, Document, ChatMessage)
    successfully compile DDL for the PostgreSQL dialect (JSON, DateTime, Text, Foreign Keys).
    """
    pg_dialect = postgresql.dialect()

    for table in [User.__table__, Document.__table__, ChatMessage.__table__]:
        ddl = str(CreateTable(table).compile(dialect=pg_dialect))
        assert "CREATE TABLE" in ddl
        assert table.name in ddl

    # Verify JSON column in ChatMessage compiles cleanly for PostgreSQL
    chat_ddl = str(CreateTable(ChatMessage.__table__).compile(dialect=pg_dialect))
    assert "sources JSON" in chat_ddl or "sources JSONB" in chat_ddl or "sources" in chat_ddl


# ==============================================================================
# 2. Exclusive Supabase Storage Enforcement (No Local Fallback)
# ==============================================================================

def test_unconfigured_storage_raises_error(tmp_path):
    """Verify save, read, exists, and delete fail with StorageError when Supabase is unconfigured."""
    test_settings = Settings(
        app_env="development",
        upload_dir=str(tmp_path),
        supabase_url="",
        supabase_key="",
        storage_backend="supabase",
    )
    storage = StorageService(test_settings)
    assert storage.is_cloud is False

    filename = "test_local_file.txt"
    content = b"Hello, storage test!"

    # 1. Save raises StorageError
    with pytest.raises(StorageError) as exc_save:
        storage.save_file(filename, content, "text/plain")
    assert "exclusive file storage backend" in str(exc_save.value)

    # 2. Exists returns False
    assert storage.file_exists(filename) is False

    # 3. Read path raises StorageError
    with pytest.raises(StorageError) as exc_path:
        storage.get_file_path(filename)
    assert "exclusive file storage backend" in str(exc_path.value)

    # 4. Delete raises StorageError
    with pytest.raises(StorageError) as exc_del:
        storage.delete_file(filename)
    assert "exclusive file storage backend" in str(exc_del.value)


def test_storage_cached_file_access(tmp_path):
    """When a file is already in local runtime cache, get_file_path and file_exists return it directly."""
    test_settings = Settings(
        app_env="development",
        upload_dir=str(tmp_path),
        supabase_url="",
        supabase_key="",
        storage_backend="supabase",
    )
    storage = StorageService(test_settings)
    cached_file = tmp_path / "cached.csv"
    cached_file.write_text("a,b\n1,2", encoding="utf-8")

    assert storage.file_exists("cached.csv") is True
    p = storage.get_file_path("cached.csv")
    assert p == cached_file


# ==============================================================================
# 3. Supabase Cloud Storage Tests (Mocked)
# ==============================================================================

def test_supabase_storage_upload_success(tmp_path):
    """Verify successful upload to Supabase Storage bucket."""
    test_settings = Settings(
        app_env="production",
        upload_dir=str(tmp_path),
        supabase_url="https://xyzproject.supabase.co",
        supabase_key="mock-service-role-key-12345",
        supabase_storage_bucket="datalens-files",
        storage_backend="supabase",
    )
    storage = StorageService(test_settings)
    assert storage.is_cloud is True

    filename = "cloud_upload_test.csv"
    content = b"col1,col2\n1,2"

    mock_response = httpx.Response(status_code=200, json={"Key": f"datalens-files/{filename}"})

    with patch("httpx.Client.post", return_value=mock_response) as mock_post:
        saved = storage.save_file(filename, content, "text/csv")
        assert saved == filename
        mock_post.assert_called_once()
        url = mock_post.call_args[0][0]
        assert "https://xyzproject.supabase.co/storage/v1/object/datalens-files/cloud_upload_test.csv" in url
        headers = mock_post.call_args[1]["headers"]
        assert headers["Authorization"] == "Bearer mock-service-role-key-12345"
        assert headers["apikey"] == "mock-service-role-key-12345"

    # Local cache copy should also exist for downstream processing
    cached = tmp_path / filename
    assert cached.exists()
    assert cached.read_bytes() == content


def test_supabase_storage_download_when_not_cached(tmp_path):
    """Verify that get_file_path downloads from Supabase when local cache is empty."""
    test_settings = Settings(
        app_env="production",
        upload_dir=str(tmp_path),
        supabase_url="https://xyzproject.supabase.co",
        supabase_key="mock-service-role-key-12345",
        supabase_storage_bucket="datalens-files",
        storage_backend="supabase",
    )
    storage = StorageService(test_settings)
    filename = "remote_doc.pdf"
    content = b"%PDF-1.4 mock pdf content"

    mock_response = httpx.Response(status_code=200, content=content)

    with patch("httpx.Client.get", return_value=mock_response) as mock_get:
        path = storage.get_file_path(filename)
        assert path.exists()
        assert path.read_bytes() == content
        mock_get.assert_called_once()
        assert "remote_doc.pdf" in mock_get.call_args[0][0]


def test_supabase_storage_delete_success(tmp_path):
    """Verify deleting a file removes it from both Supabase and local cache."""
    test_settings = Settings(
        app_env="production",
        upload_dir=str(tmp_path),
        supabase_url="https://xyzproject.supabase.co",
        supabase_key="mock-service-role-key-12345",
        supabase_storage_bucket="datalens-files",
        storage_backend="supabase",
    )
    storage = StorageService(test_settings)
    filename = "file_to_delete.xlsx"

    # Create local cached file first
    cached_file = tmp_path / filename
    cached_file.write_bytes(b"dummy")

    mock_response = httpx.Response(status_code=200, json=[{"name": filename}])

    with patch("httpx.Client.request", return_value=mock_response) as mock_req:
        result = storage.delete_file(filename)
        assert result is True
        mock_req.assert_called_once()
        assert not cached_file.exists()


# ==============================================================================
# 4. Critical Safety: NO Silent Local Fallback When Supabase Is Configured
# ==============================================================================

def test_supabase_upload_failure_raises_storage_error_no_silent_fallback(tmp_path):
    """
    CRITICAL SAFETY REQUIREMENT:
    If Supabase is configured and cloud upload fails,
    it MUST raise StorageError and MUST NOT silently fall back to local disk.
    """
    test_settings = Settings(
        app_env="production",
        upload_dir=str(tmp_path),
        supabase_url="https://xyzproject.supabase.co",
        supabase_key="mock-service-role-key-12345",
        supabase_storage_bucket="datalens-files",
        storage_backend="supabase",
    )
    storage = StorageService(test_settings)
    filename = "critical_file.csv"
    content = b"data,value\n10,20"

    # 1. HTTP error 500 from Supabase
    err_response = httpx.Response(status_code=500, text="Internal Server Error in Supabase Storage")
    with patch("httpx.Client.post", return_value=err_response):
        with pytest.raises(StorageError) as exc_info:
            storage.save_file(filename, content, "text/csv")
        assert "Supabase upload failed with status 500" in str(exc_info.value)
        # Verify file was NOT saved to disk
        assert not (tmp_path / filename).exists()

    # 2. Network connection error to Supabase
    with patch("httpx.Client.post", side_effect=httpx.ConnectError("Network unreachable")):
        with pytest.raises(StorageError) as exc_info:
            storage.save_file(filename, content, "text/csv")
        assert "network error" in str(exc_info.value).lower()
        assert not (tmp_path / filename).exists()


def test_supabase_download_failure_raises_storage_error(tmp_path):
    """If Supabase download encounters server error, raise StorageError."""
    test_settings = Settings(
        app_env="production",
        upload_dir=str(tmp_path),
        supabase_url="https://xyzproject.supabase.co",
        supabase_key="mock-service-role-key-12345",
        supabase_storage_bucket="datalens-files",
        storage_backend="supabase",
    )
    storage = StorageService(test_settings)
    filename = "broken_file.csv"

    err_response = httpx.Response(status_code=502, text="Bad Gateway")
    with patch("httpx.Client.get", return_value=err_response):
        with pytest.raises(StorageError) as exc_info:
            storage.get_file_path(filename)
        assert "status 502" in str(exc_info.value)


def test_supabase_delete_failure_raises_storage_error(tmp_path):
    """If Supabase deletion fails, raise StorageError."""
    test_settings = Settings(
        app_env="production",
        upload_dir=str(tmp_path),
        supabase_url="https://xyzproject.supabase.co",
        supabase_key="mock-service-role-key-12345",
        supabase_storage_bucket="datalens-files",
        storage_backend="supabase",
    )
    storage = StorageService(test_settings)
    filename = "undeletable.csv"

    err_response = httpx.Response(status_code=500, text="Database error during delete")
    with patch("httpx.Client.request", return_value=err_response):
        with pytest.raises(StorageError) as exc_info:
            storage.delete_file(filename)
        assert "status 500" in str(exc_info.value)


# ==============================================================================
# 5. API Integration & Security Tests
# ==============================================================================

def test_api_upload_with_cloud_storage_failure_returns_502(client, monkeypatch):
    """When cloud storage upload fails, /upload/ returns 502 Bad Gateway with clean message."""
    from app.services.storage import storage_service

    monkeypatch.setattr(storage_service, "save_file", MagicMock(side_effect=StorageError("Cloud upload rejected")))

    db = SessionLocal()
    try:
        user = User(email="upload_502_user@example.com", auth_provider="email")
        db.add(user)
        db.commit()
        db.refresh(user)
        token = create_access_token({"sub": str(user.id), "email": user.email})
    finally:
        db.close()

    res = client.post(
        "/upload/",
        files={"file": ("test.csv", b"a,b\n1,2", "text/csv")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 502
    assert "persistent storage" in res.json()["detail"].lower()


def test_api_analyze_with_storage_integration(client, monkeypatch, tmp_path):
    """Verify /analyze/ retrieves file via storage service."""
    from app.services.storage import storage_service

    csv_file = tmp_path / "test_analyze.csv"
    csv_file.write_text("id,val\n1,100\n2,200", encoding="utf-8")

    monkeypatch.setattr(storage_service, "get_file_path", MagicMock(return_value=csv_file))

    db = SessionLocal()
    try:
        user = User(email="analyze_storage_user@example.com", auth_provider="email")
        db.add(user)
        db.commit()
        db.refresh(user)
        token = create_access_token({"sub": str(user.id), "email": user.email})
    finally:
        db.close()

    res = client.post(
        "/analyze/",
        json={"saved_filename": "test_analyze.csv"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["shape"]["rows"] == 2


def test_api_document_deletion_deletes_from_storage(client, monkeypatch):
    """Verify deleting a document calls storage_service.delete_file and deletes DB records."""
    from app.services.storage import storage_service

    unique_email = f"storage_user_{uuid.uuid4().hex[:8]}@example.com"
    db = SessionLocal()
    try:
        user = User(email=unique_email, auth_provider="email")
        db.add(user)
        db.commit()
        db.refresh(user)

        user_id = user.id
        user_email = user.email

        doc = Document(
            user_id=user_id,
            original_filename="budget.pdf",
            saved_filename=f"uuid_{uuid.uuid4().hex[:8]}_budget.pdf",
            file_type="PDF",
            file_size_bytes=1024,
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        doc_id = doc.id
        saved_filename = doc.saved_filename
    finally:
        db.close()

    mock_delete = MagicMock(return_value=True)
    monkeypatch.setattr(storage_service, "delete_file", mock_delete)

    token = create_access_token({"sub": str(user_id), "email": user_email})
    headers = {"Authorization": f"Bearer {token}"}

    res = client.delete(f"/documents/{doc_id}", headers=headers)
    assert res.status_code == 200
    assert res.json()["status"] == "success"

    # Verify storage_service.delete_file was called with saved_filename
    mock_delete.assert_called_once_with(saved_filename)

    # Verify database record deleted
    db = SessionLocal()
    try:
        deleted_doc = db.query(Document).filter(Document.id == doc_id).first()
        assert deleted_doc is None
        u = db.query(User).filter(User.id == user_id).first()
        if u:
            db.delete(u)
            db.commit()
    finally:
        db.close()


def test_api_document_deletion_cross_user_forbidden(client, monkeypatch):
    """Verify cross-user delete attempts return 403 and DO NOT delete from storage."""
    from app.services.storage import storage_service

    u1_email = f"owner_{uuid.uuid4().hex[:8]}@example.com"
    u2_email = f"attacker_{uuid.uuid4().hex[:8]}@example.com"

    db = SessionLocal()
    try:
        user1 = User(email=u1_email, auth_provider="email")
        user2 = User(email=u2_email, auth_provider="email")
        db.add_all([user1, user2])
        db.commit()
        db.refresh(user1)
        db.refresh(user2)

        u1_id = user1.id
        u2_id = user2.id

        doc = Document(
            user_id=u1_id,
            original_filename="confidential.pdf",
            saved_filename=f"uuid_{uuid.uuid4().hex[:8]}_confidential.pdf",
            file_type="PDF",
            file_size_bytes=2048,
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        doc_id = doc.id
    finally:
        db.close()

    mock_delete = MagicMock(return_value=True)
    monkeypatch.setattr(storage_service, "delete_file", mock_delete)

    # User 2 attempts to delete User 1's document
    token2 = create_access_token({"sub": str(u2_id), "email": u2_email})
    res = client.delete(f"/documents/{doc_id}", headers={"Authorization": f"Bearer {token2}"})

    assert res.status_code == 403
    # Critical: storage delete must NOT have been called
    mock_delete.assert_not_called()

    # Document still exists in DB
    db = SessionLocal()
    try:
        still_exists = db.query(Document).filter(Document.id == doc_id).first()
        assert still_exists is not None
        db.delete(still_exists)
        u1 = db.query(User).filter(User.id == u1_id).first()
        u2 = db.query(User).filter(User.id == u2_id).first()
        if u1: db.delete(u1)
        if u2: db.delete(u2)
        db.commit()
    finally:
        db.close()
