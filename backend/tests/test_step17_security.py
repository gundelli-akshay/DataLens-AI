"""
backend/tests/test_step17_security.py - Targeted Security Hardening Tests.

Verifies:
1. CORS safe origin configuration.
2. Password security (bcrypt storage, no plaintext in db or responses, max length limits).
3. JWT validation & tampering protection (algorithm none, invalid signature).
4. File upload size limit enforcement and null-byte filename sanitization.
5. Document extraction multi-tenant ownership enforcement (403 IDOR protection).
6. RAG vector store cross-tenant data leakage prevention (user chunk isolation).
7. User isolation in document chat and vector index clearing.
8. Error response sanitization (no internal server paths or stack traces leaked).
9. Google login token verification hardening.
"""

import gc
import sys
import uuid
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from unittest.mock import patch
import jwt
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings
from app.core.auth import create_access_token, hash_password
from app.db.session import get_db, Base, engine, SessionLocal
from app.db.models import User, Document
from app.services.rag import vector_index, index_document_data


@pytest.fixture(autouse=True)
def setup_security_db_and_index():
    Base.metadata.create_all(bind=engine)
    vector_index.clear()
    yield
    vector_index.clear()
    gc.collect()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def test_users(client):
    db = SessionLocal()
    try:
        # Create User Alice
        alice = db.query(User).filter(User.email == "alice_sec@example.com").first()
        if not alice:
            alice = User(
                email="alice_sec@example.com",
                hashed_password=hash_password("AliceSecurePass1!"),
                full_name="Alice Security",
                auth_provider="email",
            )
            db.add(alice)
            db.commit()
            db.refresh(alice)

        # Create User Bob
        bob = db.query(User).filter(User.email == "bob_sec@example.com").first()
        if not bob:
            bob = User(
                email="bob_sec@example.com",
                hashed_password=hash_password("BobSecurePass2!"),
                full_name="Bob Security",
                auth_provider="email",
            )
            db.add(bob)
            db.commit()
            db.refresh(bob)

        alice_token = create_access_token({"sub": str(alice.id), "email": alice.email})
        bob_token = create_access_token({"sub": str(bob.id), "email": bob.email})

        return {
            "alice": alice,
            "bob": bob,
            "alice_headers": {"Authorization": f"Bearer {alice_token}"},
            "bob_headers": {"Authorization": f"Bearer {bob_token}"},
        }
    finally:
        db.close()


def test_cors_configuration_safe():
    """Verify CORS origins are configured safely without wildcard defaults."""
    assert "*" not in settings.cors_origins
    assert "http://localhost:5173" in settings.cors_origins


def test_password_max_length_protection(client):
    """Verify passwords exceeding 128 chars are rejected to mitigate bcrypt DoS."""
    massive_pwd = "A" * 200
    res = client.post("/auth/signup", json={"email": "longpwd@example.com", "password": massive_pwd})
    assert res.status_code == 422

    res_login = client.post("/auth/login", json={"email": "alice_sec@example.com", "password": massive_pwd})
    assert res_login.status_code == 422


def test_passwords_never_stored_or_leaked_in_plaintext(client, test_users):
    """Verify passwords are never stored in plaintext and never leaked in responses."""
    db = SessionLocal()
    try:
        alice = db.query(User).filter(User.email == "alice_sec@example.com").first()
        assert alice.hashed_password is not None
        assert alice.hashed_password != "AliceSecurePass1!"
        assert alice.hashed_password.startswith("$2b$") or alice.hashed_password.startswith("$2a$")
    finally:
        db.close()

    res = client.get("/auth/me", headers=test_users["alice_headers"])
    assert res.status_code == 200
    data = res.json()["user"]
    assert "password" not in data
    assert "hashed_password" not in data


def test_jwt_tampering_and_algorithm_none_rejected(client):
    """Verify tokens forged with algorithm none or invalid signature are rejected."""
    # Algorithm none attack
    forged_none = jwt.encode({"sub": "1", "email": "admin@example.com"}, key="", algorithm="none")
    res_none = client.get("/auth/me", headers={"Authorization": f"Bearer {forged_none}"})
    assert res_none.status_code == 401

    # Bad signature
    bad_sig = jwt.encode({"sub": "1", "email": "admin@example.com"}, key="wrong-secret-key-12345678901234567890", algorithm="HS256")
    res_bad = client.get("/auth/me", headers={"Authorization": f"Bearer {bad_sig}"})
    assert res_bad.status_code == 401


def test_file_upload_null_byte_sanitization(client, test_users):
    """Verify filename with null bytes is sanitized safely."""
    file_bytes = b"header1,header2\n1,2\n3,4"
    res = client.post(
        "/upload/",
        files={"file": (f"test{chr(0)}evil.csv", file_bytes, "text/csv")},
        headers=test_users["alice_headers"],
    )
    assert res.status_code == 200
    saved = res.json()["saved_filename"]
    assert chr(0) not in saved
    assert "testevil.csv" in saved


def test_file_upload_size_limit_rejection(client, test_users, monkeypatch):
    """Verify uploads exceeding maximum size limit return 413 without reading unbounded memory."""
    from app.api import upload
    monkeypatch.setattr(upload, "MAX_BYTES", 100)
    oversized = b"a" * 200
    res = client.post(
        "/upload/",
        files={"file": ("large.csv", oversized, "text/csv")},
        headers=test_users["alice_headers"],
    )
    assert res.status_code == 413
    assert "too large" in res.json()["detail"].lower()


