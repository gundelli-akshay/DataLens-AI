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


RAG_SYSTEM_PROMPT = (
    "You are DataLens AI's expert document assistant.\n"
    "Your role is to answer user questions concisely, factually, and truthfully based ONLY on the provided context excerpts below.\n\n"
    "CRITICAL CONSTRAINTS:\n"
    "1. Answer ONLY using information explicitly stated in the provided context excerpts.\n"
    "2. Do NOT invent, extrapolate, guess, or incorporate any outside knowledge or unstated facts.\n"
    "3. If the context does not contain sufficient facts to answer the question, clearly state: "
    "'The provided document does not contain sufficient information to answer this question.'\n"
    "4. Keep your answer concise, direct, and factual.\n"
    "5. When stating facts from the context, reference the source locations (e.g. Page X or Paragraph Y) wherever applicable."
)


def format_rag_context(chunks: list[dict[str, Any]]) -> str:
    """
    Format retrieved document chunks into structured context for the LLM.
    """
    if not chunks:
        return "No relevant document excerpts were found."

    parts = []
    for idx, chunk in enumerate(chunks, 1):
        source_label = ""
        if chunk.get("page_number") is not None:
            source_label = f"Page {chunk['page_number']}"
        elif chunk.get("paragraph_number") is not None:
            source_label = f"Paragraph {chunk['paragraph_number']}"
        else:
            source_label = "Excerpt"

        filename = chunk.get("filename", "Document")
        header = f"--- Context Excerpt [{idx}] | {filename} ({source_label}) ---"
        text = chunk.get("text", "").strip()
        parts.append(f"{header}\n{text}")

    return "\n\n".join(parts)


def generate_rag_answer(
    question: str,
    chunks: list[dict[str, Any]],
    client: Groq | None = None,
) -> dict[str, Any]:
    """
    Generate a concise grounded answer to the user's question using Groq LLM
    and the retrieved document context chunks.

    Args:
        question: The user's question string.
        chunks: List of retrieved chunk dictionaries from RAG retrieval.
        client: Optional Groq client instance (useful for mocking/testing).

    Returns:
        dict with status, answer, sources, and model.

    Raises:
        ValueError if question is empty or API key is not configured.
        Exception on API / LLM failures.
    """
    if not question or not question.strip():
        raise ValueError("Question cannot be empty.")

    if not chunks:
        return {
            "status": "success",
            "answer": "The provided document does not contain sufficient information to answer this question.",
            "sources": [],
            "model": settings.groq_model,
        }

    api_key = settings.groq_api_key
    if not client and not api_key:
        raise ValueError(
            "Groq API key is not configured. "
            "Please set GROQ_API_KEY in your environment (.env file)."
        )

    context_str = format_rag_context(chunks)

    user_content = (
        f"Context excerpts from document:\n\n"
        f"{context_str}\n\n"
        f"User Question: {question.strip()}\n\n"
        "Answer strictly based on the context excerpts above:"
    )

    if client is None:
        client = Groq(api_key=api_key)

    response = client.chat.completions.create(
        model=settings.groq_model,
        messages=[
            {"role": "system", "content": RAG_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.1,
    )

    answer_text = response.choices[0].message.content

    # Compile unique source references
    sources = []
    seen = set()
    for c in chunks:
        page_num = c.get("page_number")
        para_num = c.get("paragraph_number")
        fname = c.get("filename", "")
        ref_key = (fname, page_num, para_num)
        if ref_key not in seen:
            seen.add(ref_key)
            src_label = (
                f"Page {page_num}"
                if page_num is not None
                else f"Paragraph {para_num}"
                if para_num is not None
                else "Document"
            )
            raw_text = c.get("text", "").strip()
            snippet = raw_text[:160] + ("..." if len(raw_text) > 160 else "")
            sources.append({
                "source": src_label,
                "filename": fname,
                "page_number": page_num,
                "paragraph_number": para_num,
                "snippet": snippet,
                "score": c.get("score"),
            })

    return {
        "status": "success",
        "answer": answer_text,
        "sources": sources,
        "model": settings.groq_model,
    }
