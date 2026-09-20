"""Evaluation harness and golden dataset tests.

Every case here uses deterministic fixtures — no index, no provider, no API
key, no network — so the numbers are identical on every machine.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from group_project.evaluation import harness as H


ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Deterministic stand-ins
# ---------------------------------------------------------------------------

def chunk(source_id: str, index: int = 0, content: str = "", score: float = 0.9) -> dict:
    return {
        "id": f"{source_id}::chunk-{index}",
        "content": content or f"Body text for {source_id}.",
        "score": score,
        "metadata": {
            "source": f"{source_id}.md", "title": source_id, "doc_type": "legal",
            "url": "https://vinuni.edu.vn", "chunk_index": index,
        },
        "retrieval_method": "hybrid",
    }


class StubAssistant:
    """Answers from a canned map keyed by question, so scores are fixed."""

    def __init__(self, replies: dict[str, dict], *, suffix: str = "") -> None:
        self.replies = replies
        self.suffix = suffix
        self.seen: list[str] = []

    def answer(self, request) -> dict:
        self.seen.append(request.query)
        reply = self.replies.get(request.query)
        if reply is None:
            return {"answer": "I cannot verify this from the public VinUni sources.",
                    "sources": [], "retrieval_source": "none"}
        return {**reply, "answer": reply["answer"] + self.suffix}


def factory_for(replies: dict[str, dict]):
    """An assistant factory whose two configs differ, so A/B is observable."""
    def build(use_reranking: bool, score_threshold: float):
        return StubAssistant(replies, suffix="" if use_reranking else " ")
    return build


# ---------------------------------------------------------------------------
# Text normalisation
# ---------------------------------------------------------------------------

def test_normalise_folds_vietnamese_tone_marks():
    # The PDFs lose diacritics in OCR while the web pages keep them, so the
    # two spellings of the same word must compare equal.
    assert H.normalise("Học phí") == H.normalise("hoc phi")


def test_tokens_drop_stopwords_and_single_characters():
    assert H.tokens("the GPA of a student") == ["gpa", "student"]


def test_source_id_is_taken_from_the_chunk_id():
    assert H.source_id_of("residential-life-guideline-v5::chunk-12") == "residential-life-guideline-v5"
    assert H.source_id_of("no-chunk-suffix") == "no-chunk-suffix"


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def test_token_f1_is_one_for_identical_text_and_zero_when_disjoint():
    assert H.token_f1("minimum twelve credits", "minimum twelve credits") == 1.0
    assert H.token_f1("quiet hours", "tuition refund") == 0.0


def test_token_f1_is_symmetric():
    a, b = "cumulative GPA of 3.2 or higher", "maintain cumulative GPA 3.2"
    assert H.token_f1(a, b) == H.token_f1(b, a)


def test_coverage_measures_answer_tokens_present_in_the_context():
    assert H.coverage("twelve credits", "the minimum is twelve credits per semester") == 1.0
    assert H.coverage("twelve credits", "unrelated text about tuition") == 0.0
    assert H.coverage("", "anything") == 0.0


def test_context_recall_counts_expected_documents_that_were_retrieved():
    assert H.context_recall(["a", "b"], {"a", "b"}) == 1.0
    assert H.context_recall(["a", "z"], {"a", "b"}) == 0.5
    assert H.context_recall(["z"], {"a"}) == 0.0


def test_context_precision_rewards_relevant_chunks_ranked_first():
    early = H.average_precision(["a", "z", "z"], {"a"})
    late = H.average_precision(["z", "z", "a"], {"a"})
    assert early > late > 0


def test_context_precision_is_zero_without_a_hit():
    assert H.average_precision(["z", "y"], {"a"}) == 0.0
    assert H.average_precision([], {"a"}) == 0.0


def test_recall_at_5_ignores_hits_beyond_the_cutoff():
    ranked = ["z", "z", "z", "z", "z", "a"]
    assert H.recall_at_k(ranked, {"a"}, k=5) == 0.0
    assert H.recall_at_k(ranked, {"a"}, k=6) == 1.0


# ---------------------------------------------------------------------------
# Citation correctness
# ---------------------------------------------------------------------------

def test_citation_correctness_rewards_markers_pointing_at_expected_sources():
    sources = [chunk("policy-a"), chunk("policy-b")]
    assert H.citation_correctness("Answer [1] and [2].", sources, {"policy-a", "policy-b"}) == 1.0


def test_a_fabricated_citation_fails_the_case_outright():
    sources = [chunk("policy-a")]
    assert H.citation_correctness("Answer [1] plus [7].", sources, {"policy-a"}) == 0.0


def test_an_uncited_answer_scores_zero_even_when_retrieval_was_right():
    sources = [chunk("policy-a")]
    assert H.citation_correctness("A confident answer with no markers.", sources, {"policy-a"}) == 0.0


def test_citing_an_unexpected_source_is_partially_penalised():
    sources = [chunk("policy-a"), chunk("unrelated")]
    assert H.citation_correctness("Answer [1][2].", sources, {"policy-a"}) == 0.5


# ---------------------------------------------------------------------------
# Refusal detection
# ---------------------------------------------------------------------------

def test_an_answer_without_sources_is_always_a_refusal():
    assert H.looks_like_refusal("Anything at all.", []) is True


@pytest.mark.parametrize("answer", [
    "I cannot verify this from the public VinUni sources.",
    "Tôi không thể xác minh thông tin này.",
])
def test_refusal_wording_is_detected_in_both_languages(answer):
    assert H.looks_like_refusal(answer, [chunk("policy-a")]) is True


def test_a_grounded_answer_is_not_a_refusal():
    assert H.looks_like_refusal("The minimum is 12 credits [1].", [chunk("policy-a")]) is False


# ---------------------------------------------------------------------------
# Case scoring
# ---------------------------------------------------------------------------

GROUNDED_CASE = {
    "id": "T01", "question": "How many credits?", "category": "student_life",
    "language": "en", "mode": "student_life",
    "expected_answer": "The minimum is twelve credits per semester.",
    "expected_context": "minimum twelve credits", "expected_source_ids": ["academic-regs"],
    "expected_refusal": False,
}

REFUSAL_CASE = {
    "id": "T02", "question": "Weather?", "category": "out_of_scope",
    "language": "en", "mode": "auto", "expected_answer": "Refusal.",
    "expected_context": "none", "expected_source_ids": [], "expected_refusal": True,
}


def test_a_correct_grounded_answer_scores_well_across_the_board():
    result = {
        "answer": "The minimum is twelve credits per semester [1].",
        "sources": [chunk("academic-regs", content="the minimum is twelve credits per semester")],
        "retrieval_source": "hybrid",
    }
    row = H.score_case(GROUNDED_CASE, result, 100, top_k=5)

    assert row["context_recall"] == 1.0
    assert row["recall_at_5"] == 1.0
    assert row["citation_correctness"] == 1.0
    assert row["faithfulness"] == 1.0
    assert row["answer_relevance"] > 0.9
    assert row["failure_stage"] is None


def test_a_retrieval_miss_is_attributed_to_retrieval():
    result = {"answer": "Something [1].", "sources": [chunk("wrong-doc")], "retrieval_source": "hybrid"}
    row = H.score_case(GROUNDED_CASE, result, 100, top_k=5)

    assert row["context_recall"] == 0.0
    assert row["failure_stage"] == "retrieval"


def test_refusing_despite_good_evidence_is_attributed_to_generation():
    result = {
        "answer": "I cannot verify this from the public VinUni sources.",
        "sources": [chunk("academic-regs")], "retrieval_source": "hybrid",
    }
    row = H.score_case(GROUNDED_CASE, result, 100, top_k=5)

    assert row["context_recall"] == 1.0
    assert row["failure_stage"] == "generation"
    assert "Refused" in row["root_cause"]


def test_a_correct_refusal_scores_full_marks_and_flags_nothing():
    result = {"answer": "I cannot verify this.", "sources": [], "retrieval_source": "none"}
    row = H.score_case(REFUSAL_CASE, result, 40, top_k=5)

    assert row["refused"] is True
    assert all(row[m] == 1.0 for m in H.QUALITY_METRICS)
    assert row["failure_stage"] is None


def test_answering_an_out_of_scope_question_scores_zero():
    result = {"answer": "It will be sunny [1].", "sources": [chunk("x")], "retrieval_source": "hybrid"}
    row = H.score_case(REFUSAL_CASE, result, 40, top_k=5)

    assert row["refused"] is False
    assert all(row[m] == 0.0 for m in H.QUALITY_METRICS)
    assert row["failure_stage"] == "generation"


# ---------------------------------------------------------------------------
# Aggregation and the A/B run
# ---------------------------------------------------------------------------

def test_aggregate_reports_every_metric_the_dashboard_plots():
    rows = [
        H.score_case(GROUNDED_CASE, {
            "answer": "The minimum is twelve credits per semester [1].",
            "sources": [chunk("academic-regs", content="minimum twelve credits per semester")],
            "retrieval_source": "hybrid"}, 120, 5),
        H.score_case(REFUSAL_CASE, {"answer": "I cannot verify this.", "sources": [],
                                    "retrieval_source": "none"}, 80, 5),
    ]
    scores = H.aggregate(rows)

    for metric in (*H.QUALITY_METRICS, "refusal_accuracy", "latency_p50_ms", "latency_p95_ms"):
        assert metric in scores
    assert scores["refusal_accuracy"] == 1.0


def test_aggregate_of_no_cases_is_empty_rather_than_a_crash():
    assert H.aggregate([]) == {}


def test_evaluate_runs_both_configurations_over_the_same_cases():
    replies = {
        GROUNDED_CASE["question"]: {
            "answer": "The minimum is twelve credits per semester [1].",
            "sources": [chunk("academic-regs", content="minimum twelve credits per semester")],
            "retrieval_source": "hybrid"},
    }
    payload = H.evaluate(
        [GROUNDED_CASE, REFUSAL_CASE],
        assistant_factory=factory_for(replies),
        top_k=5, generator="stub", data_snapshot="fixture",
    )

    assert [c["name"] for c in payload["configs"]] == ["dense", "hybrid_rrf"]
    assert payload["run"]["dataset_size"] == 2
    assert payload["run"]["top_k"] == 5
    assert payload["run"]["data_snapshot"] == "fixture"
    for config in payload["configs"]:
        assert len(config["cases"]) == 2
        assert config["aggregate"]["refusal_accuracy"] == 1.0


def test_both_configurations_see_an_identical_question_set():
    seen: list[list[str]] = []

    def build(use_reranking, score_threshold):
        stub = StubAssistant({})
        seen.append(stub.seen)
        return stub

    H.evaluate([GROUNDED_CASE, REFUSAL_CASE], assistant_factory=build)
    assert seen[0] == seen[1] == [GROUNDED_CASE["question"], REFUSAL_CASE["question"]]


def test_a_provider_failure_is_recorded_rather_than_aborting_the_run():
    class Exploding:
        def answer(self, request):
            raise RuntimeError("provider down")

    payload = H.evaluate([GROUNDED_CASE], assistant_factory=lambda *a: Exploding())
    row = payload["configs"][0]["cases"][0]

    assert row["failure_stage"] == "provider"
    assert "provider down" in row["root_cause"]


def test_ragas_evaluator_is_refused_rather_than_silently_running_lexical():
    with pytest.raises(SystemExit):
        H.main(["--evaluator", "ragas"])


# ---------------------------------------------------------------------------
# Golden dataset
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def golden() -> list[dict]:
    return H.load_golden()


def test_golden_dataset_has_at_least_thirty_cases(golden):
    assert len(golden) >= 30


def test_golden_dataset_covers_the_agreed_composition(golden):
    counts = Counter(c["category"] for c in golden)
    assert counts["admissions"] >= 10
    assert counts["student_life"] >= 10
    assert counts["keyword_multisource"] >= 5
    assert counts["out_of_scope"] >= 5


def test_golden_dataset_represents_both_languages(golden):
    counts = Counter(c["language"] for c in golden)
    assert counts["vi"] >= 5 and counts["en"] >= 5


def test_every_case_records_answer_evidence_mode_and_refusal(golden):
    for case in golden:
        assert case["mode"] in {"auto", "admissions", "student_life"}
        assert isinstance(case["expected_refusal"], bool)
        assert isinstance(case["expected_source_ids"], list)
        for field in ("question", "expected_answer", "expected_context"):
            assert str(case[field]).strip(), f"{case['id']} is missing {field}"


def test_case_ids_are_unique(golden):
    ids = [c["id"] for c in golden]
    assert len(ids) == len(set(ids))


def test_expected_evidence_exists_in_the_data_snapshot(golden):
    manifest = json.loads((ROOT / "data" / "source_manifest.json").read_text(encoding="utf-8"))
    known = {entry["source_id"] for entry in manifest}
    for case in golden:
        unknown = set(case["expected_source_ids"]) - known
        assert not unknown, f"{case['id']} cites sources outside the snapshot: {unknown}"


def test_refusal_cases_are_exactly_the_ones_without_expected_evidence(golden):
    for case in golden:
        assert case["expected_refusal"] == (case["expected_source_ids"] == []), case["id"]
