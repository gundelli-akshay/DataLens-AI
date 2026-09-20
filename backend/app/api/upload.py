import logging
"""
api/upload.py — File upload endpoint.

POST /upload/
  Accepts:  multipart/form-data with a single `file` field
  Validates: file extension, file size, empty-file guard
  Saves to:  <project_root>/data/uploads/
  Returns:   upload metadata (no local paths exposed)

Security notes:
  - Filenames are sanitised and prefixed with a UUID to prevent
    path-traversal attacks and filename collisions.
  - File content is never executed.
  - Local filesystem paths are never returned to the client.
"""

import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import Document, User
from app.core.auth import get_optional_current_user
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/upload", tags=["Upload"])

# ── Allowed file types ─────────────────────────────────────────
ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".pdf", ".docx"}

EXTENSION_LABELS = {
    ".csv":  "CSV",
    ".xlsx": "XLSX",
    ".pdf":  "PDF",
    ".docx": "DOCX",
}

# ── Max file size ──────────────────────────────────────────────
MAX_BYTES = settings.max_upload_size_mb * 1024 * 1024


def _safe_filename(original: str) -> str:
    """
    Return a safe, unique filename.

    Steps:
    1. Strip any directory components (prevents path traversal).
    2. Replace non-alphanumeric characters (except . - _) with underscores.
    3. Prefix with a UUID hex to prevent collisions and overwrite attacks.
    """
    base = Path(original).name                        # strip directory parts
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
async def upload_file(file: UploadFile = File(...), db: Session = Depends(get_db), current_user: Optional[User] = Depends(get_optional_current_user)):
    """
    Upload a single file (CSV, XLSX, PDF, or DOCX).

    Returns upload metadata. Does NOT return local filesystem paths.
    """

    # ── 1. Extension validation ────────────────────────────────
    original_name = file.filename or "upload"
    suffix = Path(original_name).suffix.lower()

    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=(
                f"'{suffix or 'unknown'}' is not a supported file type. "
                f"Please upload a CSV, XLSX, PDF, or DOCX file."
            ),
        )

    # ── 2. Read into memory ────────────────────────────────────
    content = await file.read()

    # ── 3. Empty-file guard ────────────────────────────────────
    if len(content) == 0:
        raise HTTPException(
            status_code=400,
            detail="The uploaded file is empty. Please choose a valid file.",
        )

    # ── 4. Size validation ─────────────────────────────────────
    if len(content) > MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(
                f"File is too large ({_human_size(len(content))}). "
                f"Maximum allowed size is {settings.max_upload_size_mb} MB."
            ),
        )

    # ── 5. Save to disk ────────────────────────────────────────
    saved_name = _safe_filename(original_name)
    upload_path = settings.upload_dir_path / saved_name
    upload_path.write_bytes(content)

    #  5b. Save to DB (for PDF/DOCX) 
    if suffix in {".pdf", ".docx"}:
        doc_record = Document(
            user_id=current_user.id if current_user else None,
            original_filename=original_name,
            saved_filename=saved_name,
            file_type=EXTENSION_LABELS[suffix],
            file_size_bytes=len(content)
        )
        db.add(doc_record)
        db.commit()
        db.refresh(doc_record)


    # ── 6. Return metadata (no local paths) ────────────────────
    return {
        "status":            "success",
        "original_filename": original_name,
        "saved_filename":    saved_name,
        "file_type":         EXTENSION_LABELS[suffix],
        "file_size_bytes":   len(content),
        "file_size_display": _human_size(len(content)),
    }
