"""Public retrieval module interface."""

from typing import Protocol

from src.contracts import SearchResult

from ..models import Mode


class RetrievalEngine(Protocol):
    """Hide routing, dense, BM25, RRF, thresholds, and fallback."""

    def retrieve(
        self,
        query: str,
        *,
        mode: Mode = "auto",
        top_k: int = 5,
    ) -> list[SearchResult]: ...
