"""
services/rag.py - Advanced Lightweight Hybrid RAG Pipeline for PDF and DOCX.

Features:
- Splits extracted document text into overlapping chunks.
- Preserves source references: PDF page number or DOCX paragraph number.
- Generates local embeddings using sentence-transformers (all-MiniLM-L6-v2).
- Fast in-memory hybrid retrieval combining dense semantic similarity with
  stemmed BM25 keyword overlap for exact factual question accuracy.
- Long-document summarization retrieval covering representative sections
  (Beginning / Abstract, Intermediate Modules/Sections, and Conclusions).
- High-precision filtering with document and multi-tenant user scoping.
"""

import math
from pathlib import Path
import re
from typing import Any
from collections import Counter
import numpy as np

DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"
DEFAULT_CHUNK_SIZE = 500
DEFAULT_CHUNK_OVERLAP = 100

STOP_WORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can't", "cannot", "could", "couldn't",
    "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down", "during",
    "each", "few", "for", "from", "further", "had", "hadn't", "has", "hasn't",
    "have", "haven't", "having", "he", "he'd", "he'll", "he's", "her", "here",
    "here's", "hers", "herself", "him", "himself", "his", "how", "how's", "i",
    "i'd", "i'll", "i'm", "i've", "if", "in", "into", "is", "isn't", "it", "it's",
    "its", "itself", "let's", "me", "more", "most", "mustn't", "my", "myself",
    "no", "nor", "not", "of", "off", "on", "once", "only", "or", "other", "ought",
    "our", "ours", "ourselves", "out", "over", "own", "same", "shan't", "she",
    "she'd", "she'll", "she's", "should", "shouldn't", "so", "some", "such",
    "than", "that", "that's", "the", "their", "theirs", "them", "themselves",
    "then", "there", "there's", "these", "they", "they'd", "they'll", "they're",
    "they've", "this", "those", "through", "to", "too", "under", "until", "up",
    "very", "was", "wasn't", "we", "we'd", "we'll", "we're", "we've", "were",
    "weren't", "what", "what's", "when", "when's", "where", "where's", "which",
    "while", "who", "who's", "whom", "why", "why's", "with", "won't", "would",
    "wouldn't", "you", "you'd", "you'll", "you're", "you've", "your", "yours",
    "yourself", "yourselves"
}


def _tokenize_text(text: str) -> list[str]:
    """Tokenize text into lowercase alphanumeric words, filtering single chars & stopwords."""
    if not text:
        return []
    words = re.findall(r"\b[a-zA-Z0-9_\-\.]+\b", text.lower())
    return [w for w in words if len(w) > 1 and w not in STOP_WORDS]


def _stem_token(w: str) -> str:
    """Lightweight suffix stripping for high-accuracy keyword matching."""
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith("ing") and len(w) > 4:
        return w[:-3]
    if w.endswith("ed") and len(w) > 3:
        return w[:-2]
    if w.endswith("es") and len(w) > 3:
        return w[:-2]
    if w.endswith("s") and len(w) > 2 and not w.endswith("ss"):
        return w[:-1]
    return w


def strip_formatting_instructions(query: str) -> str:
    """
    Remove presentation/formatting directives (e.g., 'in tabular form', 'as a table',
    'in bullet points') from query so they do not degrade retrieval accuracy.
    """
    if not query:
        return ""

    cleaned = query.strip()

    patterns = [
        # Action + presentation format: e.g. "answer in tabular form", "give as a table", "respond in bullets"
        r"\b(answer|respond|provide|give|present|display|show|list)\s+(this\s+)?(in|as)\s+(a\s+)?(tabular\s+form(at)?|table\s+form(at)?|table|bullet\s+points?|bullets?|numbered\s+list|points?)\b",
        r"\bformat\s+(this\s+)?(as|in)\s+(a\s+)?(table|tabular\s+form(at)?|bullet\s+points?|numbered\s+list)\b",
        # Prepositional phrases: e.g. "in tabular form", "as a table", "in table format", "in bullets"
        r"\b(in|as)\s+(a\s+)?(tabular\s+form(at)?|table\s+form(at)?|table|bullet\s+points?|bullets?|bulleted\s+list|numbered\s+list|point\s+form)\b",
        r"\b(tabular\s+form(at)?|table\s+form(at)?)\b",
        r"\b(bullet\s+points?|bulleted\s+list|numbered\s+list)\b",
    ]

    for pat in patterns:
        cleaned = re.sub(pat, "", cleaned, flags=re.IGNORECASE)

    # Clean up leftover punctuation or whitespace
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"^[\s,;:\-\?]+", "", cleaned)
    cleaned = re.sub(r"[\s,;:\-]+$", "", cleaned).strip()

    if query.strip().endswith("?") and not cleaned.endswith("?"):
        cleaned = cleaned + "?"

    # If the entire query was formatting instructions, keep original
    if not cleaned or len(cleaned) < 2:
        return query.strip()

    return cleaned


