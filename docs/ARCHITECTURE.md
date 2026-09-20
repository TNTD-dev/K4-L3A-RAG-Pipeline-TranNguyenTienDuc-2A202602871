# VinUni Compass architecture

This structure keeps the required `task1` through `task10` modules compatible
with the course contract while moving product behavior behind a few deep module
interfaces.

## Module map

```text
src/
├── task1_...task10_...        # Course-compatible adapters
├── contracts.py               # Required public dictionary contracts
└── vinuni_compass/
    ├── bootstrap.py           # Composition root; the only wiring location
    ├── settings.py            # Validated environment configuration
    ├── models.py              # Product-level request and stream types
    ├── corpus/                # Manifest -> reviewed Data Snapshot
    ├── indexing/              # Snapshot -> idempotent Chroma index
    ├── retrieval/             # Route -> dense + BM25 -> RRF -> fallback
    ├── assistant/             # Answer, citation, refusal, session context
    ├── providers/             # External-system adapters and their ports
    └── api/                   # HTTP adapter for Streamlit and Open WebUI
```

## External interfaces

The product exposes four main interfaces:

1. `CorpusBuilder.build()` creates a reviewed, reproducible Data Snapshot.
2. `IndexBuilder.build()` creates or refreshes the canonical retrieval index.
3. `RetrievalEngine.retrieve()` hides routing, dense retrieval, BM25, RRF, and
   PageIndex fallback behind one result contract.
4. `CompassAssistant.answer()` and `CompassAssistant.stream()` are the main
   application seam used by every UI and test.

The HTTP adapter exposes `/api/query` for structured clients and
`/v1/models` plus `/v1/chat/completions` for Open WebUI. It does not contain
retrieval or generation rules.

## Ownership proposal

| Workstream | Owns | Coordinates through |
| --- | --- | --- |
| Data | `corpus`, `indexing`, source manifest | Data Snapshot and index reports |
| Retrieval | `retrieval`, Chroma and PageIndex adapters | `RetrievalEngine.retrieve()` |
| Generation | `assistant`, OpenAI adapter | `CompassAssistant.answer/stream()` |
| Experience | `api`, Streamlit, Open WebUI setup | assistant interface and HTTP schemas |
| Evaluation | golden dataset, metrics, reports | public query interface only |

No workstream imports another workstream's private modules. Cross-workstream
changes happen through the public interfaces exported by each package.

## Testing seams

- Pure corpus and retrieval behavior is tested through its package interface.
- External providers are replaced with deterministic adapters in tests.
- End-to-end behavior is tested primarily through `CompassAssistant`.
- HTTP compatibility is tested through `/api/query` and
  `/v1/chat/completions`, including SSE streaming and `[DONE]` termination.
- The legacy course contract tests continue to call `task1` through `task10`.

## Dependency direction

```text
UI adapters -> CompassAssistant -> RetrievalEngine -> provider ports
                             \-> generation provider port

ingestion command -> CorpusBuilder -> IndexBuilder -> provider ports
```

`bootstrap` is the only module allowed to choose concrete provider adapters.
Domain behavior receives dependencies instead of constructing network clients.
