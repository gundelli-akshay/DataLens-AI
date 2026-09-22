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

import collections
import logging
from pathlib import Path
import re
from typing import Any, Optional
import uuid
from app.services.storage import storage_service, StorageError

from fastapi import APIRouter, HTTPException, Request, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import func
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
            try:
                file_path = storage_service.get_file_path(safe_name)
            except Exception:
                pass

        if not file_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"File '{safe_name}' was not found. Please upload the file first via POST /upload/.",
            )

        original_filename = re.sub(r"^[0-9a-f]{32}_", "", safe_name, count=1) or safe_name

    return file_path, original_filename, extra_params, is_temporary


@router.get("/history")
async def list_user_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Return unified document and activity history strictly scoped to the authenticated user.
    Combines all previously uploaded files (PDF, DOCX, CSV, XLSX) and their previous work:
    - PDF/DOCX: filename, upload/last activity date, question count, latest Q&A preview, open chat action
    - CSV/XLSX: filename, upload date, analysis/AI Insights availability, open analysis action
    """
    docs = (
        db.query(Document)
        .filter(Document.user_id == current_user.id)
        .order_by(Document.uploaded_at.desc())
        .all()
    )

    doc_ids = [d.id for d in docs]
    all_msgs = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.document_id.in_(doc_ids),
            ChatMessage.user_id == current_user.id,
        )
        .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
        .all()
    ) if doc_ids else []

    msgs_by_doc = collections.defaultdict(list)
    for m in all_msgs:
        msgs_by_doc[m.document_id].append(m)

    history = []
    for doc in docs:
        saved_name = doc.saved_filename or ""
        orig_name = doc.original_filename or saved_name or "Document"
        suffix = Path(saved_name or orig_name).suffix.lower()
        is_doc = suffix in SUPPORTED_EXTENSIONS or (doc.file_type or "").upper() in ("PDF", "DOCX")

        if is_doc:
            msgs = msgs_by_doc[doc.id]
            user_msgs = [m for m in msgs if m.role == "user"]
            asst_msgs = [m for m in msgs if m.role == "assistant"]

            latest_user_msg = user_msgs[-1] if user_msgs else None
            latest_asst_msg = None
            if latest_user_msg:
                following_asst = [m for m in asst_msgs if m.id > latest_user_msg.id]
                latest_asst_msg = following_asst[0] if following_asst else (asst_msgs[-1] if asst_msgs else None)
            else:
                latest_asst_msg = asst_msgs[-1] if asst_msgs else None

            answer_text = latest_asst_msg.content if latest_asst_msg else ""
            preview = (
                answer_text[:160] + "..."
                if len(answer_text) > 160
                else answer_text
            )

            last_active = msgs[-1].created_at if msgs and msgs[-1].created_at else doc.uploaded_at

            history.append({
                "id": doc.id,
                "document_id": doc.id,
                "filename": orig_name,
                "original_filename": orig_name,
                "saved_filename": doc.saved_filename,
                "file_type": doc.file_type or ("DOCX" if suffix == ".docx" else "PDF"),
                "file_size_bytes": doc.file_size_bytes,
                "uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else None,
                "last_activity": last_active.isoformat() if last_active else None,
                "has_chat": len(user_msgs) > 0,
                "question_count": len(user_msgs),
                "message_count": len(msgs),
                "latest_question": latest_user_msg.content if latest_user_msg else None,
                "latest_answer": answer_text if latest_asst_msg else None,
                "latest_preview": preview if latest_asst_msg else None,
                "action": "open_chat",
            })
        else:
            has_insights = bool(doc.ai_insights and doc.ai_insights.strip())
            history.append({
                "id": doc.id,
                "document_id": doc.id,
                "filename": orig_name,
                "original_filename": orig_name,
                "saved_filename": doc.saved_filename,
                "file_type": doc.file_type or ("XLSX" if suffix == ".xlsx" else "CSV"),
                "file_size_bytes": doc.file_size_bytes,
                "uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else None,
                "last_activity": doc.uploaded_at.isoformat() if doc.uploaded_at else None,
                "has_analysis": True,
                "has_insights": has_insights,
                "action": "open_analysis",
            })

    history.sort(
        key=lambda x: x.get("last_activity") or x.get("uploaded_at") or "",
        reverse=True,
    )

    return {
        "status": "success",
        "count": len(history),
        "history": history,
    }


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

@router.get("/chat-history")
async def list_chat_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return chat history strictly scoped to the authenticated user, grouped by document (one entry per document)."""
    doc_activity = (
        db.query(
            ChatMessage.document_id,
            func.max(ChatMessage.created_at).label("last_active"),
            func.max(ChatMessage.id).label("latest_msg_id"),
        )
        .filter(
            ChatMessage.user_id == current_user.id,
            ChatMessage.document_id.isnot(None),
        )
        .group_by(ChatMessage.document_id)
        .order_by(func.max(ChatMessage.created_at).desc(), func.max(ChatMessage.id).desc())
        .all()
    )

    doc_ids = [row.document_id for row in doc_activity]
    docs_by_id = {
        d.id: d
        for d in db.query(Document).filter(
            Document.id.in_(doc_ids),
            (Document.user_id == current_user.id) | (Document.user_id.is_(None))
        ).all()
    } if doc_ids else {}

    all_chat_history_msgs = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.document_id.in_(doc_ids),
            ChatMessage.user_id == current_user.id,
        )
        .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
        .all()
    ) if doc_ids else []

    chat_msgs_by_doc = collections.defaultdict(list)
    for m in all_chat_history_msgs:
        chat_msgs_by_doc[m.document_id].append(m)

    history = []
    for row in doc_activity:
        doc_id = row.document_id
        last_active = row.last_active

        doc = docs_by_id.get(doc_id)
        if not doc:
            continue
        # Strict user isolation check
        if doc.user_id is not None and doc.user_id != current_user.id:
            continue

        msgs = chat_msgs_by_doc[doc_id]
        if not msgs:
            continue

        user_msgs = [m for m in msgs if m.role == "user"]
        asst_msgs = [m for m in msgs if m.role == "assistant"]

        latest_user_msg = user_msgs[-1] if user_msgs else None
        latest_asst_msg = None
        if latest_user_msg:
            following_asst = [m for m in asst_msgs if m.id > latest_user_msg.id]
            latest_asst_msg = following_asst[0] if following_asst else (asst_msgs[-1] if asst_msgs else None)
        else:
            latest_asst_msg = asst_msgs[-1] if asst_msgs else None

        answer_text = latest_asst_msg.content if latest_asst_msg else ""
        preview = (
            answer_text[:160] + "..."
            if len(answer_text) > 160
            else answer_text
        )

        history.append({
            "id": doc.id,
            "document_id": doc.id,
            "document_name": doc.original_filename or "Document",
            "saved_filename": doc.saved_filename,
            "file_type": doc.file_type or "PDF",
            "question": latest_user_msg.content if latest_user_msg else "",
            "answer": answer_text,
            "answer_preview": preview,
            "timestamp": (
                last_active.isoformat()
                if last_active
                else (msgs[-1].created_at.isoformat() if msgs[-1].created_at else None)
            ),
            "message_count": len(msgs),
            "question_count": len(user_msgs),
        })

    return {
        "status": "success",
        "count": len(history),
        "history": history,
    }


