import sys
from pathlib import Path
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

"""
tests/test_step15_auth.py - Targeted tests for Step 15 Authentication.

Covers:
1. User signup with email/password (secure bcrypt hashing, never plaintext).
2. User login with valid/invalid credentials.
3. Google Sign-In with mocked Google ID token verification.
4. Google login reuses existing user if email matches.
5. GET /auth/me profile retrieval and token validation (expired/invalid).
6. Protected document/chat endpoints reject unauthenticated requests with 401.
7. Data isolation: User cannot access another user's document or chat (403 Forbidden).
8. Document uploads with auth attach user_id to Document record.
9. Backward compatibility: CSV/XLSX analysis works unauthenticated.
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db.session import Base, get_db
from app.db.models import User, Document, ChatMessage
from app.core.auth import hash_password, verify_password, create_access_token

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="module", autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session():
    db = TestingSessionLocal()
    yield db
    db.close()


@pytest.fixture
def client():
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_password_hashing_security():
    """Verify passwords are secure, never stored in plaintext, and bcrypt salts match."""
    raw = "SuperSecret123!"
    hashed = hash_password(raw)
    assert hashed != raw
    assert hashed.startswith("$2b$")
    assert verify_password(raw, hashed) is True
    assert verify_password("WrongPassword", hashed) is False


def test_signup_success_and_db_record(client, db_session):
    """User can sign up with email and password, receiving a JWT and safe user record."""
    payload = {
        "email": "alice@example.com",
        "password": "Password123!",
        "full_name": "Alice Smith",
    }
    response = client.post("/auth/signup", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "success"
    assert "access_token" in data
    assert data["user"]["email"] == "alice@example.com"
    assert data["user"]["full_name"] == "Alice Smith"

    # Verify directly in database that password is not plaintext
    user = db_session.query(User).filter(User.email == "alice@example.com").first()
    assert user is not None
    assert user.hashed_password != "Password123!"
    assert verify_password("Password123!", user.hashed_password) is True


def test_signup_duplicate_email_rejected(client):
    """Duplicate email registration is rejected with 400."""
    payload = {
        "email": "alice@example.com",
        "password": "AnotherPassword456!",
        "full_name": "Alice Duplicate",
    }
    response = client.post("/auth/signup", json=payload)
    assert response.status_code == 400
    assert "already exists" in response.json()["detail"].lower()


def test_login_success(client):
    """Valid credentials return a JWT access token and user info."""
    payload = {"email": "alice@example.com", "password": "Password123!"}
    response = client.post("/auth/login", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "access_token" in data
    assert data["user"]["email"] == "alice@example.com"


def test_login_invalid_password(client):
    """Wrong password returns 401 Unauthorized."""
    payload = {"email": "alice@example.com", "password": "WrongPassword!"}
    response = client.post("/auth/login", json=payload)
    assert response.status_code == 401
    assert "Invalid email or password" in response.json()["detail"]


def test_login_nonexistent_user(client):
    """Nonexistent email returns 401 Unauthorized."""
    payload = {"email": "nobody@example.com", "password": "Password123!"}
    response = client.post("/auth/login", json=payload)
    assert response.status_code == 401


@patch("app.api.auth.id_token.verify_oauth2_token")
def test_google_login_new_user(mock_verify, client, db_session):
    """Google sign-in creates a new user when email does not exist."""
    mock_verify.return_value = {
        "sub": "google-uid-001",
        "email": "googleuser@example.com",
        "name": "Google User",
    }
    payload = {"id_token": "mock-google-id-token-xyz"}
    response = client.post("/auth/google", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["user"]["email"] == "googleuser@example.com"
    assert data["user"]["full_name"] == "Google User"
    assert data["user"]["auth_provider"] == "google"

    # Verify in DB
    user = db_session.query(User).filter(User.email == "googleuser@example.com").first()
    assert user is not None
    assert user.hashed_password is None


@patch("app.api.auth.id_token.verify_oauth2_token")
def test_google_login_reuses_existing_user(mock_verify, client, db_session):
    """If Google login email matches an existing user, reuses that User instead of duplicating."""
    alice = db_session.query(User).filter(User.email == "alice@example.com").first()
    original_id = alice.id

    mock_verify.return_value = {
        "sub": "google-uid-002",
        "email": "alice@example.com",
        "name": "Alice Smith Google",
    }
    payload = {"credential": "mock-google-credential-token"}
    response = client.post("/auth/google", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["user"]["id"] == original_id
    assert data["user"]["email"] == "alice@example.com"

    # Confirm no duplicate User was created
    users_with_email = db_session.query(User).filter(User.email == "alice@example.com").all()
    assert len(users_with_email) == 1


def test_auth_me_endpoints(client):
    """Test /auth/me with valid token, no token, and invalid token."""
    # 1. No token -> 401
    res_no_token = client.get("/auth/me")
    assert res_no_token.status_code == 401

    # 2. Invalid token -> 401
    res_invalid = client.get("/auth/me", headers={"Authorization": "Bearer invalid.token.value"})
    assert res_invalid.status_code == 401

    # 3. Valid token -> 200
    login_res = client.post("/auth/login", json={"email": "alice@example.com", "password": "Password123!"})
    token = login_res.json()["access_token"]
    res_valid = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res_valid.status_code == 200
    assert res_valid.json()["user"]["email"] == "alice@example.com"


def test_protected_document_endpoints_reject_unauthenticated(client):
    """Document operations reject unauthenticated calls with 401."""
    # Chat without token
    res_chat = client.post("/documents/chat", json={"question": "What is this?", "filename": "test.pdf"})
    assert res_chat.status_code == 401

    # Index without token
    res_index = client.post("/documents/index", json={"saved_filename": "test.pdf"})
    assert res_index.status_code == 401

    # My-documents without token
    res_my_docs = client.get("/documents/my-documents")
    assert res_my_docs.status_code == 401


def test_user_data_isolation_document_chat(client, db_session, monkeypatch):
    """User A cannot access User B's document in chat (returns 403 Forbidden)."""
    from app.api import documents
    monkeypatch.setattr(documents, "retrieve_relevant_chunks", lambda **kwargs: [{"text": "secret content", "metadata": {"page_number": 1}}])
    monkeypatch.setattr(documents, "generate_rag_answer", lambda **kwargs: {"answer": "Secret Answer", "sources": ["Page 1"], "model": "mock"})

    # Create User B (Bob)
    bob_res = client.post("/auth/signup", json={"email": "bob@example.com", "password": "BobPassword123!"})
    bob_id = bob_res.json()["user"]["id"]
    bob_token = bob_res.json()["access_token"]

    # Alice's token
    alice_token = client.post("/auth/login", json={"email": "alice@example.com", "password": "Password123!"}).json()["access_token"]

    # Create a document owned by Bob
    bobs_doc = Document(
        user_id=bob_id,
        original_filename="bobs_confidential.pdf",
        saved_filename="uuid_bobs_confidential.pdf",
        file_type="PDF",
    )
    db_session.add(bobs_doc)
    db_session.commit()

    # 1. Alice tries to chat with Bob's document -> 403 Forbidden
    res_alice_unauthorized = client.post(
        "/documents/chat",
        headers={"Authorization": f"Bearer {alice_token}"},
        json={
            "filename": "uuid_bobs_confidential.pdf",
            "question": "Tell me Bob's secrets",
        },
    )
    assert res_alice_unauthorized.status_code == 403
    assert "do not have access" in res_alice_unauthorized.json()["detail"].lower()

    # 2. Bob chats with his own document -> 200 OK
    res_bob_authorized = client.post(
        "/documents/chat",
        headers={"Authorization": f"Bearer {bob_token}"},
        json={
            "filename": "uuid_bobs_confidential.pdf",
            "question": "What is in my document?",
        },
    )
    assert res_bob_authorized.status_code == 200
    assert res_bob_authorized.json()["answer"] == "Secret Answer"

    # Verify chat messages in DB are owned by Bob
    messages = db_session.query(ChatMessage).filter(ChatMessage.document_id == bobs_doc.id).all()
    assert len(messages) == 2
    for msg in messages:
        assert msg.user_id == bob_id


