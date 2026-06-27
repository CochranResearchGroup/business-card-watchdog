from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .config import AppConfig
from .document_intake import materialize_document_pages
from .models import utc_now
from .preclassifier import assess_business_card_candidate


NEGATIVE_RECOGNITION_REPLAY_SCHEMA = "business-card-watchdog.negative-corpus-recognition-replay.v1"


def build_negative_corpus_recognition_replay(
    config: AppConfig,
    *,
    write: bool = True,
    max_pages_per_pdf: int | None = None,
    pdf_dpi: int = 200,
) -> dict[str, Any]:
    corpus_root = config.data_dir / "negative_control_corpus"
    rows, errors = _read_corpus_index(corpus_root / "index.jsonl")
    replay_id = f"negative-corpus-recognition-{utc_now().replace(':', '-')}-{_rows_digest(rows)}"
    replay_dir = corpus_root / "recognition_replays" / replay_id
    source_results = [
        _replay_source(
            row=row,
            corpus_root=corpus_root,
            replay_dir=replay_dir,
            write=write,
            max_pages_per_pdf=max_pages_per_pdf,
            pdf_dpi=pdf_dpi,
        )
        for row in rows
    ]
    source_results.sort(key=lambda row: (str(row["category"]), str(row["sha256"])))
    page_results = [
        page
        for source in source_results
        for page in list(source.get("pages") or [])
        if isinstance(page, dict)
    ]
    false_positives = [
        _false_positive(source=source, page=page)
        for source in source_results
        for page in list(source.get("pages") or [])
        if isinstance(page, dict) and page.get("classifier_training_state") == "business_card_high_confidence"
    ]
    counts = _counts(source_results=source_results, page_results=page_results, errors=errors)
    report_path = replay_dir / "recognition_replay.json"
    state = _state(source_results=source_results, false_positives=false_positives, errors=errors)
    payload: dict[str, Any] = {
        "schema": NEGATIVE_RECOGNITION_REPLAY_SCHEMA,
        "generated_at": utc_now(),
        "state": state,
        "replay_id": replay_id,
        "source_count": len(source_results),
        "page_count": len(page_results),
        "max_pages_per_pdf": max_pages_per_pdf,
        "pdf_dpi": pdf_dpi,
        "counts": counts,
        "category_summary": _category_summary(source_results),
        "classifier_state_summary": _classifier_state_summary(page_results),
        "source_results": source_results,
        "false_positive_cases": false_positives,
        "candidate_tuning_reasons": _candidate_tuning_reasons(false_positives),
        "errors": errors,
        "private_paths_redacted": True,
        "private_filenames_redacted": True,
        "replay_only_no_promotion": True,
        "ocr_attempted": 0,
        "pdfs_rasterized": counts["pdf_pages_replayed"],
        "crops_created": 0,
        "writes_attempted": 0,
        "network_calls_made": 0,
        "live_sink_calls_made": False,
        "public_web_search_used": False,
        "paid_enrichment_used": False,
        "runtime_artifact_written": False,
        "report_path": None,
        "commands": {
            "negative_corpus_recognition_replay": "negative-control-recognition-replay --json",
            "negative_corpus_recognition_replay_preview": "negative-control-recognition-replay --no-write --json",
        },
        "explicit_stop_conditions": [
            "This replay evaluates operator-declared negative controls only.",
            "This replay does not promote broad unknown-document autodetection.",
            "False positives are threshold-blocking training evidence.",
            "This replay does not OCR, crop, enrich, route, write contacts, or select live targets.",
        ],
    }
    if write and state != "blocked":
        _ensure_runtime_output_not_repo(corpus_root)
        replay_dir.mkdir(parents=True, exist_ok=True)
        written_payload = payload | {
            "runtime_artifact_written": True,
            "report_path": str(report_path),
        }
        report_path.write_text(json.dumps(written_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        payload["runtime_artifact_written"] = True
        payload["report_path"] = str(report_path)
    return payload


def _read_corpus_index(index_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not index_path.exists():
        return [], [{"error": "negative control corpus index not found"}]
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


def _replay_source(
    *,
    row: dict[str, Any],
    corpus_root: Path,
    replay_dir: Path,
    write: bool,
    max_pages_per_pdf: int | None,
    pdf_dpi: int,
) -> dict[str, Any]:
    sha256 = str(row.get("sha256") or "")
    media_kind = str(row.get("media_kind") or "unknown")
    blob_relpath = str(row.get("blob_relpath") or "")
    blob_path = corpus_root / blob_relpath
    source: dict[str, Any] = {
        "entry_id": str(row.get("entry_id") or f"negative-{sha256[:16]}"),
        "sha256": sha256,
        "sha256_prefix": sha256[:12],
        "media_kind": media_kind,
        "suffix": str(row.get("suffix") or ""),
        "size_bytes": int(row.get("size_bytes") or 0),
        "operator_declared_label": str(row.get("operator_declared_label") or ""),
        "category": str(row.get("category") or "unknown"),
        "blob_present": blob_path.exists(),
        "pages": [],
        "source_path_redacted": True,
        "source_filename_redacted": True,
    }
    if not blob_path.exists():
        source["state"] = "missing_blob"
        return source
    if media_kind == "image":
        source["pages"] = [_classify_image(blob_path, page_number=1)]
    elif media_kind == "pdf_document":
        source["pages"] = _classify_pdf_pages(
            blob_path,
            output_root=replay_dir / "document_pages",
            source_entry_id=str(source["entry_id"]),
            write=write,
            max_pages_per_pdf=max_pages_per_pdf,
            pdf_dpi=pdf_dpi,
        )
    else:
        source["state"] = "unsupported_media_kind"
        return source
    page_states = [str(page.get("classifier_training_state") or "") for page in source["pages"]]
    source["state"] = "false_positive" if "business_card_high_confidence" in page_states else "negative_control_passed"
    return source


def _classify_pdf_pages(
    path: Path,
    *,
    output_root: Path,
    source_entry_id: str,
    write: bool,
    max_pages_per_pdf: int | None,
    pdf_dpi: int,
) -> list[dict[str, Any]]:
    if not write:
        return [
            {
                "page_number": 0,
                "classifier_training_state": "indeterminate_needs_app_intelligence",
                "decision": "not_replayed_without_runtime_write",
                "score": 0.0,
                "reasons": ["PDF page replay requires runtime page materialization"],
                "source_entry_id": source_entry_id,
            }
        ]
    document_manifest = materialize_document_pages(
        path,
        output_root / source_entry_id,
        max_pages=max_pages_per_pdf,
        dpi=pdf_dpi,
    )
    pages: list[dict[str, Any]] = []
    for page in list(document_manifest.get("pages") or []):
        if not isinstance(page, dict):
            continue
        page_image = Path(str(page.get("page_image_path") or ""))
        pages.append(_classify_image(page_image, page_number=int(page.get("page_number") or 0)))
    return pages


def _classify_image(path: Path, *, page_number: int) -> dict[str, Any]:
    assessment = assess_business_card_candidate(path)
    payload = assessment.to_dict()
    state = _classifier_training_state(payload)
    dimensions = dict(payload.get("dimensions") or {})
    return {
        "page_number": page_number,
        "classifier_training_state": state,
        "decision": payload.get("decision"),
        "score": float(payload.get("score") or 0.0),
        "reasons": list(payload.get("reasons") or []),
        "dimensions": dimensions,
        "analyzer_summary": _analyzer_summary(payload),
    }


def _classifier_training_state(assessment: dict[str, Any]) -> str:
    decision = str(assessment.get("decision") or "")
    score = float(assessment.get("score") or 0.0)
    if decision == "likely_business_card" and score >= 0.55:
        return "business_card_high_confidence"
    if decision == "not_business_card" and score <= 0.05:
        return "not_business_card_high_confidence"
    return "indeterminate_needs_app_intelligence"


def _analyzer_summary(assessment: dict[str, Any]) -> dict[str, Any]:
    analyzers = dict(assessment.get("analyzers") or {})
    rectangle = dict(analyzers.get("opencv_rectangle") or {})
    text_layout = dict(analyzers.get("opencv_text_layout") or {})
    aspect = dict(analyzers.get("aspect_ratio") or {})
    return {
        "aspect_ratio_score": float(aspect.get("score") or 0.0),
        "opencv_rectangle_available": rectangle.get("available") is True,
        "card_like_count": int(rectangle.get("card_like_count") or 0),
        "text_layout_score": float(text_layout.get("score") or 0.0),
        "document_like": text_layout.get("document_like") is True,
    }


def _counts(
    *,
    source_results: list[dict[str, Any]],
    page_results: list[dict[str, Any]],
    errors: list[dict[str, Any]],
) -> dict[str, int]:
    counts = {
        "sources": len(source_results),
        "images": sum(1 for source in source_results if source.get("media_kind") == "image"),
        "pdf_documents": sum(1 for source in source_results if source.get("media_kind") == "pdf_document"),
        "pages_replayed": len(page_results),
        "pdf_pages_replayed": sum(
            len(list(source.get("pages") or []))
            for source in source_results
            if source.get("media_kind") == "pdf_document"
        ),
        "business_card_high_confidence": 0,
        "indeterminate_needs_app_intelligence": 0,
        "not_business_card_high_confidence": 0,
        "false_positive_cases": 0,
        "errors": len(errors),
    }
    for page in page_results:
        state = str(page.get("classifier_training_state") or "")
        if state in counts:
            counts[state] += 1
        if state == "business_card_high_confidence":
            counts["false_positive_cases"] += 1
    return counts


def _false_positive(*, source: dict[str, Any], page: dict[str, Any]) -> dict[str, Any]:
    return {
        "entry_id": source.get("entry_id"),
        "sha256_prefix": source.get("sha256_prefix"),
        "category": source.get("category"),
        "media_kind": source.get("media_kind"),
        "page_number": page.get("page_number"),
        "classifier_training_state": page.get("classifier_training_state"),
        "decision": page.get("decision"),
        "score": page.get("score"),
        "reasons": page.get("reasons"),
        "candidate_tuning_reason": _candidate_tuning_reason(page),
    }


def _candidate_tuning_reason(page: dict[str, Any]) -> str:
    reasons = " ".join(str(reason) for reason in list(page.get("reasons") or []))
    if "detected" in reasons and "business-card-like rectangular" in reasons:
        return "known_negative_promoted_by_rectangle_contours"
    if "card-like aspect ratio" in reasons:
        return "known_negative_promoted_by_text_layout"
    return "known_negative_false_positive_requires_review"


def _candidate_tuning_reasons(false_positives: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for row in false_positives:
        reason = str(row.get("candidate_tuning_reason") or "")
        counts[reason] = counts.get(reason, 0) + 1
    return [{"reason": reason, "count": count} for reason, count in sorted(counts.items())]


def _category_summary(source_results: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, dict[str, int]] = {}
    for source in source_results:
        category = str(source.get("category") or "unknown")
        bucket = summary.setdefault(category, {"sources": 0, "pages": 0, "false_positive_cases": 0})
        bucket["sources"] += 1
        pages = [page for page in list(source.get("pages") or []) if isinstance(page, dict)]
        bucket["pages"] += len(pages)
        bucket["false_positive_cases"] += sum(
            1 for page in pages if page.get("classifier_training_state") == "business_card_high_confidence"
        )
    return dict(sorted(summary.items()))


def _classifier_state_summary(page_results: list[dict[str, Any]]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for page in page_results:
        state = str(page.get("classifier_training_state") or "unknown")
        summary[state] = summary.get(state, 0) + 1
    return dict(sorted(summary.items()))


def _state(
    *,
    source_results: list[dict[str, Any]],
    false_positives: list[dict[str, Any]],
    errors: list[dict[str, Any]],
) -> str:
    if not source_results:
        return "blocked"
    if false_positives:
        return "false_positives_found"
    if errors:
        return "completed_with_index_errors"
    return "negative_controls_passed"


def _rows_digest(rows: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        digest.update(str(row.get("sha256") or "").encode("utf-8"))
    return digest.hexdigest()[:12] if rows else "no-rows"


def _ensure_runtime_output_not_repo(output_root: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    try:
        output_root.resolve().relative_to(repo_root)
    except ValueError:
        return
    raise ValueError(f"negative corpus recognition output root is inside the repo: {output_root}")
