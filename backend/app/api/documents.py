import logging
"""
api/documents.py - Document extraction, indexing, and RAG retrieval endpoints.

Endpoints:
- POST /documents/extract (or POST /documents/): Extract raw text & metadata from PDF/DOCX
- POST /documents/index: Extract, split into overlapping chunks, embed, and store in-memory
- POST /documents/retrieve: Semantic search returning top relevant chunks with source references (page/para)
- POST /documents/clear-index: Reset in-memory vector index for current user
- POST /documents/chat: Grounded Q&A over indexed PDF/DOCX using RAG + Groq LLM
- GET /documents/my-documents: List documents uploaded by the authenticated user

Protected: All document and chat endpoints require authentication and enforce multi-tenant isolation.
"""

from pathlib import Path
import re
from typing import Any, Optional
import uuid

from fastapi import APIRouter, HTTPException, Request, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.auth import get_current_user
from app.db.session import get_db
from app.db.models import Document, ChatMessage, User
from app.services.document_extraction import (
    extract_document,
    extract_text_from_pdf,
    extract_text_from_docx,
)
from app.services.llm import generate_rag_answer
from app.services.rag import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    index_document_data,
    retrieve_relevant_chunks,
    vector_index,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["Documents"])

SUPPORTED_EXTENSIONS = {".pdf", ".docx"}
TABULAR_EXTENSIONS = {".csv", ".xlsx"}
EXTENSION_LABELS = {
    ".pdf": "PDF",
    ".docx": "DOCX",
}


class DocumentExtractRequest(BaseModel):
    saved_filename: Optional[str] = None
    filename: Optional[str] = None


class DocumentIndexRequest(BaseModel):
    saved_filename: Optional[str] = None
    filename: Optional[str] = None
    chunk_size: int = Field(default=DEFAULT_CHUNK_SIZE, ge=50, le=5000)
    chunk_overlap: int = Field(default=DEFAULT_CHUNK_OVERLAP, ge=0, le=2000)


class DocumentChatRequest(BaseModel):
    question: str = Field(..., max_length=2000)
    filename: Optional[str] = None
    saved_filename: Optional[str] = None
    top_k: int = Field(default=4, ge=1, le=20)


class DocumentRetrieveRequest(BaseModel):
    query: str = Field(..., max_length=2000)
    top_k: int = Field(default=5, ge=1, le=50)
    filename: Optional[str] = None


def _safe_filename(original: str) -> str:
    clean = (original or "document").replace("\x00", "")
    base = Path(clean).name
    safe = "".join(
        c if (c.isalnum() or c in (".", "-", "_")) else "_"
        for c in base
    )
    return f"{uuid.uuid4().hex}_{safe}"


async def _resolve_document_file(request: Request) -> tuple[Path, str, dict[str, Any], bool]:
    """
    Helper to extract file_path, original_filename, parameters, and is_temporary flag
    from either multipart/form-data or JSON body.
    Returns: (file_path, original_filename, extra_params, is_temporary)
    """
    content_type = request.headers.get("content-type", "")
    saved_filename: Optional[str] = None
    file_bytes: Optional[bytes] = None
    original_filename: str = ""
    extra_params: dict[str, Any] = {}
    is_temporary: bool = False

    if "multipart/form-data" in content_type:
        form = await request.form()
        uploaded_file = form.get("file")
        if uploaded_file and hasattr(uploaded_file, "read"):
            original_filename = uploaded_file.filename or "uploaded_document"
            file_bytes = await uploaded_file.read()
        if "saved_filename" in form:
            saved_filename = str(form.get("saved_filename"))
        if "chunk_size" in form:
            try:
                extra_params["chunk_size"] = int(form.get("chunk_size"))
            except (ValueError, TypeError):
                pass
        if "chunk_overlap" in form:
            try:
                extra_params["chunk_overlap"] = int(form.get("chunk_overlap"))
            except (ValueError, TypeError):
                pass
    else:
        try:
            body = await request.json()
            if isinstance(body, dict):
                saved_filename = body.get("saved_filename") or body.get("filename")
                if "chunk_size" in body:
                    extra_params["chunk_size"] = int(body["chunk_size"])
                if "chunk_overlap" in body:
                    extra_params["chunk_overlap"] = int(body["chunk_overlap"])
        except Exception:
            saved_filename = request.query_params.get("saved_filename")

    if not file_bytes and not saved_filename:
        raise HTTPException(
            status_code=400,
            detail="Either 'saved_filename' or a document file must be provided.",
        )

    if file_bytes is not None:
        clean_name = (original_filename or "document").replace("\x00", "")
        suffix = Path(clean_name).suffix.lower()
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

        temp_name = _safe_filename(clean_name)
        file_path = settings.upload_dir_path / temp_name
        file_path.write_bytes(file_bytes)
        safe_name = temp_name
        is_temporary = True
    else:
        assert saved_filename is not None
        if "\x00" in saved_filename:
            raise HTTPException(status_code=400, detail="Invalid filename.")
        safe_name = Path(saved_filename).name
        if safe_name != saved_filename:
            raise HTTPException(status_code=400, detail="Invalid filename.")

        suffix = Path(safe_name).suffix.lower()
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

        file_path = settings.upload_dir_path / safe_name
        if not file_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"File '{safe_name}' was not found. Please upload the file first via POST /upload/.",
            )

        original_filename = re.sub(r"^[0-9a-f]{32}_", "", safe_name, count=1) or safe_name

    return file_path, original_filename, extra_params, is_temporary


