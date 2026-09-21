"""
tests/test_rag_accuracy.py - Focused tests for advanced RAG retrieval accuracy and source references.

Covers:
1. Factual query: "Who developed the project and for which degree?"
2. Factual query: "What can a user do in the system?"
3. Factual query: "What technologies were used?"
4. Long-document summary retrieval across representative sections (beginning, middle, conclusion).
5. Source reference filtering: returns only sources actually used for the answer, preserving page/paragraph metadata.
6. Empty source list when document contains insufficient information.
"""

from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.llm import filter_used_sources, generate_rag_answer
from app.services.rag import (
    InMemoryVectorIndex,
    index_document_data,
)


class TestRAGRetrievalAccuracy(unittest.TestCase):
    """Focused tests for direct factual questions and long-document summarization."""

    def setUp(self):
        self.test_index = InMemoryVectorIndex()

        # Multi-page test document simulating a realistic 8-page project report
        self.doc_data = {
            "filename": "datalens_capstone_report.pdf",
            "saved_filename": "saved_datalens_capstone_report.pdf",
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
                        "CHAPTER 1: INTRODUCTION & PROBLEM STATEMENT. In today's data-driven world, organizations "
                        "face immense challenges processing multi-format data. The primary objective of this project "
                        "is to build an automated, accessible AI analytics solution that combines tabular analytics and RAG."
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
                        "SECURITY HARDENING & MULTI-TENANT ISOLATION: Password hashing is implemented using bcrypt "
                        "with salt rounds. All API routes enforce strict multi-tenant isolation, ensuring users access "
                        "only their own uploaded documents and chat histories. Secrets are managed through environment variables."
                    ),
                },
                {
                    "page_number": 8,
                    "text": (
                        "CHAPTER 5: CONCLUSION AND FUTURE SCOPE. DataLens AI successfully demonstrates full-stack "
                        "automated analytics and grounded document intelligence. Future enhancements will include support "
                        "for multi-document cross-comparison and real-time streaming LLM responses."
                    ),
                },
            ],
        }

        # Index the multi-page document into test index
        index_document_data(self.doc_data, chunk_size=400, chunk_overlap=80, index=self.test_index)

    def test_factual_query_who_developed_project_and_degree(self):
        """Query 'Who developed the project and for which degree?' reliably returns Page 1."""
        query = "Who developed the project and for which degree?"
        results = self.test_index.search(query=query, top_k=3, filename="datalens_capstone_report.pdf")

        self.assertGreater(len(results), 0)
        top_chunk = results[0]

        # Top chunk must be Page 1 containing author and degree information
        self.assertEqual(top_chunk["page_number"], 1)
        self.assertIn("Alex Mercer", top_chunk["text"])
        self.assertIn("Priya Sharma", top_chunk["text"])
        self.assertIn("Bachelor of Technology", top_chunk["text"])
        self.assertIn("Computer Science", top_chunk["text"])

    def test_factual_query_what_can_user_do(self):
        """Query 'What can a user do in the system?' reliably returns the User Capabilities section on Page 6."""
        query = "What can a user do in the system?"
        results = self.test_index.search(query=query, top_k=3, filename="datalens_capstone_report.pdf")

        self.assertGreater(len(results), 0)
        top_chunk = results[0]

        # Top chunk must be Page 6 detailing user capabilities
        self.assertEqual(top_chunk["page_number"], 6)
        self.assertIn("user can", top_chunk["text"].lower())
        self.assertIn("upload", top_chunk["text"].lower())
        self.assertIn("chat with ai", top_chunk["text"].lower())

    def test_factual_query_what_technologies_used(self):
        """Query 'What technologies were used?' reliably returns the Technologies section on Page 4."""
        query = "What technologies were used?"
        results = self.test_index.search(query=query, top_k=3, filename="datalens_capstone_report.pdf")

        self.assertGreater(len(results), 0)
        top_chunk = results[0]

        # Top chunk must be Page 4 containing technology stack
        self.assertEqual(top_chunk["page_number"], 4)
        self.assertIn("FastAPI", top_chunk["text"])
        self.assertIn("React", top_chunk["text"])
        self.assertIn("PostgreSQL", top_chunk["text"])
        self.assertIn("Docker", top_chunk["text"])

    def test_long_document_summary_retrieval(self):
        """Summary queries retrieve representative content across the document (beginning, middle, conclusion)."""
        queries = [
            "Summarize the main points of this document.",
            "What is the document about?",
            "Provide an overview and summary of the project.",
        ]

        for q in queries:
            results = self.test_index.search(query=q, top_k=4, filename="datalens_capstone_report.pdf")
            self.assertGreaterEqual(len(results), 3)

            pages_retrieved = [c["page_number"] for c in results]

            # Representative summary must include beginning (Page 1), middle, and end (Page 8)
            self.assertIn(1, pages_retrieved, f"Beginning (Page 1) missing for query: '{q}'")
            self.assertIn(8, pages_retrieved, f"Conclusion (Page 8) missing for query: '{q}'")
            # Must span multiple distinct sections of the document
            self.assertGreater(len(set(pages_retrieved)), 2)

    def test_filter_used_sources_returns_only_actual_sources(self):
        """Only sources actually cited or contributing to the generated answer are returned."""
        chunks = [
            {
                "filename": "report.pdf",
                "page_number": 1,
                "paragraph_number": None,
                "text": "Submitted by Alex Mercer and Priya Sharma for Bachelor of Technology in Computer Science.",
                "score": 0.95,
            },
            {
                "filename": "report.pdf",
                "page_number": 4,
                "paragraph_number": None,
                "text": "The backend utilizes FastAPI with PostgreSQL and Docker containerization.",
                "score": 0.70,
            },
            {
                "filename": "report.pdf",
                "page_number": 7,
                "paragraph_number": None,
                "text": "Security is ensured via bcrypt password hashing and multi-tenant isolation.",
                "score": 0.65,
            },
        ]

        # Answer only addresses author and degree
        answer_authors = (
            "The project was developed by Alex Mercer and Priya Sharma for the degree of "
            "Bachelor of Technology in Computer Science (Page 1)."
        )
        sources_authors = filter_used_sources(answer_authors, chunks)

        self.assertEqual(len(sources_authors), 1)
        self.assertEqual(sources_authors[0]["source"], "Page 1")
        self.assertEqual(sources_authors[0]["page_number"], 1)
        self.assertEqual(sources_authors[0]["filename"], "report.pdf")

        # Answer only addresses technologies
        answer_tech = "The system was built using FastAPI, PostgreSQL, and Docker containerization."
        sources_tech = filter_used_sources(answer_tech, chunks)

        self.assertEqual(len(sources_tech), 1)
        self.assertEqual(sources_tech[0]["source"], "Page 4")
        self.assertEqual(sources_tech[0]["page_number"], 4)

    def test_insufficient_information_returns_empty_sources(self):
        """When answer indicates insufficient information, returned sources is an empty list."""
        chunks = [
            {
                "filename": "report.pdf",
                "page_number": 1,
                "paragraph_number": None,
                "text": "DataLens AI is an analytics platform.",
                "score": 0.50,
            },
        ]

        insufficient_ans = "The provided document does not contain sufficient information to answer this question."
        sources = filter_used_sources(insufficient_ans, chunks)
        self.assertEqual(sources, [])

    def test_generate_rag_answer_filters_sources_correctly(self):
        """generate_rag_answer integrates filter_used_sources properly."""
        mock_client = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = (
            "The project was developed by Alex Mercer and Priya Sharma for the degree of "
            "Bachelor of Technology in Computer Science (Page 1)."
        )
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response

        chunks = [
            {
                "filename": "capstone.pdf",
                "page_number": 1,
                "paragraph_number": None,
                "text": "Submitted by Alex Mercer and Priya Sharma for Bachelor of Technology.",
                "score": 0.95,
            },
            {
                "filename": "capstone.pdf",
                "page_number": 5,
                "paragraph_number": None,
                "text": "Module 3 handles Document Extraction.",
                "score": 0.60,
            },
        ]

        res = generate_rag_answer(
            question="Who developed the project and for which degree?",
            chunks=chunks,
            client=mock_client,
        )

        self.assertEqual(res["status"], "success")
        self.assertIn("Alex Mercer", res["answer"])
        # Exactly ONE source (Page 1) is returned since Page 5 was not used
        self.assertEqual(len(res["sources"]), 1)
        self.assertEqual(res["sources"][0]["source"], "Page 1")
        self.assertEqual(res["sources"][0]["page_number"], 1)

    def test_broad_overview_key_topics_and_main_findings_retrieval(self):
        """Broad queries like 'key topics', 'main findings', 'key findings' retrieve representative content across sections."""
        overview_queries = [
            "What are the key topics discussed in this document?",
            "Summarize the main findings of this project report.",
            "What are the key findings?",
            "Provide an overview of the main topics.",
        ]

        for q in overview_queries:
            results = self.test_index.search(query=q, top_k=4, filename="datalens_capstone_report.pdf")
            self.assertGreaterEqual(len(results), 3, f"Failed to retrieve representative chunks for: '{q}'")

            pages = [c["page_number"] for c in results]
            # Must retrieve beginning (intro/abstract) and conclusion (outcomes)
            self.assertIn(1, pages, f"Page 1 missing for overview query: '{q}'")
            self.assertIn(8, pages, f"Page 8 missing for overview query: '{q}'")
            self.assertGreater(len(set(pages)), 2)

    def test_query_with_in_tabular_form_retrieval(self):
        """Formatting directives like 'in tabular form' affect presentation only and do not degrade retrieval."""
        tabular_queries = [
            "What are the key topics in tabular form?",
            "List the main findings as a table",
            "What are the key findings in table format?",
        ]

        for q in tabular_queries:
            results = self.test_index.search(query=q, top_k=4, filename="datalens_capstone_report.pdf")
            self.assertGreaterEqual(len(results), 3, f"Failed to retrieve chunks for tabular query: '{q}'")

            pages = [c["page_number"] for c in results]
            self.assertIn(1, pages, f"Page 1 missing for tabular query: '{q}'")
            self.assertIn(8, pages, f"Page 8 missing for tabular query: '{q}'")

    def test_query_with_formatting_instructions_retrieves_same_content_as_base_query(self):
        """Formatting instructions (e.g. 'in tabular form', 'in bullet points') retrieve identical top content as base query."""
        # Test 1: Technologies query with and without tabular form
        base_tech_q = "What technologies were used?"
        tabular_tech_q = "What technologies were used? Answer in tabular form"
        res_base = self.test_index.search(query=base_tech_q, top_k=3, filename="datalens_capstone_report.pdf")
        res_tabular = self.test_index.search(query=tabular_tech_q, top_k=3, filename="datalens_capstone_report.pdf")

        self.assertEqual(res_base[0]["page_number"], 4)
        self.assertEqual(res_tabular[0]["page_number"], 4)
        self.assertIn("FastAPI", res_tabular[0]["text"])
        self.assertIn("PostgreSQL", res_tabular[0]["text"])

        # Test 2: User capabilities query with and without bullet points
        base_user_q = "What can a user do in the system?"
        bullets_user_q = "What can a user do in the system in bullet points"
        res_user_base = self.test_index.search(query=base_user_q, top_k=3, filename="datalens_capstone_report.pdf")
        res_user_bullets = self.test_index.search(query=bullets_user_q, top_k=3, filename="datalens_capstone_report.pdf")

        self.assertEqual(res_user_base[0]["page_number"], 6)
        self.assertEqual(res_user_bullets[0]["page_number"], 6)
        self.assertIn("upload", res_user_bullets[0]["text"].lower())

    def test_genuine_insufficient_information_cases(self):
        """Genuinely unanswerable questions return standard insufficient-information message with zero sources."""
        mock_client = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "The provided document does not contain sufficient information to answer this question."
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response

        # Scenario A: Question about an unrelated topic not present in retrieved chunks
        unrelated_q = "What was the total profit margin of Microsoft Corporation in 2024?"
        chunks = [
            {
                "filename": "capstone.pdf",
                "page_number": 1,
                "paragraph_number": None,
                "text": "DataLens AI is a university capstone project on document intelligence.",
            }
        ]

        res = generate_rag_answer(question=unrelated_q, chunks=chunks, client=mock_client)
        self.assertEqual(res["status"], "success")
        self.assertEqual(
            res["answer"],
            "The provided document does not contain sufficient information to answer this question.",
        )
        self.assertEqual(res["sources"], [])

        # Scenario B: Empty chunks list directly returns insufficient information without calling LLM
        res_empty = generate_rag_answer(question="Any unindexed query?", chunks=[])
        self.assertEqual(res_empty["status"], "success")
        self.assertIn("does not contain sufficient information", res_empty["answer"])
        self.assertEqual(res_empty["sources"], [])


if __name__ == "__main__":
    unittest.main()
