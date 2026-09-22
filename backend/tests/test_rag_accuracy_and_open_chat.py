"""
tests/test_rag_accuracy_and_open_chat.py - Focused tests for:
1. Project title and direct factual retrieval.
2. Developer and author retrieval.
3. Technology stack retrieval.
4. Workflow and user capability retrieval.
5. Genuine insufficient-information retrieval.
6. Reopening saved chat without unnecessary re-indexing.
7. Correct document and user isolation.
"""

from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db.session import get_db
from app.db.models import Base, User, Document, ChatMessage
from app.core.auth import hash_password, create_access_token
from app.core.config import settings
from app.services.llm import generate_rag_answer
from app.services.rag import (
    InMemoryVectorIndex,
    index_document_data,
    vector_index,
)


class TestRAGAccuracyAndOpenChat(unittest.TestCase):
    """Verify high-accuracy factual RAG retrieval, insufficient-info handling, and fast chat reopening."""

    def setUp(self):
        self.test_index = InMemoryVectorIndex()

        # Realistic capstone project report with distinct pages
        self.doc_data = {
            "filename": "cloud_datalens_report.pdf",
            "saved_filename": "saved_cloud_datalens_report.pdf",
            "file_type": "PDF",
            "pages": [
                {
                    "page_number": 1,
                    "text": (
                        "PROJECT REPORT ON DATALENS AI: AN INTELLIGENT DATA & DOCUMENT ANALYSIS PLATFORM. "
                        "Submitted by: Alex Mercer and Priya Sharma in partial fulfillment of the requirements "
                        "for the degree of Bachelor of Technology in Computer Science and Engineering. "
                        "Academic Year: 2025-2026. Department of Computer Science."
                    ),
                },
                {
                    "page_number": 2,
                    "text": (
                        "ABSTRACT: DataLens AI is a modern web application designed for automated exploratory "
                        "data analysis and document intelligence. The platform allows users to upload structured "
                        "datasets (CSV, XLSX) and unstructured documents (PDF, DOCX) to receive automated AI insights."
                    ),
                },
                {
                    "page_number": 3,
                    "text": (
                        "CHAPTER 1: INTRODUCTION & PROBLEM STATEMENT. Organizations face immense challenges "
                        "processing multi-format data. The primary objective is to combine tabular analytics and RAG."
                    ),
                },
                {
                    "page_number": 4,
                    "text": (
                        "SYSTEM ARCHITECTURE & TECHNOLOGIES USED: The backend is built using FastAPI (Python 3.13) "
                        "with asynchronous endpoints. Database storage utilizes PostgreSQL with SQLAlchemy ORM and SQLite "
                        "for local development. The frontend is built with React 19, Vite, Recharts, and Vanilla CSS. "
                        "Containerization is handled via Docker and Docker Compose, and embeddings use sentence-transformers."
                    ),
                },
                {
                    "page_number": 5,
                    "text": (
                        "MODULE SPECIFICATION: The system contains four core modules: "
                        "1. Authentication Module supporting JWT and Google Identity Services. "
                        "2. CSV/XLSX Analytics Engine for automated statistics and correlation. "
                        "3. Document Extraction & RAG Pipeline for PDF/DOCX retrieval. "
                        "4. Groq LLM Integration Service for fast grounded insights."
                    ),
                },
                {
                    "page_number": 6,
                    "text": (
                        "USER CAPABILITIES & WORKFLOW: In the system, a user can: "
                        "1. Sign up and authenticate securely with email/password or Google Single Sign-On. "
                        "2. Upload CSV, XLSX, PDF, or DOCX files through a drag-and-drop interface. "
                        "3. View automated column summaries, data distributions, and interactive charts. "
                        "4. Chat with AI about uploaded documents with grounded source citations and page numbers."
                    ),
                },
                {
                    "page_number": 7,
                    "text": (
                        "SECURITY HARDENING & MULTI-TENANT ISOLATION: Password hashing is implemented using bcrypt. "
                        "All API routes enforce strict multi-tenant isolation, ensuring users access only their own data."
                    ),
                },
                {
                    "page_number": 8,
                    "text": (
                        "CHAPTER 5: CONCLUSION AND FUTURE SCOPE. DataLens AI successfully demonstrates full-stack "
                        "automated analytics and grounded document intelligence."
                    ),
                },
            ],
        }

        # Index document into test index with user_id=1
        index_document_data(self.doc_data, chunk_size=400, chunk_overlap=80, user_id=1, index=self.test_index)

    def test_project_title_direct_fact_retrieval(self):
        """Direct queries asking for project title or name reliably retrieve Page 1."""
        queries = [
            "What is the project title?",
            "What is the project name?",
            "What is the title of the document?",
        ]
        for q in queries:
            results = self.test_index.search(query=q, top_k=3, filename="cloud_datalens_report.pdf", user_id=1)
            self.assertGreater(len(results), 0)
            top_chunk = results[0]
            self.assertEqual(top_chunk["page_number"], 1, f"Failed for query '{q}'")
            self.assertIn("DATALENS AI", top_chunk["text"])

    def test_developer_and_author_retrieval(self):
        """Queries for developer, authors, or creators reliably retrieve Page 1 with author names."""
        queries = [
            "Who is the developer of this project?",
            "Who are the authors?",
            "Who developed this project?",
            "Who created this project?",
        ]
        for q in queries:
            results = self.test_index.search(query=q, top_k=3, filename="cloud_datalens_report.pdf", user_id=1)
            self.assertGreater(len(results), 0)
            top_chunk = results[0]
            self.assertEqual(top_chunk["page_number"], 1, f"Failed for query '{q}'")
            self.assertIn("Alex Mercer", top_chunk["text"])
            self.assertIn("Priya Sharma", top_chunk["text"])

    def test_technology_retrieval(self):
        """Queries for technology stack or tools reliably retrieve Page 4."""
        queries = [
            "What technologies were used in this project?",
            "What is the tech stack?",
            "What backend and frontend tools are used?",
        ]
        for q in queries:
            results = self.test_index.search(query=q, top_k=3, filename="cloud_datalens_report.pdf", user_id=1)
            self.assertGreater(len(results), 0)
            top_chunk = results[0]
            self.assertEqual(top_chunk["page_number"], 4, f"Failed for query '{q}'")
            self.assertIn("FastAPI", top_chunk["text"])
            self.assertIn("React", top_chunk["text"])
            self.assertIn("PostgreSQL", top_chunk["text"])

    def test_workflow_retrieval(self):
        """Queries for user workflow or pipeline reliably retrieve Page 6."""
        queries = [
            "What is the workflow of the system?",
            "What can a user do in the system?",
            "Describe the user workflow steps.",
        ]
        for q in queries:
            results = self.test_index.search(query=q, top_k=3, filename="cloud_datalens_report.pdf", user_id=1)
            self.assertGreater(len(results), 0)
            top_chunk = results[0]
            self.assertEqual(top_chunk["page_number"], 6, f"Failed for query '{q}'")
            self.assertIn("workflow", top_chunk["text"].lower())
            self.assertIn("upload", top_chunk["text"].lower())

    @patch("app.services.llm.Groq")
    def test_genuine_insufficient_information_retrieval(self, mock_groq_class):
        """When the document truly lacks the fact (e.g. project budget), LLM returns insufficient info statement."""
        mock_groq = MagicMock()
        mock_groq_class.return_value = mock_groq
        mock_choice = MagicMock()
        mock_choice.message.content = "The provided document does not contain sufficient information to answer this question."
        mock_groq.chat.completions.create.return_value = MagicMock(choices=[mock_choice])

        query = "What is the annual financial budget and funding for this project?"
        results = self.test_index.search(query=query, top_k=3, filename="cloud_datalens_report.pdf", user_id=1)

        # None of the retrieved chunks have financial numbers or budget information
        for chunk in results:
            self.assertNotIn("budget", chunk["text"].lower())
            self.assertNotIn("funding", chunk["text"].lower())

        answer_data = generate_rag_answer(question=query, chunks=results, client=mock_groq)
        self.assertIn(
            "does not contain sufficient information",
            answer_data["answer"].lower(),
        )
        # When insufficient information is returned, sources list must be empty
        self.assertEqual(answer_data["sources"], [])

    def test_correct_document_and_user_isolation(self):
        """Strict isolation ensures cross-user and cross-document data is never returned."""
        # Index another document for user_id=2
        doc_user2 = {
            "filename": "user2_secret_patent.pdf",
            "saved_filename": "saved_user2_secret_patent.pdf",
            "file_type": "PDF",
            "pages": [
                {"page_number": 1, "text": "Confidential quantum encryption patent owned by User Two."}
            ],
        }
        index_document_data(doc_user2, user_id=2, index=self.test_index)

        # User 1 searches for quantum encryption patent
        u1_results = self.test_index.search(
            query="quantum encryption patent",
            user_id=1,
            filename="user2_secret_patent.pdf",
        )
        # Must return empty list: User 1 has no access to User 2's document
        self.assertEqual(len(u1_results), 0)

        # User 2 searches for their own patent
        u2_results = self.test_index.search(
            query="quantum encryption patent",
            user_id=2,
            filename="user2_secret_patent.pdf",
        )
        self.assertEqual(len(u2_results), 1)
        self.assertIn("Confidential quantum encryption", u2_results[0]["text"])

    def test_reopening_saved_chat_without_unnecessary_reindexing(self):
        """
        Opening a previous chat loads messages from DB immediately without re-indexing.
        When document is already indexed in-memory, /documents/index reuses the existing index.
        """
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        Base.metadata.create_all(bind=engine)

        db = TestingSessionLocal()
        user = User(
            email="chat_tester@example.com",
            hashed_password=hash_password("Password123!"),
            full_name="Chat Tester",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        doc = Document(
            user_id=user.id,
            original_filename="saved_chat_doc.pdf",
            saved_filename="0123456789abcdef_saved_chat_doc.pdf",
            file_type="PDF",
            file_size_bytes=2048,
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)

        msg1 = ChatMessage(
            document_id=doc.id,
            user_id=user.id,
            role="user",
            content="What is this document about?",
        )
        msg2 = ChatMessage(
            document_id=doc.id,
            user_id=user.id,
            role="assistant",
            content="This document covers DataLens AI architecture.",
            sources=[{"page_number": 1, "text": "Overview snippet"}],
        )
        db.add_all([msg1, msg2])
        db.commit()

        def override_get_db():
            try:
                yield db
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)
        token = create_access_token({"sub": str(user.id), "email": user.email})
        headers = {"Authorization": f"Bearer {token}"}

        # Create dummy physical file in upload_dir for realistic disk resolution
        dummy_file = settings.upload_dir_path / doc.saved_filename
        dummy_file.write_bytes(b"%PDF-1.4 dummy document for testing")

        try:
            # 1. Opening saved chat from history calls GET /documents/messages
            response = client.get(
                f"/documents/messages?saved_filename={doc.saved_filename}",
                headers=headers,
            )
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data["status"], "success")
            self.assertEqual(len(data["messages"]), 2)
            self.assertEqual(data["messages"][0]["content"], "What is this document about?")
            self.assertEqual(data["messages"][1]["content"], "This document covers DataLens AI architecture.")

            # 2. Verify in-memory index reuse: pre-populate global vector_index for this document
            vector_index.clear(user_id=user.id)
            test_chunk = {
                "chunk_id": "test_c1",
                "text": "DataLens AI architecture overview.",
                "filename": doc.original_filename,
                "saved_filename": doc.saved_filename,
                "file_type": "PDF",
                "page_number": 1,
                "user_id": user.id,
            }
            # Index chunk directly into vector_index
            index_document_data(
                {
                    "filename": doc.original_filename,
                    "saved_filename": doc.saved_filename,
                    "file_type": "PDF",
                    "pages": [{"page_number": 1, "text": "DataLens AI architecture overview."}],
                },
                user_id=user.id,
                index=vector_index,
            )

            # Call POST /documents/index with mock extract_document to ensure extraction is NOT performed
            with patch("app.api.documents.extract_document") as mock_extract:
                resp = client.post(
                    "/documents/index",
                    json={"saved_filename": doc.saved_filename},
                    headers=headers,
                )
                self.assertEqual(resp.status_code, 200)
                idx_data = resp.json()
                self.assertEqual(idx_data.get("reused_index"), True)
                mock_extract.assert_not_called()
        finally:
            if dummy_file.exists():
                try:
                    dummy_file.unlink()
                except Exception:
                    pass
            app.dependency_overrides.pop(get_db, None)
            db.close()
            vector_index.clear(user_id=user.id)
