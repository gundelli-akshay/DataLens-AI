"""
services/analysis.py — CSV/XLSX data analysis using Pandas.

Pure analysis logic with no FastAPI dependency.
Called by the /analyze/ router in api/analyze.py.

Design notes:
- All numpy scalar types are converted to plain Python types so the
  result is directly JSON-serialisable without a custom encoder.
- NaN and Infinity are converted to None (JSON null).
- Errors are returned as { "status": "error", "message": "..." }
  so the router can raise an appropriate HTTPException.
"""

import math
import re
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


# ── Helpers ─────────────────────────────────────────────────────

def _safe(value: Any) -> Any:
    """
    Convert a value to a JSON-serialisable Python native type.
    Handles numpy scalars, NaN, and Infinity.
    """
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    return value


# Minimum fraction of values that must parse as a date for the
# column to be classified as "date". 0.8 = 80%.
_DATE_THRESHOLD = 0.8
# Minimum number of non-null values required before attempting detection.
_DATE_MIN_SAMPLE = 3


def _detect_category(col: pd.Series) -> str:
    """
    Classify a column as 'numeric', 'date', or 'categorical'.

    Detection order:
    1. numeric  -- any integer or float dtype (includes bool, which
                   NumPy treats as a numeric type)
    2. date     -- pandas datetime64 dtype, OR an object (string)
                   column where >= _DATE_THRESHOLD of sampled values
                   successfully parse as a date via pd.to_datetime()
    3. categorical -- everything else

    The date-string heuristic samples up to 50 non-null values and
    runs pd.to_datetime(..., errors="coerce"). Values that cannot be
    parsed become NaT; we count the parsed fraction. A threshold of
    0.8 means "Engineering", "North", "Q1" (none parse as dates) stay
    categorical, while "2019-03-15", "2021-11-01" (all parse) become date.
    """
    if pd.api.types.is_numeric_dtype(col):
        return "numeric"

    if pd.api.types.is_datetime64_any_dtype(col):
        return "date"

    # Heuristic: check string/object columns for date-like values.
    # pd.api.types.is_string_dtype() returns True for both legacy
    # object dtype and newer pandas StringDtype, so it handles
    # all string column representations across pandas versions.
    if pd.api.types.is_string_dtype(col) and not pd.api.types.is_bool_dtype(col):
        non_null = col.dropna()
        if len(non_null) >= _DATE_MIN_SAMPLE:
            sample = non_null.head(50)                          # cap for speed
            # Suppress the pandas "Could not infer format" UserWarning —
            # errors="coerce" already handles unparseable values safely.
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                parsed = pd.to_datetime(sample, errors="coerce")   # NaT on failure
            parse_rate = parsed.notna().mean()
            if parse_rate >= _DATE_THRESHOLD:
                return "date"

    return "categorical"


def _numeric_stats(col: pd.Series) -> dict:
    """Return descriptive statistics for a numeric column."""
    desc = col.describe()
    return {
        "count":  _safe(desc.get("count")),
        "mean":   _safe(desc.get("mean")),
        "median": _safe(col.median()),
        "min":    _safe(desc.get("min")),
        "max":    _safe(desc.get("max")),
        "std":    _safe(desc.get("std")),
    }


def _categorical_summary(col: pd.Series, top_n: int = 5) -> dict:
    """Return unique count and the top-N most frequent values."""
    vc = col.value_counts(dropna=True).head(top_n)
    return {
        "unique_count": _safe(col.nunique()),
        "top_values": [
            {"value": str(k), "count": _safe(v)}
            for k, v in vc.items()
        ],
    }


# ── Chart data helpers ─────────────────────────────────────────

def _is_id_like(col_name: str, series: pd.Series) -> bool:
    """
    Return True if a column looks like a surrogate key rather than a metric.

    Heuristic 1 — name: column name is exactly "id", or starts/ends with
    "_id" / "id_" (e.g. "employee_id", "user_id").

    Heuristic 2 — values: integers that form a consecutive sequence starting
    at 0 or 1 (classic auto-increment primary key). This deliberately does
    NOT flag salary or other numeric columns that happen to be all-unique.
    """
    lower = col_name.lower()
    if re.search(r"(^|_)id(_|$)", lower):
        return True
    # Consecutive integer sequence: sorted values equal [min, min+1, ..., max]
    if pd.api.types.is_integer_dtype(series) and series.nunique() == len(series):
        sorted_vals = series.dropna().sort_values().reset_index(drop=True)
        if len(sorted_vals) > 0:
            expected = pd.RangeIndex(start=sorted_vals.iloc[0],
                                     stop=sorted_vals.iloc[0] + len(sorted_vals))
            if (sorted_vals.values == expected.values).all():
                return True
    return False


