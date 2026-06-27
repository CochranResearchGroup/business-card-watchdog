from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .config import AppConfig
from .models import utc_now
from .positive_corpus_recognition import build_positive_corpus_recognition_replay
from .positive_corpus_side_pair import build_positive_corpus_side_pair_evaluation
from .positive_corpus_workbench import build_positive_corpus_workbench_evaluation


TRAINING_REVIEW_LOOP_SCHEMA = "business-card-watchdog.positive-corpus-training-review-loop.v1"


def build_positive_corpus_training_review_loop(config: AppConfig, *, write: bool = True) -> dict[str, Any]:
    corpus_root = config.data_dir / "positive_control_corpus"
    errors: list[dict[str, Any]] = []
    recognition = _load_or_create_report(
        root=corpus_root / "recognition_replays",
        filename="recognition_replay.json",
        create=lambda: build_positive_corpus_recognition_replay(config, write=True),
        write=write,
        errors=errors,
        missing_error="no recognition replay found; run positive-corpus-recognition-replay first",
    )
    workbench = _load_or_create_report(
        root=corpus_root / "workbench_evaluations",
        filename="workbench_evaluation.json",
        create=lambda: build_positive_corpus_workbench_evaluation(config, write=True, workers=1),
        write=write,
        errors=errors,
        missing_error="no workbench evaluation found; run positive-corpus-workbench-evaluation first",
    )
    side_pair = _load_or_create_report(
        root=corpus_root / "side_pair_evaluations",
        filename="side_pair_evaluation.json",
        create=lambda: build_positive_corpus_side_pair_evaluation(config, write=True),
        write=write,
        errors=errors,
        missing_error="no side-pair evaluation found; run positive-corpus-side-pair-evaluation first",
    )
    loop_id = f"positive-corpus-review-loop-{utc_now().replace(':', '-')}-{_reports_digest(recognition, workbench, side_pair)}"
    loop_dir = corpus_root / "training_review_loops" / loop_id
    report_path = loop_dir / "training_review_loop.json"
    review_items = _review_items(recognition=recognition, workbench=workbench, side_pair=side_pair)
    app_requests = _app_intelligence_requests(review_items)
    training_candidates = _training_candidates(review_items)
    counts = _counts(review_items=review_items, app_requests=app_requests, training_candidates=training_candidates, errors=errors)
    state = "blocked" if errors and not review_items else "agent_review_ready" if review_items else "no_review_items"
    payload: dict[str, Any] = {
        "schema": TRAINING_REVIEW_LOOP_SCHEMA,
        "generated_at": utc_now(),
        "state": state,
        "loop_id": loop_id,
        "recognition_replay_id": recognition.get("replay_id"),
        "recognition_report_path": recognition.get("report_path"),
        "workbench_id": workbench.get("workbench_id"),
        "workbench_report_path": workbench.get("report_path"),
        "side_pair_evaluation_id": side_pair.get("evaluation_id"),
        "side_pair_report_path": side_pair.get("report_path"),
        "report_path": str(report_path) if write and state != "blocked" else None,
        "review_item_count": len(review_items),
        "review_items": review_items,
        "app_intelligence_request_count": len(app_requests),
        "app_intelligence_requests": app_requests,
        "training_candidate_count": len(training_candidates),
        "training_candidates": training_candidates,
        "counts": counts,
        "agent_iteration_contract": {
            "loop_mode": "evidence_review_only",
            "agent_may_propose": [
                "new_or_updated_fixture",
                "deterministic_rule_threshold_change",
                "deterministic_feature_extractor_change",
                "additional_app_intelligence_evidence_request",
            ],
            "agent_must_not": [
                "route_contact",
                "write_sink",
                "readback_sink",
                "run_enrichment",
                "search_public_web",
                "call_paid_provider",
                "select_live_target",
                "promote_unknown_document_autodetection",
            ],
            "accepted_change_requires": [
                "targeted_test_before_implementation",
                "redacted_runtime_evidence",
                "no_regression_against_existing_negative_controls",
            ],
        },
        "iteration_plan": [
            {
                "step": "inspect_review_item",
                "required_output": "failure_mode, deterministic_evidence_gap, proposed_test",
            },
            {
                "step": "decide_deterministic_change",
                "required_output": "rule_or_fixture_candidate, stop_condition_if_ambiguous",
            },
            {
                "step": "request_app_intelligence_only_if_needed",
                "required_output": "bounded evidence-only request with forbidden actions",
            },
            {
                "step": "implement_only_after_test",
                "required_output": "targeted fixture/regression test before code change",
            },
        ],
        "errors": errors,
        "private_paths_redacted": True,
        "private_filenames_redacted": True,
        "operator_declared_known_positive_only": True,
        "broad_autodetection_promoted": False,
        "dry_run": True,
        "ocr_attempted": int(dict(workbench.get("counts") or {}).get("ocr_artifacts") or 0),
        "pdfs_rasterized": int(dict(workbench.get("counts") or {}).get("pdf_pages_materialized") or 0),
        "crops_created": int(workbench.get("crops_created") or 0),
        "writes_attempted": 0,
        "network_calls_made": 0,
        "live_sink_calls_made": False,
        "public_web_search_used": False,
        "paid_enrichment_used": False,
        "runtime_artifact_written": False,
        "commands": {
            "positive_corpus_training_review_loop": "positive-corpus-training-review-loop --json",
            "positive_corpus_training_review_loop_preview": "positive-corpus-training-review-loop --no-write --json",
            "recognition_replay": "positive-corpus-recognition-replay --json",
            "workbench_evaluation": "positive-corpus-workbench-evaluation --json",
            "side_pair_evaluation": "positive-corpus-side-pair-evaluation --json",
        },
        "explicit_stop_conditions": [
            "Review items are evidence for deterministic training only.",
            "App Intelligence requests are bounded and evidence-only.",
            "No review item may route, enrich, write, read back, search the public web, call paid providers, or select live targets.",
            "Accepted corrections must become tests before deterministic rule implementation.",
            "Broad autodetection remains paused until a later exit gate with negative-control evidence.",
        ],
    }
    if write and state != "blocked":
        _ensure_runtime_output_not_repo(corpus_root)
        loop_dir.mkdir(parents=True, exist_ok=True)
        payload["runtime_artifact_written"] = True
        report_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def _load_or_create_report(
    *,
    root: Path,
    filename: str,
    create: Any,
    write: bool,
    errors: list[dict[str, Any]],
    missing_error: str,
) -> dict[str, Any]:
    latest = _latest_report(root, filename=filename)
    if latest is not None:
        return _read_json(latest)
    if not write:
        errors.append({"error": missing_error})
        return {}
    return create()


