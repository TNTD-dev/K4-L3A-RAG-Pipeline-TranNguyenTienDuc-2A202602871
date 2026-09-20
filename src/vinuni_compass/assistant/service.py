"""Citation-aware, UI-independent VinUni Compass assistant.

This module deliberately contains product policy rather than framework code so
Streamlit, HTTP clients, and offline tests get identical behaviour.
"""

from __future__ import annotations

from collections.abc import Iterable
import re
from typing import Literal

from src.contracts import GenerationResult
from src.contracts import SearchResult

from ..models import ChatRequest, StreamEvent
from ..providers.adapters import DeterministicGenerationAdapter
from ..providers.ports import GenerationPort
from ..retrieval.interface import RetrievalEngine


REFUSAL_VI = "Tôi không thể xác minh thông tin này từ các nguồn công khai hiện có."
REFUSAL_EN = "I cannot verify this from the available public sources."

ADMISSIONS_TERMS = (
    "admission", "admissions", "apply", "application", "applicant", "prospective",
    "tuyển sinh", "xét tuyển", "ứng tuyển", "đầu vào", "học bổng đầu vào",
)
STUDENT_LIFE_TERMS = (
    "student", "course", "academic", "semester", "dorm", "residential", "internship",
    "conduct", "discipline", "current student", "sinh viên", "học phần", "ký túc",
    "nội trú", "thực tập", "quy chế", "kỷ luật",
)
PII_PATTERN = re.compile(r"\b(?:\d{9,12}|\d{3}[- ]?\d{2}[- ]?\d{4})\b|@", re.I)


def _is_vietnamese(text: str) -> bool:
    return bool(re.search(r"[à-ỹđ]|\b(?:tôi|bạn|và|của|là|cho|không)\b", text.casefold()))


def _language(request: ChatRequest) -> Literal["vi", "en"]:
    text = request.query.casefold()
    if "in english" in text or "bằng tiếng anh" in text or "tiếng anh" in text:
        return "en"
    if "bằng tiếng việt" in text or "tiếng việt" in text:
        return "vi"
    return "vi" if _is_vietnamese(request.query) else "en"


def _route(query: str) -> Literal["admissions", "student_life"]:
    text = query.casefold()
    admissions = sum(term in text for term in ADMISSIONS_TERMS)
    student_life = sum(term in text for term in STUDENT_LIFE_TERMS)
    return "admissions" if admissions > student_life else "student_life"


def _matches_mode(chunk: SearchResult, mode: str) -> bool:
    chunk_mode = str(chunk.get("metadata", {}).get("mode", "")).casefold()
    # Older snapshots may not carry routing metadata.  Keep those results
    # rather than silently turning an otherwise answerable request into a refusal.
    return not chunk_mode or chunk_mode == mode


def _context(chunks: list[SearchResult]) -> str:
    parts: list[str] = []
    for index, chunk in enumerate(chunks, 1):
        meta = chunk["metadata"]
        provenance = [f"Title: {meta.get('title', 'Untitled')}", f"Source: {meta.get('source', '')}"]
        if meta.get("policy_version"):
            provenance.append(f"Policy Version: {meta['policy_version']}")
        if meta.get("effective_date"):
            provenance.append(f"Effective: {meta['effective_date']}")
        parts.append(f"[Source {index} | {' | '.join(provenance)}]\n{chunk['content']}")
    return "\n\n---\n\n".join(parts)


def _reorder(chunks: list[SearchResult]) -> list[SearchResult]:
    """Keep the best chunk at both a prominent and stable context position."""
    if len(chunks) < 3:
        return list(chunks)
    return list(chunks[::2]) + list(reversed(chunks[1::2]))


