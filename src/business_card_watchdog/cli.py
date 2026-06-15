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


def _render_status_text(payload: dict[str, object]) -> str:
    watch = dict(payload.get("watch") or {})
    commands = dict(payload.get("commands") or {})
    safe_actions = payload.get("safe_next_actions") or []
    stop_conditions = payload.get("explicit_stop_conditions") or []
    lines = [
        "Status: " + ("ready" if payload.get("skill_ready") else "blocked"),
        f"Config: {payload.get('config_path')}",
        f"Data: {payload.get('data_dir')}",
        f"Cache: {payload.get('cache_dir')}",
        f"Skill: ready={payload.get('skill_ready')} message={payload.get('skill_message')}",
        "Watch: "
        f"inputs={len(watch.get('inputs') or [])} "
        f"backlog={watch.get('backlog_count', 0)} "
        f"unsettled={watch.get('unsettled_count', 0)} "
        f"last_error={watch.get('last_error') or 'none'}",
        f"Observed: writes={payload.get('writes_attempted', 0)} network={payload.get('network_calls_made', 0)}",
        "Commands:",
    ]
    for label, key in [
        ("Runtime readiness", "runtime_readiness"),
        ("Service recovery", "service_recovery"),
        ("Watch status", "watch_status"),
        ("Watch dry run", "watch_dry_run"),
        ("Runs list", "runs_list"),
        ("MCP manifest", "mcp_manifest"),
    ]:
        command = commands.get(key)
        if command:
            lines.append(f" - {label}: {command}")

    action_rows = safe_actions if isinstance(safe_actions, list) else []
    lines.append(f"Safe next actions: {len(action_rows)}")
    for action in action_rows:
        if isinstance(action, dict):
            lines.append(f" - {action.get('action')}: {action.get('command')}")

    stop_rows = stop_conditions if isinstance(stop_conditions, list) else []
    lines.append(f"Stop conditions: {len(stop_rows)}")
    for condition in stop_rows:
        lines.append(f" - {condition}")
    return "\n".join(lines) + "\n"


def _render_watch_status_text(payload: dict[str, object]) -> str:
    lines = [
        "Watch status:",
        f"Inputs: {len(payload.get('inputs') or [])}",
        f"Seen: {payload.get('seen_count', 0)}",
        f"Backlog: {payload.get('backlog_count', 0)}",
        f"Unsettled: {payload.get('unsettled_count', 0)}",
        f"Last processed: {payload.get('last_processed_path') or 'none'}",
        f"Last error: {payload.get('last_error') or 'none'}",
        f"Scan truncated: {payload.get('scan_truncated', False)}",
    ]
    return "\n".join(lines) + "\n"


def _render_watch_dry_run_text(payload: dict[str, object]) -> str:
    assertions = dict(payload.get("assertions") or {})
    commands = dict(payload.get("commands") or {})
    safe_actions = payload.get("safe_next_actions") or []
    stop_conditions = payload.get("explicit_stop_conditions") or []
    lines = [
        f"Watch dry run: {payload.get('state')}",
        f"Harness: {payload.get('harness_id')}",
        f"Source: {payload.get('source_dir')}",
        f"Processed first scan: {len(payload.get('first_scan_processed') or [])}",
        f"Processed second scan: {len(payload.get('second_scan_processed') or [])}",
        f"Private sources used: {payload.get('private_sources_used', False)}",
        f"Observed: writes={payload.get('writes_attempted', 0)} network={payload.get('network_calls_made', 0)}",
        "Assertions: "
        + " ".join(f"{key}={value}" for key, value in sorted(assertions.items()))
        if assertions
        else "Assertions: none",
        "Commands:",
    ]
    for label, key in [
        ("Watch status", "watch_status"),
        ("Watch dry run", "watch_dry_run"),
        ("Status", "status"),
        ("Service recovery", "service_recovery"),
    ]:
        command = commands.get(key)
        if command:
            lines.append(f" - {label}: {command}")
    action_rows = safe_actions if isinstance(safe_actions, list) else []
    lines.append(f"Safe next actions: {len(action_rows)}")
    for action in action_rows:
        if isinstance(action, dict):
            lines.append(f" - {action.get('action')}: {action.get('command')}")
    stop_rows = stop_conditions if isinstance(stop_conditions, list) else []
    lines.append(f"Stop conditions: {len(stop_rows)}")
    for condition in stop_rows:
        lines.append(f" - {condition}")
    return "\n".join(lines) + "\n"


