from __future__ import annotations

import argparse
import json
from pathlib import Path

from .api import create_app
from .config import load_config, write_default_config
from .mcp import call_tool, manifest_json
from .mcp_server import serve_jsonl
from .service import BusinessCardService
from .service_ops import install_user_service, service_status, uninstall_user_service
from .watcher import PollingWatcher


def _render_phase_report_text(payload: dict[str, object]) -> str:
    dashboard = dict(payload.get("dashboard_summary") or {})
    preview = dict(payload.get("review_workbook_preview") or {})
    lines = [
        f"Run: {payload.get('run_id')}",
        f"State: {payload.get('run_state')}",
        f"Jobs: {payload.get('job_count')}",
        f"Status: {dashboard.get('status_line') or 'unknown'}",
        f"Review workbook preview: {preview.get('state') or dashboard.get('review_workbook_preview_state') or 'unknown'}",
    ]
    phase_groups = [
        ("Blocked phases", dashboard.get("blocked_phases")),
        ("Explicit-required phases", dashboard.get("explicit_required_phases")),
        ("Pending phases", dashboard.get("pending_phases")),
        ("Complete phases", dashboard.get("complete_phases")),
    ]
    for label, entries in phase_groups:
        rows = entries if isinstance(entries, list) else []
        if rows:
            formatted = ", ".join(f"{row.get('phase')}={row.get('count')}" for row in rows if isinstance(row, dict))
        else:
            formatted = "none"
        lines.append(f"{label}: {formatted}")
    return "\n".join(lines) + "\n"


def _render_pilot_readiness_report_text(payload: dict[str, object]) -> str:
    counts = dict(payload.get("counts") or {})
    lines = [
        f"Run: {payload.get('run_id')}",
        f"State: {payload.get('state')}",
        f"Jobs: {payload.get('job_count')}",
        "Readiness: "
        f"ready_for_write_pilot={counts.get('ready_for_write_pilot', 0)} "
        f"safe_auto_available={counts.get('safe_auto_available', 0)} "
        f"explicit_operator_required={counts.get('explicit_operator_required', 0)} "
        f"blocked={counts.get('blocked', 0)} "
        f"complete={counts.get('complete', 0)}",
        "Pilot evidence: "
        f"write_complete={counts.get('write_pilot_complete', 0)} "
        f"readback_complete={counts.get('readback_complete', 0)} "
        f"pilot_report_complete={counts.get('pilot_report_complete', 0)}",
    ]
    return "\n".join(lines) + "\n"


def _render_live_pilot_status_text(payload: dict[str, object]) -> str:
    counts = dict(payload.get("counts") or {})
    entries = payload.get("entries") or []
    lines = [
        f"Run: {payload.get('run_id')}",
        f"State: {payload.get('state')}",
        f"Jobs: {payload.get('job_count')}",
        "Counts: "
        + " ".join(f"{key}={value}" for key, value in sorted(counts.items()))
        if counts
        else "Counts: none",
        "Observed: "
        f"writes={payload.get('observed_writes_attempted', 0)} "
        f"network={payload.get('observed_network_calls_made', 0)}",
    ]
    for entry in entries if isinstance(entries, list) else []:
        if isinstance(entry, dict):
            lines.append(
                " - "
                f"{entry.get('job_id')} "
                f"state={entry.get('state')} "
                f"sink={entry.get('selected_target_sink') or 'none'} "
                f"closeout={entry.get('closeout_state') or 'none'}"
            )
    return "\n".join(lines) + "\n"


def _render_live_pilot_handoff_text(payload: dict[str, object]) -> str:
    action_counts = dict(payload.get("action_counts") or {})
    entries = payload.get("entries") or []
    lines = [
        f"Run: {payload.get('run_id')}",
        f"State: {payload.get('state')}",
        f"Jobs: {payload.get('job_count')}",
        "Actions: "
        + " ".join(f"{key}={value}" for key, value in sorted(action_counts.items()))
        if action_counts
        else "Actions: none",
    ]
    for entry in entries if isinstance(entries, list) else []:
        if isinstance(entry, dict):
            lines.append(
                " - "
                f"{entry.get('job_id')} "
                f"next={entry.get('next_action')} "
                f"target={entry.get('selected_target_identity') or 'none'} "
                f"abandonment={entry.get('abandonment_identity') or 'none'} "
                f"operator_required={entry.get('operator_required')} "
                f"command={entry.get('command') or 'none'}"
            )
    return "\n".join(lines) + "\n"


def _render_run_summary_text(payload: dict[str, object]) -> str:
    enrichment_budget = dict(payload.get("enrichment_budget") or {})
    public_web = dict(enrichment_budget.get("public_web") or {})
    paid_provider = dict(enrichment_budget.get("paid_provider") or {})
    sink_pilot = dict(payload.get("sink_pilot_summary") or {})
    preview = dict(payload.get("review_workbook_preview_summary") or {})
    lines = [
        f"Run: {payload.get('run_id')}",
        f"State: {payload.get('state')}",
        f"Jobs: {payload.get('job_count')}",
        f"Needs review: {payload.get('needs_review_count')}",
        f"Ready to route: {payload.get('ready_to_route_count')}",
        f"Failed: {payload.get('failed_count')}",
        "Enrichment: "
        f"public_web_requests={public_web.get('request_count', 0)} "
        f"paid_provider_requests={paid_provider.get('request_count', 0)} "
        f"paid_api_calls_attempted={paid_provider.get('paid_api_calls_attempted', 0)}",
        "Sink pilots: "
        f"write={sink_pilot.get('write_pilot_count', 0)} "
        f"readback={sink_pilot.get('readback_pilot_count', 0)} "
        f"reports={sink_pilot.get('pilot_report_count', 0)} "
        f"complete_reports={sink_pilot.get('complete_report_count', 0)}",
        "Review workbook preview: "
        f"has_preview={preview.get('has_preview', False)} "
        f"latest_valid={preview.get('latest_valid')} "
        f"errors={preview.get('latest_error_count', 0)} "
        f"warnings={preview.get('latest_warning_count', 0)}",
    ]
    return "\n".join(lines) + "\n"


