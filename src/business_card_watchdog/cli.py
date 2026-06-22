from __future__ import annotations

import argparse
import json
from pathlib import Path

from .api import create_app
from .config import load_config, write_default_config
from .cli_renderers import (
    render_lookup_selection_packet_text,
    render_pilot_readiness_report_text,
    render_review_route_readiness_text,
)
from .mcp import call_tool, manifest_json
from .mcp_server import serve_jsonl
from .service import BusinessCardService
from .service_ops import install_user_service, service_status, uninstall_user_service
from .surface_registry import (
    LOOKUP_SELECTION_PACKET_COMMAND,
    OPERATOR_LIVE_PILOT_READINESS_COMMAND,
    PILOT_READINESS_COMMAND,
    REVIEW_ROUTE_READINESS_COMMAND,
    SELECTED_TARGET_APPROVAL_BOUNDARY_COMMAND,
    SELECTED_TARGET_COMMAND_COPY_PACKET_COMMAND,
    add_operator_live_pilot_readiness_parser,
    add_pilot_readiness_runs_parser,
    add_review_route_runs_parsers,
    add_selected_target_runs_parsers,
    call_registered_cli_command,
)
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
        ("Offline pilot gap audit", "offline_pilot_gap_audit"),
        ("Operator-selected live smoke preflight", "operator_selected_live_smoke_preflight"),
        ("Service recovery", "service_recovery"),
        ("Watch status", "watch_status"),
        ("Watch backlog preflight", "watch_backlog_preflight"),
        ("Watch dry-run selection handoff", "watch_dry_run_selection_handoff"),
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


def _render_contacts_list_text(payload: dict[str, object]) -> str:
    store = dict(payload.get("store") or {})
    contacts = payload.get("contacts") or []
    lines = [
        "Contacts:",
        f"Store: {store.get('path')}",
        f"Schema version: {store.get('schema_version', 0)}",
        f"Count: {payload.get('count', 0)}",
    ]
    for contact in contacts if isinstance(contacts, list) else []:
        if isinstance(contact, dict):
            lines.append(
                " - "
                f"{contact.get('contact_id')} "
                f"{contact.get('display_name') or '(no name)'} "
                f"{contact.get('email') or ''} "
                f"run={contact.get('source_run_id')} job={contact.get('source_job_id')}"
            )
    return "\n".join(lines) + "\n"


def _render_contact_detail_text(payload: dict[str, object]) -> str:
    contact = dict(payload.get("contact") or {})
    lines = [
        f"Contact: {contact.get('contact_id')}",
        f"Name: {contact.get('display_name') or ''}",
        f"Organization: {contact.get('organization') or ''}",
        f"Email: {contact.get('email') or ''}",
        f"Phone: {contact.get('phone') or ''}",
        f"Source: run={contact.get('source_run_id')} job={contact.get('source_job_id')}",
        f"Assets: {len(contact.get('assets') or [])}",
        f"Extraction attempts: {len(contact.get('extraction_attempts') or [])}",
    ]
    return "\n".join(lines) + "\n"


def _render_contact_review_surface_text(payload: dict[str, object]) -> str:
    rows = payload.get("rows") or []
    lines = [
        "Contact review surface:",
        f"Count: {payload.get('count', 0)}",
    ]
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, dict):
            counts = dict(row.get("counts") or {})
            lines.append(
                " - "
                f"{row.get('contact_id')} "
                f"{row.get('display_name') or '(no name)'} "
                f"review={row.get('review_state')} "
                f"routes={counts.get('routing_decisions', 0)} "
                f"pending={counts.get('proposed_review_states', 0)} "
                f"mutations={counts.get('mutations', 0)}"
            )
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


