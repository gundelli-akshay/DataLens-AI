import re
import time
"""
services/llm.py - LLM service for explaining dataset analysis and RAG Q&A.

Uses Groq API to interpret and contextualize programmatic findings from
services/analysis.py and answer document questions grounded strictly in retrieved context.
Configured via environment variables (app.core.config.settings).

Constraint:
- The LLM must strictly explain findings and not calculate or invent numbers.
- In RAG mode, the LLM must strictly ground answers in retrieved context excerpts and cite sources.
"""

from typing import Any
import logging
from groq import (
    Groq,
    APIConnectionError,
    RateLimitError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    APIError,
    GroqError,
)

from app.core.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are DataLens AI's expert data analyst.
Your role is to explain, interpret, and provide rigorous analytical context for the dataset findings provided.

CRITICAL GROUNDING CONSTRAINTS:
1. Do NOT calculate, estimate, or invent new numeric values, percentages, or statistics.
2. Rely exclusively on the numbers and facts provided in the analysis summary.
3. Only state factual conclusions directly supported by the calculated analysis numbers and distributions provided.
4. Do NOT invent, extrapolate, or state causal claims or correlations unless explicitly evidenced by the calculated statistics.
5. If suggesting possible business drivers, domain implications, or underlying causes, you MUST explicitly label them as '[Hypothesis]' or '[Unverified Assumption]' so the user knows they are not measured facts.
6. Highlight verified data quality facts (missing values, duplicate rows, skewness between mean and median) strictly from the provided summary.
7. Structure your response clearly using clean markdown with the following sections:
   - ### Executive Summary
   - ### Key Patterns & Distributions
   - ### Data Quality & Observations
   - ### Recommended Next Steps
