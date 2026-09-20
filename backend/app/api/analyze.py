import logging
"""
api/analyze.py — Data analysis endpoint.

POST /analyze/
  Body:     { "saved_filename": "<uuid32>_original.csv" }
  Response: Structured analysis JSON from services/analysis.py

Supports: CSV, XLSX
Gracefully rejects: PDF, DOCX (document analysis comes in a future step)
"""

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import settings
from app.services.analysis import analyze_csv, analyze_xlsx

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analyze", tags=["Analysis"])

# ── File type classification ────────────────────────────────────
SUPPORTED_EXTENSIONS = {".csv", ".xlsx"}
DOCUMENT_EXTENSIONS  = {".pdf", ".docx"}


# ── Request schema ──────────────────────────────────────────────
class AnalyzeRequest(BaseModel):
    """
    Body for POST /analyze/.
    `saved_filename` is the UUID-prefixed filename returned by /upload/.
    """
    saved_filename: str


# ── Router ──────────────────────────────────────────────────────
@router.post("/")
def analyze_file(request: AnalyzeRequest):
    """
    Analyse a previously uploaded CSV or XLSX file.

    The file must already exist in data/uploads/ (uploaded via POST /upload/).
    Returns a structured JSON summary produced by Pandas.
    """

    # ── 1. Sanitise the filename ─────────────────────────────
    # Path.name strips any directory component — prevents path traversal.
    safe_name = Path(request.saved_filename).name
    if safe_name != request.saved_filename:
        raise HTTPException(status_code=400, detail="Invalid filename.")

    # ── 2. Resolve and verify the file exists ────────────────
    file_path = settings.upload_dir_path / safe_name
    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                f"File '{safe_name}' was not found. "
                "Please upload the file first via POST /upload/."
            ),
        )

    # ── 3. Classify the file type ────────────────────────────
    suffix = file_path.suffix.lower()

    if suffix in DOCUMENT_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"{suffix.lstrip('.').upper()} files are not supported for data analysis. "
                "Document analysis (PDF/DOCX) will be added in a future step."
            ),
        )

    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=(
                f"'{suffix}' is not a supported analysis format. "
                "Only CSV and XLSX files can be analysed."
            ),
        )

    # ── 4. Derive the original filename for display ──────────
    # Saved filename format: <32 hex chars>_<original_name>
    # e.g. "3dfee679fc0548ffbb008502_employees.csv"
    original_filename = re.sub(r"^[0-9a-f]{32}_", "", safe_name, count=1) or safe_name

    # ── 5. Run the appropriate analysis ─────────────────────
    try:
        if suffix == ".csv":
            result = analyze_csv(file_path, original_filename)
        else:
            result = analyze_xlsx(file_path, original_filename)
    except Exception as exc:
        logger.error("Analysis execution error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An unexpected internal server error occurred while analyzing the file.",
        )

    # ── 6. Surface analysis errors as HTTP errors ────────────
    if result.get("status") == "error":
        raise HTTPException(status_code=422, detail=result["message"])

    return result