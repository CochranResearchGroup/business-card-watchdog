from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .config import AppConfig
from .document_intake import materialize_document_pages
from .models import utc_now
from .positive_corpus_evaluation import build_positive_corpus_evaluation_manifest
from .preclassifier import assess_business_card_candidate


RECOGNITION_REPLAY_SCHEMA = "business-card-watchdog.positive-corpus-recognition-replay.v1"


def build_positive_corpus_recognition_replay(config: AppConfig, *, write: bool = True) -> dict[str, Any]:
    corpus_root = config.data_dir / "positive_control_corpus"
    rows, errors = _read_corpus_index(corpus_root / "index.jsonl")
    evaluation = build_positive_corpus_evaluation_manifest(config, write=False)
    replay_id = f"positive-corpus-recognition-{utc_now().replace(':', '-')}-{_rows_digest(rows)}"
    replay_dir = corpus_root / "recognition_replays" / replay_id
    source_results = [
        _replay_source(row=row, corpus_root=corpus_root, replay_dir=replay_dir, write=write)
        for row in rows
    ]
    source_results.sort(key=lambda row: (str(row["group"]), str(row["sha256"])))
    page_results = [
        page
        for source in source_results
        for page in list(source.get("pages") or [])
        if isinstance(page, dict)
    ]
    false_negatives = [
        _false_negative(source=source, page=page)
        for source in source_results
        for page in list(source.get("pages") or [])
        if isinstance(page, dict) and page.get("classifier_training_state") != "business_card_high_confidence"
    ]
    counts = _counts(source_results=source_results, page_results=page_results, errors=errors)
    report_path = replay_dir / "recognition_replay.json"
    state = _state(source_results=source_results, errors=errors)
    payload: dict[str, Any] = {
        "schema": RECOGNITION_REPLAY_SCHEMA,
        "generated_at": utc_now(),
        "state": state,
        "replay_id": replay_id,
        "evaluation_manifest_state": evaluation.get("state"),
        "evaluation_entry_count": evaluation.get("entry_count", 0),
        "source_count": len(source_results),
        "page_count": len(page_results),
        "counts": counts,
        "source_results": source_results,
        "false_negative_cases": false_negatives,
        "candidate_tuning_reasons": _candidate_tuning_reasons(false_negatives),
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
            "positive_corpus_recognition_replay": "positive-corpus-recognition-replay --json",
            "positive_corpus_recognition_replay_preview": "positive-corpus-recognition-replay --no-write --json",
        },
        "explicit_stop_conditions": [
            "This replay evaluates operator-declared positive controls only.",
            "This replay does not promote broad unknown-document autodetection.",
            "False negatives are training evidence, not discarded inputs.",
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


def _replay_source(
    *,
    row: dict[str, Any],
    corpus_root: Path,
    replay_dir: Path,
    write: bool,
) -> dict[str, Any]:
    sha256 = str(row.get("sha256") or "")
    media_kind = str(row.get("media_kind") or "unknown")
    blob_relpath = str(row.get("blob_relpath") or "")
    blob_path = corpus_root / blob_relpath
    source: dict[str, Any] = {
        "entry_id": str(row.get("entry_id") or f"positive-{sha256[:16]}"),
        "sha256": sha256,
        "sha256_prefix": sha256[:12],
        "media_kind": media_kind,
        "suffix": str(row.get("suffix") or ""),
        "size_bytes": int(row.get("size_bytes") or 0),
        "operator_declared_label": str(row.get("operator_declared_label") or ""),
        "group": _source_group(row=row, corpus_root=corpus_root),
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
        )
    else:
        source["state"] = "unsupported_media_kind"
        return source
    page_states = [str(page.get("classifier_training_state") or "") for page in source["pages"]]
    source["state"] = "recognized_positive" if "business_card_high_confidence" in page_states else "false_negative"
    return source


def _classify_pdf_pages(
    path: Path,
    *,
    output_root: Path,
    source_entry_id: str,
    write: bool,
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
    document_manifest = materialize_document_pages(path, output_root / source_entry_id)
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


def _source_group(*, row: dict[str, Any], corpus_root: Path) -> str:
    media_kind = str(row.get("media_kind") or "")
    blob_path = corpus_root / str(row.get("blob_relpath") or "")
    if media_kind == "pdf_document":
        try:
            raw = blob_path.read_bytes()
        except OSError:
            return "scanner_pdf_document"
        page_count = len(re.findall(rb"/Type\s*/Page\b", raw))
        return "likely_front_back_sequence" if page_count >= 2 and page_count % 2 == 0 else "scanner_pdf_document"
    if media_kind == "image":
        assessment = assess_business_card_candidate(blob_path)
        dimensions = assessment.dimensions
        if dimensions is not None and (dimensions.aspect_ratio >= 2.05 or max(dimensions.width, dimensions.height) >= 2800):
            return "multi_card_image_candidate"
        return "single_card_image_candidate"
    return "unsupported_or_unknown_media"


def _counts(*, source_results: list[dict[str, Any]], page_results: list[dict[str, Any]], errors: list[dict[str, Any]]) -> dict[str, int]:
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
        "false_negative_cases": 0,
        "errors": len(errors),
    }
    for page in page_results:
        state = str(page.get("classifier_training_state") or "")
        if state in counts:
            counts[state] += 1
        if state != "business_card_high_confidence":
            counts["false_negative_cases"] += 1
    return counts


def _false_negative(*, source: dict[str, Any], page: dict[str, Any]) -> dict[str, Any]:
    return {
        "entry_id": source.get("entry_id"),
        "sha256_prefix": source.get("sha256_prefix"),
        "media_kind": source.get("media_kind"),
        "group": source.get("group"),
        "page_number": page.get("page_number"),
        "classifier_training_state": page.get("classifier_training_state"),
        "decision": page.get("decision"),
        "score": page.get("score"),
        "reasons": page.get("reasons"),
        "candidate_tuning_reason": _candidate_tuning_reason(page),
    }


def _candidate_tuning_reason(page: dict[str, Any]) -> str:
    state = str(page.get("classifier_training_state") or "")
    reasons = " ".join(str(reason) for reason in list(page.get("reasons") or []))
    if state == "indeterminate_needs_app_intelligence":
        return "known_positive_indeterminate_requires_feature_or_fixture_review"
    if "aspect ratio is not business-card-like" in reasons:
        return "known_positive_rejected_by_aspect_or_page_shape"
    if "full-page document-like" in reasons:
        return "known_positive_rejected_as_document_like"
    return "known_positive_false_negative_requires_review"


def _candidate_tuning_reasons(false_negatives: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for row in false_negatives:
        reason = str(row.get("candidate_tuning_reason") or "")
        counts[reason] = counts.get(reason, 0) + 1
    return [{"reason": reason, "count": count} for reason, count in sorted(counts.items())]


def _state(*, source_results: list[dict[str, Any]], errors: list[dict[str, Any]]) -> str:
    if not source_results:
        return "blocked"
    if errors:
        return "completed_with_index_errors"
    if any(source.get("state") == "false_negative" for source in source_results):
        return "needs_recognition_tuning"
    return "known_positives_recognized"


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
    raise ValueError(f"positive corpus recognition output root is inside the repo: {output_root}")
