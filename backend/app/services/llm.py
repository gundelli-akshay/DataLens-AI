"""
services/llm.py - LLM service for explaining dataset analysis.

Uses Groq API to interpret and contextualize programmatic findings from
services/analysis.py.
Configured via environment variables (app.core.config.settings).

Constraint:
- The LLM must strictly explain findings and not calculate or invent numbers.
"""

from typing import Any
from groq import Groq

from app.core.config import settings

SYSTEM_PROMPT = (
    "You are DataLens AI's expert data analyst.\n"
    "Your role is to explain, interpret, and provide analytical context for the dataset findings provided.\n\n"
    "CRITICAL CONSTRAINTS:\n"
    "1. Do NOT calculate, estimate, or invent new numeric values, percentages, or statistics.\n"
    "2. Rely exclusively on the numbers and facts provided in the analysis summary.\n"
    "3. Highlight key patterns, notable distributions, potential data quality concerns (e.g. missing values or duplicate rows), and predominant categories.\n"
    "4. Structure your response clearly using markdown with the following sections:\n"
    "   - ### Executive Summary\n"
    "   - ### Key Patterns & Distributions\n"
    "   - ### Data Quality & Observations\n"
    "   - ### Recommended Next Steps\n"
    "5. Keep the tone professional, concise, and accessible to business and technical stakeholders."
)

def format_analysis_for_llm(data: dict[str, Any]) -> str:
    """
    Format programmatic analysis results into a structured prompt for the LLM.
    """
    filename = data.get("filename", "Dataset")
    file_type = data.get("file_type", "Unknown")
    shape = data.get("shape", {})
    rows = shape.get("rows", 0)
    cols = shape.get("columns", 0)
    missing_total = data.get("missing_total", 0)
    duplicate_rows = data.get("duplicate_rows", 0)

    lines = [
        f"Dataset: {filename} ({file_type})",
        f"Dimensions: {rows} rows, {cols} columns",
        f"Data Quality: {missing_total} total missing values, {duplicate_rows} duplicate rows",
        "",
        "Columns Overview:",
    ]

    for col in data.get("columns", []):
        name = col.get("name")
        dtype = col.get("dtype")
        cat = col.get("category")
        missing = col.get("missing_count", 0)
        unique = col.get("unique_count", 0)
        lines.append(f"  - {name} ({cat}, dtype: {dtype}): {unique} unique values, {missing} missing")

    numeric_summary = data.get("numeric_summary", {})
    if numeric_summary:
        lines.append("")
        lines.append("Numeric Columns Statistics (Pre-calculated):")
        for col, stats in numeric_summary.items():
            lines.append(
                f"  - {col}: mean={stats.get('mean')}, median={stats.get('median')}, "
                f"std={stats.get('std')}, min={stats.get('min')}, max={stats.get('max')}, count={stats.get('count')}"
            )

    categorical_summary = data.get("categorical_summary", {})
    if categorical_summary:
        lines.append("")
        lines.append("Categorical Columns Top Values (Pre-calculated):")
        for col, summary in categorical_summary.items():
            unique_cnt = summary.get("unique_count", 0)
            top_vals = summary.get("top_values", [])
            top_str = ", ".join(f"'{v.get('value')}': {v.get('count')}" for v in top_vals)
            lines.append(f"  - {col} ({unique_cnt} unique): {top_str}")

    return "\n".join(lines)

def generate_insights(analysis_data: dict[str, Any], client: Groq | None = None) -> dict[str, Any]:
    """
    Generate natural language insights from programmatic analysis using LLM.

    Args:
        analysis_data: The structured dictionary from services/analysis.py.
        client: Optional Groq client instance (useful for mocking/testing).

    Returns:
        dict with status, insights text, and model name.

    Raises:
        ValueError if API key is not configured.
        Exception on API / LLM failures.
    """
    api_key = settings.groq_api_key
    if not client and not api_key:
        raise ValueError(
            "Groq API key is not configured. "
            "Please set GROQ_API_KEY in your environment (.env file)."
        )

    prompt = format_analysis_for_llm(analysis_data)

    if client is None:
        client = Groq(api_key=api_key)

    response = client.chat.completions.create(
        model=settings.groq_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Please explain and synthesize these dataset analysis results:\n\n{prompt}"},
        ],
        temperature=0.3,
    )

    insights = response.choices[0].message.content

    return {
        "status": "success",
        "insights": insights,
        "model": settings.groq_model,
    }
