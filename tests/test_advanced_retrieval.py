import pytest
from src.vinuni_compass.retrieval.advanced import AdvancedRetrievalEngine
from src.vinuni_compass.providers.adapters import (
    DeterministicEmbeddingAdapter,
    DeterministicVectorStoreAdapter,
    DeterministicPageIndexAdapter,
    DeterministicGenerationAdapter,
)

class FakeBM25:
    def __init__(self, scores):
        self._scores = scores
    def get_scores(self, tokens):
        return self._scores

class FakeReranker:
    def __init__(self, scores=None, should_fail=False):
        self._scores = scores
        self._should_fail = should_fail
        
    def rerank(self, query, docs):
        if self._should_fail:
            raise RuntimeError("Provider failed")
        return self._scores or [1.0] * len(docs)

def metadata(mode="auto", source_id="1"):
    return {"mode": mode, "source": "test.md", "title": "Test", "doc_type": "legal"}

@pytest.fixture
def base_engine():
    vector_store = DeterministicVectorStoreAdapter()
    embedder = DeterministicEmbeddingAdapter(dimension=4)
    # 2 documents for testing
    vector_store.upsert(
        ids=["doc1", "doc2"],
        documents=["Admissions details", "Student life details"],
        embeddings=[[1,0,0,0], [0,1,0,0]],
        metadatas=[metadata("admissions", "doc1"), metadata("student_life", "doc2")]
    )
    
    corpus = [
        {"id": "doc1", "content": "Admissions details", "metadata": metadata("admissions", "doc1")},
        {"id": "doc2", "content": "Student life details", "metadata": metadata("student_life", "doc2")}
    ]
    bm25 = FakeBM25(scores=[1.5, 0.5])
    
    page_index = DeterministicPageIndexAdapter([
        {"id": "doc3", "content": "Fallback page", "score": 1.0, "metadata": metadata("auto", "doc3"), "retrieval_method": "pageindex"}
    ])
    
    return AdvancedRetrievalEngine(
        vector_store=vector_store,
        embedding_adapter=embedder,
        bm25_index=bm25,
        corpus=corpus,
        page_index=page_index,
        score_threshold=0.5
    )

def test_mode_filtering_admissions(base_engine):
    base_engine.score_threshold = -1.0
    # Query matching doc1 more closely
    results = base_engine.retrieve("Admissions", mode="admissions", top_k=5)
    assert len(results) == 1
    assert results[0]["id"] == "doc1"

def test_mode_filtering_student_life(base_engine):
    base_engine.score_threshold = -1.0
    # Query matching doc1 more closely but filtered to student_life
    results = base_engine.retrieve("Admissions", mode="student_life", top_k=5)
    # doc2 will match BM25 slightly, let's see. Wait, BM25 returns 1.5 and 0.5
    assert len(results) == 1
    assert results[0]["id"] == "doc2"

def test_page_index_fallback(base_engine):
    base_engine.score_threshold = 2.0  # Force fallback
    results = base_engine.retrieve("Query", top_k=5)
    assert len(results) == 1
    assert results[0]["id"] == "doc3"
    assert results[0]["retrieval_method"] == "pageindex"

def test_jina_reranker_fallback_to_rrf(base_engine):
    base_engine.score_threshold = -1.0
    base_engine.use_jina_reranking = True
    base_engine.reranker_adapter = FakeReranker(should_fail=True)
    results = base_engine.retrieve("Admissions", top_k=5)
    # Should not crash, should return RRF results
    assert len(results) == 2
    assert results[0]["retrieval_method"] == "hybrid"

def test_luna_expansion(base_engine):
    base_engine.use_luna_expansion = True
    base_engine.generation_adapter = DeterministicGenerationAdapter()
    # Deterministic adapter returns "Dựa trên các nguồn..."
    results = base_engine.retrieve("Admissions", top_k=5)
    # Should not crash
    assert len(results) > 0

def test_rrf_deduplication():
    # RRF should fuse identical IDs
    vector_store = DeterministicVectorStoreAdapter()
    embedder = DeterministicEmbeddingAdapter(dimension=4)
    corpus = [{"id": "doc1", "content": "Text", "metadata": metadata()}]
    vector_store.upsert(["doc1"], ["Text"], [[1,0,0,0]], [metadata()])
    bm25 = FakeBM25([1.0])
    
    engine = AdvancedRetrievalEngine(
        vector_store=vector_store,
        embedding_adapter=embedder,
        bm25_index=bm25,
        corpus=corpus,
        page_index=DeterministicPageIndexAdapter(),
        score_threshold=0.0
    )
    results = engine.retrieve("Text", top_k=5)
    assert len(results) == 1
    assert results[0]["retrieval_method"] == "hybrid"
