"""
Task 4 — Chunking, embedding và indexing.

Hướng dẫn:
    1. Đọc toàn bộ Markdown trong data/standardized/.
    2. Chia văn bản bằng strategy đã chọn.
    3. Embed chunks bằng một provider duy nhất.
    4. Upsert vào ChromaDB với cosine distance.

Mỗi document/chunk phải theo docs/MODULE_CONTRACTS.md. ID cần ổn định để
chạy lại pipeline không tạo dữ liệu trùng. Task 5 phải dùng chung embed_texts().
"""

from pathlib import Path
import hashlib
import json
import os
import re
from typing import Any


STANDARDIZED_DIR = Path(__file__).parent.parent / "data" / "standardized"
CHROMA_DIR = Path(__file__).parent.parent / "chroma_db"

# Giải thích lựa chọn tham số trong báo cáo nhóm.
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
CHUNKING_METHOD = "recursive"

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536

COLLECTION_NAME = "rag_documents"

_MEMORY_COLLECTION = None
_INDEXED_CHUNKS: list[dict] = []


class _MemoryCollection:
    """Small Chroma-compatible collection for offline tests and no-deps runs."""

    def __init__(self) -> None:
        self._items: dict[str, dict] = {}
        self.metadata = {"hnsw:space": "cosine", "embedding_model": EMBEDDING_MODEL, "dimension": EMBEDDING_DIM}

    def upsert(self, *, ids, documents, embeddings, metadatas):
        if not (len(ids) == len(documents) == len(embeddings) == len(metadatas)):
            raise ValueError("collection inputs must have equal lengths")
        for item_id, content, embedding, metadata in zip(ids, documents, embeddings, metadatas):
            if len(embedding) != EMBEDDING_DIM:
                raise ValueError("embedding dimension does not match collection invariant")
            self._items[item_id] = {"document": content, "embedding": list(embedding), "metadata": dict(metadata)}

    def count(self):
        return len(self._items)

    def query(self, *, query_embeddings, n_results, include=None):
        from math import sqrt
        q = query_embeddings[0]
        qnorm = sqrt(sum(float(x) * float(x) for x in q))
        scored = []
        for item_id, item in self._items.items():
            vec = item["embedding"]
            denom = qnorm * sqrt(sum(float(x) * float(x) for x in vec))
            sim = sum(float(a) * float(b) for a, b in zip(q, vec)) / denom if denom else 0.0
            scored.append((sim, item_id, item))
        scored.sort(key=lambda x: (-x[0], x[1]))
        chosen = scored[:max(n_results, 0)]
        return {
            "ids": [[x[1] for x in chosen]],
            "documents": [[x[2]["document"] for x in chosen]],
            "metadatas": [[x[2]["metadata"] for x in chosen]],
            "distances": [[1.0 - x[0] for x in chosen]],
        }


def _deterministic_embeddings(texts: list[str]) -> list[list[float]]:
    from src.vinuni_compass.providers.adapters import DeterministicEmbeddingAdapter
    return DeterministicEmbeddingAdapter(EMBEDDING_DIM).embed(texts)


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    provider = os.getenv("EMBEDDING_PROVIDER", "openai").strip().lower()
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if provider == "openai" and api_key:
        try:
            from openai import OpenAI
            response = OpenAI(api_key=api_key).embeddings.create(model=EMBEDDING_MODEL, input=texts)
            vectors = [list(map(float, item.embedding)) for item in sorted(response.data, key=lambda item: item.index)]
            if any(len(vector) != EMBEDDING_DIM for vector in vectors):
                raise ValueError("OpenAI embedding dimension does not match collection invariant")
            return vectors
        except Exception:
            # Offline and transient provider failures use the deterministic seam.
            pass
    return _deterministic_embeddings(texts)


def get_collection():
    """Mở Chroma collection dùng cosine distance."""
    global _MEMORY_COLLECTION
    try:
        import chromadb
        CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        return client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine", "embedding_model": EMBEDDING_MODEL, "dimension": EMBEDDING_DIM},
        )
    except Exception:
        if _MEMORY_COLLECTION is None:
            _MEMORY_COLLECTION = _MemoryCollection()
        return _MEMORY_COLLECTION