def _generate_chart_data(df: pd.DataFrame, col_info: list) -> list:
    """
    Produce up to 3 chart-ready data objects from the DataFrame.

    Returned list contains dicts of the form:
      { type, title, x_key, y_key, x_label, y_label, data: [...] }

    Chart types:
    1. bar     — average of a numeric metric grouped by a categorical column
    2. line    — numeric metric aggregated over a date column (year/month)
    3. scatter — two numeric metrics plotted point-by-point
    """
    charts = []

    numeric_cols = [c["name"] for c in col_info if c["category"] == "numeric"]
    cat_cols     = [c["name"] for c in col_info if c["category"] == "categorical"]
    date_cols    = [c["name"] for c in col_info if c["category"] == "date"]

    # Prefer real metric columns over surrogate IDs for bar/scatter/line charts.
    metric_cols = [n for n in numeric_cols if not _is_id_like(n, df[n])]
    if not metric_cols:
        metric_cols = numeric_cols  # fall back if everything looks like an ID

    # ── 1. Bar chart ──────────────────────────────────────────
    # Needs: a categorical column with 2–15 groups AND more than one value
    # per group (unique_count / row_count < 0.5 rules out name-like columns).
    n_rows = max(len(df), 1)
    best_cat = next(
        (
            c for c in cat_cols
            if 2 <= df[c].nunique(dropna=True) <= 15
            and df[c].nunique(dropna=True) / n_rows <= 0.5
        ),
        None,
    )
    if best_cat:
        if metric_cols:
            # Average metric per category — much more useful than raw counts.
            num_col = metric_cols[0]
            grouped = (
                df.groupby(best_cat)[num_col]
                  .mean()
                  .reset_index()
                  .sort_values(num_col, ascending=False)
                  .head(10)
            )
            charts.append({
                "type":    "bar",
                "title":   f"Average {num_col} by {best_cat}",
                "x_key":   "name",
                "y_key":   "value",
                "x_label": best_cat,
                "y_label": f"Avg {num_col}",
                "data": [
                    {"name": str(row[best_cat]), "value": _safe(row[num_col])}
                    for _, row in grouped.iterrows()
                ],
            })
        else:
            # No numeric columns — show frequency distribution.
            vc = df[best_cat].value_counts(dropna=True).head(10)
            charts.append({
                "type":    "bar",
                "title":   f"Distribution of {best_cat}",
                "x_key":   "name",
                "y_key":   "value",
                "x_label": best_cat,
                "y_label": "Count",
                "data": [{"name": str(k), "value": int(v)} for k, v in vc.items()],
            })

    # ── 2. Line chart ─────────────────────────────────────────
    # Needs: a date column + a metric column, and at least 2 distinct periods.
    if date_cols and metric_cols:
        date_col = date_cols[0]
        num_col  = metric_cols[0]

        temp = df[[date_col, num_col]].copy()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            temp[date_col] = pd.to_datetime(temp[date_col], errors="coerce")
        temp = temp.dropna()

        if len(temp) >= 2:
            date_range_days = (temp[date_col].max() - temp[date_col].min()).days
            # Group by year if span > 2 years, otherwise by month.
            if date_range_days > 730:
                temp["period"] = temp[date_col].dt.year.astype(str)
            else:
                temp["period"] = temp[date_col].dt.to_period("M").astype(str)

            grouped = (
                temp.groupby("period")[num_col]
                    .mean()
                    .reset_index()
                    .sort_values("period")
            )
            if len(grouped) >= 2:
                charts.append({
                    "type":    "line",
                    "title":   f"{num_col} over time",
                    "x_key":   "period",
                    "y_key":   "value",
                    "x_label": date_col,
                    "y_label": f"Avg {num_col}",
                    "data": [
                        {"period": str(row["period"]), "value": _safe(row[num_col])}
                        for _, row in grouped.iterrows()
                    ],
                })

    # ── 3. Scatter chart ──────────────────────────────────────
    # Needs: at least 2 metric columns and 3+ data points.
    if len(metric_cols) >= 2:
        x_col = metric_cols[0]
        y_col = metric_cols[1]
        sample = df[[x_col, y_col]].dropna().head(200)
        if len(sample) >= 3:
            charts.append({
                "type":    "scatter",
                "title":   f"{y_col} vs {x_col}",
                "x_key":   "x",
                "y_key":   "y",
                "x_label": x_col,
                "y_label": y_col,
                "data": [
                    {"x": _safe(row[x_col]), "y": _safe(row[y_col])}
                    for _, row in sample.iterrows()
                ],
            })

    return charts  # maximum 3 charts