def _render_runtime_readiness_text(payload: dict[str, object]) -> str:
    checks = payload.get("checks") or []
    blocked = payload.get("blocked_checks") or []
    warnings = payload.get("warning_checks") or []
    config = dict(payload.get("config") or {})
    service = dict(payload.get("service") or {})
    watch = dict(payload.get("watch") or {})
    lines = [
        f"Runtime readiness: {payload.get('state')}",
        f"Config: {config.get('config_path')} exists={config.get('config_exists')}",
        f"Data: {config.get('data_dir')}",
        f"Service: installed={service.get('installed')} unit={service.get('unit_path')}",
        "Watch: "
        f"inputs={len(watch.get('inputs') or [])} "
        f"backlog={watch.get('backlog_count', 0)} "
        f"unsettled={watch.get('unsettled_count', 0)} "
        f"last_error={watch.get('last_error') or 'none'}",
        f"Checks: total={len(checks) if isinstance(checks, list) else 0} "
        f"blocked={len(blocked) if isinstance(blocked, list) else 0} "
        f"warnings={len(warnings) if isinstance(warnings, list) else 0}",
    ]
    return "\n".join(lines) + "\n"


def _render_service_recovery_text(payload: dict[str, object]) -> str:
    commands = dict(payload.get("commands") or {})
    blocked = payload.get("blocked_reasons") or []
    safe_actions = payload.get("safe_next_actions") or []
    explicit_actions = payload.get("explicit_operator_actions") or []
    lines = [
        f"Service recovery: {payload.get('state')}",
        f"Run: {payload.get('run_id') or 'none'}",
        f"Service installed: {dict(payload.get('service') or {}).get('installed')}",
        f"Watch last error: {dict(payload.get('watch') or {}).get('last_error') or 'none'}",
        f"Blocked reasons: {len(blocked) if isinstance(blocked, list) else 0}",
        f"Safe next actions: {len(safe_actions) if isinstance(safe_actions, list) else 0}",
        f"Explicit operator actions: {len(explicit_actions) if isinstance(explicit_actions, list) else 0}",
        f"Install: {commands.get('install')}",
        f"Start: {commands.get('start')}",
        f"Status: {commands.get('status')}",
        f"Restart: {commands.get('restart')}",
        f"Resume: {commands.get('resume')}",
        f"Recover: {commands.get('recover')}",
    ]
    return "\n".join(lines) + "\n"


def _render_live_target_candidates_text(payload: dict[str, object]) -> str:
    candidates = payload.get("candidates") or []
    rows = candidates if isinstance(candidates, list) else []
    lines = [
        f"Live target candidates: {payload.get('candidate_count', 0)}",
        f"Ready: {payload.get('ready_candidate_count', 0)}",
        f"Blocked: {payload.get('blocked_candidate_count', 0)}",
    ]
    for candidate in rows:
        if not isinstance(candidate, dict):
            continue
        stops = candidate.get("stop_reasons") or []
        stop_text = "; ".join(str(item) for item in stops) if isinstance(stops, list) and stops else "none"
        lines.append(
            " - "
            f"{candidate.get('run_id')}/{candidate.get('job_id')} "
            f"sink={candidate.get('sink')} "
            f"state={candidate.get('state')} "
            f"lookup={candidate.get('lookup_readiness_state')} "
            f"stops={stop_text}"
        )
    return "\n".join(lines) + "\n"


def _render_live_readiness_audit_text(payload: dict[str, object]) -> str:
    lines = [
        f"Live readiness audit: {payload.get('state')}",
        f"Run: {payload.get('run_id') or 'none'}",
        f"Sink: {payload.get('sink') or 'all'}",
        f"Runtime: {payload.get('runtime_readiness_state')}",
        f"Service recovery: {payload.get('service_recovery_state')}",
        f"Pilot readiness: {payload.get('pilot_readiness_state') or 'none'}",
        f"Candidates: {payload.get('candidate_count', 0)}",
        f"Ready candidates: {payload.get('ready_candidate_count', 0)}",
        f"Blocked candidates: {payload.get('blocked_candidate_count', 0)}",
    ]
    if payload.get("audit_path"):
        lines.append(f"Audit path: {payload.get('audit_path')}")
    blocked = payload.get("blocked_reasons") or []
    rows = blocked if isinstance(blocked, list) else []
    lines.append(f"Blocked reasons: {len(rows)}")
    for reason in rows:
        lines.append(f" - {reason}")
    return "\n".join(lines) + "\n"


def _render_live_selection_requirements_text(payload: dict[str, object]) -> str:
    entries = payload.get("entries") or []
    rows = entries if isinstance(entries, list) else []
    state_counts = dict(payload.get("state_counts") or {})
    lines = [
        f"Live selection requirements: {payload.get('state')}",
        f"Run: {payload.get('run_id') or 'all'}",
        f"Sink: {payload.get('sink') or 'all'}",
        f"Candidates: {payload.get('candidate_count', 0)}",
        "States: "
        + " ".join(f"{key}={value}" for key, value in sorted(state_counts.items()))
        if state_counts
        else "States: none",
    ]
    for entry in rows:
        if not isinstance(entry, dict):
            continue
        missing = entry.get("missing_operator_fields") or []
        missing_text = ",".join(str(item) for item in missing) if isinstance(missing, list) and missing else "none"
        lines.append(
            " - "
            f"{entry.get('run_id')}/{entry.get('job_id')} "
            f"sink={entry.get('sink')} "
            f"state={entry.get('state')} "
            f"target={entry.get('selected_target_identity') or 'none'} "
            f"abandonment={entry.get('abandonment_identity') or 'none'} "
            f"missing={missing_text}"
        )
    if payload.get("requirements_path"):
        lines.append(f"Requirements path: {payload.get('requirements_path')}")
    return "\n".join(lines) + "\n"


def _render_review_queue_text(entries: list[dict[str, object]]) -> str:
    lines = [f"Review queue: {len(entries)} jobs"]
    if not entries:
        return "\n".join(lines) + "\n"
    for entry in entries:
        next_action = dict(entry.get("next_action") or {})
        artifact_kinds = entry.get("artifact_kinds") or []
        artifacts = ",".join(str(kind) for kind in artifact_kinds) if isinstance(artifact_kinds, list) else ""
        lines.append(
            " - "
            f"{entry.get('job_id')} "
            f"state={entry.get('state')} "
            f"next={next_action.get('action') or 'none'} "
            f"artifacts={artifacts or 'none'}"
        )
    return "\n".join(lines) + "\n"