def _latest_report(root: Path, *, filename: str) -> Path | None:
    if not root.exists():
        return None
    reports = sorted(root.glob(f"*/{filename}"), key=lambda path: path.stat().st_mtime, reverse=True)
    return reports[0] if reports else None


def _review_items(
    *,
    recognition: dict[str, Any],
    workbench: dict[str, Any],
    side_pair: dict[str, Any],
) -> list[dict[str, Any]]:
    items = [
        *[_recognition_review_item(row) for row in list(recognition.get("false_negative_cases") or []) if isinstance(row, dict)],
        *[_workbench_review_item(row) for row in list(workbench.get("processed_jobs") or []) if _workbench_needs_review(row)],
        *[_side_pair_review_item(row) for row in list(side_pair.get("app_intelligence_review_requests") or []) if isinstance(row, dict)],
    ]
    items = [item for item in items if item]
    items.sort(key=lambda row: (int(row.get("priority") or 99), str(row.get("review_item_id") or "")))
    return items


def _recognition_review_item(row: dict[str, Any]) -> dict[str, Any]:
    failure_mode = str(row.get("candidate_tuning_reason") or "known_positive_false_negative_requires_review")
    item_id = _stable_id("recognition", row.get("entry_id"), row.get("page_number"), failure_mode)
    return _base_review_item(
        review_item_id=item_id,
        category="recognition",
        priority=10 if "not_business_card" in str(row.get("classifier_training_state") or "") else 20,
        source_lineage={
            "entry_id": row.get("entry_id"),
            "sha256_prefix": row.get("sha256_prefix"),
            "media_kind": row.get("media_kind"),
            "group": row.get("group"),
            "page_number": row.get("page_number"),
            "source_path_redacted": True,
            "source_filename_redacted": True,
        },
        failure_mode=failure_mode,
        deterministic_evidence={
            "classifier_training_state": row.get("classifier_training_state"),
            "decision": row.get("decision"),
            "score": row.get("score"),
            "reasons": list(row.get("reasons") or []),
        },
        proposed_deterministic_improvement=_recognition_improvement(failure_mode),
        app_intelligence_request_type="classify_document_type",
        app_intelligence_reason="known-positive recognition evidence is insufficient for deterministic rule promotion",
    )