def is_summary_query(query: str) -> bool:
    """Detect if a user query is asking for a summary or broad document overview."""
    if not query:
        return False
    clean_q = strip_formatting_instructions(query)
    for q_check in [query, clean_q]:
        q_lower = q_check.lower().strip()
        patterns = [
            r"\bsummar(y|ize|ise|izing|ising)\b",
            r"\b(key|main|core|major|primary|important|principal)\s+(topics?|findings?|points?|takeaways?|ideas?|aspects?|themes?|areas?|components?|modules?|sections?|features?|conclusions?|recommendations?)\b",
            r"\bwhat\s+(is|are)\s+(the\s+)?(document|project|paper|report|system|dataset|file|article)\s+about\b",
            r"\bwhat\s+(does|do)\s+(the\s+)?(document|project|paper|report|system|author)\s+(discuss|cover|describe|present|explain|propose|detail)\b",
            r"\boverview\b",
            r"\bexecutive\s+summary\b",
            r"\bhigh-?level\s+overview\b",
            r"\bbriefly\s+explain\s+the\s+(document|project|paper|report)\b",
            r"\btopics?\s+(covered|discussed|included)\b",
        ]
        for pat in patterns:
            if re.search(pat, q_lower):
                return True
    return False


class BM25Scorer:
    """Fast, zero-dependency in-memory BM25 scorer for candidate document chunks."""

    def __init__(self, corpus_texts: list[str], k1: float = 1.2, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.corpus_size = len(corpus_texts)
        self.doc_lens: list[int] = []
        self.doc_freqs: Counter[str] = Counter()
        self.doc_word_counts: list[Counter[str]] = []

        for text in corpus_texts:
            tokens = [_stem_token(t) for t in _tokenize_text(text)]
            self.doc_lens.append(len(tokens))
            counts = Counter(tokens)
            self.doc_word_counts.append(counts)
            for word in counts:
                self.doc_freqs[word] += 1

        self.avg_doc_len = sum(self.doc_lens) / max(1, self.corpus_size)

    def score(self, query: str) -> list[float]:
        q_tokens = [_stem_token(t) for t in _tokenize_text(query)]
        if not q_tokens or self.corpus_size == 0:
            return [0.0] * self.corpus_size

        scores = [0.0] * self.corpus_size
        q_counts = Counter(q_tokens)

        for q_word in q_counts:
            df = self.doc_freqs.get(q_word, 0)
            if df == 0:
                continue
            idf = math.log(1.0 + (self.corpus_size - df + 0.5) / (df + 0.5))

            for idx in range(self.corpus_size):
                tf = self.doc_word_counts[idx].get(q_word, 0)
                if tf == 0:
                    continue
                d_len = self.doc_lens[idx]
                numerator = tf * (self.k1 + 1.0)
                denominator = tf + self.k1 * (1.0 - self.b + self.b * (d_len / max(1.0, self.avg_doc_len)))
                scores[idx] += idf * (numerator / denominator)

        return scores


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
    user_id: Any = None,
) -> list[dict[str, Any]]:
    """
    Split extracted document text into overlapping chunks with source references
    (PDF page_number or DOCX paragraph_number).

    Args:
        doc_data: Output dictionary from extract_document.
        chunk_size: Maximum chunk size in characters.
        chunk_overlap: Overlap between consecutive chunks.
        user_id: Optional user identifier for isolation.

    Returns:
        List of chunk dictionaries with metadata and source references.
    """
    filename = doc_data.get("filename", "document")
    saved_filename = doc_data.get("saved_filename")
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
                    "saved_filename": saved_filename,
                    "file_type": "PDF",
                    "page_number": page_num,
                    "page": page_num,
                    "paragraph_number": None,
                    "user_id": user_id,
                    "chunk_index": chunk_counter,
                    "character_count": len(chunk_text),
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
                    "saved_filename": saved_filename,
                    "file_type": "DOCX",
                    "page_number": None,
                    "paragraph_number": para_num,
                    "paragraph": para_num,
                    "user_id": user_id,
                    "chunk_index": chunk_counter,
                    "character_count": len(chunk_text),
                })
    else:
        full_text = doc_data.get("text", "")
        raw_chunks = split_text_into_chunks(full_text, chunk_size, chunk_overlap)
        for c_idx, chunk_text in enumerate(raw_chunks):
            chunk_counter += 1
            chunks.append({
                "chunk_id": f"{filename}_c{c_idx}",
                "text": chunk_text,
                "filename": filename,
                "saved_filename": saved_filename,
                "file_type": file_type,
                "page_number": 1 if file_type == "PDF" else None,
                "paragraph_number": 1 if file_type == "DOCX" else None,
                "user_id": user_id,
                "chunk_index": chunk_counter,
                "character_count": len(chunk_text),
            })

    return chunks