8. Format key comparisons in a clean markdown table when suitable to clearly present distributions.
9. Keep the tone professional, objective, and clearly distinguish measured facts from analytical hypotheses."""


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

    
    lines.append("")
    lines.append("Grounding Directive: Rely strictly on the numbers above. Clearly mark unverified domain inferences as '[Hypothesis]'.")
    return "\n".join(lines)


def _generate_grounded_fallback_insights(data: dict[str, Any]) -> str:
    """
    Generate a structured, grounded markdown analysis from pre-calculated metrics.
    Ensures valid datasets never fail with an empty message if upstream LLM is intermittent.
    """
    filename = data.get("filename", "Dataset")
    file_type = data.get("file_type", "CSV")
    shape = data.get("shape", {})
    rows = shape.get("rows", 0)
    cols = shape.get("columns", 0)
    missing = data.get("missing_total", 0)
    dupes = data.get("duplicate_rows", 0)
    numeric_summary = data.get("numeric_summary", {})
    categorical_summary = data.get("categorical_summary", {})

    lines = [
        "### Executive Summary",
        f"The dataset **{filename}** ({file_type}) comprises **{rows:,}** rows and **{cols}** columns. "
        f"Quality checks confirm **{missing:,}** total missing values and **{dupes:,}** duplicate records.",
        "",
        "### Key Patterns & Distributions",
    ]

    if numeric_summary:
        lines.append("| Metric Column | Mean | Median | Min | Max | Std Dev |")
        lines.append("|---|---|---|---|---|---|")
        for col, stats in list(numeric_summary.items())[:6]:
            mean_val = f"{stats.get('mean'):,.2f}" if isinstance(stats.get("mean"), (int, float)) else str(stats.get("mean", "—"))
            med_val = f"{stats.get('median'):,.2f}" if isinstance(stats.get("median"), (int, float)) else str(stats.get("median", "—"))
            min_val = f"{stats.get('min'):,.2f}" if isinstance(stats.get("min"), (int, float)) else str(stats.get("min", "—"))
            max_val = f"{stats.get('max'):,.2f}" if isinstance(stats.get("max"), (int, float)) else str(stats.get("max", "—"))
            std_val = f"{stats.get('std'):,.2f}" if isinstance(stats.get("std"), (int, float)) else str(stats.get("std", "—"))
            lines.append(f"| {col} | {mean_val} | {med_val} | {min_val} | {max_val} | {std_val} |")
        lines.append("")

    if categorical_summary:
        for col, cat_info in list(categorical_summary.items())[:4]:
            top_vals = cat_info.get("top_values", [])
            if top_vals:
                top_v = top_vals[0]
                lines.append(f"* **{col}**: Predominant category is `{top_v.get('value')}` with {top_v.get('count')} occurrences.")

    lines.extend([
        "",
        "### Data Quality & Observations",
        f"* **Completeness**: {'All records are complete with zero missing values.' if missing == 0 else f'{missing:,} missing values observed across columns.'}",
        f"* **Uniqueness**: {'Zero duplicate records found.' if dupes == 0 else f'{dupes:,} duplicate rows detected.'}",
        "",
        "### Recommended Next Steps",
        "* Explore relationships between key numeric metrics and categorical drivers in the Charts section.",
        "* [Hypothesis] Segment deeper by top categories to isolate variance across cohorts.",
    ])

    return "\n".join(lines)


def generate_insights(
    analysis_data: dict[str, Any],
    client: Groq | None = None,
) -> dict[str, Any]:
    """
    Generate natural language insights explaining the dataset findings using Groq LLM.
    Includes retry on transient empty responses and grounded fallback synthesis.
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

    max_attempts = 2
    insights = None

    for attempt in range(max_attempts):
        try:
            response = client.chat.completions.create(
                model=settings.groq_model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"Please explain and synthesize these dataset analysis results:\n\n{prompt}"},
                ],
                temperature=0.3 if attempt == 0 else 0.5,
            )
        except AuthenticationError as exc:
            raise ValueError("Invalid Groq API key configured. Please verify your credentials.") from exc
        except RateLimitError as exc:
            raise RuntimeError("Groq rate limit exceeded. Please wait a moment before trying again.") from exc
        except APITimeoutError as exc:
            raise RuntimeError("Groq AI service timed out. Please try again.") from exc
        except APIConnectionError as exc:
            raise RuntimeError("Unable to connect to the Groq AI service. Please check network connectivity.") from exc
        except (BadRequestError, NotFoundError) as exc:
            raise RuntimeError(f"Requested AI model '{settings.groq_model}' is unavailable or invalid.") from exc
        except (APIError, GroqError) as exc:
            raise RuntimeError(f"Groq AI service encountered an error: {str(exc)}") from exc

        # When choices list is empty, raise RuntimeError as expected by reliability tests
        if not response or not getattr(response, "choices", None) or len(response.choices) == 0:
            raise RuntimeError("Received an empty response from the AI service. Please try again.")

        first_choice = response.choices[0]
        msg = getattr(first_choice, "message", None)
        raw_content = getattr(msg, "content", None) or getattr(msg, "reasoning_content", None) or getattr(msg, "reasoning", None)

        if raw_content and str(raw_content).strip():
            insights = str(raw_content).strip()
            break

        # If content was empty on attempt 0, pause briefly and retry
        if attempt < max_attempts - 1:
            time.sleep(0.3)
            continue

    # If all attempts returned empty content, provide grounded fallback synthesis
    if not insights or not insights.strip():
        insights = _generate_grounded_fallback_insights(analysis_data)

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
    "4. For broad overview questions (such as key topics, main topics, key findings, summary, or main points), "
    "synthesize the core subjects, themes, and findings directly described across the provided context excerpts.\n"
    "5. Format your grounded answer according to any presentation format requested by the user "
    "(such as markdown tables/tabular form, bullet points, or numbered lists). If tabular form is requested, "
    "format the facts using a standard Markdown table.\n"
    "6. Keep your answer concise, direct, and factual.\n"
    "7. When stating facts from the context, reference the source locations (e.g. Page X or Paragraph Y) wherever applicable."
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



