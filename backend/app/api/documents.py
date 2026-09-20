"""
api/documents.py - Document text extraction endpoint.

POST /documents/extract (or POST /documents/)
  Accepts:
    - JSON body: { "saved_filename": "<uuid32>_document.pdf" }
    - Multipart form-data: file: UploadFile or saved_filename
  Response:
    Clean extracted text + metadata (filename, file_type, page_count, paragraph_count)

Supports: PDF, DOCX
Rejects: CSV, XLSX (415), unsupported file types (415)
"""

from pathlib import Path
import re
import uuid

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.core.config import settings
from app.services.document_extraction import (
    extract_document,
    extract_text_from_pdf,
    extract_text_from_docx,
)

router = APIRouter(prefix="/documents", tags=["Documents"])

SUPPORTED_EXTENSIONS = {".pdf", ".docx"}
TABULAR_EXTENSIONS = {".csv", ".xlsx"}


class DocumentExtractRequest(BaseModel):
    saved_filename: str | None = None
    filename: str | None = None


def _safe_filename(original: str) -> str:
    base = Path(original).name
    safe = "".join(
        c if (c.isalnum() or c in (".", "-", "_")) else "_"
        for c in base
    )
    return f"{uuid.uuid4().hex}_{safe}"


@router.post("/extract")
@router.post("/")
async def process_document(request: Request):
    """
    Process an uploaded PDF or DOCX file and extract clean text with metadata.

    Supports:
      - JSON body: {"saved_filename": "<uuid>_file.pdf"}
      - Multipart form-data: file upload
    """
    content_type = request.headers.get("content-type", "")
    saved_filename: str | None = None
    file_bytes: bytes | None = None
    original_filename: str = ""

    if "multipart/form-data" in content_type:
        form = await request.form()
        uploaded_file = form.get("file")
        if uploaded_file and hasattr(uploaded_file, "read"):
            original_filename = uploaded_file.filename or "uploaded_document"
            file_bytes = await uploaded_file.read()
        if "saved_filename" in form:
            saved_filename = str(form.get("saved_filename"))
    else:
        try:
            body = await request.json()
            if isinstance(body, dict):
                saved_filename = body.get("saved_filename") or body.get("filename")
        except Exception:
            saved_filename = request.query_params.get("saved_filename")

    if not file_bytes and not saved_filename:
        raise HTTPException(
            status_code=400,
            detail="Either 'saved_filename' or a document file must be provided.",
        )

    if file_bytes is not None:
        suffix = Path(original_filename).suffix.lower()
        if suffix in TABULAR_EXTENSIONS:
            raise HTTPException(
                status_code=415,
                detail=f"'{suffix}' is a tabular data format. Please use /analyze/ for CSV and XLSX files.",
            )
        if suffix not in SUPPORTED_EXTENSIONS:
            raise HTTPException(
                status_code=415,
                detail=f"'{suffix}' is not a supported document format. Only PDF and DOCX files are supported.",
            )

        temp_name = _safe_filename(original_filename)
        file_path = settings.upload_dir_path / temp_name
        file_path.write_bytes(file_bytes)
        safe_name = temp_name
    else:
        assert saved_filename is not None
        safe_name = Path(saved_filename).name
        if safe_name != saved_filename:
            raise HTTPException(status_code=400, detail="Invalid filename.")

        file_path = settings.upload_dir_path / safe_name
        if not file_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"File '{safe_name}' was not found. Please upload the file first via POST /upload/.",
            )

        suffix = file_path.suffix.lower()
        if suffix in TABULAR_EXTENSIONS:
            raise HTTPException(
                status_code=415,
                detail=f"'{suffix}' is a tabular data format. Please use /analyze/ for CSV and XLSX files.",
            )
        if suffix not in SUPPORTED_EXTENSIONS:
            raise HTTPException(
                status_code=415,
                detail=f"'{suffix}' is not a supported document format. Only PDF and DOCX files are supported.",
            )

        original_filename = re.sub(r"^[0-9a-f]{32}_", "", safe_name, count=1) or safe_name

    try:
        return extract_document(file_path, original_filename)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred while extracting text from the document: {str(e)}",
        )
