import sys
import uuid
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
from app.core.auth import create_access_token

# Isolated in-memory SQLite engine for tests
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
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(scope="module")
def users(db_session):
    u1 = User(
        email="user1_dashboard@example.com",
        full_name="Alice User",
        auth_provider="email",
    )
    u2 = User(
        email="user2_dashboard@example.com",
        full_name="Bob User",
        auth_provider="google",
    )
    db_session.add_all([u1, u2])
    db_session.commit()
    db_session.refresh(u1)
    db_session.refresh(u2)

    token1 = create_access_token({"sub": str(u1.id), "email": u1.email})
    token2 = create_access_token({"sub": str(u2.id), "email": u2.email})

    return {
        "user1": u1,
        "token1": token1,
        "user2": u2,
        "token2": token2,
    }


def test_unauthenticated_access_is_rejected(client):
    """Verify all dashboard and history endpoints strictly require authentication."""
    r_docs = client.get("/documents/my-documents")
    assert r_docs.status_code == 401

    r_history = client.get("/documents/chat-history")
    assert r_history.status_code == 401

    r_msgs = client.get("/documents/messages?saved_filename=some_doc.pdf")
    assert r_msgs.status_code == 401

    r_me = client.get("/auth/me")
    assert r_me.status_code == 401


def test_authenticated_user_can_access_own_documents_and_history(client, db_session, users):
    """Verify an authenticated user accesses their own profile, documents, and chat history."""
    u1 = users["user1"]
    headers1 = {"Authorization": f"Bearer {users['token1']}"}

    # Verify Profile contains created_at
    r_me = client.get("/auth/me", headers=headers1)
    assert r_me.status_code == 200
    me_data = r_me.json()
    assert me_data["user"]["email"] == "user1_dashboard@example.com"
    assert me_data["user"]["full_name"] == "Alice User"
    assert "created_at" in me_data["user"]
    assert me_data["user"]["created_at"] is not None

    # Create document for user1
    sfn1 = f"{uuid.uuid4().hex[:12]}_report.pdf"
    doc1 = Document(
        user_id=u1.id,
        original_filename="report.pdf",
        saved_filename=sfn1,
        file_type="PDF",
        file_size_bytes=1024,
    )
    db_session.add(doc1)
    db_session.commit()
    db_session.refresh(doc1)

    # Create chat messages for user1
    q_msg = ChatMessage(
        document_id=doc1.id,
        user_id=u1.id,
        role="user",
        content="What is the summary of this report?",
    )
    db_session.add(q_msg)
    db_session.flush()

    a_msg = ChatMessage(
        document_id=doc1.id,
        user_id=u1.id,
        role="assistant",
        content="This report summarizes financial quarters.",
        sources=["Page 1"],
    )
    db_session.add(a_msg)
    db_session.commit()

    # User 1 fetches documents
    r_docs = client.get("/documents/my-documents", headers=headers1)
    assert r_docs.status_code == 200
    docs_data = r_docs.json()
    assert docs_data["status"] == "success"
    assert any(d["saved_filename"] == sfn1 for d in docs_data["documents"])

    # User 1 fetches chat history
    r_hist = client.get("/documents/chat-history", headers=headers1)
    assert r_hist.status_code == 200
    hist_data = r_hist.json()
    assert hist_data["status"] == "success"
    assert hist_data["count"] >= 1
    found_item = next(h for h in hist_data["history"] if h["document_id"] == doc1.id)
    assert found_item["question"] == "What is the summary of this report?"
    assert "financial quarters" in found_item["answer"]
    assert found_item["timestamp"] is not None

    # User 1 fetches document messages
    r_msgs = client.get(f"/documents/messages?saved_filename={sfn1}", headers=headers1)
    assert r_msgs.status_code == 200
    msgs_data = r_msgs.json()
    assert len(msgs_data["messages"]) == 2
    assert msgs_data["messages"][0]["role"] == "user"
    assert msgs_data["messages"][1]["role"] == "assistant"


