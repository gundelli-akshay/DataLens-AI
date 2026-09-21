"""
tests/test_analysis_charts.py - Unit tests for intelligent chart selection and AI grounding.
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pandas as pd
from app.services.analysis import analyze_dataframe, _generate_chart_data


def test_chart_selection_prioritizes_differentiating_category():
    # Dataset where 'department' clearly separates salary, while 'gender' has almost identical average salary
    data = {
        "gender": ["F", "M", "F", "M", "F", "M", "F", "M"],
        "department": ["Engineering", "Engineering", "Engineering", "Engineering", "Support", "Support", "Support", "Support"],
        "salary": [120000, 122000, 118000, 121000, 45000, 46000, 44000, 47000],
        "years_experience": [10, 11, 9, 10, 2, 2, 1, 3],
    }
    df = pd.DataFrame(data)
    result = analyze_dataframe(df, "employees.csv", "CSV")

    charts = result.get("chart_data", [])
    assert len(charts) >= 2

    # Primary bar chart should choose 'department' because of high variance in salary
    bar_charts = [c for c in charts if c["type"] == "bar"]
    assert len(bar_charts) >= 1
    primary_bar = bar_charts[0]
    assert "department" in primary_bar["title"].lower() or "department" in primary_bar["x_label"].lower()

    # Scatter chart should pair salary and years_experience (high correlation)
    scatter_charts = [c for c in charts if c["type"] == "scatter"]
    assert len(scatter_charts) >= 1
    scatter = scatter_charts[0]
    assert ("salary" in scatter["title"].lower() and "years_experience" in scatter["title"].lower())


def test_chart_selection_ignores_constant_columns():
    data = {
        "category": ["A", "B", "C", "D"],
        "constant_num": [100, 100, 100, 100],  # 0 variance
        "real_metric": [10, 25, 50, 80],
    }
    df = pd.DataFrame(data)
    result = analyze_dataframe(df, "test.csv", "CSV")
    charts = result.get("chart_data", [])

    for c in charts:
        assert "constant_num" not in c["title"].lower()


def test_fallback_chart_when_no_dates():
    # Dataset with 2 categories and metrics, but no date column
    data = {
        "segment": ["Enterprise", "SMB", "Enterprise", "SMB"],
        "region": ["North", "North", "South", "South"],
        "revenue": [5000, 1000, 6000, 1200],
        "profit": [2000, 300, 2400, 350],
    }
    df = pd.DataFrame(data)
    result = analyze_dataframe(df, "sales.csv", "CSV")
    charts = result.get("chart_data", [])

    # Even without date column, intelligent selection produces up to 3 informative charts
    assert len(charts) == 3
