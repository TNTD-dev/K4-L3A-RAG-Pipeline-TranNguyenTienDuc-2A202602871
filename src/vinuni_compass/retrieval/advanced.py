"""Advanced retrieval engine with Luna, Jina, RRF, and PageIndex fallback."""

from typing import Iterable, Protocol
from src.contracts import SearchResult
from ..models import Mode


class VectorStore(Protocol):
    def search(self, vector: list[float], top_k: int) -> list[SearchResult]: ...

class PageIndex(Protocol):
    def search(self, query: str, top_k: int) -> list[SearchResult]: ...

class GenerationAdapter(Protocol):
    def complete(self, system_prompt: str, user_message: str) -> str: ...

class EmbeddingAdapter(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...

class RerankerAdapter(Protocol):
    def rerank(self, query: str, documents: list[str]) -> list[float]: ...


class AdvancedRetrievalEngine:
    def __init__(
        self,
        *,
        vector_store: VectorStore,
        embedding_adapter: EmbeddingAdapter,
        bm25_index: object,  # e.g. BM25Plus instance or anything with get_scores
        corpus: list[dict],  # list of chunk dicts corresponding to bm25_index
        page_index: PageIndex,
        generation_adapter: GenerationAdapter | None = None,
        reranker_adapter: RerankerAdapter | None = None,
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
        self.use_luna_expansion = use_luna_expansion
        self.use_jina_reranking = use_jina_reranking
        self.score_threshold = score_threshold

    def _expand_query(self, query: str) -> str:
        if not self.use_luna_expansion or not self.generation_adapter:
            return query
        system_prompt = (
            "You are a query expansion assistant. "
            "Expand the following query with synonyms and related terms "
            "while preserving the original intent. Return ONLY the expanded query."
        )
        try:
            expanded = self.generation_adapter.complete(system_prompt, f"Query: {query}")
            return expanded.strip() or query
        except Exception:
            return query

    def _filter_mode(self, results: list[SearchResult], mode: Mode, top_k: int) -> list[SearchResult]:
        if mode == "auto":
            return results[:top_k]
        filtered: list[SearchResult] = []
        for res in results:
            item_mode = res.get("metadata", {}).get("mode", "auto")
            if item_mode == mode or item_mode == "auto" or item_mode is None:
                filtered.append(res)
            if len(filtered) >= top_k:
                break
        return filtered

    def _dense_search(self, query: str, mode: Mode, top_k: int) -> list[SearchResult]:
        try:
            vector = self.embedding_adapter.embed([query])[0]
            fetch_k = top_k * 5 if mode != "auto" else top_k
            results = self.vector_store.search(vector, fetch_k)
            return self._filter_mode(results, mode, top_k)
        except Exception:
            return []

    def _bm25_search(self, query: str, mode: Mode, top_k: int) -> list[SearchResult]:
        import re
        tokens = [t.casefold() for t in re.findall(r"[\wÀ-ỹ]+", query)]
        if not tokens or not self.corpus:
            return []
        
        scores = self.bm25_index.get_scores(tokens)
        scored_indices = sorted(range(len(self.corpus)), key=lambda i: (-scores[i], self.corpus[i].get("id", "")))
        
        results: list[SearchResult] = []
        seen = set()
        for idx in scored_indices:
            if scores[idx] <= 0:
                continue
            item = self.corpus[idx]
            item_id = item["id"]
            if item_id in seen:
                continue
            item_mode = item.get("metadata", {}).get("mode", "auto")
            if mode != "auto" and item_mode != mode and item_mode != "auto" and item_mode is not None:
                continue
            seen.add(item_id)
            results.append({
                "id": item_id,
                "content": item["content"],
                "score": float(scores[idx]),
                "metadata": item["metadata"],
                "retrieval_method": "bm25"
            })
            if len(results) >= top_k:
                break
        return results

    def _rrf_fuse(self, lists: list[list[SearchResult]], top_k: int, k: int = 60) -> list[SearchResult]:
        scores: dict[str, float] = {}
        items: dict[str, SearchResult] = {}
        for ranked_list in lists:
            seen_in_list = set()
            rank = 0
            for item in ranked_list:
                item_id = item["id"]
                if not item_id or item_id in seen_in_list:
                    continue
                seen_in_list.add(item_id)
                rank += 1
                scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank)
                items.setdefault(item_id, item)
        
        ranked_ids = sorted(scores.keys(), key=lambda x: (-scores[x], x))[:top_k]
        return [
            {**items[item_id], "score": scores[item_id], "retrieval_method": "hybrid"}  # type: ignore
            for item_id in ranked_ids
        ]

    def _jina_rerank(self, query: str, results: list[SearchResult]) -> list[SearchResult]:
        if not results:
            return []
        docs = [res["content"] for res in results]
        scores = self.reranker_adapter.rerank(query, docs)  # type: ignore
        for res, score in zip(results, scores):
            res["score"] = score
            res["retrieval_method"] = "hybrid"
        return sorted(results, key=lambda x: (-x["score"], x["id"]))

    def retrieve(self, query: str, *, mode: Mode = "auto", top_k: int = 5) -> list[SearchResult]:
        expanded_query = self._expand_query(query)
        
        dense_results = self._dense_search(expanded_query, mode, top_k)
        bm25_results = self._bm25_search(expanded_query, mode, top_k)
        
        best_dense_score = dense_results[0]["score"] if dense_results else 0.0
        
        fused = self._rrf_fuse([dense_results, bm25_results], top_k=top_k)
        
        if self.use_jina_reranking and self.reranker_adapter:
            try:
                fused = self._jina_rerank(expanded_query, fused)
            except Exception:
                pass

        if best_dense_score < self.score_threshold:
            try:
                pageindex_results = self.page_index.search(expanded_query, top_k)
                if pageindex_results:
                    return pageindex_results
            except Exception:
                pass
                
        return fused
