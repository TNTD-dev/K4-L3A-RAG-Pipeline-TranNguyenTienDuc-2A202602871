# VinUni Compass foundation and Data Snapshot

The reviewed allowlist is `data/source_manifest.json`. It contains only
VinUniversity-hosted URLs with an explicit `classification` of `Public`.
Every entry records a stable `source_id`, title, URL, mode, Policy Version,
effective date, crawl timestamp, and content type. Internal rows are rejected
by `load_manifest()` even when their URLs are reachable.

## Rebuild the snapshot

```bash
python -m src.task1_collect_legal_docs
python -m src.task2_crawl_news
python -m src.task3_convert_markdown
python -m src.task4_chunking_indexing
```

The landing corpus is kept in `data/landing/{legal,news}` and standardized
Markdown in `data/standardized/{legal,news}`. Markdown front matter preserves
source URL, mode, classification, Policy Version, effective date, and crawl
timestamp. Refresh is explicit; the application never recrawls at startup.

## Interfaces and offline fixtures

`src/vinuni_compass/bootstrap.py` is the single composition root. Downstream
workstreams depend on these seams rather than constructing provider clients:

- `CorpusBuilder.build(manifest_path)` returns a deterministic `SnapshotReport`.
- `IndexBuilder.build(snapshot_directory)` returns an `IndexReport` and upserts
  stable chunk IDs.
- `RetrievalEngine.retrieve(...)` returns the shared `SearchResult` contract.
- `CompassAssistant.answer()` and `.stream()` are the UI-independent answer
  seam.

`src/vinuni_compass/providers/test_adapters.py` exports deterministic embedding,
vector-store, PageIndex, and generation adapters. They require no network or
secret, preserve ordering, and use the same 1,536-dimensional shape as
`text-embedding-3-small`. OpenAI embeddings are used when an API key is
explicitly configured; offline runs automatically use the deterministic
adapter.

The Chroma collection metadata treats `embedding_model` and `dimension` as
invariants. Upsert is by stable ID, so repeating the same snapshot replaces
rows rather than increasing unique chunk count.
