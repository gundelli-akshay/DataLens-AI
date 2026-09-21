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


def _detect_category(col_name: str, col: pd.Series) -> str:
    """
    Classify a column as 'id', 'numeric', 'date', or 'categorical'.

    Detection order:
    1. id          -- identifier/ID-like column (e.g. 'id', '*_id', consecutive/near-unique keys)
    2. numeric     -- any integer or float dtype
    3. date        -- pandas datetime64 or string column where >= _DATE_THRESHOLD parse as dates
    4. categorical -- everything else
    """
    if _is_id_column(col_name, col):
        return "id"

    if pd.api.types.is_numeric_dtype(col):
        return "numeric"

    if pd.api.types.is_datetime64_any_dtype(col):
        return "date"

    # Heuristic: check string/object columns for date-like values.
    if pd.api.types.is_string_dtype(col) and not pd.api.types.is_bool_dtype(col):
        non_null = col.dropna()
        if len(non_null) >= _DATE_MIN_SAMPLE:
            sample = non_null.head(50)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                parsed = pd.to_datetime(sample, errors="coerce")
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

def _is_id_column(col_name: str, series: pd.Series) -> bool:
    """
    Return True if a column represents an identifier/ID-like field rather than a metric or category.

    Heuristics:
    1. Name-based match:
       Exact match or prefix/suffix with id, uuid, guid, identifier, pk (e.g. 'id', 'match_id', 'user_id', 'id_num').
       Verified if non-null count has reasonable uniqueness (> 20% or unique == count).
    2. Auto-increment sequence:
       Consecutive integer sequence [min, min+1, ..., max] (classic primary key / index).
    3. Near-unique values:
       For datasets with >= 8 non-null rows:
       - If >= 95% unique integers with values in reasonable range (excluding common metrics).
       - If >= 95% unique strings without spaces (codes, hashes, UUIDs, identifiers),
         excluding descriptive text columns (names, titles, comments, addresses).
    """
    lower = str(col_name).lower().strip()

    # Exclude common metric/measurement terms unless explicitly containing '_id' or 'id_'
    metric_stems = [
        "salary", "revenue", "amount", "price", "cost", "score", "rate", "rating",
        "fare", "age", "temp", "profit", "sales", "discount", "margin", "weight",
        "height", "run", "runs", "wicket", "wickets", "point", "points", "year", "date"
    ]
    if any(m in lower for m in metric_stems) and not re.search(r"(^|_)(id|uuid|guid|pk)(_|$)", lower):
        return False

    # Exclude descriptive text columns unless explicitly containing '_id'
    text_stems = ["name", "title", "description", "desc", "comment", "city", "country", "address", "team"]
    if any(t in lower for t in text_stems) and not re.search(r"(^|_)(id|uuid|guid|pk)(_|$)", lower):
        return False

    # 1. Name-based identifier match
    has_id_name = bool(re.search(r"(^|_)(id|uuid|guid|identifier|pk)(_|$)", lower))

    non_null = series.dropna()
    n_count = len(non_null)
    if n_count == 0:
        return has_id_name

    n_unique = non_null.nunique()
    uniqueness_ratio = n_unique / n_count

    if has_id_name:
        if n_unique > 1 and (uniqueness_ratio >= 0.2 or n_unique >= 5 or n_unique == n_count):
            return True

    # Check minimum row threshold for statistical uniqueness heuristics
    if n_count < 8:
        return False

    # 2. Consecutive integer sequence (classic auto-increment ID)
    if pd.api.types.is_integer_dtype(series) and n_unique == n_count:
        sorted_vals = non_null.sort_values().reset_index(drop=True)
        if len(sorted_vals) > 0:
            expected = pd.RangeIndex(start=sorted_vals.iloc[0], stop=sorted_vals.iloc[0] + len(sorted_vals))
            if (sorted_vals.values == expected.values).all():
                return True

    # 3. Near-unique heuristic (>= 95% unique)
    if uniqueness_ratio >= 0.95:
        # High-cardinality integers starting >= 0 (e.g. ticket numbers, match ids without 'id' in name)
        if pd.api.types.is_integer_dtype(series):
            # Guard against large numbers that represent metrics: max should be within reasonable multiple of count
            if non_null.min() >= 0 and (non_null.max() <= n_count * 100 or has_id_name):
                return True

        # High-cardinality strings without spaces (UUIDs, transaction codes, tokens)
        if pd.api.types.is_string_dtype(series):
            sample = non_null.head(30).astype(str)
            space_ratio = sample.str.contains(r"\s").mean()
            if space_ratio < 0.15:  # Identifiers rarely have whitespace
                return True

    return False