def _render_review_routing_drill_text(payload: dict[str, object]) -> str:
    review = dict(payload.get("review") or {})
    safe_actions = dict(payload.get("safe_actions") or {})
    sink_context = dict(payload.get("fixture_sink_context") or {})
    commands = dict(payload.get("commands") or {})
    stop_conditions = payload.get("explicit_stop_conditions") or []
    route_artifacts = payload.get("route_artifact_kinds") or []
    executed = safe_actions.get("executed_actions") or []
    skipped = safe_actions.get("skipped_actions") or []
    next_actions = payload.get("next_actions") or []
    lines = [
        "Review routing drill:",
        f"Run: {payload.get('run_id')}",
        f"Job: {payload.get('job_id')}",
        f"Fixture image: {payload.get('fixture_image_path')}",
        "Fixture sinks: " + ", ".join(str(sink) for sink in payload.get("configured_fixture_sinks") or []),
        "Fixture context: "
        f"gws={sink_context.get('google_contacts_profile') or 'none'} "
        f"odollo={sink_context.get('odollo_tenant') or 'none'} "
        f"dry_run={sink_context.get('dry_run', True)}",
        f"Review: {review.get('initial_state') or 'unknown'} -> {review.get('final_state') or 'unknown'}",
        "Observed: "
        f"writes={payload.get('writes_attempted', 0)} "
        f"network={payload.get('network_calls_made', 0)} "
        f"private_sources={payload.get('private_sources_used', False)} "
        f"live_sinks={payload.get('live_sink_calls_made', False)}",
        f"Drill path: {payload.get('drill_path')}",
        f"Review bundle: {payload.get('review_bundle_path')}",
        f"Review workbook: {payload.get('review_workbook_path')}",
    ]
    artifact_rows = route_artifacts if isinstance(route_artifacts, list) else []
    lines.append(f"Route artifacts: {len(artifact_rows)}")
    for artifact in artifact_rows:
        lines.append(f" - {artifact}")
    executed_rows = executed if isinstance(executed, list) else []
    lines.append(f"Safe actions executed: {len(executed_rows)}")
    for action in executed_rows:
        lines.append(f" - {action}")
    skipped_rows = skipped if isinstance(skipped, list) else []
    lines.append(f"Manual actions skipped: {len(skipped_rows)}")
    for action in skipped_rows:
        lines.append(f" - {action}")
    next_rows = next_actions if isinstance(next_actions, list) else []
    if next_rows:
        lines.append("Next actions:")
        for action in next_rows:
            if isinstance(action, dict):
                lines.append(f" - {action.get('action')}: {action.get('command')}")
    lines.append("Commands:")
    for label, key in [
        ("Review bundle", "review_bundle"),
        ("Review workbook", "review_workbook"),
        ("Next actions", "next_actions"),
        ("Run next safe", "run_next_safe"),
        ("Phase report", "phase_report"),
    ]:
        command = commands.get(key)
        if command:
            lines.append(f" - {label}: {command}")
    stops = stop_conditions if isinstance(stop_conditions, list) else []
    lines.append(f"Stop conditions: {len(stops)}")
    for condition in stops:
        lines.append(f" - {condition}")
    return "\n".join(lines) + "\n"


