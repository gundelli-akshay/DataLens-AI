"""
api/analyze.py - CSV / XLSX Analysis endpoint.

POST /analyze/
  Accepts:  { "saved_filename": "uuid_filename.csv" }
  Validates: file exists in uploads, format is CSV or XLSX
  Processes: computes summary statistics using Pandas (analysis service)
  Returns:   structured JSON analysis report
"""

import logging
from pathlib import Path
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.config import settings
from app.db.models import Document, User
from app.db.session import get_db
from app.services.analysis import analyze_csv, analyze_xlsx
from app.services.storage import storage_service, StorageError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analyze", tags=["Analysis"])

# -- File type classification ------------------------------------
SUPPORTED_EXTENSIONS = {".csv", ".xlsx"}
DOCUMENT_EXTENSIONS = {".pdf", ".docx"}


# -- Request schema ----------------------------------------------
class AnalyzeRequest(BaseModel):
    """
    Body for POST /analyze/.
    `saved_filename` is the UUID-prefixed filename returned by /upload/.
    """
    saved_filename: str


# -- Router ------------------------------------------------------
@router.post("", include_in_schema=False)
@router.post("/")
def analyze_file(
    request: AnalyzeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Analyse a previously uploaded CSV or XLSX file.
    The file must already exist in persistent storage (uploaded via POST /upload/).
    Returns a structured JSON summary produced by Pandas.
    """
    # -- 1. Sanitise the filename -----------------------------
    filename = request.saved_filename
    if chr(0) in filename:
        raise HTTPException(status_code=400, detail="Invalid filename.")

    safe_name = Path(filename).name
    if safe_name != filename:
        raise HTTPException(status_code=400, detail="Invalid filename.")

    # -- 2. Authorization check if document is tracked in DB --
    doc = db.query(Document).filter(Document.saved_filename == safe_name).first()
    if doc and doc.user_id is not None and doc.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to access this document.")

    # -- 3. Resolve and verify the file exists ----------------
    try:
        file_path = storage_service.get_file_path(safe_name)
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=(
                f"File '{safe_name}' was not found. "
                "Please upload the file first via POST /upload/."
            ),
        )
    except StorageError as exc:
        logger.error("Failed to retrieve file '%s' from storage: %s", safe_name, exc)
        raise HTTPException(
            status_code=502,
            detail="Failed to retrieve file from persistent storage.",
        )

    # -- 4. Classify the file type ----------------------------
    suffix = file_path.suffix.lower()

    if suffix in DOCUMENT_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"{suffix.lstrip('.').upper()} files are not supported for data analysis. "
                "Document analysis (PDF/DOCX) is available in Document Chat."
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

    # -- 5. Derive the original filename for display ----------
    original_filename = re.sub(r"^[0-9a-f]{32}_", "", safe_name, count=1) or safe_name

    # -- 6. Run the appropriate analysis ---------------------
    try:
        if suffix == ".csv":
            result = analyze_csv(file_path, original_filename)
        else:
            result = analyze_xlsx(file_path, original_filename)

        if doc and doc.ai_insights:
            result["ai_insights"] = doc.ai_insights
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Analysis execution error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An unexpected internal server error occurred while analyzing the file.",
        )

    # -- 7. Surface analysis errors as HTTP errors ------------
    if result.get("status") == "error":
        raise HTTPException(status_code=422, detail=result["message"])

    return result