def filter_used_sources(answer: str, chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Filter retrieved chunks to only return sources actually used for the generated answer,
    preserving exact page/paragraph metadata.
    """
    if not answer or not chunks:
        return []

    lower_ans = answer.lower()

    # If the answer states that document has insufficient information, no sources were used
    insufficient_phrases = [
        "does not contain sufficient information",
        "insufficient information to answer",
        "cannot find sufficient information",
        "no information is provided",
        "not mentioned in the provided",
        "not found in the provided",
    ]
    if any(phrase in lower_ans for phrase in insufficient_phrases):
        return []

    ans_words = set(re.findall(r"\b[a-zA-Z0-9_\-]+\b", lower_ans))
    used_chunks: list[dict[str, Any]] = []

    for idx, c in enumerate(chunks, 1):
        page_num = c.get("page_number")
        para_num = c.get("paragraph_number")
        text = c.get("text", "")
        text_lower = text.lower()

        # 1. Check explicit citation in answer: e.g. Page 1, Paragraph 2, Excerpt 1
        explicit_cited = False
        if page_num is not None and (
            f"page {page_num}" in lower_ans
            or f"page: {page_num}" in lower_ans
            or f"p. {page_num}" in lower_ans
            or f"p.{page_num}" in lower_ans
        ):
            explicit_cited = True
        elif para_num is not None and (
            f"paragraph {para_num}" in lower_ans
            or f"para {para_num}" in lower_ans
            or f"para: {para_num}" in lower_ans
        ):
            explicit_cited = True
        elif f"excerpt [{idx}]" in lower_ans or f"[{idx}]" in lower_ans or f"excerpt {idx}" in lower_ans:
            explicit_cited = True

        if explicit_cited:
            used_chunks.append(c)
            continue

        # 2. Token / phrase overlap verification
        chunk_words = [
            w for w in re.findall(r"\b[a-zA-Z0-9_\-]+\b", text_lower)
            if len(w) >= 4 and w not in {"with", "this", "that", "from", "they", "have", "been", "also", "were", "into", "their"}
        ]
        overlap = [w for w in chunk_words if w in ans_words]

        # 3-word phrase overlap
        words_list = text_lower.split()
        phrase_match = False
        for i in range(len(words_list) - 2):
            trigram = " ".join(words_list[i:i+3])
            if len(trigram) > 12 and trigram in lower_ans:
                phrase_match = True
                break

        if phrase_match or len(overlap) >= 3:
            used_chunks.append(c)

    # Fallback: if answer is substantive but no specific chunk hit the strict threshold,
    # keep the top scoring chunk
    if not used_chunks and chunks:
        used_chunks = [chunks[0]]

    # Deduplicate while preserving source/page metadata
    sources = []
    seen = set()
    for c in used_chunks:
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

    return sources


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
        RuntimeError on API / LLM failures.
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

    try:
        response = client.chat.completions.create(
            model=settings.groq_model,
            messages=[
                {"role": "system", "content": RAG_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.1,
        )
    except AuthenticationError as exc:
        raise ValueError("Invalid Groq API key configured. Please verify your credentials.") from exc
    except RateLimitError as exc:
        raise RuntimeError("Groq rate limit exceeded. Please wait a moment before trying again.") from exc
    except APITimeoutError as exc:
        raise RuntimeError("Groq AI service timed out. Please try again.") from exc
    except APIConnectionError as exc:
        raise RuntimeError("Unable to connect to the Groq AI service. Please check network connectivity.") from exc
    except (BadRequestError, NotFoundError) as exc:
        raise RuntimeError(f"Requested AI model '{settings.groq_model}' is unavailable or invalid.") from exc
    except (APIError, GroqError) as exc:
        raise RuntimeError(f"Groq AI service encountered an error: {str(exc)}") from exc

    if not response or not getattr(response, "choices", None) or len(response.choices) == 0:
        raise RuntimeError("Received an empty response from the AI service. Please try again.")

    first_choice = response.choices[0]
    msg = getattr(first_choice, "message", None)
    answer_text = getattr(msg, "content", None) if msg else None

    if not answer_text or not answer_text.strip():
        raise RuntimeError("AI model returned an empty message. Please try again.")

    # Compile only source references actually used for the answer
    sources = filter_used_sources(answer_text, chunks)

    return {
        "status": "success",
        "answer": answer_text,
        "sources": sources,
        "model": settings.groq_model,
    }