def test_cross_user_isolation_blocks_access(client, db_session, users):
    """Verify User B cannot access User A's documents, messages, or chat history."""
    u1 = users["user1"]
    u2 = users["user2"]
    headers2 = {"Authorization": f"Bearer {users['token2']}"}

    # Document owned by User A
    sfn_alice = f"{uuid.uuid4().hex[:12]}_alice_private.pdf"
    doc_alice = Document(
        user_id=u1.id,
        original_filename="alice_private.pdf",
        saved_filename=sfn_alice,
        file_type="PDF",
        file_size_bytes=2048,
    )
    db_session.add(doc_alice)
    db_session.commit()
    db_session.refresh(doc_alice)

    msg_alice = ChatMessage(
        document_id=doc_alice.id,
        user_id=u1.id,
        role="user",
        content="Alice secret confidential question",
    )
    db_session.add(msg_alice)
    db_session.commit()

    # User B requests my-documents -> should NOT include Alice's document
    r_docs = client.get("/documents/my-documents", headers=headers2)
    assert r_docs.status_code == 200
    doc_names = [d["saved_filename"] for d in r_docs.json()["documents"]]
    assert sfn_alice not in doc_names

    # User B requests chat-history -> should NOT include Alice's messages
    r_hist = client.get("/documents/chat-history", headers=headers2)
    assert r_hist.status_code == 200
    for item in r_hist.json()["history"]:
        assert item["document_id"] != doc_alice.id
        assert "confidential" not in item["question"]

    # User B attempts to directly access Alice's document messages -> 403 Forbidden
    r_msgs = client.get(f"/documents/messages?saved_filename={sfn_alice}", headers=headers2)
    assert r_msgs.status_code == 403
    assert "access" in r_msgs.json()["detail"].lower()


def test_existing_chat_persistence_continues_to_work(client, db_session, users, monkeypatch):
    """Verify chat endpoint still persists messages in DB and updates chat history."""
    from app.api import documents
    monkeypatch.setattr(
        documents,
        "retrieve_relevant_chunks",
        lambda **kwargs: [{"text": "Doc chunk context", "metadata": {"page_number": 1}}],
    )
    monkeypatch.setattr(
        documents,
        "generate_rag_answer",
        lambda **kwargs: {
            "answer": "Grounded answer from RAG",
            "sources": ["Page 1"],
            "model": "llama3-70b-8192",
        },
    )

    u1 = users["user1"]
    headers1 = {"Authorization": f"Bearer {users['token1']}"}

    sfn = f"{uuid.uuid4().hex[:12]}_chat_persist.docx"
    doc = Document(
        user_id=u1.id,
        original_filename="chat_persist.docx",
        saved_filename=sfn,
        file_type="DOCX",
        file_size_bytes=4096,
    )
    db_session.add(doc)
    db_session.commit()

    payload = {
        "question": "What is the key insight?",
        "saved_filename": sfn,
    }

    r_chat = client.post("/documents/chat", json=payload, headers=headers1)
    assert r_chat.status_code == 200
    assert r_chat.json()["answer"] == "Grounded answer from RAG"

    # Verify message was saved and appears in chat-history
    r_hist = client.get("/documents/chat-history", headers=headers1)
    assert r_hist.status_code == 200
    found = next((h for h in r_hist.json()["history"] if h["question"] == "What is the key insight?"), None)
    assert found is not None
    assert found["answer"] == "Grounded answer from RAG"