def _references(chunks: list[SearchResult], language: str) -> str:
    heading = "Nguồn tham khảo" if language == "vi" else "Sources"
    lines = [f"\n\n{heading}:"]
    for index, chunk in enumerate(chunks, 1):
        meta = chunk["metadata"]
        details = []
        if meta.get("policy_version"):
            details.append(f"Policy Version: {meta['policy_version']}")
        if meta.get("effective_date"):
            details.append(f"Effective: {meta['effective_date']}")
        suffix = f" ({'; '.join(details)})" if details else ""
        lines.append(f"[{index}] {meta.get('title', 'Untitled')} — {meta.get('url') or meta.get('source', '')}{suffix}")
    return "\n".join(lines)


def _cite(answer: str, source_count: int) -> str:
    """Make a provider response portable even when it omitted required cites."""
    body = answer.strip()
    if not body:
        return body
    # A citation anywhere in a sentence is sufficient for short generated answers;
    # split conservatively to avoid disrupting Vietnamese abbreviations.
    sentences = re.split(r"(?<=[.!?])\s+", body)
    cited = [sentence if re.search(r"\[\d+\]", sentence) else f"{sentence} [1]" for sentence in sentences if sentence]
    return " ".join(cited)


class DefaultCompassAssistant:
    def __init__(self, retrieval: RetrievalEngine, generation: GenerationPort | None = None, *, score_threshold: float = 0.3) -> None:
        self.retrieval = retrieval
        self.generation = generation or DeterministicGenerationAdapter()
        self.score_threshold = score_threshold

    def answer(self, request: ChatRequest) -> GenerationResult:
        language = _language(request)
        refusal = REFUSAL_VI if language == "vi" else REFUSAL_EN
        if not request.query.strip() or request.top_k <= 0 or PII_PATTERN.search(request.query):
            return {"answer": refusal, "sources": [], "retrieval_source": "none", "evidence_status": "not_found"}
        mode = _route(request.query) if request.mode == "auto" else request.mode
        try:
            retrieved = self.retrieval.retrieve(request.query, mode=mode, top_k=request.top_k)
        except Exception:
            return {"answer": refusal, "sources": [], "retrieval_source": "none", "evidence_status": "not_found"}
        chunks = _reorder([item for item in retrieved if _matches_mode(item, mode)])
        if not chunks:
            return {"answer": refusal, "sources": [], "retrieval_source": "none", "evidence_status": "not_found"}
        history = request.history[-4:]
        history_text = "\n".join(f"{message.role}: {message.content}" for message in history if not PII_PATTERN.search(message.content))
        system = (
            "You are VinUni Compass using GPT-5.6 Luna. Answer only from the supplied public sources. "
            "Preserve official policy names and defined English terms. Cite every material claim inline as [n]. "
            "Do not adjudicate personal records; do not request or repeat personal information. "
            f"Answer in {'Vietnamese' if language == 'vi' else 'English'}."
        )
        user = f"Mode: {mode}\nContext:\n{_context(chunks)}\n\nRecent session context (optional):\n{history_text}\n\nQuestion: {request.query}"
        try:
            generated = self.generation.complete(system, user)
        except Exception:
            return {"answer": refusal, "sources": chunks, "retrieval_source": self._source(chunks), "evidence_status": "partial_evidence"}
        answer = _cite(generated, len(chunks))
        if not answer:
            return {"answer": refusal, "sources": chunks, "retrieval_source": self._source(chunks), "evidence_status": "partial_evidence"}
        return {"answer": answer + _references(chunks, language), "sources": chunks, "retrieval_source": self._source(chunks), "evidence_status": "supported"}

    @staticmethod
    def _source(chunks: list[SearchResult]) -> str:
        return "pageindex" if chunks and chunks[0].get("retrieval_method") == "pageindex" else "hybrid"

    def stream(self, request: ChatRequest) -> Iterable[StreamEvent]:
        result = self.answer(request)
        yield StreamEvent(type="metadata", metadata={"evidence_status": result.get("evidence_status", "not_found")})
        yield StreamEvent(type="delta", data=result["answer"])
        yield StreamEvent(type="sources", metadata={"sources": result["sources"], "retrieval_source": result["retrieval_source"], "evidence_status": result.get("evidence_status", "not_found")})
        yield StreamEvent(type="done")
