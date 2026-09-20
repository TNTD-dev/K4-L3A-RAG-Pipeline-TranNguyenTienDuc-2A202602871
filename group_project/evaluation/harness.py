"""Reproducible A/B evaluation harness for VinUni Compass.

Runs the golden dataset through the public assistant seam twice — once with
dense-only retrieval and once with hybrid + RRF — holding the Data Snapshot,
generator, prompt, top-k and evaluator fixed so the retrieval strategy is the
only variable.

    python group_project/evaluation/harness.py              # both configs
    python group_project/evaluation/harness.py --config dense
    python group_project/evaluation/harness.py --limit 5 --out-name smoke

Scoring is **lexical and deterministic by default** (``--evaluator lexical``):
no API key, no network, identical numbers on every run. Faithfulness and
answer relevance are therefore *overlap proxies*, not LLM-judged scores — the
report must say so. ``--evaluator ragas`` swaps in RAGAS, which does call a
live judge model and costs money; it is never the default.

Results are written as JSON into ``group_project/evaluation/results/`` in the
shape the Explore page renders.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.vinuni_compass.models import ChatRequest  # noqa: E402

HERE = Path(__file__).resolve().parent
GOLDEN_PATH = HERE / "golden_dataset.json"
RESULTS_DIR = HERE / "results"

#: The A/B pair. Everything except ``use_reranking`` is shared.
CONFIGS: dict[str, tuple[str, bool]] = {
    "dense": ("Config A — dense only", False),
    "hybrid_rrf": ("Config B — hybrid + RRF", True),
}

QUALITY_METRICS = (
    "faithfulness",
    "answer_relevance",
    "context_recall",
    "context_precision",
    "recall_at_5",
    "citation_correctness",
)

#: Function words carry no evidence, so they are excluded from every overlap
#: score — otherwise a fluent but unsupported answer scores well on grammar.
STOPWORDS = frozenset("""
a an and are as at be by for from has have in is it its of on or that the to was were will with
about above after again all also any because been before being between both but can could did do
does doing down during each few further here how if into more most no nor not now only other our
out over own same should so some such than then there these they this those through too under
until up very what when where which while who whom why you your
va la cua cho cac co khong nhung mot trong tai den tu theo voi duoc nay do se da neu khi nhu
va2 hoac ma nen ra vao ve boi con moi thi nhe day kia
""".split())

_WORD = re.compile(r"[0-9A-Za-zÀ-ɏḀ-ỿ]+")


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def normalise(text: str) -> str:
    """Casefold and strip Vietnamese tone marks.

    The corpus mixes accented Vietnamese with unaccented OCR output from the
    PDFs, so comparing raw strings would under-count real overlap.
    """
    decomposed = unicodedata.normalize("NFD", str(text or "").casefold())
    return unicodedata.normalize("NFC", "".join(c for c in decomposed if not unicodedata.combining(c)))


def tokens(text: str) -> list[str]:
    return [t for t in _WORD.findall(normalise(text)) if t not in STOPWORDS and len(t) > 1]


def token_f1(predicted: str, reference: str) -> float:
    """Token-level F1 — the standard lexical answer-overlap score."""
    pred, ref = tokens(predicted), tokens(reference)
    if not pred or not ref:
        return 0.0
    shared = set(pred) & set(ref)
    if not shared:
        return 0.0
    precision, recall = len(shared) / len(set(pred)), len(shared) / len(set(ref))
    return round(2 * precision * recall / (precision + recall), 4)


def coverage(answer: str, context: str) -> float:
    """Share of the answer's content tokens that appear in the context."""
    answer_tokens = set(tokens(answer))
    if not answer_tokens:
        return 0.0
    return round(len(answer_tokens & set(tokens(context))) / len(answer_tokens), 4)


def source_id_of(chunk_id: str) -> str:
    """Chunk IDs are ``<source_id>::chunk-<n>`` (see task4)."""
    return str(chunk_id).split("::", 1)[0]


# ---------------------------------------------------------------------------
# Retrieval metrics
# ---------------------------------------------------------------------------

def average_precision(retrieved: Sequence[str], expected: set[str]) -> float:
    """Rank-aware context precision: relevant chunks early score higher."""
    if not retrieved or not expected:
        return 0.0
    hits, total, seen = 0, 0.0, set()
    for rank, source_id in enumerate(retrieved, start=1):
        if source_id in seen:
            continue
        seen.add(source_id)
        if source_id in expected:
            hits += 1
            total += hits / rank
    return round(total / min(len(expected), len(seen)), 4) if hits else 0.0


def context_recall(retrieved: Sequence[str], expected: set[str]) -> float:
    if not expected:
        return 0.0
    return round(len(expected & set(retrieved)) / len(expected), 4)


def recall_at_k(retrieved: Sequence[str], expected: set[str], k: int = 5) -> float:
    return 1.0 if expected & set(retrieved[:k]) else 0.0


# ---------------------------------------------------------------------------
# Answer-level metrics
# ---------------------------------------------------------------------------

REFUSAL_MARKERS = (
    "cannot verify", "khong the xac minh", "not able to verify",
    "khong co thong tin", "no supporting evidence", "tu choi",
)