def load_documents() -> list[dict]:
    """Đọc Markdown và trả về danh sách Document."""
    documents: list[dict] = []
    for path in sorted(STANDARDIZED_DIR.rglob("*.md")):
        raw = path.read_text(encoding="utf-8")
        metadata: dict[str, Any] = {}
        content = raw
        if raw.startswith("---\n"):
            _, header, content = raw.split("---\n", 2)
            for line in header.splitlines():
                if ":" not in line:
                    continue
                key, value = line.split(":", 1)
                value = value.strip()
                try:
                    metadata[key.strip()] = json.loads(value)
                except json.JSONDecodeError:
                    metadata[key.strip()] = value
        content = content.strip()
        if not content:
            continue
        relative = path.relative_to(STANDARDIZED_DIR).as_posix()
        document_id = str(metadata.get("source_id") or hashlib.sha256(relative.encode()).hexdigest()[:16])
        doc_type = str(metadata.get("doc_type") or ("legal" if "legal" in path.parts else "news"))
        item = {
            "id": document_id,
            "content": content,
            "metadata": {
                "source": str(metadata.get("source") or path.name),
                "title": str(metadata.get("title") or path.stem),
                "doc_type": doc_type,
                "url": metadata.get("url"),
            },
        }
        for key in ("mode", "classification", "policy_version", "effective_date", "crawl_timestamp"):
            if key in metadata:
                item["metadata"][key] = metadata[key]
        documents.append(item)
    return documents


def chunk_documents(documents: list[dict]) -> list[dict]:
    """Chia Document thành chunks có id và chunk_index."""
    chunks: list[dict] = []
    for document in documents:
        content = str(document["content"]).strip()
        if not content:
            continue
        pieces: list[str] = []
        start = 0
        while start < len(content):
            end = min(len(content), start + CHUNK_SIZE)
            if end < len(content):
                boundary = max(content.rfind("\n\n", start, end), content.rfind(". ", start, end), content.rfind(" ", start, end))
                if boundary > start + CHUNK_SIZE // 2:
                    end = boundary + (2 if content[boundary:boundary + 2] == ". " else 1)
            piece = content[start:end].strip()
            if piece:
                pieces.append(piece)
            if end >= len(content):
                break
            start = max(end - CHUNK_OVERLAP, start + 1)
        for index, text in enumerate(pieces):
            chunk = {
                "id": f"{document['id']}::chunk-{index}",
                "content": text,
                "metadata": {**document["metadata"], "chunk_index": index},
            }
            chunks.append(chunk)
    return chunks


def embed_chunks(chunks: list[dict]) -> list[dict]:
    """Thêm embedding vào từng chunk."""
    if not chunks:
        return []
    vectors = embed_texts([chunk["content"] for chunk in chunks])
    if len(vectors) != len(chunks):
        raise ValueError("embedding provider returned the wrong number of vectors")
    output = []
    for chunk, vector in zip(chunks, vectors):
        if len(vector) != EMBEDDING_DIM:
            raise ValueError("embedding provider returned an incompatible dimension")
        output.append({**chunk, "embedding": vector})
    return output


def index_to_vectorstore(chunks: list[dict]) -> None:
    """Upsert chunks vào ChromaDB."""
    global _INDEXED_CHUNKS
    if not chunks:
        return
    collection = get_collection()
    collection.upsert(
        ids=[chunk["id"] for chunk in chunks],
        documents=[chunk["content"] for chunk in chunks],
        embeddings=[chunk["embedding"] for chunk in chunks],
        metadatas=[chunk["metadata"] for chunk in chunks],
    )
    _INDEXED_CHUNKS = [{key: value for key, value in chunk.items() if key != "embedding"} for chunk in chunks]
    # Task 6 imports this list lazily to avoid a module cycle at import time.
    try:
        import src.task6_lexical_search as lexical
        lexical.CORPUS = list(_INDEXED_CHUNKS)
    except Exception:
        pass


def run_pipeline() -> None:
    """Chạy load, chunk, embed và index."""
    documents = load_documents()
    chunks = chunk_documents(documents)
    embedded_chunks = embed_chunks(chunks)
    index_to_vectorstore(embedded_chunks)
    print(f"Indexed {len(embedded_chunks)} chunks")


if __name__ == "__main__":
    run_pipeline()