def _render_operator_dashboard_text(payload: dict[str, object]) -> str:
    runtime = dict(payload.get("runtime_readiness") or {})
    recovery = dict(payload.get("service_recovery") or {})
    run_summary = dict(payload.get("run_summary") or {})
    phase = dict(payload.get("phase_dashboard_summary") or {})
    live = dict(payload.get("live_pilot_summary") or {})
    live_handoff = dict(payload.get("live_pilot_handoff_summary") or {})
    review_counts = dict(payload.get("review_counts") or {})
    next_actions = dict(payload.get("next_action_summary") or {})
    commands = dict(payload.get("commands") or {})
    api_routes = dict(payload.get("api_routes") or {})
    mcp_tools = dict(payload.get("mcp_tools") or {})
    blocked = payload.get("blocked_reasons") or []
    safe_actions = payload.get("safe_next_actions") or []
    stop_conditions = payload.get("explicit_stop_conditions") or []
    lines = [
        f"Operator dashboard: {payload.get('state')}",
        f"Selected run: {payload.get('selected_run_id') or 'none'}",
        f"Runs: {payload.get('run_count', 0)}",
        f"Runtime readiness: {runtime.get('state')}",
        f"Service recovery: {recovery.get('state')}",
        f"Run state: {run_summary.get('state') or 'none'}",
        f"Jobs: {run_summary.get('job_count', 0)}",
        "Review counts: "
        + " ".join(f"{key}={value}" for key, value in sorted(review_counts.items()))
        if review_counts
        else "Review counts: none",
        "Next actions: "
        f"total={next_actions.get('action_count', 0)} "
        f"safe={next_actions.get('safe_auto_count', 0)} "
        f"explicit={next_actions.get('explicit_operator_count', 0)}",
        f"Phase status: {phase.get('status_line') or 'none'}",
        f"Live pilot: {live.get('state') or 'none'}",
        "Live handoff: "
        f"state={live_handoff.get('state') or 'none'} "
        f"operator_required={live_handoff.get('operator_required_count', 0)} "
        f"response_templates={live_handoff.get('operator_response_template_count', 0)}",
        f"Observed: writes={payload.get('writes_attempted', 0)} network={payload.get('network_calls_made', 0)}",
        "Commands:",
    ]
    for label, key in [
        ("Status", "status"),
        ("Runtime readiness", "runtime_readiness"),
        ("Service recovery", "service_recovery"),
        ("Runs list", "runs_list"),
        ("Review queue", "review_queue"),
        ("Phase report", "phase_report"),
        ("Next actions", "next_actions"),
        ("Run next safe", "run_next_safe"),
        ("Live pilot status", "live_pilot_status"),
        ("Live pilot handoff", "live_pilot_handoff"),
        ("Live pilot validate response", "live_pilot_validate_response"),
    ]:
        command = commands.get(key)
        if command:
            lines.append(f" - {label}: {command}")
    if api_routes:
        lines.append("API routes:")
        for label, key in [
            ("Operator dashboard", "operator_dashboard"),
            ("Next actions", "next_actions"),
            ("Run next safe", "run_next_safe"),
            ("Live pilot status", "live_pilot_status"),
            ("Live pilot handoff", "live_pilot_handoff"),
            ("Live pilot validate response", "live_pilot_validate_response"),
        ]:
            route = api_routes.get(key)
            if route:
                lines.append(f" - {label}: {route}")
    if mcp_tools:
        lines.append("MCP tools:")
        for label, key in [
            ("Operator dashboard", "operator_dashboard"),
            ("Next actions", "next_actions"),
            ("Run next safe", "run_next_safe"),
            ("Live pilot status", "live_pilot_status"),
            ("Live pilot handoff", "live_pilot_handoff"),
            ("Live pilot validate response", "live_pilot_validate_response"),
        ]:
            tool_entry = mcp_tools.get(key)
            if isinstance(tool_entry, dict):
                tool_name = tool_entry.get("tool")
                arguments = dict(tool_entry.get("arguments") or {})
                rendered_args = ", ".join(f"{arg_key}={arguments[arg_key]}" for arg_key in sorted(arguments))
                suffix = f" args={rendered_args}" if rendered_args else ""
                if tool_name:
                    lines.append(f" - {label}: {tool_name}{suffix}")
    sample_rows = next_actions.get("sample_actions") or []
    rows = sample_rows if isinstance(sample_rows, list) else []
    if rows:
        lines.append("Next action samples:")
        for action in rows[:5]:
            if isinstance(action, dict):
                lines.append(
                    " - "
                    f"{action.get('job_id')} "
                    f"action={action.get('action')} "
                    f"safe={action.get('safe_to_auto_continue')} "
                    f"explicit={action.get('requires_explicit_operator_action')} "
                    f"command={action.get('command') or 'none'}"
                )
    live_operator_entries = live_handoff.get("operator_entries") or []
    operator_rows = live_operator_entries if isinstance(live_operator_entries, list) else []
    if operator_rows:
        lines.append("Live handoff operator entries:")
        for entry in operator_rows[:5]:
            if isinstance(entry, dict):
                lines.append(
                    " - "
                    f"{entry.get('job_id')} "
                    f"next={entry.get('next_action')} "
                    f"command={entry.get('command') or 'none'}"
                )
                if entry.get("operator_response_template"):
                    lines.append(f"   Operator response: {entry.get('operator_response_template')}")
                if entry.get("validation_command_prefilled"):
                    lines.append(f"   Validate prefilled response: {entry.get('validation_command_prefilled')}")
    live_stop_conditions = live.get("explicit_stop_conditions") or []
    live_stop_rows = live_stop_conditions if isinstance(live_stop_conditions, list) else []
    lines.append(f"Live pilot stop conditions: {len(live_stop_rows)}")
    for condition in live_stop_rows:
        lines.append(f" - {condition}")
    handoff_stop_conditions = live_handoff.get("operator_stop_conditions") or []
    handoff_stop_rows = handoff_stop_conditions if isinstance(handoff_stop_conditions, list) else []
    lines.append(f"Live handoff stop conditions: {len(handoff_stop_rows)}")
    for condition in handoff_stop_rows:
        lines.append(f" - {condition}")
    blocked_rows = blocked if isinstance(blocked, list) else []
    lines.append(f"Blocked reasons: {len(blocked_rows)}")
    for reason in blocked_rows:
        lines.append(f" - {reason}")
    action_rows = safe_actions if isinstance(safe_actions, list) else []
    lines.append(f"Safe next actions: {len(action_rows)}")
    for action in action_rows:
        if isinstance(action, dict):
            lines.append(f" - {action.get('action')}: {action.get('command')}")
    stop_rows = stop_conditions if isinstance(stop_conditions, list) else []
    lines.append(f"Stop conditions: {len(stop_rows)}")
    for condition in stop_rows:
        lines.append(f" - {condition}")
    return "\n".join(lines) + "\n"


def _render_phase_report_text(payload: dict[str, object]) -> str:
    dashboard = dict(payload.get("dashboard_summary") or {})
    preview = dict(payload.get("review_workbook_preview") or {})
    commands = dict(payload.get("commands") or {})
    lines = [
        f"Run: {payload.get('run_id')}",
        f"State: {payload.get('run_state')}",
        f"Jobs: {payload.get('job_count')}",
        f"Status: {dashboard.get('status_line') or 'unknown'}",
        f"Review workbook preview: {preview.get('state') or dashboard.get('review_workbook_preview_state') or 'unknown'}",
        f"Live pilot handoff: {commands.get('live_pilot_handoff')}",
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
    commands = dict(payload.get("commands") or {})
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
        f"Live pilot handoff: {commands.get('live_pilot_handoff')}",
    ]
    return "\n".join(lines) + "\n"


def _render_live_pilot_status_text(payload: dict[str, object]) -> str:
    counts = dict(payload.get("counts") or {})
    commands = dict(payload.get("commands") or {})
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
        f"Live pilot handoff: {commands.get('live_pilot_handoff')}",
        f"Validate response: {commands.get('validate_operator_response')}",
    ]
    for entry in entries if isinstance(entries, list) else []:
        if isinstance(entry, dict):
            lines.append(
                " - "
                f"{entry.get('job_id')} "
                f"state={entry.get('state')} "
                f"sink={entry.get('selected_target_sink') or 'none'} "
                f"target={entry.get('selected_target_identity') or 'none'} "
                f"abandonment={entry.get('abandonment_identity') or 'none'} "
                f"closeout={entry.get('closeout_state') or 'none'}"
            )
    stop_conditions = payload.get("explicit_stop_conditions") or []
    stops = stop_conditions if isinstance(stop_conditions, list) else []
    lines.append(f"Stop conditions: {len(stops)}")
    for condition in stops:
        lines.append(f" - {condition}")
    return "\n".join(lines) + "\n"


