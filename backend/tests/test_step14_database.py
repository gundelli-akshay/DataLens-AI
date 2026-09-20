import sys
from pathlib import Path
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db.session import Base, get_db
from app.db.models import Document, ChatMessage, User
from app.core.auth import get_current_user

# Use in-memory SQLite for tests
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="module")
def db_session():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)

@pytest.fixture(scope="module")
def client(db_session):
    test_user = User(id=1, email="test14@example.com", full_name="Test 14 User", auth_provider="email")
    db_session.add(test_user)
    db_session.commit()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: test_user
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

def test_upload_document_creates_db_record(client, db_session):
    # Upload a dummy PDF
    content = b"%PDF-1.4 dummy content"
    files = {"file": ("dummy.pdf", content, "application/pdf")}
    
    response = client.post("/upload/", files=files)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    
    saved_filename = data["saved_filename"]
    
    # Verify in DB
    doc = db_session.query(Document).filter(Document.saved_filename == saved_filename).first()
    assert doc is not None
    assert doc.original_filename == "dummy.pdf"
    assert doc.file_type == "PDF"

def test_chat_creates_chat_messages(client, db_session, monkeypatch):
    # First, mock the RAG parts to avoid actual Groq / embedding calls
    from app.api import documents
    monkeypatch.setattr(documents, "retrieve_relevant_chunks", lambda **kwargs: [{"text": "dummy chunk", "metadata": {"page_number": 1}}])
    monkeypatch.setattr(documents, "generate_rag_answer", lambda **kwargs: {"answer": "Mocked answer", "sources": ["Page 1"], "model": "mock"})
    
    # We need a document in the DB
    doc = Document(
        original_filename="chat_test.pdf",
        saved_filename="uuid_chat_test.pdf",
        file_type="PDF"
    )
    db_session.add(doc)
    db_session.commit()
    
    # Send chat request
    payload = {
        "question": "What is the meaning of life?",
        "saved_filename": "uuid_chat_test.pdf"
    }
    
    response = client.post("/documents/chat", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["answer"] == "Mocked answer"
    
    # Verify ChatMessages in DB
    messages = db_session.query(ChatMessage).filter(ChatMessage.document_id == doc.id).order_by(ChatMessage.id).all()
    assert len(messages) == 2
    
    # User message
    assert messages[0].role == "user"
    assert messages[0].content == "What is the meaning of life?"
    
    # Assistant message
    assert messages[1].role == "assistant"
    assert messages[1].content == "Mocked answer"
    assert "Page 1" in messages[1].sources
