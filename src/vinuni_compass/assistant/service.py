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
    return chunk_mode == mode


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
    if not body or source_count <= 0:
        return ""
    citations = [int(value) for value in re.findall(r"\[(\d+)\]", body)]
    if any(value < 1 or value > source_count for value in citations):
        return ""
    # A citation anywhere in a sentence is sufficient for short generated answers;
    # split conservatively to avoid disrupting Vietnamese abbreviations.
    sentences = re.split(r"(?<=[.!?])\s+", body)
    cited = [sentence if re.search(r"\[\d+\]", sentence) else f"{sentence} [1]" for sentence in sentences if sentence]
    return " ".join(cited)


def _has_conflicting_versions(chunks: list[SearchResult]) -> bool:
    versions_by_title: dict[str, set[tuple[str, str]]] = {}
    for chunk in chunks:
        metadata = chunk["metadata"]
        title = str(metadata.get("title", "")).casefold()
        version = str(metadata.get("policy_version") or "")
        effective = str(metadata.get("effective_date") or "")
        if version or effective:
            versions_by_title.setdefault(title, set()).add((version, effective))
    return any(len(versions) > 1 for versions in versions_by_title.values())


def _supports_requested_year(query: str, chunks: list[SearchResult]) -> bool:
    years = set(re.findall(r"\b20\d{2}\b", query))
    if not years:
        return True
    evidence = " ".join(
        f"{chunk['content']} {chunk['metadata'].get('policy_version', '')} "
        f"{chunk['metadata'].get('effective_date', '')}"
        for chunk in chunks
    )
    return bool(years.intersection(re.findall(r"\b20\d{2}\b", evidence)))


class DefaultCompassAssistant:
    def __init__(self, retrieval: RetrievalEngine, generation: GenerationPort | None = None) -> None:
        self.retrieval = retrieval
        self.generation = generation or DeterministicGenerationAdapter()

    @staticmethod
    def _result(answer: str, chunks: list[SearchResult], status: str) -> GenerationResult:
        source = DefaultCompassAssistant._source(chunks) if chunks else "none"
        return {"answer": answer, "sources": chunks, "retrieval_source": source, "evidence_status": status}

    def _prepare(self, request: ChatRequest) -> tuple[str, str, list[SearchResult], str, str, str]:
        language = _language(request)
        refusal = REFUSAL_VI if language == "vi" else REFUSAL_EN
        mode = _route(request.query) if request.mode == "auto" else request.mode
        if not request.query.strip() or request.top_k <= 0 or PII_PATTERN.search(request.query):
            return language, refusal, [], mode, "", ""
        retrieved = self.retrieval.retrieve(request.query, mode=mode, top_k=request.top_k)
        chunks = [item for item in retrieved if _matches_mode(item, mode)]
        if not chunks or not _supports_requested_year(request.query, chunks):
            return language, refusal, [], mode, "", ""
        history = request.history[-4:]
        history_text = "\n".join(
            f"{message.role}: {message.content}"
            for message in history
            if not PII_PATTERN.search(message.content)
        )
        conflict_instruction = (
            "The sources contain conflicting policy versions. Explicitly qualify the answer and describe the conflict. "
            if _has_conflicting_versions(chunks)
            else ""
        )
        system = (
            "You are VinUni Compass using GPT-5.6 Luna. Answer only from the supplied public sources. "
            f"Preserve official policy names and defined English terms. Cite every material claim inline as [n], where n is between 1 and {len(chunks)}. "
            "Do not adjudicate personal records; do not request or repeat personal information. "
            f"{conflict_instruction}Answer in {'Vietnamese' if language == 'vi' else 'English'}."
        )
        user = (
            f"Mode: {mode}\nContext:\n{_context(chunks)}\n\n"
            f"Recent session context (optional):\n{history_text}\n\nQuestion: {request.query}"
        )
        status = "partial_evidence" if _has_conflicting_versions(chunks) else "supported"
        return language, refusal, chunks, mode, system, user + f"\n\nEvidence status: {status}"

    def answer(self, request: ChatRequest) -> GenerationResult:
        try:
            language, refusal, chunks, _, system, user = self._prepare(request)
        except Exception:
            language = _language(request)
            refusal = REFUSAL_VI if language == "vi" else REFUSAL_EN
            return self._result(refusal, [], "not_found")
        if not chunks:
            return self._result(refusal, [], "not_found")
        try:
            generated = self.generation.complete(system, user)
        except Exception:
            return self._result(refusal, chunks, "partial_evidence")
        answer = _cite(generated, len(chunks))
        if not answer:
            return self._result(refusal, chunks, "partial_evidence")
        status = "partial_evidence" if _has_conflicting_versions(chunks) else "supported"
        return self._result(answer + _references(chunks, language), chunks, status)

    @staticmethod
    def _source(chunks: list[SearchResult]) -> str:
        return "pageindex" if chunks and chunks[0].get("retrieval_method") == "pageindex" else "hybrid"

    def stream(self, request: ChatRequest) -> Iterable[StreamEvent]:
        try:
            language, refusal, chunks, _, system, user = self._prepare(request)
        except Exception:
            yield StreamEvent(type="error", data="Unable to retrieve public evidence.")
            yield StreamEvent(type="done")
            return
        if not chunks:
            yield StreamEvent(type="metadata", metadata={"evidence_status": "not_found"})
            yield StreamEvent(type="delta", data=refusal)
            yield StreamEvent(type="sources", metadata={"sources": [], "retrieval_source": "none", "evidence_status": "not_found"})
            yield StreamEvent(type="done")
            return
        status = "partial_evidence" if _has_conflicting_versions(chunks) else "supported"
        yield StreamEvent(type="metadata", metadata={"evidence_status": status})
        generated = ""
        try:
            for delta in self.generation.stream(system, user):
                if delta:
                    generated += delta
                    yield StreamEvent(type="delta", data=delta)
        except Exception:
            yield StreamEvent(type="error", data="The answer provider is temporarily unavailable.")
            yield StreamEvent(type="done")
            return
        citation_indices = [int(value) for value in re.findall(r"\[\s*(\d+)\s*\]", generated)]
        if any(index < 1 or index > len(chunks) for index in citation_indices):
            yield StreamEvent(type="error", data="The generated citations could not be verified.")
            yield StreamEvent(type="done")
            return
        if not citation_indices:
            yield StreamEvent(type="delta", data=" [1]")
        references = _references(chunks, language)
        yield StreamEvent(type="delta", data=references)
        yield StreamEvent(type="sources", metadata={"sources": chunks, "retrieval_source": self._source(chunks), "evidence_status": status})
        yield StreamEvent(type="done")
