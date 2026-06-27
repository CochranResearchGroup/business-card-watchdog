from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .config import AppConfig
from .models import utc_now
from .positive_control_labels import build_positive_control_label_inventory
from .positive_control_scenarios import build_positive_control_scenario_manifest
from .positive_corpus_recognition import build_positive_corpus_recognition_replay


POSITIVE_CONTROL_RECOGNITION_TRAINING_SCHEMA = (
    "business-card-watchdog.positive-control-recognition-training-replay.v1"
)


def build_positive_control_recognition_training_replay(
    config: AppConfig,
    *,
    write: bool = True,
) -> dict[str, Any]:
    corpus_root = config.data_dir / "positive_control_corpus"
    label_inventory = build_positive_control_label_inventory(config, write=False)
    scenario_manifest = build_positive_control_scenario_manifest(config, write=False)
    baseline = build_positive_corpus_recognition_replay(config, write=write)
    label_by_entry = {
        str(entry.get("entry_id") or ""): entry
        for entry in list(label_inventory.get("entries") or [])
        if isinstance(entry, dict)
    }
    page_cases = _page_cases(baseline=baseline, label_by_entry=label_by_entry)
    scenario_results = _scenario_results(
        scenario_manifest=scenario_manifest,
        baseline_by_entry=_baseline_by_entry(baseline),
    )
    app_intelligence_requests = _app_intelligence_requests(page_cases=page_cases, scenario_results=scenario_results)
    replay_id = f"positive-control-recognition-training-{utc_now().replace(':', '-')}-{_training_digest(page_cases, scenario_results)}"
    replay_dir = corpus_root / "recognition_training_replays" / replay_id
    report_path = replay_dir / "recognition_training_replay.json"
    before_counts = _counts(page_cases, state_key="baseline_training_state")
    after_counts = _counts(page_cases, state_key="tuned_training_state")
    payload: dict[str, Any] = {
        "schema": POSITIVE_CONTROL_RECOGNITION_TRAINING_SCHEMA,
        "generated_at": utc_now(),
        "state": _state(page_cases=page_cases, baseline=baseline),
        "replay_id": replay_id,
        "label_inventory_state": label_inventory.get("state"),
        "scenario_manifest_state": scenario_manifest.get("state"),
        "baseline_recognition_replay_id": baseline.get("replay_id"),
        "source_count": int(baseline.get("source_count") or 0),
        "page_case_count": len(page_cases),
        "scenario_count": int(scenario_manifest.get("scenario_count") or 0),
        "before_counts": before_counts,
        "after_counts": after_counts,
        "improvement_summary": _improvement_summary(before_counts=before_counts, after_counts=after_counts),
        "page_cases": page_cases,
        "false_negative_groups": _false_negative_groups(page_cases),
        "scenario_results": scenario_results,
        "app_intelligence_requests": app_intelligence_requests,
        "app_intelligence_request_count": len(app_intelligence_requests),
        "tuning_changes": _tuning_changes(page_cases),
        "broad_autodetection_paused": True,
        "unknown_document_threshold_changed": False,
        "negative_regression_required_before_threshold_change": True,
        "private_paths_redacted": True,
        "private_filenames_redacted": True,
        "replay_only_no_promotion": True,
        "ocr_attempted": 0,
        "pdfs_rasterized": int(baseline.get("pdfs_rasterized") or 0),
        "crops_created": 0,
        "writes_attempted": 0,
        "network_calls_made": 0,
        "live_sink_calls_made": False,
        "public_web_search_used": False,
        "paid_enrichment_used": False,
        "runtime_artifact_written": False,
        "report_path": None,
        "commands": {
            "positive_control_recognition_training_replay": "positive-control-recognition-training-replay --json",
            "positive_control_recognition_training_replay_preview": (
                "positive-control-recognition-training-replay --no-write --json"
            ),
            "positive_corpus_recognition_replay": "positive-corpus-recognition-replay --json",
            "negative_control_recognition_replay": "negative-control-recognition-replay --max-pages-per-pdf 1 --pdf-dpi 100 --json",
        },
        "explicit_stop_conditions": [
            "This report evaluates operator-declared positive controls and generated scenario plans only.",
            "This report does not change broad unknown-document autodetection thresholds.",
            "Contextual tuning may demote known-positive high-confidence negative outcomes to review, not promote unknown documents.",
            "Any future broad promotion threshold change requires separate negative-control regression evidence.",
            "This replay does not OCR, crop, enrich, route, write contacts, or select live targets.",
        ],
    }
    if write and payload["state"] != "blocked":
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


