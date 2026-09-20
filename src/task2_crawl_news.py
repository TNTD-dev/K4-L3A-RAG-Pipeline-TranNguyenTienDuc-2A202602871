"""
Task 2 — Crawl bài viết/thông báo.

Hướng dẫn:
    1. Điền tối thiểu 5 URL công khai vào ARTICLE_URLS.
    2. Crawl từng URL bằng Crawl4AI.
    3. Lưu mỗi bài thành một JSON trong data/landing/news/.
    4. Giữ đủ url, title, date_crawled và content_markdown.

Cài browser trước khi chạy:
    python -m playwright install chromium
    
-> Dùng Firecrawl or bất cứ công cụ nào bạn quen    
"""

import asyncio
import json
from pathlib import Path
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.request import Request, urlopen


DATA_DIR = Path(__file__).parent.parent / "data" / "landing" / "news"

ARTICLE_URLS = [
    "https://admissions.vinuni.edu.vn/undergraduate/",
    "https://admissions.vinuni.edu.vn/scholarship-and-financial-aid/undergraduate-programs/scholarships/",
    "https://admissions.vinuni.edu.vn/tuition-fee/undergraduate/",
    "https://admissions.vinuni.edu.vn/tuition-fee-and-financial-support/",
    "https://admissions.vinuni.edu.vn/undergraduate/faqs/tuition-fee-scholarship-and-financial-aids/",
    "https://policy.vinuni.edu.vn/all-policies/academic-regulations-for-full-time-undergraduate-programs/",
    "https://policy.vinuni.edu.vn/all-policies/residential-life-guideline/",
    "https://policy.vinuni.edu.vn/all-policies/student-affairs-regulations-code-of-conduct/",
    "https://policy.vinuni.edu.vn/all-policies/internship-management-policy/",
    "https://policy.vinuni.edu.vn/all-policies/guidelines-for-student-financial-support-request/",
]


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.title: list[str] = []
        self.in_title = False
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "svg"}:
            self.skip += 1
        if tag == "title":
            self.in_title = True

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg"} and self.skip:
            self.skip -= 1
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.skip:
            return
        text = " ".join(data.split())
        if not text:
            return
        if self.in_title:
            self.title.append(text)
        self.parts.append(text)


async def crawl_article(url: str) -> dict:
    def fetch() -> dict:
        request = Request(url, headers={"User-Agent": "VinUniCompass/0.1 (public-source-audit)"})
        try:
            with urlopen(request, timeout=30) as response:
                html = response.read().decode("utf-8", errors="ignore")
        except Exception:
            # Some official properties challenge automated clients.  Jina's
            # read-only reader is used only as a transport fallback; the
            # allowlisted provenance URL remains the VinUniversity URL.
            proxy = "https://r.jina.ai/http://" + url.removeprefix("https://")
            with urlopen(Request(proxy, headers={"User-Agent": "VinUniCompass/0.1"}), timeout=45) as response:
                html = response.read().decode("utf-8", errors="ignore")
        parser = _TextExtractor()
        parser.feed(html)
        return {
            "url": url,
            "title": " ".join(parser.title) or url.rstrip("/").rsplit("/", 1)[-1],
            "date_crawled": datetime.now(timezone.utc).isoformat(),
            "content_markdown": "\n\n".join(parser.parts),
            "classification": "Public",
        }
    return await asyncio.to_thread(fetch)


async def crawl_all() -> None:
    """Crawl và lưu từng bài thành một file JSON."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    for index, url in enumerate(ARTICLE_URLS, 1):
        try:
            article = await crawl_article(url)
            output = DATA_DIR / f"article_{index:02d}.json"
            output.write_text(
                json.dumps(article, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"Saved: {output}")
        except Exception as error:
            print(f"Failed: {url} — {error}")


if __name__ == "__main__":
    asyncio.run(crawl_all())
