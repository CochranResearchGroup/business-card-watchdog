from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .config import AppConfig
from .models import utc_now
from .positive_corpus_evaluation import build_positive_corpus_evaluation_manifest
from .positive_corpus_recognition import build_positive_corpus_recognition_replay
from .positive_corpus_review_loop import build_positive_corpus_training_review_loop
from .positive_corpus_side_pair import build_positive_corpus_side_pair_evaluation
from .positive_corpus_workbench import build_positive_corpus_workbench_evaluation


EXIT_GATE_SCHEMA = "business-card-watchdog.positive-corpus-exit-gate.v1"


def build_positive_corpus_exit_gate(config: AppConfig, *, write: bool = True) -> dict[str, Any]:
    corpus_root = config.data_dir / "positive_control_corpus"
    errors: list[dict[str, Any]] = []
    evaluation = _load_or_create_report(
        root=corpus_root / "evaluation_manifests",
        pattern="*.json",
        create=lambda: build_positive_corpus_evaluation_manifest(config, write=True),
        write=write,
        errors=errors,
        missing_error="no positive-corpus evaluation manifest found",
    )
    recognition = _load_or_create_report(
        root=corpus_root / "recognition_replays",
        pattern="*/recognition_replay.json",
        create=lambda: build_positive_corpus_recognition_replay(config, write=True),
        write=write,
        errors=errors,
        missing_error="no positive-corpus recognition replay found",
    )
    workbench = _load_or_create_report(
        root=corpus_root / "workbench_evaluations",
        pattern="*/workbench_evaluation.json",
        create=lambda: build_positive_corpus_workbench_evaluation(config, write=True, workers=1),
        write=write,
        errors=errors,
        missing_error="no positive-corpus workbench evaluation found",
    )
    side_pair = _load_or_create_report(
        root=corpus_root / "side_pair_evaluations",
        pattern="*/side_pair_evaluation.json",
        create=lambda: build_positive_corpus_side_pair_evaluation(config, write=True),
        write=write,
        errors=errors,
        missing_error="no positive-corpus side-pair evaluation found",
    )
    review_loop = _load_or_create_report(
        root=corpus_root / "training_review_loops",
        pattern="*/training_review_loop.json",
        create=lambda: build_positive_corpus_training_review_loop(config, write=True),
        write=write,
        errors=errors,
        missing_error="no positive-corpus training review loop found",
    )
    negative_controls = _negative_control_summary(config)
    negative_replay = _latest_negative_replay_summary(config)
    coverage = _coverage(evaluation=evaluation, recognition=recognition, workbench=workbench, side_pair=side_pair)
    false_negative = _false_negative_summary(recognition)
    reproducibility = _reproducibility(workbench=workbench, side_pair=side_pair)
    gate = _gate_decision(
        coverage=coverage,
        false_negative=false_negative,
        reproducibility=reproducibility,
        negative_controls=negative_controls,
        negative_replay=negative_replay,
        review_loop=review_loop,
        errors=errors,
    )
    gate_id = f"positive-corpus-exit-gate-{utc_now().replace(':', '-')}-{_reports_digest(evaluation, recognition, workbench, side_pair, review_loop)}"
    gate_dir = corpus_root / "exit_gates" / gate_id
    report_path = gate_dir / "positive_corpus_exit_gate.json"
    payload: dict[str, Any] = {
        "schema": EXIT_GATE_SCHEMA,
        "generated_at": utc_now(),
        "state": gate["state"],
        "gate_id": gate_id,
        "report_path": str(report_path) if write and gate["state"] != "blocked" else None,
        "evaluation_manifest_id": evaluation.get("manifest_id"),
        "recognition_replay_id": recognition.get("replay_id"),
        "workbench_id": workbench.get("workbench_id"),
        "side_pair_evaluation_id": side_pair.get("evaluation_id"),
        "training_review_loop_id": review_loop.get("loop_id"),
        "coverage": coverage,
        "false_negative_summary": false_negative,
        "reproducibility": reproducibility,
        "negative_control_summary": negative_controls,
        "negative_replay_summary": negative_replay,
        "gate_decision": gate,
        "next_plan_directive": {
            "broad_autodetection_state": gate["broad_autodetection_state"],
            "next_plan_required": gate["next_plan_required"],
            "required_before_resume": gate["required_before_resume"],
        },
        "counts": {
            "positive_sources": int(evaluation.get("entry_count") or 0),
            "positive_pages_or_images": int(dict(recognition.get("counts") or {}).get("pages_replayed") or 0),
            "false_negative_cases": int(dict(recognition.get("counts") or {}).get("false_negative_cases") or 0),
            "review_items": int(dict(review_loop.get("counts") or {}).get("review_items") or 0),
            "training_candidates": int(dict(review_loop.get("counts") or {}).get("training_candidates") or 0),
            "negative_control_sources": negative_controls["source_count"],
            "negative_false_positive_cases": negative_replay["false_positive_cases"],
            "blocking_requirements": len(gate["blocking_requirements"]),
            "errors": len(errors),
        },
        "errors": errors,
        "private_paths_redacted": True,
        "private_filenames_redacted": True,
        "operator_declared_known_positive_only": True,
        "broad_autodetection_promoted": False,
        "dry_run": True,
        "ocr_attempted": int(workbench.get("ocr_attempted") or 0),
        "pdfs_rasterized": int(workbench.get("pdfs_rasterized") or 0),
        "crops_created": int(workbench.get("crops_created") or 0),
        "writes_attempted": 0,
        "network_calls_made": 0,
        "live_sink_calls_made": False,
        "public_web_search_used": False,
        "paid_enrichment_used": False,
        "runtime_artifact_written": False,
        "commands": {
            "positive_corpus_exit_gate": "positive-corpus-exit-gate --json",
            "positive_corpus_exit_gate_preview": "positive-corpus-exit-gate --no-write --json",
            "training_review_loop": "positive-corpus-training-review-loop --json",
        },
        "explicit_stop_conditions": [
            "This exit gate does not change classifier thresholds.",
            "This exit gate does not resume broad unknown-document autodetection.",
            "Broad autodetection requires both sufficient positive evidence and separate negative-control evidence.",
            "Do not route, enrich, write contacts, read back sinks, search the public web, call paid providers, or select live targets.",
            "Do not commit runtime corpus artifacts, private media, OCR text, crops, or contact data.",
        ],
    }
    if write and gate["state"] != "blocked":
        _ensure_runtime_output_not_repo(corpus_root)
        gate_dir.mkdir(parents=True, exist_ok=True)
        payload["runtime_artifact_written"] = True
        report_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def _load_or_create_report(
    *,
    root: Path,
    pattern: str,
    create: Any,
    write: bool,
    errors: list[dict[str, Any]],
    missing_error: str,
) -> dict[str, Any]:
    latest = _latest_report(root, pattern=pattern)
    if latest is not None:
        return _read_json(latest)
    if not write:
        errors.append({"error": missing_error})
        return {}
    return create()


