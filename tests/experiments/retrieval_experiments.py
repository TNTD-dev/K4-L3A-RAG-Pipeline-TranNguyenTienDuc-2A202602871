"""Reproducible offline Recall@5 comparisons for retrieval decisions.

The harness uses deterministic provider doubles and the same shared BM25/RRF
seams as production. Live Luna/Jina runs are optional and are not required for
the checked-in baseline report.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

if __package__ in {None, ""}:  # Allow the documented direct script command.
    sys.path.insert(0, str(Path(__file__).parents[2]))

from src.task6_lexical_search import build_bm25_index
from src.vinuni_compass.providers.adapters import (
    DeterministicPageIndexAdapter,
    DeterministicVectorStoreAdapter,
)
from src.vinuni_compass.retrieval.advanced import AdvancedRetrievalEngine


class KeywordEmbedding:
    """Tiny deterministic query encoder with one intentional dense miss."""

    vectors = {
        "tuition deadline": [1.0, 0.0, 0.0, 0.0, 0.0],
        "scholarship eligibility": [1.0, 0.0, 0.0, 0.0, 0.0],
        "quiet hours dorm": [0.0, 0.0, 1.0, 0.0, 0.0],
        "library hours": [0.0, 0.0, 0.0, 1.0, 0.0],
        "internship credits": [0.0, 0.0, 0.0, 0.0, 1.0],
        "financial aid": [1.0, 0.0, 0.0, 0.0, 0.0],
    }

    def embed(self, texts):
        return [self.vectors.get(text.casefold(), [0.0] * 5) for text in texts]


class ExpansionAdapter:
    def complete(self, system_prompt, user_message):
        del system_prompt
        return "scholarship eligibility" if "financial aid" in user_message.casefold() else user_message


class OverlapReranker:
    def rerank(self, query, documents):
        terms = set(query.casefold().split())
        return [sum(term in document.casefold().split() for term in terms) for document in documents]


def build_corpus():
    rows = [
        ("tuition", "tuition fees and payment deadline", "admissions"),
        ("scholarship", "scholarship eligibility and application", "admissions"),
        ("dorm", "residential quiet hours and dorm rules", "student_life"),
        ("library", "library opening hours and services", "student_life"),
        ("internship", "internship credits and placement rules", "student_life"),
        ("generic", "general campus information", "student_life"),
    ]
    return [
        {
            "id": item_id,
            "content": content,
            "metadata": {
                "source": f"{item_id}.md",
                "title": item_id.title(),
                "doc_type": "legal",
                "url": None,
                "chunk_index": 0,
                "mode": mode,
            },
        }
        for item_id, content, mode in rows
    ]


def build_engine(*, hybrid=True, expansion=False, jina=False):
    corpus = build_corpus()
    vectors = {
        "tuition": [1, 0, 0, 0, 0],
        "scholarship": [0, 1, 0, 0, 0],
        "dorm": [0, 0, 1, 0, 0],
        "library": [0, 0, 0, 1, 0],
        "internship": [0, 0, 0, 0, 1],
        "generic": [0, 0, 0, 0, 0.5],
    }
    store = DeterministicVectorStoreAdapter()
    store.upsert(
        [row["id"] for row in corpus],
        [row["content"] for row in corpus],
        [vectors[row["id"]] for row in corpus],
        [row["metadata"] for row in corpus],
    )
    return AdvancedRetrievalEngine(
        vector_store=store,
        embedding_adapter=KeywordEmbedding(),
        bm25_index=build_bm25_index(corpus),
        corpus=corpus,
        page_index=DeterministicPageIndexAdapter(),
        generation_adapter=ExpansionAdapter() if expansion else None,
        reranker_adapter=OverlapReranker() if jina else None,
        use_hybrid=hybrid,
        use_luna_expansion=expansion,
        use_jina_reranking=jina,
        score_threshold=-1.0,
    )


def recall_at_5(engine, dataset):
    hits = 0
    for query, expected_id in dataset:
        if expected_id in {item["id"] for item in engine.retrieve(query, top_k=5)}:
            hits += 1
    return hits / len(dataset) if dataset else 0.0


def run_experiments(output_path: Path | None = None) -> dict:
    baseline = [
        ("tuition deadline", "tuition"),
        ("scholarship eligibility", "scholarship"),
        ("quiet hours dorm", "dorm"),
        ("library hours", "library"),
        ("internship credits", "internship"),
    ]
    expansion_cases = baseline + [("financial aid", "scholarship")]
    report = {
        "metric": "Recall@5",
        "provider_mode": "deterministic offline doubles",
        "baseline_cases": len(baseline),
        "results": {
            "dense_only": recall_at_5(build_engine(hybrid=False), baseline),
            "hybrid_rrf": recall_at_5(build_engine(), baseline),
            "expansion_off": recall_at_5(build_engine(), expansion_cases),
            "expansion_on": recall_at_5(build_engine(expansion=True), expansion_cases),
            "rrf_off_jina": recall_at_5(build_engine(), baseline),
            "rrf_on_jina": recall_at_5(build_engine(jina=True), baseline),
        },
    }
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def test_recall_experiments(tmp_path):
    report = run_experiments(tmp_path / "retrieval_ab.json")
    results = report["results"]
    assert 0.0 <= results["dense_only"] <= 1.0
    assert 0.0 <= results["hybrid_rrf"] <= 1.0
    assert results["hybrid_rrf"] >= results["dense_only"]
    assert results["expansion_on"] >= results["expansion_off"]
    assert 0.0 <= results["rrf_on_jina"] <= 1.0
    assert (tmp_path / "retrieval_ab.json").exists()


if __name__ == "__main__":
    destination = Path(__file__).parents[2] / "reports" / "retrieval_ab.json"
    print(json.dumps(run_experiments(destination), indent=2))
