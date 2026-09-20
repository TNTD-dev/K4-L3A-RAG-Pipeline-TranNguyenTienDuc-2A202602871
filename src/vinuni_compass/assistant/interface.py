"""The main application seam."""

from typing import Iterable, Protocol

from src.contracts import GenerationResult

from ..models import ChatRequest, StreamEvent


class CompassAssistant(Protocol):
    """Answer and stream without exposing retrieval or provider details."""

    def answer(self, request: ChatRequest) -> GenerationResult: ...

    def stream(self, request: ChatRequest) -> Iterable[StreamEvent]: ...
