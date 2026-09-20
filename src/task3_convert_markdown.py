"""
Task 3 — Chuẩn hóa dữ liệu sang Markdown.

Hướng dẫn:
    1. Dùng MarkItDown để convert PDF/DOCX.
    2. Đọc JSON và giữ metadata ở đầu file Markdown.
    3. Giữ cấu trúc thư mục legal/ và news/.
    4. Không tạo file rỗng hoặc file trùng khi chạy lại.

Cài đặt:
    Dependency MarkItDown đã được khai báo trong pyproject.toml.
    
-> Hoặc dùng công cụ nào bạn quen khác Markitdown
"""

from pathlib import Path
import json
import re
import subprocess


LANDING_DIR = Path(__file__).parent.parent / "data" / "landing"
OUTPUT_DIR = Path(__file__).parent.parent / "data" / "standardized"


def _manifest_lookup() -> dict[str, dict]:
    path = LANDING_DIR.parent / "source_manifest.json"
    if not path.exists():
        return {}
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {str(item.get("source_id")): item for item in entries if isinstance(item, dict)}


def convert_legal_docs() -> None:
    legal_dir = LANDING_DIR / "legal"
    output_dir = OUTPUT_DIR / "legal"
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = _manifest_lookup()
    try:
        from markitdown import MarkItDown
        converter = MarkItDown()
    except Exception:
        converter = None
    for path in sorted(legal_dir.iterdir()):
        if path.suffix.lower() not in {".pdf", ".doc", ".docx"}:
            continue
        text = ""
        if converter is not None:
            try:
                text = converter.convert(str(path)).text_content
            except Exception:
                text = ""
        if not text:
            try:
                from pypdf import PdfReader
                text = "\n\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
            except Exception:
                try:
                    text = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True, check=True).stdout
                except Exception:
                    text = path.read_bytes().decode("utf-8", errors="ignore")
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        if text:
            target = output_dir / f"{path.stem}.md"
            item = manifest.get(path.stem, {})
            metadata = {
                "source_id": item.get("source_id", path.stem), "source": path.name,
                "title": item.get("title", path.stem), "doc_type": "legal",
                "url": item.get("url"), "mode": item.get("mode"),
                "classification": item.get("classification", "Public"),
                "policy_version": item.get("policy_version"),
                "effective_date": item.get("effective_date"),
                "crawl_timestamp": item.get("crawl_timestamp"),
            }
            header = "---\n" + "\n".join(f"{key}: {json.dumps(value, ensure_ascii=False)}" for key, value in metadata.items()) + "\n---\n\n"
            target.write_text(header + f"# {metadata['title']}\n\n{text}\n", encoding="utf-8")


def convert_news_articles() -> None:
    news_dir = LANDING_DIR / "news"
    output_dir = OUTPUT_DIR / "news"
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_by_url = {item.get("url"): item for item in _manifest_lookup().values()}
    for path in sorted(news_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        content = str(data.get("content_markdown", "")).strip()
        if not content:
            continue
        metadata = {
            "source_id": manifest_by_url.get(data.get("url"), {}).get("source_id", path.stem),
            "source": path.name, "title": data.get("title", path.stem),
            "doc_type": "news", "url": data.get("url"),
            "crawl_timestamp": data.get("date_crawled"),
        }
        item = manifest_by_url.get(data.get("url"), {})
        metadata.update({
            "mode": item.get("mode"), "classification": data.get("classification", item.get("classification", "Public")),
            "policy_version": item.get("policy_version"), "effective_date": item.get("effective_date"),
        })
        header = "---\n" + "\n".join(f"{key}: {json.dumps(value, ensure_ascii=False)}" for key, value in metadata.items()) + "\n---\n\n"
        (output_dir / f"{path.stem}.md").write_text(header + f"# {metadata['title']}\n\n" + content + "\n", encoding="utf-8")


def convert_all() -> None:
    """Convert toàn bộ dữ liệu landing."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    convert_legal_docs()
    convert_news_articles()
    print(f"Saved Markdown to: {OUTPUT_DIR}")


if __name__ == "__main__":
    convert_all()
