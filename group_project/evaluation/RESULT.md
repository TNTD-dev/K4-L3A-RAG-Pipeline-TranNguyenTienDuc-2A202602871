# RAG evaluation results

## Run information

| Field | Value |
| --- | --- |
| Evaluation date | 2026-09-20 (UTC) |
| Framework | Local deterministic harness (`group_project.evaluation.harness`) |
| Evaluator | `lexical-v1`: deterministic token-overlap proxy; not an LLM judge |
| Generator | `gpt-5.6-luna` configured; provider fallback may use the deterministic adapter |
| Embedding model | `text-embedding-3-small` |
| Data Snapshot | `vinuni-public-2026-09-20` — 18 public sources, latest crawl `2026-09-20T07:40:00+00:00` |
| Golden dataset | 30 cases: 10 Admissions, 10 Student Life, 5 keyword/multi-source, 5 refusal; Vietnamese and English included |
| `top_k` / threshold | 5 / 0.30 |

The reproducible per-case inputs and all 60 outputs are in
[`golden_dataset.json`](golden_dataset.json) and
[`results/issue5-ab.json`](results/issue5-ab.json). Run again with:

```bash
python -m group_project.evaluation.harness --out-name issue5-ab
```

## Configurations

- **Config A — dense only:** shared production assistant with dense retrieval only.
- **Config B — hybrid + RRF:** same assistant, corpus, snapshot, prompt,
  generator, evaluator, threshold and `top_k`; only BM25 + one RRF fusion changes.
- PageIndex fallback is disabled in both configurations, so it cannot confound comparison.

## Overall scores

| Metric | Dense only | Hybrid + RRF | Delta B−A |
| --- | ---: | ---: | ---: |
| Faithfulness proxy | 0.1667 | 0.1989 | +0.0322 |
| Answer relevance proxy | 0.1667 | 0.1552 | -0.0115 |
| Context recall | 0.1667 | 0.6333 | +0.4666 |
| Context precision | 0.1667 | 0.5444 | +0.3777 |
| Recall@5 | 0.1667 | 0.6667 | +0.5000 |
| Citation correctness | 0.1667 | 0.2939 | +0.1272 |
| Refusal accuracy | 0.1667 | 0.8000 | +0.6333 |
| Latency p50 / p95 | 8 / 11 ms | 8 / 11 ms | 0 / 0 ms |

## A/B comparison

Hybrid + RRF is the better retrieval configuration for this snapshot: it
substantially improves source recall, precision and Recall@5 without a measured
latency increase in the local deterministic run. The proxy answer metrics remain
low because this run did not prove that a live Luna response was used; therefore
they are diagnostic signals, not a quality claim about a deployed model.

## Worst performers and failure analysis

| Case | Config | Failure stage | Root cause |
| --- | --- | --- | --- |
| A01 — Nursing tuition | Dense | retrieval | No expected source reached the context window. |
| A02 — Medical Doctor tuition | Hybrid + RRF | retrieval | No expected source reached the context window. |
| S04 — overnight guest request | Hybrid + RRF | retrieval | No expected source reached the context window. |
| O01 — Hanoi weather | Hybrid + RRF | generation | The answer was not refused despite being out of scope. |

## Recommendations

| Priority | Action | Evidence | Verification |
| ---: | --- | --- | --- |
| 1 | Rebuild Chroma with the selected embedding provider before the final demo. | Tuition cases still miss their expected source. | Re-run this harness and inspect A01/A02 context recall. |
| 2 | Improve refusal routing before production demo. | Hybrid refusal accuracy is 0.80; O01 was answered. | All five out-of-scope cases should report `not_found`. |
| 3 | Run a separately labelled live-Luna evaluation after keys are configured. | Current faithfulness/relevance are lexical proxies and fallback is possible. | Save a new results JSON with confirmed provider metadata and compare to this baseline. |

## Cost and limitations

This checked-in run uses no live evaluator and does not claim provider cost. A
live Luna or RAGAS evaluation must be recorded separately with its model, token
usage and cost. `context_precision` deduplicates repeated chunks from the same
source document, preventing a single document from inflating the metric.
