"""
app/api/auth.py - Authentication Endpoints.

Routes:
- POST /auth/signup: Register with email and password
- POST /auth/login: Authenticate with email and password
- POST /auth/google: Authenticate or sign up using Google ID token
- GET /auth/me: Retrieve current authenticated user profile
"""

import logging
import re
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

from app.core.config import settings
from app.core.auth import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
)
from app.db.models import User
from app.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


class SignupRequest(BaseModel):
    email: str
    password: str = Field(..., min_length=6, max_length=128, description="Password must be between 6 and 128 characters")
    full_name: Optional[str] = Field(None, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email_format(cls, v: str) -> str:
        clean = v.strip().lower()
        if len(clean) > 254:
            raise ValueError("Email exceeds maximum allowed length")
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", clean):
            raise ValueError("Invalid email format")
        return clean


class LoginRequest(BaseModel):
    email: str
    password: str = Field(..., max_length=128)


class GoogleLoginRequest(BaseModel):
    id_token: Optional[str] = None
    credential: Optional[str] = None


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: Optional[str] = None
    auth_provider: str
    created_at: Optional[str] = None


class AuthTokenResponse(BaseModel):
    status: str = "success"
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


@router.post("/signup", response_model=AuthTokenResponse, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, db: Session = Depends(get_db)):
    """Register a new user with email and securely hashed password."""
    email = payload.email.lower().strip()

    # Check if email is already registered
    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email already exists. Please log in.",
        )

    # Hash password with bcrypt
    hashed = hash_password(payload.password)

    new_user = User(
        email=email,
        hashed_password=hashed,
        full_name=payload.full_name.strip() if payload.full_name else None,
        auth_provider="email",
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Issue JWT token
    token = create_access_token({"sub": str(new_user.id), "email": new_user.email})

    return {
        "status": "success",
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": new_user.id,
            "email": new_user.email,
            "full_name": new_user.full_name,
            "auth_provider": new_user.auth_provider,
        },
    }


@router.post("/login", response_model=AuthTokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate with email and password."""
    email = payload.email.lower().strip()

    user = db.query(User).filter(User.email == email).first()
    if not user or not user.hashed_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    if not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    token = create_access_token({"sub": str(user.id), "email": user.email})

    return {
        "status": "success",
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "auth_provider": user.auth_provider,
        },
    }


@router.post("/google", response_model=AuthTokenResponse)
def google_login(payload: GoogleLoginRequest, db: Session = Depends(get_db)):
    """
    Authenticate or register a user using a Google Identity Services ID token.
    If the email matches an existing user, reuses that User instead of creating a duplicate.
    Validates token audience against configured Google Client ID.
    """
    token_str = payload.id_token or payload.credential
    if not token_str or not token_str.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google ID token (id_token or credential) is required.",
        )

    configured_audience = settings.google_client_id.strip() if settings.google_client_id else None

    # In production, require Google Client ID configuration
    if settings.is_production and not configured_audience:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Sign-In is not configured on this server.",
        )

    try:
        idinfo = id_token.verify_oauth2_token(
            token_str, google_requests.Request(), audience=configured_audience
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid Google ID token: {str(exc)}",
        )

    # Mandatory security check: require verified email address from Google
    if not idinfo.get("email_verified", False):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google account email is not verified.",
        )

    email = idinfo.get("email")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google token did not contain a valid email address.",
        )
    email = email.lower().strip()
    name = idinfo.get("name")

    # Check for existing user (reuse existing User if matches email)
    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(
            email=email,
            hashed_password=None,
            full_name=name,
            auth_provider="google",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        # If user exists but had no full_name, update with Google name if provided
        if not user.full_name and name:
            user.full_name = name
            db.commit()
            db.refresh(user)

    token = create_access_token({"sub": str(user.id), "email": user.email})

    return {
        "status": "success",
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "auth_provider": user.auth_provider,
        },
    }




class AuthConfigResponse(BaseModel):
    status: str = "success"
    google_client_id: str = ""
    google_auth_enabled: bool = False


@router.get("/config", response_model=AuthConfigResponse)
def get_auth_config():
    """
    Return public authentication configuration.
    Allows frontend clients to configure Google Identity Services dynamically
    without baking client IDs into static production bundles.
    Never exposes secrets or credentials.
    """
    client_id = settings.google_client_id.strip() if settings.google_client_id else ""
    return {
        "status": "success",
        "google_client_id": client_id,
        "google_auth_enabled": bool(client_id),
    }

@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    """Return the profile of the currently authenticated user."""
    return {
        "status": "success",
        "user": {
            "id": current_user.id,
            "email": current_user.email,
            "full_name": current_user.full_name,
            "auth_provider": current_user.auth_provider,
            "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
        },
    }
