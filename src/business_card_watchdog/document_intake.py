from __future__ import annotations

import base64
import hashlib
import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DOCUMENT_SUFFIXES = {".pdf"}
_PLACEHOLDER_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAFgwJ/l8y2"
    "OQAAAABJRU5ErkJggg=="
)


@dataclass(frozen=True)
class DocumentPage:
    source_document_path: Path
    page_number: int
    page_image_path: Path
    rasterization_mode: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "business-card-watchdog.document-page.v1",
            "source_document_path": str(self.source_document_path),
            "page_number": self.page_number,
            "page_image_path": str(self.page_image_path),
            "media_kind": "page_image",
            "rasterization_mode": self.rasterization_mode,
            "sha256": _sha256(self.page_image_path),
        }


def is_supported_document(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in DOCUMENT_SUFFIXES


def materialize_document_pages(
    document_path: Path,
    output_root: Path,
    *,
    max_pages: int | None = None,
    dpi: int = 200,
) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    page_dir = output_root / _safe_stem(document_path)
    page_dir.mkdir(parents=True, exist_ok=True)
    pages = _rasterize_with_pdftoppm(document_path, page_dir, max_pages=max_pages, dpi=dpi)
    if not pages:
        pages = _materialize_placeholder_pages(document_path, page_dir, max_pages=max_pages)
    payload = {
        "schema": "business-card-watchdog.document-pages.v1",
        "source_document_path": str(document_path),
        "source_media_kind": "pdf_document",
        "page_count": len(pages),
        "pages": [page.to_dict() for page in pages],
        "writes_attempted": 0,
        "network_calls_made": 0,
    }
    manifest_path = page_dir / "document_pages.json"
    manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload | {"manifest_path": str(manifest_path)}


def build_source_page_artifact(page: dict[str, Any], *, job_id: str) -> dict[str, Any]:
    return {
        "schema": "business-card-watchdog.source-page.v1",
        "job_id": job_id,
        "source_document_path": page["source_document_path"],
        "page_number": page["page_number"],
        "page_image_path": page["page_image_path"],
        "media_kind": page["media_kind"],
        "rasterization_mode": page["rasterization_mode"],
        "sha256": page["sha256"],
    }


def build_card_side_candidate(page: dict[str, Any], *, job_id: str) -> dict[str, Any]:
    return {
        "schema": "business-card-watchdog.card-side-candidate.v1",
        "job_id": job_id,
        "source_document_path": page["source_document_path"],
        "page_number": page["page_number"],
        "page_image_path": page["page_image_path"],
        "side_label": "unknown",
        "confidence": "needs_ocr",
        "evidence": [
            {
                "kind": "scanner_page_lineage",
                "value": f"page:{page['page_number']}",
                "weight": "strong_hint",
            }
        ],
        "blocked_reason": "OCR side classification has not run for this page.",
    }


def _rasterize_with_pdftoppm(
    document_path: Path,
    page_dir: Path,
    *,
    max_pages: int | None,
    dpi: int,
) -> list[DocumentPage]:
    binary = shutil.which("pdftoppm")
    if not binary:
        return []
    prefix = page_dir / "page"
    command = [binary, "-png", "-r", str(max(50, dpi))]
    if max_pages is not None and max_pages > 0:
        command.extend(["-f", "1", "-l", str(max_pages)])
    command.extend([str(document_path), str(prefix)])
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return []
    paths = sorted(page_dir.glob("page-*.png"))
    return [
        DocumentPage(
            source_document_path=document_path,
            page_number=index,
            page_image_path=path,
            rasterization_mode="pdftoppm",
        )
        for index, path in enumerate(paths, start=1)
    ]


def _materialize_placeholder_pages(
    document_path: Path,
    page_dir: Path,
    *,
    max_pages: int | None,
) -> list[DocumentPage]:
    pages: list[DocumentPage] = []
    page_count = _pdf_page_count(document_path)
    if max_pages is not None and max_pages > 0:
        page_count = min(page_count, max_pages)
    for page_number in range(1, page_count + 1):
        page_path = page_dir / f"page-{page_number:04d}.png"
        page_path.write_bytes(_PLACEHOLDER_PNG)
        pages.append(
            DocumentPage(
                source_document_path=document_path,
                page_number=page_number,
                page_image_path=page_path,
                rasterization_mode="placeholder",
            )
        )
    return pages


def _pdf_page_count(path: Path) -> int:
    try:
        raw = path.read_bytes()
    except OSError:
        return 1
    count = len(re.findall(rb"/Type\s*/Page\b", raw))
    return max(1, count)


def _safe_stem(path: Path) -> str:
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "-", path.stem).strip(".-")
    return stem or "document"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