def looks_like_refusal(answer: str, sources: Sequence[dict]) -> bool:
    if not sources:
        return True
    normalised = normalise(answer)
    return any(marker in normalised for marker in REFUSAL_MARKERS)


def citation_correctness(answer: str, sources: Sequence[dict], expected: set[str]) -> float:
    """Do the ``[n]`` markers point at real, relevant sources?

    A marker outside the returned range is a fabricated citation and fails the
    case outright. Otherwise the score is the share of cited sources that come
    from an expected document.
    """
    markers = [int(n) for n in re.findall(r"\[(\d{1,2})\]", answer or "")]
    if not markers:
        return 0.0
    if any(n < 1 or n > len(sources) for n in markers):
        return 0.0
    if not expected:
        return 0.0
    cited = {source_id_of(sources[n - 1].get("id", "")) for n in set(markers)}
    return round(len(cited & expected) / len(cited), 4)


# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------

def default_assistant_factory(use_reranking: bool, score_threshold: float) -> Any:
    """Use the shared production composition root for a controlled A/B run.

    Both configurations use the same corpus, generator, prompt, top-k and
    threshold.  PageIndex is disabled in both so the only changing variable is
    dense-only retrieval versus dense + BM25 fused by RRF.
    """
    from dataclasses import replace

    from src.vinuni_compass.bootstrap import build_assistant
    from src.vinuni_compass.settings import Settings

    settings = replace(Settings.from_env(), score_threshold=score_threshold)
    return build_assistant(
        settings,
        use_hybrid=use_reranking,
        use_pageindex_fallback=False,
    )


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

def score_case(case: dict, result: dict, latency_ms: int, top_k: int) -> dict:
    sources = list(result.get("sources") or [])
    answer = str(result.get("answer") or "")
    retrieved = [source_id_of(s.get("id", "")) for s in sources]
    expected = set(case.get("expected_source_ids") or [])
    refused = looks_like_refusal(answer, sources)
    expects_refusal = bool(case.get("expected_refusal"))

    row: dict[str, Any] = {
        "id": case["id"],
        "question": case["question"],
        "category": case.get("category"),
        "language": case.get("language"),
        "mode": case.get("mode", "auto"),
        "expected_refusal": expects_refusal,
        "refused": refused,
        "answer": answer,
        "retrieved_source_ids": retrieved,
        "expected_source_ids": sorted(expected),
        "retrieval_source": result.get("retrieval_source"),
        "latency_ms": latency_ms,
        "failure_stage": None,
        "root_cause": None,
    }

    if expects_refusal:
        # A refusal case has no evidence to retrieve; grading it on recall
        # would reward retrieving irrelevant chunks. It is scored on behaviour.
        correct = 1.0 if refused else 0.0
        row.update({
            "faithfulness": correct,
            "answer_relevance": correct,
            "context_recall": correct,
            "context_precision": correct,
            "recall_at_5": correct,
            "citation_correctness": 1.0 if refused and not re.search(r"\[\d", answer) else 0.0,
        })
        if not refused:
            row["failure_stage"] = "generation"
            row["root_cause"] = "Answered an out-of-scope question instead of refusing."
        return row

    context = "\n".join(str(s.get("content", "")) for s in sources)
    row.update({
        "faithfulness": coverage(answer, context),
        "answer_relevance": token_f1(answer, case["expected_answer"]),
        "context_recall": context_recall(retrieved, expected),
        "context_precision": average_precision(retrieved, expected),
        "recall_at_5": recall_at_k(retrieved, expected, k=min(5, top_k)),
        "citation_correctness": citation_correctness(answer, sources, expected),
    })

    # Attribute the failure to the earliest stage that broke, so the report
    # points at the component to fix rather than at the symptom.
    if row["context_recall"] == 0.0:
        row["failure_stage"] = "retrieval"
        row["root_cause"] = "No chunk from an expected source reached the context window."
    elif refused:
        row["failure_stage"] = "generation"
        row["root_cause"] = "Refused although supporting evidence was retrieved."
    elif row["faithfulness"] < 0.5:
        row["failure_stage"] = "generation"
        row["root_cause"] = "Answer wording is largely absent from the retrieved context."
    elif row["citation_correctness"] < 1.0:
        row["failure_stage"] = "generation"
        row["root_cause"] = "Citations are missing or point outside the expected sources."
    return row


