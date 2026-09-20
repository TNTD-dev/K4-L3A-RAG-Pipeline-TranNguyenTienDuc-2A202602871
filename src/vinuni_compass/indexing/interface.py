"""Public indexing module interface."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from src.task4_chunking_indexing import chunk_documents, embed_chunks, load_documents, index_to_vectorstore


@dataclass(frozen=True)
class IndexReport:
    collection_name: str
    document_count: int
    chunk_count: int


class IndexBuilder(Protocol):
    """Deep seam hiding loading, chunking, embedding, and upserting."""

    def build(self, snapshot_directory: Path) -> IndexReport: ...


class TaskIndexBuilder:
    """Default composition adapter around the stable course task seam."""

    def build(self, snapshot_directory: Path) -> IndexReport:
        import src.task4_chunking_indexing as task4

        old_directory = task4.STANDARDIZED_DIR
        task4.STANDARDIZED_DIR = snapshot_directory
        try:
            documents = load_documents()
            chunks = chunk_documents(documents)
            indexed = embed_chunks(chunks)
            index_to_vectorstore(indexed)
        finally:
            task4.STANDARDIZED_DIR = old_directory
        return IndexReport(
            collection_name=task4.COLLECTION_NAME,
            document_count=len(documents),
            chunk_count=len(indexed),
        )