def _render_live_pilot_handoff_text(payload: dict[str, object]) -> str:
    action_counts = dict(payload.get("action_counts") or {})
    commands = dict(payload.get("commands") or {})
    response_templates = payload.get("operator_response_templates") or []
    entries = payload.get("entries") or []
    lines = [
        f"Run: {payload.get('run_id')}",
        f"State: {payload.get('state')}",
        f"Jobs: {payload.get('job_count')}",
        "Actions: "
        + " ".join(f"{key}={value}" for key, value in sorted(action_counts.items()))
        if action_counts
        else "Actions: none",
        f"Response templates: {len(response_templates) if isinstance(response_templates, list) else 0}",
        f"Validate response: {commands.get('validate_operator_response')}",
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
            if entry.get("operator_response_template"):
                lines.append(f"   Operator response: {entry.get('operator_response_template')}")
            entry_commands = dict(entry.get("commands") or {})
            prefilled_validate_command = entry_commands.get("validate_operator_response_prefilled")
            if prefilled_validate_command:
                lines.append(f"   Validate prefilled response: {prefilled_validate_command}")
    stop_conditions = payload.get("operator_stop_conditions") or []
    stops = stop_conditions if isinstance(stop_conditions, list) else []
    lines.append(f"Operator stop conditions: {len(stops)}")
    for condition in stops:
        lines.append(f" - {condition}")
    return "\n".join(lines) + "\n"


def _render_live_pilot_operator_response_validation_text(payload: dict[str, object]) -> str:
    missing = payload.get("missing_fields") or []
    mismatches = payload.get("mismatches") or []
    lines = [
        f"Run: {payload.get('run_id')}",
        f"State: {payload.get('state')}",
        f"Next validation step: {payload.get('next_validation_step') or 'none'}",
        f"Missing fields: {', '.join(str(item) for item in missing) if isinstance(missing, list) and missing else 'none'}",
        f"Mismatches: {', '.join(str(item) for item in mismatches) if isinstance(mismatches, list) and mismatches else 'none'}",
        f"Creates selected target: {payload.get('creates_selected_live_target', False)}",
        f"Observed: writes={payload.get('writes_attempted', 0)} network={payload.get('network_calls_made', 0)}",
    ]
    if payload.get("select_target_command"):
        lines.append(f"Select target: {payload.get('select_target_command')}")
    if payload.get("selected_target_audit_command"):
        lines.append(f"Selected target audit: {payload.get('selected_target_audit_command')}")
    if payload.get("lookup_smoke_handoff_command"):
        lines.append(f"Lookup smoke handoff: {payload.get('lookup_smoke_handoff_command')}")
    sequence = payload.get("post_selection_sequence") or []
    if isinstance(sequence, list) and sequence:
        lines.append("Post-selection sequence:")
        for item in sequence:
            if isinstance(item, dict):
                lines.append(f" - {item.get('step')}: {item.get('command')}")
    stop_conditions = payload.get("explicit_stop_conditions") or []
    stops = stop_conditions if isinstance(stop_conditions, list) else []
    lines.append(f"Stop conditions: {len(stops)}")
    for condition in stops:
        lines.append(f" - {condition}")
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
        f"Live pilot status: {commands.get('live_pilot_status')}",
        f"Live pilot handoff: {commands.get('live_pilot_handoff')}",
        f"Recover: {commands.get('recover')}",
    ]
    action_rows = safe_actions if isinstance(safe_actions, list) else []
    for action in action_rows:
        if isinstance(action, dict):
            lines.append(f" - {action.get('action')}: {action.get('command')}")
    return "\n".join(lines) + "\n"


def _render_live_target_candidates_text(payload: dict[str, object]) -> str:
    candidates = payload.get("candidates") or []
    rows = candidates if isinstance(candidates, list) else []
    commands = dict(payload.get("commands") or {})
    lines = [
        f"Live target candidates: {payload.get('candidate_count', 0)}",
        f"Ready: {payload.get('ready_candidate_count', 0)}",
        f"Blocked: {payload.get('blocked_candidate_count', 0)}",
    ]
    for candidate in rows:
        if not isinstance(candidate, dict):
            continue
        candidate_commands = dict(candidate.get("commands") or {})
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
        for label, key in [
            ("Inspect job", "inspect_job"),
            ("Pilot readiness", "pilot_readiness"),
            ("Lookup readiness", "lookup_readiness"),
            ("Select lookup target", "select_lookup_target"),
            ("Validate response", "validate_operator_response"),
        ]:
            command = candidate_commands.get(key)
            if command:
                lines.append(f"   {label}: {command}")
    for label, key in [
        ("Live readiness audit", "live_readiness_audit"),
        ("Selection requirements", "live_selection_requirements"),
        ("Live pilot handoff", "live_pilot_handoff"),
        ("Validate response", "validate_operator_response"),
    ]:
        command = commands.get(key)
        if command:
            lines.append(f"{label}: {command}")
    return "\n".join(lines) + "\n"