def _is_id_like(col_name: str, series: pd.Series) -> bool:
    """Alias for _is_id_column for backward compatibility."""
    return _is_id_column(col_name, series)


def _is_low_cardinality_or_ordinal(col_name: str, series: pd.Series) -> bool:
    """
    Return True if a numeric column is a low-cardinality discrete, ordinal, or coded rating
    (such as Education, JobLevel, satisfaction ratings, survey scales) rather than
    a continuous numeric measurement.
    """
    non_null = series.dropna()
    if len(non_null) == 0:
        return True

    n_unique = non_null.nunique()

    # Low cardinality (<= 6 unique values) is discrete/ordinal or binary
    if n_unique <= 6:
        return True

    lower = str(col_name).lower().strip()
    ordinal_terms = [
        "level", "rating", "satisfaction", "education", "tier", "grade",
        "scale", "rank", "score", "involvement", "balance", "status", "priority",
        "stage", "performance"
    ]

    # Coded/ordinal naming with <= 12 unique values
    if any(term in lower for term in ordinal_terms) and n_unique <= 12:
        return True

    # Integers with <= 8 unique values
    if pd.api.types.is_integer_dtype(series) and n_unique <= 8:
        return True

    return False


def _generate_chart_data(df: pd.DataFrame, col_info: list) -> list:
    """
    Produce up to 3 chart-ready data objects from the DataFrame prioritizing meaningful relationships.

    Returned list contains dicts of the form:
      { type, title, x_key, y_key, x_label, y_label, data: [...] }

    Prioritization heuristics:
    1. Bar chart: Finds the (categorical, numeric) pair where category groups have
       the highest meaningful variance in metric averages. Falls back to top categorical distribution.
    2. Line chart: Finds a date column and pairs with the metric showing most variation over time.
    3. Scatter chart: Calculates pairwise Pearson correlations between numeric metrics and selects
       the pair with the strongest non-trivial correlation (or highest mutual variance).
    4. Fallback chart: If no date column exists, provides a secondary distinctive category or distribution.
    """
    charts = []

    numeric_cols = [c["name"] for c in col_info if c["category"] == "numeric"]
    cat_cols     = [c["name"] for c in col_info if c["category"] == "categorical"]
    date_cols    = [c["name"] for c in col_info if c["category"] == "date"]

    # Filter out ID-like columns and constant columns with 0 variance
    metric_cols = []
    for n in numeric_cols:
        if _is_id_like(n, df[n]):
            continue
        s = df[n].dropna()
        if len(s) >= 2 and s.nunique() > 1:
            metric_cols.append(n)

    if not metric_cols:
        metric_cols = [n for n in numeric_cols if df[n].dropna().nunique() > 1] or numeric_cols

    n_rows = max(len(df), 1)

    # Valid candidate categories: 2 to 20 unique values, not unique IDs
    candidate_cats = [
        c for c in cat_cols
        if 2 <= df[c].nunique(dropna=True) <= 20
        and df[c].nunique(dropna=True) / n_rows <= 0.6
    ]

    selected_bar_cat = None
    selected_bar_num = None

    # ── 1. Primary Bar Chart: Highest-variance (Category, Metric) relationship ──
    if candidate_cats and metric_cols:
        best_score = -1.0
        best_pair = (candidate_cats[0], metric_cols[0])

        for cat in candidate_cats[:5]:
            cat_counts = df[cat].value_counts(dropna=True)
            # Penalize heavily unbalanced categories (e.g. 99% in one class)
            balance_factor = min(cat_counts) / max(cat_counts.max(), 1)

            for num in metric_cols[:5]:
                try:
                    group_means = df.groupby(cat)[num].mean().dropna()
                    if len(group_means) >= 2:
                        overall_std = df[num].std()
                        if overall_std and overall_std > 0:
                            # Relative spread between category averages
                            variance_score = (group_means.std() / overall_std) * (0.5 + 0.5 * balance_factor)
                        else:
                            variance_score = group_means.std()

                        if variance_score > best_score:
                            best_score = variance_score
                            best_pair = (cat, num)
                except Exception:
                    continue

        selected_bar_cat, selected_bar_num = best_pair
        grouped = (
            df.groupby(selected_bar_cat)[selected_bar_num]
              .mean()
              .reset_index()
              .sort_values(selected_bar_num, ascending=False)
              .head(10)
        )
        charts.append({
            "type":    "bar",
            "title":   f"Average {selected_bar_num} by {selected_bar_cat}",
            "x_key":   "name",
            "y_key":   "value",
            "x_label": selected_bar_cat,
            "y_label": f"Avg {selected_bar_num}",
            "data": [
                {"name": str(row[selected_bar_cat]), "value": _safe(row[selected_bar_num])}
                for _, row in grouped.iterrows()
            ],
        })

    elif candidate_cats:
        # No numeric columns available — frequency distribution of the best category
        selected_bar_cat = candidate_cats[0]
        vc = df[selected_bar_cat].value_counts(dropna=True).head(10)
        charts.append({
            "type":    "bar",
            "title":   f"Distribution of {selected_bar_cat}",
            "x_key":   "name",
            "y_key":   "value",
            "x_label": selected_bar_cat,
            "y_label": "Count",
            "data": [{"name": str(k), "value": int(v)} for k, v in vc.items()],
        })

    # ── 2. Line chart: Time-series progression ─────────────────
    line_added = False
    if date_cols and metric_cols:
        date_col = date_cols[0]
        # Choose metric with highest variance over time
        num_col = selected_bar_num or metric_cols[0]

        temp = df[[date_col, num_col]].copy()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            temp[date_col] = pd.to_datetime(temp[date_col], errors="coerce")
        temp = temp.dropna()

        if len(temp) >= 2:
            date_range_days = (temp[date_col].max() - temp[date_col].min()).days
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
                line_added = True

    # ── 3. Scatter chart: Best continuous metric correlation ──
    if len(metric_cols) >= 2:
        # Prioritize continuous numeric columns over low-cardinality ordinal ratings
        continuous_metrics = [
            n for n in metric_cols
            if not _is_low_cardinality_or_ordinal(n, df[n])
        ]

        # Use continuous metrics if >= 2 available; otherwise fall back to metrics sorted by highest unique values
        scatter_pool = (
            continuous_metrics
            if len(continuous_metrics) >= 2
            else sorted(metric_cols, key=lambda n: df[n].nunique(dropna=True), reverse=True)
        )

        best_corr_pair = (scatter_pool[0], scatter_pool[1])
        highest_corr = -1.0

        # Calculate pairwise correlation on continuous pool
        sub_df = df[scatter_pool[:8]].dropna()
        if len(sub_df) >= 4:
            try:
                corr_matrix = sub_df.corr(method="pearson")
                for i in range(len(corr_matrix.columns)):
                    for j in range(i + 1, len(corr_matrix.columns)):
                        c1 = corr_matrix.columns[i]
                        c2 = corr_matrix.columns[j]
                        val = corr_matrix.iloc[i, j]
                        if pd.notna(val):
                            abs_val = abs(val)
                            # Avoid identical duplicate columns (|r| >= 0.9999)
                            if abs_val < 0.9999 and abs_val > highest_corr:
                                highest_corr = abs_val
                                best_corr_pair = (c1, c2)
            except Exception:
                pass

        x_col, y_col = best_corr_pair
        sample = df[[x_col, y_col]].dropna().head(250)
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

    # ── 4. Additional Charts: Secondary Category Breakdowns ──
    if len(charts) < 4 and len(candidate_cats) >= 2 and metric_cols:
        used_cats = {selected_bar_cat}
        for next_cat in candidate_cats:
            if next_cat in used_cats:
                continue
            if len(charts) >= 4:
                break
            
            target_metric = next((m for m in metric_cols if m != selected_bar_num), metric_cols[0])
            try:
                grouped2 = (
                    df.groupby(next_cat)[target_metric]
                      .mean()
                      .reset_index()
                      .sort_values(target_metric, ascending=False)
                      .head(8)
                )
                charts.append({
                    "type":    "bar",
                    "title":   f"Average {target_metric} by {next_cat}",
                    "x_key":   "name",
                    "y_key":   "value",
                    "x_label": next_cat,
                    "y_label": f"Avg {target_metric}",
                    "data": [
                        {"name": str(row[next_cat]), "value": _safe(row[target_metric])}
                        for _, row in grouped2.iterrows()
                    ],
                })
                used_cats.add(next_cat)
            except Exception:
                continue

    return charts[:4]


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
        category = _detect_category(str(col_name), series)

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