def test_chat_history_groups_by_document_and_restores_all_messages(client, db_session, users):
    """Verify that multiple questions for a single document collapse into ONE history entry,
    and reopening that entry provides all historical messages in chronological order."""
    u1 = users["user1"]
    headers1 = {"Authorization": f"Bearer {users['token1']}"}

    # Create a document for user1
    sfn_multi = f"{uuid.uuid4().hex[:12]}_multi_q.pdf"
    doc_multi = Document(
        user_id=u1.id,
        original_filename="multi_questions_doc.pdf",
        saved_filename=sfn_multi,
        file_type="PDF",
        file_size_bytes=5000,
    )
    db_session.add(doc_multi)
    db_session.commit()
    db_session.refresh(doc_multi)

    # Add 5 questions and 5 answers for doc_multi
    for i in range(1, 6):
        q = ChatMessage(
            document_id=doc_multi.id,
            user_id=u1.id,
            role="user",
            content=f"Question {i} about multi_q?",
        )
        db_session.add(q)
        db_session.flush()

        a = ChatMessage(
            document_id=doc_multi.id,
            user_id=u1.id,
            role="assistant",
            content=f"Answer {i} for question {i}.",
            sources=[f"Page {i}"],
        )
        db_session.add(a)
        db_session.commit()

    # Query chat-history
    r_hist = client.get("/documents/chat-history", headers=headers1)
    assert r_hist.status_code == 200
    hist = r_hist.json()["history"]

    # Filter to items for this document
    doc_entries = [h for h in hist if h["document_id"] == doc_multi.id]
    # REQUIREMENT: Exactly ONE history entry per document/conversation!
    assert len(doc_entries) == 1
    entry = doc_entries[0]

    assert entry["document_name"] == "multi_questions_doc.pdf"
    assert entry["saved_filename"] == sfn_multi
    assert entry["file_type"] == "PDF"
    assert entry["question_count"] == 5
    assert entry["message_count"] == 10
    # Shows the latest question and answer preview
    assert entry["question"] == "Question 5 about multi_q?"
    assert "Answer 5" in entry["answer"]
    assert entry["timestamp"] is not None

    # REQUIREMENT: Opening chat must restore all previous questions and answers in chronological order
    r_msgs = client.get(f"/documents/messages?saved_filename={sfn_multi}", headers=headers1)
    assert r_msgs.status_code == 200
    msgs = r_msgs.json()["messages"]
    assert len(msgs) == 10

    # Verify chronological sequence
    for i in range(1, 6):
        user_msg = msgs[(i - 1) * 2]
        asst_msg = msgs[(i - 1) * 2 + 1]
        assert user_msg["role"] == "user"
        assert user_msg["content"] == f"Question {i} about multi_q?"
        assert asst_msg["role"] == "assistant"
        assert asst_msg["content"] == f"Answer {i} for question {i}."


def test_app_startup_session_preserved_and_database_data_retained(client, db_session, users):
    """Verify that on app startup/reload:
    1. The authenticated user session is active and valid.
    2. Historical documents, chat messages, and database records remain fully preserved.
    3. No workspace state leaks into or deletes existing persisted data."""
    u1 = users["user1"]
    headers1 = {"Authorization": f"Bearer {users['token1']}"}

    # Simulate app startup / reload: verify session is immediately valid via /auth/me
    r_me = client.get("/auth/me", headers=headers1)
    assert r_me.status_code == 200
    me = r_me.json()["user"]
    assert me["email"] == u1.email
    assert me["full_name"] == u1.full_name

    # Verify that existing documents are completely preserved
    r_docs = client.get("/documents/my-documents", headers=headers1)
    assert r_docs.status_code == 200
    docs = r_docs.json()["documents"]
    assert len(docs) >= 1

    # Verify that existing chat history is completely preserved
    r_hist = client.get("/documents/chat-history", headers=headers1)
    assert r_hist.status_code == 200
    history = r_hist.json()["history"]
    assert len(history) >= 1

    # Ensure no database records were removed
    db_doc_count = db_session.query(Document).filter(Document.user_id == u1.id).count()
    db_msg_count = db_session.query(ChatMessage).filter(ChatMessage.user_id == u1.id).count()
    assert db_doc_count >= 1
    assert db_msg_count >= 1