def test_upload_attaches_user_id_when_authenticated(client, db_session):
    """Uploading a document with Bearer token associates Document.user_id."""
    alice_token = client.post("/auth/login", json={"email": "alice@example.com", "password": "Password123!"}).json()["access_token"]
    alice_id = db_session.query(User).filter(User.email == "alice@example.com").first().id

    content = b"%PDF-1.4 Alice's private document"
    files = {"file": ("alice_doc.pdf", content, "application/pdf")}

    response = client.post(
        "/upload/",
        headers={"Authorization": f"Bearer {alice_token}"},
        files=files,
    )
    assert response.status_code == 200
    saved_filename = response.json()["saved_filename"]

    doc = db_session.query(Document).filter(Document.saved_filename == saved_filename).first()
    assert doc is not None
    assert doc.user_id == alice_id


def test_csv_analysis_unchanged_and_unauthenticated(client):
    """CSV analysis continues to work without authentication."""
    csv_content = b"col1,col2\n10,20\n30,40\n"
    files = {"file": ("test_data.csv", csv_content, "text/csv")}

    upload_res = client.post("/upload/", files=files)
    assert upload_res.status_code == 200
    saved_name = upload_res.json()["saved_filename"]

    analyze_res = client.post("/analyze/", json={"saved_filename": saved_name})
    assert analyze_res.status_code == 200
    data = analyze_res.json()
    assert data["shape"]["rows"] == 2
    assert data["shape"]["columns"] == 2
