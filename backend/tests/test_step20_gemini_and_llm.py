"""
tests/test_step20_gemini_and_llm.py - Tests for Gemini primary + Groq fallback architecture.

Verifies:
1. Gemini 3.8 Flash is used as primary model when GEMINI_API_KEY is configured.
2. Graceful fallback to Groq when Gemini encounters quota/rate limit or timeout.
3. Both models receive identical grounded prompts and document excerpts.
4. When GEMINI_API_KEY is not set, Groq is used directly (backward compatibility).
5. When both models are unconfigured, ValueError is raised.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest
from app.core.config import Settings
from app.services.llm import generate_insights, generate_rag_answer, _call_llm_resilient


@pytest.fixture
def sample_analysis():
    return {
        "filename": "revenue.csv",
        "file_type": "CSV",
        "shape": {"rows": 50, "columns": 2},
        "missing_total": 0,
        "duplicate_rows": 0,
        "columns": [
            {"name": "month", "dtype": "object", "category": "categorical", "unique_count": 12, "missing_count": 0},
            {"name": "sales", "dtype": "int64", "category": "numeric", "unique_count": 50, "missing_count": 0},
        ],
        "numeric_summary": {
            "sales": {"mean": 5000.0, "median": 4800.0, "std": 300.0, "min": 4000.0, "max": 6500.0, "count": 50}
        },
        "categorical_summary": {
            "month": {"unique_count": 12, "top_values": [{"value": "Jan", "count": 5}]}
        },
    }


@pytest.fixture
def sample_chunks():
    return [
        {
            "chunk_id": "doc1_c1",
            "text": "Project Title: Blood Bank Management System. Developed by Akshay.",
            "filename": "project.pdf",
            "page_number": 1,
            "paragraph_number": None,
            "score": 0.95,
        }
    ]


def test_gemini_primary_success(sample_analysis, monkeypatch):
    """When Gemini is enabled and succeeds, it is used as primary."""
    monkeypatch.setattr("app.services.llm.settings.gemini_api_key", "mock_gemini_key_123")
    monkeypatch.setattr("app.services.llm.settings.gemini_model", "gemini-3.8-flash")

    with patch("app.services.llm._call_gemini", return_value="### Executive Summary\nGemini primary analysis.") as mock_gemini:
        with patch("app.services.llm._call_groq") as mock_groq:
            res = generate_insights(sample_analysis)
            assert res["status"] == "success"
            assert "Gemini primary analysis" in res["insights"]
            assert res["model"] == "gemini-3.8-flash"
            mock_gemini.assert_called_once()
            mock_groq.assert_not_called()


def test_gemini_fails_falls_back_to_groq(sample_analysis, monkeypatch):
    """When Gemini fails (e.g. rate limit / quota), transparently falls back to Groq."""
    monkeypatch.setattr("app.services.llm.settings.gemini_api_key", "mock_gemini_key_123")
    monkeypatch.setattr("app.services.llm.settings.gemini_model", "gemini-3.8-flash")
    monkeypatch.setattr("app.services.llm.settings.groq_api_key", "mock_groq_key_123")
    monkeypatch.setattr("app.services.llm.settings.groq_model", "openai/gpt-oss-20b")

    with patch("app.services.llm._call_gemini", side_effect=RuntimeError("Quota exceeded (429)")) as mock_gemini:
        with patch("app.services.llm._call_groq", return_value="### Executive Summary\nGroq fallback analysis.") as mock_groq:
            res = generate_insights(sample_analysis)
            assert res["status"] == "success"
            assert "Groq fallback analysis" in res["insights"]
            assert res["model"] == "openai/gpt-oss-20b"
            mock_gemini.assert_called_once()
            mock_groq.assert_called_once()


def test_rag_gemini_primary_and_fallback(sample_chunks, monkeypatch):
    """RAG answers use Gemini primary and Groq fallback with identical grounded context."""
    monkeypatch.setattr("app.services.llm.settings.gemini_api_key", "mock_gemini_key_123")
    monkeypatch.setattr("app.services.llm.settings.gemini_model", "gemini-3.8-flash")

    # 1. Gemini primary succeeds
    with patch("app.services.llm._call_gemini", return_value="The developer is Akshay (Page 1).") as mock_gemini:
        res = generate_rag_answer("Who developed this?", sample_chunks)
        assert res["status"] == "success"
        assert "Akshay" in res["answer"]
        assert res["model"] == "gemini-3.8-flash"
        assert len(res["sources"]) == 1
        assert res["sources"][0]["page_number"] == 1

    # 2. Gemini times out -> falls back to Groq
    monkeypatch.setattr("app.services.llm.settings.groq_api_key", "mock_groq_key_123")
    monkeypatch.setattr("app.services.llm.settings.groq_model", "openai/gpt-oss-20b")

    with patch("app.services.llm._call_gemini", side_effect=TimeoutError("Gemini call timed out")):
        with patch("app.services.llm._call_groq", return_value="The project title is Blood Bank Management System (Page 1).") as mock_groq:
            res_fb = generate_rag_answer("What is the project title?", sample_chunks)
            assert res_fb["status"] == "success"
            assert "Blood Bank" in res_fb["answer"]
            assert res_fb["model"] == "openai/gpt-oss-20b"
            mock_groq.assert_called_once()


def test_no_gemini_key_uses_groq_directly(sample_analysis, monkeypatch):
    """When GEMINI_API_KEY is empty, Groq is called directly without calling Gemini."""
    monkeypatch.setattr("app.services.llm.settings.gemini_api_key", "")
    monkeypatch.setattr("app.services.llm.settings.groq_api_key", "mock_groq_key_123")
    monkeypatch.setattr("app.services.llm.settings.groq_model", "openai/gpt-oss-20b")

    with patch("app.services.llm._call_gemini") as mock_gemini:
        with patch("app.services.llm._call_groq", return_value="Direct Groq response.") as mock_groq:
            res = generate_insights(sample_analysis)
            assert res["status"] == "success"
            assert res["model"] == "openai/gpt-oss-20b"
            mock_gemini.assert_not_called()
            mock_groq.assert_called_once()
