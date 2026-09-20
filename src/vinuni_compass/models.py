"""Small product-level types shared across public module interfaces."""

from dataclasses import dataclass, field
from typing import Literal, Mapping


Mode = Literal["auto", "admissions", "student_life"]
EvidenceStatus = Literal["supported", "partial_evidence", "not_found"]
StreamEventType = Literal["metadata", "delta", "sources", "error", "done"]


@dataclass(frozen=True)
class ChatMessage:
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True)
class ChatRequest:
    """A UI-independent request to VinUni Compass."""

    query: str
    mode: Mode = "auto"
    history: tuple[ChatMessage, ...] = ()
    top_k: int = 5


@dataclass(frozen=True)
class StreamEvent:
    """Portable event consumed by HTTP and in-process UI adapters."""

    type: StreamEventType
    data: str = ""
    metadata: Mapping[str, object] = field(default_factory=dict)
