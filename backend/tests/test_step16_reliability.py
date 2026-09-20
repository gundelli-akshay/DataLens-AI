import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient
from groq import RateLimitError, APITimeoutError, APIConnectionError

from app.main import app
from app.core.config import settings
from app.core.auth import get_current_user
from app.db.models import User
from app.services.llm import generate_insights, generate_rag_answer
from app.services.rag import index_document_data, InMemoryVectorIndex


@pytest.fixture
def mock_user():
    return User(
        id=101,
        email="reliability_test@example.com",
        full_name="Reliability Tester",
        auth_provider="email",
    )


@pytest.fixture
def client(mock_user):
    app.dependency_overrides[get_current_user] = lambda: mock_user
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# --- LLM Error Handling Tests ---

def test_generate_insights_missing_api_key():
    """Missing API key raises clean ValueError."""
    with patch.object(settings, "groq_api_key", ""):
        with pytest.raises(ValueError) as exc_info:
            generate_insights({"filename": "test.csv", "shape": {"rows": 10, "columns": 2}})
        assert "Groq API key is not configured" in str(exc_info.value)


def test_generate_insights_rate_limit_handled(client):
    """RateLimitError in insights is translated to a clean 502 LLM service error."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = RateLimitError(
        message="Rate limit reached", response=MagicMock(status_code=429), body=None
    )

    with patch("app.services.llm.Groq", return_value=mock_client):
        res = client.post(
            "/ai/insights/",
            json={"analysis": {"status": "success", "shape": {"rows": 5, "columns": 2}}},
        )
        assert res.status_code == 502
        assert "LLM service error" in res.json()["detail"]
        assert "rate limit exceeded" in res.json()["detail"].lower()


def test_generate_insights_timeout_handled(client):
    """APITimeoutError in insights is translated to a clean 502 LLM service error."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = APITimeoutError(request=MagicMock())

    with patch("app.services.llm.Groq", return_value=mock_client):
        res = client.post(
            "/ai/insights/",
            json={"analysis": {"status": "success", "shape": {"rows": 5, "columns": 2}}},
        )
        assert res.status_code == 502
        assert "timed out" in res.json()["detail"].lower()


def test_generate_insights_empty_response_handled(client):
    """Empty response from Groq raises clean 502 error instead of crashing."""
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.choices = []  # Empty choices list
    mock_client.chat.completions.create.return_value = mock_resp

    with patch("app.services.llm.Groq", return_value=mock_client):
        res = client.post(
            "/ai/insights/",
            json={"analysis": {"status": "success", "shape": {"rows": 5, "columns": 2}}},
        )
        assert res.status_code == 502
        assert "empty response" in res.json()["detail"].lower()


# --- RAG & Document Chat Reliability Tests ---

def test_rag_empty_chunks_grounded_fallback():
    """RAG with empty chunks returns strict fallback without calling LLM."""
    res = generate_rag_answer(question="What is the total revenue?", chunks=[])
    assert res["status"] == "success"
    assert "does not contain sufficient information" in res["answer"]
    assert res["sources"] == []


def test_rag_empty_document_indexing():
    """Empty or whitespace document returns 0 indexed chunks gracefully."""
    empty_doc = {
        "filename": "empty.pdf",
        "file_type": "PDF",
        "pages": [{"page_number": 1, "text": "   "}],
        "metadata": {},
    }
    local_index = InMemoryVectorIndex()
    result = index_document_data(empty_doc, index=local_index)
    assert result["status"] == "success"
    assert result["chunks_indexed"] == 0


def test_document_chat_rate_limit_handled(client):
    """RateLimitError during document chat returns clean 502."""
    test_pdf = settings.upload_dir_path / "rate_limit_test.pdf"
    test_pdf.write_bytes(b"%PDF-1.4 dummy")

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = RateLimitError(
        message="Rate limit reached", response=MagicMock(status_code=429), body=None
    )

    with patch("app.services.llm.Groq", return_value=mock_client):
        with patch("app.api.documents.retrieve_relevant_chunks", return_value=[{"text": "Sample context", "page_number": 1}]):
            res = client.post(
                "/documents/chat",
                json={"saved_filename": "rate_limit_test.pdf", "question": "Explain this file"},
            )
            assert res.status_code == 502
            assert "rate limit exceeded" in res.json()["detail"].lower()

    if test_pdf.exists():
        test_pdf.unlink()


def test_document_chat_validation(client):
    """Empty question and missing filename return 400 validation error."""
    # Empty question
    res1 = client.post("/documents/chat", json={"question": "   ", "saved_filename": "doc.pdf"})
    assert res1.status_code == 400
    assert "cannot be empty" in res1.json()["detail"]

    # Missing filename
    res2 = client.post("/documents/chat", json={"question": "What is AI?"})
    assert res2.status_code == 400
    assert "must be provided" in res2.json()["detail"]


# --- Error Sanitization & Generic 500 Tests ---

def test_unexpected_exception_returns_generic_500_without_stack_trace(client):
    """Unexpected backend errors return generic 500 without leaking stack traces or paths."""
    with patch("app.api.analyze.analyze_csv", side_effect=Exception("Secret internal traceback at C:\\Server\\Private")):
        upload_res = client.post(
            "/upload/",
            files={"file": ("test.csv", b"a,b\n1,2", "text/csv")},
        )
        assert upload_res.status_code == 200
        saved_name = upload_res.json()["saved_filename"]

        res = client.post("/analyze/", json={"saved_filename": saved_name})
        assert res.status_code == 500
        detail = res.json()["detail"]
        assert "unexpected internal server error" in detail.lower()
        # Assert internal paths / secrets are NOT leaked to the client
        assert "Private" not in detail
        assert "traceback" not in detail.lower()
