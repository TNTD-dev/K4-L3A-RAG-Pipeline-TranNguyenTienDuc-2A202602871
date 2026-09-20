"""
Task 6 — Lexical search bằng BM25.

Dùng cùng corpus chunks với Task 5. BM25 phù hợp với từ khóa chính xác, mã tài
liệu và tên riêng. Output phải theo SearchResult và sort score giảm dần.
"""


CORPUS: list[dict] = []


def _tokens(text: str) -> list[str]:
    return [token.casefold() for token in __import__("re").findall(r"[\wÀ-ỹ]+", text)]


def build_bm25_index(corpus: list[dict]):
    """Tạo BM25 index từ cùng corpus chunks của Task 4."""
    tokenized = [_tokens(item.get("content", "")) for item in corpus]
    try:
        from rank_bm25 import BM25Okapi
        return BM25Okapi(tokenized)
    except Exception:
        class SimpleBM25:
            def __init__(self, rows):
                self.rows = rows
                self.avgdl = sum(map(len, rows)) / max(len(rows), 1)

            def get_scores(self, query_tokens):
                import math
                n = len(self.rows)
                doc_freq = {}
                for row in self.rows:
                    for token in set(row):
                        doc_freq[token] = doc_freq.get(token, 0) + 1
                scores = []
                for row in self.rows:
                    length = len(row) or 1
                    value = 0.0
                    for token in query_tokens:
                        tf = row.count(token)
                        if not tf:
                            continue
                        idf = math.log((n - doc_freq.get(token, 0) + 0.5) / (doc_freq.get(token, 0) + 0.5) + 1)
                        value += idf * (tf * 2.5) / (tf + 1.5 * (0.25 + 0.75 * length / max(self.avgdl, 1)))
                    scores.append(value)
                return scores
        return SimpleBM25(tokenized)


def lexical_search(query: str, top_k: int = 10) -> list[dict]:
    """Trả về BM25 SearchResult theo score giảm dần."""
    global CORPUS
    if not CORPUS:
        # Lazy loading keeps standalone task6 usage useful while preserving
        # the shared canonical chunk corpus once task4 has indexed it.
        try:
            from .task4_chunking_indexing import chunk_documents, load_documents
            CORPUS = chunk_documents(load_documents())
        except Exception:
            CORPUS = []
    if top_k <= 0 or not CORPUS or not query.strip():
        return []
    bm25 = build_bm25_index(CORPUS)
    scores = list(map(float, bm25.get_scores(_tokens(query))))
    ranked = sorted(range(len(CORPUS)), key=lambda i: (-scores[i], CORPUS[i].get("id", "")))
    results: list[dict] = []
    seen: set[str] = set()
    for index in ranked:
        if scores[index] <= 0:
            continue
        item = CORPUS[index]
        if item["id"] in seen:
            continue
        seen.add(item["id"])
        results.append({**item, "score": scores[index], "retrieval_method": "bm25"})
        if len(results) >= top_k:
            break
    return results


if __name__ == "__main__":
    for result in lexical_search("test query", top_k=3):
        print(result)