def aggregate(cases: Sequence[dict]) -> dict[str, float]:
    if not cases:
        return {}
    out: dict[str, float] = {
        metric: round(statistics.fmean(c[metric] for c in cases), 4) for metric in QUALITY_METRICS
    }
    out["refusal_accuracy"] = round(
        statistics.fmean(float(c["refused"] == c["expected_refusal"]) for c in cases), 4
    )
    latencies = sorted(c["latency_ms"] for c in cases)
    out["latency_p50_ms"] = latencies[len(latencies) // 2]
    out["latency_p95_ms"] = latencies[max(0, min(len(latencies) - 1, int(len(latencies) * 0.95)))]
    out["latency_mean_ms"] = round(statistics.fmean(latencies))
    return out


def run_config(
    name: str,
    cases: Sequence[dict],
    *,
    top_k: int,
    score_threshold: float,
    assistant_factory: Callable[[bool, float], Any],
) -> dict:
    label, use_reranking = CONFIGS[name]
    assistant = assistant_factory(use_reranking, score_threshold)
    rows = []
    for case in cases:
        request = ChatRequest(query=case["question"], mode=case.get("mode", "auto"), top_k=top_k)
        started = time.perf_counter()
        try:
            result = assistant.answer(request)
        except Exception as exc:  # a provider failure is a data point, not a crash
            result = {"answer": "", "sources": [], "retrieval_source": "none"}
            row = score_case(case, result, round((time.perf_counter() - started) * 1000), top_k)
            row["failure_stage"] = "provider"
            row["root_cause"] = f"{type(exc).__name__}: {exc}"
            rows.append(row)
            continue
        latency = round((time.perf_counter() - started) * 1000)
        rows.append(score_case(case, result, latency, top_k))
    return {"name": name, "label": label, "aggregate": aggregate(rows), "cases": rows}


def load_golden(path: Path = GOLDEN_PATH) -> list[dict]:
    cases = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(cases, list) or not cases:
        raise ValueError(f"{path} does not contain a non-empty list of cases")
    return cases


def evaluate(
    cases: Sequence[dict],
    *,
    config_names: Iterable[str] = tuple(CONFIGS),
    top_k: int = 5,
    score_threshold: float = 0.3,
    assistant_factory: Callable[[bool, float], Any] = default_assistant_factory,
    evaluator: str = "lexical-v1 (deterministic overlap proxy)",
    generator: str = "unknown",
    embedding_model: str = "unknown",
    data_snapshot: str = "unknown",
) -> dict:
    configs = [
        run_config(name, cases, top_k=top_k, score_threshold=score_threshold,
                   assistant_factory=assistant_factory)
        for name in config_names
    ]
    return {
        "run": {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "generator": generator,
            "evaluator": evaluator,
            "embedding_model": embedding_model,
            "data_snapshot": data_snapshot,
            "top_k": top_k,
            "score_threshold": score_threshold,
            "dataset_size": len(cases),
        },
        "configs": configs,
    }


def describe_environment() -> dict[str, str]:
    """Record what actually produced the numbers, for reproducibility.

    ``task10.call_llm`` swallows provider errors and silently falls back to the
    offline adapter, so the configured model name is *not* proof that it ran.
    The caveat travels with the value rather than living only in the report.
    """
    info = {
        "generator": "unknown",
        "embedding_model": "unknown",
        "data_snapshot": "unknown",
    }
    try:
        from src.vinuni_compass.settings import Settings

        settings = Settings.from_env()
        info["generator"] = (
            f"{settings.openai_model} (configured; task10 falls back to the "
            "offline deterministic adapter on any provider error)"
        )
        info["embedding_model"] = settings.embedding_model
        info["data_snapshot"] = settings.data_snapshot
    except Exception:
        pass

    manifest = ROOT / "data" / "source_manifest.json"
    if manifest.exists():
        entries = json.loads(manifest.read_text(encoding="utf-8"))
        stamps = [e.get("crawl_timestamp") for e in entries if e.get("crawl_timestamp")]
        suffix = f" ({len(entries)} sources"
        suffix += f" @ {max(stamps)})" if stamps else ")"
        info["data_snapshot"] = f"{info['data_snapshot']}{suffix}"
    return info


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", action="append", choices=sorted(CONFIGS), help="Repeatable; default is both.")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--score-threshold", type=float, default=0.3)
    parser.add_argument("--limit", type=int, help="Only run the first N golden cases.")
    parser.add_argument("--evaluator", choices=["lexical", "ragas"], default="lexical",
                        help="'ragas' calls a live judge model and needs an API key.")
    parser.add_argument("--out-name", help="File stem inside results/ (default: a timestamp).")
    args = parser.parse_args(argv)

    if args.evaluator == "ragas":
        parser.error(
            "RAGAS scoring is not wired up yet: it needs a live judge model and an API key. "
            "Use the default --evaluator lexical, and record the limitation in RESULT.md."
        )

    cases = load_golden()
    if args.limit:
        cases = cases[: args.limit]

    environment = describe_environment()
    payload = evaluate(
        cases,
        config_names=args.config or tuple(CONFIGS),
        top_k=args.top_k,
        score_threshold=args.score_threshold,
        **environment,
    )

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stem = args.out_name or datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%SZ")
    out = RESULTS_DIR / f"{stem}.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"{len(cases)} cases -> {out.relative_to(ROOT)}")
    for config in payload["configs"]:
        scores = config["aggregate"]
        print(f"\n  {config['label']}")
        for metric in (*QUALITY_METRICS, "refusal_accuracy"):
            print(f"    {metric:<22} {scores.get(metric, float('nan')):.3f}")
        print(f"    {'latency p50 / p95 (ms)':<22} {scores.get('latency_p50_ms')} / {scores.get('latency_p95_ms')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