@router.get("/messages")
async def get_document_messages(
    saved_filename: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return all chat messages for a specific document owned by the authenticated user."""
    doc = (
        db.query(Document)
        .filter(Document.saved_filename == saved_filename)
        .first()
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    if doc.user_id is not None and doc.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this document.",
        )

    messages = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.document_id == doc.id,
            ChatMessage.user_id == current_user.id,
        )
        .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
        .all()
    )
    return {
        "status": "success",
        "document": {
            "id": doc.id,
            "original_filename": doc.original_filename,
            "saved_filename": doc.saved_filename,
            "file_type": doc.file_type,
        },
        "messages": [
            {
                "id": msg.id,
                "role": msg.role,
                "content": msg.content,
                "sources": msg.sources or [],
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
            }
            for msg in messages
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

    # Reuse existing in-memory index when available to avoid duplicate extraction & embedding work
    if not is_temporary:
        base_name = file_path.name
        existing_doc_chunks = [
            c for c in vector_index.chunks
            if c.get("user_id") == current_user.id
            and (
                c.get("saved_filename") == base_name
                or c.get("filename") == base_name
                or (c.get("saved_filename") and Path(c.get("saved_filename")).name == base_name)
                or (c.get("filename") and Path(c.get("filename")).name == base_name)
            )
        ]
        if existing_doc_chunks:
            return {
                "status": "success",
                "filename": original_filename,
                "saved_filename": base_name,
                "file_type": EXTENSION_LABELS.get(file_path.suffix.lower(), "DOCUMENT"),
                "chunks_indexed": len(existing_doc_chunks),
                "total_indexed_chunks": vector_index.count(user_id=current_user.id),
                "metadata": {},
                "reused_index": True,
            }

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
        try:
            file_to_index = storage_service.get_file_path(target_name)
        except Exception:
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

    # Generate answer via LLM service
    try:
        answer_data = generate_rag_answer(question=question, chunks=retrieved_chunks)

        # Multi-stage evidence expansion: if first retrieval result did not contain enough context,
        # search and re-rank additional candidate evidence before returning an unavailable response.
        insufficient_markers = [
            "does not contain sufficient information",
            "insufficient information to answer",
            "cannot find sufficient information",
            "no information is provided",
            "not mentioned in the provided",
            "not found in the provided",
        ]
        ans_text_lower = (answer_data.get("answer") or "").lower()
        if any(marker in ans_text_lower for marker in insufficient_markers):
            total_doc_chunks = len([
                c for c in vector_index.chunks
                if (current_user.id is None or c.get("user_id") == current_user.id)
            ])
            if total_doc_chunks > len(retrieved_chunks):
                expanded_top_k = min(12, max(len(retrieved_chunks) + 4, total_doc_chunks))
                expanded_chunks = retrieve_relevant_chunks(
                    query=question,
                    top_k=expanded_top_k,
                    filename=target_name,
                    user_id=current_user.id,
                    index=vector_index,
                )
                if len(expanded_chunks) > len(retrieved_chunks):
                    secondary_answer = generate_rag_answer(question=question, chunks=expanded_chunks)
                    sec_text_lower = (secondary_answer.get("answer") or "").lower()
                    if not any(marker in sec_text_lower for marker in insufficient_markers):
                        answer_data = secondary_answer
                        retrieved_chunks = expanded_chunks

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


@router.delete("/{document_id}")
async def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Permanently delete a document and all associated data owned by the authenticated user:
    - Verifies document ownership (cross-user delete blocked with 403 Forbidden).
    - For PDF/DOCX: deletes Document, ChatMessage records, in-memory RAG index, and uploaded file on disk.
    - For CSV/XLSX: deletes Document, saved AI Insights, and uploaded file on disk.
    - Does not expose filesystem paths or sensitive information.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    if doc.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to delete this document.",
        )

    saved_filename = doc.saved_filename
    doc_id = doc.id

    # 1. Clean up in-memory vector index for this document & user
    if saved_filename:
        try:
            vector_index.remove_document(saved_filename, user_id=current_user.id)
        except Exception as e:
            logger.warning("Error clearing vector index for document %s: %s", saved_filename, e)

    # 2. Delete all ChatMessages associated with this document and user
    try:
        db.query(ChatMessage).filter(
            ChatMessage.document_id == doc_id,
            ChatMessage.user_id == current_user.id,
        ).delete(synchronize_session=False)
    except Exception as e:
        logger.warning("Error deleting chat messages for document %s: %s", doc_id, e)

    # 3. Delete the uploaded file from storage (without exposing path)
    if saved_filename:
        safe_name = Path(saved_filename).name
        try:
            storage_service.delete_file(safe_name)
        except StorageError as e:
            logger.error("Error deleting file %s from persistent storage: %s", safe_name, e)
            raise HTTPException(
                status_code=502,
                detail="Failed to delete file from persistent storage.",
            )
        except Exception as e:
            logger.warning("Error deleting file %s: %s", safe_name, e)

    # 4. Delete the Document record (cascades or deletes saved ai_insights)
    db.delete(doc)
    db.commit()

    return {
        "status": "success",
        "message": "Document and associated data permanently deleted.",
        "deleted_id": doc_id,
    }
