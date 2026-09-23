"""
api/insights.py - AI Insights endpoint.

POST /ai/insights/
  Body options:
    1. { "analysis": { ... } }           -- programmatic analysis result already in hand
    2. { "saved_filename": "uuid_..." }  -- analyze uploaded CSV/XLSX on the fly
  Response:
    {
      "status": "success",
      "insights": "markdown string",
      "model": "gemini-3.8-flash" or "openai/gpt-oss-20b"
    }
"""

import logging
from pathlib import Path
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.config import settings
from app.db.models import Document, User
from app.db.session import get_db
from app.services.analysis import analyze_csv, analyze_xlsx
from app.services.llm import generate_insights
from app.services.storage import storage_service, StorageError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai/insights", tags=["AI Insights"])

SUPPORTED_EXTENSIONS = {".csv", ".xlsx"}
DOCUMENT_EXTENSIONS = {".pdf", ".docx"}


class InsightsRequest(BaseModel):
    saved_filename: str | None = None
    analysis: dict[str, Any] | None = None


@router.post("", include_in_schema=False)
@router.post("/")
def get_insights(
    request: InsightsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Generate natural language insights from data analysis results using Gemini (primary)
    or Groq (secondary/fallback).
    """
    analysis_data = request.analysis
    doc = None

    # If saved_filename is given, perform eager authorization and input validation
    if request.saved_filename:
        filename = request.saved_filename
        if chr(0) in filename:
            raise HTTPException(status_code=400, detail="Invalid filename.")

        safe_name = Path(filename).name
        if safe_name != filename:
            raise HTTPException(status_code=400, detail="Invalid filename.")

        # Eager authorization check
        doc = db.query(Document).filter(Document.saved_filename == safe_name).first()
        if doc and doc.user_id is not None and doc.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized to access this document.")

    # If analysis dictionary was not directly provided, compute it from saved_filename
    if not analysis_data:
        if not request.saved_filename:
            raise HTTPException(
                status_code=400,
                detail="Either 'analysis' or 'saved_filename' must be provided.",
            )

        safe_name = Path(request.saved_filename).name

        try:
            file_path = storage_service.get_file_path(safe_name)
        except FileNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"File '{safe_name}' was not found in uploads.",
            )
        except StorageError as exc:
            logger.error("Failed to retrieve file '%s' from storage: %s", safe_name, exc)
            raise HTTPException(
                status_code=502,
                detail="Failed to retrieve file from persistent storage.",
            )

        suffix = file_path.suffix.lower()
        if suffix in DOCUMENT_EXTENSIONS:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"{suffix.lstrip('.').upper()} files are not supported for data analysis insights. "
                    "Document analysis is available in Document Chat."
                ),
            )

        if suffix not in SUPPORTED_EXTENSIONS:
            raise HTTPException(
                status_code=415,
                detail=f"'{suffix}' is not supported. Only CSV and XLSX files can be analyzed.",
            )

        original_filename = re.sub(r"^[0-9a-f]{32}_", "", safe_name, count=1) or safe_name

        if suffix == ".csv":
            result = analyze_csv(file_path, original_filename)
        else:
            result = analyze_xlsx(file_path, original_filename)

        if result.get("status") == "error":
            raise HTTPException(status_code=422, detail=result.get("message", "Analysis failed."))

        analysis_data = result

    # Validate analysis_data has expected structure
    if not isinstance(analysis_data, dict) or analysis_data.get("status") == "error":
        raise HTTPException(
            status_code=422,
            detail="Invalid analysis data provided.",
        )

    try:
        insights_result = generate_insights(analysis_data)
        if doc:
            doc.ai_insights = insights_result.get("insights")
            db.commit()
        return insights_result
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=f"LLM service error: {str(exc)}")
    except Exception as exc:
        logger.error("Unexpected error in get_insights: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An unexpected internal server error occurred while generating insights.",
        )
