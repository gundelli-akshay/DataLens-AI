"""
tests/test_hr_matches_fixes.py - Tests for empty AI response resilience and low-cardinality chart exclusion.

Validates:
1. Groq AI empty response is handled gracefully without crashing with 'AI model returned an empty message'.
2. Fallback synthesis is grounded, structured, and succeeds on valid datasets.
3. Scatter plot selection excludes low-cardinality coded/ordinal fields (Education, JobLevel, JobSatisfaction)
   and strictly prefers continuous numeric metrics (MonthlyIncome, Age, TotalWorkingYears).
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pandas as pd
from app.services.llm import generate_insights, _generate_grounded_fallback_insights
from app.services.analysis import analyze_dataframe, _is_low_cardinality_or_ordinal


def test_empty_ai_response_fallback_resilience():
    """Verify that an empty message from the LLM returns grounded fallback instead of crashing."""
    sample_analysis = {
        "status": "success",
        "filename": "hr_data.csv",
        "file_type": "CSV",
        "shape": {"rows": 100, "columns": 5},
        "missing_total": 0,
        "duplicate_rows": 0,
        "numeric_summary": {
            "MonthlyIncome": {"mean": 6500.0, "median": 5100.0, "min": 1000.0, "max": 20000.0, "std": 3200.0, "count": 100}
        },
        "categorical_summary": {
            "Department": {"unique_count": 3, "top_values": [{"value": "R&D", "count": 60}, {"value": "Sales", "count": 40}]}
        },
    }

    # Simulate Groq returning a message with empty content
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = ""  # Empty string response
    mock_choice.message.reasoning_content = None
    mock_choice.message.reasoning = None

    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_resp

    result = generate_insights(sample_analysis, client=mock_client)
    assert result["status"] == "success"
    assert "insights" in result
    assert len(result["insights"]) > 0
    # Must contain structured grounded markdown sections
    assert "Executive Summary" in result["insights"]
    assert "MonthlyIncome" in result["insights"]


def test_ai_reasoning_content_extraction():
    """Verify that reasoning models returning output in reasoning_content are extracted."""
    sample_analysis = {"shape": {"rows": 10, "columns": 2}}
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = None
    mock_choice.message.reasoning_content = "### Executive Summary\nExtracted from reasoning tokens."
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_resp

    result = generate_insights(sample_analysis, client=mock_client)
    assert result["status"] == "success"
    assert "Extracted from reasoning tokens" in result["insights"]


def test_scatter_excludes_low_cardinality_ordinal_fields():
    """Verify scatter plots avoid Education/JobLevel and prefer continuous variables."""
    n_rows = 50
    data = {
        # Low cardinality / ordinal ratings
        "Education": [1, 2, 3, 4, 5] * 10,
        "JobLevel": [1, 2, 3, 4, 5] * 10,
        "JobSatisfaction": [1, 2, 3, 4, 1] * 10,
        # Continuous numeric metrics
        "Age": [22 + (i % 40) for i in range(n_rows)],
        "MonthlyIncome": [2500 + i * 450 for i in range(n_rows)],
        "TotalWorkingYears": [1 + (i % 35) for i in range(n_rows)],
    }
    df = pd.DataFrame(data)

    # Validate helper detection
    assert _is_low_cardinality_or_ordinal("Education", df["Education"]) is True
    assert _is_low_cardinality_or_ordinal("JobLevel", df["JobLevel"]) is True
    assert _is_low_cardinality_or_ordinal("JobSatisfaction", df["JobSatisfaction"]) is True
    assert _is_low_cardinality_or_ordinal("MonthlyIncome", df["MonthlyIncome"]) is False
    assert _is_low_cardinality_or_ordinal("Age", df["Age"]) is False

    result = analyze_dataframe(df, "hr_test.csv", "CSV")
    charts = result.get("chart_data", [])

    scatter_charts = [c for c in charts if c["type"] == "scatter"]
    assert len(scatter_charts) >= 1
    scatter = scatter_charts[0]

    title = scatter["title"].lower()
    x_label = scatter.get("x_label", "").lower()
    y_label = scatter.get("y_label", "").lower()

    # Scatter MUST NOT use ordinal ratings
    for ordinal_col in ["education", "joblevel", "jobsatisfaction"]:
        assert ordinal_col not in title
        assert x_label != ordinal_col
        assert y_label != ordinal_col

    # Scatter MUST use continuous metrics
    continuous_terms = ["monthlyincome", "age", "totalworkingyears"]
    assert any(term in title for term in continuous_terms)
