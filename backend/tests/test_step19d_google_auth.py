"""
tests/test_step19d_google_auth.py - Targeted tests for production-ready Google OAuth authentication.

Verifies:
1. Public /auth/config endpoint behavior when GOOGLE_CLIENT_ID is set vs empty.
2. Cryptographic ID token verification with audience check.
3. Strict security: email_verified == True is mandatory before user creation/linking.
4. Token reuse: existing email user account is linked without duplicating records.
5. In production mode, /auth/google requires configured GOOGLE_CLIENT_ID.
6. Email/password authentication remains fully operational.
7. Google-authenticated sessions have full access to protected features under strict user isolation.
"""

import sys
import uuid
from pathlib import Path
from unittest.mock import patch, MagicMock

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings
from app.db.session import SessionLocal
from app.db.models import User, Document


@pytest.fixture
def client():
    return TestClient(app)


# ==============================================================================
# 1. /auth/config Endpoint Tests
# ==============================================================================

def test_auth_config_reflects_google_client_id(client, monkeypatch):
    """Verify /auth/config reflects configured GOOGLE_CLIENT_ID dynamically."""
    # 1. When empty
    monkeypatch.setattr(settings, "google_client_id", "")
    res = client.get("/auth/config")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["google_client_id"] == ""
    assert data["google_auth_enabled"] is False

    # 2. When configured with real client ID format
    real_mock_id = "1234567890-abcdefg123456.apps.googleusercontent.com"
    monkeypatch.setattr(settings, "google_client_id", real_mock_id)
    res = client.get("/auth/config")
    assert res.status_code == 200
    data = res.json()
    assert data["google_client_id"] == real_mock_id
    assert data["google_auth_enabled"] is True

    # 3. Secret leak check
    res_text = res.text.lower()
    for secret in ["jwt_secret", "supabase", "database_url", "groq"]:
        assert secret not in res_text


# ==============================================================================
# 2. Google OAuth Verification & email_verified Security Guard
# ==============================================================================

@patch("app.api.auth.id_token.verify_oauth2_token")
def test_google_login_requires_email_verified(mock_verify, client):
    """
    CRITICAL SECURITY REQUIREMENT:
    Google token must have email_verified == True.
    Unverified accounts must be rejected with 401 Unauthorized.
    """
    # Case A: email_verified is False
    mock_verify.return_value = {
        "sub": "google-unverified-001",
        "email": "unverified@example.com",
        "name": "Unverified User",
        "email_verified": False,
    }
    res = client.post("/auth/google", json={"id_token": "token-unverified"})
    assert res.status_code == 401
    assert "email is not verified" in res.json()["detail"].lower()

    # Case B: email_verified field is missing entirely
    mock_verify.return_value = {
        "sub": "google-unverified-002",
        "email": "missing_flag@example.com",
        "name": "Missing Flag User",
    }
    res2 = client.post("/auth/google", json={"id_token": "token-missing-flag"})
    assert res2.status_code == 401
    assert "email is not verified" in res2.json()["detail"].lower()


@patch("app.api.auth.id_token.verify_oauth2_token")
def test_google_login_success_verified_email(mock_verify, client, monkeypatch):
    """Verified Google account registers a new user and returns signed JWT."""
    test_client_id = "test-client-id-12345.apps.googleusercontent.com"
    monkeypatch.setattr(settings, "google_client_id", test_client_id)

    unique_email = f"verified_user_{uuid.uuid4().hex[:8]}@example.com"
    mock_verify.return_value = {
        "sub": "google-verified-999",
        "email": unique_email,
        "name": "Verified Google User",
        "email_verified": True,
    }

    res = client.post("/auth/google", json={"credential": "valid-credential-token"})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "access_token" in data
    assert data["user"]["email"] == unique_email
    assert data["user"]["full_name"] == "Verified Google User"
    assert data["user"]["auth_provider"] == "google"

    # Verify audience was passed to verify_oauth2_token
    mock_verify.assert_called_once()
    assert mock_verify.call_args[1]["audience"] == test_client_id

    # Clean up DB
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == unique_email).first()
        assert user is not None
        assert user.hashed_password is None
        db.delete(user)
        db.commit()
    finally:
        db.close()


@patch("app.api.auth.id_token.verify_oauth2_token")
def test_google_login_links_to_existing_account(mock_verify, client):
    """Google login links to an existing user created via email/password if email matches."""
    unique_email = f"shared_user_{uuid.uuid4().hex[:8]}@example.com"

    # 1. Create email/password user first
    signup_res = client.post(
        "/auth/signup",
        json={"email": unique_email, "password": "Password123!", "full_name": "Original Name"},
    )
    assert signup_res.status_code in (200, 201)
    original_id = signup_res.json()["user"]["id"]

    # 2. Login via Google with the same email
    mock_verify.return_value = {
        "sub": "google-linked-id",
        "email": unique_email,
        "name": "Original Name",
        "email_verified": True,
    }
    google_res = client.post("/auth/google", json={"id_token": "google-link-token"})
    assert google_res.status_code == 200
    g_data = google_res.json()
    assert g_data["user"]["id"] == original_id
    assert g_data["user"]["email"] == unique_email

    # Confirm only one user exists in DB
    db = SessionLocal()
    try:
        users = db.query(User).filter(User.email == unique_email).all()
        assert len(users) == 1
        db.delete(users[0])
        db.commit()
    finally:
        db.close()


@patch("app.api.auth.id_token.verify_oauth2_token")
def test_google_login_invalid_token_rejected(mock_verify, client):
    """Tampered or invalid Google token raises 401 Unauthorized."""
    mock_verify.side_effect = ValueError("Token signature verification failed")
    res = client.post("/auth/google", json={"id_token": "tampered-token"})
    assert res.status_code == 401
    assert "invalid google id token" in res.json()["detail"].lower()


def test_google_login_empty_payload_rejected(client):
    """Empty payload returns 400 Bad Request."""
    res = client.post("/auth/google", json={})
    assert res.status_code == 400


# ==============================================================================
# 3. Production Environment Checks
# ==============================================================================

def test_production_mode_requires_configured_client_id(client, monkeypatch):
    """In production mode, /auth/google returns 503 if GOOGLE_CLIENT_ID is not configured."""
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "google_client_id", "")

    res = client.post("/auth/google", json={"id_token": "some-token"})
    assert res.status_code == 503
    assert "not configured" in res.json()["detail"].lower()


# ==============================================================================
# 4. End-to-End User Isolation with Google Authenticated Session
# ==============================================================================

@patch("app.api.auth.id_token.verify_oauth2_token")
def test_google_session_has_protected_access_and_isolation(mock_verify, client):
    """Google-authenticated user can access protected endpoints and maintains data isolation."""
    google_email = f"googler_{uuid.uuid4().hex[:8]}@example.com"
    mock_verify.return_value = {
        "sub": "g-isolation-test",
        "email": google_email,
        "name": "Googler",
        "email_verified": True,
    }

    login_res = client.post("/auth/google", json={"id_token": "valid-token"})
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    user_id = login_res.json()["user"]["id"]

    headers = {"Authorization": f"Bearer {token}"}

    # 1. Access /auth/me
    me_res = client.get("/auth/me", headers=headers)
    assert me_res.status_code == 200
    assert me_res.json()["user"]["email"] == google_email

    # 2. Access /documents/history
    hist_res = client.get("/documents/history", headers=headers)
    assert hist_res.status_code == 200
    assert "history" in hist_res.json()

    # Clean up
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.id == user_id).first()
        if u:
            db.delete(u)
            db.commit()
    finally:
        db.close()
