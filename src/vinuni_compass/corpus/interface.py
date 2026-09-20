"""Public corpus module interface."""

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from typing import Protocol


@dataclass(frozen=True, init=False)
class SourceManifestEntry:
    source_id: str
    title: str
    url: str
    mode: str
    classification: str
    policy_version: str | None = None
    effective_date: str | None = None
    content_type: str = "page"
    crawl_timestamp: str | None = None

    def __init__(
        self, source_id: str, title: str, url: str, mode: str,
        classification: str, version: str | None = None,
        effective_date: str | None = None, content_type: str = "page",
        crawl_timestamp: str | None = None, *, policy_version: str | None = None,
    ) -> None:
        """Accept both scaffold ``version`` and manifest ``policy_version``."""
        object.__setattr__(self, "source_id", source_id)
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "url", url)
        object.__setattr__(self, "mode", mode)
        object.__setattr__(self, "classification", classification)
        resolved = policy_version if policy_version is not None else version
        object.__setattr__(self, "policy_version", resolved)
        object.__setattr__(self, "effective_date", effective_date)
        object.__setattr__(self, "content_type", content_type)
        object.__setattr__(self, "crawl_timestamp", crawl_timestamp)

    @property
    def version(self) -> str | None:
        return self.policy_version


@dataclass(frozen=True)
class SnapshotReport:
    snapshot_id: str
    document_count: int
    output_directory: Path


class CorpusBuilder(Protocol):
    """Deep seam hiding download, validation, and standardization."""

    def build(self, manifest_path: Path) -> SnapshotReport: ...


PUBLIC_CLASSIFICATION = "Public"
OFFICIAL_HOST_SUFFIXES = ("vinuni.edu.vn", "vinuni.edu.vn.")


def _stable_id(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _clean_html(value: str) -> str:
    value = re.sub(r"<script[\s\S]*?</script>", " ", value, flags=re.I)
    value = re.sub(r"<style[\s\S]*?</style>", " ", value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def load_manifest(path: Path) -> list[SourceManifestEntry]:
    """Read and validate the reviewed JSON manifest.

    Reachability is not treated as public access: every entry must explicitly
    declare ``classification: Public`` and use a VinUniversity host.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("source manifest must be a JSON list")
    entries: list[SourceManifestEntry] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("manifest entries must be objects")
        required = ("source_id", "title", "url", "mode", "classification")
        if any(not str(item.get(key, "")).strip() for key in required):
            raise ValueError("manifest entry is missing a required field")
        if item["classification"] != PUBLIC_CLASSIFICATION:
            raise ValueError(f"non-Public source rejected: {item['source_id']}")
        host = urlparse(item["url"]).hostname or ""
        if not any(host == suffix or host.endswith("." + suffix) for suffix in OFFICIAL_HOST_SUFFIXES):
            raise ValueError(f"non-VinUniversity source rejected: {item['url']}")
        if item["source_id"] in seen:
            raise ValueError(f"duplicate source_id: {item['source_id']}")
        seen.add(item["source_id"])
        entries.append(SourceManifestEntry(
            source_id=str(item["source_id"]), title=str(item["title"]),
            url=str(item["url"]), mode=str(item["mode"]),
            classification=str(item["classification"]),
            policy_version=item.get("policy_version", item.get("version")),
            effective_date=item.get("effective_date"),
            content_type=str(item.get("content_type", "page")),
            crawl_timestamp=item.get("crawl_timestamp"),
        ))
    return entries


class FileCorpusBuilder:
    """Build a deterministic, provenance-preserving local Data Snapshot."""

    def __init__(self, output_directory: Path | None = None, timeout: int = 30) -> None:
        self.output_directory = output_directory or Path("data/standardized")
        self.timeout = timeout

    def build(self, manifest_path: Path) -> SnapshotReport:
        entries = load_manifest(manifest_path)
        self.output_directory.mkdir(parents=True, exist_ok=True)
        snapshot_payload = json.dumps([entry.__dict__ for entry in entries], sort_keys=True)
        snapshot_id = "snapshot-" + _stable_id(snapshot_payload)
        manifest_out = self.output_directory / "snapshot_manifest.json"
        manifest_out.write_text(snapshot_payload, encoding="utf-8")
        count = 0
        for entry in entries:
            content = self._fetch(entry)
            if not content.strip():
                raise ValueError(f"empty source: {entry.source_id}")
            mode_dir = "legal" if entry.content_type.lower() in {"pdf", "policy", "legal"} else "news"
            target = self.output_directory / mode_dir / f"{entry.source_id}.md"
            target.parent.mkdir(parents=True, exist_ok=True)
            metadata = {
                "source_id": entry.source_id, "source": entry.source_id,
                "title": entry.title, "doc_type": "legal" if mode_dir == "legal" else "news",
                "url": entry.url, "mode": entry.mode, "classification": entry.classification,
                "policy_version": entry.policy_version, "effective_date": entry.effective_date,
                "crawl_timestamp": entry.crawl_timestamp or datetime.now(timezone.utc).isoformat(),
            }
            header = "---\n" + "\n".join(f"{key}: {json.dumps(value, ensure_ascii=False)}" for key, value in metadata.items()) + "\n---\n\n"
            target.write_text(header + f"# {entry.title}\n\n" + content.strip() + "\n", encoding="utf-8")
            count += 1
        return SnapshotReport(snapshot_id=snapshot_id, document_count=count, output_directory=self.output_directory)

    def _fetch(self, entry: SourceManifestEntry) -> str:
        request = Request(entry.url, headers={"User-Agent": "VinUniCompass/0.1 (public-source-audit)"})
        with urlopen(request, timeout=self.timeout) as response:
            payload = response.read()
        if entry.content_type.lower() in {"pdf", "policy", "legal"} or entry.url.lower().endswith(".pdf"):
            try:
                from markitdown import MarkItDown
                import tempfile
                with tempfile.NamedTemporaryFile(suffix=".pdf") as handle:
                    handle.write(payload); handle.flush()
                    return MarkItDown().convert(handle.name).text_content
            except Exception:
                # A text fallback keeps ingestion usable in minimal CI images.
                return payload.decode("utf-8", errors="ignore")
        return _clean_html(payload.decode("utf-8", errors="ignore"))