def _workbench_review_item(row: dict[str, Any]) -> dict[str, Any]:
    failure_mode = _workbench_failure_mode(row)
    item_id = _stable_id("workbench", row.get("job_id"), row.get("page_number"), failure_mode)
    return _base_review_item(
        review_item_id=item_id,
        category="crop_ocr",
        priority=30 if failure_mode == "raw_ocr_unavailable" else 25,
        source_lineage={
            "job_id": row.get("job_id"),
            "media_kind": row.get("media_kind"),
            "page_number": row.get("page_number"),
            "rasterization_mode": row.get("rasterization_mode"),
            "source_path_redacted": True,
            "source_filename_redacted": True,
        },
        failure_mode=failure_mode,
        deterministic_evidence={
            "classifier_training_state": row.get("classifier_training_state"),
            "known_positive_bypass_admission": row.get("known_positive_bypass_admission"),
            "candidate_crop_count": row.get("candidate_crop_count"),
            "crop_quality_state": row.get("crop_quality_state"),
            "crop_acceptance_state": row.get("crop_acceptance_state"),
            "extraction_quality_status": row.get("extraction_quality_status"),
            "ocr_quality_gate_state": row.get("ocr_quality_gate_state"),
            "ocr_text_present": row.get("ocr_text_present"),
            "ocr_text_source": row.get("ocr_text_source"),
            "app_intelligence_request_count": row.get("app_intelligence_request_count"),
        },
        proposed_deterministic_improvement=_workbench_improvement(failure_mode),
        app_intelligence_request_type="verify_contact_fields"
        if failure_mode in {"raw_ocr_unavailable", "ocr_quality_needs_review"}
        else "assess_crop_quality",
        app_intelligence_reason=f"known-positive crop/OCR evidence requires review: {failure_mode}",
    )


def _side_pair_review_item(row: dict[str, Any]) -> dict[str, Any]:
    failure_mode = _side_pair_failure_mode(row)
    item_id = _stable_id("side-pair", row.get("request_id"), row.get("request_type"), failure_mode)
    return _base_review_item(
        review_item_id=item_id,
        category="side_pair",
        priority=15 if failure_mode == "conflicting_side_pair_evidence" else 35,
        source_lineage={
            "request_id": row.get("request_id"),
            "request_type": row.get("request_type"),
            "page_numbers": list(row.get("page_numbers") or []),
            "side_labels": list(row.get("side_labels") or []),
            "proposal_id": row.get("proposal_id"),
            "front_job_id": row.get("front_job_id"),
            "back_job_id": row.get("back_job_id"),
            "source_path_redacted": True,
            "source_filename_redacted": True,
        },
        failure_mode=failure_mode,
        deterministic_evidence=dict(row.get("deterministic_evidence") or {}),
        proposed_deterministic_improvement=_side_pair_improvement(failure_mode),
        app_intelligence_request_type=str(row.get("request_type") or "pair_card_sides"),
        app_intelligence_reason=str(row.get("reason") or "side-pair evidence requires review"),
    )


