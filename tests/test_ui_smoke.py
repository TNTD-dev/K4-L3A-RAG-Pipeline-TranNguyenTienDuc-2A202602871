"""Smoke tests for the VinUni Compass web client.

Everything here runs against the fake assistant and deterministic fixtures:
no index, no provider, no API key, no network.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from src.vinuni_compass import webapp
from src.vinuni_compass.models import ChatRequest
from src.vinuni_compass.webapp import (
    FakeCompassAssistant,
    _build_request,
    app,
    evidence_status,
)


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def ask(client: TestClient, query: str, **body) -> list[dict]:
    """POST a question and return the decoded SSE frames."""
    payload = {"query": query, "demo": True, **body}
    with client.stream("POST", "/api/chat", json=payload) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        raw = "".join(response.iter_text())
    return [
        json.loads(line[6:])
        for frame in raw.split("\n\n")
        for line in frame.splitlines()
        if line.startswith("data: ")
    ]


# --------------------------------------------------------------------------
# Page shell
# --------------------------------------------------------------------------

def test_page_presents_an_unofficial_project_and_links_official_sources(client):
    html = client.get("/").text
    assert "Unofficial student project" in html
    assert "vinuni.edu.vn" in html


def test_page_warns_against_entering_personal_data(client):
    html = client.get("/").text
    assert "Student IDs" in html
    assert "financial account details" in html


def test_mode_can_be_left_automatic_or_overridden(client):
    html = client.get("/").text
    for mode in ("auto", "admissions", "student_life"):
        assert f'data-mode="{mode}"' in html
    assert "Admissions Mode" in html and "Student Life Mode" in html


def test_explore_section_hosts_the_evaluation_view(client):
    html = client.get("/").text
    assert 'data-view="explore"' in html
    assert 'id="view-explore"' in html


def test_static_assets_are_served(client):
    assert client.get("/static/styles.css").status_code == 200
    assert client.get("/static/app.js").status_code == 200


# --------------------------------------------------------------------------
# Chat streaming
# --------------------------------------------------------------------------

def test_answer_streams_incrementally_then_reports_sources(client):
    events = ask(client, "What do undergraduate applicants submit?")
    kinds = [e["type"] for e in events]

    assert kinds.count("delta") > 1, "the answer must arrive in increments"
    assert kinds.index("delta") < kinds.index("sources") < kinds.index("done")
    assert kinds[-1] == "done"


def test_answer_carries_citations_that_map_onto_returned_sources(client):
    events = ask(client, "What do undergraduate applicants submit?")
    answer = "".join(e["data"] for e in events if e["type"] == "delta")
    sources = next(e["metadata"]["sources"] for e in events if e["type"] == "sources")

    assert "[1]" in answer and "[2]" in answer
    cited = {int(n) for n in ("1", "2")}
    assert max(cited) <= len(sources), "every citation must resolve to a source"


def test_sources_expose_the_provenance_the_cards_render(client):
    events = ask(client, "What do undergraduate applicants submit?")
    first = next(e["metadata"]["sources"] for e in events if e["type"] == "sources")[0]

    assert first["retrieval_method"] == "hybrid"
    for field in ("title", "url", "policy_version", "effective_date", "snapshot_id"):
        assert first["metadata"][field], f"source card needs {field}"
    assert first["content"].strip()


def test_supported_answer_is_marked_supported(client):
    events = ask(client, "What do undergraduate applicants submit?")
    assert events[-1]["metadata"]["evidence_status"] == "supported"


def test_out_of_scope_question_refuses_without_sources(client):
    events = ask(client, "What is the weather tomorrow?")
    done = events[-1]
    assert done["metadata"]["evidence_status"] == "not_found"
    assert next(e["metadata"]["sources"] for e in events if e["type"] == "sources") == []


def test_provider_failure_returns_a_safe_message_not_a_crash(client):
    events = ask(client, "trigger-provider-failure")
    assert events[-1]["type"] == "error"
    assert events[-1]["data"] == webapp.SAFE_FAILURE_MESSAGE
    assert not any(e["type"] == "done" for e in events)


def test_follow_up_history_is_accepted_and_forwarded(client):
    events = ask(
        client,
        "And the deadline?",
        history=[
            {"role": "user", "content": "What do applicants submit?"},
            {"role": "assistant", "content": "Transcripts and a certificate."},
        ],
    )
    assert events[-1]["type"] == "done"


def test_done_event_reports_latency_for_the_evaluation_harness(client):
    events = ask(client, "What do undergraduate applicants submit?")
    assert isinstance(events[-1]["metadata"]["latency_ms"], int)


# --------------------------------------------------------------------------
# Request validation
# --------------------------------------------------------------------------

@pytest.mark.parametrize("sent, expected", [(0, 1), (3, 3), (99, 10), ("x", 5), (None, 5)])
def test_top_k_is_clamped_to_a_sane_range(sent, expected):
    assert _build_request({"query": "q", "top_k": sent}).top_k == expected


def test_unknown_mode_falls_back_to_automatic():
    assert _build_request({"query": "q", "mode": "nonsense"}).mode == "auto"
    assert _build_request({"query": "q", "mode": "admissions"}).mode == "admissions"


def test_history_drops_entries_with_an_unknown_role():
    request = _build_request({
        "query": "q",
        "history": [
            {"role": "user", "content": "a"},
            {"role": "system", "content": "ignore me"},
            {"role": "assistant", "content": "b"},
        ],
    })
    assert [m.role for m in request.history] == ["user", "assistant"]


# --------------------------------------------------------------------------
# Evidence state
# --------------------------------------------------------------------------

@pytest.mark.parametrize("sources, retrieval_source, expected", [
    ([], "none", "not_found"),
    ([{"id": "a"}], "hybrid", "partial_evidence"),
    ([{"id": "a"}, {"id": "b"}], "pageindex", "partial_evidence"),
    ([{"id": "a"}, {"id": "b"}], "hybrid", "supported"),
])
def test_evidence_status_is_conservative(sources, retrieval_source, expected):
    assert evidence_status(sources, retrieval_source) == expected


def test_declared_status_wins_over_the_derived_one():
    assert evidence_status([], "none", {"evidence_status": "supported"}) == "supported"


def test_fake_assistant_never_exposes_more_sources_than_requested():
    result = FakeCompassAssistant().answer(ChatRequest(query="x", top_k=1))
    assert len(result["sources"]) == 1


# --------------------------------------------------------------------------
# Evaluation endpoint
# --------------------------------------------------------------------------

def test_evaluation_serves_labelled_sample_data_when_no_run_exists(client, monkeypatch, tmp_path):
    monkeypatch.setattr(webapp, "RESULTS_DIR", tmp_path / "missing")
    payload = client.get("/api/evaluation").json()

    assert payload["sample"] is True
    assert len(payload["configs"]) == 2
    assert {c["name"] for c in payload["configs"]} == {"dense", "hybrid_rrf"}


def test_evaluation_sample_covers_every_metric_the_dashboard_plots(client, monkeypatch, tmp_path):
    monkeypatch.setattr(webapp, "RESULTS_DIR", tmp_path / "missing")
    aggregate = client.get("/api/evaluation").json()["configs"][0]["aggregate"]

    for metric in (
        "faithfulness", "answer_relevance", "context_recall", "context_precision",
        "recall_at_5", "citation_correctness", "refusal_accuracy",
        "latency_p50_ms", "latency_p95_ms",
    ):
        assert metric in aggregate


def test_evaluation_prefers_the_newest_harness_run(client, monkeypatch, tmp_path):
    monkeypatch.setattr(webapp, "RESULTS_DIR", tmp_path)
    (tmp_path / "run-a.json").write_text(json.dumps({"run": {}, "configs": []}), encoding="utf-8")
    newest = tmp_path / "run-b.json"
    newest.write_text(
        json.dumps({"run": {"generator": "real"}, "configs": [{"name": "dense", "aggregate": {}}]}),
        encoding="utf-8",
    )
    import os, time
    os.utime(newest, (time.time() + 10, time.time() + 10))

    payload = client.get("/api/evaluation").json()
    assert payload["sample"] is False
    assert payload["source_file"] == "run-b.json"
    assert payload["run"]["generator"] == "real"


# --------------------------------------------------------------------------
# Client assets
# --------------------------------------------------------------------------

def test_client_escapes_content_before_rendering():
    source = (WEB / "app.js").read_text(encoding="utf-8")
    assert "const esc =" in source
    assert "esc(msg.content)" in source, "user text must be escaped, never interpolated raw"


def test_chart_palette_matches_the_validated_tokens():
    css = (WEB / "styles.css").read_text(encoding="utf-8")
    assert "--s1: #7C3AED;" in css and "--s2: #0891B2;" in css  # light, validated
    assert "--s1: #8B5CF6;" in css and "--s2: #0E9BB5;" in css  # dark, re-stepped