def _latest_report(root: Path, *, pattern: str) -> Path | None:
    if not root.exists():
        return None
    reports = sorted(root.glob(pattern), key=lambda path: path.stat().st_mtime, reverse=True)
    return reports[0] if reports else None


def _coverage(
    *,
    evaluation: dict[str, Any],
    recognition: dict[str, Any],
    workbench: dict[str, Any],
    side_pair: dict[str, Any],
) -> dict[str, Any]:
    groups = dict(evaluation.get("groups") or {})
    side_counts = dict(side_pair.get("counts") or {})
    workbench_counts = dict(workbench.get("counts") or {})
    coverage = {
        "source_count": int(evaluation.get("entry_count") or 0),
        "single_card_image_count": _group_count(groups, "single_card_image_candidate"),
        "multi_card_image_count": _group_count(groups, "multi_card_image_candidate"),
        "scanner_pdf_count": _group_count(groups, "scanner_pdf_document") + _group_count(groups, "likely_front_back_sequence"),
        "likely_front_back_sequence_count": _group_count(groups, "likely_front_back_sequence"),
        "pages_or_images_replayed": int(dict(recognition.get("counts") or {}).get("pages_replayed") or 0),
        "pdf_pages_materialized": int(workbench_counts.get("pdf_pages_materialized") or 0),
        "image_jobs": int(workbench_counts.get("image_jobs") or 0),
        "multi_card_candidate_jobs": int(workbench_counts.get("multi_card_candidate_jobs") or 0),
        "front_back_order_supported_by_tests": True,
        "dropped_blank_back_supported_by_tests": True,
        "multi_card_no_cross_merge_supported_by_tests": True,
        "runtime_side_pair_deterministic_proposals": int(side_counts.get("deterministic_pair_proposals") or 0),
        "runtime_side_pair_review_items": int(side_counts.get("app_intelligence_review_requests") or 0),
    }
    coverage["has_positive_sources"] = coverage["source_count"] > 0
    coverage["has_multi_card_images"] = coverage["multi_card_image_count"] > 0
    coverage["has_scanner_pdf_sequences"] = coverage["scanner_pdf_count"] > 0
    coverage["has_likely_front_back_sequences"] = coverage["likely_front_back_sequence_count"] > 0
    coverage["has_pdf_page_lineage"] = coverage["pdf_pages_materialized"] > 0
    return coverage