def test_unified_history_all_four_file_types_and_user_isolation(client, db_session, users):
    """
    Test the single unified History endpoint (/documents/history):
    1. Unauthenticated request rejected with 401.
    2. Combines all four file types: PDF, DOCX, CSV, XLSX.
    3. Verifies PDF/DOCX show filename, upload/last activity date, question count, latest Q&A preview, open_chat action.
    4. Verifies CSV/XLSX show filename, upload date, AI Insights availability, open_analysis action.
    5. Strict user isolation: User 2 sees none of User 1's history items.
    """
    u1 = users["user1"]
    u2 = users["user2"]
    headers1 = {"Authorization": f"Bearer {users['token1']}"}
    headers2 = {"Authorization": f"Bearer {users['token2']}"}

    # 1. Unauthenticated check
    r_unauth = client.get("/documents/history")
    assert r_unauth.status_code == 401

    # 2. Setup all four file types for User 1
    # PDF with chat
    sfn_pdf = f"{uuid.uuid4().hex[:12]}_research.pdf"
    doc_pdf = Document(
        user_id=u1.id,
        original_filename="research.pdf",
        saved_filename=sfn_pdf,
        file_type="PDF",
        file_size_bytes=12000,
    )
    # DOCX without chat
    sfn_docx = f"{uuid.uuid4().hex[:12]}_contract.docx"
    doc_docx = Document(
        user_id=u1.id,
        original_filename="contract.docx",
        saved_filename=sfn_docx,
        file_type="DOCX",
        file_size_bytes=8500,
    )
    # CSV with AI Insights saved
    sfn_csv = f"{uuid.uuid4().hex[:12]}_sales.csv"
    doc_csv = Document(
        user_id=u1.id,
        original_filename="sales.csv",
        saved_filename=sfn_csv,
        file_type="CSV",
        file_size_bytes=3400,
        ai_insights="Sales increased by 15% across Q3.",
    )
    # XLSX without AI Insights
    sfn_xlsx = f"{uuid.uuid4().hex[:12]}_budget.xlsx"
    doc_xlsx = Document(
        user_id=u1.id,
        original_filename="budget.xlsx",
        saved_filename=sfn_xlsx,
        file_type="XLSX",
        file_size_bytes=15000,
        ai_insights=None,
    )
    db_session.add_all([doc_pdf, doc_docx, doc_csv, doc_xlsx])
    db_session.commit()
    db_session.refresh(doc_pdf)

    # Add chat to PDF
    q_pdf = ChatMessage(
        document_id=doc_pdf.id,
        user_id=u1.id,
        role="user",
        content="What is the primary methodology?",
    )
    db_session.add(q_pdf)
    db_session.flush()

    a_pdf = ChatMessage(
        document_id=doc_pdf.id,
        user_id=u1.id,
        role="assistant",
        content="The methodology uses empirical randomized trials.",
        sources=["Section 2.1"],
    )
    db_session.add(a_pdf)
    db_session.commit()

    # 3. Query /documents/history as User 1
    r_hist = client.get("/documents/history", headers=headers1)
    assert r_hist.status_code == 200
    data = r_hist.json()
    assert data["status"] == "success"
    history = data["history"]
    saved_names = [h["saved_filename"] for h in history]

    assert sfn_pdf in saved_names
    assert sfn_docx in saved_names
    assert sfn_csv in saved_names
    assert sfn_xlsx in saved_names

    # Check PDF item
    pdf_item = next(h for h in history if h["saved_filename"] == sfn_pdf)
    assert pdf_item["filename"] == "research.pdf"
    assert pdf_item["file_type"] == "PDF"
    assert pdf_item["question_count"] == 1
    assert pdf_item["has_chat"] is True
    assert pdf_item["latest_question"] == "What is the primary methodology?"
    assert "randomized trials" in pdf_item["latest_answer"]
    assert pdf_item["action"] == "open_chat"
    assert pdf_item["uploaded_at"] is not None

    # Check DOCX item (no chat)
    docx_item = next(h for h in history if h["saved_filename"] == sfn_docx)
    assert docx_item["filename"] == "contract.docx"
    assert docx_item["file_type"] == "DOCX"
    assert docx_item["question_count"] == 0
    assert docx_item["has_chat"] is False
    assert docx_item["latest_question"] is None
    assert docx_item["action"] == "open_chat"

    # Check CSV item (with AI Insights)
    csv_item = next(h for h in history if h["saved_filename"] == sfn_csv)
    assert csv_item["filename"] == "sales.csv"
    assert csv_item["file_type"] == "CSV"
    assert csv_item["has_insights"] is True
    assert csv_item["has_analysis"] is True
    assert csv_item["action"] == "open_analysis"

    # Check XLSX item (without AI Insights)
    xlsx_item = next(h for h in history if h["saved_filename"] == sfn_xlsx)
    assert xlsx_item["filename"] == "budget.xlsx"
    assert xlsx_item["file_type"] == "XLSX"
    assert xlsx_item["has_insights"] is False
    assert xlsx_item["has_analysis"] is True
    assert xlsx_item["action"] == "open_analysis"

    # 4. Strict user isolation: User 2 should NOT see any of User 1's items
    r_user2 = client.get("/documents/history", headers=headers2)
    assert r_user2.status_code == 200
    user2_items = r_user2.json()["history"]
    user2_saved_names = [h["saved_filename"] for h in user2_items]

    assert sfn_pdf not in user2_saved_names
    assert sfn_docx not in user2_saved_names
    assert sfn_csv not in user2_saved_names
    assert sfn_xlsx not in user2_saved_names


