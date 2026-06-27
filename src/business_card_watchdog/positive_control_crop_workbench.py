from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .config import AppConfig
from .document_intake import materialize_document_pages
from .models import utc_now
from .positive_control_labels import build_positive_control_label_inventory
from .positive_control_scenarios import build_positive_control_scenario_manifest
from .preclassifier import assess_business_card_candidate


POSITIVE_CONTROL_CROP_WORKBENCH_SCHEMA = "business-card-watchdog.positive-control-crop-workbench.v1"
CROP_CANDIDATE_SCHEMA = "business-card-watchdog.positive-control-crop-candidate.v1"


def build_positive_control_crop_workbench(config: AppConfig, *, write: bool = True) -> dict[str, Any]:
    corpus_root = config.data_dir / "positive_control_corpus"
    index_rows, errors = _read_corpus_index(corpus_root / "index.jsonl")
    row_by_entry_id = {
        str(row.get("entry_id") or f"positive-{str(row.get('sha256') or '')[:16]}"): row
        for row in index_rows
    }
    label_inventory = build_positive_control_label_inventory(config, write=False)
    scenario_manifest = build_positive_control_scenario_manifest(config, write=False)
    entries = [entry for entry in list(label_inventory.get("entries") or []) if isinstance(entry, dict)]
    workbench_id = f"positive-control-crop-workbench-{utc_now().replace(':', '-')}-{_entries_digest(entries)}"
    workbench_dir = corpus_root / "crop_workbenches" / workbench_id
    candidate_dir = workbench_dir / "crop_candidates"
    page_dir = workbench_dir / "document_pages"
    report_path = workbench_dir / "crop_workbench.json"
    source_results = [
        _evaluate_entry(
            entry=entry,
            row=row_by_entry_id.get(str(entry.get("entry_id") or ""), {}),
            corpus_root=corpus_root,
            candidate_dir=candidate_dir,
            page_dir=page_dir,
            write=write,
        )
        for entry in entries
    ]
    source_results.sort(key=lambda row: (str(row.get("source_kind") or ""), str(row.get("entry_id") or "")))
    crop_candidates = [
        candidate
        for source in source_results
        for unit in list(source.get("processing_units") or [])
        if isinstance(unit, dict)
        for candidate in list(unit.get("crop_candidates") or [])
        if isinstance(candidate, dict)
    ]
    review_requests = [
        request
        for source in source_results
        for unit in list(source.get("processing_units") or [])
        if isinstance(unit, dict)
        for request in list(unit.get("review_requests") or [])
        if isinstance(request, dict)
    ]
    counts = _counts(
        entries=entries,
        source_results=source_results,
        crop_candidates=crop_candidates,
        review_requests=review_requests,
        errors=errors,
    )
    state = _state(entries=entries, errors=errors)
    payload: dict[str, Any] = {
        "schema": POSITIVE_CONTROL_CROP_WORKBENCH_SCHEMA,
        "generated_at": utc_now(),
        "state": state if write else ("ready_for_runtime_crop_workbench" if state != "blocked" else "blocked"),
        "workbench_id": workbench_id,
        "label_inventory_state": label_inventory.get("state"),
        "scenario_manifest_state": scenario_manifest.get("state"),
        "scenario_count": int(scenario_manifest.get("scenario_count") or 0),
        "source_count": len(entries),
        "source_results": source_results,
        "counts": counts,
        "review_requests": review_requests,
        "errors": errors,
        "private_paths_redacted": True,
        "private_filenames_redacted": True,
        "operator_declared_known_positive_only": True,
        "broad_autodetection_promoted": False,
        "contacts_review_required": True,
        "dry_run": True,
        "ocr_attempted": 0,
        "pdfs_rasterized": counts["pdf_pages_materialized"],
        "crops_created": counts["crop_candidate_count"],
        "writes_attempted": 0,
        "network_calls_made": 0,
        "live_sink_calls_made": False,
        "public_web_search_used": False,
        "paid_enrichment_used": False,
        "runtime_artifact_written": False,
        "report_path": None,
        "candidate_artifact_dir": str(candidate_dir) if write and state != "blocked" else None,
        "commands": {
            "positive_control_crop_workbench": "positive-control-crop-workbench --json",
            "positive_control_crop_workbench_preview": "positive-control-crop-workbench --no-write --json",
            "positive_control_recognition_training": "positive-control-recognition-training-replay --no-write --json",
        },
        "explicit_stop_conditions": [
            "This workbench evaluates operator-declared positive controls only.",
            "This workbench generates crop-candidate evidence, not contact drafts.",
            "This workbench does not OCR, enrich, route, write contacts, read back sinks, search public web, or call paid providers.",
            "Crop candidate artifacts must remain under user-scoped runtime storage and must not be committed to git.",
            "Low-confidence crop choices require review or App Intelligence evidence before OCR/contact extraction.",
        ],
    }
    if write and state != "blocked":
        _ensure_runtime_output_not_repo(corpus_root)
        workbench_dir.mkdir(parents=True, exist_ok=True)
        report_payload = payload | {
            "runtime_artifact_written": True,
            "report_path": str(report_path),
        }
        report_path.write_text(json.dumps(report_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        payload["runtime_artifact_written"] = True
        payload["report_path"] = str(report_path)
    return payload


def _evaluate_entry(
    *,
    entry: dict[str, Any],
    row: dict[str, Any],
    corpus_root: Path,
    candidate_dir: Path,
    page_dir: Path,
    write: bool,
) -> dict[str, Any]:
    entry_id = str(entry.get("entry_id") or "")
    media_kind = str(entry.get("media_kind") or "")
    blob_path = corpus_root / str(row.get("blob_relpath") or "")
    result: dict[str, Any] = {
        "entry_id": entry_id,
        "sha256_prefix": entry.get("sha256_prefix"),
        "source_kind": entry.get("source_kind"),
        "media_kind": media_kind,
        "card_count_label": entry.get("card_count_label"),
        "processing_units": [],
        "state": "pending",
        "source_path_redacted": True,
        "source_filename_redacted": True,
    }
    if not blob_path.exists():
        result["state"] = "missing_blob"
        return result
    if media_kind == "image":
        result["processing_units"] = [
            _evaluate_image_unit(
                image_path=blob_path,
                entry=entry,
                unit_id=f"{entry_id}-image-001",
                page_number=None,
                page_role="front_or_back_or_composite_unknown",
                candidate_dir=candidate_dir,
                write=write,
            )
        ]
    elif media_kind == "pdf_document":
        result["processing_units"] = _evaluate_pdf_units(
            pdf_path=blob_path,
            entry=entry,
            candidate_dir=candidate_dir,
            page_dir=page_dir,
            write=write,
        )
    else:
        result["state"] = "unsupported_media_kind"
        return result
    states = {str(unit.get("state") or "") for unit in list(result["processing_units"] or []) if isinstance(unit, dict)}
    if "crop_review_required" in states:
        result["state"] = "crop_review_required"
    elif "crop_candidates_ready" in states:
        result["state"] = "crop_candidates_ready"
    else:
        result["state"] = "no_crop_candidates"
    return result


def _evaluate_pdf_units(
    *,
    pdf_path: Path,
    entry: dict[str, Any],
    candidate_dir: Path,
    page_dir: Path,
    write: bool,
) -> list[dict[str, Any]]:
    entry_id = str(entry.get("entry_id") or "")
    page_labels = [label for label in list(entry.get("page_labels") or []) if isinstance(label, dict)]
    if not write:
        return [
            {
                "unit_id": f"{entry_id}-page-{int(label.get('page_number') or 0):03d}",
                "media_kind": "pdf_page",
                "page_number": label.get("page_number"),
                "page_role": label.get("side_expectation") or "front_or_back_unknown",
                "state": "requires_runtime_page_materialization",
                "crop_candidates": [],
                "review_requests": [],
                "source_path_redacted": True,
                "source_filename_redacted": True,
            }
            for label in page_labels
        ]
    document_manifest = materialize_document_pages(pdf_path, page_dir / entry_id, dpi=150)
    units: list[dict[str, Any]] = []
    for page in list(document_manifest.get("pages") or []):
        if not isinstance(page, dict):
            continue
        page_number = int(page.get("page_number") or 0)
        units.append(
            _evaluate_image_unit(
                image_path=Path(str(page.get("page_image_path") or "")),
                entry=entry,
                unit_id=f"{entry_id}-page-{page_number:03d}",
                page_number=page_number,
                page_role=_page_role(entry=entry, page_number=page_number),
                candidate_dir=candidate_dir,
                write=write,
            )
        )
    return units


def _evaluate_image_unit(
    *,
    image_path: Path,
    entry: dict[str, Any],
    unit_id: str,
    page_number: int | None,
    page_role: str,
    candidate_dir: Path,
    write: bool,
) -> dict[str, Any]:
    source_kind = str(entry.get("source_kind") or "")
    assessment = assess_business_card_candidate(image_path)
    assessment_payload = assessment.to_dict()
    boxes = _candidate_boxes(assessment_payload=assessment_payload, source_kind=source_kind)
    crop_candidates = [
        _crop_candidate(
            entry=entry,
            unit_id=unit_id,
            page_number=page_number,
            page_role=page_role,
            box=box,
            index=index,
            source_kind=source_kind,
            assessment_payload=assessment_payload,
            candidate_dir=candidate_dir,
            write=write,
        )
        for index, box in enumerate(boxes, start=1)
    ]
    review_requests = _review_requests(
        unit_id=unit_id,
        entry=entry,
        source_kind=source_kind,
        page_number=page_number,
        page_role=page_role,
        crop_candidates=crop_candidates,
        assessment_payload=assessment_payload,
    )
    state = "crop_candidates_ready" if crop_candidates and not review_requests else "crop_review_required"
    return {
        "unit_id": unit_id,
        "media_kind": "pdf_page" if page_number is not None else "image",
        "page_number": page_number,
        "page_role": page_role,
        "state": state,
        "source_kind": source_kind,
        "classifier_decision": assessment_payload.get("decision"),
        "classifier_score": float(assessment_payload.get("score") or 0.0),
        "analyzer_summary": _analyzer_summary(assessment_payload),
        "crop_candidates": crop_candidates,
        "review_requests": review_requests,
        "source_path_redacted": True,
        "source_filename_redacted": True,
    }


def _candidate_boxes(*, assessment_payload: dict[str, Any], source_kind: str) -> list[dict[str, Any]]:
    analyzers = dict(assessment_payload.get("analyzers") or {})
    rectangle = dict(analyzers.get("opencv_rectangle") or {})
    boxes = [box for box in list(rectangle.get("boxes") or []) if isinstance(box, dict)]
    if boxes:
        return boxes[:8] if source_kind == "multi_card_image_candidate" else boxes[:1]
    dimensions = dict(assessment_payload.get("dimensions") or {})
    aspect = dict(analyzers.get("aspect_ratio") or {})
    if source_kind != "multi_card_image_candidate" and dimensions and float(aspect.get("score") or 0.0) > 0:
        return [
            {
                "x": 0,
                "y": 0,
                "width": int(dimensions.get("width") or 0),
                "height": int(dimensions.get("height") or 0),
                "area_fraction": 1.0,
                "ratio": round(float(aspect.get("ratio") or 0.0), 4),
                "fallback": "full_frame_card_aspect",
            }
        ]
    return []


def _crop_candidate(
    *,
    entry: dict[str, Any],
    unit_id: str,
    page_number: int | None,
    page_role: str,
    box: dict[str, Any],
    index: int,
    source_kind: str,
    assessment_payload: dict[str, Any],
    candidate_dir: Path,
    write: bool,
) -> dict[str, Any]:
    candidate_id = f"{unit_id}-crop-{index:03d}"
    quality = _quality_metrics(box=box, assessment_payload=assessment_payload)
    state = "accepted_for_ocr_workbench" if quality["ocr_readiness"] == "ready" else "review_required"
    artifact_path = candidate_dir / f"{candidate_id}.json"
    candidate: dict[str, Any] = {
        "schema": CROP_CANDIDATE_SCHEMA,
        "candidate_id": candidate_id,
        "unit_id": unit_id,
        "entry_id": entry.get("entry_id"),
        "sha256_prefix": entry.get("sha256_prefix"),
        "source_kind": source_kind,
        "media_kind": "pdf_page" if page_number is not None else "image",
        "page_number": page_number,
        "page_role": page_role,
        "candidate_kind": "child_card_candidate" if source_kind == "multi_card_image_candidate" else "primary_card_candidate",
        "box": {
            "x": int(box.get("x") or 0),
            "y": int(box.get("y") or 0),
            "width": int(box.get("width") or 0),
            "height": int(box.get("height") or 0),
        },
        "quality": quality,
        "state": state,
        "artifact_path": str(artifact_path) if write else None,
        "requires_review": state != "accepted_for_ocr_workbench",
        "requires_app_intelligence": state != "accepted_for_ocr_workbench",
        "source_path_redacted": True,
        "source_filename_redacted": True,
    }
    if write:
        candidate_dir.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(json.dumps(candidate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return candidate


def _quality_metrics(*, box: dict[str, Any], assessment_payload: dict[str, Any]) -> dict[str, Any]:
    analyzers = dict(assessment_payload.get("analyzers") or {})
    rectangle = dict(analyzers.get("opencv_rectangle") or {})
    aspect_ratio = float(box.get("ratio") or 0.0)
    area_fraction = float(box.get("area_fraction") or 0.0)
    contour_confidence = float(rectangle.get("score") or 0.0)
    if box.get("fallback") == "full_frame_card_aspect":
        contour_confidence = max(contour_confidence, 0.35)
    edge_completeness = min(1.0, max(0.0, area_fraction / 0.04)) if area_fraction < 0.04 else 1.0
    ocr_ready = contour_confidence >= 0.55 or box.get("fallback") == "full_frame_card_aspect"
    return {
        "aspect_ratio": round(aspect_ratio, 4),
        "contour_confidence": round(contour_confidence, 4),
        "edge_completeness": round(edge_completeness, 4),
        "skew_rotation_estimate_degrees": 0,
        "size": {
            "width": int(box.get("width") or 0),
            "height": int(box.get("height") or 0),
            "area_fraction": round(area_fraction, 4),
        },
        "ocr_readiness": "ready" if ocr_ready else "needs_review",
    }


def _review_requests(
    *,
    unit_id: str,
    entry: dict[str, Any],
    source_kind: str,
    page_number: int | None,
    page_role: str,
    crop_candidates: list[dict[str, Any]],
    assessment_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    requests: list[dict[str, Any]] = []
    low_confidence_candidates = [
        candidate for candidate in crop_candidates if candidate.get("requires_review") is True
    ]
    if not crop_candidates:
        requests.append(
            _review_request(
                unit_id=unit_id,
                entry=entry,
                source_kind=source_kind,
                page_number=page_number,
                page_role=page_role,
                reason="no_plausible_crop_candidate",
                assessment_payload=assessment_payload,
            )
        )
    elif low_confidence_candidates:
        requests.append(
            _review_request(
                unit_id=unit_id,
                entry=entry,
                source_kind=source_kind,
                page_number=page_number,
                page_role=page_role,
                reason="low_confidence_crop_candidate",
                assessment_payload=assessment_payload,
            )
        )
    if source_kind == "multi_card_image_candidate" and len(crop_candidates) <= 1:
        requests.append(
            _review_request(
                unit_id=unit_id,
                entry=entry,
                source_kind=source_kind,
                page_number=page_number,
                page_role=page_role,
                reason="multi_card_image_needs_child_crop_review",
                assessment_payload=assessment_payload,
            )
        )
    return requests


def _review_request(
    *,
    unit_id: str,
    entry: dict[str, Any],
    source_kind: str,
    page_number: int | None,
    page_role: str,
    reason: str,
    assessment_payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "request_id": f"crop-review-{unit_id}-{reason}",
        "request_kind": "crop_candidate_review",
        "bounded_question": "Which crop candidate should advance to OCR for this operator-declared positive-control card evidence?",
        "allowed_outputs": [
            "accept_primary_crop",
            "split_multi_card_children",
            "request_app_intelligence_crop",
            "mark_low_confidence",
        ],
        "reason": reason,
        "evidence": {
            "entry_id": entry.get("entry_id"),
            "sha256_prefix": entry.get("sha256_prefix"),
            "source_kind": source_kind,
            "page_number": page_number,
            "page_role": page_role,
            "classifier_decision": assessment_payload.get("decision"),
            "classifier_score": assessment_payload.get("score"),
            "analyzer_summary": _analyzer_summary(assessment_payload),
        },
        "private_paths_redacted": True,
        "private_filenames_redacted": True,
    }


def _analyzer_summary(assessment_payload: dict[str, Any]) -> dict[str, Any]:
    analyzers = dict(assessment_payload.get("analyzers") or {})
    rectangle = dict(analyzers.get("opencv_rectangle") or {})
    text_layout = dict(analyzers.get("opencv_text_layout") or {})
    aspect = dict(analyzers.get("aspect_ratio") or {})
    dimensions = dict(assessment_payload.get("dimensions") or {})
    return {
        "dimensions": dimensions,
        "aspect_ratio_score": float(aspect.get("score") or 0.0),
        "opencv_rectangle_available": rectangle.get("available") is True,
        "card_like_count": int(rectangle.get("card_like_count") or 0),
        "text_layout_score": float(text_layout.get("score") or 0.0),
        "document_like": text_layout.get("document_like") is True,
    }


def _page_role(*, entry: dict[str, Any], page_number: int) -> str:
    for page_label in list(entry.get("page_labels") or []):
        if not isinstance(page_label, dict):
            continue
        if int(page_label.get("page_number") or 0) == page_number:
            return str(page_label.get("side_expectation") or page_label.get("page_kind") or "unknown")
    return "front_or_back_unknown"


def _counts(
    *,
    entries: list[dict[str, Any]],
    source_results: list[dict[str, Any]],
    crop_candidates: list[dict[str, Any]],
    review_requests: list[dict[str, Any]],
    errors: list[dict[str, Any]],
) -> dict[str, int]:
    units = [
        unit
        for source in source_results
        for unit in list(source.get("processing_units") or [])
        if isinstance(unit, dict)
    ]
    return {
        "sources": len(entries),
        "images": sum(1 for entry in entries if entry.get("media_kind") == "image"),
        "pdf_documents": sum(1 for entry in entries if entry.get("media_kind") == "pdf_document"),
        "processing_units": len(units),
        "image_units": sum(1 for unit in units if unit.get("media_kind") == "image"),
        "pdf_page_units": sum(1 for unit in units if unit.get("media_kind") == "pdf_page"),
        "pdf_pages_materialized": sum(1 for unit in units if unit.get("media_kind") == "pdf_page"),
        "crop_candidate_count": len(crop_candidates),
        "primary_crop_candidates": sum(1 for candidate in crop_candidates if candidate.get("candidate_kind") == "primary_card_candidate"),
        "child_crop_candidates": sum(1 for candidate in crop_candidates if candidate.get("candidate_kind") == "child_card_candidate"),
        "accepted_for_ocr_workbench": sum(1 for candidate in crop_candidates if candidate.get("state") == "accepted_for_ocr_workbench"),
        "review_required_candidates": sum(1 for candidate in crop_candidates if candidate.get("requires_review") is True),
        "crop_review_requests": len(review_requests),
        "app_intelligence_request_count": sum(
            1 for request in review_requests if request.get("request_kind") == "crop_candidate_review"
        ),
        "multi_card_sources": sum(1 for entry in entries if entry.get("source_kind") == "multi_card_image_candidate"),
        "multi_card_units": sum(1 for unit in units if unit.get("source_kind") == "multi_card_image_candidate"),
        "multi_card_units_with_children": sum(
            1
            for unit in units
            if unit.get("source_kind") == "multi_card_image_candidate"
            and any(
                candidate.get("candidate_kind") == "child_card_candidate"
                for candidate in list(unit.get("crop_candidates") or [])
                if isinstance(candidate, dict)
            )
        ),
        "errors": len(errors),
    }


def _state(*, entries: list[dict[str, Any]], errors: list[dict[str, Any]]) -> str:
    if not entries:
        return "blocked"
    if errors:
        return "completed_with_index_errors"
    return "crop_workbench_review_required"


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


def _entries_digest(entries: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for entry in entries:
        digest.update(str(entry.get("sha256") or "").encode("utf-8"))
    return digest.hexdigest()[:12] if entries else "no-entries"


def _ensure_runtime_output_not_repo(output_root: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    try:
        output_root.resolve().relative_to(repo_root)
    except ValueError:
        return
    raise ValueError(f"positive control crop workbench output root is inside the repo: {output_root}")