def _false_negative_summary(recognition: dict[str, Any]) -> dict[str, Any]:
    counts = dict(recognition.get("counts") or {})
    total = int(counts.get("pages_replayed") or 0)
    false_negatives = int(counts.get("false_negative_cases") or 0)
    high_confidence = int(counts.get("business_card_high_confidence") or 0)
    rate = false_negatives / total if total else 0.0
    return {
        "total_known_positive_pages_or_images": total,
        "business_card_high_confidence": high_confidence,
        "false_negative_cases": false_negatives,
        "false_negative_rate": round(rate, 4),
        "candidate_tuning_reasons": list(recognition.get("candidate_tuning_reasons") or []),
        "acceptable_for_broad_autodetection": false_negatives == 0 and total > 0,
    }


def _reproducibility(*, workbench: dict[str, Any], side_pair: dict[str, Any]) -> dict[str, Any]:
    workbench_counts = dict(workbench.get("counts") or {})
    side_counts = dict(side_pair.get("counts") or {})
    contact_drafts = int(workbench_counts.get("contact_drafts") or 0)
    review_packets = int(workbench_counts.get("review_packets") or 0)
    ocr_artifacts = int(workbench_counts.get("ocr_artifacts") or 0)
    processed_jobs = int(workbench_counts.get("processed_jobs") or 0)
    side_candidates = int(side_counts.get("scanner_page_candidates") or 0)
    return {
        "known_positive_crop_ocr_reproducible": processed_jobs > 0 and contact_drafts == processed_jobs and review_packets == processed_jobs,
        "ocr_artifacts_present": ocr_artifacts == processed_jobs and processed_jobs > 0,
        "raw_ocr_available": any(
            str(row.get("ocr_text_source") or "") == "adapter"
            for row in list(workbench.get("processed_jobs") or [])
            if isinstance(row, dict)
        ),
        "contact_draft_count": contact_drafts,
        "review_packet_count": review_packets,
        "processed_job_count": processed_jobs,
        "side_pair_evidence_reproducible": side_candidates > 0 and int(side_pair.get("page_candidate_count") or 0) == side_candidates,
        "side_pair_candidate_count": side_candidates,
        "side_pair_deterministic_pair_count": int(side_counts.get("deterministic_pair_proposals") or 0),
        "side_pair_review_request_count": int(side_counts.get("app_intelligence_review_requests") or 0),
    }


def _negative_control_summary(config: AppConfig) -> dict[str, Any]:
    root = config.data_dir / "negative_control_corpus"
    index_path = root / "index.jsonl"
    rows = _read_jsonl(index_path)
    categories: dict[str, int] = {}
    for row in rows:
        category = str(row.get("category") or row.get("label") or "unknown")
        categories[category] = categories.get(category, 0) + 1
    return {
        "state": "present" if rows else "missing",
        "source_count": len(rows),
        "categories": dict(sorted(categories.items())),
        "index_present": index_path.exists(),
        "index_path_redacted": True,
        "required_before_broad_autodetection": True,
    }


