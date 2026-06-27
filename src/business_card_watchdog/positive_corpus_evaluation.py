from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .config import AppConfig
from .models import utc_now
from .preclassifier import read_image_dimensions


EVALUATION_MANIFEST_SCHEMA = "business-card-watchdog.positive-corpus-evaluation-manifest.v1"


def build_positive_corpus_evaluation_manifest(
    config: AppConfig,
    *,
    write: bool = True,
) -> dict[str, Any]:
    corpus_root = config.data_dir / "positive_control_corpus"
    index_path = corpus_root / "index.jsonl"
    rows, errors = _read_corpus_index(index_path)
    entries = [_evaluation_entry(row=row, corpus_root=corpus_root) for row in rows]
    entries.sort(key=lambda entry: (str(entry["group"]), str(entry["sha256"])))
    groups = _groups(entries)
    manifest_id = f"positive-corpus-evaluation-{utc_now().replace(':', '-')}-{_entries_digest(entries)}"
    manifest_path = corpus_root / "evaluation_manifests" / f"{manifest_id}.json"
    state = _state(entries=entries, errors=errors)
    payload: dict[str, Any] = {
        "schema": EVALUATION_MANIFEST_SCHEMA,
        "generated_at": utc_now(),
        "state": state,
        "manifest_id": manifest_id,
        "entry_count": len(entries),
        "groups": groups,
        "entries": entries,
        "errors": errors,
        "corpus_index_present": index_path.exists(),
        "corpus_root_redacted": True,
        "private_paths_redacted": True,
        "private_filenames_redacted": True,
        "stable_replay_order": [entry["entry_id"] for entry in entries],
        "files_inspected": len(entries),
        "ocr_attempted": 0,
        "pdfs_rasterized": 0,
        "crops_created": 0,
        "writes_attempted": 0,
        "network_calls_made": 0,
        "live_sink_calls_made": False,
        "public_web_search_used": False,
        "paid_enrichment_used": False,
        "runtime_artifact_written": False,
        "manifest_path": None,
        "commands": {
            "positive_corpus_evaluation_manifest": "positive-corpus-evaluation-manifest --json",
            "positive_corpus_evaluation_manifest_preview": "positive-corpus-evaluation-manifest --no-write --json",
        },
        "explicit_stop_conditions": [
            "This manifest summarizes operator-declared positive controls only.",
            "This surface does not OCR, crop, rasterize PDFs, enrich, route, or write contacts.",
            "Use this manifest for deterministic training/evaluation replay, not broad autodetection promotion.",
            "Do not commit runtime corpus manifests or private card artifacts to git.",
        ],
    }
    if write and state != "blocked":
        _ensure_runtime_output_not_repo(corpus_root)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        written_payload = payload | {
            "runtime_artifact_written": True,
            "manifest_path": str(manifest_path),
        }
        manifest_path.write_text(json.dumps(written_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        payload["runtime_artifact_written"] = True
        payload["manifest_path"] = str(manifest_path)
    return payload


def _read_corpus_index(index_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not index_path.exists():
        return [], [{"error": "positive control corpus index not found"}]
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for line_number, line in enumerate(index_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            errors.append({"line_number": line_number, "error": "invalid corpus index JSON"})
            continue
        if not isinstance(row, dict):
            errors.append({"line_number": line_number, "error": "corpus index row is not an object"})
            continue
        rows.append(row)
    return rows, errors


def _evaluation_entry(*, row: dict[str, Any], corpus_root: Path) -> dict[str, Any]:
    sha256 = str(row.get("sha256") or "")
    media_kind = str(row.get("media_kind") or "unknown")
    suffix = str(row.get("suffix") or "")
    blob_relpath = str(row.get("blob_relpath") or "")
    blob_path = corpus_root / blob_relpath
    metadata: dict[str, Any] = {}
    if media_kind == "pdf_document":
        page_count = _pdf_page_count(blob_path)
        metadata["page_count"] = page_count
        metadata["likely_front_back_sequence"] = page_count >= 2 and page_count % 2 == 0
        metadata["expected_pair_candidate_count"] = page_count // 2 if metadata["likely_front_back_sequence"] else 0
        group = "likely_front_back_sequence" if metadata["likely_front_back_sequence"] else "scanner_pdf_document"
    elif media_kind == "image":
        dimensions = read_image_dimensions(blob_path) if blob_path.exists() else None
        if dimensions is not None:
            metadata["dimensions"] = dimensions.to_dict()
            metadata["aspect_ratio"] = round(dimensions.aspect_ratio, 4)
        group = _image_group(metadata)
    else:
        group = "unsupported_or_unknown_media"
    return {
        "schema": "business-card-watchdog.positive-corpus-evaluation-entry.v1",
        "entry_id": str(row.get("entry_id") or f"positive-{sha256[:16]}"),
        "sha256": sha256,
        "media_kind": media_kind,
        "suffix": suffix,
        "size_bytes": int(row.get("size_bytes") or 0),
        "operator_declared_label": str(row.get("operator_declared_label") or ""),
        "group": group,
        "metadata": metadata,
        "blob_present": blob_path.exists(),
        "source_path_redacted": True,
        "source_filename_redacted": True,
    }


def _image_group(metadata: dict[str, Any]) -> str:
    dimensions = dict(metadata.get("dimensions") or {})
    if not dimensions:
        return "single_card_image_candidate"
    width = int(dimensions.get("width") or 0)
    height = int(dimensions.get("height") or 0)
    aspect_ratio = float(metadata.get("aspect_ratio") or 0.0)
    if aspect_ratio >= 2.05 or max(width, height) >= 2800:
        return "multi_card_image_candidate"
    return "single_card_image_candidate"


def _groups(entries: list[dict[str, Any]]) -> dict[str, Any]:
    group_names = [
        "single_card_image_candidate",
        "multi_card_image_candidate",
        "scanner_pdf_document",
        "likely_front_back_sequence",
        "unsupported_or_unknown_media",
    ]
    groups: dict[str, Any] = {}
    for group_name in group_names:
        members = [entry for entry in entries if entry["group"] == group_name]
        groups[group_name] = {
            "count": len(members),
            "entry_ids": [entry["entry_id"] for entry in members],
        }
    return groups


def _pdf_page_count(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        raw = path.read_bytes()
    except OSError:
        return 0
    count = len(re.findall(rb"/Type\s*/Page\b", raw))
    return max(1, count)


def _entries_digest(entries: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for entry in entries:
        digest.update(str(entry.get("sha256") or "").encode("utf-8"))
    return digest.hexdigest()[:12] if entries else "no-entries"


def _state(*, entries: list[dict[str, Any]], errors: list[dict[str, Any]]) -> str:
    if not entries:
        return "blocked"
    if errors:
        return "ready_with_index_errors"
    return "ready_for_positive_corpus_replay"


def _ensure_runtime_output_not_repo(output_root: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    try:
        output_root.resolve().relative_to(repo_root)
    except ValueError:
        return
    raise ValueError(f"positive corpus evaluation output root is inside the repo: {output_root}")