def test_reopening_csv_xlsx_restores_saved_ai_insights_without_groq_call(client, db_session, users, tmp_path, monkeypatch):
    """
    Verify that reopening an existing CSV or XLSX analysis restores the saved AI Insights
    and does NOT trigger any new Groq LLM API request.
    """
    from app.core.config import settings

    u1 = users["user1"]
    headers1 = {"Authorization": f"Bearer {users['token1']}"}

    # Create dummy CSV on disk in upload directory
    csv_content = b"colA,colB\n1,10\n2,20\n3,30\n"
    sfn_reopen = f"{uuid.uuid4().hex[:12]}_reopen_test.csv"
    file_on_disk = settings.upload_dir_path / sfn_reopen
    file_on_disk.write_bytes(csv_content)

    try:
        # Create Document with pre-saved AI Insights
        saved_insights_text = "Existing cached AI insights for reopen test."
        doc = Document(
            user_id=u1.id,
            original_filename="reopen_test.csv",
            saved_filename=sfn_reopen,
            file_type="CSV",
            file_size_bytes=len(csv_content),
            ai_insights=saved_insights_text,
        )
        db_session.add(doc)
        db_session.commit()

        # Monkeypatch generate_insights to fail if called
        def fail_if_groq_called(*args, **kwargs):
            raise AssertionError("Groq generate_insights should NOT be called when reopening an existing analysis!")

        from app.api import insights
        monkeypatch.setattr(insights, "generate_insights", fail_if_groq_called)

        # Call POST /analyze/ to reopen analysis
        r_analyze = client.post("/analyze/", json={"saved_filename": sfn_reopen}, headers=headers1)
        assert r_analyze.status_code == 200
        data = r_analyze.json()
        assert data["status"] == "success"
        # Verify saved AI Insights were restored from DB
        assert data.get("ai_insights") == saved_insights_text

    finally:
        if file_on_disk.exists():
            file_on_disk.unlink()


def test_delete_document_success_pdf_and_cleanup(client, db_session, users):
    """
    Verify successful deletion of an authenticated user's own PDF document:
    - Removes Document record from database
    - Removes associated ChatMessage records
    - Cleans up in-memory vector index chunks
    - Removes the uploaded file from disk
    - Deleted item immediately disappears from /documents/history
    """
    from app.core.config import settings
    from app.services.rag import vector_index

    u1 = users["user1"]
    headers1 = {"Authorization": f"Bearer {users['token1']}"}

    # Create dummy PDF file on disk
    sfn_pdf = f"{uuid.uuid4().hex[:12]}_delete_target.pdf"
    file_path = settings.upload_dir_path / sfn_pdf
    file_path.write_bytes(b"%PDF-1.4 dummy pdf content for delete test")

    try:
        # Create Document record
        doc_pdf = Document(
            user_id=u1.id,
            original_filename="delete_target.pdf",
            saved_filename=sfn_pdf,
            file_type="PDF",
            file_size_bytes=len(file_path.read_bytes()),
        )
        db_session.add(doc_pdf)
        db_session.commit()
        db_session.refresh(doc_pdf)
        doc_id = doc_pdf.id

        # Add ChatMessage records
        q_msg = ChatMessage(
            document_id=doc_id,
            user_id=u1.id,
            role="user",
            content="Question before delete?",
        )
        a_msg = ChatMessage(
            document_id=doc_id,
            user_id=u1.id,
            role="assistant",
            content="Answer before delete.",
            sources=["Page 1"],
        )
        db_session.add_all([q_msg, a_msg])
        db_session.commit()

        # Add chunks to vector_index
        dummy_chunk = {
            "chunk_id": f"{sfn_pdf}_c0",
            "text": "dummy text",
            "filename": "delete_target.pdf",
            "saved_filename": sfn_pdf,
            "file_type": "PDF",
            "user_id": u1.id,
        }
        import numpy as np
        vector_index.add_documents([dummy_chunk], np.zeros((1, 384), dtype=np.float32))

        # Verify it appears in /documents/history before delete
        r_hist_before = client.get("/documents/history", headers=headers1)
        assert r_hist_before.status_code == 200
        assert any(h["id"] == doc_id for h in r_hist_before.json()["history"])

        # Execute DELETE /documents/{document_id}
        r_del = client.delete(f"/documents/{doc_id}", headers=headers1)
        assert r_del.status_code == 200
        assert r_del.json()["status"] == "success"
        assert r_del.json()["deleted_id"] == doc_id

        # Verify Document record is deleted
        assert db_session.query(Document).filter(Document.id == doc_id).first() is None

        # Verify ChatMessages are deleted
        assert db_session.query(ChatMessage).filter(ChatMessage.document_id == doc_id).count() == 0

        # Verify vector_index chunks are removed
        user_chunks = [c for c in vector_index.chunks if c.get("saved_filename") == sfn_pdf]
        assert len(user_chunks) == 0

        # Verify file is deleted from disk
        assert not file_path.exists()

        # Verify it no longer appears in /documents/history
        r_hist_after = client.get("/documents/history", headers=headers1)
        assert r_hist_after.status_code == 200
        assert not any(h["id"] == doc_id for h in r_hist_after.json()["history"])

    finally:
        if file_path.exists():
            file_path.unlink()