def _render_jobs_list_text(entries: list[dict[str, object]]) -> str:
    lines = [f"Jobs: {len(entries)}"]
    for entry in entries:
        lines.append(
            " - "
            f"{entry.get('job_id')} "
            f"run={entry.get('run_id')} "
            f"state={entry.get('state')} "
            f"image={entry.get('image_path')}"
        )
    return "\n".join(lines) + "\n"


def _render_job_show_text(payload: dict[str, object]) -> str:
    artifacts = payload.get("artifacts") or []
    artifact_kinds = [
        str(artifact.get("kind"))
        for artifact in artifacts
        if isinstance(artifact, dict) and artifact.get("kind")
    ]
    lines = [
        f"Job: {payload.get('job_id')}",
        f"Run: {payload.get('run_id')}",
        f"State: {payload.get('state')}",
        f"Image: {payload.get('image_path')}",
        f"Artifacts: {','.join(sorted(artifact_kinds)) if artifact_kinds else 'none'}",
    ]
    if payload.get("error"):
        lines.append(f"Error: {payload.get('error')}")
    return "\n".join(lines) + "\n"


def _render_runs_list_text(entries: list[dict[str, object]]) -> str:
    lines = [f"Runs: {len(entries)}"]
    for entry in entries:
        lines.append(
            " - "
            f"{entry.get('run_id')} "
            f"state={entry.get('state')} "
            f"jobs={entry.get('job_count')} "
            f"updated={entry.get('updated_at') or 'unknown'}"
        )
    return "\n".join(lines) + "\n"


