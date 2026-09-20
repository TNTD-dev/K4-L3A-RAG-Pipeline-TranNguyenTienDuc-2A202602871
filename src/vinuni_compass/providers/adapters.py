"""Deterministic test adapters and small production-facing provider shims.

The adapters are intentionally dependency-light.  They let all contract and
acceptance tests run without a network connection or API key while keeping
the provider ports used by the production composition root explicit.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Iterable, Sequence

from src.contracts import SearchResult


class OpenAIEmbeddingAdapter:
    """Lazy OpenAI adapter; construction performs no network request."""

    def __init__(self, api_key: str, model: str = "text-embedding-3-small", dimension: int = 1536) -> None:
        if not api_key.strip():
            raise ValueError("api_key is required for OpenAI embeddings")
        self.api_key, self.model, self.dimension = api_key, model, dimension

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        from openai import OpenAI
        client = OpenAI(api_key=self.api_key)
        vectors: list[list[float]] = []
        batch_size = 100
        for i in range(0, len(texts), batch_size):
            batch = list(texts[i : i + batch_size])
            response = client.embeddings.create(model=self.model, input=batch)
            batch_vectors = [list(map(float, item.embedding)) for item in sorted(response.data, key=lambda item: item.index)]
            vectors.extend(batch_vectors)
        if any(len(vector) != self.dimension for vector in vectors):
            raise ValueError("OpenAI embedding dimension does not match collection invariant")
        return vectors


class OpenAIGenerationAdapter:
    """Lazy OpenAI chat adapter implementing the generation port."""

    def __init__(self, api_key: str, model: str = "gpt-5.6-luna", temperature: float = 0.3) -> None:
        if not api_key.strip():
            raise ValueError("api_key is required for OpenAI generation")
        self.api_key, self.model, self.temperature = api_key, model, temperature

    def complete(self, system_prompt: str, user_message: str) -> str:
        from openai import OpenAI
        request = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        }
        if not self.model.startswith("gpt-5.6"):
            request["temperature"] = self.temperature
        response = OpenAI(api_key=self.api_key).chat.completions.create(**request)
        return response.choices[0].message.content or ""

    def stream(self, system_prompt: str, user_message: str) -> Iterable[str]:
        from openai import OpenAI
        request = {
            "model": self.model,
            "stream": True,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        }
        if not self.model.startswith("gpt-5.6"):
            request["temperature"] = self.temperature
        response = OpenAI(api_key=self.api_key).chat.completions.create(**request)
        for event in response:
            delta = event.choices[0].delta.content if event.choices else None
            if delta:
                yield delta


class DeterministicEmbeddingAdapter:
    """Stable hashed-token embeddings suitable for offline tests.

    This is not presented as a quality replacement for OpenAI embeddings; it
    is a deterministic seam with the same shape and ordering guarantees.
    """

    def __init__(self, dimension: int = 1536) -> None:
        if dimension <= 0:
            raise ValueError("dimension must be positive")
        self.dimension = dimension

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            vector = [0.0] * self.dimension
            tokens = re.findall(r"[\wÀ-ỹ]+", text.casefold())
            for token in tokens:
                digest = hashlib.sha256(token.encode("utf-8")).digest()
                index = int.from_bytes(digest[:4], "big") % self.dimension
                sign = 1.0 if digest[4] & 1 else -1.0
                vector[index] += sign
            norm = math.sqrt(sum(value * value for value in vector))
            vectors.append([value / norm for value in vector] if norm else vector)
        return vectors


class DeterministicVectorStoreAdapter:
    """In-memory cosine store with idempotent upsert semantics."""

    def __init__(self) -> None:
        self._items: dict[str, tuple[str, list[float], dict]] = {}
        self.dimension: int | None = None

    def upsert(
        self,
        ids: Sequence[str],
        documents: Sequence[str],
        embeddings: Sequence[Sequence[float]],
        metadatas: Sequence[dict],
    ) -> None:
        if not (len(ids) == len(documents) == len(embeddings) == len(metadatas)):
            raise ValueError("vector store inputs must have equal lengths")
        for item_id, content, vector, metadata in zip(ids, documents, embeddings, metadatas):
            values = [float(value) for value in vector]
            if self.dimension is None:
                self.dimension = len(values)
            if len(values) != self.dimension:
                raise ValueError("embedding dimension does not match collection invariant")
            self._items[item_id] = (content, values, dict(metadata))

    def search(self, vector: Sequence[float], top_k: int) -> list[SearchResult]:
        if top_k <= 0 or not self._items:
            return []
        query = [float(value) for value in vector]
        if self.dimension is not None and len(query) != self.dimension:
            raise ValueError("query dimension does not match collection invariant")
        qnorm = math.sqrt(sum(value * value for value in query))
        scored: list[SearchResult] = []
        for item_id, (content, embedding, metadata) in self._items.items():
            denom = qnorm * math.sqrt(sum(value * value for value in embedding))
            score = sum(a * b for a, b in zip(query, embedding)) / denom if denom else 0.0
            scored.append({
                "id": item_id,
                "content": content,
                "score": float(score),
                "metadata": metadata,
                "retrieval_method": "dense",
            })
        return sorted(scored, key=lambda item: (-item["score"], item["id"]))[:top_k]


class ChromaVectorStoreAdapter:
    """Read the canonical Task 4 Chroma collection through the product port."""

    def __init__(self, collection=None) -> None:
        if collection is None:
            from src.task4_chunking_indexing import get_collection
            collection = get_collection()
        self.collection = collection

    def search(self, vector: Sequence[float], top_k: int) -> list[SearchResult]:
        if top_k <= 0:
            return []
        response = self.collection.query(
            query_embeddings=[list(vector)],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )
        ids = (response.get("ids") or [[]])[0]
        documents = (response.get("documents") or [[]])[0]
        metadatas = (response.get("metadatas") or [[]])[0]
        distances = (response.get("distances") or [[]])[0]
        rows: list[SearchResult] = []
        for item_id, document, metadata, distance in zip(ids, documents, metadatas, distances):
            rows.append({
                "id": str(item_id),
                "content": str(document or ""),
                "score": max(0.0, 1.0 - float(distance)),
                "metadata": metadata or {},
                "retrieval_method": "dense",
            })
        return sorted(rows, key=lambda item: (-item["score"], item["id"]))


class TaskPageIndexAdapter:
    """Adapter for the optional course PageIndex boundary."""

    def search(self, query: str, top_k: int) -> list[SearchResult]:
        from src.task8_pageindex_vectorless import pageindex_search
        return pageindex_search(query, top_k=top_k)


class DeterministicPageIndexAdapter:
    """Offline PageIndex stand-in; callers can seed results for tests."""

    def __init__(self, results: Iterable[SearchResult] = ()) -> None:
        self.results = list(results)

    def search(self, query: str, top_k: int) -> list[SearchResult]:
        del query
        return [dict(item, retrieval_method="pageindex") for item in self.results[:max(top_k, 0)]]


class DeterministicGenerationAdapter:
    """Predictable citation-aware generation for local tests and demos."""

    def complete(self, system_prompt: str, user_message: str) -> str:
        del system_prompt
        question = user_message.rsplit("Question:", 1)[-1].strip()
        return f"Dựa trên các nguồn được cung cấp, câu hỏi của bạn là: {question}. [1]"

    def stream(self, system_prompt: str, user_message: str) -> Iterable[str]:
        answer = self.complete(system_prompt, user_message)
        yield from answer.split(" ")


class JinaRerankerAdapter:
    """Reranker using Jina AI API."""

    def __init__(self, api_key: str, model: str = "jina-reranker-v2-base-multilingual") -> None:
        if not api_key.strip():
            raise ValueError("api_key is required for Jina reranker")
        self.api_key, self.model = api_key, model

    def rerank(self, query: str, documents: list[str]) -> list[float]:
        if not documents:
            return []
        import urllib.request
        import urllib.error
        import json

        url = "https://api.jina.ai/v1/rerank"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        data = {
            "model": self.model,
            "query": query,
            "documents": documents
        }
        req = urllib.request.Request(url, data=json.dumps(data).encode("utf-8"), headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
                # Jina returns a list of results in "results" array, each has "index" and "relevance_score"
                # Sort by index to match original document order
                results = sorted(payload.get("results", []), key=lambda x: x["index"])
                return [r.get("relevance_score", 0.0) for r in results]
        except urllib.error.URLError:
            raise RuntimeError("Jina reranker provider unavailable")