class EmbeddingService:
    """Singleton service for generating dense embeddings via sentence-transformers."""

    _model = None

    @classmethod
    def get_model(cls, model_name: str = DEFAULT_EMBEDDING_MODEL):
        if cls._model is None:
            from sentence_transformers import SentenceTransformer
            cls._model = SentenceTransformer(model_name)
        return cls._model

    @classmethod
    def encode(cls, texts: str | list[str], model_name: str = DEFAULT_EMBEDDING_MODEL) -> np.ndarray:
        model = cls.get_model(model_name)
        if isinstance(texts, str):
            embedding = model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
            return np.asarray(embedding, dtype=np.float32)
        embeddings = model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
        return np.asarray(embeddings, dtype=np.float32)


class InMemoryVectorIndex:
    """In-memory hybrid vector store combining dense cosine similarity and BM25."""

    def __init__(self):
        self.chunks: list[dict[str, Any]] = []
        self.embeddings: np.ndarray | None = None

    def add_documents(self, chunks: list[dict[str, Any]], embeddings: np.ndarray) -> int:
        """Add chunks and their dense embeddings to the index."""
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
        query: np.ndarray | str,
        top_k: int = 5,
        filename: str | None = None,
        user_id: Any = None,
        query_text: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Retrieve relevant chunks matching query using lightweight hybrid retrieval:
        combines dense semantic similarity with BM25 keyword overlap.
        For summary/overview queries, retrieves representative content across the document.

        Args:
            query: Query string or query embedding vector.
            top_k: Maximum number of results to return.
            filename: Optional filter to search within a specific document.
            user_id: Scoping filter for multi-tenant isolation.
            query_text: Optional explicit query text string if query is a vector.

        Returns:
            List of chunk dicts with source references and relevance scores.
        """
        if self.embeddings is None or len(self.chunks) == 0:
            return []

        # Resolve query string and query embedding vector (cleaning presentation formatting for retrieval)
        q_str = ""
        if isinstance(query, str):
            q_clean = strip_formatting_instructions(query)
            q_str = q_clean.strip() or query.strip()
            query_embedding = EmbeddingService.encode(q_str)
        else:
            query_embedding = query
            q_clean = strip_formatting_instructions(query_text or "")
            q_str = q_clean.strip() or (query_text or "").strip()

        q = np.asarray(query_embedding, dtype=np.float32).reshape(-1)
        q_norm = np.linalg.norm(q)
        if q_norm > 0:
            q = q / q_norm

        def _user_matches(c: dict[str, Any]) -> bool:
            if user_id is None:
                return True
            c_uid = c.get("user_id")
            return c_uid is None or c_uid == user_id

        def _doc_matches(c: dict[str, Any]) -> bool:
            if not _user_matches(c):
                return False
            if not filename:
                return True
            c_fn = c.get("filename")
            c_sfn = c.get("saved_filename")
            if c_fn == filename or c_sfn == filename:
                return True
            target_base = Path(filename).name
            if c_fn and (Path(c_fn).name == target_base or Path(c_fn).name.endswith(f"_{target_base}")):
                return True
            if c_sfn and (Path(c_sfn).name == target_base or Path(c_sfn).name.endswith(f"_{target_base}")):
                return True
            return False

        indices = [i for i, c in enumerate(self.chunks) if _doc_matches(c)]
        if not indices:
            return []

        # 1. Compute Dense Cosine Similarities
        sub_embeddings = self.embeddings[indices]
        sub_norms = np.linalg.norm(sub_embeddings, axis=1, keepdims=True)
        sub_norms[sub_norms == 0] = 1.0
        norm_sub_embeddings = sub_embeddings / sub_norms
        dense_similarities = np.dot(norm_sub_embeddings, q)

        # 2. Check for Broad Overview / Summary Intent
        if q_str and is_summary_query(q_str):
            return self._retrieve_summary_chunks(
                indices=indices,
                dense_similarities=dense_similarities,
                top_k=top_k,
            )

        # 3. Compute BM25 Lexical Keyword Overlap Scores if query string is present
        if q_str:
            corpus_texts = [self.chunks[i]["text"] for i in indices]
            bm25 = BM25Scorer(corpus_texts)
            bm25_scores = np.array(bm25.score(q_str), dtype=np.float32)

            # Min-Max Normalization
            d_min, d_max = float(dense_similarities.min()), float(dense_similarities.max())
            d_norm = (dense_similarities - d_min) / (d_max - d_min + 1e-6)

            b_min, b_max = float(bm25_scores.min()), float(bm25_scores.max())
            if b_max > 0:
                b_norm = (bm25_scores - b_min) / (b_max - b_min + 1e-6)
                # Weighted hybrid combination: 0.55 dense + 0.45 lexical
                hybrid_scores = 0.55 * d_norm + 0.45 * b_norm

                # Exact keyword and phrase matching bonus
                q_tokens = [_stem_token(t) for t in _tokenize_text(q_str)]
                for i_pos, text in enumerate(corpus_texts):
                    text_tokens = set([_stem_token(t) for t in _tokenize_text(text)])
                    match_ratio = len(text_tokens.intersection(q_tokens)) / max(1, len(q_tokens))
                    if match_ratio >= 0.5:
                        hybrid_scores[i_pos] += 0.2 * match_ratio
            else:
                hybrid_scores = d_norm

            final_scores = hybrid_scores
        else:
            final_scores = dense_similarities

        ranked_order = np.argsort(-final_scores)
        k = min(top_k, len(indices))
        results: list[dict[str, Any]] = []

        for r_i in ranked_order[:k]:
            orig_i = indices[r_i]
            chunk_copy = dict(self.chunks[orig_i])
            chunk_copy["score"] = round(float(final_scores[r_i]), 4)
            results.append(chunk_copy)

        return results

    def _retrieve_summary_chunks(
        self,
        indices: list[int],
        dense_similarities: np.ndarray,
        top_k: int,
    ) -> list[dict[str, Any]]:
        """
        For summary/overview queries, select representative content across the document:
        - If total chunks <= top_k: returns all chunks in chronological order.
        - If total chunks > top_k: returns beginning, ending, top semantic chunks, and
          evenly distributed intermediate sections.
        """
        total = len(indices)
        if total <= top_k:
            sorted_indices = sorted(
                indices,
                key=lambda idx: (
                    self.chunks[idx].get("chunk_index", 0),
                    self.chunks[idx].get("page_number") or 0,
                    self.chunks[idx].get("paragraph_number") or 0,
                ),
            )
            results: list[dict[str, Any]] = []
            for orig_i in sorted_indices:
                chunk_copy = dict(self.chunks[orig_i])
                local_pos = indices.index(orig_i)
                chunk_copy["score"] = round(float(dense_similarities[local_pos]), 4)
                results.append(chunk_copy)
            return results

        selected_idx_set = set()

        # 1. Beginning: first chunk (title, abstract, intro)
        selected_idx_set.add(indices[0])

        # 2. Ending: last chunk (conclusion, recommendations)
        selected_idx_set.add(indices[-1])

        # 3. Top dense semantic chunks matching the query
        top_dense_indices = np.argsort(-dense_similarities)
        for t_idx in top_dense_indices:
            selected_idx_set.add(indices[t_idx])
            if len(selected_idx_set) >= min(3, top_k):
                break

        # 4. Evenly distributed intermediate points across the document
        needed = top_k - len(selected_idx_set)
        if needed > 0 and total > 2:
            step = total / (needed + 1)
            for step_i in range(1, needed + 1):
                pos = min(int(step * step_i), total - 2)
                selected_idx_set.add(indices[pos])

        # Order selected chunks chronologically by chunk_index / page_number
        sorted_indices = sorted(
            list(selected_idx_set),
            key=lambda idx: (
                self.chunks[idx].get("chunk_index", 0),
                self.chunks[idx].get("page_number") or 0,
                self.chunks[idx].get("paragraph_number") or 0,
            ),
        )

        results: list[dict[str, Any]] = []
        for orig_i in sorted_indices[:top_k]:
            chunk_copy = dict(self.chunks[orig_i])
            local_pos = indices.index(orig_i)
            chunk_copy["score"] = round(float(dense_similarities[local_pos]), 4)
            results.append(chunk_copy)

        return results

    def remove_document(self, filename: str, user_id: Any = None) -> int:
        """Remove chunks belonging to a specific document (by filename or saved_filename) for a user."""
        if not self.chunks:
            return 0

        target_base = Path(filename).name

        def _is_doc_match(c: dict[str, Any]) -> bool:
            if user_id is not None and c.get("user_id") != user_id:
                return False
            c_fn = c.get("filename")
            c_sfn = c.get("saved_filename")
            if c_fn == filename or c_sfn == filename:
                return True
            if c_fn and (Path(c_fn).name == target_base or Path(c_fn).name.endswith(f"_{target_base}")):
                return True
            if c_sfn and (Path(c_sfn).name == target_base or Path(c_sfn).name.endswith(f"_{target_base}")):
                return True
            return False

        keep_indices = [i for i, c in enumerate(self.chunks) if not _is_doc_match(c)]
        removed_count = len(self.chunks) - len(keep_indices)

        self.chunks = [self.chunks[i] for i in keep_indices]
        if not self.chunks or self.embeddings is None:
            self.embeddings = None
        else:
            self.embeddings = self.embeddings[keep_indices]

        return removed_count

    def clear(self, user_id: Any = None) -> None:
        """Clear indexed documents, scoping to user_id if provided."""
        if user_id is None:
            self.chunks = []
            self.embeddings = None
            return

        keep_indices = [i for i, c in enumerate(self.chunks) if c.get("user_id") != user_id]
        self.chunks = [self.chunks[i] for i in keep_indices]
        if not self.chunks or self.embeddings is None:
            self.embeddings = None
        else:
            self.embeddings = self.embeddings[keep_indices]

    def count(self, user_id: Any = None) -> int:
        """Return total number of chunks currently indexed, optionally filtered by user_id."""
        if user_id is None:
            return len(self.chunks)
        return sum(1 for c in self.chunks if c.get("user_id") == user_id)


# Global singleton vector index for in-memory RAG
vector_index = InMemoryVectorIndex()


def index_document_data(
    doc_data: dict[str, Any],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    user_id: Any = None,
    index: InMemoryVectorIndex = vector_index,
) -> dict[str, Any]:
    """
    Chunk extracted document data, generate dense embeddings, and index into in-memory store.

    Args:
        doc_data: Dictionary output from document extraction service.
        chunk_size: Chunk size in characters.
        chunk_overlap: Overlap in characters.
        user_id: User identifier for multi-tenant isolation.
        index: Target InMemoryVectorIndex instance.

    Returns:
        Summary dict containing indexing metadata and chunk count.
    """
    chunks = chunk_extracted_document(doc_data, chunk_size=chunk_size, chunk_overlap=chunk_overlap, user_id=user_id)
    if not chunks:
        return {
            "status": "success",
            "filename": doc_data.get("filename", "document"),
            "file_type": doc_data.get("file_type", "UNKNOWN"),
            "chunks_indexed": 0,
            "total_indexed_chunks": index.count(user_id=user_id),
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
    user_id: Any = None,
    index: InMemoryVectorIndex = vector_index,
) -> list[dict[str, Any]]:
    """
    Retrieve top relevant chunks matching query using lightweight hybrid retrieval.

    Args:
        query: Query string.
        top_k: Maximum chunks to retrieve.
        filename: Optional filter by filename.
        user_id: User identifier for multi-tenant isolation.
        index: Vector index instance.

    Returns:
        List of matching chunk dicts with source references and similarity scores.
    """
    if not query or not query.strip():
        return []

    return index.search(query=query.strip(), top_k=top_k, filename=filename, user_id=user_id)
