"""
tests/test_step9_insights.py - Comprehensive tests for Step 9 AI Insights.

Tests:
1. LLM service prompt formatting and constraints (no calculation, only explaining).
2. Service behavior with missing API key (raises ValueError).
3. Service behavior with mocked OpenAI client.
4. /ai/insights/ endpoint with direct analysis payload (mocked LLM).
5. /ai/insights/ endpoint with saved_filename for uploaded CSV (mocked LLM).
6. Non-existent file (404).
7. Path traversal attempt (400).
8. Unsupported file types (PDF/DOCX -> 422, TXT -> 415).
9. Missing both analysis and filename (400).
10. Unconfigured API key error response (503).
11. LLM provider exception handling (502).
"""

import sys
import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure backend directory is in path
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings
from app.services.llm import (
    SYSTEM_PROMPT,
    format_analysis_for_llm,
    generate_insights,
)


class TestStep9LLMService(unittest.TestCase):
    """Unit tests for app.services.llm."""

    def setUp(self):
        self.sample_analysis = {
            "status": "success",
            "filename": "sales.csv",
            "file_type": "CSV",
            "shape": {"rows": 100, "columns": 3},
            "columns": [
                {"name": "region", "dtype": "object", "category": "categorical", "missing_count": 0, "unique_count": 4},
                {"name": "revenue", "dtype": "float64", "category": "numeric", "missing_count": 2, "unique_count": 98},
                {"name": "order_date", "dtype": "object", "category": "date", "missing_count": 0, "unique_count": 45},
            ],
            "missing_total": 2,
            "duplicate_rows": 0,
            "numeric_summary": {
                "revenue": {"mean": 150.5, "median": 140.0, "min": 20.0, "max": 500.0, "std": 35.2, "count": 98}
            },
            "categorical_summary": {
                "region": {
                    "unique_count": 4,
                    "top_values": [
                        {"value": "North", "count": 40},
                        {"value": "South", "count": 30},
                    ],
                }
            },
        }

    def test_system_prompt_restricts_calculations(self):
        """Ensure system prompt forbids calculating or inventing new numeric results."""
        self.assertIn("Do NOT calculate", SYSTEM_PROMPT)
        self.assertIn("invent new numeric values", SYSTEM_PROMPT)
        self.assertIn("rely exclusively on the numbers and facts provided", SYSTEM_PROMPT.lower())

    def test_format_analysis_for_llm(self):
        """Prompt formatting includes all key metadata, numeric stats, and top categories."""
        formatted = format_analysis_for_llm(self.sample_analysis)
        self.assertIn("Dataset: sales.csv (CSV)", formatted)
        self.assertIn("Dimensions: 100 rows, 3 columns", formatted)
        self.assertIn("Data Quality: 2 total missing values, 0 duplicate rows", formatted)
        self.assertIn("region (categorical", formatted)
        self.assertIn("revenue: mean=150.5", formatted)
        self.assertIn("top values", formatted.lower())
        self.assertIn("'North': 40", formatted)

    def test_generate_insights_missing_key_raises(self):
        """When API key is missing and no client passed, raise ValueError."""
        with patch.object(settings, "groq_api_key", ""):
            with self.assertRaises(ValueError) as ctx:
                generate_insights(self.sample_analysis)
            self.assertIn("Groq API key is not configured", str(ctx.exception))

    def test_generate_insights_with_mock_client(self):
        """generate_insights succeeds when using a mock OpenAI client."""
        mock_client = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "### Executive Summary\nThe sales dataset contains 100 transactions..."
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response

        res = generate_insights(self.sample_analysis, client=mock_client)

        self.assertEqual(res["status"], "success")
        self.assertIn("The sales dataset contains 100 transactions", res["insights"])
        self.assertEqual(res["model"], settings.groq_model)
        mock_client.chat.completions.create.assert_called_once()


