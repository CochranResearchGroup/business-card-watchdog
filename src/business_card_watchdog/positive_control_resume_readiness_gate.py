from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from .config import AppConfig
from .models import utc_now
from .positive_control_crop_workbench import build_positive_control_crop_workbench
from .positive_control_labels import build_positive_control_label_inventory
from .positive_control_ocr_drafts import build_positive_control_ocr_contact_drafts
from .positive_control_recognition_training import build_positive_control_recognition_training_replay
from .positive_control_scenarios import build_positive_control_scenario_manifest
from .positive_control_side_pair_evidence import build_positive_control_side_pair_evidence
from .positive_control_training_review_loop import build_positive_control_training_review_loop


POSITIVE_CONTROL_RESUME_READINESS_GATE_SCHEMA = (
    "business-card-watchdog.positive-control-resume-readiness-gate.v1"
)


def build_positive_control_resume_readiness_gate(config: AppConfig, *, write: bool = True) -> dict[str, Any]:
    corpus_root = config.data_dir / "positive_control_corpus"
    errors: list[dict[str, Any]] = []
    labels = _load_or_create_report(
        root=corpus_root / "label_inventories",
        pattern="*.json",
        create=lambda: build_positive_control_label_inventory(config, write=True),
        write=write,
        errors=errors,
        missing_error="no positive-control label inventory found",
    )
    scenarios = _load_or_create_report(
        root=corpus_root / "scenario_manifests",
        pattern="*.json",
        create=lambda: build_positive_control_scenario_manifest(config, write=True),
        write=write,
        errors=errors,
        missing_error="no positive-control scenario manifest found",
    )
    recognition = _load_or_create_report(
        root=corpus_root / "recognition_training_replays",
        pattern="*/recognition_training_replay.json",
        create=lambda: build_positive_control_recognition_training_replay(config, write=True),
        write=write,
        errors=errors,
        missing_error="no positive-control recognition training replay found",
    )
    crop = _load_or_create_report(
        root=corpus_root / "crop_workbenches",
        pattern="*/crop_workbench.json",
        create=lambda: build_positive_control_crop_workbench(config, write=True),
        write=write,
        errors=errors,
        missing_error="no positive-control crop workbench found",
    )
    ocr = _load_or_create_report(
        root=corpus_root / "ocr_contact_drafts",
        pattern="*/ocr_contact_drafts.json",
        create=lambda: build_positive_control_ocr_contact_drafts(config, write=True),
        write=write,
        errors=errors,
        missing_error="no positive-control OCR contact drafts found",
    )
    side_pair = _load_or_create_report(
        root=corpus_root / "side_pair_evidence",
        pattern="*/side_pair_evidence.json",
        create=lambda: build_positive_control_side_pair_evidence(config, write=True),
        write=write,
        errors=errors,
        missing_error="no positive-control side-pair evidence found",
    )
    review_loop = _load_or_create_report(
        root=corpus_root / "training_review_loops",
        pattern="*/training_review_loop.json",
        create=lambda: build_positive_control_training_review_loop(config, write=True),
        write=write,
        errors=errors,
        missing_error="no positive-control training review loop found",
    )
    prior_exit_gate = _latest_json(corpus_root / "exit_gates", "*/positive_corpus_exit_gate.json")
    negative_controls = _negative_control_summary(config)
    negative_replay = _latest_negative_replay_summary(config)
    decision = _decision(
        errors=errors,
        labels=labels,
        scenarios=scenarios,
        recognition=recognition,
        crop=crop,
        ocr=ocr,
        side_pair=side_pair,
        review_loop=review_loop,
        negative_controls=negative_controls,
        negative_replay=negative_replay,
    )
    gate_id = (
        f"positive-control-resume-readiness-{utc_now().replace(':', '-')}-"
        f"{_reports_digest(labels, scenarios, recognition, crop, ocr, side_pair, review_loop, prior_exit_gate)}"
    )
    gate_dir = corpus_root / "resume_readiness_gates" / gate_id
    report_path = gate_dir / "resume_readiness_gate.json"
    payload: dict[str, Any] = {
        "schema": POSITIVE_CONTROL_RESUME_READINESS_GATE_SCHEMA,
        "generated_at": utc_now(),
        "state": decision["state"] if write else ("ready_for_runtime_resume_readiness_gate" if decision["state"] != "blocked" else "blocked"),
        "gate_id": gate_id,
        "label_inventory_id": labels.get("inventory_id"),
        "scenario_manifest_id": scenarios.get("manifest_id"),
        "recognition_replay_id": recognition.get("replay_id"),
        "crop_workbench_id": crop.get("workbench_id"),
        "ocr_draft_id": ocr.get("draft_id"),
        "side_pair_report_id": side_pair.get("report_id"),
        "training_review_loop_id": review_loop.get("loop_id"),
        "prior_exit_gate_state": prior_exit_gate.get("state"),
        "decision": decision,
        "operating_mode": decision["operating_mode"],
        "negative_control_summary": negative_controls,
        "negative_replay_summary": negative_replay,
        "counts": _counts(
            labels=labels,
            scenarios=scenarios,
            recognition=recognition,
            crop=crop,
            ocr=ocr,
            side_pair=side_pair,
            review_loop=review_loop,
            negative_controls=negative_controls,
            negative_replay=negative_replay,
            blockers=decision["blocking_requirements"],
            errors=errors,
        ),
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
            "positive_control_resume_readiness_gate": "positive-control-resume-readiness-gate --json",
            "positive_control_resume_readiness_gate_preview": (
                "positive-control-resume-readiness-gate --no-write --json"
            ),
            "positive_control_training_review_loop": "positive-control-training-review-loop --json",
            "negative_control_recognition_replay": "negative-control-recognition-replay --max-pages-per-pdf 1 --pdf-dpi 100 --json",
        },
        "explicit_stop_conditions": [
            "This gate reports readiness only; it does not change classifier thresholds.",
            "This gate does not resume broad unknown-document autodetection.",
            "Known-card crop/OCR processing may continue only for operator-declared positive controls.",
            "Broad autodetection requires resolved positive-control review items and passing negative-control replay.",
            "Do not route, enrich, create sink payloads, write contacts, read back sinks, search public web, call paid providers, or select live targets.",
        ],
    }
    if write and decision["state"] != "blocked":
        _ensure_runtime_output_not_repo(corpus_root)
        gate_dir.mkdir(parents=True, exist_ok=True)
        report_payload = payload | {"runtime_artifact_written": True, "report_path": str(report_path)}
        report_path.write_text(json.dumps(report_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        payload["runtime_artifact_written"] = True
        payload["report_path"] = str(report_path)
    return payload


def _decision(
    *,
    errors: list[dict[str, Any]],
    labels: dict[str, Any],
    scenarios: dict[str, Any],
    recognition: dict[str, Any],
    crop: dict[str, Any],
    ocr: dict[str, Any],
    side_pair: dict[str, Any],
    review_loop: dict[str, Any],
    negative_controls: dict[str, Any],
    negative_replay: dict[str, Any],
) -> dict[str, Any]:
    blockers: list[str] = []
    if errors:
        blockers.append("required Plan 0099 evidence reports are missing")
    if _positive_source_count(labels) <= 0:
        blockers.append("positive-control label inventory is empty")
    if int(scenarios.get("scenario_count") or 0) <= 0:
        blockers.append("positive-control generated scenario manifest is missing")
    after_counts = dict(recognition.get("after_counts") or {})
    false_negatives = int(after_counts.get("not_business_card_high_confidence") or 0) + int(
        after_counts.get("indeterminate_needs_app_intelligence") or 0
    )
    if false_negatives > 0:
        blockers.append("known-positive recognition cases still require review or deterministic tuning")
    crop_counts = dict(crop.get("counts") or {})
    if int(crop_counts.get("crop_review_requests") or 0) > 0:
        blockers.append("known-positive crop review requests remain open")
    ocr_counts = dict(ocr.get("counts") or {})
    if int(ocr_counts.get("missing_ocr") or 0) > 0:
        blockers.append("known-positive OCR output is missing for accepted crop candidates")
    side_counts = dict(side_pair.get("counts") or {})
    if int(side_counts.get("app_intelligence_review_requests") or 0) > 0:
        blockers.append("front/back side-pair review requests remain open")
    review_counts = dict(review_loop.get("counts") or {})
    if int(review_counts.get("training_candidates") or 0) > 0:
        blockers.append("agent review-loop training candidates require targeted tests before promotion")
    if negative_controls["source_count"] <= 0:
        blockers.append("negative-control corpus is required before broad autodetection reconsideration")
    elif not negative_replay["report_present"]:
        blockers.append("negative-control recognition replay is required before broad autodetection reconsideration")
    elif negative_replay["false_positive_cases"] > 0:
        blockers.append("negative-control false positives remain unresolved")
    if errors and _positive_source_count(labels) <= 0:
        state = "blocked"
    elif blockers:
        state = "known_card_only_training_required"
    else:
        state = "ready_for_bounded_autodetection_pilot_plan"
    return {
        "state": state,
        "operating_mode": "known_card_only" if blockers else "bounded_autodetection_pilot_candidate",
        "known_card_crop_ocr_allowed": int(crop_counts.get("accepted_for_ocr_workbench") or 0) > 0,
        "broad_autodetection_resume_allowed": not blockers,
        "threshold_change_allowed": (
            not blockers
            and negative_replay["report_present"]
            and negative_replay["false_positive_cases"] == 0
        ),
        "blocking_requirements": blockers,
        "required_before_resume": [
            "resolve or fixture known-positive recognition review items",
            "resolve crop and OCR evidence gaps for known positives",
            "resolve ambiguous or conflicting side-pair graphs",
            "promote agent training candidates only after targeted tests and replay metrics",
            "keep negative-control replay passing before threshold changes",
        ],
        "next_plan_required": (
            "Continue known-card-only processing and resolve Plan 0099 training candidates."
            if blockers
            else "Write a separate bounded autodetection pilot plan before changing thresholds."
        ),
    }


def _counts(
    *,
    labels: dict[str, Any],
    scenarios: dict[str, Any],
    recognition: dict[str, Any],
    crop: dict[str, Any],
    ocr: dict[str, Any],
    side_pair: dict[str, Any],
    review_loop: dict[str, Any],
    negative_controls: dict[str, Any],
    negative_replay: dict[str, Any],
    blockers: list[str],
    errors: list[dict[str, Any]],
) -> dict[str, int]:
    recognition_after = dict(recognition.get("after_counts") or {})
    crop_counts = dict(crop.get("counts") or {})
    ocr_counts = dict(ocr.get("counts") or {})
    side_counts = dict(side_pair.get("counts") or {})
    review_counts = dict(review_loop.get("counts") or {})
    return {
        "positive_sources": _positive_source_count(labels),
        "scenario_plans": int(scenarios.get("scenario_count") or 0),
        "known_positive_false_negative_or_review_cases": int(
            recognition_after.get("not_business_card_high_confidence") or 0
        )
        + int(recognition_after.get("indeterminate_needs_app_intelligence") or 0),
        "crop_review_requests": int(crop_counts.get("crop_review_requests") or 0),
        "accepted_crop_candidates": int(crop_counts.get("accepted_for_ocr_workbench") or 0),
        "missing_ocr": int(ocr_counts.get("missing_ocr") or 0),
        "side_pair_review_requests": int(side_counts.get("app_intelligence_review_requests") or 0),
        "training_review_items": int(review_counts.get("review_items") or 0),
        "training_candidates": int(review_counts.get("training_candidates") or 0),
        "negative_control_sources": negative_controls["source_count"],
        "negative_false_positive_cases": negative_replay["false_positive_cases"],
        "blocking_requirements": len(blockers),
        "errors": len(errors),
    }


def _load_or_create_report(
    *,
    root: Path,
    pattern: str,
    create: Callable[[], dict[str, Any]],
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


def _positive_source_count(labels: dict[str, Any]) -> int:
    return int(labels.get("source_count") or labels.get("entry_count") or 0)


def _latest_json(root: Path, pattern: str) -> dict[str, Any]:
    path = _latest_report(root, pattern=pattern)
    return _read_json(path) if path else {}


def _negative_control_summary(config: AppConfig) -> dict[str, Any]:
    rows = _read_jsonl(config.data_dir / "negative_control_corpus" / "index.jsonl")
    categories: dict[str, int] = {}
    for row in rows:
        category = str(row.get("category") or row.get("label") or "unknown")
        categories[category] = categories.get(category, 0) + 1
    return {
        "state": "present" if rows else "missing",
        "source_count": len(rows),
        "categories": dict(sorted(categories.items())),
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
    raise ValueError(f"positive control resume readiness output root is inside the repo: {output_root}")


def _reports_digest(*reports: dict[str, Any]) -> str:
    digest = hashlib.sha256()
    for report in reports:
        for key in ("inventory_id", "manifest_id", "replay_id", "workbench_id", "draft_id", "report_id", "loop_id"):
            digest.update(str(report.get(key) or "").encode("utf-8"))
    return digest.hexdigest()[:12] if any(reports) else "no-reports"