def _base_review_item(
    *,
    review_item_id: str,
    category: str,
    priority: int,
    source_lineage: dict[str, Any],
    failure_mode: str,
    deterministic_evidence: dict[str, Any],
    proposed_deterministic_improvement: dict[str, Any],
    app_intelligence_request_type: str,
    app_intelligence_reason: str,
) -> dict[str, Any]:
    return {
        "schema": "business-card-watchdog.positive-corpus-training-review-item.v1",
        "review_item_id": review_item_id,
        "category": category,
        "priority": priority,
        "state": "agent_review_required",
        "source_lineage": source_lineage,
        "failure_mode": failure_mode,
        "deterministic_evidence": deterministic_evidence,
        "proposed_deterministic_improvement": proposed_deterministic_improvement,
        "app_intelligence_request_type": app_intelligence_request_type,
        "app_intelligence_reason": app_intelligence_reason,
        "stop_conditions": _review_item_stop_conditions(),
        "routing_allowed": False,
        "enrichment_allowed": False,
        "sink_write_allowed": False,
        "sink_readback_allowed": False,
        "public_web_search_allowed": False,
        "paid_enrichment_allowed": False,
        "live_target_selection_allowed": False,
        "source_path_redacted": True,
        "source_filename_redacted": True,
    }


def _app_intelligence_requests(review_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_app_intelligence_request(item) for item in review_items]


def _app_intelligence_request(item: dict[str, Any]) -> dict[str, Any]:
    request_id = _stable_id("app-intelligence", item.get("review_item_id"), item.get("app_intelligence_request_type"))
    return {
        "schema": "business-card-watchdog.app-intelligence-review-request.v1",
        "request_id": request_id,
        "review_item_id": item.get("review_item_id"),
        "request_type": item.get("app_intelligence_request_type"),
        "status": "planned",
        "reason": item.get("app_intelligence_reason"),
        "allowed_answer_shape": "evidence_only_no_state_transition",
        "allowed_response_schema": _allowed_response_schema(str(item.get("app_intelligence_request_type") or "")),
        "deterministic_evidence": item.get("deterministic_evidence"),
        "source_lineage": item.get("source_lineage"),
        "training_promotion": {
            "mode": "candidate_only",
            "accepted_response_creates_contact_state": False,
            "expected_followup": "add_or_update_deterministic_fixture_before_safe_apply",
        },
        "stop_rules": _review_item_stop_conditions(),
        "writes_attempted": 0,
        "network_calls_made": 0,
        "routing_allowed": False,
        "enrichment_allowed": False,
        "sink_write_allowed": False,
        "sink_readback_allowed": False,
        "public_web_search_allowed": False,
        "paid_enrichment_allowed": False,
        "live_target_selection_allowed": False,
    }


