"""HTTP layer for the VinUni Compass web client.

Owned by the Experience workstream. It consumes only the public assistant seam
(``CompassAssistant.stream``) and never imports another workstream's private
modules.

Built on Starlette + uvicorn, both of which ship with the existing dependency
set, so the UI adds no new package. This is deliberately *not*
``src/vinuni_compass/api/routes.py``: that module declares the shared
``/api/query`` and ``/v1/*`` transport owned by a different ticket, and nothing
here touches those paths.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, StreamingResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from .models import ChatMessage, ChatRequest, StreamEvent


ROOT = Path(__file__).resolve().parents[2]
WEB_DIR = ROOT / "web"
RESULTS_DIR = ROOT / "group_project" / "evaluation" / "results"

OFFICIAL_SOURCE_URL = "https://vinuni.edu.vn"

SAFE_FAILURE_MESSAGE = (
    "I could not reach the retrieval service just now, so I will not guess. "
    "Please try again in a moment, or check the official VinUni pages directly."
)

REFUSAL_MESSAGE = (
    "I cannot verify this from the public VinUni sources in the current Data "
    "Snapshot, so I will not answer. Please check with the official page or office."
)

#: The evidence states the client renders. Each one carries its own label and
#: icon in the UI, so meaning never depends on colour alone.
EVIDENCE_STATES = ("supported", "partial_evidence", "not_found")


# --------------------------------------------------------------------------
# Evidence state
# --------------------------------------------------------------------------

def evidence_status(
    sources: list[dict[str, Any]],
    retrieval_source: str | None,
    metadata: dict[str, Any] | None = None,
) -> str:
    """Resolve the evidence state shown to the reader.

    The assistant may publish ``evidence_status`` on a metadata or sources
    event. When it does not, derive a conservative state from the public result
    contract so the UI never overstates how well an answer is supported.
    """
    declared = (metadata or {}).get("evidence_status")
    if declared in EVIDENCE_STATES:
        return str(declared)
    if not sources or retrieval_source == "none":
        return "not_found"
    if retrieval_source == "pageindex" or len(sources) == 1:
        return "partial_evidence"
    return "supported"


# --------------------------------------------------------------------------
# Fake assistant
# --------------------------------------------------------------------------

class FakeCompassAssistant:
    """Deterministic stand-in used for UI development and smoke tests.

    Mirrors :class:`~.assistant.interface.CompassAssistant` without touching an
    index, a provider, or a network. Queries containing ``fail_on`` raise, so
    the error path can be exercised from the browser.
    """

    def __init__(self, *, fail_on: str = "trigger-provider-failure") -> None:
        self.fail_on = fail_on

    def _result(self, request: ChatRequest) -> dict[str, Any]:
        if "weather" in request.query.lower():
            return {"answer": REFUSAL_MESSAGE, "sources": [], "retrieval_source": "none"}
        mode = request.mode if request.mode != "auto" else "admissions"
        sources = [
            {
                "id": f"demo-chunk-{i}",
                "content": (
                    "Undergraduate applicants submit the online application, academic "
                    "transcripts, and an English proficiency certificate before the "
                    "published deadline for each admission round."
                ),
                "score": round(0.82 - 0.07 * i, 4),
                "metadata": {
                    "source": "undergraduate-student-handbook.md",
                    "title": f"Undergraduate Student Handbook — section {i + 1}",
                    "doc_type": "legal",
                    "url": OFFICIAL_SOURCE_URL,
                    "chunk_index": i,
                    "mode": mode,
                    "policy_version": "v8.1",
                    "effective_date": "2025-08-01",
                    "snapshot_id": "demo-snapshot",
                },
                "retrieval_method": "hybrid",
            }
            for i in range(min(request.top_k, 3))
        ]
        answer = (
            "Applicants submit the online application together with academic "
            "transcripts [1] and an English proficiency certificate [2] before the "
            "round deadline. This is a student project, so confirm the current "
            "requirements on the official admissions page."
        )
        return {"answer": answer, "sources": sources, "retrieval_source": "hybrid"}

    def answer(self, request: ChatRequest) -> dict[str, Any]:
        if self.fail_on in request.query:
            raise RuntimeError("simulated provider failure")
        return self._result(request)

    def stream(self, request: ChatRequest) -> Iterable[StreamEvent]:
        result = self.answer(request)
        status = "not_found" if result["retrieval_source"] == "none" else "supported"
        yield StreamEvent(type="metadata", metadata={"evidence_status": status, "mode": request.mode})
        for word in result["answer"].split(" "):
            yield StreamEvent(type="delta", data=word + " ")
        yield StreamEvent(
            type="sources",
            metadata={
                "sources": result["sources"],
                "retrieval_source": result["retrieval_source"],
                "evidence_status": status,
            },
        )
        yield StreamEvent(type="done")


_live_assistant: tuple[Any, str | None] | None = None


def get_assistant(demo: bool) -> tuple[Any, str | None]:
    """Return ``(assistant, warning)``.

    Falls back to :class:`FakeCompassAssistant` when the production graph cannot
    be composed, so a missing index or API key degrades the page rather than
    breaking it.
    """
    global _live_assistant
    if demo:
        return FakeCompassAssistant(), None
    if _live_assistant is None:
        try:
            from .bootstrap import build_assistant

            _live_assistant = (build_assistant(), None)
        except Exception as exc:  # pragma: no cover - depends on local setup
            _live_assistant = (
                FakeCompassAssistant(),
                f"Live assistant unavailable ({type(exc).__name__}); showing demo answers.",
            )
    return _live_assistant


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------

def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _build_request(body: dict[str, Any]) -> ChatRequest:
    history = tuple(
        ChatMessage(role=item["role"], content=str(item.get("content", "")))
        for item in body.get("history") or []
        if item.get("role") in {"user", "assistant"}
    )
    mode = body.get("mode") if body.get("mode") in {"auto", "admissions", "student_life"} else "auto"
    try:
        top_k = max(1, min(10, int(body.get("top_k", 5))))
    except (TypeError, ValueError):
        top_k = 5
    return ChatRequest(query=str(body.get("query", "")).strip(), mode=mode, history=history, top_k=top_k)


def _stream_events(assistant: Any, request: ChatRequest, warning: str | None) -> Iterator[str]:
    """Translate assistant events into SSE frames.

    Any provider or retrieval failure is converted into a terminal ``error``
    frame. The client keeps its existing thread and renders a safe message, so
    a failure never costs the conversation.
    """
    started = time.perf_counter()
    if warning:
        yield _sse({"type": "warning", "data": warning})

    text, sources, status = "", [], None
    try:
        for event in assistant.stream(request):
            if event.type == "metadata":
                status = event.metadata.get("evidence_status") or status
                yield _sse({"type": "metadata", "metadata": dict(event.metadata)})
            elif event.type == "delta":
                text += event.data
                yield _sse({"type": "delta", "data": event.data})
            elif event.type == "sources":
                sources = list(event.metadata.get("sources") or [])
                status = evidence_status(
                    sources, event.metadata.get("retrieval_source"), dict(event.metadata)
                )
                yield _sse({"type": "sources", "metadata": {"sources": sources, "evidence_status": status}})
            elif event.type == "error":
                yield _sse({"type": "error", "data": SAFE_FAILURE_MESSAGE})
                return
            elif event.type == "done":
                break
    except Exception:
        yield _sse({"type": "error", "data": SAFE_FAILURE_MESSAGE})
        return

    if not text.strip():
        yield _sse({"type": "error", "data": SAFE_FAILURE_MESSAGE})
        return

    yield _sse(
        {
            "type": "done",
            "metadata": {
                "evidence_status": status or evidence_status(sources, "hybrid" if sources else "none"),
                "latency_ms": round((time.perf_counter() - started) * 1000),
            },
        }
    )


async def chat(request: Request) -> StreamingResponse:
    body = await request.json()
    chat_request = _build_request(body)
    assistant, warning = get_assistant(bool(body.get("demo")))
    # Starlette runs a sync iterator in a worker thread, which keeps the
    # blocking assistant call off the event loop.
    return StreamingResponse(
        _stream_events(assistant, chat_request, warning),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


def _sample_evaluation() -> dict[str, Any]:
    """Clearly-labelled placeholder so Explore is reviewable before a real run."""
    metrics = (
        "faithfulness",
        "answer_relevance",
        "context_recall",
        "context_precision",
        "recall_at_5",
        "citation_correctness",
    )
    configs = []
    for name, label, base in (
        ("dense", "Config A — dense only", 0.72),
        ("hybrid_rrf", "Config B — hybrid + RRF", 0.83),
    ):
        cases = []
        for i in range(12):
            drift = ((i * 7) % 5) / 25
            cases.append(
                {
                    "id": f"G{i + 1:02d}",
                    "question": f"Sample question {i + 1}",
                    "category": ["admissions", "student_life", "keyword", "out_of_scope"][i % 4],
                    "language": "vi" if i % 2 else "en",
                    "mode": ["admissions", "student_life", "auto"][i % 3],
                    "expected_refusal": i % 4 == 3,
                    "refused": i % 4 == 3,
                    "faithfulness": round(min(1.0, base + drift), 3),
                    "answer_relevance": round(min(1.0, base + drift - 0.04), 3),
                    "context_recall": round(min(1.0, base + drift + 0.03), 3),
                    "context_precision": round(min(1.0, base + drift - 0.07), 3),
                    "recall_at_5": 1.0 if drift > 0.05 else 0.0,
                    "citation_correctness": round(min(1.0, base + drift), 3),
                    "latency_ms": 900 + i * 40 + (200 if name == "hybrid_rrf" else 0),
                    "failure_stage": "retrieval" if drift == 0 else None,
                    "root_cause": "Query terms absent from the chunk" if drift == 0 else None,
                }
            )
        aggregate = {key: round(sum(c[key] for c in cases) / len(cases), 3) for key in metrics}
        aggregate["refusal_accuracy"] = round(
            sum(c["refused"] == c["expected_refusal"] for c in cases) / len(cases), 3
        )
        latencies = sorted(c["latency_ms"] for c in cases)
        aggregate["latency_p50_ms"] = latencies[len(latencies) // 2]
        aggregate["latency_p95_ms"] = latencies[int(len(latencies) * 0.95) - 1]
        configs.append({"name": name, "label": label, "aggregate": aggregate, "cases": cases})

    return {
        "sample": True,
        "run": {
            "timestamp": "sample",
            "generator": "sample-generator",
            "evaluator": "sample-evaluator",
            "embedding_model": "sample-embeddings",
            "data_snapshot": "sample-snapshot",
            "top_k": 5,
            "dataset_size": 12,
        },
        "configs": configs,
    }


async def evaluation(request: Request) -> JSONResponse:
    """Serve the newest harness run, or a labelled sample when none exists."""
    runs = sorted(RESULTS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True) \
        if RESULTS_DIR.is_dir() else []
    if not runs or request.query_params.get("sample") == "1":
        return JSONResponse(_sample_evaluation())
    payload = json.loads(runs[0].read_text(encoding="utf-8"))
    payload["sample"] = False
    payload["source_file"] = runs[0].name
    payload["available_runs"] = [p.name for p in runs]
    return JSONResponse(payload)


async def index(request: Request) -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


app = Starlette(
    routes=[
        Route("/", index),
        Route("/api/chat", chat, methods=["POST"]),
        Route("/api/evaluation", evaluation),
        Mount("/static", StaticFiles(directory=WEB_DIR), name="static"),
    ]
)
