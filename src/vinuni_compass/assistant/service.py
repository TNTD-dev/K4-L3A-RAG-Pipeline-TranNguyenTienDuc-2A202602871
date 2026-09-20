"""Framework-independent assistant implementation used by all UI adapters."""

from __future__ import annotations

from collections.abc import Iterable

from src.contracts import GenerationResult
from src.task10_generation import SYSTEM_PROMPT, call_llm, format_context, reorder_for_llm

from ..models import ChatRequest, StreamEvent
from ..retrieval.interface import RetrievalEngine


class DefaultCompassAssistant:
    def __init__(self, retrieval: RetrievalEngine, *, score_threshold: float = 0.3) -> None:
        self.retrieval = retrieval
        self.score_threshold = score_threshold

    def answer(self, request: ChatRequest) -> GenerationResult:
        chunks = self.retrieval.retrieve(request.query, mode=request.mode, top_k=request.top_k)
        if not chunks:
            return {"answer": "Tôi không thể xác minh thông tin này từ nguồn hiện có.", "sources": [], "retrieval_source": "none"}
        context = format_context(reorder_for_llm(chunks))
        answer = call_llm(SYSTEM_PROMPT, f"Context:\n{context}\n\nQuestion: {request.query}")
        method = chunks[0].get("retrieval_method")
        return {
            "answer": answer or "Tôi không thể xác minh thông tin này từ nguồn hiện có.",
            "sources": chunks,
            "retrieval_source": method if method in {"hybrid", "pageindex"} else "hybrid",
        }

    def stream(self, request: ChatRequest) -> Iterable[StreamEvent]:
        result = self.answer(request)
        yield StreamEvent(type="delta", data=result["answer"])
        yield StreamEvent(type="sources", metadata={"sources": result["sources"], "retrieval_source": result["retrieval_source"]})
        yield StreamEvent(type="done")
