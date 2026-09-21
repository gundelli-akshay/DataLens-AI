"""
tests/test_id_detection.py - Unit tests for identifier/ID-like column detection and exclusion.

Validates:
1. Columns named 'id', 'match_id', 'user_id', or near-unique keys are categorized as 'id'.
2. ID columns are marked as 'id' in column metadata (rendered as 'ID' badge in UI).
3. ID columns are excluded from numeric_summary and categorical_summary.
4. ID columns are never selected for bar, line, or scatter charts.
5. True numeric metrics (e.g. salary, win_by_runs) and categories (e.g. team1, city) remain uninhibited.
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pandas as pd
from app.services.analysis import analyze_dataframe, _detect_category, _is_id_column


def test_is_id_column_detection():
    # 1. Standard 'id' column from matches.csv
    match_ids = pd.Series(list(range(1, 101)), name="id")
    assert _is_id_column("id", match_ids) is True
    assert _detect_category("id", match_ids) == "id"

    # 2. Suffixed / prefixed identifier names
    user_ids = pd.Series(list(range(1001, 1050)), name="user_id")
    assert _is_id_column("user_id", user_ids) is True
    assert _detect_category("user_id", user_ids) == "id"

    match_id_col = pd.Series(list(range(50)), name="match_id")
    assert _is_id_column("match_id", match_id_col) is True
    assert _detect_category("match_id", match_id_col) == "id"

    # 3. Near-unique sequential integers without 'id' in the name
    seq_col = pd.Series(list(range(100)), name="row_sequence")
    assert _is_id_column("row_sequence", seq_col) is True
    assert _detect_category("row_sequence", seq_col) == "id"

    # 4. Near-unique string codes / UUIDs
    uuid_col = pd.Series([f"code_{i:04d}" for i in range(100)], name="transaction_code")
    assert _is_id_column("transaction_code", uuid_col) is True
    assert _detect_category("transaction_code", uuid_col) == "id"


def test_measurements_and_categories_not_flagged_as_id():
    # Salary metric with unique numbers
    salaries = pd.Series([50000 + i * 1500 for i in range(50)], name="salary")
    assert _is_id_column("salary", salaries) is False
    assert _detect_category("salary", salaries) == "numeric"

    # Sports runs metric (as in matches.csv)
    runs = pd.Series([0, 14, 25, 0, 140, 20, 0, 5, 0, 12], name="win_by_runs")
    assert _is_id_column("win_by_runs", runs) is False
    assert _detect_category("win_by_runs", runs) == "numeric"

    # Team / Name categories
    teams = pd.Series(["Mumbai Indians", "CSK", "RCB", "KKR"] * 10, name="team1")
    assert _is_id_column("team1", teams) is False
    assert _detect_category("team1", teams) == "categorical"


def test_matches_dataset_simulation_id_exclusion():
    # Simulate matches.csv structure
    n_rows = 60
    data = {
        "id": list(range(1, n_rows + 1)),                             # ID
        "season": [2017, 2018, 2019] * 20,                            # Numeric/Category
        "city": ["Hyderabad", "Pune", "Rajkot", "Indore"] * 15,       # Categorical
        "team1": ["Sunrisers", "Rising Pune", "Gujarat Lions"] * 20,   # Categorical
        "team2": ["RCB", "Mumbai Indians", "KKR"] * 20,               # Categorical
        "win_by_runs": [35, 0, 10, 0, 15, 0] * 10,                    # Numeric metric
        "win_by_wickets": [0, 7, 0, 10, 0, 6] * 10,                   # Numeric metric
    }
    df = pd.DataFrame(data)
    result = analyze_dataframe(df, "matches.csv", "CSV")

    columns = result["columns"]
    id_col_meta = next((c for c in columns if c["name"] == "id"), None)
    assert id_col_meta is not None
    # 1. Must be categorized as 'id'
    assert id_col_meta["category"] == "id"

    # 2. Excluded from numeric_summary
    assert "id" not in result["numeric_summary"]
    assert "win_by_runs" in result["numeric_summary"]
    assert "win_by_wickets" in result["numeric_summary"]

    # 3. Excluded from categorical_summary
    assert "id" not in result["categorical_summary"]
    assert "team1" in result["categorical_summary"]

    # 4. Excluded from chart_data
    charts = result["chart_data"]
    for chart in charts:
        title = chart["title"].lower()
        x_label = chart.get("x_label", "").lower()
        y_label = chart.get("y_label", "").lower()
        assert "average id" not in title
        assert "distribution of id" not in title
        assert "id vs" not in title
        assert "vs id" not in title
        assert x_label != "id"
        assert y_label != "avg id"
