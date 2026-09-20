"""
services/document_extraction.py - Document text extraction service.

Provides page-by-page text extraction for PDF files using PyMuPDF
and paragraph-by-paragraph text extraction for DOCX files using python-docx.

Returns clean extracted text and structured metadata.
"""

from pathlib import Path
from typing import Any
import pymupdf
import docx


def _clean_text(text: str) -> str:
    """
    Normalise whitespace and clean extracted text.
    Replaces null bytes and trailing whitespace per line.
    """
    if not text:
        return ""
    text = text.replace("\x00", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.split("\n")]
    return "\n".join(lines).strip()


def extract_text_from_pdf(file_path: Path | str, original_filename: str = "") -> dict[str, Any]:
    """
    Extract text from a PDF document page-by-page using PyMuPDF.

    Args:
        file_path: Path to the PDF file on disk.
        original_filename: Display name of the original file.

    Returns:
        Structured dictionary containing extracted text and metadata.

    Raises:
        ValueError if the file cannot be opened or is corrupted.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    filename = original_filename or path.name

    try:
        doc = pymupdf.open(str(path))
    except Exception as e:
        raise ValueError(f"Unable to read PDF file '{filename}'. The file may be corrupt or not a valid PDF.") from None

    try:
        pages: list[dict[str, Any]] = []
        full_text_chunks: list[str] = []
        total_pages = len(doc)

        for page_idx in range(total_pages):
            page = doc[page_idx]
            raw_text = page.get_text() or ""
            cleaned = _clean_text(raw_text)

            pages.append({
                "page_number": page_idx + 1,
                "text": cleaned,
                "character_count": len(cleaned),
                "word_count": len(cleaned.split()),
            })

            if cleaned:
                full_text_chunks.append(cleaned)

        full_text = "\n\n".join(full_text_chunks)

        return {
            "status": "success",
            "filename": filename,
            "file_type": "PDF",
            "page_count": total_pages,
            "paragraph_count": None,
            "total_pages": total_pages,
            "total_paragraphs": None,
            "total_characters": len(full_text),
            "total_words": len(full_text.split()),
            "metadata": {
                "filename": filename,
                "file_type": "PDF",
                "page_count": total_pages,
                "paragraph_count": None,
                "total_characters": len(full_text),
                "total_words": len(full_text.split()),
            },
            "text": full_text,
            "pages": pages,
            "paragraphs": [],
        }
    finally:
        doc.close()


def extract_text_from_docx(file_path: Path | str, original_filename: str = "") -> dict[str, Any]:
    """
    Extract text from a DOCX document paragraph-by-paragraph using python-docx.

    Args:
        file_path: Path to the DOCX file on disk.
        original_filename: Display name of the original file.

    Returns:
        Structured dictionary containing extracted text and metadata.

    Raises:
        ValueError if the file cannot be opened or is corrupted.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    filename = original_filename or path.name

    try:
        doc = docx.Document(str(path))
    except Exception as e:
        raise ValueError(f"Unable to read DOCX file '{filename}'. The file may be corrupt or not a valid Word document.") from None

    paragraphs: list[dict[str, Any]] = []
    full_text_chunks: list[str] = []

    p_counter = 0
    for p in doc.paragraphs:
        cleaned = _clean_text(p.text)
        if cleaned:
            p_counter += 1
            paragraphs.append({
                "paragraph_number": p_counter,
                "text": cleaned,
                "character_count": len(cleaned),
                "word_count": len(cleaned.split()),
            })
            full_text_chunks.append(cleaned)

    full_text = "\n\n".join(full_text_chunks)

    return {
        "status": "success",
        "filename": filename,
        "file_type": "DOCX",
        "page_count": None,
        "paragraph_count": len(paragraphs),
        "total_pages": None,
        "total_paragraphs": len(paragraphs),
        "total_characters": len(full_text),
        "total_words": len(full_text.split()),
        "metadata": {
            "filename": filename,
            "file_type": "DOCX",
            "page_count": None,
            "paragraph_count": len(paragraphs),
            "total_characters": len(full_text),
            "total_words": len(full_text.split()),
        },
        "text": full_text,
        "pages": [],
        "paragraphs": paragraphs,
    }


def extract_document(file_path: Path | str, original_filename: str = "") -> dict[str, Any]:
    """
    Dispatch document extraction based on file extension (.pdf or .docx).

    Args:
        file_path: Path to the file.
        original_filename: Optional original filename.

    Returns:
        Extraction result dictionary.

    Raises:
        ValueError if unsupported extension or extraction failure.
    """
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        return extract_text_from_pdf(path, original_filename)
    elif suffix == ".docx":
        return extract_text_from_docx(path, original_filename)
    else:
        raise ValueError(
            f"Unsupported document format '{suffix}'. Only PDF and DOCX files are supported."
        )
