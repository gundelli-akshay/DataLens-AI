"""
api/documents.py - Document extraction, indexing, and RAG retrieval endpoints.

Endpoints:
- POST /documents/extract (or POST /documents/): Extract raw text & metadata from PDF/DOCX
- POST /documents/index: Extract, split into overlapping chunks, embed, and store in-memory
- POST /documents/retrieve: Semantic search returning top relevant chunks with source references (page/para)
- POST /documents/clear-index: Reset in-memory vector index

Supports: PDF, DOCX
Rejects: CSV, XLSX (415), unsupported file types (415)
"""

from pathlib import Path
import re
from typing import Any
import uuid

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.config import settings
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

router = APIRouter(prefix="/documents", tags=["Documents"])

SUPPORTED_EXTENSIONS = {".pdf", ".docx"}
TABULAR_EXTENSIONS = {".csv", ".xlsx"}


class DocumentExtractRequest(BaseModel):
    saved_filename: str | None = None
    filename: str | None = None


class DocumentIndexRequest(BaseModel):
    saved_filename: str | None = None
    filename: str | None = None
    chunk_size: int = Field(default=DEFAULT_CHUNK_SIZE, ge=50, le=5000)
    chunk_overlap: int = Field(default=DEFAULT_CHUNK_OVERLAP, ge=0, le=2000)


class DocumentChatRequest(BaseModel):
    question: str
    filename: str | None = None
    saved_filename: str | None = None
    top_k: int = Field(default=4, ge=1, le=20)


class DocumentRetrieveRequest(BaseModel):
    query: str
    top_k: int = Field(default=5, ge=1, le=50)
    filename: str | None = None


def _safe_filename(original: str) -> str:
    base = Path(original).name
    safe = "".join(
        c if (c.isalnum() or c in (".", "-", "_")) else "_"
        for c in base
    )
    return f"{uuid.uuid4().hex}_{safe}"


async def _resolve_document_file(request: Request) -> tuple[Path, str, dict[str, Any]]:
    """
    Helper to extract file_path, original_filename, and parameters from either
    multipart/form-data or JSON body.
    """
    content_type = request.headers.get("content-type", "")
    saved_filename: str | None = None
    file_bytes: bytes | None = None
    original_filename: str = ""
    extra_params: dict[str, Any] = {}

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

    return file_path, original_filename, extra_params


@router.post("/extract")
@router.post("/")
async def process_document(request: Request):
    """
    Process an uploaded PDF or DOCX file and extract clean text with metadata.

    Supports:
      - JSON body: {"saved_filename": "<uuid>_file.pdf"}
      - Multipart form-data: file upload
    """
    file_path, original_filename, _ = await _resolve_document_file(request)

    try:
        return extract_document(file_path, original_filename)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred while extracting text from the document: {str(e)}",
        )


@router.post("/index")
async def index_document_endpoint(request: Request):
    """
    Extract text from a PDF or DOCX document, split into overlapping chunks,
    compute local embeddings via sentence-transformers, and index in memory.

    Supports:
      - Multipart form: file upload (optional chunk_size, chunk_overlap)
      - JSON body: {"saved_filename": "...", "chunk_size": 500, "chunk_overlap": 100}
    """
    file_path, original_filename, extra_params = await _resolve_document_file(request)

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
        raise HTTPException(
            status_code=500,
            detail=f"Failed to extract document for indexing: {str(e)}",
        )

    try:
        index_result = index_document_data(
            extraction_result,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            index=vector_index,
        )
        return index_result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to index document: {str(e)}",
        )


@router.post("/retrieve")
async def retrieve_endpoint(payload: DocumentRetrieveRequest):
    """
    Retrieve top relevant chunks matching a semantic query.

    Request JSON:
      - query: query string (required)
      - top_k: maximum number of chunks to return (default: 5)
      - filename: optional filter to limit search to a specific document

    Returns:
      Matching chunks sorted descending by cosine similarity score,
      including source references (page_number or paragraph_number).
    """
    query = payload.query.strip() if payload.query else ""
    if not query:
        raise HTTPException(status_code=400, detail="Query string cannot be empty.")

    try:
        results = retrieve_relevant_chunks(
            query=query,
            top_k=payload.top_k,
            filename=payload.filename,
            index=vector_index,
        )
        return {
            "status": "success",
            "query": query,
            "count": len(results),
            "results": results,
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Retrieval query failed: {str(e)}",
        )


@router.post("/clear-index")
async def clear_index_endpoint():
    """Clear all stored embeddings and chunks from the in-memory vector index."""
    vector_index.clear()
    return {
        "status": "success",
        "message": "In-memory vector index cleared.",
        "total_indexed_chunks": 0,
    }

@router.post("/chat")
async def chat_document_endpoint(payload: DocumentChatRequest):
    """
    Answer user questions about an uploaded PDF/DOCX document using RAG retrieval + Groq LLM.
    Strictly grounds answers in the retrieved document chunks and cites page/paragraph sources.
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

    # If no chunks match target_name in vector_index, check if file exists on disk to auto-index
    def _has_chunks(fn: str) -> bool:
        base = Path(fn).name
        for c in vector_index.chunks:
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
        orig_name = target_name

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
                orig_name = re.sub(r"^[0-9a-f]{32}_", "", file_to_index.name, count=1) or file_to_index.name
                extraction_result = extract_document(file_to_index, orig_name)
                extraction_result["saved_filename"] = file_to_index.name
                index_document_data(extraction_result, index=vector_index)
            except Exception as e:
                # If extraction fails, continue to retrieval or error
                pass

    # Retrieve relevant chunks matching query
    try:
        retrieved_chunks = retrieve_relevant_chunks(
            query=question,
            top_k=payload.top_k,
            filename=target_name,
            index=vector_index,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"RAG retrieval failed: {str(e)}")

    # Generate answer via Groq LLM service
    try:
        answer_data = generate_rag_answer(question=question, chunks=retrieved_chunks)
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
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LLM service error: {str(exc)}")