def _page_cases(*, baseline: dict[str, Any], label_by_entry: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for source in list(baseline.get("source_results") or []):
        if not isinstance(source, dict):
            continue
        entry_id = str(source.get("entry_id") or "")
        label = label_by_entry.get(entry_id, {})
        for page in list(source.get("pages") or []):
            if not isinstance(page, dict):
                continue
            baseline_state = str(page.get("classifier_training_state") or "")
            tuned = _tuned_state(source=source, label=label, page=page)
            case = {
                "case_id": f"{entry_id}-page-{int(page.get('page_number') or 0):03d}",
                "entry_id": entry_id,
                "sha256_prefix": source.get("sha256_prefix"),
                "source_kind": label.get("source_kind") or source.get("group"),
                "media_kind": source.get("media_kind"),
                "capture_mode": label.get("capture_mode") or "unknown",
                "card_count_label": label.get("card_count_label") or "unknown",
                "orientation_label": label.get("orientation_label") or "unknown",
                "scenario_kind": "real_positive_control_source",
                "page_number": page.get("page_number"),
                "page_role": _page_role(label=label, page_number=int(page.get("page_number") or 0)),
                "baseline_training_state": baseline_state,
                "tuned_training_state": tuned["state"],
                "decision": page.get("decision"),
                "score": page.get("score"),
                "reasons": page.get("reasons"),
                "analyzer_summary": page.get("analyzer_summary"),
                "tuning_action": tuned["action"],
                "tuning_reason": tuned["reason"],
                "app_intelligence_review_required": tuned["state"] == "indeterminate_needs_app_intelligence",
                "private_paths_redacted": True,
                "private_filenames_redacted": True,
            }
            cases.append(case)
    cases.sort(key=lambda row: (str(row["source_kind"]), str(row["entry_id"]), int(row["page_number"] or 0)))
    return cases


def _tuned_state(*, source: dict[str, Any], label: dict[str, Any], page: dict[str, Any]) -> dict[str, str]:
    baseline_state = str(page.get("classifier_training_state") or "")
    source_kind = str(label.get("source_kind") or source.get("group") or "")
    reasons = " ".join(str(reason) for reason in list(page.get("reasons") or []))
    if baseline_state == "business_card_high_confidence":
        return {
            "state": baseline_state,
            "action": "accept_baseline_high_confidence_positive",
            "reason": "deterministic_business_card_evidence_sufficient",
        }
    if (
        baseline_state == "not_business_card_high_confidence"
        and source_kind == "multi_card_image_candidate"
        and "document-like" in reasons
    ):
        return {
            "state": "indeterminate_needs_app_intelligence",
            "action": "demote_known_positive_multi_card_document_like_negative_to_review",
            "reason": "known_positive_multi_card_document_like_requires_crop_or_vision_review",
        }
    if baseline_state == "not_business_card_high_confidence" and source_kind.startswith("scanner_pdf"):
        return {
            "state": "indeterminate_needs_app_intelligence",
            "action": "demote_known_positive_pdf_negative_to_review",
            "reason": "known_positive_pdf_page_requires_vision_or_ocr_context",
        }
    if baseline_state == "indeterminate_needs_app_intelligence":
        return {
            "state": baseline_state,
            "action": "keep_indeterminate_for_app_intelligence",
            "reason": _indeterminate_reason(source_kind=source_kind, page=page),
        }
    return {
        "state": baseline_state or "indeterminate_needs_app_intelligence",
        "action": "keep_baseline_state",
        "reason": "known_positive_false_negative_requires_review",
    }


def _indeterminate_reason(*, source_kind: str, page: dict[str, Any]) -> str:
    summary = dict(page.get("analyzer_summary") or {})
    if summary.get("document_like") is True:
        return "known_positive_document_like_page_requires_app_intelligence"
    if source_kind == "scanner_pdf_front_back_sequence_candidate":
        return "scanner_pdf_sequence_page_lacks_deterministic_card_features"
    if source_kind == "multi_card_image_candidate":
        return "multi_card_image_requires_crop_or_vision_review"
    return "known_positive_indeterminate_requires_feature_or_fixture_review"


def _page_role(*, label: dict[str, Any], page_number: int) -> str:
    for page_label in list(label.get("page_labels") or []):
        if not isinstance(page_label, dict):
            continue
        if int(page_label.get("page_number") or 0) == page_number:
            return str(page_label.get("side_expectation") or page_label.get("page_kind") or "unknown")
    return "front_or_back_or_composite_unknown"


def _baseline_by_entry(baseline: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(source.get("entry_id") or ""): source
        for source in list(baseline.get("source_results") or [])
        if isinstance(source, dict)
    }


def _scenario_results(*, scenario_manifest: dict[str, Any], baseline_by_entry: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for scenario in list(scenario_manifest.get("scenarios") or []):
        if not isinstance(scenario, dict):
            continue
        source = baseline_by_entry.get(str(scenario.get("source_entry_id") or ""), {})
        page_states = [
            str(page.get("classifier_training_state") or "")
            for page in list(source.get("pages") or [])
            if isinstance(page, dict)
        ]
        operations = [
            str(operation.get("operation") or "")
            for operation in list(scenario.get("operations") or [])
            if isinstance(operation, dict)
        ]
        requires_materialization = any(
            operation
            in {
                "rotate_image",
                "rotate_pages",
                "swap_adjacent_front_back_pages",
                "duplicate_first_page",
                "compose_mixed_multi_card_image_plan",
                "omit_even_pages_as_blank_or_dropped_backs",
                "omit_odd_pages_as_fronts",
            }
            for operation in operations
        )
        rows.append(
            {
                "scenario_id": scenario.get("scenario_id"),
                "scenario_kind": scenario.get("scenario_kind"),
                "source_entry_id": scenario.get("source_entry_id"),
                "source_kind": scenario.get("source_kind"),
                "operation_names": operations,
                "baseline_source_state": source.get("state") or "source_not_replayed",
                "baseline_page_states": page_states,
                "expected_replay_status": "requires_materialized_replay" if requires_materialization else "baseline_source_replayed",
                "app_intelligence_review_required": "business_card_high_confidence" not in page_states,
                "replay_targets": list(scenario.get("replay_targets") or []),
                "private_paths_redacted": True,
                "private_filenames_redacted": True,
            }
        )
    rows.sort(key=lambda row: str(row.get("scenario_id") or ""))
    return rows


def _app_intelligence_requests(
    *,
    page_cases: list[dict[str, Any]],
    scenario_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    requests: list[dict[str, Any]] = []
    for case in page_cases:
        if case.get("tuned_training_state") != "indeterminate_needs_app_intelligence":
            continue
        requests.append(
            {
                "request_id": f"appintel-{case['case_id']}",
                "request_kind": "positive_control_recognition_review",
                "bounded_question": "Does this operator-declared positive-control page/image contain one or more business card sides?",
                "allowed_outputs": [
                    "business_card_present",
                    "business_card_backside_only",
                    "multi_card_image",
                    "not_enough_visual_evidence",
                ],
                "evidence": {
                    "case_id": case.get("case_id"),
                    "entry_id": case.get("entry_id"),
                    "sha256_prefix": case.get("sha256_prefix"),
                    "source_kind": case.get("source_kind"),
                    "page_role": case.get("page_role"),
                    "baseline_training_state": case.get("baseline_training_state"),
                    "tuned_training_state": case.get("tuned_training_state"),
                    "tuning_reason": case.get("tuning_reason"),
                },
                "private_paths_redacted": True,
                "private_filenames_redacted": True,
            }
        )
    blocked_scenarios = [
        scenario
        for scenario in scenario_results
        if scenario.get("expected_replay_status") == "requires_materialized_replay"
        and scenario.get("app_intelligence_review_required") is True
    ][:10]
    for scenario in blocked_scenarios:
        requests.append(
            {
                "request_id": f"appintel-scenario-{scenario.get('scenario_id')}",
                "request_kind": "positive_control_scenario_review",
                "bounded_question": "After materialization, should this generated positive-control scenario be treated as business card evidence or routed to crop/OCR review?",
                "allowed_outputs": [
                    "recognition_replay_needed",
                    "crop_ocr_replay_needed",
                    "side_pair_replay_needed",
                    "not_enough_visual_evidence",
                ],
                "evidence": {
                    "scenario_id": scenario.get("scenario_id"),
                    "scenario_kind": scenario.get("scenario_kind"),
                    "source_entry_id": scenario.get("source_entry_id"),
                    "operation_names": scenario.get("operation_names"),
                    "expected_replay_status": scenario.get("expected_replay_status"),
                },
                "private_paths_redacted": True,
                "private_filenames_redacted": True,
            }
        )
    return requests


def _counts(page_cases: list[dict[str, Any]], *, state_key: str) -> dict[str, int]:
    counts = {
        "pages_or_images": len(page_cases),
        "business_card_high_confidence": 0,
        "indeterminate_needs_app_intelligence": 0,
        "not_business_card_high_confidence": 0,
        "false_negative_cases": 0,
        "high_confidence_negative_known_positive_cases": 0,
    }
    for case in page_cases:
        state = str(case.get(state_key) or "")
        if state in counts:
            counts[state] += 1
        if state != "business_card_high_confidence":
            counts["false_negative_cases"] += 1
        if state == "not_business_card_high_confidence":
            counts["high_confidence_negative_known_positive_cases"] += 1
    return counts


def _improvement_summary(*, before_counts: dict[str, int], after_counts: dict[str, int]) -> dict[str, Any]:
    before_high_neg = before_counts["high_confidence_negative_known_positive_cases"]
    after_high_neg = after_counts["high_confidence_negative_known_positive_cases"]
    before_false_neg = before_counts["false_negative_cases"]
    after_false_neg = after_counts["false_negative_cases"]
    return {
        "high_confidence_negative_known_positive_before": before_high_neg,
        "high_confidence_negative_known_positive_after": after_high_neg,
        "high_confidence_negative_known_positive_reduction": before_high_neg - after_high_neg,
        "false_negative_cases_before": before_false_neg,
        "false_negative_cases_after": after_false_neg,
        "false_negative_case_delta": after_false_neg - before_false_neg,
        "interpretation": (
            "Contextual positive-control tuning moves high-confidence known-positive negatives to review; "
            "remaining false negatives require App Intelligence, crop/OCR, or fixture-backed rule work."
        ),
    }


def _false_negative_groups(page_cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str, str, str, str, str], dict[str, Any]] = {}
    for case in page_cases:
        if case.get("tuned_training_state") == "business_card_high_confidence":
            continue
        key = (
            str(case.get("scenario_kind") or ""),
            str(case.get("source_kind") or ""),
            str(case.get("page_role") or ""),
            str(case.get("card_count_label") or ""),
            str(case.get("orientation_label") or ""),
            str(case.get("capture_mode") or ""),
            str(case.get("tuning_reason") or ""),
        )
        bucket = groups.setdefault(
            key,
            {
                "scenario_kind": key[0],
                "source_kind": key[1],
                "page_role": key[2],
                "card_count_label": key[3],
                "orientation_label": key[4],
                "capture_mode": key[5],
                "tuning_reason": key[6],
                "count": 0,
                "case_ids": [],
            },
        )
        bucket["count"] += 1
        bucket["case_ids"].append(case.get("case_id"))
    return sorted(groups.values(), key=lambda row: (-int(row["count"]), str(row["tuning_reason"])))


def _tuning_changes(page_cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    changed = [
        case
        for case in page_cases
        if case.get("baseline_training_state") != case.get("tuned_training_state")
    ]
    if not changed:
        return []
    return [
        {
            "change_id": "known_positive_multi_card_document_like_negative_to_review",
            "scope": "operator_declared_positive_controls_only",
            "before_state": "not_business_card_high_confidence",
            "after_state": "indeterminate_needs_app_intelligence",
            "case_count": len(changed),
            "case_ids": [case.get("case_id") for case in changed],
            "requires_negative_regression_before_broad_threshold_change": True,
        }
    ]


def _state(*, page_cases: list[dict[str, Any]], baseline: dict[str, Any]) -> str:
    if not page_cases or baseline.get("state") == "blocked":
        return "blocked"
    if any(case.get("tuned_training_state") != "business_card_high_confidence" for case in page_cases):
        return "needs_app_intelligence_or_feature_tuning"
    return "known_positives_recognized_after_contextual_tuning"


def _training_digest(page_cases: list[dict[str, Any]], scenario_results: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for case in page_cases:
        digest.update(str(case.get("case_id") or "").encode("utf-8"))
        digest.update(str(case.get("tuned_training_state") or "").encode("utf-8"))
    for scenario in scenario_results:
        digest.update(str(scenario.get("scenario_id") or "").encode("utf-8"))
    return digest.hexdigest()[:12] if page_cases or scenario_results else "no-cases"


def _ensure_runtime_output_not_repo(output_root: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    try:
        output_root.resolve().relative_to(repo_root)
    except ValueError:
        return
    raise ValueError(f"positive control recognition training output root is inside the repo: {output_root}")