def _render_live_readiness_audit_text(payload: dict[str, object]) -> str:
    commands = dict(payload.get("commands") or {})
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
    for label, key in [
        ("Target candidates", "target_candidates"),
        ("Selection requirements", "selection_requirements"),
        ("Runtime readiness", "runtime_readiness"),
        ("Service recovery", "service_recovery"),
        ("Pilot readiness", "pilot_readiness"),
        ("Live pilot handoff", "live_pilot_handoff"),
        ("Validate response", "validate_operator_response"),
    ]:
        command = commands.get(key)
        if command:
            lines.append(f"{label}: {command}")
    return "\n".join(lines) + "\n"


def _render_live_selection_requirements_text(payload: dict[str, object]) -> str:
    entries = payload.get("entries") or []
    rows = entries if isinstance(entries, list) else []
    state_counts = dict(payload.get("state_counts") or {})
    commands = dict(payload.get("commands") or {})
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
        entry_commands = dict(entry.get("commands") or {})
        lines.append(
            " - "
            f"{entry.get('run_id')}/{entry.get('job_id')} "
            f"sink={entry.get('sink')} "
            f"state={entry.get('state')} "
            f"target={entry.get('selected_target_identity') or 'none'} "
            f"abandonment={entry.get('abandonment_identity') or 'none'} "
            f"missing={missing_text}"
        )
        if entry_commands.get("selection_packet"):
            lines.append(f"   Selection packet: {entry_commands.get('selection_packet')}")
        if entry_commands.get("select_target"):
            lines.append(f"   Select target: {entry_commands.get('select_target')}")
        if entry.get("operator_response_template"):
            lines.append(f"   Operator response: {entry.get('operator_response_template')}")
        if entry_commands.get("validate_operator_response_prefilled"):
            lines.append(f"   Validate prefilled response: {entry_commands.get('validate_operator_response_prefilled')}")
    if payload.get("requirements_path"):
        lines.append(f"Requirements path: {payload.get('requirements_path')}")
    for label, key in [
        ("Live target candidates", "live_target_candidates"),
        ("Live readiness audit", "live_readiness_audit"),
        ("Selection requirements", "live_selection_requirements"),
        ("Live pilot handoff", "live_pilot_handoff"),
    ]:
        command = commands.get(key)
        if command:
            lines.append(f"{label}: {command}")
    return "\n".join(lines) + "\n"


def _render_live_selection_packet_text(payload: dict[str, object]) -> str:
    existing = dict(payload.get("existing_selected_target") or {})
    scope_allows = dict(payload.get("scope_allows") or {})
    blocked_reasons = payload.get("blocked_reasons") or []
    stop_conditions = payload.get("explicit_stop_conditions") or []
    commands = dict(payload.get("commands") or {})
    lines = [
        f"Live selection packet: {payload.get('state')}",
        f"Run: {payload.get('run_id')}",
        f"Job: {payload.get('job_id')}",
        f"Sink: {payload.get('sink')}",
        f"Operator: {payload.get('operator')}",
        f"Scope: {payload.get('scope')}",
        "Scope allows: "
        f"lookup={scope_allows.get('lookup', False)} "
        f"write={scope_allows.get('write', False)} "
        f"readback={scope_allows.get('readback', False)}",
        "Existing target: "
        f"exists={existing.get('exists', False)} "
        f"identity={existing.get('identity') or 'none'} "
        f"sink={existing.get('sink') or 'none'} "
        f"scope={existing.get('scope') or 'none'} "
        f"safety_confirmed={existing.get('target_safety_confirmed', False)} "
        f"abandoned={existing.get('abandoned', False)}",
        "Replacement: "
        f"requires_abandonment={existing.get('replacement_requires_abandonment', False)} "
        f"can_select_now={existing.get('can_select_replacement_now', False)}",
        f"Observed: writes={payload.get('writes_attempted', 0)} network={payload.get('network_calls_made', 0)}",
    ]
    if payload.get("packet_path"):
        lines.append(f"Packet path: {payload.get('packet_path')}")
    rows = blocked_reasons if isinstance(blocked_reasons, list) else []
    lines.append(f"Blocked reasons: {len(rows)}")
    for reason in rows:
        lines.append(f" - {reason}")
    if payload.get("operator_response_template"):
        lines.append(f"Operator response: {payload.get('operator_response_template')}")
    abandon_command = existing.get("abandon_command")
    if abandon_command:
        lines.append(f"Abandon existing target: {abandon_command}")
    validate_command = commands.get("validate_operator_response")
    if validate_command:
        lines.append(f"Validate response: {validate_command}")
    prefilled_validate_command = commands.get("validate_operator_response_prefilled")
    if prefilled_validate_command:
        lines.append(f"Validate prefilled response: {prefilled_validate_command}")
    create_command = commands.get("create_selected_target")
    if create_command:
        lines.append(f"Create selected target: {create_command}")
    stops = stop_conditions if isinstance(stop_conditions, list) else []
    lines.append(f"Stop conditions: {len(stops)}")
    for condition in stops:
        lines.append(f" - {condition}")
    return "\n".join(lines) + "\n"


