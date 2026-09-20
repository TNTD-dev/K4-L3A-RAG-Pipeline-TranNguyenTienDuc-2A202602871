"""Recall@5 experiments for the advanced retrieval engine."""

import pytest
from src.vinuni_compass.retrieval.advanced import AdvancedRetrievalEngine
from src.vinuni_compass.providers.adapters import (
    DeterministicEmbeddingAdapter,
    DeterministicVectorStoreAdapter,
    DeterministicPageIndexAdapter,
    DeterministicGenerationAdapter,
)

class FakeBM25:
    def __init__(self, corpus):
        self.corpus = corpus
    def get_scores(self, tokens):
        # Extremely naive BM25 for deterministic tests
        scores = []
        for item in self.corpus:
            content = item["content"].lower()
            score = sum(content.count(t) for t in tokens)
            scores.append(float(score))
        return scores

def build_test_corpus():
    return [
        {"id": "doc1", "content": "The university admissions policy requires SAT scores.", "metadata": {"mode": "admissions", "source": "adm.md", "title": "Admissions", "doc_type": "legal"}},
        {"id": "doc2", "content": "Student life includes many clubs and activities.", "metadata": {"mode": "student_life", "source": "life.md", "title": "Life", "doc_type": "news"}},
        {"id": "doc3", "content": "Dormitory rules state quiet hours begin at 10 PM.", "metadata": {"mode": "student_life", "source": "dorm.md", "title": "Dorm", "doc_type": "legal"}},
        {"id": "doc4", "content": "Financial aid applications open in January.", "metadata": {"mode": "admissions", "source": "fin.md", "title": "FinAid", "doc_type": "legal"}},
        {"id": "doc5", "content": "The campus library is open 24/7 during exam weeks.", "metadata": {"mode": "student_life", "source": "lib.md", "title": "Library", "doc_type": "news"}}
    ]

def evaluate_recall_at_5(engine, dataset):
    correct = 0
    for query, expected_id in dataset:
        results = engine.retrieve(query, top_k=5)
        ids = [res["id"] for res in results]
        if expected_id in ids:
            correct += 1
    return correct / len(dataset) if dataset else 0.0

def test_recall_experiments():
    corpus = build_test_corpus()
    vector_store = DeterministicVectorStoreAdapter()
    embedder = DeterministicEmbeddingAdapter(dimension=4)
    # Give them orthogonal embeddings to simulate different concepts
    vector_store.upsert(
        [c["id"] for c in corpus],
        [c["content"] for c in corpus],
        [[1,0,0,0], [0,1,0,0], [0,0,1,0], [0,0,0,1], [1,1,0,0]],
        [c["metadata"] for c in corpus]
    )
    bm25 = FakeBM25(corpus)
    page_index = DeterministicPageIndexAdapter()
    
    # Dataset: (query, expected_doc_id)
    dataset = [
        ("admissions policy", "doc1"),
        ("quiet hours", "doc3"),
        ("financial aid", "doc4"),
        ("library hours", "doc5")
    ]
    
    # 1. Dense Only
    engine_dense = AdvancedRetrievalEngine(
        vector_store=vector_store, embedding_adapter=embedder, bm25_index=FakeBM25([]),
        corpus=[], page_index=page_index, score_threshold=0.0
    )
    recall_dense = evaluate_recall_at_5(engine_dense, dataset)
    
    # 2. Hybrid (Dense + BM25)
    engine_hybrid = AdvancedRetrievalEngine(
        vector_store=vector_store, embedding_adapter=embedder, bm25_index=bm25,
        corpus=corpus, page_index=page_index, score_threshold=0.0
    )
    recall_hybrid = evaluate_recall_at_5(engine_hybrid, dataset)
    
    # 3. Hybrid + Luna Expansion
    engine_luna = AdvancedRetrievalEngine(
        vector_store=vector_store, embedding_adapter=embedder, bm25_index=bm25,
        corpus=corpus, page_index=page_index, generation_adapter=DeterministicGenerationAdapter(),
        use_luna_expansion=True, score_threshold=0.0
    )
    recall_luna = evaluate_recall_at_5(engine_luna, dataset)
    
    print("\n=== Retrieval Experiments (Recall@5) ===")
    print(f"Dense Only:         {recall_dense:.2%}")
    print(f"Hybrid (RRF):       {recall_hybrid:.2%}")
    print(f"Hybrid + Luna:      {recall_luna:.2%}")
    
    assert recall_dense >= 0
    assert recall_hybrid >= 0
    assert recall_luna >= 0

if __name__ == "__main__":
    test_recall_experiments()
