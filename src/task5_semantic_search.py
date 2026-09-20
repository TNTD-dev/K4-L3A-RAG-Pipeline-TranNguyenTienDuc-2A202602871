"""
Task 5 — Semantic search.

Embed query bằng chính hàm của Task 4, query ChromaDB và đổi cosine distance
thành similarity. Output phải theo SearchResult, sort giảm dần và không quá top_k.
"""

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from .task4_chunking_indexing import embed_texts, get_collection


def semantic_search(query: str, top_k: int = 10) -> list[dict]:
    """Trả về dense SearchResult theo score giảm dần."""
    if top_k <= 0 or not query.strip():
        return []
    query_vector = embed_texts([query])[0]
    response = get_collection().query(
        query_embeddings=[query_vector], n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )
    rows = zip(
        (response.get("ids") or [[]])[0],
        (response.get("documents") or [[]])[0],
        (response.get("metadatas") or [[]])[0],
        (response.get("distances") or [[]])[0],
    )
    results: list[dict] = []
    seen: set[str] = set()
    for item_id, content, metadata, distance in rows:
        if not item_id or item_id in seen:
            continue
        seen.add(item_id)
        # Chroma's cosine distance is 1-cosine similarity.  Keep the original
        # score (without RRF) for the fallback threshold decision.
        results.append({
            "id": item_id, "content": content or "", "score": max(0.0, 1.0 - float(distance)),
            "metadata": metadata or {}, "retrieval_method": "dense",
        })
    return sorted(results, key=lambda item: (-item["score"], item["id"]))[:top_k]


if __name__ == "__main__":
    for result in semantic_search("test query", top_k=3):
        print(result)