class TestStep9InsightsEndpoint(unittest.TestCase):
    """Integration tests for POST /ai/insights/ endpoint."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.sample_analysis = {
            "status": "success",
            "filename": "employees.csv",
            "file_type": "CSV",
            "shape": {"rows": 5, "columns": 3},
            "columns": [
                {"name": "name", "dtype": "object", "category": "categorical", "missing_count": 0, "unique_count": 5},
                {"name": "salary", "dtype": "int64", "category": "numeric", "missing_count": 0, "unique_count": 5},
                {"name": "dept", "dtype": "object", "category": "categorical", "missing_count": 0, "unique_count": 2},
            ],
            "missing_total": 0,
            "duplicate_rows": 0,
            "numeric_summary": {
                "salary": {"mean": 70000.0, "median": 70000.0, "min": 50000.0, "max": 90000.0, "std": 15811.39, "count": 5}
            },
            "categorical_summary": {
                "dept": {"unique_count": 2, "top_values": [{"value": "Engineering", "count": 3}, {"value": "HR", "count": 2}]}
            },
        }

    def test_insights_direct_analysis_success(self):
        """Calling /ai/insights/ with valid analysis dictionary succeeds with mocked LLM."""
        mock_return = {
            "status": "success",
            "insights": "### Executive Summary\nThe employee dataset has 5 records with an average salary of 70,000.",
            "model": "openai/gpt-oss-20b",
        }
        with patch("app.api.insights.generate_insights", return_value=mock_return) as mock_gen:
            resp = self.client.post("/ai/insights/", json={"analysis": self.sample_analysis})
            self.assertEqual(resp.status_code, 200)
            body = resp.json()
            self.assertEqual(body["status"], "success")
            self.assertIn("Executive Summary", body["insights"])
            self.assertEqual(body["model"], "openai/gpt-oss-20b")
            mock_gen.assert_called_once()

    def test_insights_with_saved_filename(self):
        """Calling /ai/insights/ with saved_filename runs analysis and passes to LLM."""
        test_filename = "00000000000000000000000000000001_test_insights.csv"
        file_path = settings.upload_dir_path / test_filename
        file_path.write_text("dept,salary\nEngineering,80000\nHR,60000\n", encoding="utf-8")

        mock_return = {
            "status": "success",
            "insights": "### Insights\nDepartment analysis shows 2 departments.",
            "model": "openai/gpt-oss-20b",
        }

        try:
            with patch("app.api.insights.generate_insights", return_value=mock_return) as mock_gen:
                resp = self.client.post("/ai/insights/", json={"saved_filename": test_filename})
                self.assertEqual(resp.status_code, 200)
                body = resp.json()
                self.assertEqual(body["status"], "success")
                self.assertIn("Department analysis", body["insights"])
                mock_gen.assert_called_once()
                # Verify passed analysis has shape and columns
                passed_data = mock_gen.call_args[0][0]
                self.assertEqual(passed_data["shape"]["rows"], 2)
                self.assertIn("dept", passed_data["column_names"])
        finally:
            if file_path.exists():
                file_path.unlink()

    def test_insights_missing_body_params(self):
        """Returns 400 when neither analysis nor saved_filename is provided."""
        resp = self.client.post("/ai/insights/", json={})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Either 'analysis' or 'saved_filename'", resp.json()["detail"])

    def test_insights_nonexistent_file(self):
        """Returns 404 when saved_filename does not exist."""
        resp = self.client.post("/ai/insights/", json={"saved_filename": "non_existent_file.csv"})
        self.assertEqual(resp.status_code, 404)
        self.assertIn("was not found", resp.json()["detail"])

    def test_insights_path_traversal(self):
        """Returns 400 when saved_filename contains directory traversal."""
        resp = self.client.post("/ai/insights/", json={"saved_filename": "../secret.csv"})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Invalid filename", resp.json()["detail"])

    def test_insights_pdf_rejection(self):
        """Returns 422 with document message when file is a PDF."""
        test_pdf = "00000000000000000000000000000002_doc.pdf"
        file_path = settings.upload_dir_path / test_pdf
        file_path.write_bytes(b"%PDF-1.4 dummy")
        try:
            resp = self.client.post("/ai/insights/", json={"saved_filename": test_pdf})
            self.assertEqual(resp.status_code, 422)
            self.assertIn("PDF files are not supported", resp.json()["detail"])
        finally:
            if file_path.exists():
                file_path.unlink()

    def test_insights_unsupported_file_extension(self):
        """Returns 415 when file has unsupported extension (e.g. .txt)."""
        test_txt = "00000000000000000000000000000003_data.txt"
        file_path = settings.upload_dir_path / test_txt
        file_path.write_text("just text", encoding="utf-8")
        try:
            resp = self.client.post("/ai/insights/", json={"saved_filename": test_txt})
            self.assertEqual(resp.status_code, 415)
            self.assertIn("not supported", resp.json()["detail"])
        finally:
            if file_path.exists():
                file_path.unlink()

    def test_insights_missing_api_key_returns_503(self):
        """Returns 503 when Groq API key is not configured."""
        with patch("app.api.insights.generate_insights", side_effect=ValueError("Groq API key is not configured.")):
            resp = self.client.post("/ai/insights/", json={"analysis": self.sample_analysis})
            self.assertEqual(resp.status_code, 503)
            self.assertIn("Groq API key is not configured", resp.json()["detail"])

    def test_insights_llm_failure_returns_502(self):
        """Returns 502 when LLM service throws an upstream error."""
        with patch("app.api.insights.generate_insights", side_effect=RuntimeError("OpenAI connection timeout")):
            resp = self.client.post("/ai/insights/", json={"analysis": self.sample_analysis})
            self.assertEqual(resp.status_code, 502)
            self.assertIn("LLM service error", resp.json()["detail"])


if __name__ == "__main__":
    unittest.main(verbosity=2)