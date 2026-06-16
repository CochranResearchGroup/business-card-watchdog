from __future__ import annotations

import json
import hashlib
import shlex
from typing import Any

from .config import ensure_runtime_dirs
from .ledger import RunLedger
from .models import utc_now


def build_operator_live_pilot_readiness_packet(
    service: Any,
    *,
    run_id: str,
    sink: str | None = None,
    write: bool = True,
) -> dict[str, Any]:
    selected_sink = str(sink or "").strip()
    if selected_sink and selected_sink not in {"google_contacts", "odoo"}:
        raise ValueError("operator live pilot readiness packet requires sink google_contacts or odoo")
    ensure_runtime_dirs(service.config)
    dashboard = service.operator_dashboard(run_id=run_id)
    preflight = service.operator_selected_live_smoke_preflight(
        run_id=run_id,
        sink=selected_sink or None,
        write=False,
    )
    dashboard_commands = dict(dashboard.get("commands") or {})
    dashboard_api_routes = dict(dashboard.get("api_routes") or {})
    dashboard_mcp_tools = dict(dashboard.get("mcp_tools") or {})
    ready_entries = [entry for entry in list(preflight.get("ready_entries") or []) if isinstance(entry, dict)]
    active_entries = [
        entry for entry in list(preflight.get("active_selected_targets") or []) if isinstance(entry, dict)
    ]
    dashboard_sample_actions = [
        action
        for action in list(dict(dashboard.get("next_action_summary") or {}).get("sample_actions") or [])
        if isinstance(action, dict)
    ]
    dashboard_ready_entries = [
        {
            "run_id": action.get("run_id"),
            "job_id": action.get("job_id"),
            "state": "ready_for_operator_response",
            "action": action.get("action"),
            "commands": {
                "validate_operator_response_prefilled": dashboard_commands.get("live_pilot_validate_response"),
                "selected_target_approval_boundary": dashboard_commands.get("selected_target_approval_boundary"),
                "selected_target_command_copy_packet": dashboard_commands.get("selected_target_command_copy_packet"),
            },
        }
        for action in dashboard_sample_actions
        if action.get("action") == "decide_sink_apply"
        and action.get("requires_explicit_operator_action") is True
    ]
    operator_ready_entries = ready_entries or dashboard_ready_entries
    selected_entry = (
        operator_ready_entries[0]
        if operator_ready_entries
        else active_entries[0]
        if active_entries
        else {}
    )
    entry_commands = dict(selected_entry.get("commands") or {})
    checks = [
        {
            "name": "operator_dashboard_loaded",
            "ok": dashboard.get("schema") == "business-card-watchdog.operator-dashboard.v1",
            "evidence": dashboard.get("state"),
        },
        {
            "name": "operator_selected_preflight_loaded",
            "ok": preflight.get("schema") == "business-card-watchdog.operator-selected-live-smoke-preflight.v1",
            "evidence": preflight.get("state"),
        },
        {
            "name": "selected_target_approval_boundary_visible",
            "ok": "selected_target_approval_boundary" in dashboard_commands
            and "selected_target_approval_boundary" in dashboard_api_routes
            and "selected_target_approval_boundary" in dashboard_mcp_tools,
            "evidence": dashboard_commands.get("selected_target_approval_boundary"),
        },
        {
            "name": "selected_target_command_copy_visible",
            "ok": "selected_target_command_copy_packet" in dashboard_commands
            and "selected_target_command_copy_packet" in dashboard_api_routes
            and "selected_target_command_copy_packet" in dashboard_mcp_tools,
            "evidence": dashboard_commands.get("selected_target_command_copy_packet"),
        },
        {
            "name": "operator_selection_candidate_available",
            "ok": bool(operator_ready_entries or active_entries),
            "evidence": {
                "ready_entry_count": len(operator_ready_entries),
                "active_selected_target_count": len(active_entries),
            },
        },
        {
            "name": "synthetic_rehearsal_gate_available",
            "ok": dashboard_commands.get("live_pilot_rehearsal_drill") == "drills live-pilot-rehearsal --json",
            "evidence": dashboard_commands.get("live_pilot_rehearsal_drill"),
        },
    ]
    blocked_reasons = [
        str(reason)
        for reason in list(preflight.get("blocked_reasons") or [])
        if reason
        not in {
            "no candidate is ready for operator selection",
            "no candidate is ready for selected-target approval",
        }
        or not operator_ready_entries
    ]
    blocked_reasons.extend(f"{check['name']} is not ready" for check in checks if check.get("ok") is not True)
    if active_entries and not blocked_reasons:
        state = "selected_target_active"
        recommended_next_step = "inspect_selected_target_audit"
    elif operator_ready_entries and not blocked_reasons:
        state = "ready_for_operator_response"
        recommended_next_step = "selected_target_approval_boundary"
    else:
        state = "blocked"
        recommended_next_step = "resolve_blocked_checks"
    packet_path = service.config.runs_dir / run_id / "operator_live_pilot_readiness_packet.json"
    payload: dict[str, Any] = {
        "schema": "business-card-watchdog.operator-live-pilot-readiness-packet.v1",
        "generated_at": utc_now(),
        "state": state,
        "recommended_next_step": recommended_next_step,
        "run_id": run_id,
        "sink": selected_sink or None,
        "selected_entry": selected_entry,
        "ready_entry_count": len(operator_ready_entries),
        "active_selected_target_count": len(active_entries),
        "checks": checks,
        "blocked_reasons": blocked_reasons,
        "dashboard_summary": {
            "state": dashboard.get("state"),
            "selected_run_id": dashboard.get("selected_run_id"),
            "review_counts": dashboard.get("review_counts"),
            "next_action_summary": dashboard.get("next_action_summary"),
        },
        "preflight_summary": {
            "state": preflight.get("state"),
            "recommended_next_step": preflight.get("recommended_next_step"),
            "candidate_count": preflight.get("candidate_count", 0),
            "ready_entry_count": preflight.get("ready_entry_count", 0),
            "active_selected_target_count": preflight.get("active_selected_target_count", 0),
        },
        "synthetic_rehearsal_contract": {
            "command": "drills live-pilot-rehearsal --json",
            "required_packet_states": {
                "selected_target_approval_boundary": "ready_for_explicit_selected_target_creation",
                "selected_target_command_copy_packet": "ready_for_operator_copy",
                "live_pilot_command_copy_packet": "ready_for_operator_copy",
            },
            "must_report_zero_writes": True,
            "must_report_zero_network": True,
        },
        "commands": {
            "operator_dashboard": f"operator-dashboard --run-id {run_id} --json",
            "operator_live_pilot_readiness_packet": (
                "operator-live-pilot-readiness-packet"
                f" --run-id {run_id}"
                + (f" --sink {selected_sink}" if selected_sink else "")
                + " --json"
            ),
            "operator_selected_live_smoke_preflight": (
                "operator-selected-live-smoke-preflight"
                f" --run-id {run_id}"
                + (f" --sink {selected_sink}" if selected_sink else "")
                + " --no-write --json"
            ),
            "live_pilot_rehearsal_drill": "drills live-pilot-rehearsal --json",
            "validate_operator_response_prefilled": entry_commands.get("validate_operator_response_prefilled"),
            "selected_target_approval_boundary": dashboard_commands.get("selected_target_approval_boundary"),
            "selected_target_command_copy_packet": dashboard_commands.get("selected_target_command_copy_packet"),
            "live_pilot_status": dashboard_commands.get("live_pilot_status"),
            "live_pilot_handoff": dashboard_commands.get("live_pilot_handoff"),
        },
        "packet_path": str(packet_path) if write else None,
        "packet_written": False,
        "writes_attempted": 0,
        "network_calls_made": 0,
        "explicit_stop_conditions": [
            "This packet does not create selected_live_target.json.",
            "This packet does not run synthetic rehearsal automatically; run the rehearsal command separately for proof.",
            "This packet does not execute live lookup, live write, or live readback.",
            "Do not process private SyncThing images, run public-web search, or call paid enrichment from this packet.",
        ],
    }
    if write:
        packet_path.parent.mkdir(parents=True, exist_ok=True)
        packet_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        payload["packet_written"] = True
        ledger = RunLedger(service.config.runs_dir / run_id)
        ledger.record_artifact(job_id="__run__", kind="operator_live_pilot_readiness_packet", path=packet_path)
        ledger.record_event(
            "operator_live_pilot_readiness_packet_created",
            {
                "run_id": run_id,
                "sink": selected_sink or None,
                "state": state,
                "packet_path": str(packet_path),
                "writes_attempted": 0,
                "network_calls_made": 0,
            },
        )
    return payload