def _render_run_show_text(payload: dict[str, object]) -> str:
    jobs = payload.get("jobs") or []
    artifacts = payload.get("artifacts") or []
    lines = [
        f"Run: {payload.get('run_id')}",
        f"State: {payload.get('state')}",
        f"Jobs: {payload.get('job_count')}",
        f"Loaded jobs: {len(jobs) if isinstance(jobs, list) else 0}",
        f"Artifacts: {len(artifacts) if isinstance(artifacts, list) else 0}",
        f"Run dir: {payload.get('run_dir')}",
    ]
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bcw")
    parser.add_argument("--config", type=Path, default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-config")

    status = sub.add_parser("status")
    status.add_argument("--json", action="store_true")

    doctor = sub.add_parser("doctor")
    doctor.add_argument("--json", action="store_true")

    runtime_readiness = sub.add_parser("runtime-readiness")
    runtime_readiness.add_argument("--json", action="store_true")

    live_target_candidates = sub.add_parser("live-target-candidates")
    live_target_candidates.add_argument("--run-id", default=None)
    live_target_candidates.add_argument("--sink", choices=["google_contacts", "odoo"], default=None)
    live_target_candidates.add_argument("--json", action="store_true")

    live_readiness_audit = sub.add_parser("live-readiness-audit")
    live_readiness_audit.add_argument("--run-id", default=None)
    live_readiness_audit.add_argument("--sink", choices=["google_contacts", "odoo"], default=None)
    live_readiness_audit.add_argument("--no-write", action="store_true")
    live_readiness_audit.add_argument("--json", action="store_true")
    live_selection_requirements = sub.add_parser("live-selection-requirements")
    live_selection_requirements.add_argument("--run-id", default=None)
    live_selection_requirements.add_argument("--sink", choices=["google_contacts", "odoo"], default=None)
    live_selection_requirements.add_argument("--no-write", action="store_true")
    live_selection_requirements.add_argument("--json", action="store_true")

    process = sub.add_parser("process")
    process.add_argument("source")
    process.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True)
    process.add_argument("--workers", type=int, default=2)

    runs = sub.add_parser("runs")
    runs_sub = runs.add_subparsers(dest="runs_command", required=True)
    runs_list = runs_sub.add_parser("list")
    runs_list.add_argument("--json", action="store_true")
    runs_show = runs_sub.add_parser("show")
    runs_show.add_argument("run_id")
    runs_show.add_argument("--json", action="store_true")
    runs_summary = runs_sub.add_parser("summary")
    runs_summary.add_argument("run_id")
    runs_summary.add_argument("--json", action="store_true")
    runs_phase_report = runs_sub.add_parser("phase-report")
    runs_phase_report.add_argument("run_id")
    runs_phase_report.add_argument("--json", action="store_true")
    runs_pilot_readiness = runs_sub.add_parser("pilot-readiness")
    runs_pilot_readiness.add_argument("run_id")
    runs_pilot_readiness.add_argument("--json", action="store_true")
    runs_live_pilot_status = runs_sub.add_parser("live-pilot-status")
    runs_live_pilot_status.add_argument("run_id")
    runs_live_pilot_status.add_argument("--no-write", action="store_true")
    runs_live_pilot_status.add_argument("--json", action="store_true")
    runs_live_pilot_handoff = runs_sub.add_parser("live-pilot-handoff")
    runs_live_pilot_handoff.add_argument("run_id")
    runs_live_pilot_handoff.add_argument("--no-write", action="store_true")
    runs_live_pilot_handoff.add_argument("--json", action="store_true")

    jobs = sub.add_parser("jobs")
    jobs_sub = jobs.add_subparsers(dest="jobs_command", required=True)
    jobs_list = jobs_sub.add_parser("list")
    jobs_list.add_argument("--run-id", default=None)
    jobs_list.add_argument("--json", action="store_true")
    jobs_show = jobs_sub.add_parser("show")
    jobs_show.add_argument("job_id")
    jobs_show.add_argument("--run-id", default=None)
    jobs_show.add_argument("--json", action="store_true")
    jobs_review = jobs_sub.add_parser("review")
    jobs_review.add_argument("job_id")
    jobs_review.add_argument("--run-id", required=True)
    jobs_review.add_argument("--reviewer", default="operator")
    jobs_review.add_argument(
        "--action",
        choices=[
            "approve_for_routing",
            "approve_enrichment_merge",
            "keep_needs_review",
            "request_enrichment",
            "resolve_duplicate",
            "reject_not_card",
            "skip",
        ],
        default="keep_needs_review",
    )
    jobs_review.add_argument("--field-corrections-json", default="{}")
    jobs_review.add_argument("--crop-selection-json", default="{}")
    jobs_review.add_argument("--approved-enrichment-fields-json", default="[]")
    jobs_review.add_argument("--duplicate-resolution-json", default="{}")
    jobs_review.add_argument("--notes", default="")
    jobs_review.add_argument("--json", action="store_true")

    reviews = sub.add_parser("reviews")
    reviews_sub = reviews.add_subparsers(dest="reviews_command", required=True)
    reviews_list = reviews_sub.add_parser("list")
    reviews_list.add_argument("--run-id", default=None)
    reviews_list.add_argument("--state", default="needs_review")
    reviews_list.add_argument("--next-action", default=None)
    reviews_list.add_argument("--artifact-kind", default=None)
    reviews_list.add_argument("--json", action="store_true")
    reviews_bundle = reviews_sub.add_parser("bundle")
    reviews_bundle.add_argument("--run-id", required=True)
    reviews_bundle.add_argument("--state", default="all")
    reviews_bundle.add_argument("--no-write", action="store_true")
    reviews_bundle.add_argument("--json", action="store_true")
    reviews_html = reviews_sub.add_parser("html")
    reviews_html.add_argument("--run-id", required=True)
    reviews_html.add_argument("--state", default="all")
    reviews_html.add_argument("--no-write", action="store_true")
    reviews_html.add_argument("--json", action="store_true")
    reviews_workbook = reviews_sub.add_parser("workbook")
    reviews_workbook.add_argument("--run-id", required=True)
    reviews_workbook.add_argument("--state", default="all")
    reviews_workbook.add_argument("--no-write", action="store_true")
    reviews_workbook.add_argument("--json", action="store_true")
    reviews_preview_validation = reviews_sub.add_parser("preview-validation")
    reviews_preview_validation.add_argument("--run-id", required=True)
    reviews_preview_validation.add_argument("--reviewer", default="operator")
    reviews_preview_validation.add_argument("--decisions-csv-file", type=Path, required=True)
    reviews_preview_validation.add_argument("--write-artifacts", action="store_true")
    reviews_preview_validation.add_argument("--json", action="store_true")
    reviews_apply = reviews_sub.add_parser("apply-decisions")
    reviews_apply.add_argument("--run-id", required=True)
    reviews_apply.add_argument("--reviewer", default="operator")
    reviews_apply.add_argument("--decisions-json", default="[]")
    reviews_apply.add_argument("--decisions-file", type=Path, default=None)
    reviews_apply.add_argument("--decisions-csv-file", type=Path, default=None)
    reviews_apply.add_argument("--preview", action="store_true")
    reviews_apply.add_argument("--preview-write", action="store_true")
    reviews_apply.add_argument("--json", action="store_true")

    actions = sub.add_parser("actions")
    actions_sub = actions.add_subparsers(dest="actions_command", required=True)
    actions_run_next = actions_sub.add_parser("run-next")
    actions_run_next.add_argument("--run-id", default=None)
    actions_run_next.add_argument("--limit", type=int, default=10)
    actions_run_next.add_argument("--json", action="store_true")

    sinks = sub.add_parser("sinks")
    sinks_sub = sinks.add_subparsers(dest="sinks_command", required=True)
    sinks_check = sinks_sub.add_parser("check")
    sinks_check.add_argument("--json", action="store_true")
    sinks_lookup_plan = sinks_sub.add_parser("lookup-plan")
    sinks_lookup_plan.add_argument("job_id")
    sinks_lookup_plan.add_argument("--run-id", required=True)
    sinks_lookup_plan.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True)
    sinks_lookup_plan.add_argument("--json", action="store_true")
    sinks_plan = sinks_sub.add_parser("plan")
    sinks_plan.add_argument("job_id")
    sinks_plan.add_argument("--run-id", required=True)
    sinks_plan.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True)
    sinks_plan.add_argument("--json", action="store_true")
    sinks_apply_preflight = sinks_sub.add_parser("apply-preflight")
    sinks_apply_preflight.add_argument("job_id")
    sinks_apply_preflight.add_argument("--run-id", required=True)
    sinks_apply_preflight.add_argument("--apply", action=argparse.BooleanOptionalAction, default=False)
    sinks_apply_preflight.add_argument("--json", action="store_true")
    sinks_apply = sinks_sub.add_parser("apply")
    sinks_apply.add_argument("job_id")
    sinks_apply.add_argument("--run-id", required=True)
    sinks_apply.add_argument("--apply", action=argparse.BooleanOptionalAction, default=False)
    sinks_apply.add_argument("--simulate", action=argparse.BooleanOptionalAction, default=False)
    sinks_apply.add_argument("--json", action="store_true")
    sinks_apply_pilot_readiness = sinks_sub.add_parser("apply-pilot-readiness")
    sinks_apply_pilot_readiness.add_argument("job_id")
    sinks_apply_pilot_readiness.add_argument("--run-id", required=True)
    sinks_apply_pilot_readiness.add_argument("--sink", choices=["google_contacts", "odoo"], default=None)
    sinks_apply_pilot_readiness.add_argument("--json", action="store_true")
    sinks_apply_pilot_report = sinks_sub.add_parser("apply-pilot-report")
    sinks_apply_pilot_report.add_argument("job_id")
    sinks_apply_pilot_report.add_argument("--run-id", required=True)
    sinks_apply_pilot_report.add_argument("--json", action="store_true")
    sinks_apply_pilot_bundle = sinks_sub.add_parser("apply-pilot-bundle")
    sinks_apply_pilot_bundle.add_argument("job_id")
    sinks_apply_pilot_bundle.add_argument("--run-id", required=True)
    sinks_apply_pilot_bundle.add_argument("--sink", choices=["google_contacts", "odoo"], required=True)
    sinks_apply_pilot_bundle.add_argument("--operator", default="operator")
    sinks_apply_pilot_bundle.add_argument("--json", action="store_true")
    sinks_apply_decision = sinks_sub.add_parser("apply-decision")
    sinks_apply_decision.add_argument("job_id")
    sinks_apply_decision.add_argument("--run-id", required=True)
    sinks_apply_decision.add_argument("--decision", choices=["approve", "reject", "noop"], required=True)
    sinks_apply_decision.add_argument("--reviewer", default="operator")
    sinks_apply_decision.add_argument("--reason", default="")
    sinks_apply_decision.add_argument("--json", action="store_true")
    sinks_adapter_request = sinks_sub.add_parser("adapter-request")
    sinks_adapter_request.add_argument("job_id")
    sinks_adapter_request.add_argument("--run-id", required=True)
    sinks_adapter_request.add_argument("--phase", choices=["lookup", "write", "readback"], default="lookup")
    sinks_adapter_request.add_argument("--json", action="store_true")
    sinks_lookup_result = sinks_sub.add_parser("lookup-result")
    sinks_lookup_result.add_argument("job_id")
    sinks_lookup_result.add_argument("--run-id", required=True)
    sinks_lookup_result.add_argument("--matches-by-sink-json", default="{}")
    sinks_lookup_result.add_argument("--json", action="store_true")
    sinks_lookup_pilot = sinks_sub.add_parser("lookup-pilot")
    sinks_lookup_pilot.add_argument("job_id")
    sinks_lookup_pilot.add_argument("--run-id", required=True)
    sinks_lookup_pilot.add_argument("--sink", choices=["google_contacts", "odoo"], required=True)
    sinks_lookup_pilot.add_argument("--approved-by", required=True)
    sinks_lookup_pilot.add_argument("--matches-json", default="[]")
    sinks_lookup_pilot.add_argument("--simulate", action=argparse.BooleanOptionalAction, default=True)
    sinks_lookup_pilot.add_argument("--json", action="store_true")
    sinks_lookup_readiness = sinks_sub.add_parser("lookup-readiness")
    sinks_lookup_readiness.add_argument("job_id")
    sinks_lookup_readiness.add_argument("--run-id", required=True)
    sinks_lookup_readiness.add_argument("--sink", choices=["google_contacts", "odoo"], required=True)
    sinks_lookup_readiness.add_argument("--json", action="store_true")
    sinks_lookup_smoke_handoff = sinks_sub.add_parser("lookup-smoke-handoff")
    sinks_lookup_smoke_handoff.add_argument("job_id")
    sinks_lookup_smoke_handoff.add_argument("--run-id", required=True)
    sinks_lookup_smoke_handoff.add_argument("--sink", choices=["google_contacts", "odoo"], required=True)
    sinks_lookup_smoke_handoff.add_argument("--approved-by", default="operator")
    sinks_lookup_smoke_handoff.add_argument("--json", action="store_true")
    sinks_live_selection_packet = sinks_sub.add_parser("live-selection-packet")
    sinks_live_selection_packet.add_argument("job_id")
    sinks_live_selection_packet.add_argument("--run-id", required=True)
    sinks_live_selection_packet.add_argument("--sink", choices=["google_contacts", "odoo"], required=True)
    sinks_live_selection_packet.add_argument("--operator", required=True)
    sinks_live_selection_packet.add_argument("--scope", choices=["lookup", "write", "readback", "all"], default="lookup")
    sinks_live_selection_packet.add_argument("--reason", default="")
    sinks_live_selection_packet.add_argument("--no-write", action="store_true")
    sinks_live_selection_packet.add_argument("--json", action="store_true")
    sinks_select_live_target = sinks_sub.add_parser("select-live-target")
    sinks_select_live_target.add_argument("job_id")
    sinks_select_live_target.add_argument("--run-id", required=True)
    sinks_select_live_target.add_argument("--sink", choices=["google_contacts", "odoo"], required=True)
    sinks_select_live_target.add_argument("--operator", required=True)
    sinks_select_live_target.add_argument("--scope", choices=["lookup", "write", "readback", "all"], default="lookup")
    sinks_select_live_target.add_argument("--reason", default="")
    sinks_select_live_target.add_argument("--safety-confirmation", required=True)
    sinks_select_live_target.add_argument("--json", action="store_true")
    sinks_selected_target_audit = sinks_sub.add_parser("selected-target-audit")
    sinks_selected_target_audit.add_argument("job_id")
    sinks_selected_target_audit.add_argument("--run-id", required=True)
    sinks_selected_target_audit.add_argument("--scope", choices=["lookup", "write", "readback", "all"], default=None)
    sinks_selected_target_audit.add_argument("--no-write", action="store_true")
    sinks_selected_target_audit.add_argument("--json", action="store_true")
    sinks_abandon_live_pilot = sinks_sub.add_parser("abandon-live-pilot")
    sinks_abandon_live_pilot.add_argument("job_id")
    sinks_abandon_live_pilot.add_argument("--run-id", required=True)
    sinks_abandon_live_pilot.add_argument("--operator", required=True)
    sinks_abandon_live_pilot.add_argument("--reason", required=True)
    sinks_abandon_live_pilot.add_argument("--json", action="store_true")
    sinks_execute_lookup_smoke = sinks_sub.add_parser("execute-lookup-smoke")
    sinks_execute_lookup_smoke.add_argument("job_id")
    sinks_execute_lookup_smoke.add_argument("--run-id", required=True)
    sinks_execute_lookup_smoke.add_argument("--json", action="store_true")
    sinks_write_pilot = sinks_sub.add_parser("write-pilot")
    sinks_write_pilot.add_argument("job_id")
    sinks_write_pilot.add_argument("--run-id", required=True)
    sinks_write_pilot.add_argument("--sink", choices=["google_contacts", "odoo"], required=True)
    sinks_write_pilot.add_argument("--approved-by", required=True)
    sinks_write_pilot.add_argument("--simulate", action=argparse.BooleanOptionalAction, default=True)
    sinks_write_pilot.add_argument("--json", action="store_true")
    sinks_readback_pilot = sinks_sub.add_parser("readback-pilot")
    sinks_readback_pilot.add_argument("job_id")
    sinks_readback_pilot.add_argument("--run-id", required=True)
    sinks_readback_pilot.add_argument("--sink", choices=["google_contacts", "odoo"], required=True)
    sinks_readback_pilot.add_argument("--approved-by", required=True)
    sinks_readback_pilot.add_argument("--readback-json", default="{}")
    sinks_readback_pilot.add_argument("--simulate", action=argparse.BooleanOptionalAction, default=True)
    sinks_readback_pilot.add_argument("--json", action="store_true")
    sinks_live_pilot_closeout = sinks_sub.add_parser("live-pilot-closeout")
    sinks_live_pilot_closeout.add_argument("job_id")
    sinks_live_pilot_closeout.add_argument("--run-id", required=True)
    sinks_live_pilot_closeout.add_argument("--no-write", action="store_true")
    sinks_live_pilot_closeout.add_argument("--json", action="store_true")
    sinks_assess_duplicates = sinks_sub.add_parser("assess-duplicates")
    sinks_assess_duplicates.add_argument("job_id")
    sinks_assess_duplicates.add_argument("--run-id", required=True)
    sinks_assess_duplicates.add_argument("--json", action="store_true")

    enrichment = sub.add_parser("enrichment")
    enrichment_sub = enrichment.add_subparsers(dest="enrichment_command", required=True)
    enrichment_check = enrichment_sub.add_parser("check")
    enrichment_check.add_argument("--mode", choices=["none", "public_web", "api", "all"], default=None)
    enrichment_check.add_argument("--allow-paid-enrichment", action="store_true")
    enrichment_check.add_argument("--json", action="store_true")
    enrichment_request = enrichment_sub.add_parser("request")
    enrichment_request.add_argument("job_id")
    enrichment_request.add_argument("--run-id", required=True)
    enrichment_request.add_argument("--mode", choices=["public_web", "api", "all"], default="public_web")
    enrichment_request.add_argument("--requested-by", default="operator")
    enrichment_request.add_argument("--allow-paid-enrichment", action="store_true")
    enrichment_request.add_argument("--public-web-results-json", default="[]")
    enrichment_request.add_argument("--provider-results-json", default="[]")
    enrichment_request.add_argument("--json", action="store_true")
    enrichment_public_web_results = enrichment_sub.add_parser("public-web-results")
    enrichment_public_web_results.add_argument("job_id")
    enrichment_public_web_results.add_argument("--run-id", required=True)
    enrichment_public_web_results.add_argument("--searched-by", default="operator")
    enrichment_public_web_results.add_argument("--results-json", default="[]")
    enrichment_public_web_results.add_argument("--json", action="store_true")
    enrichment_public_web_handoff = enrichment_sub.add_parser("public-web-handoff")
    enrichment_public_web_handoff.add_argument("job_id")
    enrichment_public_web_handoff.add_argument("--run-id", required=True)
    enrichment_public_web_handoff.add_argument("--json", action="store_true")
    enrichment_provider_handoff = enrichment_sub.add_parser("provider-handoff")
    enrichment_provider_handoff.add_argument("job_id")
    enrichment_provider_handoff.add_argument("--run-id", required=True)
    enrichment_provider_handoff.add_argument("--json", action="store_true")
    enrichment_provider_results = enrichment_sub.add_parser("provider-results")
    enrichment_provider_results.add_argument("job_id")
    enrichment_provider_results.add_argument("--run-id", required=True)
    enrichment_provider_results.add_argument("--provider", default="apollo")
    enrichment_provider_results.add_argument("--submitted-by", default="operator")
    enrichment_provider_results.add_argument("--results-json", default="[]")
    enrichment_provider_results.add_argument("--json", action="store_true")

    watch = sub.add_parser("watch")
    watch.add_argument("--once", action="store_true")
    watch.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True)
    watch.add_argument("--interval-seconds", type=float, default=10.0)
    watch.add_argument("--settle-seconds", type=float, default=None)

    watch_status = sub.add_parser("watch-status")
    watch_status.add_argument("--json", action="store_true")

    watch_dry_run = sub.add_parser("watch-dry-run")
    watch_dry_run.add_argument("--json", action="store_true")

    watch_reset = sub.add_parser("watch-reset")
    watch_reset.add_argument("--yes", action="store_true")

    api = sub.add_parser("api")
    api.add_argument("--host", default="127.0.0.1")
    api.add_argument("--port", type=int, default=8787)

    service = sub.add_parser("service")
    service_sub = service.add_subparsers(dest="service_command", required=True)
    service_status_parser = service_sub.add_parser("status")
    service_status_parser.add_argument("--json", action="store_true")
    service_install = service_sub.add_parser("install")
    service_install.add_argument("--json", action="store_true")
    service_uninstall = service_sub.add_parser("uninstall")
    service_uninstall.add_argument("--json", action="store_true")
    service_recovery = service_sub.add_parser("recovery")
    service_recovery.add_argument("--run-id", default=None)
    service_recovery.add_argument("--json", action="store_true")

    sub.add_parser("mcp-manifest")
    sub.add_parser("mcp-stdio")
    mcp_call = sub.add_parser("mcp-call")
    mcp_call.add_argument("tool_name")
    mcp_call.add_argument("--arguments-json", default="{}")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "init-config":
        print(write_default_config(args.config))
        return 0

    config = load_config(args.config)
    service = BusinessCardService(config)

    if args.command == "status":
        payload = service.status()
        print(json.dumps(payload, indent=2) if args.json else payload)
        return 0 if payload["skill_ready"] else 2

    if args.command == "doctor":
        payload = service.doctor()
        print(json.dumps(payload, indent=2) if args.json else payload)
        return 0 if payload["ok"] else 2

    if args.command == "runtime-readiness":
        payload = service.runtime_readiness()
        print(json.dumps(payload, indent=2) if args.json else _render_runtime_readiness_text(payload), end="")
        return 0 if payload["state"] != "blocked" else 2

    if args.command == "live-target-candidates":
        payload = service.live_target_candidates(run_id=args.run_id, sink=args.sink)
        print(json.dumps(payload, indent=2) if args.json else _render_live_target_candidates_text(payload), end="")
        return 0

    if args.command == "live-readiness-audit":
        payload = service.live_readiness_audit(
            run_id=args.run_id,
            sink=args.sink,
            write=not args.no_write,
        )
        print(json.dumps(payload, indent=2) if args.json else _render_live_readiness_audit_text(payload), end="")
        return 0

    if args.command == "live-selection-requirements":
        payload = service.live_selection_requirements(
            run_id=args.run_id,
            sink=args.sink,
            write=not args.no_write,
        )
        print(json.dumps(payload, indent=2) if args.json else _render_live_selection_requirements_text(payload), end="")
        return 0

    if args.command == "process":
        run = service.process_source(
            args.source,
            dry_run=args.dry_run,
            workers=args.workers,
        )
        print(json.dumps(run, indent=2))
        return 0

    if args.command == "runs":
        if args.runs_command == "list":
            payload = service.list_runs()
        elif args.runs_command == "summary":
            payload = service.run_summary(args.run_id)
        elif args.runs_command == "phase-report":
            payload = service.phase_report(args.run_id)
        elif args.runs_command == "pilot-readiness":
            payload = service.pilot_readiness_report(args.run_id)
        elif args.runs_command == "live-pilot-status":
            payload = service.live_pilot_status(run_id=args.run_id, write=not args.no_write)
        elif args.runs_command == "live-pilot-handoff":
            payload = service.live_pilot_handoff(run_id=args.run_id, write=not args.no_write)
        else:
            payload = service.get_run(args.run_id)
        if args.runs_command == "live-pilot-handoff" and not args.json:
            print(_render_live_pilot_handoff_text(payload), end="")
            return 0
        if args.runs_command == "live-pilot-status" and not args.json:
            print(_render_live_pilot_status_text(payload), end="")
            return 0
        if args.runs_command == "pilot-readiness" and not args.json:
            print(_render_pilot_readiness_report_text(payload), end="")
            return 0
        if args.runs_command == "phase-report" and not args.json:
            print(_render_phase_report_text(payload), end="")
            return 0
        if args.runs_command == "summary" and not args.json:
            print(_render_run_summary_text(payload), end="")
            return 0
        if args.runs_command == "list" and not args.json:
            print(_render_runs_list_text(payload), end="")
            return 0
        if args.runs_command == "show" and not args.json:
            print(_render_run_show_text(payload), end="")
            return 0
        print(json.dumps(payload, indent=2) if args.json else payload)
        return 0

    if args.command == "reviews":
        if args.reviews_command == "bundle":
            payload = service.review_bundle(run_id=args.run_id, state=args.state, write=not args.no_write)
        elif args.reviews_command == "html":
            payload = service.review_html(run_id=args.run_id, state=args.state, write=not args.no_write)
        elif args.reviews_command == "workbook":
            payload = service.review_workbook(run_id=args.run_id, state=args.state, write=not args.no_write)
            if not args.json:
                print(payload["csv"], end="")
                return 0
        elif args.reviews_command == "preview-validation":
            payload = service.preview_review_workbook_csv(
                run_id=args.run_id,
                reviewer=args.reviewer,
                csv_text=args.decisions_csv_file.read_text(encoding="utf-8"),
                write=args.write_artifacts,
            )
            if not args.json:
                print(payload["validation_csv"], end="")
                return 0
        elif args.reviews_command == "apply-decisions":
            if args.decisions_csv_file is not None:
                csv_text = args.decisions_csv_file.read_text(encoding="utf-8")
                if args.preview:
                    payload = service.preview_review_workbook_csv(
                        run_id=args.run_id,
                        reviewer=args.reviewer,
                        csv_text=csv_text,
                        write=args.preview_write,
                    )
                else:
                    payload = service.apply_review_workbook_csv(
                        run_id=args.run_id,
                        reviewer=args.reviewer,
                        csv_text=csv_text,
                    )
            else:
                decisions_body = (
                    args.decisions_file.read_text(encoding="utf-8")
                    if args.decisions_file is not None
                    else args.decisions_json
                )
                payload = service.apply_review_decisions(
                    run_id=args.run_id,
                    reviewer=args.reviewer,
                    decisions=json.loads(decisions_body),
                )
        else:
            payload = service.review_queue(
                run_id=args.run_id,
                state=args.state,
                next_action=args.next_action,
                artifact_kind=args.artifact_kind,
            )
            if not args.json:
                print(_render_review_queue_text(payload), end="")
                return 0
        print(json.dumps(payload, indent=2) if args.json else payload)
        return 0

    if args.command == "actions":
        payload = service.run_next_actions(run_id=args.run_id, limit=args.limit)
        print(json.dumps(payload, indent=2) if args.json else payload)
        return 0

    if args.command == "jobs":
        if args.jobs_command == "list":
            payload = service.list_jobs(args.run_id)
        elif args.jobs_command == "show":
            payload = service.get_job(args.job_id, run_id=args.run_id)
        else:
            payload = service.submit_review(
                job_id=args.job_id,
                run_id=args.run_id,
                reviewer=args.reviewer,
                action=args.action,
                field_corrections=json.loads(args.field_corrections_json),
                crop_selection=json.loads(args.crop_selection_json),
                approved_enrichment_fields=json.loads(args.approved_enrichment_fields_json),
                duplicate_resolution=json.loads(args.duplicate_resolution_json),
                notes=args.notes,
            )
        if args.jobs_command == "list" and not args.json:
            print(_render_jobs_list_text(payload), end="")
            return 0
        if args.jobs_command == "show" and not args.json:
            print(_render_job_show_text(payload), end="")
            return 0
        print(json.dumps(payload, indent=2) if args.json else payload)
        return 0

    if args.command == "sinks":
        if args.sinks_command == "check":
            payload = service.sink_readiness()
        elif args.sinks_command == "lookup-plan":
            payload = service.plan_sink_lookup_for_job(
                job_id=args.job_id,
                run_id=args.run_id,
                dry_run=args.dry_run,
            )
        elif args.sinks_command == "plan":
            payload = service.plan_sinks_for_job(
                job_id=args.job_id,
                run_id=args.run_id,
                dry_run=args.dry_run,
            )
        elif args.sinks_command == "apply-preflight":
            payload = service.preflight_sink_apply(
                job_id=args.job_id,
                run_id=args.run_id,
                apply=args.apply,
            )
        elif args.sinks_command == "apply-decision":
            payload = service.decide_sink_apply(
                job_id=args.job_id,
                run_id=args.run_id,
                decision=args.decision,
                reviewer=args.reviewer,
                reason=args.reason,
            )
        elif args.sinks_command == "apply":
            payload = service.apply_sinks_for_job(
                job_id=args.job_id,
                run_id=args.run_id,
                apply=args.apply,
                simulate=args.simulate,
            )
        elif args.sinks_command == "apply-pilot-readiness":
            payload = service.build_sink_apply_pilot_readiness_for_job(
                job_id=args.job_id,
                run_id=args.run_id,
                sink=args.sink,
            )
        elif args.sinks_command == "apply-pilot-report":
            payload = service.build_sink_apply_pilot_report_for_job(
                job_id=args.job_id,
                run_id=args.run_id,
            )
        elif args.sinks_command == "apply-pilot-bundle":
            payload = service.build_sink_apply_pilot_bundle_for_job(
                job_id=args.job_id,
                run_id=args.run_id,
                sink=args.sink,
                operator=args.operator,
            )
        elif args.sinks_command == "adapter-request":
            payload = service.build_sink_adapter_request_for_job(
                job_id=args.job_id,
                run_id=args.run_id,
                phase=args.phase,
            )
        elif args.sinks_command == "lookup-result":
            payload = service.record_sink_lookup_result_for_job(
                job_id=args.job_id,
                run_id=args.run_id,
                matches_by_sink=json.loads(args.matches_by_sink_json),
            )
        elif args.sinks_command == "lookup-pilot":
            payload = service.execute_sink_lookup_pilot_for_job(
                job_id=args.job_id,
                run_id=args.run_id,
                sink=args.sink,
                approved_by=args.approved_by,
                matches=json.loads(args.matches_json),
                simulate=args.simulate,
            )
        elif args.sinks_command == "lookup-readiness":
            payload = service.live_lookup_readiness_report(
                job_id=args.job_id,
                run_id=args.run_id,
                sink=args.sink,
            )
        elif args.sinks_command == "lookup-smoke-handoff":
            payload = service.build_sink_lookup_smoke_handoff_for_job(
                job_id=args.job_id,
                run_id=args.run_id,
                sink=args.sink,
                approved_by=args.approved_by,
            )
        elif args.sinks_command == "live-selection-packet":
            payload = service.live_selection_packet(
                job_id=args.job_id,
                run_id=args.run_id,
                sink=args.sink,
                operator=args.operator,
                scope=args.scope,
                reason=args.reason,
                write=not args.no_write,
            )
        elif args.sinks_command == "select-live-target":
            payload = service.select_live_target_for_job(
                job_id=args.job_id,
                run_id=args.run_id,
                sink=args.sink,
                operator=args.operator,
                scope=args.scope,
                reason=args.reason,
                safety_confirmation=args.safety_confirmation,
            )
        elif args.sinks_command == "selected-target-audit":
            payload = service.selected_live_target_audit(
                job_id=args.job_id,
                run_id=args.run_id,
                scope=args.scope,
                write=not args.no_write,
            )
        elif args.sinks_command == "abandon-live-pilot":
            payload = service.live_pilot_abandon_for_job(
                job_id=args.job_id,
                run_id=args.run_id,
                operator=args.operator,
                reason=args.reason,
            )
        elif args.sinks_command == "execute-lookup-smoke":
            payload = service.execute_selected_lookup_smoke_for_job(
                job_id=args.job_id,
                run_id=args.run_id,
            )
        elif args.sinks_command == "write-pilot":
            payload = service.execute_sink_write_pilot_for_job(
                job_id=args.job_id,
                run_id=args.run_id,
                sink=args.sink,
                approved_by=args.approved_by,
                simulate=args.simulate,
            )
        elif args.sinks_command == "readback-pilot":
            payload = service.execute_sink_readback_pilot_for_job(
                job_id=args.job_id,
                run_id=args.run_id,
                sink=args.sink,
                approved_by=args.approved_by,
                readback=json.loads(args.readback_json),
                simulate=args.simulate,
            )
        elif args.sinks_command == "live-pilot-closeout":
            payload = service.build_live_pilot_closeout_for_job(
                job_id=args.job_id,
                run_id=args.run_id,
                write=not args.no_write,
            )
        else:
            payload = service.assess_downstream_duplicates_for_job(
                job_id=args.job_id,
                run_id=args.run_id,
            )
        print(json.dumps(payload, indent=2) if args.json else payload)
        return 0

    if args.command == "enrichment":
        if args.enrichment_command == "check":
            payload = service.enrichment_readiness(
                mode=args.mode,
                allow_paid_enrichment=args.allow_paid_enrichment,
            )
        elif args.enrichment_command == "request":
            payload = service.request_enrichment(
                job_id=args.job_id,
                run_id=args.run_id,
                mode=args.mode,
                requested_by=args.requested_by,
                allow_paid_enrichment=args.allow_paid_enrichment,
                public_web_results=json.loads(args.public_web_results_json),
                provider_results=json.loads(args.provider_results_json),
            )
        elif args.enrichment_command == "public-web-results":
            payload = service.record_public_web_enrichment_results(
                job_id=args.job_id,
                run_id=args.run_id,
                searched_by=args.searched_by,
                results=json.loads(args.results_json),
            )
        elif args.enrichment_command == "public-web-handoff":
            payload = service.build_public_web_enrichment_handoff(
                job_id=args.job_id,
                run_id=args.run_id,
            )
        elif args.enrichment_command == "provider-handoff":
            payload = service.build_provider_enrichment_handoff(
                job_id=args.job_id,
                run_id=args.run_id,
            )
        else:
            payload = service.record_provider_enrichment_results(
                job_id=args.job_id,
                run_id=args.run_id,
                provider=args.provider,
                submitted_by=args.submitted_by,
                results=json.loads(args.results_json),
            )
        print(json.dumps(payload, indent=2) if args.json else payload)
        checks = payload.get("checks") or payload.get("readiness", {}).get("checks", [])
        return 0 if all(check["status"] == "ready" for check in checks) else 2

    if args.command == "watch":
        PollingWatcher(
            config,
            interval_seconds=args.interval_seconds,
            settle_seconds=args.settle_seconds,
        ).run(
            dry_run=args.dry_run,
            once=args.once,
        )
        return 0

    if args.command == "watch-status":
        payload = service.watch_status()
        print(json.dumps(payload, indent=2) if args.json else payload)
        return 0 if payload["last_error"] is None else 2

    if args.command == "watch-dry-run":
        payload = service.watch_dry_run_harness()
        print(json.dumps(payload, indent=2) if args.json else payload)
        return 0 if payload["state"] == "passed" else 2

    if args.command == "watch-reset":
        if not args.yes:
            raise SystemExit("Refusing to reset watcher state without --yes")
        print(json.dumps(service.watch_reset(), indent=2))
        return 0

    if args.command == "api":
        try:
            import uvicorn
        except ImportError as exc:
            raise SystemExit("Install with the api extra: pip install -e '.[api]'") from exc
        uvicorn.run(create_app(), host=args.host, port=args.port)
        return 0

    if args.command == "service":
        if args.service_command == "install":
            payload = install_user_service(config).to_dict()
        elif args.service_command == "uninstall":
            payload = uninstall_user_service().to_dict()
        elif args.service_command == "recovery":
            payload = service.service_recovery_report(run_id=args.run_id)
        else:
            payload = service_status().to_dict()
        if args.service_command == "recovery" and not args.json:
            print(_render_service_recovery_text(payload), end="")
        else:
            print(json.dumps(payload, indent=2) if args.json else payload)
        return 0

    if args.command == "mcp-manifest":
        print(manifest_json(), end="")
        return 0

    if args.command == "mcp-stdio":
        serve_jsonl(config=config)
        return 0

    if args.command == "mcp-call":
        payload = call_tool(
            args.tool_name,
            json.loads(args.arguments_json),
            config=config,
        )
        print(json.dumps(payload, indent=2))
        return 0

    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