# ── Core analyser ───────────────────────────────────────────────

def analyze_dataframe(df: pd.DataFrame, filename: str, file_type: str) -> dict:
    """
    Analyse a Pandas DataFrame and return a fully JSON-safe summary dict.

    Structure returned:
    {
      "status":               "success",
      "filename":             str,
      "file_type":            "CSV" | "XLSX",
      "shape":                { "rows": int, "columns": int },
      "column_names":         [str, ...],
      "columns":              [{ name, dtype, category, missing_count,
                                 missing_pct, unique_count }, ...],
      "missing_total":        int,
      "duplicate_rows":       int,
      "numeric_summary":      { col_name: { count, mean, median,
                                            min, max, std }, ... },
      "categorical_summary":  { col_name: { unique_count,
                                            top_values: [{value, count}] }, ... },
    }
    """
    rows, cols = df.shape

    column_info = []
    numeric_summary = {}
    categorical_summary = {}

    for col_name in df.columns:
        series = df[col_name]
        missing = int(series.isna().sum())
        missing_pct = round((missing / rows * 100), 2) if rows > 0 else 0.0
        unique = _safe(series.nunique(dropna=True))
        category = _detect_category(series)

        column_info.append({
            "name":          str(col_name),
            "dtype":         str(series.dtype),
            "category":      category,
            "missing_count": missing,
            "missing_pct":   missing_pct,
            "unique_count":  unique,
        })

        if category == "numeric":
            numeric_summary[str(col_name)] = _numeric_stats(series)
        elif category == "categorical":
            categorical_summary[str(col_name)] = _categorical_summary(series)

    total_missing = int(df.isna().sum().sum())
    duplicate_rows = int(df.duplicated().sum())

    return {
        "status":               "success",
        "filename":             filename,
        "file_type":            file_type,
        "shape":                {"rows": rows, "columns": cols},
        "column_names":         [str(c) for c in df.columns],
        "columns":              column_info,
        "missing_total":        total_missing,
        "duplicate_rows":       duplicate_rows,
        "numeric_summary":      numeric_summary,
        "categorical_summary":  categorical_summary,
        "chart_data":           _generate_chart_data(df, column_info),
    }


# ── Format-specific readers ─────────────────────────────────────

def analyze_csv(file_path: Path, original_filename: str) -> dict:
    """
    Read a CSV file into a DataFrame and return analysis.
    Falls back to latin-1 encoding if UTF-8 fails.
    """
    try:
        df = pd.read_csv(
            file_path,
            encoding="utf-8",
            on_bad_lines="skip",   # skip rows with too many/few fields
        )
    except UnicodeDecodeError:
        try:
            df = pd.read_csv(
                file_path,
                encoding="latin-1",
                on_bad_lines="skip",
            )
        except Exception as exc:
            return {"status": "error", "message": f"Could not read CSV file '{original_filename}'. The file format may be invalid or corrupt."}
    except Exception as exc:
        return {"status": "error", "message": f"Could not read CSV file '{original_filename}'. The file format may be invalid or corrupt."}

    if df.empty:
        return {
            "status": "error",
            "message": "The CSV file is empty or contains no readable rows.",
        }

    return analyze_dataframe(df, original_filename, "CSV")


def analyze_xlsx(file_path: Path, original_filename: str) -> dict:
    """
    Read the first sheet of an XLSX workbook and return analysis.
    The sheet name is included in the result for transparency.
    """
    try:
        xl = pd.ExcelFile(file_path, engine="openpyxl")
        sheet_name = xl.sheet_names[0]
        df = xl.parse(sheet_name)
    except Exception as exc:
        return {"status": "error", "message": f"Could not read XLSX file '{original_filename}'. The file format may be invalid or corrupt."}

    if df.empty:
        return {
            "status": "error",
            "message": "The XLSX file is empty or contains no readable rows.",
        }

    result = analyze_dataframe(df, original_filename, "XLSX")
    result["sheet_name"] = sheet_name   # add XLSX-specific metadata
    return result