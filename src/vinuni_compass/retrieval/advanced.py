"""Production hybrid retrieval with resilient optional providers.

The engine is deliberately the single retrieval seam used by the application.
Dense and BM25 providers may fail independently; in that case the remaining
results are still useful and the optional PageIndex/Jina providers never make
the caller crash.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

from src.contracts import SearchResult
from src.task6_lexical_search import _tokens
from src.task7_reranking import rerank_rrf

from ..models import Mode
from ..providers.ports import (
    EmbeddingPort,
    GenerationPort,
    RerankerPort,
    VectorStorePort,
    VectorlessSearchPort,
)


class AdvancedRetrievalEngine:
    """Coordinate dense, lexical, RRF, reranking, and vectorless fallback."""

    def __init__(
        self,
        *,
        vector_store: VectorStorePort,
        embedding_adapter: EmbeddingPort,
        bm25_index: Any,
        corpus: list[dict],
        page_index: VectorlessSearchPort,
        generation_adapter: GenerationPort | None = None,
        reranker_adapter: RerankerPort | None = None,
        use_hybrid: bool = True,
        use_pageindex_fallback: bool = True,
        use_luna_expansion: bool = False,
        use_jina_reranking: bool = False,
        score_threshold: float = 0.3,
    ) -> None:
        self.vector_store = vector_store
        self.embedding_adapter = embedding_adapter
        self.bm25_index = bm25_index
        self.corpus = corpus
        self.page_index = page_index
        self.generation_adapter = generation_adapter
        self.reranker_adapter = reranker_adapter
        self.use_hybrid = use_hybrid
        self.use_pageindex_fallback = use_pageindex_fallback
        self.use_luna_expansion = use_luna_expansion
        self.use_jina_reranking = use_jina_reranking
        self.score_threshold = score_threshold

    @staticmethod
    def _top_k(top_k: int) -> int:
        return max(int(top_k), 0)

    @staticmethod
    def _normalize_result(item: object, method: str) -> SearchResult | None:
        """Convert provider output to the shared contract or drop bad rows."""
        if not isinstance(item, dict):
            return None
        item_id = item.get("id")
        content = item.get("content", item.get("document", ""))
        raw_score = item.get("score", 0.0)
        metadata = item.get("metadata")
        if not isinstance(item_id, str) or not item_id.strip():
            return None
        if not isinstance(content, str) or not content.strip():
            return None
        if not isinstance(metadata, dict):
            metadata = {}
        if isinstance(raw_score, bool):
            return None
        try:
            score = float(raw_score)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(score):
            return None
        url = metadata.get("url")
        if url is not None and not isinstance(url, str):
            url = None
        chunk_index = metadata.get("chunk_index", 0)
        if isinstance(chunk_index, bool) or not isinstance(chunk_index, int) or chunk_index < 0:
            chunk_index = 0
        normalized_metadata: dict[str, object] = {
            "source": str(metadata.get("source") or item_id),
            "title": str(metadata.get("title") or item_id),
            "doc_type": str(metadata.get("doc_type") or "unknown"),
            "url": url,
            "chunk_index": chunk_index,
        }
        for key in (
            "mode",
            "classification",
            "policy_version",
            "effective_date",
            "crawl_timestamp",
        ):
            if key in metadata:
                normalized_metadata[key] = metadata[key]
        return {
            "id": item_id,
            "content": content,
            "score": score,
            "metadata": normalized_metadata,  # type: ignore[typeddict-item]
            "retrieval_method": method,  # type: ignore[typeddict-item]
        }

    @classmethod
    def _filter_and_sort(
        cls,
        results: Sequence[object],
        mode: Mode,
        top_k: int,
        method: str,
    ) -> list[SearchResult]:
        normalized: list[SearchResult] = []
        for item in results:
            result = cls._normalize_result(item, method)
            if result is None:
                continue
            item_mode = result["metadata"].get("mode")
            if mode != "auto" and item_mode not in (None, "auto", mode):
                continue
            normalized.append(result)
        normalized.sort(key=lambda row: (-row["score"], row["id"]))
        deduplicated: list[SearchResult] = []
        seen: set[str] = set()
        for result in normalized:
            if result["id"] in seen:
                continue
            seen.add(result["id"])
            deduplicated.append(result)
            if len(deduplicated) >= top_k:
                break
        return deduplicated

    def _expand_query(self, query: str) -> str:
        if not self.use_luna_expansion or self.generation_adapter is None:
            return query
        prompt = (
            "Expand the query with useful synonyms and related terms while "
            "preserving its intent. Return only the expanded query."
        )
        try:
            expanded = self.generation_adapter.complete(prompt, f"Query: {query}")
            return expanded.strip() or query
        except Exception:
            return query

    def _dense_search(self, query: str, mode: Mode, top_k: int) -> list[SearchResult]:
        if top_k <= 0:
            return []
        try:
            vectors = self.embedding_adapter.embed([query])
            if not vectors:
                return []
            raw = self.vector_store.search(vectors[0], max(top_k * 5, top_k))
            return self._filter_and_sort(raw, mode, top_k, "dense")
        except Exception:
            return []

    def _bm25_search(self, query: str, mode: Mode, top_k: int) -> list[SearchResult]:
        if top_k <= 0 or not query.strip() or not self.corpus:
            return []
        try:
            tokens = _tokens(query)
            if not tokens:
                return []
            scores = list(self.bm25_index.get_scores(tokens))
            if len(scores) != len(self.corpus):
                return []
            raw = []
            for item, score in zip(self.corpus, scores):
                if float(score) <= 0:
                    continue
                raw.append({**item, "score": float(score)})
            return self._filter_and_sort(raw, mode, top_k, "bm25")
        except Exception:
            return []

    @staticmethod
    def _rrf_fuse(
        lists: list[list[SearchResult]], top_k: int, k: int = 60
    ) -> list[SearchResult]:
        # Reuse the canonical task-7 implementation; this wrapper keeps the
        # product seam easy to spy on in tests and guarantees one fusion call.
        return rerank_rrf(lists, top_k=top_k, k=k)  # type: ignore[return-value]

    def _jina_rerank(
        self, query: str, results: list[SearchResult], top_k: int
    ) -> list[SearchResult]:
        if not results or self.reranker_adapter is None:
            return results[:top_k]
        scores = list(self.reranker_adapter.rerank(query, [r["content"] for r in results]))
        if len(scores) != len(results):
            raise ValueError("reranker returned the wrong number of scores")
        if any(isinstance(score, bool) or not math.isfinite(float(score)) for score in scores):
            raise ValueError("reranker returned an invalid score")
        reranked = [{**result, "score": float(score)} for result, score in zip(results, scores)]
        return self._filter_and_sort(reranked, "auto", top_k, "hybrid")

    def _pageindex_fallback(
        self, query: str, mode: Mode, top_k: int
    ) -> list[SearchResult]:
        try:
            raw = self.page_index.search(query, top_k)
        except Exception:
            return []
        return self._filter_and_sort(raw, mode, top_k, "pageindex")

    def retrieve(self, query: str, *, mode: Mode = "auto", top_k: int = 5) -> list[SearchResult]:
        top_k = self._top_k(top_k)
        if top_k <= 0 or not query.strip():
            return []
        expanded_query = self._expand_query(query)
        dense_results = self._dense_search(expanded_query, mode, top_k)
        bm25_results = self._bm25_search(expanded_query, mode, top_k)
        # Never rely on provider ordering: threshold uses the original dense
        # cosine score, not an RRF or reranker score.
        best_dense_score = max((result["score"] for result in dense_results), default=0.0)

        if self.use_hybrid:
            candidates = self._rrf_fuse([dense_results, bm25_results], top_k=top_k)
        else:
            candidates = dense_results[:top_k]

        if self.use_jina_reranking and self.reranker_adapter is not None and candidates:
            try:
                candidates = self._jina_rerank(expanded_query, candidates, top_k)
            except Exception:
                candidates = candidates[:top_k]

        if self.use_pageindex_fallback and best_dense_score < self.score_threshold:
            fallback = self._pageindex_fallback(expanded_query, mode, top_k)
            if fallback:
                return fallback
        return candidates[:top_k]
