from src.vinuni_compass.assistant.service import DefaultCompassAssistant
from src.vinuni_compass.models import ChatMessage, ChatRequest


def chunk(item_id="policy-0", mode="admissions", content="Applicants may apply for scholarships."):
    return {
        "id": item_id, "content": content, "score": 0.9, "retrieval_method": "hybrid",
        "metadata": {"source": "policy.md", "title": "Admissions Policy", "doc_type": "legal",
                     "url": "https://example.edu/policy", "chunk_index": 0, "mode": mode,
                     "policy_version": "V1", "effective_date": "2026-01-01"},
    }


class FakeRetrieval:
    def __init__(self, results):
        self.results, self.calls = results, []

    def retrieve(self, query, *, mode="auto", top_k=5):
        self.calls.append((query, mode, top_k))
        return self.results[:top_k]


class FakeLuna:
    def __init__(self, text="Scholarships are available [1]."):
        self.text, self.calls = text, []

    def complete(self, system_prompt, user_message):
        self.calls.append((system_prompt, user_message))
        return self.text

    def stream(self, system_prompt, user_message):
        yield self.complete(system_prompt, user_message)


def test_auto_routes_admissions_and_returns_traceable_citations():
    retrieval, luna = FakeRetrieval([chunk()]), FakeLuna()
    answer = DefaultCompassAssistant(retrieval, luna).answer(ChatRequest("How do I apply for admission?"))
    assert retrieval.calls[0][1] == "admissions"
    assert answer["evidence_status"] == "supported"
    assert "[1]" in answer["answer"] and "Sources:" in answer["answer"]
    assert "Policy Version: V1" in answer["answer"]
    assert "GPT-5.6 Luna" in luna.calls[0][0]


def test_manual_mode_is_respected_and_filters_wrong_mode():
    retrieval = FakeRetrieval([chunk("a", "admissions"), chunk("b", "student_life")])
    answer = DefaultCompassAssistant(retrieval, FakeLuna()).answer(ChatRequest("What are tuition fees?", mode="student_life"))
    assert retrieval.calls[0][1] == "student_life"
    assert [item["id"] for item in answer["sources"]] == ["b"]


def test_vietnamese_question_and_minimal_safe_history_are_forwarded():
    luna = FakeLuna("Thông tin có trong quy định.")
    request = ChatRequest("Học bổng tuyển sinh thế nào?", history=(
        ChatMessage("user", "old context"), ChatMessage("user", "My id is 123456789"),
    ))
    answer = DefaultCompassAssistant(FakeRetrieval([chunk()]), luna).answer(request)
    assert answer["answer"].endswith("2026-01-01)")
    assert "old context" in luna.calls[0][1]
    assert "123456789" not in luna.calls[0][1]


def test_no_evidence_and_provider_error_are_safe():
    empty = DefaultCompassAssistant(FakeRetrieval([]), FakeLuna()).answer(ChatRequest("Unknown policy"))
    assert empty["retrieval_source"] == "none" and empty["evidence_status"] == "not_found"
    class BrokenLuna(FakeLuna):
        def complete(self, system_prompt, user_message):
            raise TimeoutError("secret should not leak")
    failed = DefaultCompassAssistant(FakeRetrieval([chunk()]), BrokenLuna()).answer(ChatRequest("admission"))
    assert "secret" not in failed["answer"] and failed["evidence_status"] == "partial_evidence"


def test_stream_is_portable_and_matches_answer():
    assistant = DefaultCompassAssistant(FakeRetrieval([chunk()]), FakeLuna())
    events = list(assistant.stream(ChatRequest("admission")))
    assert events[0].type == "metadata" and events[-1].type == "done"
    assert sum(event.type == "delta" for event in events) >= 2
    assert next(event for event in events if event.type == "sources").metadata["sources"]


def test_sources_keep_retrieval_order_and_invalid_citations_are_rejected():
    ranked = [chunk(f"policy-{index}") | {"score": 1 - index / 10} for index in range(4)]
    assistant = DefaultCompassAssistant(FakeRetrieval(ranked), FakeLuna("Unsupported claim [99]."))

    result = assistant.answer(ChatRequest("admission", top_k=4))

    assert [item["id"] for item in result["sources"]] == [f"policy-{index}" for index in range(4)]
    assert result["evidence_status"] == "partial_evidence"
    assert "[99]" not in result["answer"]


def test_untagged_and_unsupported_year_evidence_are_refused():
    untagged = chunk()
    untagged["metadata"].pop("mode")
    assert DefaultCompassAssistant(FakeRetrieval([untagged]), FakeLuna()).answer(
        ChatRequest("admission")
    )["evidence_status"] == "not_found"
    assert DefaultCompassAssistant(FakeRetrieval([chunk()]), FakeLuna()).answer(
        ChatRequest("What was the admission policy in 2035?")
    )["evidence_status"] == "not_found"


def test_conflicting_policy_versions_are_qualified_as_partial():
    current = chunk("current")
    older = chunk("older")
    older["metadata"] = {**older["metadata"], "policy_version": "V0", "effective_date": "2025-01-01"}

    result = DefaultCompassAssistant(FakeRetrieval([current, older]), FakeLuna()).answer(
        ChatRequest("admission")
    )

    assert result["evidence_status"] == "partial_evidence"


def test_stream_uses_provider_stream_and_returns_safe_error_event():
    class StreamingLuna(FakeLuna):
        def complete(self, system_prompt, user_message):
            raise AssertionError("stream must not call complete")

        def stream(self, system_prompt, user_message):
            yield "Scholarships "
            yield "are available [1]."

    events = list(DefaultCompassAssistant(FakeRetrieval([chunk()]), StreamingLuna()).stream(ChatRequest("admission")))
    assert [event.data for event in events if event.type == "delta"][:2] == ["Scholarships ", "are available [1]."]

    class BrokenStream(FakeLuna):
        def stream(self, system_prompt, user_message):
            raise TimeoutError("secret")
            yield

    failed = list(DefaultCompassAssistant(FakeRetrieval([chunk()]), BrokenStream()).stream(ChatRequest("admission")))
    assert [event.type for event in failed][-2:] == ["error", "done"]
    assert "secret" not in failed[-2].data
