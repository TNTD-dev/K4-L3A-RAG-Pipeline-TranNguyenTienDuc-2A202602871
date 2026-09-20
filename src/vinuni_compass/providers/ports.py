"""Ports justified by production and deterministic test adapters."""

from typing import Iterable, Protocol, Sequence

from src.contracts import SearchResult


class EmbeddingPort(Protocol):
    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class VectorStorePort(Protocol):
    def search(self, vector: Sequence[float], top_k: int) -> list[SearchResult]: ...


class VectorlessSearchPort(Protocol):
    def search(self, query: str, top_k: int) -> list[SearchResult]: ...


class GenerationPort(Protocol):
    def complete(self, system_prompt: str, user_message: str) -> str: ...

    def stream(self, system_prompt: str, user_message: str) -> Iterable[str]: ...
