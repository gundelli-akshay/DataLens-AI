from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship

from app.db.session import Base


def utc_now():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=True)  # Null for Google OAuth users
    full_name = Column(String, nullable=True)
    auth_provider = Column(String, default="email")  # "email" or "google"
    created_at = Column(DateTime, default=utc_now)

    documents = relationship("Document", back_populates="user", cascade="all, delete-orphan")
    chat_messages = relationship("ChatMessage", back_populates="user", cascade="all, delete-orphan")


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    original_filename = Column(String, index=True)
    saved_filename = Column(String, unique=True, index=True)
    file_type = Column(String)
    file_size_bytes = Column(Integer, nullable=True)
    uploaded_at = Column(DateTime, default=utc_now)
    ai_insights = Column(Text, nullable=True)

    user = relationship("User", back_populates="documents")
    chat_messages = relationship("ChatMessage", back_populates="document", cascade="all, delete-orphan")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    role = Column(String, index=True)
    content = Column(Text)
    sources = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=utc_now)

    document = relationship("Document", back_populates="chat_messages")
    user = relationship("User", back_populates="chat_messages")
