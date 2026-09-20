"""
services/rag.py - Basic Retrieval-Augmented Generation (RAG) pipeline for PDF and DOCX.

Features:
- Splits extracted document text into overlapping chunks.
- Preserves source references: PDF page number or DOCX paragraph number.
- Generates local embeddings using sentence-transformers (all-MiniLM-L6-v2).
- Stores embeddings in a simple in-memory vector index using NumPy.
- Fast cosine-similarity retrieval returning the top relevant chunks with source metadata.
"""

from pathlib import Path
from typing import Any
import numpy as np

DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"
DEFAULT_CHUNK_SIZE = 500
DEFAULT_CHUNK_OVERLAP = 100


def split_text_into_chunks(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[str]:
    """
    Split text into overlapping chunks respecting whitespace boundaries where feasible.

    Args:
        text: Input text string.
        chunk_size: Maximum character length of each chunk.
        chunk_overlap: Number of overlapping characters between consecutive chunks.

    Returns:
        List of non-empty chunk strings.
    """
    if not text:
        return []

    cleaned = text.strip()
    if not cleaned:
        return []

    if len(cleaned) <= chunk_size:
        return [cleaned]

    step = max(1, chunk_size - chunk_overlap)
    chunks: list[str] = []
    text_len = len(cleaned)
    start = 0

    while start < text_len:
        end = min(start + chunk_size, text_len)

        # Break at word boundary if not at the absolute end
        if end < text_len:
            # Look for whitespace boundary in the latter half of the window
            boundary = cleaned.rfind(" ", start + step // 2, end)
            if boundary != -1:
                end = boundary

        chunk_content = cleaned[start:end].strip()
        if chunk_content:
            chunks.append(chunk_content)

        if end >= text_len:
            break

        start += step

    return chunks


def chunk_extracted_document(
    doc_data: dict[str, Any],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[dict[str, Any]]:
    """
    Split extracted document text (from Step 11 extraction) into overlapping chunks
    with source references (PDF page_number or DOCX paragraph_number).

    Args:
        doc_data: Output dictionary from extract_document / extract_text_from_pdf / extract_text_from_docx.
        chunk_size: Maximum chunk size in characters.
        chunk_overlap: Overlap between consecutive chunks.

    Returns:
        List of chunk dictionaries with metadata and source references.
    """
    filename = doc_data.get("filename", "document")
    file_type = (doc_data.get("file_type") or "PDF").upper()
    chunks: list[dict[str, Any]] = []
    chunk_counter = 0

    pages = doc_data.get("pages") or []
    paragraphs = doc_data.get("paragraphs") or []

    if file_type == "PDF" and pages:
        for page in pages:
            page_num = page.get("page_number", 1)
            page_text = page.get("text", "")
            page_chunks = split_text_into_chunks(page_text, chunk_size, chunk_overlap)

            for c_idx, chunk_text in enumerate(page_chunks):
                chunk_counter += 1
                chunks.append({
                    "chunk_id": f"{filename}_p{page_num}_c{c_idx}",
                    "text": chunk_text,
                    "filename": filename,
                    "file_type": "PDF",
                    "page_number": page_num,
                    "paragraph_number": None,
                    "chunk_index": chunk_counter,
                    "character_count": len(chunk_text),
                    "word_count": len(chunk_text.split()),
                })

    elif file_type == "DOCX" and paragraphs:
        for para in paragraphs:
            para_num = para.get("paragraph_number", 1)
            para_text = para.get("text", "")
            para_chunks = split_text_into_chunks(para_text, chunk_size, chunk_overlap)

            for c_idx, chunk_text in enumerate(para_chunks):
                chunk_counter += 1
                chunks.append({
                    "chunk_id": f"{filename}_para{para_num}_c{c_idx}",
                    "text": chunk_text,
                    "filename": filename,
                    "file_type": "DOCX",
                    "page_number": None,
                    "paragraph_number": para_num,
                    "chunk_index": chunk_counter,
                    "character_count": len(chunk_text),
                    "word_count": len(chunk_text.split()),
                })

    else:
        # Fallback if pages or paragraphs list is empty
        full_text = doc_data.get("text", "")
        fallback_chunks = split_text_into_chunks(full_text, chunk_size, chunk_overlap)
        for c_idx, chunk_text in enumerate(fallback_chunks):
            chunk_counter += 1
            chunks.append({
                "chunk_id": f"{filename}_c{c_idx}",
                "text": chunk_text,
                "filename": filename,
                "file_type": file_type,
                "page_number": 1 if file_type == "PDF" else None,
                "paragraph_number": 1 if file_type == "DOCX" else None,
                "chunk_index": chunk_counter,
                "character_count": len(chunk_text),
                "word_count": len(chunk_text.split()),
            })

    return chunks


class EmbeddingService:
    """Service to load sentence-transformers model and generate local text embeddings."""

    _model = None

    @classmethod
    def get_model(cls, model_name: str = DEFAULT_EMBEDDING_MODEL):
        if cls._model is None:
            from sentence_transformers import SentenceTransformer
            cls._model = SentenceTransformer(model_name)
        return cls._model

    @classmethod
    def encode(cls, texts: list[str] | str, model_name: str = DEFAULT_EMBEDDING_MODEL) -> np.ndarray:
        """
        Generate L2-normalized embeddings for input text(s).

        Returns:
            np.ndarray of shape (N, embedding_dim) and float32 dtype.
        """
        if isinstance(texts, str):
            texts = [texts]

        if len(texts) == 0:
            return np.empty((0, 384), dtype=np.float32)

        model = cls.get_model(model_name)
        embeddings = model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(embeddings, dtype=np.float32)


class InMemoryVectorIndex:
    """
    Simple, fast in-memory vector index using NumPy for cosine similarity search.
    """

    def __init__(self):
        self.chunks: list[dict[str, Any]] = []
        self.embeddings: np.ndarray | None = None

    def add_documents(self, chunks: list[dict[str, Any]], embeddings: np.ndarray) -> int:
        """
        Add chunks and their corresponding embeddings to the in-memory index.

        Args:
            chunks: List of chunk metadata dictionaries.
            embeddings: 2D numpy array of shape (len(chunks), embedding_dim).

        Returns:
            Total number of chunks currently stored in index.
        """
        if len(chunks) == 0:
            return len(self.chunks)

        emb_array = np.asarray(embeddings, dtype=np.float32)
        if len(chunks) != len(emb_array):
            raise ValueError(
                f"Chunks count ({len(chunks)}) does not match embeddings length ({len(emb_array)})."
            )

        self.chunks.extend(chunks)

        if self.embeddings is None or self.embeddings.size == 0:
            self.embeddings = emb_array
        else:
            self.embeddings = np.vstack([self.embeddings, emb_array])

        return len(self.chunks)

    def search(
        self,
        query_embedding: np.ndarray,
        top_k: int = 5,
        filename: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Retrieve the top_k most relevant chunks for a given query embedding.

        Args:
            query_embedding: 1D or 2D vector for the query.
            top_k: Maximum number of results to return.
            filename: Optional filter to search within a specific document.

        Returns:
            List of chunk dicts sorted descending by similarity score.
        """
        if self.embeddings is None or len(self.chunks) == 0:
            return []

        q = np.asarray(query_embedding, dtype=np.float32).reshape(-1)
        q_norm = np.linalg.norm(q)
        if q_norm > 0:
            q = q / q_norm

        if filename:
            indices = [i for i, c in enumerate(self.chunks) if c.get("filename") == filename]
            if not indices:
                return []
            sub_embeddings = self.embeddings[indices]
            sub_norms = np.linalg.norm(sub_embeddings, axis=1, keepdims=True)
            sub_norms[sub_norms == 0] = 1.0
            norm_sub_embeddings = sub_embeddings / sub_norms
            similarities = np.dot(norm_sub_embeddings, q)

            ranked_order = np.argsort(-similarities)
            k = min(top_k, len(indices))
            results: list[dict[str, Any]] = []

            for r_i in ranked_order[:k]:
                orig_i = indices[r_i]
                chunk_copy = dict(self.chunks[orig_i])
                chunk_copy["score"] = round(float(similarities[r_i]), 4)
                results.append(chunk_copy)

            return results
        else:
            norms = np.linalg.norm(self.embeddings, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            norm_embeddings = self.embeddings / norms
            similarities = np.dot(norm_embeddings, q)

            k = min(top_k, len(self.chunks))
            ranked_indices = np.argsort(-similarities)[:k]

            results = []
            for idx in ranked_indices:
                chunk_copy = dict(self.chunks[idx])
                chunk_copy["score"] = round(float(similarities[idx]), 4)
                results.append(chunk_copy)

            return results

    def clear(self) -> None:
        """Clear all indexed documents and embeddings."""
        self.chunks = []
        self.embeddings = None

    def count(self) -> int:
        """Return total number of chunks currently indexed."""
        return len(self.chunks)


# Global singleton vector index for in-memory RAG
vector_index = InMemoryVectorIndex()


def index_document_data(
    doc_data: dict[str, Any],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    index: InMemoryVectorIndex = vector_index,
) -> dict[str, Any]:
    """
    Chunk extracted document data, generate embeddings, and index into in-memory store.

    Args:
        doc_data: Dictionary output from document extraction service.
        chunk_size: Chunk size in characters.
        chunk_overlap: Overlap in characters.
        index: Target InMemoryVectorIndex instance.

    Returns:
        Summary dict containing indexing metadata and chunk count.
    """
    chunks = chunk_extracted_document(doc_data, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    if not chunks:
        return {
            "status": "success",
            "filename": doc_data.get("filename", "document"),
            "file_type": doc_data.get("file_type", "UNKNOWN"),
            "chunks_indexed": 0,
            "total_indexed_chunks": index.count(),
            "metadata": doc_data.get("metadata", {}),
        }

    texts = [c["text"] for c in chunks]
    embeddings = EmbeddingService.encode(texts)
    total_indexed = index.add_documents(chunks, embeddings)

    return {
        "status": "success",
        "filename": doc_data.get("filename", "document"),
        "file_type": doc_data.get("file_type", "UNKNOWN"),
        "chunks_indexed": len(chunks),
        "total_indexed_chunks": total_indexed,
        "metadata": doc_data.get("metadata", {}),
    }


def retrieve_relevant_chunks(
    query: str,
    top_k: int = 5,
    filename: str | None = None,
    index: InMemoryVectorIndex = vector_index,
) -> list[dict[str, Any]]:
    """
    Retrieve top relevant chunks matching query using semantic similarity search.

    Args:
        query: Query string.
        top_k: Maximum chunks to retrieve.
        filename: Optional filter by filename.
        index: Vector index instance.

    Returns:
        List of matching chunk dicts with source references and similarity scores.
    """
    if not query or not query.strip():
        return []

    q_embedding = EmbeddingService.encode(query.strip())
    return index.search(q_embedding, top_k=top_k, filename=filename)