@router.get("/my-documents")
async def list_my_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return all documents owned by the authenticated user."""
    docs = (
        db.query(Document)
        .filter(Document.user_id == current_user.id)
        .order_by(Document.uploaded_at.desc())
        .all()
    )
    return {
        "status": "success",
        "count": len(docs),
        "documents": [
            {
                "id": doc.id,
                "original_filename": doc.original_filename,
                "saved_filename": doc.saved_filename,
                "file_type": doc.file_type,
                "file_size_bytes": doc.file_size_bytes,
                "uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else None,
            }
            for doc in docs
        ],
    }


@router.post("/extract")
@router.post("/")
async def extract_document_endpoint(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Extract raw text and document structure from an uploaded PDF or DOCX file.
    Protected: validates document ownership and cleans up temporary direct uploads.
    """
    file_path, original_filename, _, is_temporary = await _resolve_document_file(request)

    # Ownership check for pre-saved files
    target_name = file_path.name
    doc_record = (
        db.query(Document)
        .filter(
            (Document.saved_filename == target_name)
            | (Document.original_filename == target_name)
        )
        .first()
    )
    if doc_record and doc_record.user_id is not None and doc_record.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this document.",
        )

    try:
        return extract_document(file_path, original_filename)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error("Error extracting document: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An unexpected internal server error occurred while extracting text from the document.",
        )
    finally:
        # Clean up temporary direct upload file after extraction
        if is_temporary and file_path.exists():
            try:
                file_path.unlink()
            except Exception:
                pass


@router.post("/index")
async def index_document_endpoint(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Extract text from a PDF or DOCX document, split into overlapping chunks,
    compute local embeddings via sentence-transformers, and index in memory.
    Protected: verifies document ownership and tags chunks with current_user.id.
    """
    file_path, original_filename, extra_params, is_temporary = await _resolve_document_file(request)

    # Check ownership in DB if record exists
    target_name = file_path.name
    doc_record = (
        db.query(Document)
        .filter(
            (Document.saved_filename == target_name)
            | (Document.original_filename == target_name)
        )
        .first()
    )
    if doc_record and doc_record.user_id is not None and doc_record.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this document.",
        )

    # If direct upload, create document record associated with current_user
    if is_temporary and not doc_record:
        doc_record = Document(
            user_id=current_user.id,
            original_filename=original_filename,
            saved_filename=file_path.name,
            file_type=EXTENSION_LABELS.get(file_path.suffix.lower(), "DOCUMENT"),
            file_size_bytes=file_path.stat().st_size if file_path.exists() else None,
        )
        db.add(doc_record)
        db.commit()
        db.refresh(doc_record)

    chunk_size = extra_params.get("chunk_size", DEFAULT_CHUNK_SIZE)
    chunk_overlap = extra_params.get("chunk_overlap", DEFAULT_CHUNK_OVERLAP)

    if chunk_overlap >= chunk_size:
        raise HTTPException(
            status_code=400,
            detail=f"chunk_overlap ({chunk_overlap}) must be strictly less than chunk_size ({chunk_size}).",
        )

    try:
        extraction_result = extract_document(file_path, original_filename)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error("Error extracting document for indexing: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An unexpected internal server error occurred while reading the document.",
        )

    extraction_result["saved_filename"] = file_path.name

    try:
        index_result = index_document_data(
            extraction_result,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            user_id=current_user.id,
            index=vector_index,
        )
        return index_result
    except Exception as e:
        logger.error("Error indexing document: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An unexpected internal server error occurred while indexing the document.",
        )


@router.post("/retrieve")
async def retrieve_endpoint(
    payload: DocumentRetrieveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Retrieve top relevant chunks matching a semantic query.
    Protected: strictly limits retrieval to current_user documents and chunks.
    """
    query = payload.query.strip() if payload.query else ""
    if not query:
        raise HTTPException(status_code=400, detail="Query string cannot be empty.")

    if payload.filename:
        target_name = payload.filename.strip()
        doc_record = (
            db.query(Document)
            .filter(
                (Document.saved_filename == target_name)
                | (Document.original_filename == target_name)
            )
            .first()
        )
        if doc_record and doc_record.user_id is not None and doc_record.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this document.",
            )

    try:
        results = retrieve_relevant_chunks(
            query=query,
            top_k=payload.top_k,
            filename=payload.filename,
            user_id=current_user.id,
            index=vector_index,
        )
        return {
            "status": "success",
            "query": query,
            "count": len(results),
            "results": results,
        }
    except Exception as e:
        logger.error("Retrieval query failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An unexpected internal server error occurred during retrieval.",
        )