def test_delete_document_success_csv_and_cleanup(client, db_session, users):
    """
    Verify successful deletion of an authenticated user's own CSV document:
    - Removes Document record
    - Removes saved AI insights
    - Removes uploaded file from disk
    - Deleted item no longer appears in /documents/history
    """
    from app.core.config import settings

    u1 = users["user1"]
    headers1 = {"Authorization": f"Bearer {users['token1']}"}

    # Create dummy CSV file on disk
    sfn_csv = f"{uuid.uuid4().hex[:12]}_delete_target.csv"
    file_path = settings.upload_dir_path / sfn_csv
    file_path.write_bytes(b"a,b\n1,2\n")

    try:
        # Create Document record with saved AI insights
        doc_csv = Document(
            user_id=u1.id,
            original_filename="delete_target.csv",
            saved_filename=sfn_csv,
            file_type="CSV",
            file_size_bytes=len(file_path.read_bytes()),
            ai_insights="Insights to be deleted along with document.",
        )
        db_session.add(doc_csv)
        db_session.commit()
        db_session.refresh(doc_csv)
        doc_id = doc_csv.id

        # Verify it appears in /documents/history before delete
        r_hist_before = client.get("/documents/history", headers=headers1)
        assert r_hist_before.status_code == 200
        assert any(h["id"] == doc_id for h in r_hist_before.json()["history"])

        # Execute DELETE /documents/{document_id}
        r_del = client.delete(f"/documents/{doc_id}", headers=headers1)
        assert r_del.status_code == 200
        assert r_del.json()["status"] == "success"

        # Verify Document record is deleted (which purges saved AI insights)
        assert db_session.query(Document).filter(Document.id == doc_id).first() is None

        # Verify file is deleted from disk
        assert not file_path.exists()

        # Verify it no longer appears in /documents/history
        r_hist_after = client.get("/documents/history", headers=headers1)
        assert r_hist_after.status_code == 200
        assert not any(h["id"] == doc_id for h in r_hist_after.json()["history"])

    finally:
        if file_path.exists():
            file_path.unlink()


def test_cross_user_delete_attempt_is_strictly_blocked(client, db_session, users):
    """
    Verify security:
    - User 2 cannot delete User 1's document (returns 403 Forbidden).
    - User 1's document, file, messages, and insights remain completely intact.
    """
    u1 = users["user1"]
    u2 = users["user2"]
    headers2 = {"Authorization": f"Bearer {users['token2']}"}

    doc_victim = Document(
        user_id=u1.id,
        original_filename="victim_doc.docx",
        saved_filename=f"{uuid.uuid4().hex[:12]}_victim.docx",
        file_type="DOCX",
        file_size_bytes=2048,
    )
    db_session.add(doc_victim)
    db_session.commit()
    db_session.refresh(doc_victim)
    victim_id = doc_victim.id

    # User 2 attempts to delete User 1's document -> 403
    r_del = client.delete(f"/documents/{victim_id}", headers=headers2)
    assert r_del.status_code == 403
    assert "permission" in r_del.json()["detail"].lower()

    # Verify User 1's document is still in database
    doc_check = db_session.query(Document).filter(Document.id == victim_id).first()
    assert doc_check is not None
    assert doc_check.user_id == u1.id
