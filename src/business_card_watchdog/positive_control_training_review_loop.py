from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from .config import AppConfig
from .models import utc_now
from .positive_control_crop_workbench import build_positive_control_crop_workbench
from .positive_control_ocr_drafts import build_positive_control_ocr_contact_drafts
from .positive_control_recognition_training import build_positive_control_recognition_training_replay
from .positive_control_side_pair_evidence import build_positive_control_side_pair_evidence


POSITIVE_CONTROL_TRAINING_REVIEW_LOOP_SCHEMA = (
    "business-card-watchdog.positive-control-training-review-loop.v1"
)
REVIEW_ITEM_SCHEMA = "business-card-watchdog.positive-control-training-review-item.v1"


def build_positive_control_training_review_loop(config: AppConfig, *, write: bool = True) -> dict[str, Any]:
    corpus_root = config.data_dir / "positive_control_corpus"
    errors: list[dict[str, Any]] = []
    recognition = _load_or_create_report(
        root=corpus_root / "recognition_training_replays",
        filename="recognition_training_replay.json",
        create=lambda: build_positive_control_recognition_training_replay(config, write=True),
        write=write,
        errors=errors,
        missing_error="no positive-control recognition training replay found",
    )
    crop = _load_or_create_report(
        root=corpus_root / "crop_workbenches",
        filename="crop_workbench.json",
        create=lambda: build_positive_control_crop_workbench(config, write=True),
        write=write,
        errors=errors,
        missing_error="no positive-control crop workbench found",
    )
    ocr = _load_or_create_report(
        root=corpus_root / "ocr_contact_drafts",
        filename="ocr_contact_drafts.json",
        create=lambda: build_positive_control_ocr_contact_drafts(config, write=True),
        write=write,
        errors=errors,
        missing_error="no positive-control OCR contact drafts found",
    )
    side_pair = _load_or_create_report(
        root=corpus_root / "side_pair_evidence",
        filename="side_pair_evidence.json",
        create=lambda: build_positive_control_side_pair_evidence(config, write=True),
        write=write,
        errors=errors,
        missing_error="no positive-control side-pair evidence found",
    )
    review_items = _review_items(recognition=recognition, crop=crop, ocr=ocr, side_pair=side_pair)
    app_requests = _app_intelligence_requests(review_items)
    training_candidates = _training_candidates(review_items)
    counts = _counts(
        review_items=review_items,
        app_requests=app_requests,
        training_candidates=training_candidates,
        errors=errors,
    )
    loop_id = (
        f"positive-control-training-review-loop-{utc_now().replace(':', '-')}-"
        f"{_reports_digest(recognition, crop, ocr, side_pair)}"
    )
    loop_dir = corpus_root / "training_review_loops" / loop_id
    report_path = loop_dir / "training_review_loop.json"
    state = "blocked" if errors and not review_items else "agent_review_ready" if review_items else "no_review_items"
    payload: dict[str, Any] = {
        "schema": POSITIVE_CONTROL_TRAINING_REVIEW_LOOP_SCHEMA,
        "generated_at": utc_now(),
        "state": state if write else ("ready_for_runtime_training_review_loop" if state != "blocked" else "blocked"),
        "loop_id": loop_id,
        "recognition_replay_id": recognition.get("replay_id"),
        "crop_workbench_id": crop.get("workbench_id"),
        "ocr_draft_id": ocr.get("draft_id"),
        "side_pair_report_id": side_pair.get("report_id"),
        "review_item_count": len(review_items),
        "review_items": review_items,
        "app_intelligence_request_count": len(app_requests),
        "app_intelligence_requests": app_requests,
        "training_candidate_count": len(training_candidates),
        "training_candidates": training_candidates,
        "counts": counts,
        "agent_iteration_contract": {
            "loop_mode": "evidence_review_only",
            "allowed_iteration_outputs": [
                "deterministic_rule_proposal",
                "fixture_or_test_proposal",
                "bounded_app_intelligence_evidence_request",
                "explicit_stop_condition",
            ],
            "accepted_change_requires": [
                "targeted_test_before_implementation",
                "before_after_replay_metrics",
                "negative_control_regression_check_before_threshold_change",
            ],
            "host_authority": [
                "state_transitions",
                "ledgers",
                "approvals",
                "replay",
                "sink_writes",
                "stop_rules",
            ],
        },
        "private_paths_redacted": True,
        "private_filenames_redacted": True,
        "operator_declared_known_positive_only": True,
        "broad_autodetection_promoted": False,
        "dry_run": True,
        "routing_allowed": False,
        "enrichment_allowed": False,
        "sink_payloads_created": 0,
        "ocr_attempted": int(ocr.get("ocr_attempted") or 0),
        "pdfs_rasterized": int(max(crop.get("pdfs_rasterized") or 0, ocr.get("pdfs_rasterized") or 0)),
        "crops_created": int(crop.get("crops_created") or 0),
        "writes_attempted": 0,
        "network_calls_made": 0,
        "live_sink_calls_made": False,
        "public_web_search_used": False,
        "paid_enrichment_used": False,
        "runtime_artifact_written": False,
        "report_path": None,
        "errors": errors,
        "commands": {
            "positive_control_training_review_loop": "positive-control-training-review-loop --json",
            "positive_control_training_review_loop_preview": (
                "positive-control-training-review-loop --no-write --json"
            ),
            "positive_control_recognition_training_replay": "positive-control-recognition-training-replay --json",
            "positive_control_crop_workbench": "positive-control-crop-workbench --json",
            "positive_control_ocr_contact_drafts": "positive-control-ocr-contact-drafts --json",
            "positive_control_side_pair_evidence": "positive-control-side-pair-evidence --json",
        },
        "explicit_stop_conditions": [
            "Agents may review evidence and propose tests or deterministic rule candidates only.",
            "App Intelligence requests are bounded evidence requests, not workflow control.",
            "No review item may route, enrich, create sink payloads, write contacts, read back sinks, search public web, call paid providers, or select live targets.",
            "Accepted improvements require targeted tests and replay evidence before implementation.",
            "Broad autodetection remains paused until a separate readiness gate passes with negative-control evidence.",
        ],
    }
    if write and state != "blocked":
        _ensure_runtime_output_not_repo(corpus_root)
        loop_dir.mkdir(parents=True, exist_ok=True)
        report_payload = payload | {"runtime_artifact_written": True, "report_path": str(report_path)}
        report_path.write_text(json.dumps(report_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        payload["runtime_artifact_written"] = True
        payload["report_path"] = str(report_path)
    return payload


def _load_or_create_report(
    *,
    root: Path,
    filename: str,
    create: Callable[[], dict[str, Any]],
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
    crop: dict[str, Any],
    ocr: dict[str, Any],
    side_pair: dict[str, Any],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    items.extend(_recognition_items(recognition))
    items.extend(_crop_items(crop))
    items.extend(_ocr_items(ocr))
    items.extend(_side_pair_items(side_pair))
    items.sort(key=lambda item: (int(item.get("priority") or 99), str(item.get("review_item_id") or "")))
    return items


def _recognition_items(recognition: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for case in list(recognition.get("page_cases") or []):
        if not isinstance(case, dict):
            continue
        if case.get("tuned_training_state") == "business_card_high_confidence":
            continue
        items.append(
            _base_item(
                category="recognition",
                priority=10,
                subject_id=case.get("case_id"),
                failure_mode=str(case.get("tuning_reason") or "known_positive_requires_review"),
                source_lineage={
                    "entry_id": case.get("entry_id"),
                    "sha256_prefix": case.get("sha256_prefix"),
                    "media_kind": case.get("media_kind"),
                    "page_number": case.get("page_number"),
                    "source_path_redacted": True,
                    "source_filename_redacted": True,
                },
                deterministic_evidence={
                    "baseline_training_state": case.get("baseline_training_state"),
                    "tuned_training_state": case.get("tuned_training_state"),
                    "decision": case.get("decision"),
                    "score": case.get("score"),
                    "reasons": list(case.get("reasons") or []),
                },
                agent_next_output="fixture_or_test_proposal",
                deterministic_rule_target="preclassifier_positive_control_features",
                suggested_test="positive_control_recognition_false_negative_fixture",
                app_request_kind="document_type_or_card_presence_review",
            )
        )
    for scenario in list(recognition.get("scenario_results") or []):
        if not isinstance(scenario, dict) or scenario.get("app_intelligence_review_required") is not True:
            continue
        items.append(
            _base_item(
                category="recognition_scenario",
                priority=20,
                subject_id=scenario.get("scenario_id"),
                failure_mode="generated_positive_control_scenario_requires_replay_or_review",
                source_lineage={
                    "scenario_id": scenario.get("scenario_id"),
                    "source_entry_id": scenario.get("source_entry_id"),
                    "source_kind": scenario.get("source_kind"),
                    "source_path_redacted": True,
                    "source_filename_redacted": True,
                },
                deterministic_evidence={
                    "scenario_kind": scenario.get("scenario_kind"),
                    "operation_names": list(scenario.get("operation_names") or []),
                    "baseline_page_states": list(scenario.get("baseline_page_states") or []),
                },
                agent_next_output="deterministic_rule_proposal",
                deterministic_rule_target="positive_control_scenario_replay",
                suggested_test="positive_control_generated_scenario_replay_fixture",
                app_request_kind="scenario_card_presence_review",
            )
        )
    return items


def _crop_items(crop: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _base_item(
            category="crop",
            priority=30,
            subject_id=request.get("request_id"),
            failure_mode=str(request.get("reason") or "crop_review_required"),
            source_lineage=dict(request.get("evidence") or {}) | {
                "source_path_redacted": True,
                "source_filename_redacted": True,
            },
            deterministic_evidence=dict(request.get("evidence") or {}),
            agent_next_output="bounded_app_intelligence_evidence_request",
            deterministic_rule_target="known_card_crop_candidate_selection",
            suggested_test="positive_control_crop_review_fixture",
            app_request_kind="crop_candidate_review",
        )
        for request in list(crop.get("review_requests") or [])
        if isinstance(request, dict)
    ]


def _ocr_items(ocr: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for review in list(ocr.get("review_items") or []):
        if not isinstance(review, dict):
            continue
        items.append(
            _base_item(
                category="ocr",
                priority=25 if review.get("kind") == "missing_ocr" else 35,
                subject_id=review.get("review_item_id"),
                failure_mode=str(review.get("kind") or "ocr_review_required"),
                source_lineage={
                    "review_item_id": review.get("review_item_id"),
                    "source_path_redacted": True,
                    "source_filename_redacted": True,
                },
                deterministic_evidence={
                    "severity": review.get("severity"),
                    "message": review.get("message"),
                },
                agent_next_output="explicit_stop_condition"
                if review.get("kind") == "missing_ocr"
                else "fixture_or_test_proposal",
                deterministic_rule_target="ocr_adapter_or_contact_field_extraction",
                suggested_test="positive_control_ocr_contact_draft_fixture",
                app_request_kind="ocr_or_contact_field_review",
            )
        )
    return items


def _side_pair_items(side_pair: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for edge in list(side_pair.get("edges") or []):
        if not isinstance(edge, dict) or edge.get("state") not in {"review_required", "blocked_conflict"}:
            continue
        items.append(
            _base_item(
                category="side_pair",
                priority=15 if edge.get("state") == "blocked_conflict" else 40,
                subject_id=edge.get("edge_id"),
                failure_mode=str(edge.get("state") or "side_pair_review_required"),
                source_lineage={
                    "edge_id": edge.get("edge_id"),
                    "entry_id": edge.get("entry_id"),
                    "page_numbers": list(edge.get("page_numbers") or []),
                    "source_path_redacted": True,
                    "source_filename_redacted": True,
                },
                deterministic_evidence={
                    "reason": edge.get("reason"),
                    "deterministic_clues": edge.get("deterministic_clues"),
                    "conflict_evidence": edge.get("conflict_evidence"),
                },
                agent_next_output="bounded_app_intelligence_evidence_request",
                deterministic_rule_target="front_back_side_pair_graph",
                suggested_test="positive_control_side_pair_graph_fixture",
                app_request_kind="front_back_side_pair_review",
            )
        )
    return items


def _base_item(
    *,
    category: str,
    priority: int,
    subject_id: Any,
    failure_mode: str,
    source_lineage: dict[str, Any],
    deterministic_evidence: dict[str, Any],
    agent_next_output: str,
    deterministic_rule_target: str,
    suggested_test: str,
    app_request_kind: str,
) -> dict[str, Any]:
    review_item_id = _stable_id("positive-control-review", category, subject_id, failure_mode)
    return {
        "schema": REVIEW_ITEM_SCHEMA,
        "review_item_id": review_item_id,
        "category": category,
        "priority": priority,
        "state": "agent_review_required",
        "failure_mode": failure_mode,
        "source_lineage": source_lineage,
        "deterministic_evidence": deterministic_evidence,
        "agent_next_output": agent_next_output,
        "proposed_deterministic_improvement": {
            "deterministic_rule_target": deterministic_rule_target,
            "suggested_test": suggested_test,
            "requires_before_after_metrics": True,
        },
        "app_intelligence_request_kind": app_request_kind,
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
    return [
        {
            "schema": "business-card-watchdog.positive-control-app-intelligence-request.v1",
            "request_id": _stable_id("positive-control-app-request", item.get("review_item_id")),
            "review_item_id": item.get("review_item_id"),
            "request_kind": item.get("app_intelligence_request_kind"),
            "status": "planned",
            "allowed_outputs": _allowed_outputs(str(item.get("app_intelligence_request_kind") or "")),
            "allowed_answer_shape": "evidence_only_no_state_transition",
            "deterministic_evidence": item.get("deterministic_evidence"),
            "source_lineage": item.get("source_lineage"),
            "forbidden_actions": _forbidden_actions(),
            "writes_attempted": 0,
            "network_calls_made": 0,
            "routing_allowed": False,
            "enrichment_allowed": False,
            "sink_write_allowed": False,
            "sink_readback_allowed": False,
            "public_web_search_allowed": False,
            "paid_enrichment_allowed": False,
        }
        for item in review_items
        if item.get("agent_next_output") == "bounded_app_intelligence_evidence_request"
    ]


def _training_candidates(review_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for item in review_items:
        improvement = dict(item.get("proposed_deterministic_improvement") or {})
        candidates.append(
            {
                "schema": "business-card-watchdog.positive-control-training-candidate.v1",
                "candidate_id": _stable_id("positive-control-training-candidate", item.get("review_item_id")),
                "review_item_id": item.get("review_item_id"),
                "category": item.get("category"),
                "failure_mode": item.get("failure_mode"),
                "agent_next_output": item.get("agent_next_output"),
                "state": "candidate_requires_test_before_apply",
                "deterministic_rule_target": improvement.get("deterministic_rule_target"),
                "suggested_test": improvement.get("suggested_test"),
                "promotion_requires": [
                    "write_or_update_targeted_test",
                    "rerun_positive_control_evidence",
                    "rerun_negative_control_replay_before_threshold_change",
                ],
                "routing_allowed": False,
                "enrichment_allowed": False,
                "sink_write_allowed": False,
                "sink_readback_allowed": False,
            }
        )
    return candidates


def _counts(
    *,
    review_items: list[dict[str, Any]],
    app_requests: list[dict[str, Any]],
    training_candidates: list[dict[str, Any]],
    errors: list[dict[str, Any]],
) -> dict[str, int]:
    categories = ["recognition", "recognition_scenario", "crop", "ocr", "side_pair"]
    counts = {
        "review_items": len(review_items),
        "app_intelligence_requests": len(app_requests),
        "training_candidates": len(training_candidates),
        "errors": len(errors),
        "routing_allowed_items": sum(1 for item in review_items if item.get("routing_allowed") is True),
        "sink_write_allowed_items": sum(1 for item in review_items if item.get("sink_write_allowed") is True),
        "public_web_allowed_items": sum(1 for item in review_items if item.get("public_web_search_allowed") is True),
    }
    for category in categories:
        counts[f"{category}_items"] = sum(1 for item in review_items if item.get("category") == category)
    return counts


def _allowed_outputs(request_kind: str) -> list[str]:
    return {
        "crop_candidate_review": ["accept_primary_crop", "split_multi_card_children", "needs_more_evidence"],
        "front_back_side_pair_review": [
            "same_card_pair",
            "not_same_card",
            "blank_or_dropped_back",
            "front_only",
            "needs_more_ocr_or_visual_evidence",
        ],
    }.get(request_kind, ["evidence_supports_rule", "evidence_blocks_rule", "needs_more_evidence"])


def _forbidden_actions() -> list[str]:
    return [
        "route_contact",
        "write_sink",
        "readback_sink",
        "run_enrichment",
        "search_public_web",
        "call_paid_provider",
        "select_live_target",
        "resume_broad_autodetection",
    ]


def _review_item_stop_conditions() -> list[str]:
    return [
        "Return evidence and recommendation only; do not change host state.",
        "Do not route, enrich, write, read back, search public web, call paid providers, or select a live target.",
        "Accepted evidence must become a deterministic fixture or rule candidate before implementation.",
        "Do not resume broad autodetection from this review item.",
    ]


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
    raise ValueError(f"positive control training review loop output root is inside the repo: {output_root}")


def _reports_digest(*reports: dict[str, Any]) -> str:
    digest = hashlib.sha256()
    for report in reports:
        for key in ("replay_id", "workbench_id", "draft_id", "report_id", "report_path"):
            digest.update(str(report.get(key) or "").encode("utf-8"))
    return digest.hexdigest()[:12] if any(reports) else "no-reports"


def _stable_id(*parts: Any) -> str:
    digest = hashlib.sha256("\0".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:20]
    return f"positive_control_review_{digest}"
