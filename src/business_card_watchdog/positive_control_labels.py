from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .config import AppConfig
from .models import utc_now
from .preclassifier import read_image_dimensions


POSITIVE_CONTROL_LABEL_INVENTORY_SCHEMA = "business-card-watchdog.positive-control-label-inventory.v1"


def build_positive_control_label_inventory(config: AppConfig, *, write: bool = True) -> dict[str, Any]:
    corpus_root = config.data_dir / "positive_control_corpus"
    rows, errors = _read_corpus_index(corpus_root / "index.jsonl")
    entries = [_inventory_entry(row=row, corpus_root=corpus_root) for row in rows]
    entries.sort(key=lambda entry: (str(entry["source_kind"]), str(entry["sha256"])))
    inventory_id = f"positive-control-label-inventory-{utc_now().replace(':', '-')}-{_entries_digest(entries)}"
    inventory_path = corpus_root / "label_inventories" / f"{inventory_id}.json"
    missing_label_report = _missing_label_report(entries)
    state = _state(entries=entries, errors=errors)
    payload: dict[str, Any] = {
        "schema": POSITIVE_CONTROL_LABEL_INVENTORY_SCHEMA,
        "generated_at": utc_now(),
        "state": state,
        "inventory_id": inventory_id,
        "entry_count": len(entries),
        "entries": entries,
        "stable_replay_order": [entry["entry_id"] for entry in entries],
        "group_summary": _group_summary(entries),
        "missing_label_report": missing_label_report,
        "training_promotion_allowed": missing_label_report["missing_label_count"] == 0 and state != "blocked",
        "known_card_crop_ocr_allowed": state != "blocked",
        "errors": errors,
        "corpus_index_present": (corpus_root / "index.jsonl").exists(),
        "private_paths_redacted": True,
        "private_filenames_redacted": True,
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
        "inventory_path": None,
        "commands": {
            "positive_control_label_inventory": "positive-control-label-inventory --json",
            "positive_control_label_inventory_preview": "positive-control-label-inventory --no-write --json",
        },
        "explicit_stop_conditions": [
            "This inventory summarizes operator-declared positive controls only.",
            "This inventory does not OCR, crop, rasterize PDFs, enrich, route, or write contacts.",
            "Missing labels block training promotion, not known-card crop/OCR work.",
            "Do not commit runtime label inventories or private card artifacts to git.",
        ],
    }
    if write and state != "blocked":
        _ensure_runtime_output_not_repo(corpus_root)
        inventory_path.parent.mkdir(parents=True, exist_ok=True)
        written_payload = payload | {
            "runtime_artifact_written": True,
            "inventory_path": str(inventory_path),
        }
        inventory_path.write_text(json.dumps(written_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        payload["runtime_artifact_written"] = True
        payload["inventory_path"] = str(inventory_path)
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


def _inventory_entry(*, row: dict[str, Any], corpus_root: Path) -> dict[str, Any]:
    sha256 = str(row.get("sha256") or "")
    media_kind = str(row.get("media_kind") or "unknown")
    suffix = str(row.get("suffix") or "")
    blob_relpath = str(row.get("blob_relpath") or "")
    blob_path = corpus_root / blob_relpath
    base: dict[str, Any] = {
        "schema": "business-card-watchdog.positive-control-label-inventory-entry.v1",
        "entry_id": str(row.get("entry_id") or f"positive-{sha256[:16]}"),
        "sha256": sha256,
        "sha256_prefix": sha256[:12],
        "media_kind": media_kind,
        "suffix": suffix,
        "size_bytes": int(row.get("size_bytes") or 0),
        "operator_declared_label": str(row.get("operator_declared_label") or ""),
        "blob_present": blob_path.exists(),
        "source_path_redacted": True,
        "source_filename_redacted": True,
    }
    if media_kind == "pdf_document":
        return base | _pdf_labels(blob_path)
    if media_kind == "image":
        return base | _image_labels(blob_path)
    return base | {
        "source_kind": "unsupported_or_unknown_media",
        "capture_mode": "unknown",
        "card_count_label": "unknown",
        "orientation_label": "unknown",
        "front_back_expectation": "unknown",
        "blank_back_expectation": "unknown",
        "page_count": 0,
        "page_labels": [],
        "scenario_labels": {},
        "missing_labels": ["source_kind", "capture_mode", "card_count", "orientation", "front_back_expectation"],
    }


def _pdf_labels(blob_path: Path) -> dict[str, Any]:
    page_count = _pdf_page_count(blob_path)
    likely_sequence = page_count >= 2 and page_count % 2 == 0
    source_kind = "scanner_pdf_front_back_sequence_candidate" if likely_sequence else "scanner_pdf_document"
    front_back_expectation = (
        "likely_adjacent_front_back_sequence_order_unknown"
        if likely_sequence
        else "front_back_expectation_unknown"
    )
    missing = ["front_back_order", "page_orientation"]
    if not likely_sequence:
        missing.append("front_back_pairing")
    return {
        "source_kind": source_kind,
        "capture_mode": "scanner_pdf",
        "card_count_label": "one_card_per_page_expected",
        "orientation_label": "pdf_page_orientation_unknown",
        "front_back_expectation": front_back_expectation,
        "blank_back_expectation": "possible_dropped_or_blank_back",
        "page_count": page_count,
        "expected_pair_candidate_count": page_count // 2 if likely_sequence else 0,
        "page_labels": _pdf_page_labels(page_count=page_count, likely_sequence=likely_sequence),
        "scenario_labels": {
            "source_kind": source_kind,
            "capture_mode": "scanner_pdf",
            "front_back_order": "unknown",
            "supports_front_first": likely_sequence,
            "supports_back_first": likely_sequence,
            "supports_dropped_blank_back": True,
            "multi_card_image": False,
        },
        "missing_labels": missing,
    }


def _pdf_page_labels(*, page_count: int, likely_sequence: bool) -> list[dict[str, Any]]:
    labels: list[dict[str, Any]] = []
    for page_number in range(1, page_count + 1):
        pair_slot = (page_number + 1) // 2 if likely_sequence else None
        labels.append(
            {
                "page_number": page_number,
                "page_kind": "business_card_side_candidate",
                "side_expectation": "front_or_back_unknown" if likely_sequence else "unknown",
                "pair_slot": pair_slot,
                "front_back_order": "unknown",
                "blank_back_possible": True,
            }
        )
    return labels


def _image_labels(blob_path: Path) -> dict[str, Any]:
    dimensions = read_image_dimensions(blob_path) if blob_path.exists() else None
    metadata: dict[str, Any] = {}
    if dimensions is not None:
        metadata["dimensions"] = dimensions.to_dict()
        metadata["aspect_ratio"] = round(dimensions.aspect_ratio, 4)
    card_count_label = _image_card_count_label(metadata)
    orientation = _image_orientation_label(metadata)
    source_kind = "multi_card_image_candidate" if card_count_label == "multi_card_candidate" else "single_card_image_candidate"
    missing = ["capture_mode"]
    if orientation == "unknown":
        missing.append("orientation")
    return {
        "source_kind": source_kind,
        "capture_mode": "camera_or_scanner_image_unknown",
        "card_count_label": card_count_label,
        "orientation_label": orientation,
        "front_back_expectation": "single_side_or_composite_image_unknown",
        "blank_back_expectation": "not_applicable_to_single_image",
        "page_count": 1,
        "image_metadata": metadata,
        "page_labels": [
            {
                "page_number": 1,
                "page_kind": source_kind,
                "side_expectation": "front_or_back_or_composite_unknown",
                "pair_slot": None,
                "front_back_order": "unknown",
                "blank_back_possible": False,
            }
        ],
        "scenario_labels": {
            "source_kind": source_kind,
            "capture_mode": "camera_or_scanner_image_unknown",
            "front_back_order": "not_applicable",
            "supports_front_first": False,
            "supports_back_first": False,
            "supports_dropped_blank_back": False,
            "multi_card_image": card_count_label == "multi_card_candidate",
        },
        "missing_labels": missing,
    }


def _image_card_count_label(metadata: dict[str, Any]) -> str:
    dimensions = dict(metadata.get("dimensions") or {})
    if not dimensions:
        return "single_card_candidate"
    width = int(dimensions.get("width") or 0)
    height = int(dimensions.get("height") or 0)
    aspect_ratio = float(metadata.get("aspect_ratio") or 0.0)
    if aspect_ratio >= 2.05 or max(width, height) >= 2800:
        return "multi_card_candidate"
    return "single_card_candidate"


def _image_orientation_label(metadata: dict[str, Any]) -> str:
    dimensions = dict(metadata.get("dimensions") or {})
    if not dimensions:
        return "unknown"
    width = int(dimensions.get("width") or 0)
    height = int(dimensions.get("height") or 0)
    if width > height:
        return "landscape"
    if height > width:
        return "portrait"
    return "square"


def _pdf_page_count(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        raw = path.read_bytes()
    except OSError:
        return 0
    count = len(re.findall(rb"/Type\s*/Page\b", raw))
    return max(1, count)


def _group_summary(entries: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, dict[str, Any]] = {}
    for entry in entries:
        group = str(entry.get("source_kind") or "unknown")
        bucket = groups.setdefault(group, {"count": 0, "entry_ids": []})
        bucket["count"] += 1
        bucket["entry_ids"].append(entry.get("entry_id"))
    return dict(sorted(groups.items()))


def _missing_label_report(entries: list[dict[str, Any]]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    label_counts: dict[str, int] = {}
    for entry in entries:
        missing = [str(label) for label in list(entry.get("missing_labels") or [])]
        if not missing:
            continue
        for label in missing:
            label_counts[label] = label_counts.get(label, 0) + 1
        items.append(
            {
                "entry_id": entry.get("entry_id"),
                "sha256_prefix": entry.get("sha256_prefix"),
                "source_kind": entry.get("source_kind"),
                "missing_labels": missing,
                "effect": "blocks_training_promotion_only",
            }
        )
    return {
        "missing_label_count": len(items),
        "missing_label_counts": dict(sorted(label_counts.items())),
        "items": items,
        "blocks_known_card_crop_ocr": False,
        "blocks_training_promotion": bool(items),
    }


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
    return "training_inventory_ready"


def _ensure_runtime_output_not_repo(output_root: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    try:
        output_root.resolve().relative_to(repo_root)
    except ValueError:
        return
    raise ValueError(f"positive control label inventory output root is inside the repo: {output_root}")
