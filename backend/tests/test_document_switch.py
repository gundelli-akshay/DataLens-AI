"""
tests/test_document_switch.py - Tests for switching documents, clearing chat UI state,
and ensuring previous chat history in the database is preserved and isolated.

Covers:
1. Switching from Document A to Document B initializes fresh chat state.
2. Previous chat history for Document A remains intact in the database.
3. No leakage of messages, filenames, or sources between Document A and Document B.
4. Clearing active client state does not delete database chat messages.
"""

from pathlib import Path
import sys
import unittest
import uuid
from unittest.mock import MagicMock, patch

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings
from app.core.auth import create_access_token, hash_password
from app.db.models import Document, ChatMessage, User
from app.db.session import SessionLocal
from app.services.rag import index_document_data, vector_index


class TestDocumentSwitchAndPersistence(unittest.TestCase):
    """Integration tests verifying document switching, chat isolation, and DB persistence."""

    def setUp(self):
        self.client = TestClient(app)
        self.db = SessionLocal()

        # Create or fetch test user
        email = "switch_user@example.com"
        user = self.db.query(User).filter(User.email == email).first()
        if not user:
            user = User(
                email=email,
                hashed_password=hash_password("SecurePassword123!"),
                full_name="Switch Tester",
            )
            self.db.add(user)
            self.db.commit()
            self.db.refresh(user)

        self.user = user
        token = create_access_token({"sub": str(user.id), "email": user.email})
        self.headers = {"Authorization": f"Bearer {token}"}

        # Clear vector index for this user
        vector_index.clear(user_id=self.user.id)

    def tearDown(self):
        try:
            self.db.query(ChatMessage).delete()
            self.db.query(Document).delete()
            self.db.commit()
        except Exception:
            pass
        finally:
            self.db.close()

    @patch("app.services.llm.Groq")
    def test_switching_documents_preserves_db_history_and_isolates_sources(self, mock_groq_class):
        """
        When switching from Doc A to Doc B:
        1. Chat messages for Doc A are saved in DB.
        2. Chat with Doc B produces fresh answers and citations for Doc B only.
        3. Doc A's chat history is NOT deleted from the database.
        """
        uid_a = uuid.uuid4().hex[:12]
        saved_fn_a = f"{uid_a}_alpha_report.pdf"

        # ── Step 1: Create Document A in DB & Index it ──
        doc_a = Document(
            user_id=self.user.id,
            original_filename="Alpha_Report.pdf",
            saved_filename=saved_fn_a,
            file_type="PDF",
            file_size_bytes=1024,
        )
        self.db.add(doc_a)
        self.db.commit()
        self.db.refresh(doc_a)

        doc_a_data = {
            "filename": doc_a.original_filename,
            "saved_filename": doc_a.saved_filename,
            "file_type": "PDF",
            "pages": [
                {"page_number": 1, "text": "Alpha Project Overview: Alpha is a high-speed telemetry engine."},
                {"page_number": 2, "text": "Alpha Security: Alpha implements end-to-end token encryption."},
            ],
        }
        index_document_data(doc_a_data, user_id=self.user.id, index=vector_index)

        # ── Step 2: Chat with Document A ──
        mock_groq_instance = MagicMock()
        mock_choice_a = MagicMock()
        mock_choice_a.message.content = "Alpha is a high-speed telemetry engine (Page 1)."
        mock_response_a = MagicMock()
        mock_response_a.choices = [mock_choice_a]
        mock_groq_instance.chat.completions.create.return_value = mock_response_a
        mock_groq_class.return_value = mock_groq_instance

        res_a = self.client.post(
            "/documents/chat",
            headers=self.headers,
            json={
                "saved_filename": doc_a.saved_filename,
                "question": "What is Alpha?",
                "top_k": 2,
            },
        )
        self.assertEqual(res_a.status_code, 200)
        data_a = res_a.json()
        self.assertEqual(data_a["status"], "success")
        self.assertIn("telemetry engine", data_a["answer"])
        self.assertEqual(data_a["sources"][0]["source"], "Page 1")

        # Verify Doc A chat messages exist in DB
        chat_a_count = self.db.query(ChatMessage).filter(ChatMessage.document_id == doc_a.id).count()
        self.assertEqual(chat_a_count, 2)  # 1 user + 1 assistant

        # ── Step 3: Switch to Document B (simulate upload another file) ──
        uid_b = uuid.uuid4().hex[:12]
        saved_fn_b = f"{uid_b}_beta_manual.docx"

        doc_b = Document(
            user_id=self.user.id,
            original_filename="Beta_Manual.docx",
            saved_filename=saved_fn_b,
            file_type="DOCX",
            file_size_bytes=2048,
        )
        self.db.add(doc_b)
        self.db.commit()
        self.db.refresh(doc_b)

        doc_b_data = {
            "filename": doc_b.original_filename,
            "saved_filename": doc_b.saved_filename,
            "file_type": "DOCX",
            "paragraphs": [
                {"paragraph_number": 1, "text": "Beta Guidelines: Beta provides automated data labeling workflows."},
                {"paragraph_number": 2, "text": "Beta Deployment: Beta operates on Kubernetes microservices."},
            ],
        }
        index_document_data(doc_b_data, user_id=self.user.id, index=vector_index)

        # Chat with Document B
        mock_choice_b = MagicMock()
        mock_choice_b.message.content = "Beta provides automated data labeling workflows (Paragraph 1)."
        mock_response_b = MagicMock()
        mock_response_b.choices = [mock_choice_b]
        mock_groq_instance.chat.completions.create.return_value = mock_response_b

        res_b = self.client.post(
            "/documents/chat",
            headers=self.headers,
            json={
                "saved_filename": doc_b.saved_filename,
                "question": "What is Beta?",
                "top_k": 2,
            },
        )
        self.assertEqual(res_b.status_code, 200)
        data_b = res_b.json()
        self.assertEqual(data_b["status"], "success")
        self.assertIn("labeling workflows", data_b["answer"])
        self.assertEqual(data_b["sources"][0]["source"], "Paragraph 1")
        self.assertNotIn("Alpha", data_b["sources"][0]["filename"])

        # ── Step 4: Verify Database Persistence ──
        # Doc A messages are NOT deleted from the database
        chat_a_count_after = self.db.query(ChatMessage).filter(ChatMessage.document_id == doc_a.id).count()
        self.assertEqual(chat_a_count_after, 2)

        # Doc B messages exist independently in the database
        chat_b_count = self.db.query(ChatMessage).filter(ChatMessage.document_id == doc_b.id).count()
        self.assertEqual(chat_b_count, 2)

    def test_client_clear_index_does_not_delete_db_chat_history(self):
        """Clearing in-memory vector index does NOT delete chat messages from the database."""
        uid = uuid.uuid4().hex[:12]
        saved_fn = f"{uid}_persist_test.pdf"

        doc = Document(
            user_id=self.user.id,
            original_filename="Persist_Test.pdf",
            saved_filename=saved_fn,
            file_type="PDF",
            file_size_bytes=512,
        )
        self.db.add(doc)
        self.db.commit()
        self.db.refresh(doc)

        msg = ChatMessage(
            document_id=doc.id,
            user_id=self.user.id,
            role="user",
            content="Persistent test query",
        )
        self.db.add(msg)
        self.db.commit()

        # Call clear-index endpoint
        clear_res = self.client.post("/documents/clear-index", headers=self.headers)
        self.assertEqual(clear_res.status_code, 200)

        # Verify DB chat message is still present
        remaining = self.db.query(ChatMessage).filter(ChatMessage.document_id == doc.id).count()
        self.assertEqual(remaining, 1)


if __name__ == "__main__":
    unittest.main()