@router.post("/clear-index")
async def clear_index_endpoint(
    current_user: User = Depends(get_current_user),
):
    """Clear in-memory vector index entries for the authenticated user."""
    vector_index.clear(user_id=current_user.id)
    return {
        "status": "success",
        "message": "In-memory vector index cleared for user.",
        "total_indexed_chunks": vector_index.count(user_id=current_user.id),
    }


@router.post("/chat")
async def chat_document_endpoint(
    payload: DocumentChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Answer user questions about an uploaded PDF/DOCX document using RAG retrieval + Groq LLM.
    Strictly grounds answers in the retrieved document chunks and cites page/paragraph sources.
    Protected: validates document ownership and associates chat messages with authenticated user.
    """
    question = (payload.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question string cannot be empty.")

    target_name = payload.saved_filename or payload.filename
    if not target_name or not target_name.strip():
        raise HTTPException(
            status_code=400,
            detail="A document filename or saved_filename must be provided.",
        )
    target_name = target_name.strip()

    # Document ownership validation
    doc_record = (
        db.query(Document)
        .filter(
            (Document.saved_filename == target_name)
            | (Document.original_filename == target_name)
        )
        .first()
    )
    if doc_record and doc_record.user_id is not None and doc_record.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this document.",
        )

    # If no chunks match target_name for current user in vector_index, check if file exists on disk to auto-index
    def _has_chunks(fn: str) -> bool:
        base = Path(fn).name
        for c in vector_index.chunks:
            c_uid = c.get("user_id")
            if c_uid is not None and c_uid != current_user.id:
                continue
            c_fn = c.get("filename")
            c_sfn = c.get("saved_filename")
            if c_fn == fn or c_sfn == fn:
                return True
            if c_fn and (Path(c_fn).name == base or Path(c_fn).name.endswith(f"_{base}")):
                return True
            if c_sfn and (Path(c_sfn).name == base or Path(c_sfn).name.endswith(f"_{base}")):
                return True
        return False

    if not _has_chunks(target_name):
        file_to_index = None
        candidate = settings.upload_dir_path / target_name
        if candidate.exists() and candidate.is_file():
            file_to_index = candidate
        else:
            base = Path(target_name).name
            matches = list(settings.upload_dir_path.glob(f"*_{base}"))
            if not matches:
                matches = list(settings.upload_dir_path.glob(f"*{base}"))
            if matches:
                file_to_index = matches[0]

        if file_to_index:
            try:
                orig_name = (
                    re.sub(r"^[0-9a-f]{32}_", "", file_to_index.name, count=1)
                    or file_to_index.name
                )
                extraction_result = extract_document(file_to_index, orig_name)
                extraction_result["saved_filename"] = file_to_index.name
                index_document_data(extraction_result, user_id=current_user.id, index=vector_index)
            except Exception:
                pass

    # Retrieve relevant chunks matching query strictly scoped to current_user
    try:
        retrieved_chunks = retrieve_relevant_chunks(
            query=question,
            top_k=payload.top_k,
            filename=target_name,
            user_id=current_user.id,
            index=vector_index,
        )
    except Exception as e:
        logger.error("RAG retrieval failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An unexpected internal server error occurred during RAG retrieval.",
        )

    # Generate answer via Groq LLM service
    try:
        answer_data = generate_rag_answer(question=question, chunks=retrieved_chunks)

        # Save Chat Messages to DB associated with current_user and document
        if doc_record:
            if doc_record.user_id is None:
                doc_record.user_id = current_user.id

            user_msg = ChatMessage(
                document_id=doc_record.id,
                user_id=current_user.id,
                role="user",
                content=question,
            )
            db.add(user_msg)

            assistant_msg = ChatMessage(
                document_id=doc_record.id,
                user_id=current_user.id,
                role="assistant",
                content=answer_data["answer"],
                sources=answer_data["sources"],
            )
            db.add(assistant_msg)
            db.commit()

        return {
            "status": "success",
            "question": question,
            "filename": target_name,
            "answer": answer_data["answer"],
            "sources": answer_data["sources"],
            "model": answer_data.get("model", settings.groq_model),
            "chunks_retrieved": len(retrieved_chunks),
        }
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=f"LLM service error: {str(exc)}")
    except Exception as exc:
        logger.error("Unexpected error in chat_document_endpoint: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An unexpected internal server error occurred while processing document chat.",
        )