def _training_candidates(review_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for item in review_items:
        improvement = dict(item.get("proposed_deterministic_improvement") or {})
        candidates.append(
            {
                "schema": "business-card-watchdog.positive-corpus-training-candidate.v1",
                "candidate_id": _stable_id("training-candidate", item.get("review_item_id")),
                "review_item_id": item.get("review_item_id"),
                "category": item.get("category"),
                "failure_mode": item.get("failure_mode"),
                "state": "candidate_requires_test_before_apply",
                "suggested_test": improvement.get("suggested_test"),
                "deterministic_rule_target": improvement.get("deterministic_rule_target"),
                "proposed_change": improvement.get("proposed_change"),
                "source_lineage": item.get("source_lineage"),
                "promotion_requires": [
                    "write_or_update_targeted_test",
                    "run_existing_negative_control_tests",
                    "rerun_positive_corpus_evidence_report",
                ],
                "routing_allowed": False,
                "enrichment_allowed": False,
                "sink_write_allowed": False,
                "sink_readback_allowed": False,
            }
        )
    return candidates


def _recognition_improvement(failure_mode: str) -> dict[str, Any]:
    if failure_mode == "known_positive_rejected_as_document_like":
        return {
            "deterministic_rule_target": "preclassifier_text_layout_document_like_gate",
            "proposed_change": "add fixture coverage for multi-card or scanner-page business cards before changing document-like rejection",
            "suggested_test": "known_positive_document_like_false_negative_fixture",
        }
    if failure_mode == "known_positive_rejected_by_aspect_or_page_shape":
        return {
            "deterministic_rule_target": "preclassifier_aspect_ratio_gate",
            "proposed_change": "add card-page/page-raster aspect fixture before threshold tuning",
            "suggested_test": "known_positive_scanner_page_aspect_false_negative_fixture",
        }
    return {
        "deterministic_rule_target": "preclassifier_feature_extraction",
        "proposed_change": "add known-positive fixture or feature evidence before broad promotion threshold changes",
        "suggested_test": "known_positive_indeterminate_recognition_fixture",
    }


def _workbench_improvement(failure_mode: str) -> dict[str, Any]:
    if failure_mode == "raw_ocr_unavailable":
        return {
            "deterministic_rule_target": "business_card_to_contact_adapter_artifact_contract",
            "proposed_change": "require raw OCR text or explicit OCR-unavailable evidence before side-pair training",
            "suggested_test": "known_card_workbench_raw_ocr_artifact_contract",
        }
    if failure_mode == "crop_quality_needs_review":
        return {
            "deterministic_rule_target": "crop_quality_acceptance",
            "proposed_change": "add crop-quality fixture and recrop proposal expectation before changing crop gates",
            "suggested_test": "known_card_crop_quality_review_fixture",
        }
    return {
        "deterministic_rule_target": "ocr_quality_gate",
        "proposed_change": "add OCR quality fixture before allowing contact extraction to proceed",
        "suggested_test": "known_card_ocr_quality_review_fixture",
    }


def _side_pair_improvement(failure_mode: str) -> dict[str, Any]:
    if failure_mode == "conflicting_side_pair_evidence":
        return {
            "deterministic_rule_target": "side_pair_conflict_blocker",
            "proposed_change": "preserve blocked merge and add conflict fixture before any pairing relaxation",
            "suggested_test": "side_pair_conflicting_identity_blocks_merge",
        }
    if failure_mode == "blank_back_candidate":
        return {
            "deterministic_rule_target": "side_pair_blank_back_handling",
            "proposed_change": "add dropped-or-blank-back fixture before treating adjacency as complete pair",
            "suggested_test": "side_pair_blank_back_does_not_cross_merge",
        }
    return {
        "deterministic_rule_target": "side_pair_context_scoring",
        "proposed_change": "add front/back OCR clue fixture or request bounded App Intelligence evidence before pairing",
        "suggested_test": "side_pair_ambiguous_adjacency_review_fixture",
    }


def _workbench_needs_review(row: dict[str, Any]) -> bool:
    return (
        row.get("ocr_text_source") == "derived_from_contact_spec"
        or str(row.get("crop_quality_state") or "") in {"bad", "qr_only", "no_crops"}
        or str(row.get("ocr_quality_gate_state") or "") == "needs_app_intelligence_review"
        or int(row.get("app_intelligence_request_count") or 0) > 0
    )


def _workbench_failure_mode(row: dict[str, Any]) -> str:
    if row.get("ocr_text_source") == "derived_from_contact_spec":
        return "raw_ocr_unavailable"
    if str(row.get("crop_quality_state") or "") in {"bad", "qr_only", "no_crops"}:
        return "crop_quality_needs_review"
    return "ocr_quality_needs_review"


def _side_pair_failure_mode(row: dict[str, Any]) -> str:
    evidence = dict(row.get("deterministic_evidence") or {})
    negative = set(str(item) for item in list(evidence.get("negative_evidence_kinds") or []))
    recommendations = str(row.get("reason") or "").casefold()
    if negative:
        return "conflicting_side_pair_evidence"
    if "blank" in recommendations:
        return "blank_back_candidate"
    return "ambiguous_side_pair_requires_review"


def _allowed_response_schema(request_type: str) -> dict[str, Any]:
    allowed = {
        "classify_document_type": ["business_card", "not_business_card", "needs_more_deterministic_evidence"],
        "assess_crop_quality": ["crop_good", "crop_bad", "use_recrop_candidate", "needs_more_deterministic_evidence"],
        "verify_contact_fields": ["fields_verified", "fields_need_correction", "needs_more_deterministic_evidence"],
        "pair_card_sides": ["same_card_pair", "not_same_card", "blank_back", "needs_more_deterministic_evidence"],
        "resolve_ocr_merge_conflict": [
            "use_front_value",
            "use_back_value",
            "fields_need_correction",
            "needs_more_deterministic_evidence",
        ],
    }
    return {
        "type": "object",
        "required": ["recommendation", "confidence", "rationale", "evidence"],
        "properties": {
            "recommendation": {
                "type": "string",
                "enum": allowed.get(request_type, ["needs_more_deterministic_evidence"]),
            },
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "rationale": {"type": "string"},
            "evidence": {"type": "object"},
            "training_hint": {"type": "string"},
        },
        "forbidden_actions": [
            "route_contact",
            "write_sink",
            "readback_sink",
            "run_enrichment",
            "search_public_web",
            "call_paid_provider",
            "select_live_target",
        ],
    }


def _review_item_stop_conditions() -> list[str]:
    return [
        "Return evidence and recommendation only; do not change contact state.",
        "Do not route, enrich, write, read back, search the public web, call paid providers, or select a live target.",
        "Accepted evidence must become a deterministic fixture or rule candidate before implementation.",
        "Do not resume broad autodetection from this review item.",
    ]


def _counts(
    *,
    review_items: list[dict[str, Any]],
    app_requests: list[dict[str, Any]],
    training_candidates: list[dict[str, Any]],
    errors: list[dict[str, Any]],
) -> dict[str, int]:
    return {
        "review_items": len(review_items),
        "recognition_items": sum(1 for item in review_items if item.get("category") == "recognition"),
        "crop_ocr_items": sum(1 for item in review_items if item.get("category") == "crop_ocr"),
        "side_pair_items": sum(1 for item in review_items if item.get("category") == "side_pair"),
        "app_intelligence_requests": len(app_requests),
        "training_candidates": len(training_candidates),
        "errors": len(errors),
        "routing_allowed_items": sum(1 for item in review_items if item.get("routing_allowed") is True),
        "sink_write_allowed_items": sum(1 for item in review_items if item.get("sink_write_allowed") is True),
        "public_web_allowed_items": sum(1 for item in review_items if item.get("public_web_search_allowed") is True),
    }


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _ensure_runtime_output_not_repo(output_root: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    try:
        output_root.resolve().relative_to(repo_root)
    except ValueError:
        return
    raise ValueError(f"positive corpus training review loop output root is inside the repo: {output_root}")


def _reports_digest(*reports: dict[str, Any]) -> str:
    digest = hashlib.sha256()
    for report in reports:
        for key in ("replay_id", "workbench_id", "evaluation_id", "report_path"):
            digest.update(str(report.get(key) or "").encode("utf-8"))
    return digest.hexdigest()[:12] if any(reports) else "no-reports"


def _stable_id(*parts: Any) -> str:
    digest = hashlib.sha256("\0".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:20]
    return f"review_{digest}"