def test_extract_ownership_isolation(client, test_users):
    """Verify User B cannot extract text from User A's document (IDOR protection)."""
    db = SessionLocal()
    alice_doc_path = None
    doc = None
    try:
        unique_suffix = uuid.uuid4().hex
        alice_doc_name = f"{unique_suffix}_alice_confidential.pdf"
        alice_doc_path = settings.upload_dir_path / alice_doc_name
        alice_doc_path.write_bytes(b"%PDF-1.4 simulated pdf")

        doc = Document(
            user_id=test_users["alice"].id,
            original_filename="alice_confidential.pdf",
            saved_filename=alice_doc_name,
            file_type="PDF",
            file_size_bytes=len(alice_doc_path.read_bytes()),
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)

        # Bob attempts to extract Alice's document
        res = client.post(
            "/documents/extract",
            json={"saved_filename": alice_doc_name},
            headers=test_users["bob_headers"],
        )
        assert res.status_code == 403
        assert "do not have access" in res.json()["detail"].lower()
    finally:
        if doc and doc.id:
            try:
                db.delete(doc)
                db.commit()
            except Exception:
                pass
        db.close()
        gc.collect()
        if alice_doc_path and alice_doc_path.exists():
            try:
                alice_doc_path.unlink()
            except Exception:
                pass


def test_rag_cross_tenant_isolation(client, test_users):
    """
    Verify that in-memory vector retrieval isolates chunks by user_id.
    User B cannot retrieve User A's indexed chunks even if query matches perfectly.
    """
    vector_index.clear()

    # Index document chunks belonging to Alice
    alice_data = {
        "filename": "alice_secrets.pdf",
        "saved_filename": "alice_secrets.pdf",
        "file_type": "PDF",
        "pages": [{"page_number": 1, "text": "Alice's secret financial report contains dividend details of $10M."}],
    }
    index_document_data(alice_data, user_id=test_users["alice"].id, index=vector_index)

    # Index document chunks belonging to Bob
    bob_data = {
        "filename": "bob_notes.pdf",
        "saved_filename": "bob_notes.pdf",
        "file_type": "PDF",
        "pages": [{"page_number": 1, "text": "Bob's general weekly grocery list with apples and milk."}],
    }
    index_document_data(bob_data, user_id=test_users["bob"].id, index=vector_index)

    # Bob retrieves without specifying filename
    res_bob = client.post(
        "/documents/retrieve",
        json={"query": "financial dividend report $10M"},
        headers=test_users["bob_headers"],
    )
    assert res_bob.status_code == 200
    bob_results = res_bob.json()["results"]
    for chunk in bob_results:
        assert "Alice's secret" not in chunk["text"]
        assert chunk.get("user_id") == test_users["bob"].id

    # Alice retrieves the same query
    res_alice = client.post(
        "/documents/retrieve",
        json={"query": "financial dividend report $10M"},
        headers=test_users["alice_headers"],
    )
    assert res_alice.status_code == 200
    alice_results = res_alice.json()["results"]
    assert len(alice_results) > 0
    assert any("Alice's secret" in c["text"] for c in alice_results)


def test_clear_index_user_isolation(test_users):
    """Verify clearing index only removes the calling user's chunks."""
    vector_index.clear()

    # Add chunks for both Alice and Bob
    alice_data = {
        "filename": "alice_doc.pdf",
        "file_type": "PDF",
        "pages": [{"page_number": 1, "text": "Alice's private content."}],
    }
    bob_data = {
        "filename": "bob_doc.pdf",
        "file_type": "PDF",
        "pages": [{"page_number": 1, "text": "Bob's private content."}],
    }
    index_document_data(alice_data, user_id=test_users["alice"].id, index=vector_index)
    index_document_data(bob_data, user_id=test_users["bob"].id, index=vector_index)

    assert vector_index.count() == 2
    assert vector_index.count(user_id=test_users["alice"].id) == 1
    assert vector_index.count(user_id=test_users["bob"].id) == 1

    # Alice clears her index
    vector_index.clear(user_id=test_users["alice"].id)

    # Alice's chunk is gone, Bob's chunk remains safe
    assert vector_index.count(user_id=test_users["alice"].id) == 0
    assert vector_index.count(user_id=test_users["bob"].id) == 1
    assert vector_index.count() == 1


def test_error_response_does_not_leak_filesystem_paths(client, test_users):
    """Verify error responses on corrupted files do not leak absolute server paths."""
    unique_suffix = uuid.uuid4().hex
    corrupt_name = f"{unique_suffix}_corrupt.pdf"
    corrupt_path = settings.upload_dir_path / corrupt_name
    corrupt_path.write_bytes(b"%PDF-corrupted invalid byte sequence")

    try:
        res = client.post(
            "/documents/extract",
            json={"saved_filename": corrupt_name},
            headers=test_users["alice_headers"],
        )
        assert res.status_code == 422
        detail = res.json()["detail"]
        # Ensure server drive letter and path fragments are NOT leaked
        assert "C:\\" not in detail
        assert "C:/" not in detail
        assert "OneDrive" not in detail
        assert "Desktop" not in detail
        assert "uploads" not in detail
    finally:
        gc.collect()
        if corrupt_path.exists():
            try:
                corrupt_path.unlink()
            except Exception:
                pass


def test_google_login_invalid_token_rejected(client):
    """Verify invalid Google ID tokens are rejected with 401 and clean message."""
    res = client.post("/auth/google", json={"id_token": "malicious.forged.google_token"})
    assert res.status_code == 401
    assert "invalid google id token" in res.json()["detail"].lower()