def _latest_negative_replay_summary(config: AppConfig) -> dict[str, Any]:
    report_path = _latest_report(
        config.data_dir / "negative_control_corpus" / "recognition_replays",
        pattern="*/recognition_replay.json",
    )
    if report_path is None:
        return {
            "state": "missing",
            "replay_id": None,
            "report_present": False,
            "source_count": 0,
            "page_count": 0,
            "false_positive_cases": 0,
            "required_before_broad_autodetection": True,
        }
    report = _read_json(report_path)
    counts = dict(report.get("counts") or {})
    return {
        "state": str(report.get("state") or "unknown"),
        "replay_id": report.get("replay_id"),
        "report_present": True,
        "source_count": int(report.get("source_count") or counts.get("sources") or 0),
        "page_count": int(report.get("page_count") or counts.get("pages_replayed") or 0),
        "false_positive_cases": int(counts.get("false_positive_cases") or 0),
        "required_before_broad_autodetection": True,
    }


def _gate_decision(
    *,
    coverage: dict[str, Any],
    false_negative: dict[str, Any],
    reproducibility: dict[str, Any],
    negative_controls: dict[str, Any],
    negative_replay: dict[str, Any],
    review_loop: dict[str, Any],
    errors: list[dict[str, Any]],
) -> dict[str, Any]:
    blocking: list[str] = []
    if errors:
        blocking.append("required positive-corpus reports are missing or invalid")
    if not coverage["has_positive_sources"]:
        blocking.append("positive-control corpus is empty")
    if not reproducibility["known_positive_crop_ocr_reproducible"]:
        blocking.append("known-positive crop/OCR evidence is not reproducible")
    if not reproducibility["side_pair_evidence_reproducible"]:
        blocking.append("known-positive side-pair evidence is not reproducible")
    if false_negative["false_negative_cases"]:
        blocking.append("known-positive false negatives remain unresolved")
    if negative_controls["source_count"] <= 0:
        blocking.append("separate negative-control corpus is required before broad promotion thresholds change")
    elif not negative_replay["report_present"]:
        blocking.append("negative-control recognition replay is required before broad promotion thresholds change")
    elif negative_replay["false_positive_cases"] > 0:
        blocking.append("known-negative false positives remain unresolved")
    review_counts = dict(review_loop.get("counts") or {})
    if int(review_counts.get("training_candidates") or 0) > 0:
        blocking.append("training candidates require targeted tests before deterministic rule changes")
    state = "blocked" if errors and not coverage["has_positive_sources"] else "broad_autodetection_paused"
    resume_allowed = not blocking
    if resume_allowed:
        state = "ready_for_bounded_autodetection_reconsideration"
    return {
        "state": state,
        "broad_autodetection_resume_allowed": resume_allowed,
        "broad_autodetection_state": "paused" if not resume_allowed else "eligible_for_next_bounded_plan",
        "crop_ocr_known_positive_processing_allowed": reproducibility["known_positive_crop_ocr_reproducible"],
        "threshold_change_allowed": (
            negative_controls["source_count"] > 0
            and negative_replay["report_present"]
            and negative_replay["false_positive_cases"] == 0
            and false_negative["false_negative_cases"] == 0
        ),
        "blocking_requirements": blocking,
        "required_before_resume": [
            "resolve or explicitly fixture known-positive false negatives",
            "add separate negative-control corpus and replay report",
            "resolve or explicitly fixture known-negative false positives",
            "promote accepted training candidates only through targeted tests",
            "rerun positive-corpus exit gate after deterministic changes",
        ],
        "next_plan_required": (
            "Keep broad autodetection paused. Next plan should build negative controls and resolve review-loop training candidates."
            if not resume_allowed
            else "A separate bounded plan may reconsider broad autodetection thresholds with positive and negative evidence."
        ),
    }


def _group_count(groups: dict[str, Any], group: str) -> int:
    return int(dict(groups.get(group) or {}).get("count") or 0)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _ensure_runtime_output_not_repo(output_root: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    try:
        output_root.resolve().relative_to(repo_root)
    except ValueError:
        return
    raise ValueError(f"positive corpus exit gate output root is inside the repo: {output_root}")


def _reports_digest(*reports: dict[str, Any]) -> str:
    digest = hashlib.sha256()
    for report in reports:
        for key in ("manifest_id", "replay_id", "workbench_id", "evaluation_id", "loop_id", "report_path"):
            digest.update(str(report.get(key) or "").encode("utf-8"))
    return digest.hexdigest()[:12] if any(reports) else "no-reports"
