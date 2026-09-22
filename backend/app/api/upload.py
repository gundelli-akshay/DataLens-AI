"""
api/upload.py - File upload endpoint.

POST /upload/
  Accepts:  multipart/form-data with a single `file` field
  Validates: file extension, file size, empty-file guard
  Saves to:  <project_root>/data/uploads/
  Returns:   upload metadata (no local paths exposed)

Security notes:
  - Filenames are sanitised (null bytes stripped, directory components removed)
    and prefixed with a UUID to prevent path-traversal attacks and collisions.
  - Upload stream is read in chunks to prevent memory exhaustion (DoS).
  - File content is never executed.
  - Local filesystem paths are never returned to the client.
"""

import logging
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, HTTPException, UploadFile, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import Document, User
from app.core.auth import get_current_user
from app.core.config import settings
from app.services.storage import storage_service, StorageError
import urllib.parse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/upload", tags=["Upload"])

# -- Allowed file types -----------------------------------------
ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".pdf", ".docx"}

EXTENSION_LABELS = {
    ".csv":  "CSV",
    ".xlsx": "XLSX",
    ".pdf":  "PDF",
    ".docx": "DOCX",
}

# -- Max file size ----------------------------------------------
MAX_BYTES = settings.max_upload_size_mb * 1024 * 1024
STREAM_CHUNK_SIZE = 1024 * 1024  # 1 MB chunk


def _clean_input_filename(name: str) -> str:
    """Strip null bytes, escaped nulls, and URL-encoded null representations."""
    unquoted = urllib.parse.unquote(name or "upload")
    return unquoted.replace(chr(0), "").replace("%00", "").replace("\\0", "").replace("\\x00", "")


def _safe_filename(original: str) -> str:
    """
    Return a safe, unique filename.
    1. Strip null bytes and directory components (prevents path traversal).
    2. Replace non-alphanumeric characters (except . - _) with underscores.
    3. Prefix with a UUID hex to prevent collisions and overwrite attacks.
    """
    clean_original = _clean_input_filename(original)
    base = Path(clean_original).name
    safe = "".join(
        c if (c.isalnum() or c in (".", "-", "_")) else "_"
        for c in base
    )
    return f"{uuid.uuid4().hex}_{safe}"


def _human_size(n: int) -> str:
    """Convert bytes to a human-readable string."""
    if n < 1_024:
        return f"{n} B"
    if n < 1_024 ** 2:
        return f"{n / 1_024:.1f} KB"
    return f"{n / 1_024 ** 2:.2f} MB"


@router.post("/")
async def upload_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Upload a single file (CSV, XLSX, PDF, or DOCX).
    Returns upload metadata. Does NOT return local filesystem paths.
    """
    # -- 1. Extension validation --------------------------------
    original_name = file.filename or "upload"
    clean_name = _clean_input_filename(original_name)
    suffix = Path(clean_name).suffix.lower()

    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=(
                f"'{suffix or 'unknown'}' is not a supported file type. "
                f"Please upload a CSV, XLSX, PDF, or DOCX file."
            ),
        )

    # -- 2. Chunked read into memory to prevent OOM DoS ---------
    chunks = []
    total_bytes = 0

    while True:
        chunk = await file.read(STREAM_CHUNK_SIZE)
        if not chunk:
            break
        total_bytes += len(chunk)
        if total_bytes > MAX_BYTES:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"File is too large ({_human_size(total_bytes)}). "
                    f"Maximum allowed size is {settings.max_upload_size_mb} MB."
                ),
            )
        chunks.append(chunk)

    content = b"".join(chunks)

    # -- 3. Empty-file guard ------------------------------------
    if len(content) == 0:
        raise HTTPException(
            status_code=400,
            detail="The uploaded file is empty. Please choose a valid file.",
        )

    # -- 4. Save to persistent storage --------------------------
    saved_name = _safe_filename(clean_name)
    try:
        storage_service.save_file(
            saved_filename=saved_name,
            content=content,
            content_type=file.content_type or "application/octet-stream",
        )
    except StorageError as exc:
        logger.error("Storage upload failed: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Failed to store uploaded file in persistent storage. Please try again.",
        )

    # -- 5. Save to DB (for all uploaded files) -----------------
    if suffix in ALLOWED_EXTENSIONS:
        doc_record = Document(
            user_id=current_user.id,
            original_filename=clean_name,
            saved_filename=saved_name,
            file_type=EXTENSION_LABELS[suffix],
            file_size_bytes=len(content),
        )
        db.add(doc_record)
        db.commit()
        db.refresh(doc_record)

    # -- 6. Return metadata (no local paths) --------------------
    return {
        "status":            "success",
        "original_filename": clean_name,
        "saved_filename":    saved_name,
        "file_type":         EXTENSION_LABELS[suffix],
        "file_size_bytes":   len(content),
        "file_size_display": _human_size(len(content)),
    }