def _render_selected_target_audit_text(payload: dict[str, object]) -> str:
    selected_target = dict(payload.get("selected_target") or {})
    blocked_reasons = payload.get("blocked_reasons") or []
    mismatches = payload.get("mismatches") or []
    stop_conditions = payload.get("explicit_stop_conditions") or []
    commands = dict(payload.get("commands") or {})
    lines = [
        f"Selected target audit: {payload.get('state')}",
        f"Run: {payload.get('run_id')}",
        f"Job: {payload.get('job_id')}",
        f"Scope: {payload.get('scope')}",
        f"Sink: {payload.get('sink') or 'none'}",
        f"Operator: {payload.get('operator') or 'none'}",
        "Selected target: "
        f"exists={payload.get('selected_target_exists', False)} "
        f"identity={selected_target.get('selection_id') or selected_target.get('created_at') or 'none'} "
        f"scope={selected_target.get('scope') or 'none'} "
        f"safety_confirmed={payload.get('target_safety_confirmed', False)}",
        f"Observed: writes={payload.get('writes_attempted', 0)} network={payload.get('network_calls_made', 0)}",
    ]
    if payload.get("audit_path"):
        lines.append(f"Audit path: {payload.get('audit_path')}")
    mismatch_rows = mismatches if isinstance(mismatches, list) else []
    lines.append(f"Mismatches: {len(mismatch_rows)}")
    for mismatch in mismatch_rows:
        lines.append(f" - {mismatch}")
    blocked_rows = blocked_reasons if isinstance(blocked_reasons, list) else []
    lines.append(f"Blocked reasons: {len(blocked_rows)}")
    for reason in blocked_rows:
        lines.append(f" - {reason}")
    for label, key in [
        ("Lookup smoke", "lookup_smoke"),
        ("Write pilot", "write_pilot"),
        ("Readback pilot", "readback_pilot"),
    ]:
        command = commands.get(key)
        if command:
            lines.append(f"{label}: {command}")
    stops = stop_conditions if isinstance(stop_conditions, list) else []
    lines.append(f"Stop conditions: {len(stops)}")
    for condition in stops:
        lines.append(f" - {condition}")
    return "\n".join(lines) + "\n"


def _render_live_pilot_closeout_text(payload: dict[str, object]) -> str:
    report = dict(payload.get("report") or payload)
    lookup = dict(report.get("lookup") or {})
    audit = dict(report.get("selected_target_audit") or {})
    write = dict(report.get("write") or {})
    readback = dict(report.get("readback") or {})
    apply_report = dict(report.get("apply_report") or {})
    blocked_reasons = report.get("blocked_reasons") or []
    missing_artifacts = report.get("missing_artifacts") or []
    stop_conditions = report.get("explicit_stop_conditions") or []
    commands = dict(report.get("commands") or {})
    lines = [
        f"Live pilot closeout: {report.get('state')}",
        f"Run: {report.get('run_id')}",
        f"Job: {report.get('job_id')}",
        f"Scope: {report.get('scope')}",
        f"Sink: {report.get('sink') or 'none'}",
        f"Operator: {report.get('operator') or 'none'}",
        "Selected target audit: "
        f"state={audit.get('state') or 'none'} "
        f"safety_confirmed={audit.get('target_safety_confirmed')}",
        "Lookup: "
        f"status={lookup.get('status') or 'none'} "
        f"matches={lookup.get('match_count', 0)} "
        f"duplicate={lookup.get('downstream_duplicate_state') or 'none'}",
        "Write: "
        f"state={write.get('state') or 'none'} "
        f"simulated={write.get('simulated')} "
        f"resource={write.get('resource_id') or 'none'}",
        "Readback: "
        f"state={readback.get('state') or 'none'} "
        f"matched={readback.get('matched')} "
        f"resource={readback.get('resource_id') or 'none'}",
        "Apply report: "
        f"state={apply_report.get('state') or 'none'} "
        f"consistency_errors={len(apply_report.get('consistency_errors') or [])} "
        f"closeout_errors={len(apply_report.get('closeout_consistency_errors') or [])}",
        f"Observed: writes={report.get('writes_attempted', 0)} network={report.get('network_calls_made', 0)}",
    ]
    if payload.get("closeout_path"):
        lines.append(f"Closeout path: {payload.get('closeout_path')}")
    missing_rows = missing_artifacts if isinstance(missing_artifacts, list) else []
    lines.append(f"Missing artifacts: {len(missing_rows)}")
    for artifact in missing_rows:
        lines.append(f" - {artifact}")
    blocked_rows = blocked_reasons if isinstance(blocked_reasons, list) else []
    lines.append(f"Blocked reasons: {len(blocked_rows)}")
    for reason in blocked_rows:
        lines.append(f" - {reason}")
    for label, key in [
        ("Selected target audit", "selected_target_audit"),
        ("Lookup smoke", "lookup_smoke"),
        ("Apply pilot report", "apply_pilot_report"),
        ("Closeout", "closeout"),
    ]:
        command = commands.get(key)
        if command:
            lines.append(f"{label}: {command}")
    stops = stop_conditions if isinstance(stop_conditions, list) else []
    lines.append(f"Stop conditions: {len(stops)}")
    for condition in stops:
        lines.append(f" - {condition}")
    return "\n".join(lines) + "\n"