def build_selected_target_approval_boundary(
    service: Any,
    run_id: str,
    *,
    operator: str,
    sink: str | None = None,
    job_id: str | None = None,
    response: str | None = None,
    write: bool = True,
) -> dict[str, Any]:
    approval_packet = service.live_pilot_approval_packet(run_id=run_id, job_id=job_id)
    entries = []
    for entry in list(approval_packet.get("entries") or []):
        if not isinstance(entry, dict):
            continue
        entry_operator = str(entry.get("operator") or "")
        operator_matches = not operator or entry_operator == operator or entry_operator.startswith("<")
        if (not sink or str(entry.get("sink") or "") == sink) and operator_matches:
            entries.append(entry)
    selected_entry = entries[0] if entries else None
    selected_job_id = str((selected_entry or {}).get("job_id") or job_id or "")
    response_to_validate = response or ""
    validation = None
    preflight = None
    preview = None
    if response_to_validate:
        validation = service.validate_live_pilot_operator_response(
            run_id=run_id,
            response=response_to_validate,
        )
        preflight = service.selected_live_target_preflight(
            run_id=run_id,
            response=response_to_validate,
        )
        preview = service.selected_live_target_artifact_preview(
            run_id=run_id,
            response=response_to_validate,
        )
    if selected_entry is None:
        state = "blocked"
        blocked_reasons = ["no approval entry matched the requested run/job/sink/operator"]
    elif not response_to_validate:
        state = "awaiting_operator_response"
        blocked_reasons = ["operator response with tenant/profile safety confirmation is required"]
    elif validation and validation.get("state") == "ready_for_live_lookup_request":
        state = "selected_target_exists"
        blocked_reasons = []
    elif preflight and preflight.get("state") == "ready_to_create_selected_target":
        state = "ready_for_explicit_selected_target_creation"
        blocked_reasons = []
    else:
        state = "blocked"
        blocked_reasons = []
        if validation:
            blocked_reasons.extend(str(item) for item in list(validation.get("missing_fields") or []))
            blocked_reasons.extend(str(item) for item in list(validation.get("mismatches") or []))
        if preflight:
            blocked_reasons.extend(str(item) for item in list(preflight.get("blocked_reasons") or []))
        if not blocked_reasons:
            blocked_reasons.append("selected target approval boundary is not ready")

    commands = {
        "approval_packet": (
            f"runs live-pilot-approval-packet {shlex.quote(run_id)}"
            + (f" --job-id {shlex.quote(selected_job_id)}" if selected_job_id else "")
            + " --json"
        ),
        "live_pilot_handoff": f"runs live-pilot-handoff {shlex.quote(run_id)} --no-write --json",
        "selected_target_approval_boundary": (
            f"runs selected-target-approval-boundary {shlex.quote(run_id)} "
            f"--operator {shlex.quote(operator)}"
            + (f" --sink {shlex.quote(sink)}" if sink else "")
            + (f" --job-id {shlex.quote(selected_job_id)}" if selected_job_id else "")
            + " --json"
        ),
        "validate_response": (
            f"runs live-pilot-validate-response {shlex.quote(run_id)} "
            f"--response {shlex.quote(response_to_validate)} --json"
            if response_to_validate
            else None
        ),
        "selected_target_preflight": (
            f"runs selected-live-target-preflight {shlex.quote(run_id)} "
            f"--response {shlex.quote(response_to_validate)} --json"
            if response_to_validate
            else None
        ),
        "selected_target_preview": (
            f"runs selected-live-target-preview {shlex.quote(run_id)} "
            f"--response {shlex.quote(response_to_validate)} --json"
            if response_to_validate
            else None
        ),
        "select_target": (preflight or {}).get("select_target_command") if preflight else None,
    }
    payload: dict[str, Any] = {
        "schema": "business-card-watchdog.selected-target-approval-boundary.v1",
        "generated_at": utc_now(),
        "state": state,
        "run_id": run_id,
        "job_id": selected_job_id or None,
        "sink": sink or (selected_entry or {}).get("sink"),
        "operator": operator,
        "response_supplied": bool(response_to_validate),
        "approval_packet_state": approval_packet.get("state"),
        "approval_entry_count": len(entries),
        "selected_entry": selected_entry,
        "operator_response_template": (selected_entry or {}).get("operator_response_template"),
        "validation_command_prefilled": (selected_entry or {}).get("validation_command_prefilled"),
        "validation": validation,
        "preflight": preflight,
        "preview": preview,
        "blocked_reasons": blocked_reasons,
        "would_create_selected_live_target": bool(preflight and preflight.get("would_create_selected_live_target")),
        "creates_selected_live_target": False,
        "writes_attempted": 0,
        "network_calls_made": 0,
        "runtime_artifact_written": False,
        "boundary_path": None,
        "commands": commands,
        "explicit_stop_conditions": [
            "This boundary packet does not create selected_live_target.json.",
            "Run the select_target command only after explicit operator approval and tenant/profile safety confirmation.",
            "This boundary packet does not execute live lookup, write, or readback.",
            "Do not process private SyncThing images, run public-web search, or call paid enrichment from this packet.",
        ],
    }
    if write:
        boundary_path = service.config.runs_dir / run_id / "selected_target_approval_boundary.json"
        payload["runtime_artifact_written"] = True
        payload["boundary_path"] = str(boundary_path)
        boundary_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        ledger = RunLedger(service.config.runs_dir / run_id)
        ledger.record_artifact(job_id="__run__", kind="selected_target_approval_boundary", path=boundary_path)
        ledger.record_event(
            "selected_target_approval_boundary_created",
            {
                "run_id": run_id,
                "job_id": selected_job_id or None,
                "sink": payload["sink"],
                "operator": operator,
                "state": state,
                "boundary_path": str(boundary_path),
                "writes_attempted": 0,
                "network_calls_made": 0,
            },
        )
    return payload