def _render_watch_backlog_preflight_text(payload: dict[str, object]) -> str:
    counts = dict(payload.get("counts") or {})
    commands = dict(payload.get("commands") or {})
    safe_actions = payload.get("safe_next_actions") or []
    stop_conditions = payload.get("explicit_stop_conditions") or []
    lines = [
        f"Watch backlog preflight: {payload.get('state')}",
        f"Inputs: {payload.get('input_count', 0)}",
        f"Seen: {counts.get('seen', 0)}",
        f"Backlog: {counts.get('backlog', 0)}",
        f"Unsettled: {counts.get('unsettled', 0)}",
        f"Scan truncated: {payload.get('scan_truncated', False)}",
        f"Last error present: {payload.get('last_error_present', False)}",
        f"Recommended next action: {payload.get('recommended_next_action')}",
        "Observed: "
        f"files={payload.get('files_processed', 0)} "
        f"ocr={payload.get('ocr_attempted', 0)} "
        f"writes={payload.get('writes_attempted', 0)} "
        f"network={payload.get('network_calls_made', 0)}",
        f"Runtime artifact written: {payload.get('runtime_artifact_written', False)}",
    ]
    if payload.get("preflight_path"):
        lines.append(f"Preflight path: {payload.get('preflight_path')}")
    lines.append("Commands:")
    for label, key in [
        ("Watch status", "watch_status"),
        ("Watch backlog preflight", "watch_backlog_preflight"),
        ("Watch dry run", "watch_dry_run"),
        ("Watch once dry run", "watch_once_dry_run"),
        ("Runtime readiness", "runtime_readiness"),
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


def _render_watch_practice_corpus_manifest_text(payload: dict[str, object]) -> str:
    counts = dict(payload.get("counts") or {})
    commands = dict(payload.get("commands") or {})
    stop_conditions = payload.get("explicit_stop_conditions") or []
    lines = [
        f"Practice corpus manifest: {payload.get('state')}",
        f"Inputs: {payload.get('input_count', 0)}",
        f"Entries: {payload.get('entry_count', 0)}",
        f"Include globs: {len(payload.get('include_globs') or [])}",
        f"Images: {counts.get('images', 0)}",
        f"PDF documents: {counts.get('pdf_documents', 0)}",
        f"Current watcher processable: {counts.get('current_watcher_processable', 0)}",
        f"Unsettled: {counts.get('unsettled', 0)}",
        f"Errors: {counts.get('errors', 0)}",
        f"Scan truncated: {payload.get('scan_truncated', False)}",
        "Observed: "
        f"files={payload.get('files_processed', 0)} "
        f"ocr={payload.get('ocr_attempted', 0)} "
        f"pdfs={payload.get('pdfs_rasterized', 0)} "
        f"crops={payload.get('crops_created', 0)} "
        f"writes={payload.get('writes_attempted', 0)} "
        f"network={payload.get('network_calls_made', 0)}",
        f"Runtime artifact written: {payload.get('runtime_artifact_written', False)}",
    ]
    if payload.get("manifest_path"):
        lines.append(f"Manifest path: {payload.get('manifest_path')}")
    if commands.get("practice_corpus_manifest_preview"):
        lines.append(f"Preview: {commands.get('practice_corpus_manifest_preview')}")
    stop_rows = stop_conditions if isinstance(stop_conditions, list) else []
    lines.append(f"Stop conditions: {len(stop_rows)}")
    for condition in stop_rows:
        lines.append(f" - {condition}")
    return "\n".join(lines) + "\n"


def _render_watch_dry_run_selection_handoff_text(payload: dict[str, object]) -> str:
    commands = dict(payload.get("commands") or {})
    entries = payload.get("entries") or []
    stop_conditions = payload.get("explicit_stop_conditions") or []
    lines = [
        f"Watch dry-run selection handoff: {payload.get('state')}",
        f"Entries: {payload.get('entry_count', 0)}",
        f"Recommended next step: {payload.get('recommended_next_step')}",
        f"Handoff written: {payload.get('handoff_written', False)}",
    ]
    if payload.get("handoff_path"):
        lines.append(f"Handoff path: {payload.get('handoff_path')}")
    entry_rows = entries if isinstance(entries, list) else []
    for entry in entry_rows:
        if isinstance(entry, dict):
            lines.append(
                " - "
                f"{entry.get('input_ref')}: {entry.get('state')} "
                f"{entry.get('configured_ref_display')}"
            )
            if entry.get("operator_response_template"):
                lines.append(f"   Operator response: {entry.get('operator_response_template')}")
    lines.append("Commands:")
    for label, key in [
        ("Watch backlog preflight", "watch_backlog_preflight"),
        ("Validate operator response", "validate_operator_response"),
        ("Command copy packet", "command_copy_packet"),
    ]:
        command = commands.get(key)
        if command:
            lines.append(f" - {label}: {command}")
    stop_rows = stop_conditions if isinstance(stop_conditions, list) else []
    lines.append(f"Stop conditions: {len(stop_rows)}")
    for condition in stop_rows:
        lines.append(f" - {condition}")
    return "\n".join(lines) + "\n"


def _render_watch_dry_run_operator_response_validation_text(payload: dict[str, object]) -> str:
    response = dict(payload.get("operator_response_redacted") or {})
    fields = dict(response.get("fields") or {})
    lines = [
        f"Watch dry-run response validation: {payload.get('state')}",
        f"Next validation step: {payload.get('next_validation_step')}",
        f"Input ref: {fields.get('input_ref') or 'none'}",
        f"Operator: {fields.get('operator') or 'none'}",
        f"Mode: {fields.get('mode') or 'none'}",
        f"Safety confirmation present: {response.get('safety_confirmation_present', False)}",
        f"Missing fields: {len(payload.get('missing_fields') or [])}",
        f"Mismatches: {len(payload.get('mismatches') or [])}",
        f"Observed: files={payload.get('files_processed', 0)} ocr={payload.get('ocr_attempted', 0)} "
        f"writes={payload.get('writes_attempted', 0)} network={payload.get('network_calls_made', 0)}",
    ]
    for item in payload.get("missing_fields") or []:
        lines.append(f" - missing: {item}")
    for item in payload.get("mismatches") or []:
        lines.append(f" - mismatch: {item}")
    return "\n".join(lines) + "\n"


def _render_watch_dry_run_command_copy_packet_text(payload: dict[str, object]) -> str:
    lines = [
        f"Watch dry-run command copy packet: {payload.get('state')}",
        f"Validation state: {payload.get('validation_state')}",
        f"Acknowledgement ok: {payload.get('acknowledgement_ok', False)}",
        f"Command copy text: {payload.get('command_copy_text') or 'none'}",
        f"Observed: files={payload.get('files_processed', 0)} ocr={payload.get('ocr_attempted', 0)} "
        f"writes={payload.get('writes_attempted', 0)} network={payload.get('network_calls_made', 0)}",
    ]
    for reason in payload.get("blocked_reasons") or []:
        lines.append(f" - blocked: {reason}")
    return "\n".join(lines) + "\n"


def _render_watch_dry_run_readiness_text(payload: dict[str, object]) -> str:
    preflight = dict(payload.get("preflight_summary") or {})
    counts = dict(preflight.get("counts") or {})
    handoff = dict(payload.get("handoff_summary") or {})
    checks = payload.get("readiness_checks") or []
    sequence = payload.get("operator_sequence") or []
    blocked_reasons = payload.get("blocked_reasons") or []
    commands = dict(payload.get("commands") or {})
    stop_conditions = payload.get("explicit_stop_conditions") or []
    lines = [
        f"Watch dry-run readiness: {payload.get('state')}",
        f"Recommended next step: {payload.get('recommended_next_step')}",
        f"Inputs: {preflight.get('input_count', 0)}",
        f"Backlog: {counts.get('backlog', 0)}",
        f"Unsettled: {counts.get('unsettled', 0)}",
        f"Handoff: {handoff.get('state')}",
        f"Entries: {handoff.get('entry_count', 0)}",
        "Observed: "
        f"files={payload.get('files_processed', 0)} "
        f"ocr={payload.get('ocr_attempted', 0)} "
        f"writes={payload.get('writes_attempted', 0)} "
        f"network={payload.get('network_calls_made', 0)}",
        f"Runtime artifact written: {payload.get('runtime_artifact_written', False)}",
    ]
    if payload.get("readiness_path"):
        lines.append(f"Readiness path: {payload.get('readiness_path')}")
    check_rows = checks if isinstance(checks, list) else []
    lines.append(f"Readiness checks: {len(check_rows)}")
    for check in check_rows:
        if isinstance(check, dict):
            lines.append(f" - {check.get('check')}: {check.get('status')}")
    blocked_rows = blocked_reasons if isinstance(blocked_reasons, list) else []
    if blocked_rows:
        lines.append("Blocked reasons:")
        for reason in blocked_rows:
            lines.append(f" - {reason}")
    sequence_rows = sequence if isinstance(sequence, list) else []
    lines.append(f"Operator sequence: {len(sequence_rows)}")
    for step in sequence_rows:
        if isinstance(step, dict):
            lines.append(f" - {step.get('step')}: {step.get('command')}")
    lines.append("Commands:")
    for label, key in [
        ("Readiness", "watch_dry_run_readiness"),
        ("Execution drill", "watch_dry_run_execution_drill"),
        ("Selection handoff", "watch_dry_run_selection_handoff"),
        ("Command copy packet", "watch_dry_run_command_copy_packet"),
        ("Watch once dry run", "watch_once_dry_run"),
    ]:
        command = commands.get(key)
        if command:
            lines.append(f" - {label}: {command}")
    stop_rows = stop_conditions if isinstance(stop_conditions, list) else []
    lines.append(f"Stop conditions: {len(stop_rows)}")
    for condition in stop_rows:
        lines.append(f" - {condition}")
    return "\n".join(lines) + "\n"


def _render_review_routing_drill_text(payload: dict[str, object]) -> str:
    review = dict(payload.get("review") or {})
    safe_actions = dict(payload.get("safe_actions") or {})
    readback = dict(payload.get("agent_loop_readback") or {})
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
        f"Agent readback: {readback.get('state') or 'unknown'}",
        f"Manual boundary: {readback.get('next_manual_boundary') or 'none'}",
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


def _render_live_pilot_rehearsal_drill_text(payload: dict[str, object]) -> str:
    assertions = dict(payload.get("assertions") or {})
    commands = dict(payload.get("commands") or {})
    sample_outputs = dict(payload.get("sample_outputs") or {})
    stop_conditions = payload.get("explicit_stop_conditions") or []
    failed = [key for key, value in assertions.items() if value is not True]
    lines = [
        "Live pilot rehearsal drill:",
        f"Run: {payload.get('run_id')}",
        f"Job: {payload.get('job_id')}",
        f"State: {payload.get('state')}",
        f"Sink: {payload.get('sink')}",
        f"Operator: {payload.get('operator')}",
        f"Scope: {payload.get('scope')}",
        f"Command copy ready: {payload.get('command_copy_ready', False)}",
        "Observed: "
        f"writes={payload.get('writes_attempted', 0)} "
        f"network={payload.get('network_calls_made', 0)} "
        f"private_sources={payload.get('private_sources_used', False)} "
        f"live_sinks={payload.get('live_sink_calls_made', False)}",
        f"Assertions: {len(assertions)}",
    ]
    if failed:
        lines.append("Failed assertions: " + ", ".join(sorted(failed)))
    for label, key in [
        ("Operator dashboard", "operator_dashboard"),
        ("Live pilot status", "live_pilot_status"),
        ("Live pilot handoff", "live_pilot_handoff"),
        ("Selected target approval boundary", "selected_target_approval_boundary"),
        ("Selected target command copy packet", "selected_target_command_copy_packet"),
        ("Command copy packet", "command_copy_packet"),
    ]:
        command = commands.get(key)
        if command:
            lines.append(f"{label}: {command}")
    if sample_outputs.get("live_pilot_rehearsal_markdown_path"):
        lines.append(f"Sample output: {sample_outputs.get('live_pilot_rehearsal_markdown_path')}")
    stop_rows = stop_conditions if isinstance(stop_conditions, list) else []
    lines.append(f"Stop conditions: {len(stop_rows)}")
    for condition in stop_rows:
        lines.append(f" - {condition}")
    return "\n".join(lines) + "\n"


def _render_child_replacement_readiness_drill_text(payload: dict[str, object]) -> str:
    assertions = dict(payload.get("assertions") or {})
    sample_outputs = dict(payload.get("sample_outputs") or {})
    readiness_states = dict(payload.get("readiness_states") or {})
    commands = dict(payload.get("commands") or {})
    stop_conditions = payload.get("explicit_stop_conditions") or []
    failed = [key for key, value in assertions.items() if value is not True]
    lines = [
        "Child replacement readiness drill:",
        f"Run: {payload.get('run_id')}",
        f"Job: {payload.get('job_id')}",
        f"Candidate: {payload.get('candidate_id')}",
        f"State: {payload.get('state')}",
        f"Fixture child candidates: {payload.get('fixture_child_candidate_count')}",
        "Observed: "
        f"writes={payload.get('writes_attempted', 0)} "
        f"network={payload.get('network_calls_made', 0)} "
        f"private_sources={payload.get('private_sources_used', False)} "
        f"live_sinks={payload.get('live_sink_calls_made', False)}",
        f"Assertions: {len(assertions)}",
    ]
    if failed:
        lines.append("Failed assertions: " + ", ".join(sorted(failed)))
    for key in [
        "blocked_replacement_audit",
        "blocked_replacement_validation",
        "replacement_handoff",
        "replacement_response",
        "replacement_checklist",
        "ready_replacement_copy_packet",
        "closeout",
    ]:
        if key in readiness_states:
            lines.append(f"{key}: {readiness_states.get(key)}")
    for label, key in [
        ("Review bundle", "review_bundle_path"),
        ("Review HTML", "review_html_path"),
        ("Review workbook", "review_workbook_path"),
        ("Sample output", "child_replacement_readiness_markdown_path"),
    ]:
        value = sample_outputs.get(key)
        if value:
            lines.append(f"{label}: {value}")
    for label, key in [
        ("Operator dashboard", "operator_dashboard"),
        ("Closeout status", "closeout_status"),
        ("Review bundle", "review_bundle"),
        ("Review HTML", "review_html"),
        ("Review workbook", "review_workbook"),
    ]:
        command = commands.get(key)
        if command:
            lines.append(f"{label}: {command}")
    stop_rows = stop_conditions if isinstance(stop_conditions, list) else []
    lines.append(f"Stop conditions: {len(stop_rows)}")
    for condition in stop_rows:
        lines.append(f" - {condition}")
    return "\n".join(lines) + "\n"


def _render_multi_card_preclassification_drill_text(payload: dict[str, object]) -> str:
    assertions = dict(payload.get("assertions") or {})
    commands = dict(payload.get("commands") or {})
    stop_conditions = payload.get("explicit_stop_conditions") or []
    failed = [key for key, value in assertions.items() if value is not True]
    lines = [
        "Multi-card preclassification drill:",
        f"Run: {payload.get('run_id')}",
        f"State: {payload.get('state')}",
        f"Expected cards: {payload.get('expected_card_count')}",
        f"Detected card-like boxes: {payload.get('detected_card_like_count')}",
        "Observed: "
        f"writes={payload.get('writes_attempted', 0)} "
        f"network={payload.get('network_calls_made', 0)} "
        f"private_sources={payload.get('private_sources_used', False)} "
        f"live_sinks={payload.get('live_sink_calls_made', False)}",
        f"Assertions: {len(assertions)}",
    ]
    if failed:
        lines.append("Failed assertions: " + ", ".join(sorted(failed)))
    for label, key in [
        ("Rerun drill", "multi_card_preclassification_drill"),
        ("Operator dashboard", "operator_dashboard"),
        ("Run show", "run_show"),
    ]:
        command = commands.get(key)
        if command:
            lines.append(f"{label}: {command}")
    stop_rows = stop_conditions if isinstance(stop_conditions, list) else []
    lines.append(f"Stop conditions: {len(stop_rows)}")
    for condition in stop_rows:
        lines.append(f" - {condition}")
    return "\n".join(lines) + "\n"


def _render_watch_dry_run_selection_drill_text(payload: dict[str, object]) -> str:
    assertions = dict(payload.get("assertions") or {})
    sample_outputs = dict(payload.get("sample_outputs") or {})
    commands = dict(payload.get("commands") or {})
    stop_conditions = payload.get("explicit_stop_conditions") or []
    failed = [key for key, value in assertions.items() if value is not True]
    lines = [
        "Watch dry-run selection drill:",
        f"Run: {payload.get('run_id')}",
        f"State: {payload.get('state')}",
        f"Command copy ready: {payload.get('command_copy_ready', False)}",
        "Observed: "
        f"files={payload.get('files_processed', 0)} "
        f"ocr={payload.get('ocr_attempted', 0)} "
        f"writes={payload.get('writes_attempted', 0)} "
        f"network={payload.get('network_calls_made', 0)}",
        f"Assertions: {len(assertions)}",
    ]
    if failed:
        lines.append("Failed assertions: " + ", ".join(sorted(failed)))
    if sample_outputs.get("watch_dry_run_selection_markdown_path"):
        lines.append(f"Sample output: {sample_outputs.get('watch_dry_run_selection_markdown_path')}")
    lines.append("Commands:")
    for label, key in [
        ("Backlog preflight", "watch_backlog_preflight"),
        ("Selection handoff", "watch_dry_run_selection_handoff"),
        ("Validate response", "watch_dry_run_validate_response"),
        ("Command copy packet", "watch_dry_run_command_copy_packet"),
    ]:
        command = commands.get(key)
        if command:
            lines.append(f" - {label}: {command}")
    stop_rows = stop_conditions if isinstance(stop_conditions, list) else []
    lines.append(f"Stop conditions: {len(stop_rows)}")
    for condition in stop_rows:
        lines.append(f" - {condition}")
    return "\n".join(lines) + "\n"


def _render_watch_dry_run_execution_drill_text(payload: dict[str, object]) -> str:
    assertions = dict(payload.get("assertions") or {})
    sample_outputs = dict(payload.get("sample_outputs") or {})
    commands = dict(payload.get("commands") or {})
    processed_run = dict(payload.get("processed_run") or {})
    stop_conditions = payload.get("explicit_stop_conditions") or []
    failed = [key for key, value in assertions.items() if value is not True]
    lines = [
        "Watch dry-run execution drill:",
        f"Drill: {payload.get('drill_id')}",
        f"State: {payload.get('state')}",
        f"Processed run: {processed_run.get('run_id')}",
        f"Processed run state: {processed_run.get('state')}",
        "Observed: "
        f"files={payload.get('files_processed', 0)} "
        f"ocr={payload.get('ocr_attempted', 0)} "
        f"writes={payload.get('writes_attempted', 0)} "
        f"network={payload.get('network_calls_made', 0)}",
        f"Assertions: {len(assertions)}",
    ]
    if failed:
        lines.append("Failed assertions: " + ", ".join(sorted(failed)))
    if sample_outputs.get("watch_dry_run_execution_markdown_path"):
        lines.append(f"Sample output: {sample_outputs.get('watch_dry_run_execution_markdown_path')}")
    lines.append("Commands:")
    for label, key in [
        ("Re-run execution drill", "watch_dry_run_execution_drill"),
        ("Selection drill", "watch_dry_run_selection_drill"),
        ("Run summary", "run_summary"),
        ("Operator dashboard", "operator_dashboard"),
    ]:
        command = commands.get(key)
        if command:
            lines.append(f" - {label}: {command}")
    stop_rows = stop_conditions if isinstance(stop_conditions, list) else []
    lines.append(f"Stop conditions: {len(stop_rows)}")
    for condition in stop_rows:
        lines.append(f" - {condition}")
    return "\n".join(lines) + "\n"


def _render_operator_dashboard_text(payload: dict[str, object]) -> str:
    runtime = dict(payload.get("runtime_readiness") or {})
    recovery = dict(payload.get("service_recovery") or {})
    run_summary = dict(payload.get("run_summary") or {})
    phase = dict(payload.get("phase_dashboard_summary") or {})
    live = dict(payload.get("live_pilot_summary") or {})
    live_handoff = dict(payload.get("live_pilot_handoff_summary") or {})
    checklist_rollup = dict(live_handoff.get("pilot_checklist_rollup") or {})
    latest_drill = dict(payload.get("latest_review_routing_drill") or {})
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
        "Live pilot checklist: "
        f"jobs={checklist_rollup.get('checklist_job_count', 0)} "
        f"steps={checklist_rollup.get('step_count', 0)} "
        f"live_calls={checklist_rollup.get('live_call_count', 0)} "
        f"sink_writes={checklist_rollup.get('sink_write_step_count', 0)} "
        f"explicit_steps={checklist_rollup.get('explicit_operator_step_count', 0)}",
        "Latest review routing drill: "
        f"{latest_drill.get('state') or 'not_run'} "
        f"run={latest_drill.get('run_id') or 'none'} "
        f"readback={latest_drill.get('agent_readback_state') or 'none'} "
        f"manual={latest_drill.get('next_manual_boundary') or 'none'}",
        f"Observed: writes={payload.get('writes_attempted', 0)} network={payload.get('network_calls_made', 0)}",
        "Commands:",
    ]
    for label, key in [
        ("Status", "status"),
        ("Runtime readiness", "runtime_readiness"),
        ("Service recovery", "service_recovery"),
        ("Runs list", "runs_list"),
        ("Review queue", "review_queue"),
        ("Child review queue", "child_review_queue"),
        ("Phase report", "phase_report"),
        ("Next actions", "next_actions"),
        ("Run next safe", "run_next_safe"),
        ("Multi-card preclassification drill", "multi_card_preclassification_drill"),
        ("Review routing drill", "review_routing_drill"),
        ("Live pilot rehearsal drill", "live_pilot_rehearsal_drill"),
        ("Live pilot status", "live_pilot_status"),
        ("Live pilot handoff", "live_pilot_handoff"),
        ("Live pilot approval packet", "live_pilot_approval_packet"),
        ("Live pilot validate response", "live_pilot_validate_response"),
        ("Selected target preflight", "selected_live_target_preflight"),
        ("Selected target approval boundary", "selected_target_approval_boundary"),
        ("Selected target command copy packet", "selected_target_command_copy_packet"),
        ("Selected target preview", "selected_live_target_preview"),
        ("Selected target from response", "selected_live_target_from_response"),
        ("Selected target handoff", "selected_live_target_handoff_from_response"),
        ("Lookup smoke handoff", "lookup_smoke_handoff_from_response"),
        ("Lookup smoke execution packet", "selected_lookup_smoke_execution_packet_from_response"),
        ("Write pilot execution packet", "selected_write_pilot_execution_packet_from_response"),
        ("Readback pilot execution packet", "selected_readback_pilot_execution_packet_from_response"),
        ("Live pilot closeout packet", "live_pilot_closeout_packet_from_response"),
        ("Live pilot workflow packet", "live_pilot_operator_workflow_packet_from_response"),
        ("Live pilot rehearsal", "live_pilot_operator_rehearsal_from_response"),
        ("Live pilot readiness export", "live_pilot_readiness_export_from_response"),
        ("Live pilot execution checklist", "live_pilot_execution_checklist_from_response"),
        ("Live pilot command copy packet", "live_pilot_command_copy_packet_from_response"),
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
            ("Multi-card preclassification drill", "multi_card_preclassification_drill"),
            ("Review routing drill", "review_routing_drill"),
            ("Live pilot rehearsal drill", "live_pilot_rehearsal_drill"),
            ("Live pilot status", "live_pilot_status"),
            ("Live pilot handoff", "live_pilot_handoff"),
            ("Live pilot approval packet", "live_pilot_approval_packet"),
            ("Live pilot validate response", "live_pilot_validate_response"),
            ("Selected target preflight", "selected_live_target_preflight"),
            ("Selected target approval boundary", "selected_target_approval_boundary"),
            ("Selected target command copy packet", "selected_target_command_copy_packet"),
            ("Selected target preview", "selected_live_target_preview"),
            ("Selected target from response", "selected_live_target_from_response"),
            ("Selected target handoff", "selected_live_target_handoff_from_response"),
            ("Lookup smoke handoff", "lookup_smoke_handoff_from_response"),
            ("Lookup smoke execution packet", "selected_lookup_smoke_execution_packet_from_response"),
            ("Write pilot execution packet", "selected_write_pilot_execution_packet_from_response"),
            ("Readback pilot execution packet", "selected_readback_pilot_execution_packet_from_response"),
            ("Live pilot closeout packet", "live_pilot_closeout_packet_from_response"),
            ("Live pilot workflow packet", "live_pilot_operator_workflow_packet_from_response"),
            ("Live pilot rehearsal", "live_pilot_operator_rehearsal_from_response"),
            ("Live pilot readiness export", "live_pilot_readiness_export_from_response"),
            ("Live pilot execution checklist", "live_pilot_execution_checklist_from_response"),
            ("Live pilot command copy packet", "live_pilot_command_copy_packet_from_response"),
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
            ("Multi-card preclassification drill", "multi_card_preclassification_drill"),
            ("Review routing drill", "review_routing_drill"),
            ("Live pilot rehearsal drill", "live_pilot_rehearsal_drill"),
            ("Live pilot status", "live_pilot_status"),
            ("Live pilot handoff", "live_pilot_handoff"),
            ("Live pilot approval packet", "live_pilot_approval_packet"),
            ("Live pilot validate response", "live_pilot_validate_response"),
            ("Selected target preflight", "selected_live_target_preflight"),
            ("Selected target approval boundary", "selected_target_approval_boundary"),
            ("Selected target command copy packet", "selected_target_command_copy_packet"),
            ("Selected target preview", "selected_live_target_preview"),
            ("Selected target from response", "selected_live_target_from_response"),
            ("Selected target handoff", "selected_live_target_handoff_from_response"),
            ("Lookup smoke handoff", "lookup_smoke_handoff_from_response"),
            ("Lookup smoke execution packet", "selected_lookup_smoke_execution_packet_from_response"),
            ("Write pilot execution packet", "selected_write_pilot_execution_packet_from_response"),
            ("Readback pilot execution packet", "selected_readback_pilot_execution_packet_from_response"),
            ("Live pilot closeout packet", "live_pilot_closeout_packet_from_response"),
            ("Live pilot workflow packet", "live_pilot_operator_workflow_packet_from_response"),
            ("Live pilot rehearsal", "live_pilot_operator_rehearsal_from_response"),
            ("Live pilot readiness export", "live_pilot_readiness_export_from_response"),
            ("Live pilot execution checklist", "live_pilot_execution_checklist_from_response"),
            ("Live pilot command copy packet", "live_pilot_command_copy_packet_from_response"),
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
    execution_packet = dict(live_handoff.get("execution_packet") or {})
    if execution_packet:
        lines.append(
            "Live pilot execution packet: "
            f"state={execution_packet.get('state')} "
            f"operator_required={execution_packet.get('operator_required_count', 0)} "
            f"next_safe={execution_packet.get('next_safe_command') or 'none'} "
            f"next_explicit={execution_packet.get('next_explicit_operator_command') or 'none'}"
        )
        lines.append(
            "Live pilot execution policy: "
            f"forbid_live_or_sink={execution_packet.get('forbidden_live_or_sink_write_from_dashboard')}"
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
                sequence_summary = dict(entry.get("pilot_command_sequence_summary") or {})
                if sequence_summary:
                    lines.append(
                        "   Sequence: "
                        f"safe={sequence_summary.get('safe_inspection_step_count', 0)} "
                        f"explicit={sequence_summary.get('explicit_operator_step_count', 0)} "
                        f"live={sequence_summary.get('live_call_step_count', 0)} "
                        f"sink_writes={sequence_summary.get('sink_write_step_count', 0)} "
                        f"next_safe={sequence_summary.get('next_safe_inspection_step') or 'none'} "
                        f"next_explicit={sequence_summary.get('next_explicit_operator_step') or 'none'}"
                    )
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
    approval_readback = dict(payload.get("approval_readback") or {})
    if approval_readback:
        lines.append(
            "Approval readback: "
            f"state={approval_readback.get('state')} "
            f"matches_template={approval_readback.get('response_matches_template')} "
            f"missing={approval_readback.get('missing_field_count', 0)} "
            f"mismatches={approval_readback.get('mismatch_count', 0)} "
            f"next_safe={approval_readback.get('next_safe_step') or 'none'}"
        )
    sequence = payload.get("post_selection_sequence") or []
    if isinstance(sequence, list) and sequence:
        lines.append("Post-selection sequence:")
        for item in sequence:
            if isinstance(item, dict):
                lines.append(f" - {item.get('step')}: {item.get('command')}")
    grouped_sequence = dict(payload.get("validation_command_sequence") or {})
    if grouped_sequence:
        lines.append(
            "Validation sequence groups: "
            f"safe={grouped_sequence.get('safe_inspection_step_count', 0)} "
            f"explicit={grouped_sequence.get('explicit_operator_step_count', 0)} "
            f"live={grouped_sequence.get('live_call_step_count', 0)} "
            f"sink_writes={grouped_sequence.get('sink_write_step_count', 0)}"
        )
    stop_conditions = payload.get("explicit_stop_conditions") or []
    stops = stop_conditions if isinstance(stop_conditions, list) else []
    lines.append(f"Stop conditions: {len(stops)}")
    for condition in stops:
        lines.append(f" - {condition}")
    return "\n".join(lines) + "\n"


def _render_selected_live_target_preflight_text(payload: dict[str, object]) -> str:
    lines = [
        f"Run: {payload.get('run_id')}",
        f"Job: {payload.get('job_id') or 'none'}",
        f"State: {payload.get('state')}",
        f"Validation state: {payload.get('validation_state')}",
        f"Would create selected target: {payload.get('would_create_selected_live_target', False)}",
        f"Creates selected target: {payload.get('creates_selected_live_target', False)}",
        f"Observed: writes={payload.get('writes_attempted', 0)} network={payload.get('network_calls_made', 0)}",
    ]
    if payload.get("select_target_command"):
        lines.append(f"Select target: {payload.get('select_target_command')}")
    blockers = payload.get("blocked_reasons") or []
    rows = blockers if isinstance(blockers, list) else []
    lines.append(f"Blocked reasons: {len(rows)}")
    for reason in rows:
        lines.append(f" - {reason}")
    stop_conditions = payload.get("explicit_stop_conditions") or []
    stops = stop_conditions if isinstance(stop_conditions, list) else []
    lines.append(f"Stop conditions: {len(stops)}")
    for condition in stops:
        lines.append(f" - {condition}")
    return "\n".join(lines) + "\n"


def _render_selected_live_target_artifact_preview_text(payload: dict[str, object]) -> str:
    artifact_preview = dict(payload.get("artifact_preview") or {})
    lines = [
        f"Run: {payload.get('run_id')}",
        f"Job: {payload.get('job_id') or 'none'}",
        f"State: {payload.get('state')}",
        f"Preflight state: {payload.get('preflight_state')}",
        f"Would write path: {payload.get('would_write_path') or 'none'}",
        f"Would create selected target: {payload.get('would_create_selected_live_target', False)}",
        f"Creates selected target: {payload.get('creates_selected_live_target', False)}",
        f"Observed: writes={payload.get('writes_attempted', 0)} network={payload.get('network_calls_made', 0)}",
    ]
    if artifact_preview:
        lines.append(
            "Artifact preview: "
            f"sink={artifact_preview.get('sink')} "
            f"scope={artifact_preview.get('scope')} "
            f"operator={artifact_preview.get('operator')} "
            f"lookup={dict(artifact_preview.get('scope_allows') or {}).get('lookup')} "
            f"write={dict(artifact_preview.get('scope_allows') or {}).get('write')} "
            f"readback={dict(artifact_preview.get('scope_allows') or {}).get('readback')}"
        )
    blockers = payload.get("blocked_reasons") or []
    rows = blockers if isinstance(blockers, list) else []
    lines.append(f"Blocked reasons: {len(rows)}")
    for reason in rows:
        lines.append(f" - {reason}")
    stop_conditions = payload.get("explicit_stop_conditions") or []
    stops = stop_conditions if isinstance(stop_conditions, list) else []
    lines.append(f"Stop conditions: {len(stops)}")
    for condition in stops:
        lines.append(f" - {condition}")
    return "\n".join(lines) + "\n"


def _render_selected_live_target_from_response_text(payload: dict[str, object]) -> str:
    lines = [
        f"Run: {payload.get('run_id')}",
        f"State: {payload.get('state')}",
        f"Write selected target: {payload.get('write_selected_target', False)}",
        f"Creates selected target: {payload.get('creates_selected_live_target', False)}",
        f"Target path: {payload.get('target_path') or 'none'}",
        f"Observed: writes={payload.get('writes_attempted', 0)} network={payload.get('network_calls_made', 0)}",
    ]
    preview = dict(payload.get("preview") or {})
    if preview:
        lines.append(f"Preview state: {preview.get('state')}")
    blockers = payload.get("blocked_reasons") or []
    rows = blockers if isinstance(blockers, list) else []
    lines.append(f"Blocked reasons: {len(rows)}")
    for reason in rows:
        lines.append(f" - {reason}")
    stop_conditions = payload.get("explicit_stop_conditions") or []
    stops = stop_conditions if isinstance(stop_conditions, list) else []
    lines.append(f"Stop conditions: {len(stops)}")
    for condition in stops:
        lines.append(f" - {condition}")
    return "\n".join(lines) + "\n"


def _render_selected_live_target_handoff_from_response_text(payload: dict[str, object]) -> str:
    audit = dict(payload.get("selected_target_audit") or {})
    lines = [
        f"Run: {payload.get('run_id')}",
        f"Job: {payload.get('job_id') or 'none'}",
        f"State: {payload.get('state')}",
        f"Validation state: {payload.get('validation_state')}",
        f"Write audit: {payload.get('write_audit', False)}",
        f"Audit written: {payload.get('audit_written', False)}",
        f"Audit state: {audit.get('state') or 'none'}",
        f"Selected target: {payload.get('selected_target_identity') or 'none'}",
        f"Next safe command: {payload.get('next_safe_command') or 'none'}",
        f"Next explicit command: {payload.get('next_explicit_operator_command') or 'none'}",
        f"Creates selected target: {payload.get('creates_selected_live_target', False)}",
        f"Observed: writes={payload.get('writes_attempted', 0)} network={payload.get('network_calls_made', 0)}",
    ]
    blockers = payload.get("blocked_reasons") or []
    rows = blockers if isinstance(blockers, list) else []
    lines.append(f"Blocked reasons: {len(rows)}")
    for reason in rows:
        lines.append(f" - {reason}")
    stop_conditions = payload.get("explicit_stop_conditions") or []
    stops = stop_conditions if isinstance(stop_conditions, list) else []
    lines.append(f"Stop conditions: {len(stops)}")
    for condition in stops:
        lines.append(f" - {condition}")
    return "\n".join(lines) + "\n"


def _render_lookup_smoke_handoff_from_response_text(payload: dict[str, object]) -> str:
    handoff = dict(payload.get("lookup_smoke_handoff") or {})
    lines = [
        f"Run: {payload.get('run_id')}",
        f"Job: {payload.get('job_id') or 'none'}",
        f"State: {payload.get('state')}",
        f"Sink: {payload.get('sink') or 'none'}",
        f"Operator: {payload.get('operator') or 'none'}",
        f"Validation state: {payload.get('validation_state')}",
        f"Write handoff: {payload.get('write_handoff', False)}",
        f"Handoff written: {payload.get('handoff_written', False)}",
        f"Lookup handoff state: {handoff.get('state') or 'none'}",
        f"Next safe command: {payload.get('next_safe_command') or 'none'}",
        f"Next explicit command: {payload.get('next_explicit_operator_command') or 'none'}",
        f"Observed: writes={payload.get('writes_attempted', 0)} network={payload.get('network_calls_made', 0)}",
    ]
    blockers = payload.get("blocked_reasons") or []
    rows = blockers if isinstance(blockers, list) else []
    lines.append(f"Blocked reasons: {len(rows)}")
    for reason in rows:
        lines.append(f" - {reason}")
    stop_conditions = payload.get("explicit_stop_conditions") or []
    stops = stop_conditions if isinstance(stop_conditions, list) else []
    lines.append(f"Stop conditions: {len(stops)}")
    for condition in stops:
        lines.append(f" - {condition}")
    return "\n".join(lines) + "\n"


def _render_selected_lookup_smoke_execution_packet_from_response_text(payload: dict[str, object]) -> str:
    lines = [
        f"Run: {payload.get('run_id')}",
        f"Job: {payload.get('job_id') or 'none'}",
        f"State: {payload.get('state')}",
        f"Sink: {payload.get('sink') or 'none'}",
        f"Operator: {payload.get('operator') or 'none'}",
        f"Execute selected lookup smoke: {payload.get('execute_selected_lookup_smoke', False)}",
        f"Would execute selected lookup smoke: {payload.get('would_execute_selected_lookup_smoke', False)}",
        f"Smoke path: {payload.get('smoke_path') or 'none'}",
        f"Next safe command: {payload.get('next_safe_command') or 'none'}",
        f"Next explicit command: {payload.get('next_explicit_operator_command') or 'none'}",
        f"Observed: writes={payload.get('writes_attempted', 0)} network={payload.get('network_calls_made', 0)}",
    ]
    blockers = payload.get("blocked_reasons") or []
    rows = blockers if isinstance(blockers, list) else []
    lines.append(f"Blocked reasons: {len(rows)}")
    for reason in rows:
        lines.append(f" - {reason}")
    stop_conditions = payload.get("explicit_stop_conditions") or []
    stops = stop_conditions if isinstance(stop_conditions, list) else []
    lines.append(f"Stop conditions: {len(stops)}")
    for condition in stops:
        lines.append(f" - {condition}")
    return "\n".join(lines) + "\n"


def _render_selected_write_pilot_execution_packet_from_response_text(payload: dict[str, object]) -> str:
    lines = [
        f"Run: {payload.get('run_id')}",
        f"Job: {payload.get('job_id') or 'none'}",
        f"State: {payload.get('state')}",
        f"Sink: {payload.get('sink') or 'none'}",
        f"Operator: {payload.get('operator') or 'none'}",
        f"Execute write pilot: {payload.get('execute_write_pilot', False)}",
        f"Would execute write pilot: {payload.get('would_execute_write_pilot', False)}",
        f"Write pilot path: {payload.get('write_pilot_path') or 'none'}",
        f"Apply readiness path: {payload.get('apply_readiness_path') or 'none'}",
        f"Next safe command: {payload.get('next_safe_command') or 'none'}",
        f"Next explicit command: {payload.get('next_explicit_operator_command') or 'none'}",
        f"Observed: writes={payload.get('writes_attempted', 0)} network={payload.get('network_calls_made', 0)}",
    ]
    blockers = payload.get("blocked_reasons") or []
    rows = blockers if isinstance(blockers, list) else []
    lines.append(f"Blocked reasons: {len(rows)}")
    for reason in rows:
        lines.append(f" - {reason}")
    stop_conditions = payload.get("explicit_stop_conditions") or []
    stops = stop_conditions if isinstance(stop_conditions, list) else []
    lines.append(f"Stop conditions: {len(stops)}")
    for condition in stops:
        lines.append(f" - {condition}")
    return "\n".join(lines) + "\n"


def _render_selected_readback_pilot_execution_packet_from_response_text(payload: dict[str, object]) -> str:
    lines = [
        f"Run: {payload.get('run_id')}",
        f"Job: {payload.get('job_id') or 'none'}",
        f"State: {payload.get('state')}",
        f"Sink: {payload.get('sink') or 'none'}",
        f"Operator: {payload.get('operator') or 'none'}",
        f"Execute readback pilot: {payload.get('execute_readback_pilot', False)}",
        f"Would execute readback pilot: {payload.get('would_execute_readback_pilot', False)}",
        f"Readback pilot path: {payload.get('readback_pilot_path') or 'none'}",
        f"Next safe command: {payload.get('next_safe_command') or 'none'}",
        f"Next explicit command: {payload.get('next_explicit_operator_command') or 'none'}",
        f"Observed: writes={payload.get('writes_attempted', 0)} network={payload.get('network_calls_made', 0)}",
    ]
    blockers = payload.get("blocked_reasons") or []
    rows = blockers if isinstance(blockers, list) else []
    lines.append(f"Blocked reasons: {len(rows)}")
    for reason in rows:
        lines.append(f" - {reason}")
    stop_conditions = payload.get("explicit_stop_conditions") or []
    stops = stop_conditions if isinstance(stop_conditions, list) else []
    lines.append(f"Stop conditions: {len(stops)}")
    for condition in stops:
        lines.append(f" - {condition}")
    return "\n".join(lines) + "\n"


def _render_live_pilot_closeout_packet_from_response_text(payload: dict[str, object]) -> str:
    report = dict(payload.get("closeout_report") or {})
    lines = [
        f"Run: {payload.get('run_id')}",
        f"Job: {payload.get('job_id') or 'none'}",
        f"State: {payload.get('state')}",
        f"Closeout state: {report.get('state') or 'none'}",
        f"Sink: {payload.get('sink') or 'none'}",
        f"Operator: {payload.get('operator') or 'none'}",
        f"Write closeout: {payload.get('write_closeout', False)}",
        f"Closeout written: {payload.get('closeout_written', False)}",
        f"Closeout path: {payload.get('closeout_path') or 'none'}",
        f"Next safe command: {payload.get('next_safe_command') or 'none'}",
        f"Next explicit command: {payload.get('next_explicit_operator_command') or 'none'}",
        f"Observed: writes={payload.get('writes_attempted', 0)} network={payload.get('network_calls_made', 0)}",
    ]
    blockers = payload.get("blocked_reasons") or []
    rows = blockers if isinstance(blockers, list) else []
    lines.append(f"Blocked reasons: {len(rows)}")
    for reason in rows:
        lines.append(f" - {reason}")
    missing = report.get("missing_artifacts") or []
    missing_rows = missing if isinstance(missing, list) else []
    lines.append(f"Missing closeout artifacts: {len(missing_rows)}")
    for artifact in missing_rows:
        lines.append(f" - {artifact}")
    stop_conditions = payload.get("explicit_stop_conditions") or []
    stops = stop_conditions if isinstance(stop_conditions, list) else []
    lines.append(f"Stop conditions: {len(stops)}")
    for condition in stops:
        lines.append(f" - {condition}")
    return "\n".join(lines) + "\n"


def _render_live_pilot_operator_workflow_packet_from_response_text(payload: dict[str, object]) -> str:
    lines = [
        f"Run: {payload.get('run_id')}",
        f"Job: {payload.get('job_id') or 'none'}",
        f"State: {payload.get('state')}",
        f"Sink: {payload.get('sink') or 'none'}",
        f"Operator: {payload.get('operator') or 'none'}",
        f"Blocked steps: {payload.get('blocked_step_count', 0)}",
        f"Next safe command: {payload.get('next_safe_command') or 'none'}",
        f"Next explicit command: {payload.get('next_explicit_operator_command') or 'none'}",
        f"Observed: writes={payload.get('writes_attempted', 0)} network={payload.get('network_calls_made', 0)}",
    ]
    steps = payload.get("step_summary") or []
    step_rows = steps if isinstance(steps, list) else []
    lines.append(f"Workflow steps: {len(step_rows)}")
    for step in step_rows:
        if isinstance(step, dict):
            reasons = step.get("blocked_reasons") or []
            reason_count = len(reasons) if isinstance(reasons, list) else 0
            lines.append(f" - {step.get('step')}: state={step.get('state')} blockers={reason_count}")
    stop_conditions = payload.get("explicit_stop_conditions") or []
    stops = stop_conditions if isinstance(stop_conditions, list) else []
    lines.append(f"Stop conditions: {len(stops)}")
    for condition in stops:
        lines.append(f" - {condition}")
    return "\n".join(lines) + "\n"


def _render_live_pilot_operator_rehearsal_from_response_text(payload: dict[str, object]) -> str:
    lines = [
        f"Run: {payload.get('run_id')}",
        f"Job: {payload.get('job_id') or 'none'}",
        f"State: {payload.get('state')}",
        f"Workflow state: {payload.get('workflow_state')}",
        f"Sink: {payload.get('sink') or 'none'}",
        f"Operator: {payload.get('operator') or 'none'}",
        f"Next safe command: {payload.get('next_safe_command') or 'none'}",
        f"Next explicit command: {payload.get('next_explicit_operator_command') or 'none'}",
        f"Observed: writes={payload.get('writes_attempted', 0)} network={payload.get('network_calls_made', 0)}",
    ]
    steps = payload.get("rehearsal_steps") or []
    step_rows = steps if isinstance(steps, list) else []
    lines.append(f"Rehearsal steps: {len(step_rows)}")
    for step in step_rows:
        if isinstance(step, dict):
            lines.append(
                " - "
                f"{step.get('step')}: "
                f"safe={step.get('safe_to_auto_continue')} "
                f"explicit={step.get('requires_explicit_operator_action')} "
                f"command={step.get('command') or 'none'}"
            )
    blocked_steps = payload.get("workflow_blocked_steps") or []
    blocked_rows = blocked_steps if isinstance(blocked_steps, list) else []
    lines.append(f"Workflow blocked steps: {len(blocked_rows)}")
    for step in blocked_rows:
        lines.append(f" - {step}")
    stop_conditions = payload.get("explicit_stop_conditions") or []
    stops = stop_conditions if isinstance(stop_conditions, list) else []
    lines.append(f"Stop conditions: {len(stops)}")
    for condition in stops:
        lines.append(f" - {condition}")
    return "\n".join(lines) + "\n"


def _render_live_pilot_readiness_export_from_response_text(payload: dict[str, object]) -> str:
    response = dict(payload.get("operator_response_redacted") or {})
    review_packet = dict(payload.get("review_packet") or {})
    lines = [
        f"Run: {payload.get('run_id')}",
        f"Job: {payload.get('job_id') or 'none'}",
        f"State: {payload.get('state')}",
        f"Sink: {payload.get('sink') or 'none'}",
        f"Operator: {payload.get('operator') or 'none'}",
        f"Write export: {payload.get('write', False)}",
        f"Export written: {payload.get('export_written', False)}",
        f"Export path: {payload.get('export_path') or 'none'}",
        f"Raw response stored: {response.get('raw_response_stored', False)}",
        f"Next safe command: {review_packet.get('next_safe_command') or 'none'}",
        f"Next explicit command: {review_packet.get('next_explicit_operator_command') or 'none'}",
        f"Observed: writes={payload.get('writes_attempted', 0)} network={payload.get('network_calls_made', 0)}",
    ]
    steps = review_packet.get("rehearsal_steps") or []
    step_rows = steps if isinstance(steps, list) else []
    lines.append(f"Rehearsal steps: {len(step_rows)}")
    for step in step_rows:
        if isinstance(step, dict):
            lines.append(
                " - "
                f"{step.get('step')}: "
                f"safe={step.get('safe_to_auto_continue')} "
                f"explicit={step.get('requires_explicit_operator_action')} "
                f"command={step.get('command') or 'none'}"
            )
    blocked_steps = review_packet.get("workflow_blocked_steps") or []
    blocked_rows = blocked_steps if isinstance(blocked_steps, list) else []
    lines.append(f"Workflow blocked steps: {len(blocked_rows)}")
    for step in blocked_rows:
        lines.append(f" - {step}")
    stop_conditions = payload.get("explicit_stop_conditions") or []
    stops = stop_conditions if isinstance(stop_conditions, list) else []
    lines.append(f"Stop conditions: {len(stops)}")
    for condition in stops:
        lines.append(f" - {condition}")
    return "\n".join(lines) + "\n"


def _render_live_pilot_execution_checklist_from_response_text(payload: dict[str, object]) -> str:
    lines = [
        f"Run: {payload.get('run_id')}",
        f"Job: {payload.get('job_id') or 'none'}",
        f"State: {payload.get('state')}",
        f"Sink: {payload.get('sink') or 'none'}",
        f"Operator: {payload.get('operator') or 'none'}",
        f"Readiness export loaded: {payload.get('readiness_export_loaded', False)}",
        f"Executable live command: {payload.get('executable_live_command') or 'none'}",
        f"Next safe command: {payload.get('next_safe_command') or 'none'}",
        f"Observed: writes={payload.get('writes_attempted', 0)} network={payload.get('network_calls_made', 0)}",
    ]
    checks = payload.get("checklist_items") or []
    check_rows = checks if isinstance(checks, list) else []
    lines.append(f"Checklist items: {len(check_rows)}")
    for check in check_rows:
        if isinstance(check, dict):
            lines.append(f" - {check.get('name')}: ok={check.get('ok')} evidence={check.get('evidence')}")
    blockers = payload.get("blocked_reasons") or []
    blocker_rows = blockers if isinstance(blockers, list) else []
    lines.append(f"Blocked reasons: {len(blocker_rows)}")
    for reason in blocker_rows:
        lines.append(f" - {reason}")
    stop_conditions = payload.get("explicit_stop_conditions") or []
    stops = stop_conditions if isinstance(stop_conditions, list) else []
    lines.append(f"Stop conditions: {len(stops)}")
    for condition in stops:
        lines.append(f" - {condition}")
    return "\n".join(lines) + "\n"


def _render_live_pilot_command_copy_packet_from_response_text(payload: dict[str, object]) -> str:
    lines = [
        f"Run: {payload.get('run_id')}",
        f"Job: {payload.get('job_id') or 'none'}",
        f"State: {payload.get('state')}",
        f"Sink: {payload.get('sink') or 'none'}",
        f"Operator: {payload.get('operator') or 'none'}",
        f"Checklist state: {payload.get('checklist_state') or 'none'}",
        f"Acknowledgement required: {payload.get('acknowledgement_required', True)}",
        f"Acknowledgement ok: {payload.get('acknowledgement_ok', False)}",
        f"Command copy text: {payload.get('command_copy_text') or 'none'}",
        f"Observed: writes={payload.get('writes_attempted', 0)} network={payload.get('network_calls_made', 0)}",
    ]
    blockers = payload.get("blocked_reasons") or []
    blocker_rows = blockers if isinstance(blockers, list) else []
    lines.append(f"Blocked reasons: {len(blocker_rows)}")
    for reason in blocker_rows:
        lines.append(f" - {reason}")
    stop_conditions = payload.get("explicit_stop_conditions") or []
    stops = stop_conditions if isinstance(stop_conditions, list) else []
    lines.append(f"Stop conditions: {len(stops)}")
    for condition in stops:
        lines.append(f" - {condition}")
    return "\n".join(lines) + "\n"


def _render_live_pilot_approval_packet_text(payload: dict[str, object]) -> str:
    lines = [
        f"Run: {payload.get('run_id')}",
        f"State: {payload.get('state')}",
        f"Approval entries: {payload.get('entry_count', 0)}",
        f"Creates selected target: {payload.get('creates_selected_live_target', False)}",
        f"Observed: writes={payload.get('writes_attempted', 0)} network={payload.get('network_calls_made', 0)}",
    ]
    entries = payload.get("entries") or []
    rows = entries if isinstance(entries, list) else []
    if rows:
        lines.append("Approval packet entries:")
        for entry in rows:
            if isinstance(entry, dict):
                lines.append(
                    " - "
                    f"{entry.get('job_id')} "
                    f"sink={entry.get('sink')} "
                    f"scope={entry.get('scope')} "
                    f"next={entry.get('next_action')}"
                )
                if entry.get("operator_response_template"):
                    lines.append(f"   Operator response: {entry.get('operator_response_template')}")
                if entry.get("validation_command_prefilled"):
                    lines.append(f"   Validate prefilled response: {entry.get('validation_command_prefilled')}")
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


def _render_dry_run_closeout_text(payload: dict[str, object]) -> str:
    state_counts = dict(payload.get("state_counts") or {})
    artifact_counts = dict(payload.get("artifact_counts") or {})
    blocked_reasons = payload.get("blocked_reasons") or []
    actions = payload.get("safe_next_actions") or []
    commands = dict(payload.get("commands") or {})
    stop_conditions = payload.get("explicit_stop_conditions") or []
    lines = [
        f"Dry-run closeout: {payload.get('state')}",
        f"Run: {payload.get('run_id')}",
        f"Run state: {payload.get('run_state')}",
        f"Dry run: {payload.get('dry_run')}",
        f"Jobs: {payload.get('job_count', 0)}",
        f"Ready to route: {state_counts.get('ready_to_route', 0)}",
        f"Needs review: {state_counts.get('needs_review', 0)}",
        f"Failed: {state_counts.get('failed', 0)}",
        f"Contact candidates: {payload.get('contact_candidate_count', 0)}",
        f"Review artifacts: {payload.get('review_packet_count', 0) + payload.get('review_report_count', 0)}",
        f"Sink payloads: {payload.get('sink_payload_count', 0)}",
        f"Live event types: {len(payload.get('live_event_types') or [])}",
        f"Live artifact kinds: {len(payload.get('live_artifact_kinds') or [])}",
        "Observed: "
        f"files={payload.get('files_processed', 0)} "
        f"ocr_artifacts={payload.get('ocr_artifact_count', 0)} "
        f"writes={payload.get('writes_attempted', 0)} "
        f"network={payload.get('network_calls_made', 0)}",
        f"Runtime artifact written: {payload.get('runtime_artifact_written', False)}",
    ]
    if payload.get("closeout_path"):
        lines.append(f"Closeout path: {payload.get('closeout_path')}")
    if artifact_counts:
        lines.append(f"Artifact kinds: {len(artifact_counts)}")
    blocked_rows = blocked_reasons if isinstance(blocked_reasons, list) else []
    if blocked_rows:
        lines.append("Blocked reasons:")
        for reason in blocked_rows:
            lines.append(f" - {reason}")
    action_rows = actions if isinstance(actions, list) else []
    lines.append(f"Safe next actions: {len(action_rows)}")
    for action in action_rows:
        if isinstance(action, dict):
            lines.append(f" - {action.get('action')}: {action.get('command')}")
    lines.append("Commands:")
    for label, key in [
        ("Closeout", "dry_run_closeout"),
        ("Run summary", "run_summary"),
        ("Phase report", "phase_report"),
        ("Reviews", "reviews"),
        ("Next actions", "next_actions"),
        ("Operator dashboard", "operator_dashboard"),
    ]:
        command = commands.get(key)
        if command:
            lines.append(f" - {label}: {command}")
    stop_rows = stop_conditions if isinstance(stop_conditions, list) else []
    lines.append(f"Stop conditions: {len(stop_rows)}")
    for condition in stop_rows:
        lines.append(f" - {condition}")
    return "\n".join(lines) + "\n"


def _render_dry_run_review_handoff_text(payload: dict[str, object]) -> str:
    action_counts = dict(payload.get("next_action_counts") or {})
    commands = dict(payload.get("commands") or {})
    blocked_reasons = payload.get("blocked_reasons") or []
    safe_actions = payload.get("safe_auto_actions") or []
    explicit_actions = payload.get("explicit_operator_actions") or []
    stop_conditions = payload.get("explicit_stop_conditions") or []
    lines = [
        f"Dry-run review handoff: {payload.get('state')}",
        f"Run: {payload.get('run_id')}",
        f"Closeout: {payload.get('closeout_state')}",
        f"Jobs: {payload.get('job_count', 0)}",
        f"Needs review: {payload.get('needs_review_count', 0)}",
        f"Ready to route: {payload.get('ready_to_route_count', 0)}",
        f"Failed: {payload.get('failed_count', 0)}",
        f"Next actions: {payload.get('next_action_count', 0)}",
        f"Safe auto actions: {payload.get('safe_auto_action_count', 0)}",
        f"Explicit operator actions: {payload.get('explicit_operator_action_count', 0)}",
        "Observed: "
        f"writes={payload.get('writes_attempted', 0)} "
        f"network={payload.get('network_calls_made', 0)} "
        f"live_sinks={payload.get('live_sink_calls_made', False)}",
        f"Runtime artifact written: {payload.get('runtime_artifact_written', False)}",
    ]
    if payload.get("handoff_path"):
        lines.append(f"Handoff path: {payload.get('handoff_path')}")
    blocked_rows = blocked_reasons if isinstance(blocked_reasons, list) else []
    if blocked_rows:
        lines.append("Blocked reasons:")
        for reason in blocked_rows:
            lines.append(f" - {reason}")
    if action_counts:
        lines.append("Next action counts:")
        for action, count in sorted(action_counts.items()):
            lines.append(f" - {action}: {count}")
    safe_rows = safe_actions if isinstance(safe_actions, list) else []
    lines.append(f"Safe action rows: {len(safe_rows)}")
    for action in safe_rows[:10]:
        if isinstance(action, dict):
            lines.append(f" - {action.get('job_id')}: {action.get('action')} ({action.get('command')})")
    explicit_rows = explicit_actions if isinstance(explicit_actions, list) else []
    lines.append(f"Explicit action rows: {len(explicit_rows)}")
    for action in explicit_rows[:10]:
        if isinstance(action, dict):
            lines.append(f" - {action.get('job_id')}: {action.get('action')} ({action.get('command')})")
    lines.append("Commands:")
    for label, key in [
        ("Handoff", "dry_run_review_handoff"),
        ("Closeout", "dry_run_closeout"),
        ("Review bundle", "review_bundle"),
        ("Review workbook", "review_workbook"),
        ("Phase report", "phase_report"),
        ("Next actions", "next_actions"),
        ("Run next safe", "run_next_safe"),
        ("Operator dashboard", "operator_dashboard"),
        ("Live pilot status", "live_pilot_status"),
    ]:
        command = commands.get(key)
        if command:
            lines.append(f" - {label}: {command}")
    stop_rows = stop_conditions if isinstance(stop_conditions, list) else []
    lines.append(f"Stop conditions: {len(stop_rows)}")
    for condition in stop_rows:
        lines.append(f" - {condition}")
    return "\n".join(lines) + "\n"


def _render_dry_run_safe_loop_text(payload: dict[str, object]) -> str:
    before_counts = dict(payload.get("before_next_action_counts") or {})
    after_counts = dict(payload.get("after_next_action_counts") or {})
    commands = dict(payload.get("safe_inspection_commands") or {})
    stop_conditions = payload.get("explicit_stop_conditions") or []
    executed = payload.get("executed") or []
    skipped = payload.get("skipped") or []
    lines = [
        f"Dry-run safe loop: {payload.get('state')}",
        f"Run: {payload.get('run_id')}",
        f"Closeout: {payload.get('closeout_state')}",
        f"Before handoff: {payload.get('before_handoff_state')}",
        f"After handoff: {payload.get('after_handoff_state')}",
        f"Limit: {payload.get('limit', 0)}",
        f"Executed: {payload.get('executed_count', 0)}",
        f"Skipped: {payload.get('skipped_count', 0)}",
        f"Before safe auto actions: {payload.get('before_safe_auto_action_count', 0)}",
        f"After safe auto actions: {payload.get('after_safe_auto_action_count', 0)}",
        f"After explicit operator actions: {payload.get('after_explicit_operator_action_count', 0)}",
        "Observed: "
        f"writes={payload.get('writes_attempted', 0)} "
        f"network={payload.get('network_calls_made', 0)} "
        f"live_sinks={payload.get('live_sink_calls_made', False)}",
        f"Runtime artifact written: {payload.get('runtime_artifact_written', False)}",
    ]
    if payload.get("safe_loop_path"):
        lines.append(f"Safe loop path: {payload.get('safe_loop_path')}")
    if before_counts:
        lines.append("Before next action counts:")
        for action, count in sorted(before_counts.items()):
            lines.append(f" - {action}: {count}")
    if after_counts:
        lines.append("After next action counts:")
        for action, count in sorted(after_counts.items()):
            lines.append(f" - {action}: {count}")
    executed_rows = executed if isinstance(executed, list) else []
    lines.append(f"Executed rows: {len(executed_rows)}")
    for action in executed_rows[:10]:
        if isinstance(action, dict):
            lines.append(f" - {action.get('job_id')}: {action.get('action')}")
    skipped_rows = skipped if isinstance(skipped, list) else []
    lines.append(f"Skipped rows: {len(skipped_rows)}")
    for action in skipped_rows[:10]:
        if isinstance(action, dict):
            lines.append(f" - {action.get('job_id')}: {action.get('action')}")
    lines.append("Commands:")
    for label, key in [
        ("Safe loop", "dry_run_safe_loop"),
        ("Handoff", "dry_run_review_handoff"),
        ("Closeout", "dry_run_closeout"),
        ("Phase report", "phase_report"),
        ("Review bundle", "review_bundle"),
        ("Next actions", "next_actions"),
        ("Live pilot status", "live_pilot_status"),
    ]:
        command = commands.get(key)
        if command:
            lines.append(f" - {label}: {command}")
    stop_rows = stop_conditions if isinstance(stop_conditions, list) else []
    lines.append(f"Stop conditions: {len(stop_rows)}")
    for condition in stop_rows:
        lines.append(f" - {condition}")
    return "\n".join(lines) + "\n"


def _render_close_lookup_prerequisites_text(payload: dict[str, object]) -> str:
    commands = dict(payload.get("commands") or {})
    executed = payload.get("executed") or []
    skipped = payload.get("skipped") or []
    stop_conditions = payload.get("explicit_stop_conditions") or []
    lines = [
        f"Close lookup prerequisites: {payload.get('state')}",
        f"Run: {payload.get('run_id')}",
        f"Sink: {payload.get('sink') or 'auto'}",
        f"Operator: {payload.get('operator')}",
        f"Limit: {payload.get('limit', 0)}",
        f"Before packet: {payload.get('before_packet_state')}",
        f"After packet: {payload.get('after_packet_state')}",
        f"Executed: {payload.get('executed_count', 0)}",
        f"Skipped: {payload.get('skipped_count', 0)}",
        "Observed: "
        f"writes={payload.get('writes_attempted', 0)} "
        f"network={payload.get('network_calls_made', 0)} "
        f"live_sinks={payload.get('live_sink_calls_made', False)} "
        f"creates_selected_target={payload.get('creates_selected_live_target', False)}",
        f"Runtime artifact written: {payload.get('runtime_artifact_written', False)}",
    ]
    if payload.get("closeout_path"):
        lines.append(f"Closeout path: {payload.get('closeout_path')}")
    executed_rows = executed if isinstance(executed, list) else []
    lines.append(f"Executed rows: {len(executed_rows)}")
    for row in executed_rows[:10]:
        if isinstance(row, dict):
            lines.append(f" - {row.get('job_id')}: {row.get('action')}")
    skipped_rows = skipped if isinstance(skipped, list) else []
    lines.append(f"Skipped rows: {len(skipped_rows)}")
    for row in skipped_rows[:10]:
        if isinstance(row, dict):
            lines.append(f" - {row.get('job_id')}: {row.get('action')}")
    lines.append("Commands:")
    for label, key in [
        ("Close lookup prerequisites", "close_lookup_prerequisites"),
        ("Lookup selection packet", "lookup_selection_packet"),
        ("Review-route readiness", "review_route_readiness"),
        ("Next actions", "next_actions"),
        ("Review queue", "review_queue"),
        ("Live pilot status", "live_pilot_status"),
    ]:
        command = commands.get(key)
        if command:
            lines.append(f" - {label}: {command}")
    stop_rows = stop_conditions if isinstance(stop_conditions, list) else []
    lines.append(f"Stop conditions: {len(stop_rows)}")
    for condition in stop_rows:
        lines.append(f" - {condition}")
    return "\n".join(lines) + "\n"


def _render_selected_target_approval_boundary_text(payload: dict[str, object]) -> str:
    commands = dict(payload.get("commands") or {})
    lines = [
        f"Selected-target approval boundary: {payload.get('state')}",
        f"Run: {payload.get('run_id')}",
        f"Job: {payload.get('job_id') or 'none'}",
        f"Sink: {payload.get('sink') or 'none'}",
        f"Operator: {payload.get('operator')}",
        f"Response supplied: {payload.get('response_supplied', False)}",
        f"Approval entries: {payload.get('approval_entry_count', 0)}",
        f"Would create selected target: {payload.get('would_create_selected_live_target', False)}",
        f"Creates selected target: {payload.get('creates_selected_live_target', False)}",
        f"Observed: writes={payload.get('writes_attempted', 0)} network={payload.get('network_calls_made', 0)}",
        f"Runtime artifact written: {payload.get('runtime_artifact_written', False)}",
    ]
    if payload.get("boundary_path"):
        lines.append(f"Boundary path: {payload.get('boundary_path')}")
    if payload.get("operator_response_template"):
        lines.append(f"Operator response: {payload.get('operator_response_template')}")
    if payload.get("validation_command_prefilled"):
        lines.append(f"Validate prefilled response: {payload.get('validation_command_prefilled')}")
    blockers = payload.get("blocked_reasons") or []
    rows = blockers if isinstance(blockers, list) else []
    lines.append(f"Blocked reasons: {len(rows)}")
    for reason in rows:
        lines.append(f" - {reason}")
    lines.append("Commands:")
    for label, key in [
        ("Approval packet", "approval_packet"),
        ("Live pilot handoff", "live_pilot_handoff"),
        ("Boundary", "selected_target_approval_boundary"),
        ("Validate response", "validate_response"),
        ("Selected target preflight", "selected_target_preflight"),
        ("Selected target preview", "selected_target_preview"),
        ("Select target", "select_target"),
    ]:
        command = commands.get(key)
        if command:
            lines.append(f" - {label}: {command}")
    stop_conditions = payload.get("explicit_stop_conditions") or []
    stops = stop_conditions if isinstance(stop_conditions, list) else []
    lines.append(f"Stop conditions: {len(stops)}")
    for condition in stops:
        lines.append(f" - {condition}")
    return "\n".join(lines) + "\n"


def _render_selected_target_command_copy_packet_text(payload: dict[str, object]) -> str:
    lines = [
        f"Selected-target command copy packet: {payload.get('state')}",
        f"Run: {payload.get('run_id')}",
        f"Job: {payload.get('job_id') or 'none'}",
        f"Sink: {payload.get('sink') or 'none'}",
        f"Operator: {payload.get('operator') or 'none'}",
        f"Boundary state: {payload.get('boundary_state') or 'none'}",
        f"Acknowledgement required: {payload.get('acknowledgement_required', True)}",
        f"Acknowledgement ok: {payload.get('acknowledgement_ok', False)}",
        f"Command copy text: {payload.get('command_copy_text') or 'none'}",
        f"Creates selected target: {payload.get('creates_selected_live_target', False)}",
        f"Observed: writes={payload.get('writes_attempted', 0)} network={payload.get('network_calls_made', 0)}",
    ]
    blockers = payload.get("blocked_reasons") or []
    rows = blockers if isinstance(blockers, list) else []
    lines.append(f"Blocked reasons: {len(rows)}")
    for reason in rows:
        lines.append(f" - {reason}")
    stop_conditions = payload.get("explicit_stop_conditions") or []
    stops = stop_conditions if isinstance(stop_conditions, list) else []
    lines.append(f"Stop conditions: {len(stops)}")
    for condition in stops:
        lines.append(f" - {condition}")
    return "\n".join(lines) + "\n"


def _render_runtime_readiness_text(payload: dict[str, object]) -> str:
    checks = payload.get("checks") or []
    blocked = payload.get("blocked_checks") or []
    warnings = payload.get("warning_checks") or []
    safe_actions = payload.get("safe_next_actions") or []
    stop_conditions = payload.get("explicit_stop_conditions") or []
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


def _render_service_recovery_text(payload: dict[str, object]) -> str:
    commands = dict(payload.get("commands") or {})
    latest_drill = dict(payload.get("latest_review_routing_drill") or {})
    checklist_rollup = dict(payload.get("live_pilot_checklist_rollup") or {})
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
        "Latest review routing drill: "
        f"{latest_drill.get('state') or 'not_run'} "
        f"run={latest_drill.get('run_id') or 'none'} "
        f"readback={latest_drill.get('agent_readback_state') or 'none'}",
        "Live pilot checklist: "
        f"jobs={checklist_rollup.get('checklist_job_count', 0)} "
        f"steps={checklist_rollup.get('step_count', 0)} "
        f"live_calls={checklist_rollup.get('live_call_count', 0)} "
        f"sink_writes={checklist_rollup.get('sink_write_step_count', 0)}",
        f"Install: {commands.get('install')}",
        f"Start: {commands.get('start')}",
        f"Status: {commands.get('status')}",
        f"Review routing drill: {commands.get('review_routing_drill')}",
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


def _render_offline_pilot_gap_audit_text(payload: dict[str, object]) -> str:
    coverage = dict(payload.get("coverage") or {})
    commands = dict(payload.get("commands") or {})
    doc_checks = payload.get("doc_checks") or []
    drill_surfaces = payload.get("drill_surfaces") or []
    boundaries = payload.get("remaining_boundaries") or []
    stop_conditions = payload.get("explicit_stop_conditions") or []
    lines = [
        f"Offline pilot gap audit: {payload.get('state')}",
        "Coverage: "
        f"{coverage.get('covered_count', 0)}/{coverage.get('total_count', 0)} "
        f"missing_docs={coverage.get('missing_doc_count', 0)}",
        f"Recommended next slice: {payload.get('recommended_next_slice')}",
        f"Audit path: {payload.get('audit_path') or 'not written'}",
        "Observed: "
        f"writes={payload.get('writes_attempted', 0)} "
        f"network={payload.get('network_calls_made', 0)}",
    ]
    doc_rows = doc_checks if isinstance(doc_checks, list) else []
    lines.append(f"Docs: {len(doc_rows)}")
    for row in doc_rows:
        if isinstance(row, dict):
            lines.append(f" - {row.get('name')}: exists={row.get('exists')} path={row.get('path')}")
    drill_rows = drill_surfaces if isinstance(drill_surfaces, list) else []
    lines.append(f"Drills: {len(drill_rows)}")
    for row in drill_rows:
        if isinstance(row, dict):
            lines.append(f" - {row.get('name')}: {row.get('cli')}")
    boundary_rows = boundaries if isinstance(boundaries, list) else []
    lines.append(f"Remaining boundaries: {len(boundary_rows)}")
    for row in boundary_rows:
        if isinstance(row, dict):
            lines.append(f" - {row.get('boundary')}: {row.get('state')} - {row.get('reason')}")
    for label, key in [
        ("Operator dashboard", "operator_dashboard"),
        ("Runtime readiness", "runtime_readiness"),
        ("Live pilot rehearsal drill", "live_pilot_rehearsal_drill"),
        ("Child replacement readiness drill", "child_replacement_readiness_drill"),
    ]:
        command = commands.get(key)
        if command:
            lines.append(f"{label}: {command}")
    stop_rows = stop_conditions if isinstance(stop_conditions, list) else []
    lines.append(f"Stop conditions: {len(stop_rows)}")
    for condition in stop_rows:
        lines.append(f" - {condition}")
    return "\n".join(lines) + "\n"


def _render_operator_selected_live_smoke_preflight_text(payload: dict[str, object]) -> str:
    commands = dict(payload.get("commands") or {})
    blockers = payload.get("blocked_reasons") or []
    ready_entries = payload.get("ready_entries") or []
    checklist = payload.get("operator_selection_checklist") or []
    lines = [
        f"Operator-selected live smoke preflight: {payload.get('state')}",
        f"Recommended next step: {payload.get('recommended_next_step')}",
        f"Run: {payload.get('run_id') or 'none'}",
        f"Sink: {payload.get('sink') or 'all'}",
        f"Candidates: {payload.get('candidate_count', 0)} ready={payload.get('ready_candidate_count', 0)} blocked={payload.get('blocked_candidate_count', 0)}",
        f"Entries: {payload.get('entry_count', 0)} ready={payload.get('ready_entry_count', 0)} active={payload.get('active_selected_target_count', 0)}",
        f"Preflight path: {payload.get('preflight_path') or 'not written'}",
        f"Observed: writes={payload.get('writes_attempted', 0)} network={payload.get('network_calls_made', 0)}",
    ]
    blocker_rows = blockers if isinstance(blockers, list) else []
    lines.append(f"Blocked reasons: {len(blocker_rows)}")
    for reason in blocker_rows:
        lines.append(f" - {reason}")
    entry_rows = ready_entries if isinstance(ready_entries, list) else []
    lines.append(f"Ready entries: {len(entry_rows)}")
    for entry in entry_rows:
        if isinstance(entry, dict):
            lines.append(
                " - "
                f"{entry.get('run_id')}/{entry.get('job_id')} "
                f"sink={entry.get('sink')} "
                f"missing={','.join(str(item) for item in entry.get('missing_operator_fields') or []) or 'none'}"
            )
    checklist_rows = checklist if isinstance(checklist, list) else []
    lines.append(f"Checklist: {len(checklist_rows)}")
    for item in checklist_rows:
        if isinstance(item, dict):
            lines.append(f" - {item.get('step')}: {item.get('command')}")
    for label, key in [
        ("Preflight", "operator_selected_live_smoke_preflight"),
        ("Offline gap audit", "offline_pilot_gap_audit"),
        ("Live readiness audit", "live_readiness_audit"),
        ("Selection requirements", "live_selection_requirements"),
        ("Validate response", "validate_operator_response"),
    ]:
        command = commands.get(key)
        if command:
            lines.append(f"{label}: {command}")
    return "\n".join(lines) + "\n"


def _render_operator_live_pilot_readiness_packet_text(payload: dict[str, object]) -> str:
    checks = payload.get("checks") or []
    blocked_reasons = payload.get("blocked_reasons") or []
    commands = dict(payload.get("commands") or {})
    rehearsal = dict(payload.get("synthetic_rehearsal_contract") or {})
    lines = [
        f"Operator live pilot readiness packet: {payload.get('state')}",
        f"Recommended next step: {payload.get('recommended_next_step')}",
        f"Run: {payload.get('run_id')}",
        f"Sink: {payload.get('sink') or 'all'}",
        f"Entries: ready={payload.get('ready_entry_count', 0)} active={payload.get('active_selected_target_count', 0)}",
        f"Packet path: {payload.get('packet_path') or 'not written'}",
        f"Observed: writes={payload.get('writes_attempted', 0)} network={payload.get('network_calls_made', 0)}",
        f"Synthetic rehearsal: {rehearsal.get('command')}",
    ]
    check_rows = checks if isinstance(checks, list) else []
    lines.append(f"Checks: {len(check_rows)}")
    for check in check_rows:
        if isinstance(check, dict):
            evidence = check.get("evidence")
            if isinstance(evidence, dict):
                evidence_text = ", ".join(f"{key}={value}" for key, value in sorted(evidence.items()))
            else:
                evidence_text = str(evidence)
            lines.append(f" - {check.get('name')}: {check.get('ok')} evidence={evidence_text}")
    blocker_rows = blocked_reasons if isinstance(blocked_reasons, list) else []
    lines.append(f"Blocked reasons: {len(blocker_rows)}")
    for reason in blocker_rows:
        lines.append(f" - {reason}")
    for label, key in [
        ("Operator dashboard", "operator_dashboard"),
        ("Operator preflight", "operator_selected_live_smoke_preflight"),
        ("Rehearsal drill", "live_pilot_rehearsal_drill"),
        ("Validate response", "validate_operator_response_prefilled"),
        ("Selected target approval boundary", "selected_target_approval_boundary"),
        ("Selected target command copy packet", "selected_target_command_copy_packet"),
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
    checklist = payload.get("pilot_command_checklist") or []
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
    checklist_rows = checklist if isinstance(checklist, list) else []
    lines.append(f"Pilot checklist: {len(checklist_rows)}")
    for row in checklist_rows:
        if not isinstance(row, dict):
            continue
        lines.append(
            f" - {row.get('step')}: live={row.get('live_call', False)} "
            f"writes_sink={row.get('writes_sink', False)} command={row.get('command')}"
        )
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


def _render_child_review_queue_text(entries: list[dict[str, object]]) -> str:
    lines = [f"Child review queue: {len(entries)} candidates"]
    if not entries:
        return "\n".join(lines) + "\n"
    for entry in entries:
        next_action = dict(entry.get("next_action") or {})
        lines.append(
            " - "
            f"{entry.get('candidate_id')} "
            f"job={entry.get('job_id')} "
            f"state={entry.get('state')} "
            f"next={next_action.get('action') or 'none'}"
        )
    return "\n".join(lines) + "\n"


def _render_side_pair_review_queue_text(entries: list[dict[str, object]]) -> str:
    lines = [f"Side pair review queue: {len(entries)} proposals"]
    if not entries:
        return "\n".join(lines) + "\n"
    for entry in entries:
        next_action = dict(entry.get("next_action") or {})
        proposal = dict(entry.get("proposal") or {})
        lines.append(
            " - "
            f"{entry.get('proposal_id')} "
            f"state={entry.get('state')} "
            f"front={proposal.get('front_job_id')} "
            f"back={proposal.get('back_job_id')} "
            f"next={next_action.get('action') or 'none'}"
        )
    return "\n".join(lines) + "\n"


def _render_child_route_prep_queue_text(entries: list[dict[str, object]]) -> str:
    lines = [f"Child route prep queue: {len(entries)} candidates"]
    if not entries:
        return "\n".join(lines) + "\n"
    for entry in entries:
        next_action = dict(entry.get("next_action") or {})
        lines.append(
            " - "
            f"{entry.get('candidate_id')} "
            f"job={entry.get('job_id')} "
            f"state={entry.get('state')} "
            f"next={next_action.get('action') or 'none'}"
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

    offline_pilot_gap_audit = sub.add_parser("offline-pilot-gap-audit")
    offline_pilot_gap_audit.add_argument("--no-write", action="store_true")
    offline_pilot_gap_audit.add_argument("--json", action="store_true")

    operator_selected_live_smoke_preflight = sub.add_parser("operator-selected-live-smoke-preflight")
    operator_selected_live_smoke_preflight.add_argument("--run-id", default=None)
    operator_selected_live_smoke_preflight.add_argument("--sink", choices=["google_contacts", "odoo"], default=None)
    operator_selected_live_smoke_preflight.add_argument("--no-write", action="store_true")
    operator_selected_live_smoke_preflight.add_argument("--json", action="store_true")
    add_operator_live_pilot_readiness_parser(sub)

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
    add_pilot_readiness_runs_parser(runs_sub)
    runs_dry_run_closeout = runs_sub.add_parser("dry-run-closeout")
    runs_dry_run_closeout.add_argument("run_id")
    runs_dry_run_closeout.add_argument("--no-write", action="store_true")
    runs_dry_run_closeout.add_argument("--json", action="store_true")
    runs_dry_run_review_handoff = runs_sub.add_parser("dry-run-review-handoff")
    runs_dry_run_review_handoff.add_argument("run_id")
    runs_dry_run_review_handoff.add_argument("--no-write", action="store_true")
    runs_dry_run_review_handoff.add_argument("--json", action="store_true")
    runs_dry_run_safe_loop = runs_sub.add_parser("dry-run-safe-loop")
    runs_dry_run_safe_loop.add_argument("run_id")
    runs_dry_run_safe_loop.add_argument("--limit", type=int, default=5)
    runs_dry_run_safe_loop.add_argument("--no-write", action="store_true")
    runs_dry_run_safe_loop.add_argument("--json", action="store_true")
    add_review_route_runs_parsers(runs_sub)
    runs_close_lookup_prerequisites = runs_sub.add_parser("close-lookup-prerequisites")
    runs_close_lookup_prerequisites.add_argument("run_id")
    runs_close_lookup_prerequisites.add_argument("--operator", required=True)
    runs_close_lookup_prerequisites.add_argument("--sink", choices=["google_contacts", "odoo"], default=None)
    runs_close_lookup_prerequisites.add_argument("--limit", type=int, default=5)
    runs_close_lookup_prerequisites.add_argument("--no-write", action="store_true")
    runs_close_lookup_prerequisites.add_argument("--json", action="store_true")
    runs_live_pilot_status = runs_sub.add_parser("live-pilot-status")
    runs_live_pilot_status.add_argument("run_id")
    runs_live_pilot_status.add_argument("--no-write", action="store_true")
    runs_live_pilot_status.add_argument("--json", action="store_true")
    runs_live_pilot_handoff = runs_sub.add_parser("live-pilot-handoff")
    runs_live_pilot_handoff.add_argument("run_id")
    runs_live_pilot_handoff.add_argument("--no-write", action="store_true")
    runs_live_pilot_handoff.add_argument("--json", action="store_true")
    runs_live_pilot_approval_packet = runs_sub.add_parser("live-pilot-approval-packet")
    runs_live_pilot_approval_packet.add_argument("run_id")
    runs_live_pilot_approval_packet.add_argument("--job-id", default=None)
    runs_live_pilot_approval_packet.add_argument("--json", action="store_true")
    add_selected_target_runs_parsers(runs_sub)
    runs_selected_live_target_preflight = runs_sub.add_parser("selected-live-target-preflight")
    runs_selected_live_target_preflight.add_argument("run_id")
    runs_selected_live_target_preflight.add_argument("--response", required=True)
    runs_selected_live_target_preflight.add_argument("--json", action="store_true")
    runs_selected_live_target_preview = runs_sub.add_parser("selected-live-target-preview")
    runs_selected_live_target_preview.add_argument("run_id")
    runs_selected_live_target_preview.add_argument("--response", required=True)
    runs_selected_live_target_preview.add_argument("--json", action="store_true")
    runs_selected_live_target_from_response = runs_sub.add_parser("selected-live-target-from-response")
    runs_selected_live_target_from_response.add_argument("run_id")
    runs_selected_live_target_from_response.add_argument("--response", required=True)
    runs_selected_live_target_from_response.add_argument("--write-selected-target", action="store_true")
    runs_selected_live_target_from_response.add_argument("--reason", default="")
    runs_selected_live_target_from_response.add_argument("--json", action="store_true")
    runs_selected_live_target_handoff_from_response = runs_sub.add_parser(
        "selected-live-target-handoff-from-response"
    )
    runs_selected_live_target_handoff_from_response.add_argument("run_id")
    runs_selected_live_target_handoff_from_response.add_argument("--response", required=True)
    runs_selected_live_target_handoff_from_response.add_argument("--write-audit", action="store_true")
    runs_selected_live_target_handoff_from_response.add_argument("--json", action="store_true")
    runs_lookup_smoke_handoff_from_response = runs_sub.add_parser("lookup-smoke-handoff-from-response")
    runs_lookup_smoke_handoff_from_response.add_argument("run_id")
    runs_lookup_smoke_handoff_from_response.add_argument("--response", required=True)
    runs_lookup_smoke_handoff_from_response.add_argument("--write-handoff", action="store_true")
    runs_lookup_smoke_handoff_from_response.add_argument("--json", action="store_true")
    runs_selected_lookup_smoke_execution_packet_from_response = runs_sub.add_parser(
        "selected-lookup-smoke-execution-packet-from-response"
    )
    runs_selected_lookup_smoke_execution_packet_from_response.add_argument("run_id")
    runs_selected_lookup_smoke_execution_packet_from_response.add_argument("--response", required=True)
    runs_selected_lookup_smoke_execution_packet_from_response.add_argument(
        "--execute-selected-lookup-smoke",
        action="store_true",
    )
    runs_selected_lookup_smoke_execution_packet_from_response.add_argument("--json", action="store_true")
    runs_selected_write_pilot_execution_packet_from_response = runs_sub.add_parser(
        "selected-write-pilot-execution-packet-from-response"
    )
    runs_selected_write_pilot_execution_packet_from_response.add_argument("run_id")
    runs_selected_write_pilot_execution_packet_from_response.add_argument("--response", required=True)
    runs_selected_write_pilot_execution_packet_from_response.add_argument(
        "--execute-write-pilot",
        action="store_true",
    )
    runs_selected_write_pilot_execution_packet_from_response.add_argument("--json", action="store_true")
    runs_selected_readback_pilot_execution_packet_from_response = runs_sub.add_parser(
        "selected-readback-pilot-execution-packet-from-response"
    )
    runs_selected_readback_pilot_execution_packet_from_response.add_argument("run_id")
    runs_selected_readback_pilot_execution_packet_from_response.add_argument("--response", required=True)
    runs_selected_readback_pilot_execution_packet_from_response.add_argument(
        "--execute-readback-pilot",
        action="store_true",
    )
    runs_selected_readback_pilot_execution_packet_from_response.add_argument("--json", action="store_true")
    runs_live_pilot_closeout_packet_from_response = runs_sub.add_parser(
        "live-pilot-closeout-packet-from-response"
    )
    runs_live_pilot_closeout_packet_from_response.add_argument("run_id")
    runs_live_pilot_closeout_packet_from_response.add_argument("--response", required=True)
    runs_live_pilot_closeout_packet_from_response.add_argument("--write-closeout", action="store_true")
    runs_live_pilot_closeout_packet_from_response.add_argument("--json", action="store_true")
    runs_live_pilot_operator_workflow_packet_from_response = runs_sub.add_parser(
        "live-pilot-operator-workflow-packet-from-response"
    )
    runs_live_pilot_operator_workflow_packet_from_response.add_argument("run_id")
    runs_live_pilot_operator_workflow_packet_from_response.add_argument("--response", required=True)
    runs_live_pilot_operator_workflow_packet_from_response.add_argument("--json", action="store_true")
    runs_live_pilot_operator_rehearsal_from_response = runs_sub.add_parser(
        "live-pilot-operator-rehearsal-from-response"
    )
    runs_live_pilot_operator_rehearsal_from_response.add_argument("run_id")
    runs_live_pilot_operator_rehearsal_from_response.add_argument("--response", required=True)
    runs_live_pilot_operator_rehearsal_from_response.add_argument("--json", action="store_true")
    runs_live_pilot_readiness_export_from_response = runs_sub.add_parser(
        "live-pilot-readiness-export-from-response"
    )
    runs_live_pilot_readiness_export_from_response.add_argument("run_id")
    runs_live_pilot_readiness_export_from_response.add_argument("--response", required=True)
    runs_live_pilot_readiness_export_from_response.add_argument("--no-write", action="store_true")
    runs_live_pilot_readiness_export_from_response.add_argument("--json", action="store_true")
    runs_live_pilot_execution_checklist_from_response = runs_sub.add_parser(
        "live-pilot-execution-checklist-from-response"
    )
    runs_live_pilot_execution_checklist_from_response.add_argument("run_id")
    runs_live_pilot_execution_checklist_from_response.add_argument("--response", required=True)
    runs_live_pilot_execution_checklist_from_response.add_argument("--json", action="store_true")
    runs_live_pilot_command_copy_packet_from_response = runs_sub.add_parser(
        "live-pilot-command-copy-packet-from-response"
    )
    runs_live_pilot_command_copy_packet_from_response.add_argument("run_id")
    runs_live_pilot_command_copy_packet_from_response.add_argument("--response", required=True)
    runs_live_pilot_command_copy_packet_from_response.add_argument("--acknowledgement", default="")
    runs_live_pilot_command_copy_packet_from_response.add_argument("--json", action="store_true")
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
    reviews_children = reviews_sub.add_parser("children")
    reviews_children.add_argument("--run-id", default=None)
    reviews_children.add_argument("--state", default="needs_review")
    reviews_children.add_argument("--json", action="store_true")
    reviews_side_pairs = reviews_sub.add_parser("side-pairs")
    reviews_side_pairs.add_argument("--run-id", default=None)
    reviews_side_pairs.add_argument("--state", default="proposed")
    reviews_side_pairs.add_argument("--json", action="store_true")
    reviews_side_pair_review = reviews_sub.add_parser("side-pair-review")
    reviews_side_pair_review.add_argument("proposal_id")
    reviews_side_pair_review.add_argument("--run-id", required=True)
    reviews_side_pair_review.add_argument("--reviewer", default="operator")
    reviews_side_pair_review.add_argument(
        "--action",
        choices=["approve_side_pair_merge", "keep_needs_review", "reject_side_pair"],
        default="keep_needs_review",
    )
    reviews_side_pair_review.add_argument("--field-corrections-json", default="{}")
    reviews_side_pair_review.add_argument("--notes", default="")
    reviews_side_pair_review.add_argument("--json", action="store_true")
    reviews_child_review = reviews_sub.add_parser("child-review")
    reviews_child_review.add_argument("candidate_id")
    reviews_child_review.add_argument("--run-id", required=True)
    reviews_child_review.add_argument("--reviewer", default="operator")
    reviews_child_review.add_argument(
        "--action",
        choices=["approve_child_for_routing", "keep_needs_review", "reject_child_contact"],
        default="keep_needs_review",
    )
    reviews_child_review.add_argument("--field-corrections-json", default="{}")
    reviews_child_review.add_argument("--notes", default="")
    reviews_child_review.add_argument("--json", action="store_true")
    reviews_child_route_prep_queue = reviews_sub.add_parser("child-route-prep-queue")
    reviews_child_route_prep_queue.add_argument("--run-id", default=None)
    reviews_child_route_prep_queue.add_argument("--state", default="approved_for_dedupe")
    reviews_child_route_prep_queue.add_argument("--json", action="store_true")
    reviews_child_route_prep = reviews_sub.add_parser("child-route-prep")
    reviews_child_route_prep.add_argument("candidate_id")
    reviews_child_route_prep.add_argument("--run-id", required=True)
    reviews_child_route_prep.add_argument("--live", action="store_true")
    reviews_child_route_prep.add_argument("--json", action="store_true")
    reviews_child_lookup_result = reviews_sub.add_parser("child-lookup-result")
    reviews_child_lookup_result.add_argument("candidate_id")
    reviews_child_lookup_result.add_argument("--run-id", required=True)
    reviews_child_lookup_result.add_argument("--matches-by-sink-json", default="{}")
    reviews_child_lookup_result.add_argument("--json", action="store_true")
    reviews_child_assess_duplicates = reviews_sub.add_parser("child-assess-duplicates")
    reviews_child_assess_duplicates.add_argument("candidate_id")
    reviews_child_assess_duplicates.add_argument("--run-id", required=True)
    reviews_child_assess_duplicates.add_argument("--json", action="store_true")
    reviews_child_resolve_duplicate = reviews_sub.add_parser("child-resolve-duplicate")
    reviews_child_resolve_duplicate.add_argument("candidate_id")
    reviews_child_resolve_duplicate.add_argument("--run-id", required=True)
    reviews_child_resolve_duplicate.add_argument("--reviewer", default="operator")
    reviews_child_resolve_duplicate.add_argument(
        "--decision",
        choices=["create_new", "merge_existing", "noop"],
        required=True,
    )
    reviews_child_resolve_duplicate.add_argument("--target-identity", default="")
    reviews_child_resolve_duplicate.add_argument("--reason", default="")
    reviews_child_resolve_duplicate.add_argument("--json", action="store_true")
    reviews_child_sink_plan_gate = reviews_sub.add_parser("child-sink-plan-gate")
    reviews_child_sink_plan_gate.add_argument("candidate_id")
    reviews_child_sink_plan_gate.add_argument("--run-id", required=True)
    reviews_child_sink_plan_gate.add_argument("--json", action="store_true")
    reviews_child_sink_apply_preflight = reviews_sub.add_parser("child-sink-apply-preflight")
    reviews_child_sink_apply_preflight.add_argument("candidate_id")
    reviews_child_sink_apply_preflight.add_argument("--run-id", required=True)
    reviews_child_sink_apply_preflight.add_argument("--apply", action="store_true")
    reviews_child_sink_apply_preflight.add_argument("--json", action="store_true")
    reviews_child_selected_target_handoff = reviews_sub.add_parser("child-selected-target-handoff")
    reviews_child_selected_target_handoff.add_argument("candidate_id")
    reviews_child_selected_target_handoff.add_argument("--run-id", required=True)
    reviews_child_selected_target_handoff.add_argument("--sink", required=True)
    reviews_child_selected_target_handoff.add_argument("--operator", default="operator")
    reviews_child_selected_target_handoff.add_argument("--scope", default="write")
    reviews_child_selected_target_handoff.add_argument("--reason", default="")
    reviews_child_selected_target_handoff.add_argument("--json", action="store_true")
    reviews_child_validate_selected_target_response = reviews_sub.add_parser(
        "child-validate-selected-target-response"
    )
    reviews_child_validate_selected_target_response.add_argument("candidate_id")
    reviews_child_validate_selected_target_response.add_argument("--run-id", required=True)
    reviews_child_validate_selected_target_response.add_argument("--response", required=True)
    reviews_child_validate_selected_target_response.add_argument("--json", action="store_true")
    reviews_child_selected_target_execution_checklist = reviews_sub.add_parser(
        "child-selected-target-execution-checklist"
    )
    reviews_child_selected_target_execution_checklist.add_argument("candidate_id")
    reviews_child_selected_target_execution_checklist.add_argument("--run-id", required=True)
    reviews_child_selected_target_execution_checklist.add_argument("--response", required=True)
    reviews_child_selected_target_execution_checklist.add_argument("--json", action="store_true")
    reviews_child_selected_target_command_copy_packet = reviews_sub.add_parser(
        "child-selected-target-command-copy-packet"
    )
    reviews_child_selected_target_command_copy_packet.add_argument("candidate_id")
    reviews_child_selected_target_command_copy_packet.add_argument("--run-id", required=True)
    reviews_child_selected_target_command_copy_packet.add_argument("--response", required=True)
    reviews_child_selected_target_command_copy_packet.add_argument("--acknowledgement", default="")
    reviews_child_selected_target_command_copy_packet.add_argument("--json", action="store_true")
    reviews_child_selected_target_audit = reviews_sub.add_parser("child-selected-target-audit")
    reviews_child_selected_target_audit.add_argument("candidate_id")
    reviews_child_selected_target_audit.add_argument("--run-id", required=True)
    reviews_child_selected_target_audit.add_argument("--sink", default=None)
    reviews_child_selected_target_audit.add_argument("--operator", default=None)
    reviews_child_selected_target_audit.add_argument("--scope", default=None)
    reviews_child_selected_target_audit.add_argument("--no-write", action="store_true")
    reviews_child_selected_target_audit.add_argument("--json", action="store_true")
    reviews_child_abandon_selected_target = reviews_sub.add_parser("child-abandon-selected-target")
    reviews_child_abandon_selected_target.add_argument("candidate_id")
    reviews_child_abandon_selected_target.add_argument("--run-id", required=True)
    reviews_child_abandon_selected_target.add_argument("--operator", required=True)
    reviews_child_abandon_selected_target.add_argument("--reason", required=True)
    reviews_child_abandon_selected_target.add_argument("--json", action="store_true")
    reviews_child_selected_target_replacement_reset = reviews_sub.add_parser(
        "child-selected-target-replacement-reset"
    )
    reviews_child_selected_target_replacement_reset.add_argument("candidate_id")
    reviews_child_selected_target_replacement_reset.add_argument("--run-id", required=True)
    reviews_child_selected_target_replacement_reset.add_argument("--sink", required=True)
    reviews_child_selected_target_replacement_reset.add_argument("--operator", required=True)
    reviews_child_selected_target_replacement_reset.add_argument("--scope", default="write")
    reviews_child_selected_target_replacement_reset.add_argument("--reset-by", default="operator")
    reviews_child_selected_target_replacement_reset.add_argument("--reason", default="")
    reviews_child_selected_target_replacement_reset.add_argument("--json", action="store_true")
    reviews_child_replacement_handoff_refresh = reviews_sub.add_parser("child-replacement-handoff-refresh")
    reviews_child_replacement_handoff_refresh.add_argument("candidate_id")
    reviews_child_replacement_handoff_refresh.add_argument("--run-id", required=True)
    reviews_child_replacement_handoff_refresh.add_argument("--sink", required=True)
    reviews_child_replacement_handoff_refresh.add_argument("--operator", required=True)
    reviews_child_replacement_handoff_refresh.add_argument("--scope", default="write")
    reviews_child_replacement_handoff_refresh.add_argument("--reason", default="")
    reviews_child_replacement_handoff_refresh.add_argument("--json", action="store_true")
    reviews_child_validate_replacement_response = reviews_sub.add_parser("child-validate-replacement-response")
    reviews_child_validate_replacement_response.add_argument("candidate_id")
    reviews_child_validate_replacement_response.add_argument("--run-id", required=True)
    reviews_child_validate_replacement_response.add_argument("--response", required=True)
    reviews_child_validate_replacement_response.add_argument("--json", action="store_true")
    reviews_child_replacement_execution_checklist = reviews_sub.add_parser(
        "child-replacement-execution-checklist"
    )
    reviews_child_replacement_execution_checklist.add_argument("candidate_id")
    reviews_child_replacement_execution_checklist.add_argument("--run-id", required=True)
    reviews_child_replacement_execution_checklist.add_argument("--response", required=True)
    reviews_child_replacement_execution_checklist.add_argument("--json", action="store_true")
    reviews_child_replacement_command_copy_packet = reviews_sub.add_parser(
        "child-replacement-command-copy-packet"
    )
    reviews_child_replacement_command_copy_packet.add_argument("candidate_id")
    reviews_child_replacement_command_copy_packet.add_argument("--run-id", required=True)
    reviews_child_replacement_command_copy_packet.add_argument("--response", required=True)
    reviews_child_replacement_command_copy_packet.add_argument("--acknowledgement", default="")
    reviews_child_replacement_command_copy_packet.add_argument("--json", action="store_true")
    reviews_child_replacement_closeout_status = reviews_sub.add_parser(
        "child-replacement-closeout-status"
    )
    reviews_child_replacement_closeout_status.add_argument("candidate_id")
    reviews_child_replacement_closeout_status.add_argument("--run-id", required=True)
    reviews_child_replacement_closeout_status.add_argument("--json", action="store_true")
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

    contacts = sub.add_parser("contacts")
    contacts_sub = contacts.add_subparsers(dest="contacts_command", required=True)
    contacts_status = contacts_sub.add_parser("status")
    contacts_status.add_argument("--json", action="store_true")
    contacts_init = contacts_sub.add_parser("init")
    contacts_init.add_argument("--json", action="store_true")
    contacts_list = contacts_sub.add_parser("list")
    contacts_list.add_argument("--limit", type=int, default=100)
    contacts_list.add_argument("--json", action="store_true")
    contacts_show = contacts_sub.add_parser("show")
    contacts_show.add_argument("contact_id")
    contacts_show.add_argument("--json", action="store_true")
    contacts_review_surface = contacts_sub.add_parser("review-surface")
    contacts_review_surface.add_argument("--contact-id", default=None)
    contacts_review_surface.add_argument("--limit", type=int, default=100)
    contacts_review_surface.add_argument("--json", action="store_true")
    contacts_field_correct = contacts_sub.add_parser("field-correct")
    contacts_field_correct.add_argument("contact_id")
    contacts_field_correct.add_argument("--operator", default="operator")
    contacts_field_correct.add_argument("--field-corrections-json", required=True)
    contacts_field_correct.add_argument("--reason", default="")
    contacts_field_correct.add_argument("--json", action="store_true")
    contacts_crop_decision = contacts_sub.add_parser("crop-decision")
    contacts_crop_decision.add_argument("contact_id")
    contacts_crop_decision.add_argument("--operator", default="operator")
    contacts_crop_decision.add_argument("--asset-id", required=True)
    contacts_crop_decision.add_argument("--decision", choices=["accept", "reject", "needs_recrop", "use_alternate"], required=True)
    contacts_crop_decision.add_argument("--reason", default="")
    contacts_crop_decision.add_argument("--selected-crop-path", default="")
    contacts_crop_decision.add_argument("--selected-crop-sha256", default="")
    contacts_crop_decision.add_argument("--json", action="store_true")
    contacts_enrichment_merge = contacts_sub.add_parser("enrichment-merge")
    contacts_enrichment_merge.add_argument("contact_id")
    contacts_enrichment_merge.add_argument("--operator", default="operator")
    contacts_enrichment_merge.add_argument("--attempt-id", required=True)
    contacts_enrichment_merge.add_argument("--approved-fields-json", required=True)
    contacts_enrichment_merge.add_argument("--reason", default="")
    contacts_enrichment_merge.add_argument("--json", action="store_true")
    contacts_sink_approval = contacts_sub.add_parser("sink-approval")
    contacts_sink_approval.add_argument("contact_id")
    contacts_sink_approval.add_argument("--operator", default="operator")
    contacts_sink_approval.add_argument("--attempt-id", required=True)
    contacts_sink_approval.add_argument(
        "--approval-state",
        choices=["approved_for_lookup", "approved_for_write_pilot", "rejected", "needs_review"],
        required=True,
    )
    contacts_sink_approval.add_argument("--scope", choices=["lookup", "write", "readback", "all"], default="lookup")
    contacts_sink_approval.add_argument("--reason", default="")
    contacts_sink_approval.add_argument("--json", action="store_true")
    contacts_route_override = contacts_sub.add_parser("route-override")
    contacts_route_override.add_argument("contact_id")
    contacts_route_override.add_argument("--operator", default="operator")
    contacts_route_override.add_argument("--selected-sinks-json", required=True)
    contacts_route_override.add_argument("--selected-sink-state", default="dry_run")
    contacts_route_override.add_argument("--selected-target-profile", default="")
    contacts_route_override.add_argument("--selected-target-tenant", default="")
    contacts_route_override.add_argument("--route-candidate-state", default="operator_overridden")
    contacts_route_override.add_argument("--decision-id", default="")
    contacts_route_override.add_argument("--reason", default="")
    contacts_route_override.add_argument("--json", action="store_true")
    contacts_review_recommend = contacts_sub.add_parser("review-recommend")
    contacts_review_recommend.add_argument("contact_id")
    contacts_review_recommend.add_argument("--source", default="app_intelligence")
    contacts_review_recommend.add_argument("--category", required=True)
    contacts_review_recommend.add_argument("--recommendation", required=True)
    contacts_review_recommend.add_argument("--rationale", default="")
    contacts_review_recommend.add_argument("--confidence", type=float, default=None)
    contacts_review_recommend.add_argument("--evidence-json", default="{}")
    contacts_review_recommend.add_argument("--json", action="store_true")
    contacts_review_states = contacts_sub.add_parser("review-states")
    contacts_review_states.add_argument("--contact-id", default=None)
    contacts_review_states.add_argument("--state", default="all")
    contacts_review_states.add_argument("--limit", type=int, default=100)
    contacts_review_states.add_argument("--json", action="store_true")
    contacts_review_decide = contacts_sub.add_parser("review-decide")
    contacts_review_decide.add_argument("review_state_id")
    contacts_review_decide.add_argument("--reviewer", default="operator")
    contacts_review_decide.add_argument("--decision", choices=["accept", "reject"], required=True)
    contacts_review_decide.add_argument("--notes", default="")
    contacts_review_decide.add_argument("--json", action="store_true")
    contacts_review_safe_loop = contacts_sub.add_parser("review-safe-loop")
    contacts_review_safe_loop.add_argument("--limit", type=int, default=10)
    contacts_review_safe_loop.add_argument("--reviewer", default="safe-loop")
    contacts_review_safe_loop.add_argument("--apply", action="store_true")
    contacts_review_safe_loop.add_argument("--json", action="store_true")
    contacts_route_approval = contacts_sub.add_parser("route-selection-approval-boundary")
    contacts_route_approval.add_argument("contact_id")
    contacts_route_approval.add_argument("--operator", required=True)
    contacts_route_approval.add_argument("--sink", choices=["google_contacts", "odoo"], default=None)
    contacts_route_approval.add_argument("--response", default=None)
    contacts_route_approval.add_argument("--no-write", action="store_true")
    contacts_route_approval.add_argument("--json", action="store_true")
    contacts_route_command_copy = contacts_sub.add_parser("route-selection-command-copy-packet")
    contacts_route_command_copy.add_argument("contact_id")
    contacts_route_command_copy.add_argument("--operator", required=True)
    contacts_route_command_copy.add_argument("--response", required=True)
    contacts_route_command_copy.add_argument("--acknowledgement", default="")
    contacts_route_command_copy.add_argument("--sink", choices=["google_contacts", "odoo"], default=None)
    contacts_route_command_copy.add_argument("--json", action="store_true")
    contacts_project_run = contacts_sub.add_parser("project-run")
    contacts_project_run.add_argument("run_id")
    contacts_project_run.add_argument("--json", action="store_true")
    contacts_drift = contacts_sub.add_parser("drift")
    contacts_drift.add_argument("run_id")
    contacts_drift.add_argument("--json", action="store_true")

    drills = sub.add_parser("drills")
    drills_sub = drills.add_subparsers(dest="drills_command", required=True)
    drills_multi_card_preclassification = drills_sub.add_parser("multi-card-preclassification")
    drills_multi_card_preclassification.add_argument("--json", action="store_true")
    drills_watch_dry_run_selection = drills_sub.add_parser("watch-dry-run-selection")
    drills_watch_dry_run_selection.add_argument("--json", action="store_true")
    drills_watch_dry_run_execution = drills_sub.add_parser("watch-dry-run-execution")
    drills_watch_dry_run_execution.add_argument("--json", action="store_true")
    drills_review_routing = drills_sub.add_parser("review-routing")
    drills_review_routing.add_argument("--json", action="store_true")
    drills_live_pilot_rehearsal = drills_sub.add_parser("live-pilot-rehearsal")
    drills_live_pilot_rehearsal.add_argument("--json", action="store_true")
    drills_child_replacement_readiness = drills_sub.add_parser("child-replacement-readiness")
    drills_child_replacement_readiness.add_argument("--json", action="store_true")

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
    enrichment_check.add_argument("--provider", default="apollo")
    enrichment_check.add_argument("--json", action="store_true")
    enrichment_request = enrichment_sub.add_parser("request")
    enrichment_request.add_argument("job_id")
    enrichment_request.add_argument("--run-id", required=True)
    enrichment_request.add_argument("--mode", choices=["public_web", "api", "all"], default="public_web")
    enrichment_request.add_argument("--requested-by", default="operator")
    enrichment_request.add_argument("--allow-paid-enrichment", action="store_true")
    enrichment_request.add_argument("--provider", default="apollo")
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

    watch_backlog_preflight = sub.add_parser("watch-backlog-preflight")
    watch_backlog_preflight.add_argument("--no-write", action="store_true")
    watch_backlog_preflight.add_argument("--json", action="store_true")

    watch_practice_corpus_manifest = sub.add_parser("watch-practice-corpus-manifest")
    watch_practice_corpus_manifest.add_argument("--no-write", action="store_true")
    watch_practice_corpus_manifest.add_argument("--include-glob", action="append", default=[])
    watch_practice_corpus_manifest.add_argument("--json", action="store_true")

    watch_dry_run_selection_handoff = sub.add_parser("watch-dry-run-selection-handoff")
    watch_dry_run_selection_handoff.add_argument("--no-write", action="store_true")
    watch_dry_run_selection_handoff.add_argument("--json", action="store_true")

    watch_dry_run_validate_response = sub.add_parser("watch-dry-run-validate-response")
    watch_dry_run_validate_response.add_argument("--response", required=True)
    watch_dry_run_validate_response.add_argument("--json", action="store_true")

    watch_dry_run_command_copy_packet = sub.add_parser("watch-dry-run-command-copy-packet")
    watch_dry_run_command_copy_packet.add_argument("--response", required=True)
    watch_dry_run_command_copy_packet.add_argument("--acknowledgement", default="")
    watch_dry_run_command_copy_packet.add_argument("--json", action="store_true")

    watch_dry_run_readiness = sub.add_parser("watch-dry-run-readiness")
    watch_dry_run_readiness.add_argument("--no-write", action="store_true")
    watch_dry_run_readiness.add_argument("--json", action="store_true")

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

    if args.command == "offline-pilot-gap-audit":
        payload = service.offline_pilot_gap_audit(write=not args.no_write)
        print(json.dumps(payload, indent=2) if args.json else _render_offline_pilot_gap_audit_text(payload), end="")
        return 0 if payload["state"] != "needs_offline_attention" else 2

    if args.command == "operator-selected-live-smoke-preflight":
        payload = service.operator_selected_live_smoke_preflight(
            run_id=args.run_id,
            sink=args.sink,
            write=not args.no_write,
        )
        output = (
            json.dumps(payload, indent=2)
            if args.json
            else _render_operator_selected_live_smoke_preflight_text(payload)
        )
        print(output, end="")
        return 0 if payload["state"] != "needs_preparation" else 2

    if args.command == OPERATOR_LIVE_PILOT_READINESS_COMMAND:
        payload = call_registered_cli_command(service, args)
        output = (
            json.dumps(payload, indent=2)
            if args.json
            else _render_operator_live_pilot_readiness_packet_text(payload)
        )
        print(output, end="")
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
        elif args.runs_command == PILOT_READINESS_COMMAND:
            payload = call_registered_cli_command(service, args)
        elif args.runs_command == "dry-run-closeout":
            payload = service.dry_run_closeout(args.run_id, write=not args.no_write)
        elif args.runs_command == "dry-run-review-handoff":
            payload = service.dry_run_review_handoff(args.run_id, write=not args.no_write)
        elif args.runs_command == "dry-run-safe-loop":
            payload = service.dry_run_safe_loop(args.run_id, limit=args.limit, write=not args.no_write)
        elif args.runs_command in {
            REVIEW_ROUTE_READINESS_COMMAND,
            LOOKUP_SELECTION_PACKET_COMMAND,
        }:
            payload = call_registered_cli_command(service, args)
        elif args.runs_command == "close-lookup-prerequisites":
            payload = service.close_lookup_prerequisites(
                args.run_id,
                operator=args.operator,
                sink=args.sink,
                limit=args.limit,
                write=not args.no_write,
            )
        elif args.runs_command == "live-pilot-status":
            payload = service.live_pilot_status(run_id=args.run_id, write=not args.no_write)
        elif args.runs_command == "live-pilot-handoff":
            payload = service.live_pilot_handoff(run_id=args.run_id, write=not args.no_write)
        elif args.runs_command == "live-pilot-approval-packet":
            payload = service.live_pilot_approval_packet(run_id=args.run_id, job_id=args.job_id)
        elif args.runs_command in {
            SELECTED_TARGET_APPROVAL_BOUNDARY_COMMAND,
            SELECTED_TARGET_COMMAND_COPY_PACKET_COMMAND,
        }:
            payload = call_registered_cli_command(service, args)
        elif args.runs_command == "selected-live-target-preflight":
            payload = service.selected_live_target_preflight(run_id=args.run_id, response=args.response)
        elif args.runs_command == "selected-live-target-preview":
            payload = service.selected_live_target_artifact_preview(run_id=args.run_id, response=args.response)
        elif args.runs_command == "selected-live-target-from-response":
            payload = service.selected_live_target_from_response(
                run_id=args.run_id,
                response=args.response,
                write_selected_target=args.write_selected_target,
                reason=args.reason,
            )
        elif args.runs_command == "selected-live-target-handoff-from-response":
            payload = service.selected_live_target_handoff_from_response(
                run_id=args.run_id,
                response=args.response,
                write_audit=args.write_audit,
            )
        elif args.runs_command == "lookup-smoke-handoff-from-response":
            payload = service.lookup_smoke_handoff_from_response(
                run_id=args.run_id,
                response=args.response,
                write_handoff=args.write_handoff,
            )
        elif args.runs_command == "selected-lookup-smoke-execution-packet-from-response":
            payload = service.selected_lookup_smoke_execution_packet_from_response(
                run_id=args.run_id,
                response=args.response,
                execute_selected_lookup_smoke=args.execute_selected_lookup_smoke,
            )
        elif args.runs_command == "selected-write-pilot-execution-packet-from-response":
            payload = service.selected_write_pilot_execution_packet_from_response(
                run_id=args.run_id,
                response=args.response,
                execute_write_pilot=args.execute_write_pilot,
            )
        elif args.runs_command == "selected-readback-pilot-execution-packet-from-response":
            payload = service.selected_readback_pilot_execution_packet_from_response(
                run_id=args.run_id,
                response=args.response,
                execute_readback_pilot=args.execute_readback_pilot,
            )
        elif args.runs_command == "live-pilot-closeout-packet-from-response":
            payload = service.live_pilot_closeout_packet_from_response(
                run_id=args.run_id,
                response=args.response,
                write_closeout=args.write_closeout,
            )
        elif args.runs_command == "live-pilot-operator-workflow-packet-from-response":
            payload = service.live_pilot_operator_workflow_packet_from_response(
                run_id=args.run_id,
                response=args.response,
            )
        elif args.runs_command == "live-pilot-operator-rehearsal-from-response":
            payload = service.live_pilot_operator_rehearsal_from_response(
                run_id=args.run_id,
                response=args.response,
            )
        elif args.runs_command == "live-pilot-readiness-export-from-response":
            payload = service.live_pilot_readiness_export_from_response(
                run_id=args.run_id,
                response=args.response,
                write=not args.no_write,
            )
        elif args.runs_command == "live-pilot-execution-checklist-from-response":
            payload = service.live_pilot_execution_checklist_from_response(
                run_id=args.run_id,
                response=args.response,
            )
        elif args.runs_command == "live-pilot-command-copy-packet-from-response":
            payload = service.live_pilot_command_copy_packet_from_response(
                run_id=args.run_id,
                response=args.response,
                acknowledgement=args.acknowledgement,
            )
        elif args.runs_command == "live-pilot-validate-response":
            payload = service.validate_live_pilot_operator_response(run_id=args.run_id, response=args.response)
        else:
            payload = service.get_run(args.run_id)
        if args.runs_command == "live-pilot-command-copy-packet-from-response" and not args.json:
            print(_render_live_pilot_command_copy_packet_from_response_text(payload), end="")
            return 0
        if args.runs_command == "live-pilot-execution-checklist-from-response" and not args.json:
            print(_render_live_pilot_execution_checklist_from_response_text(payload), end="")
            return 0
        if args.runs_command == "live-pilot-readiness-export-from-response" and not args.json:
            print(_render_live_pilot_readiness_export_from_response_text(payload), end="")
            return 0
        if args.runs_command == "live-pilot-operator-rehearsal-from-response" and not args.json:
            print(_render_live_pilot_operator_rehearsal_from_response_text(payload), end="")
            return 0
        if args.runs_command == "live-pilot-operator-workflow-packet-from-response" and not args.json:
            print(_render_live_pilot_operator_workflow_packet_from_response_text(payload), end="")
            return 0
        if args.runs_command == "live-pilot-closeout-packet-from-response" and not args.json:
            print(_render_live_pilot_closeout_packet_from_response_text(payload), end="")
            return 0
        if args.runs_command == "selected-readback-pilot-execution-packet-from-response" and not args.json:
            print(_render_selected_readback_pilot_execution_packet_from_response_text(payload), end="")
            return 0
        if args.runs_command == "selected-write-pilot-execution-packet-from-response" and not args.json:
            print(_render_selected_write_pilot_execution_packet_from_response_text(payload), end="")
            return 0
        if args.runs_command == "selected-lookup-smoke-execution-packet-from-response" and not args.json:
            print(_render_selected_lookup_smoke_execution_packet_from_response_text(payload), end="")
            return 0
        if args.runs_command == "lookup-smoke-handoff-from-response" and not args.json:
            print(_render_lookup_smoke_handoff_from_response_text(payload), end="")
            return 0
        if args.runs_command == "selected-live-target-handoff-from-response" and not args.json:
            print(_render_selected_live_target_handoff_from_response_text(payload), end="")
            return 0
        if args.runs_command == "selected-live-target-from-response" and not args.json:
            print(_render_selected_live_target_from_response_text(payload), end="")
            return 0
        if args.runs_command == "selected-live-target-preview" and not args.json:
            print(_render_selected_live_target_artifact_preview_text(payload), end="")
            return 0
        if args.runs_command == "selected-live-target-preflight" and not args.json:
            print(_render_selected_live_target_preflight_text(payload), end="")
            return 0
        if args.runs_command == "live-pilot-approval-packet" and not args.json:
            print(_render_live_pilot_approval_packet_text(payload), end="")
            return 0
        if args.runs_command == SELECTED_TARGET_APPROVAL_BOUNDARY_COMMAND and not args.json:
            print(_render_selected_target_approval_boundary_text(payload), end="")
            return 0
        if args.runs_command == SELECTED_TARGET_COMMAND_COPY_PACKET_COMMAND and not args.json:
            print(_render_selected_target_command_copy_packet_text(payload), end="")
            return 0
        if args.runs_command == "live-pilot-validate-response" and not args.json:
            print(_render_live_pilot_operator_response_validation_text(payload), end="")
            return 0
        if args.runs_command == "live-pilot-handoff" and not args.json:
            print(_render_live_pilot_handoff_text(payload), end="")
            return 0
        if args.runs_command == "live-pilot-status" and not args.json:
            print(_render_live_pilot_status_text(payload), end="")
            return 0
        if args.runs_command == PILOT_READINESS_COMMAND and not args.json:
            print(render_pilot_readiness_report_text(payload), end="")
            return 0
        if args.runs_command == "dry-run-closeout" and not args.json:
            print(_render_dry_run_closeout_text(payload), end="")
            return 0
        if args.runs_command == "dry-run-review-handoff" and not args.json:
            print(_render_dry_run_review_handoff_text(payload), end="")
            return 0
        if args.runs_command == "dry-run-safe-loop" and not args.json:
            print(_render_dry_run_safe_loop_text(payload), end="")
            return 0
        if args.runs_command == REVIEW_ROUTE_READINESS_COMMAND and not args.json:
            print(render_review_route_readiness_text(payload), end="")
            return 0
        if args.runs_command == LOOKUP_SELECTION_PACKET_COMMAND and not args.json:
            print(render_lookup_selection_packet_text(payload), end="")
            return 0
        if args.runs_command == "close-lookup-prerequisites" and not args.json:
            print(_render_close_lookup_prerequisites_text(payload), end="")
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

    if args.command == "contacts":
        if args.contacts_command == "status":
            payload = service.contact_store_status()
        elif args.contacts_command == "init":
            payload = service.initialize_contact_store()
        elif args.contacts_command == "list":
            payload = service.list_contacts(limit=args.limit)
        elif args.contacts_command == "show":
            payload = service.get_contact(args.contact_id)
        elif args.contacts_command == "review-surface":
            payload = service.contact_review_surface(contact_id=args.contact_id, limit=args.limit)
        elif args.contacts_command == "field-correct":
            payload = service.apply_contact_field_corrections(
                contact_id=args.contact_id,
                operator=args.operator,
                field_corrections=json.loads(args.field_corrections_json),
                reason=args.reason,
            )
        elif args.contacts_command == "crop-decision":
            payload = service.decide_contact_crop(
                contact_id=args.contact_id,
                operator=args.operator,
                asset_id=args.asset_id,
                decision=args.decision,
                reason=args.reason,
                selected_crop_path=args.selected_crop_path,
                selected_crop_sha256=args.selected_crop_sha256,
            )
        elif args.contacts_command == "enrichment-merge":
            payload = service.apply_contact_enrichment_merge(
                contact_id=args.contact_id,
                operator=args.operator,
                attempt_id=args.attempt_id,
                approved_fields=list(json.loads(args.approved_fields_json)),
                reason=args.reason,
            )
        elif args.contacts_command == "sink-approval":
            payload = service.set_contact_sink_approval_state(
                contact_id=args.contact_id,
                operator=args.operator,
                attempt_id=args.attempt_id,
                approval_state=args.approval_state,
                scope=args.scope,
                reason=args.reason,
            )
        elif args.contacts_command == "route-override":
            payload = service.override_contact_route(
                contact_id=args.contact_id,
                operator=args.operator,
                selected_sinks=list(json.loads(args.selected_sinks_json)),
                selected_sink_state=args.selected_sink_state,
                selected_target_profile=args.selected_target_profile,
                selected_target_tenant=args.selected_target_tenant,
                route_candidate_state=args.route_candidate_state,
                decision_id=args.decision_id,
                reason=args.reason,
            )
        elif args.contacts_command == "review-recommend":
            payload = service.record_contact_review_recommendation(
                contact_id=args.contact_id,
                source=args.source,
                category=args.category,
                recommendation=args.recommendation,
                rationale=args.rationale,
                confidence=args.confidence,
                evidence=json.loads(args.evidence_json),
            )
        elif args.contacts_command == "review-states":
            payload = service.list_contact_review_states(
                contact_id=args.contact_id,
                state=args.state,
                limit=args.limit,
            )
        elif args.contacts_command == "review-decide":
            payload = service.decide_contact_review_state(
                review_state_id=args.review_state_id,
                reviewer=args.reviewer,
                decision=args.decision,
                notes=args.notes,
            )
        elif args.contacts_command == "review-safe-loop":
            payload = service.run_contact_review_safe_loop(
                limit=args.limit,
                reviewer=args.reviewer,
                apply=args.apply,
            )
        elif args.contacts_command == "route-selection-approval-boundary":
            payload = service.contact_route_selection_approval_boundary(
                args.contact_id,
                operator=args.operator,
                sink=args.sink,
                response=args.response,
                write=not args.no_write,
            )
        elif args.contacts_command == "route-selection-command-copy-packet":
            payload = service.contact_route_selection_command_copy_packet(
                args.contact_id,
                operator=args.operator,
                response=args.response,
                acknowledgement=args.acknowledgement,
                sink=args.sink,
            )
        elif args.contacts_command == "project-run":
            payload = service.project_contacts_from_run(args.run_id)
        else:
            payload = service.contact_projection_drift(args.run_id)
        if args.json:
            print(json.dumps(payload, indent=2), end="")
        elif args.contacts_command in {"status", "init", "project-run", "drift"}:
            print(json.dumps(payload, indent=2), end="")
        elif args.contacts_command == "list":
            print(_render_contacts_list_text(payload), end="")
        elif args.contacts_command == "review-surface":
            print(_render_contact_review_surface_text(payload), end="")
        elif args.contacts_command in {
            "field-correct",
            "route-override",
            "review-recommend",
            "review-states",
            "review-decide",
            "review-safe-loop",
            "route-selection-approval-boundary",
            "route-selection-command-copy-packet",
        }:
            print(json.dumps(payload, indent=2), end="")
        else:
            print(_render_contact_detail_text(payload), end="")
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
        elif args.reviews_command == "children":
            payload = service.child_review_queue(run_id=args.run_id, state=args.state)
            if not args.json:
                print(_render_child_review_queue_text(payload), end="")
                return 0
        elif args.reviews_command == "side-pairs":
            payload = service.side_pair_review_queue(run_id=args.run_id, state=args.state)
            if not args.json:
                print(_render_side_pair_review_queue_text(payload), end="")
                return 0
        elif args.reviews_command == "side-pair-review":
            payload = service.submit_side_pair_review(
                run_id=args.run_id,
                proposal_id=args.proposal_id,
                reviewer=args.reviewer,
                action=args.action,
                field_corrections=json.loads(args.field_corrections_json),
                notes=args.notes,
            )
        elif args.reviews_command == "child-review":
            payload = service.submit_child_review(
                run_id=args.run_id,
                candidate_id=args.candidate_id,
                reviewer=args.reviewer,
                action=args.action,
                field_corrections=json.loads(args.field_corrections_json),
                notes=args.notes,
            )
        elif args.reviews_command == "child-route-prep-queue":
            payload = service.child_route_prep_queue(run_id=args.run_id, state=args.state)
            if not args.json:
                print(_render_child_route_prep_queue_text(payload), end="")
                return 0
        elif args.reviews_command == "child-route-prep":
            payload = service.prepare_child_route(
                run_id=args.run_id,
                candidate_id=args.candidate_id,
                dry_run=not args.live,
            )
        elif args.reviews_command == "child-lookup-result":
            payload = service.record_child_sink_lookup_result(
                run_id=args.run_id,
                candidate_id=args.candidate_id,
                matches_by_sink=json.loads(args.matches_by_sink_json),
            )
        elif args.reviews_command == "child-assess-duplicates":
            payload = service.assess_child_downstream_duplicates(
                run_id=args.run_id,
                candidate_id=args.candidate_id,
            )
        elif args.reviews_command == "child-resolve-duplicate":
            payload = service.resolve_child_duplicate(
                run_id=args.run_id,
                candidate_id=args.candidate_id,
                reviewer=args.reviewer,
                decision=args.decision,
                target_identity=args.target_identity,
                reason=args.reason,
            )
        elif args.reviews_command == "child-sink-plan-gate":
            payload = service.child_sink_plan_gate(
                run_id=args.run_id,
                candidate_id=args.candidate_id,
            )
        elif args.reviews_command == "child-sink-apply-preflight":
            payload = service.child_sink_apply_preflight(
                run_id=args.run_id,
                candidate_id=args.candidate_id,
                apply=args.apply,
            )
        elif args.reviews_command == "child-selected-target-handoff":
            payload = service.child_selected_target_handoff(
                run_id=args.run_id,
                candidate_id=args.candidate_id,
                sink=args.sink,
                operator=args.operator,
                scope=args.scope,
                reason=args.reason,
            )
        elif args.reviews_command == "child-validate-selected-target-response":
            payload = service.validate_child_selected_target_response(
                run_id=args.run_id,
                candidate_id=args.candidate_id,
                response=args.response,
            )
        elif args.reviews_command == "child-selected-target-execution-checklist":
            payload = service.child_selected_target_execution_checklist(
                run_id=args.run_id,
                candidate_id=args.candidate_id,
                response=args.response,
            )
        elif args.reviews_command == "child-selected-target-command-copy-packet":
            payload = service.child_selected_target_command_copy_packet(
                run_id=args.run_id,
                candidate_id=args.candidate_id,
                response=args.response,
                acknowledgement=args.acknowledgement,
            )
        elif args.reviews_command == "child-selected-target-audit":
            payload = service.child_selected_target_audit(
                run_id=args.run_id,
                candidate_id=args.candidate_id,
                sink=args.sink,
                operator=args.operator,
                scope=args.scope,
                write=not args.no_write,
            )
        elif args.reviews_command == "child-abandon-selected-target":
            payload = service.abandon_child_selected_target(
                run_id=args.run_id,
                candidate_id=args.candidate_id,
                operator=args.operator,
                reason=args.reason,
            )
        elif args.reviews_command == "child-selected-target-replacement-reset":
            payload = service.child_selected_target_replacement_reset(
                run_id=args.run_id,
                candidate_id=args.candidate_id,
                sink=args.sink,
                operator=args.operator,
                scope=args.scope,
                reset_by=args.reset_by,
                reason=args.reason,
            )
        elif args.reviews_command == "child-replacement-handoff-refresh":
            payload = service.refresh_child_replacement_handoff(
                run_id=args.run_id,
                candidate_id=args.candidate_id,
                sink=args.sink,
                operator=args.operator,
                scope=args.scope,
                reason=args.reason,
            )
        elif args.reviews_command == "child-validate-replacement-response":
            payload = service.validate_child_replacement_response(
                run_id=args.run_id,
                candidate_id=args.candidate_id,
                response=args.response,
            )
        elif args.reviews_command == "child-replacement-execution-checklist":
            payload = service.child_replacement_execution_checklist(
                run_id=args.run_id,
                candidate_id=args.candidate_id,
                response=args.response,
            )
        elif args.reviews_command == "child-replacement-command-copy-packet":
            payload = service.child_replacement_command_copy_packet(
                run_id=args.run_id,
                candidate_id=args.candidate_id,
                response=args.response,
                acknowledgement=args.acknowledgement,
            )
        elif args.reviews_command == "child-replacement-closeout-status":
            payload = service.child_replacement_closeout_status(
                run_id=args.run_id,
                candidate_id=args.candidate_id,
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
        if args.drills_command == "multi-card-preclassification":
            payload = service.multi_card_preclassification_drill()
            if not args.json:
                print(_render_multi_card_preclassification_drill_text(payload), end="")
                return 0
        elif args.drills_command == "watch-dry-run-selection":
            payload = service.watch_dry_run_selection_drill()
            if not args.json:
                print(_render_watch_dry_run_selection_drill_text(payload), end="")
                return 0
        elif args.drills_command == "watch-dry-run-execution":
            payload = service.watch_dry_run_execution_drill()
            if not args.json:
                print(_render_watch_dry_run_execution_drill_text(payload), end="")
                return 0
        elif args.drills_command == "review-routing":
            payload = service.review_routing_drill()
            if not args.json:
                print(_render_review_routing_drill_text(payload), end="")
                return 0
        elif args.drills_command == "live-pilot-rehearsal":
            payload = service.live_pilot_rehearsal_drill()
            if not args.json:
                print(_render_live_pilot_rehearsal_drill_text(payload), end="")
                return 0
        elif args.drills_command == "child-replacement-readiness":
            payload = service.child_replacement_readiness_drill()
            if not args.json:
                print(_render_child_replacement_readiness_drill_text(payload), end="")
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
                provider=args.provider,
            )
        elif args.enrichment_command == "request":
            payload = service.request_enrichment(
                job_id=args.job_id,
                run_id=args.run_id,
                mode=args.mode,
                requested_by=args.requested_by,
                allow_paid_enrichment=args.allow_paid_enrichment,
                provider=args.provider,
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

    if args.command == "watch-backlog-preflight":
        payload = service.watch_backlog_preflight(write=not args.no_write)
        print(json.dumps(payload, indent=2) if args.json else _render_watch_backlog_preflight_text(payload), end="")
        return 0 if payload["state"] != "blocked" else 2

    if args.command == "watch-practice-corpus-manifest":
        payload = service.watch_practice_corpus_manifest(
            write=not args.no_write,
            include_globs=list(args.include_glob or []),
        )
        output = (
            json.dumps(payload, indent=2) if args.json else _render_watch_practice_corpus_manifest_text(payload)
        )
        print(output, end="")
        return 0 if payload["state"] != "blocked" else 2

    if args.command == "watch-dry-run-selection-handoff":
        payload = service.watch_dry_run_selection_handoff(write=not args.no_write)
        output = json.dumps(payload, indent=2) if args.json else _render_watch_dry_run_selection_handoff_text(payload)
        print(output, end="")
        return 0 if payload["state"] == "awaiting_operator_response" else 2

    if args.command == "watch-dry-run-validate-response":
        payload = service.validate_watch_dry_run_operator_response(response=args.response)
        output = (
            json.dumps(payload, indent=2)
            if args.json
            else _render_watch_dry_run_operator_response_validation_text(payload)
        )
        print(output, end="")
        return 0 if payload["state"] == "ready_for_command_copy" else 2

    if args.command == "watch-dry-run-command-copy-packet":
        payload = service.watch_dry_run_command_copy_packet(
            response=args.response,
            acknowledgement=args.acknowledgement,
        )
        output = json.dumps(payload, indent=2) if args.json else _render_watch_dry_run_command_copy_packet_text(payload)
        print(output, end="")
        return 0 if payload["state"] == "ready_for_operator_copy" else 2

    if args.command == "watch-dry-run-readiness":
        payload = service.watch_dry_run_readiness(write=not args.no_write)
        output = json.dumps(payload, indent=2) if args.json else _render_watch_dry_run_readiness_text(payload)
        print(output, end="")
        return 0 if payload["state"] == "ready_for_operator_response" else 2

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