def _render_lookup_smoke_handoff_text(payload: dict[str, object]) -> str:
    handoff = dict(payload.get("handoff") or payload)
    readiness = dict(handoff.get("readiness") or {})
    missing = handoff.get("missing_requirements") or []
    artifacts = dict(handoff.get("artifacts") or {})
    commands = dict(handoff.get("commands") or {})
    stop_conditions = handoff.get("stop_conditions") or []
    lines = [
        f"Lookup smoke handoff: {handoff.get('state')}",
        f"Run: {handoff.get('run_id')}",
        f"Job: {handoff.get('job_id')}",
        f"Sink: {handoff.get('sink')}",
        f"Approved by: {handoff.get('approved_by')}",
        f"Read only: {handoff.get('read_only')}",
        f"Readiness: {readiness.get('state') or readiness.get('status') or 'unknown'}",
        f"Observed: writes={handoff.get('writes_attempted', 0)} network={handoff.get('network_calls_made', 0)}",
    ]
    if payload.get("handoff_path"):
        lines.append(f"Handoff path: {payload.get('handoff_path')}")
    missing_rows = missing if isinstance(missing, list) else []
    lines.append(f"Missing requirements: {len(missing_rows)}")
    for requirement in missing_rows:
        lines.append(f" - {requirement}")
    if artifacts:
        lines.append("Artifacts:")
        for name, artifact in sorted(artifacts.items()):
            if isinstance(artifact, dict):
                lines.append(f" - {name}: exists={artifact.get('exists', False)} path={artifact.get('path')}")
    for label, key in [
        ("Lookup readiness", "lookup_readiness"),
        ("Live lookup pilot", "live_lookup_pilot"),
        ("Assess duplicates", "assess_duplicates"),
        ("Review bundle", "review_bundle"),
    ]:
        command = commands.get(key)
        if command:
            lines.append(f"{label}: {command}")
    stops = stop_conditions if isinstance(stop_conditions, list) else []
    lines.append(f"Stop conditions: {len(stops)}")
    for condition in stops:
        lines.append(f" - {condition}")
    note = handoff.get("operator_note")
    if note:
        lines.append(f"Operator note: {note}")
    return "\n".join(lines) + "\n"


def _render_apply_pilot_report_text(payload: dict[str, object]) -> str:
    report = dict(payload.get("report") or payload)
    missing_artifacts = report.get("missing_artifacts") or []
    consistency_errors = report.get("consistency_errors") or []
    sinks = report.get("sinks") or []
    paths = dict(report.get("artifact_paths") or {})
    lines = [
        f"Apply pilot report: {report.get('state')}",
        f"Run: {report.get('run_id')}",
        f"Job: {report.get('job_id')}",
        f"Reason: {report.get('reason') or 'none'}",
        (
            "Evidence: "
            f"readiness={report.get('readiness_state') or 'missing'} "
            f"apply_result={report.get('apply_result_state') or 'missing'} "
            f"readback_request={report.get('readback_request_state') or 'missing'}"
        ),
        f"Observed: writes={report.get('writes_attempted', 0)} network={report.get('network_calls_made', 0)}",
    ]
    if payload.get("report_path"):
        lines.append(f"Report path: {payload.get('report_path')}")
    sink_rows = sinks if isinstance(sinks, list) else []
    lines.append(f"Sinks: {len(sink_rows)}")
    for sink in sink_rows:
        sink_report = dict(sink)
        lines.append(
            " - "
            f"{sink_report.get('sink') or 'unknown'}: "
            f"write={sink_report.get('write_state') or 'missing'} "
            f"write_simulated={sink_report.get('write_simulated')} "
            f"write_resource={sink_report.get('write_resource_id') or 'none'} "
            f"readback={sink_report.get('readback_state') or 'missing'} "
            f"readback_simulated={sink_report.get('readback_simulated')} "
            f"readback_matched={sink_report.get('readback_matched')} "
            f"readback_resource={sink_report.get('readback_resource_id') or 'none'}"
        )
    missing_rows = missing_artifacts if isinstance(missing_artifacts, list) else []
    lines.append(f"Missing artifacts: {len(missing_rows)}")
    for artifact in missing_rows:
        lines.append(f" - {artifact}")
    error_rows = consistency_errors if isinstance(consistency_errors, list) else []
    lines.append(f"Consistency errors: {len(error_rows)}")
    for error in error_rows:
        lines.append(f" - {error}")
    if paths:
        lines.append("Artifact paths:")
        for key in sorted(paths):
            lines.append(f" - {key}: {paths[key]}")
    return "\n".join(lines) + "\n"


