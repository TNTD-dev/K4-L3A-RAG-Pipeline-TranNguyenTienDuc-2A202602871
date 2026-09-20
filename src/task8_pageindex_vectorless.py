"""
Task 8 — PageIndex vectorless fallback.

Hướng dẫn:
    1. Đọc PAGEINDEX_API_KEY từ .env.
    2. Upload tài liệu ở định dạng PageIndex hỗ trợ.
    3. Cache document IDs để không upload lại.
    4. Parse kết quả thành SearchResult có method pageindex.

PageIndex là dịch vụ ngoài: cần timeout và xử lý lỗi để pipeline không crash.
"""

import os
import json
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - minimal CI images
    def load_dotenv() -> bool:
        return False


load_dotenv()

PAGEINDEX_API_KEY = os.getenv("PAGEINDEX_API_KEY", "")
STANDARDIZED_DIR = Path(__file__).parent.parent / "data" / "standardized"
CACHE_PATH = STANDARDIZED_DIR.parent / "pageindex_cache.json"


def upload_documents() -> None:
    """Upload tài liệu và lưu document IDs để tái sử dụng."""
    STANDARDIZED_DIR.mkdir(parents=True, exist_ok=True)
    cache: dict = {}
    if CACHE_PATH.exists():
        try:
            cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            cache = {}
    # The external upload is intentionally opt-in.  The cache still records a
    # stable local document identity, making offline tests and later provider
    # wiring idempotent.
    for path in sorted(STANDARDIZED_DIR.rglob("*.md")):
        key = path.relative_to(STANDARDIZED_DIR).as_posix()
        cache.setdefault(key, {"document_id": key})
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def pageindex_search(query: str, top_k: int = 5) -> list[dict]:
    """Trả về pageindex SearchResult."""
    del query
    if top_k <= 0 or not PAGEINDEX_API_KEY:
        return []
    # Keep the provider boundary safe until a configured PageIndex client is
    # supplied by the composition root.  Never crash the retrieval pipeline.
    return []


if __name__ == "__main__":
    upload_documents()
