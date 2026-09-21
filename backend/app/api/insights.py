import logging
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
      "model": "gpt-4o-mini"
    }
"""

import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import settings
from app.services.analysis import analyze_csv, analyze_xlsx
from app.services.llm import generate_insights
from app.db.session import get_db
from app.db.models import Document
from fastapi import Depends
from sqlalchemy.orm import Session
from app.core.auth import get_optional_current_user
from app.db.models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai/insights", tags=["AI Insights"])

SUPPORTED_EXTENSIONS = {".csv", ".xlsx"}
DOCUMENT_EXTENSIONS  = {".pdf", ".docx"}


class InsightsRequest(BaseModel):
    saved_filename: str | None = None
    analysis: dict[str, Any] | None = None


@router.post("/")
def get_insights(request: InsightsRequest, db: Session = Depends(get_db), current_user: User | None = Depends(get_optional_current_user)):
    """
    Generate natural language insights from data analysis results using an LLM.
    """
    analysis_data = request.analysis

    # If analysis dictionary was not directly provided, compute it from saved_filename
    if not analysis_data:
        if not request.saved_filename:
            raise HTTPException(
                status_code=400,
                detail="Either 'analysis' or 'saved_filename' must be provided.",
            )

        filename = request.saved_filename
        if "\x00" in filename:
            raise HTTPException(status_code=400, detail="Invalid filename.")

        safe_name = Path(filename).name
        if safe_name != filename:
            raise HTTPException(status_code=400, detail="Invalid filename.")

        file_path = settings.upload_dir_path / safe_name
        if not file_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"File '{safe_name}' was not found in uploads.",
            )

        suffix = file_path.suffix.lower()
        if suffix in DOCUMENT_EXTENSIONS:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"{suffix.lstrip('.').upper()} files are not supported for data analysis insights. "
                    "Document analysis will be added in a future step."
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
        if request.saved_filename:
            doc = db.query(Document).filter(Document.saved_filename == request.saved_filename).first()
            if doc:
                if doc.user_id is not None and (current_user is None or doc.user_id != current_user.id):
                    raise HTTPException(status_code=403, detail="Not authorized to access this document.")
                doc.ai_insights = insights_result.get("insights")
                db.commit()
        return insights_result
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
