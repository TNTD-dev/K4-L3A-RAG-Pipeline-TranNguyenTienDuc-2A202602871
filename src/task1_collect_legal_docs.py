"""
Task 1 — Thu thập tài liệu chính sách/quy định.

Hướng dẫn:
    1. Chọn chủ đề của nhóm.
    2. Tìm tối thiểu 3 tài liệu PDF/DOCX từ nguồn công khai.
    3. Lưu file gốc vào data/landing/legal/.
    4. Đặt tên không dấu và thể hiện đúng nội dung.

Ví dụ tài liệu: học phí, học bổng, ký túc xá, quy trình đăng ký.
Nếu website chặn crawler, hãy chọn nguồn công khai khác; không vượt WAF.
"""

from pathlib import Path
import json
from urllib.request import Request, urlopen


DATA_DIR = Path(__file__).parent.parent / "data" / "landing" / "legal"


def setup_directory() -> None:
    """Tạo thư mục lưu tài liệu gốc."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Ready: {DATA_DIR}")


def download_documents() -> None:
    """Tải ít nhất 3 PDF/DOCX từ nguồn công khai."""
    manifest_path = DATA_DIR.parent.parent / "source_manifest.json"
    if not manifest_path.exists():
        print(f"Missing reviewed manifest: {manifest_path}")
        return
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for item in manifest:
        if item.get("content_type") not in {"pdf", "policy", "legal"}:
            continue
        target = DATA_DIR / f"{item['source_id']}.pdf"
        if target.exists() and target.stat().st_size > 1024:
            continue
        request = Request(item["url"], headers={"User-Agent": "VinUniCompass/0.1 (public-source-audit)"})
        try:
            with urlopen(request, timeout=60) as response:
                payload = response.read()
            if len(payload) <= 1024:
                raise ValueError("response is unexpectedly small")
            target.write_bytes(payload)
            print(f"Saved: {target}")
        except Exception as error:
            print(f"Failed: {item['url']} — {error}")


if __name__ == "__main__":
    setup_directory()
    download_documents()