def build_selected_target_command_copy_packet(
    service: Any,
    run_id: str,
    *,
    operator: str,
    response: str,
    acknowledgement: str = "",
    sink: str | None = None,
    job_id: str | None = None,
) -> dict[str, Any]:
    boundary = service.selected_target_approval_boundary(
        run_id,
        operator=operator,
        sink=sink,
        job_id=job_id,
        response=response,
        write=False,
    )
    blocked_reasons = list(boundary.get("blocked_reasons") or [])
    normalized_acknowledgement = " ".join(str(acknowledgement or "").lower().split())
    acknowledgement_terms = {
        "run_id": str(boundary.get("run_id") or ""),
        "job_id": str(boundary.get("job_id") or ""),
        "sink": str(boundary.get("sink") or ""),
        "operator": str(boundary.get("operator") or ""),
    }
    missing_acknowledgement_terms = [
        f"{key}={value}"
        for key, value in acknowledgement_terms.items()
        if value and value.lower() not in normalized_acknowledgement
    ]
    acknowledgement_verb_ok = any(
        verb in normalized_acknowledgement
        for verb in ["acknowledge", "acknowledged", "approve", "approved", "copy", "ready"]
    )
    if not normalized_acknowledgement:
        blocked_reasons.append("operator acknowledgement is required before selected-target command copy text is shown")
    if missing_acknowledgement_terms:
        blocked_reasons.append(
            "operator acknowledgement must name "
            + ", ".join(missing_acknowledgement_terms)
            + " before selected-target command copy text is shown"
        )
    if not acknowledgement_verb_ok:
        blocked_reasons.append("operator acknowledgement must include one of acknowledge, approved, copy, or ready")
    boundary_ready = boundary.get("state") == "ready_for_explicit_selected_target_creation"
    acknowledgement_ok = bool(normalized_acknowledgement and not missing_acknowledgement_terms and acknowledgement_verb_ok)
    select_command = None
    if boundary_ready and acknowledgement_ok and not blocked_reasons:
        select_command = (
            f"runs selected-live-target-from-response {shlex.quote(run_id)} "
            f"--response {shlex.quote(response)} --write-selected-target --json"
        )
    state = "ready_for_operator_copy" if select_command else "blocked"
    return {
        "schema": "business-card-watchdog.selected-target-command-copy-packet.v1",
        "generated_at": utc_now(),
        "state": state,
        "run_id": run_id,
        "job_id": boundary.get("job_id"),
        "sink": boundary.get("sink"),
        "operator": operator,
        "acknowledgement_required": True,
        "acknowledgement_ok": acknowledgement_ok,
        "acknowledgement_instruction": (
            "Acknowledge the exact run_id, job_id, sink, and operator plus an approval/copy verb before copying."
        ),
        "acknowledgement_redacted": {
            "raw_acknowledgement_stored": False,
            "sha256": hashlib.sha256(acknowledgement.encode("utf-8")).hexdigest() if acknowledgement else None,
            "required_terms": acknowledgement_terms,
            "missing_terms": missing_acknowledgement_terms,
        },
        "boundary_state": boundary.get("state"),
        "boundary": boundary,
        "command_copy_text": select_command,
        "selected_target_command": select_command,
        "blocked_reasons": blocked_reasons,
        "creates_selected_live_target": False,
        "writes_attempted": 0,
        "network_calls_made": 0,
        "explicit_stop_conditions": [
            "This packet only returns selected-target creation command text for operator copy; it never executes the command.",
            "Do not copy command_copy_text unless state is ready_for_operator_copy.",
            "Copying command_copy_text would create selected_live_target.json but would not execute live lookup, write, or readback.",
            "Do not process private SyncThing images, run public-web search, or call paid enrichment from this packet.",
        ],
    }