def _render_apply_pilot_bundle_text(payload: dict[str, object]) -> str:
    bundle = dict(payload.get("bundle") or payload)
    readiness = dict(bundle.get("readiness") or {})
    missing = bundle.get("missing_requirements") or []
    requirements = bundle.get("requirements") or []
    commands = dict(bundle.get("commands") or {})
    stop_conditions = bundle.get("stop_conditions") or []
    remediation = dict(bundle.get("remediation") or {})
    lines = [
        f"Apply pilot bundle: {bundle.get('state')}",
        f"Run: {bundle.get('run_id')}",
        f"Job: {bundle.get('job_id')}",
        f"Sink: {bundle.get('sink')}",
        f"Operator: {bundle.get('operator')}",
        f"Mock pilot: {bundle.get('can_attempt_mock_pilot', False)}",
        f"Live pilot: {bundle.get('can_attempt_live_pilot', False)}",
        f"Readiness: {readiness.get('state') or readiness.get('status') or 'unknown'}",
        f"Observed: writes={bundle.get('writes_attempted', 0)} network={bundle.get('network_calls_made', 0)}",
    ]
    if payload.get("bundle_path"):
        lines.append(f"Bundle path: {payload.get('bundle_path')}")
    req_rows = requirements if isinstance(requirements, list) else []
    lines.append(f"Requirements: {len(req_rows)}")
    for requirement in req_rows:
        if isinstance(requirement, dict):
            lines.append(f" - {requirement.get('name')}: ok={requirement.get('ok')} reason={requirement.get('reason') or 'none'}")
    missing_rows = missing if isinstance(missing, list) else []
    lines.append(f"Missing requirements: {len(missing_rows)}")
    for requirement in missing_rows:
        lines.append(f" - {requirement}")
    for label, key in [
        ("Apply pilot readiness", "apply_pilot_readiness"),
        ("Mock write", "mock_write"),
        ("Live write", "live_write"),
        ("Readback request", "readback_request"),
        ("Mock readback", "mock_readback"),
        ("Live readback", "live_readback"),
        ("Pilot report", "pilot_report"),
    ]:
        command = commands.get(key)
        if command:
            lines.append(f"{label}: {command}")
    stops = stop_conditions if isinstance(stop_conditions, list) else []
    lines.append(f"Stop conditions: {len(stops)}")
    for condition in stops:
        lines.append(f" - {condition}")
    notes = remediation.get("notes") or remediation.get("manual_checks") or []
    note_rows = notes if isinstance(notes, list) else []
    if note_rows:
        lines.append("Remediation notes:")
        for note in note_rows:
            lines.append(f" - {note}")
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

    operator_dashboard = sub.add_parser("operator-dashboard")
    operator_dashboard.add_argument("--run-id", default=None)
    operator_dashboard.add_argument("--json", action="store_true")

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
    runs_live_pilot_validate_response = runs_sub.add_parser("live-pilot-validate-response")
    runs_live_pilot_validate_response.add_argument("run_id")
    runs_live_pilot_validate_response.add_argument("--response", required=True)
    runs_live_pilot_validate_response.add_argument("--json", action="store_true")

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
    actions_next = actions_sub.add_parser("next")
    actions_next.add_argument("--run-id", default=None)
    actions_next.add_argument("--limit", type=int, default=20)
    actions_next.add_argument("--json", action="store_true")
    actions_run_next = actions_sub.add_parser("run-next")
    actions_run_next.add_argument("--run-id", default=None)
    actions_run_next.add_argument("--limit", type=int, default=10)
    actions_run_next.add_argument("--json", action="store_true")

    drills = sub.add_parser("drills")
    drills_sub = drills.add_subparsers(dest="drills_command", required=True)
    drills_review_routing = drills_sub.add_parser("review-routing")
    drills_review_routing.add_argument("--json", action="store_true")

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
        print(json.dumps(payload, indent=2) if args.json else _render_status_text(payload), end="")
        return 0 if payload["skill_ready"] else 2

    if args.command == "operator-dashboard":
        payload = service.operator_dashboard(run_id=args.run_id)
        print(json.dumps(payload, indent=2) if args.json else _render_operator_dashboard_text(payload), end="")
        return 0 if payload["state"] != "blocked" else 2

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
        elif args.runs_command == "live-pilot-validate-response":
            payload = service.validate_live_pilot_operator_response(run_id=args.run_id, response=args.response)
        else:
            payload = service.get_run(args.run_id)
        if args.runs_command == "live-pilot-validate-response" and not args.json:
            print(_render_live_pilot_operator_response_validation_text(payload), end="")
            return 0
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
        if args.actions_command == "next":
            payload = service.next_actions(run_id=args.run_id, limit=args.limit)
        else:
            payload = service.run_next_actions(run_id=args.run_id, limit=args.limit)
        print(json.dumps(payload, indent=2) if args.json else payload)
        return 0

    if args.command == "drills":
        if args.drills_command == "review-routing":
            payload = service.review_routing_drill()
            if not args.json:
                print(_render_review_routing_drill_text(payload), end="")
                return 0
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
        if args.sinks_command == "live-selection-packet" and not args.json:
            print(_render_live_selection_packet_text(payload), end="")
            return 0
        if args.sinks_command == "selected-target-audit" and not args.json:
            print(_render_selected_target_audit_text(payload), end="")
            return 0
        if args.sinks_command == "live-pilot-closeout" and not args.json:
            print(_render_live_pilot_closeout_text(payload), end="")
            return 0
        if args.sinks_command == "lookup-smoke-handoff" and not args.json:
            print(_render_lookup_smoke_handoff_text(payload), end="")
            return 0
        if args.sinks_command == "apply-pilot-report" and not args.json:
            print(_render_apply_pilot_report_text(payload), end="")
            return 0
        if args.sinks_command == "apply-pilot-bundle" and not args.json:
            print(_render_apply_pilot_bundle_text(payload), end="")
            return 0
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
        print(json.dumps(payload, indent=2) if args.json else _render_watch_status_text(payload), end="")
        return 0 if payload["last_error"] is None else 2

    if args.command == "watch-dry-run":
        payload = service.watch_dry_run_harness()
        print(json.dumps(payload, indent=2) if args.json else _render_watch_dry_run_text(payload), end="")
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
