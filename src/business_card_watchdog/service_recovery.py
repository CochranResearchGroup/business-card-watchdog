from __future__ import annotations

from typing import Any

from .models import utc_now


_EXPLICIT_OPERATOR_ACTIONS = {
    "decide_sink_apply",
    "execute_sink_lookup_pilot",
    "execute_sink_write_pilot",
    "execute_sink_readback_pilot",
    "await_apply_approval",
    "request_enrichment",
    "review_contact",
    "review_duplicate",
    "review_enrichment",
    "resolve_duplicate",
}


def build_service_recovery_report(business_service: Any, *, run_id: str | None = None) -> dict[str, Any]:
    readiness = business_service.runtime_readiness()
    service = dict(readiness["service"])
    watch = dict(readiness["watch"])
    runs = business_service.list_runs()
    selected_run_id = run_id or (str(runs[0]["run_id"]) if runs else None)
    latest_drill = business_service.latest_review_routing_drill(selected_run_id=selected_run_id)
    run_summary: dict[str, Any] | None = None
    phase_report: dict[str, Any] | None = None
    pilot_readiness: dict[str, Any] | None = None
    next_actions: dict[str, Any] | None = None
    live_pilot_checklist_rollup = _live_pilot_checklist_rollup(None)
    if selected_run_id:
        run_summary = business_service.run_summary(selected_run_id)
        phase_report = business_service.phase_report(selected_run_id)
        pilot_readiness = business_service.pilot_readiness_report(selected_run_id)
        next_actions = business_service.next_actions(run_id=selected_run_id, limit=20)
        live_pilot_checklist_rollup = _live_pilot_checklist_rollup(
            business_service.live_pilot_handoff(run_id=selected_run_id, write=False)
        )

    command_prefix = f"bcw --config {business_service.config.config_path} "
    service_name = str(service.get("service_name") or "business-card-watchdog.service")
    commands = {
        "install": f"{command_prefix}service install --json",
        "start": f"systemctl --user start {service_name}",
        "status": f"{command_prefix}service status --json",
        "runtime_status": f"{command_prefix}runtime-readiness --json",
        "watch_status": f"{command_prefix}watch-status --json",
        "review_routing_drill": f"{command_prefix}drills review-routing --json",
        "restart": f"systemctl --user restart {service_name}",
        "resume": f"{command_prefix}actions run-next --run-id {selected_run_id} --limit 10 --json"
        if selected_run_id
        else f"{command_prefix}runs list --json",
        "recover": f"{command_prefix}service recovery --run-id {selected_run_id} --json"
        if selected_run_id
        else f"{command_prefix}service recovery --json",
        "live_pilot_status": f"{command_prefix}runs live-pilot-status {selected_run_id} --no-write --json"
        if selected_run_id
        else f"{command_prefix}runs list --json",
        "live_pilot_handoff": f"{command_prefix}runs live-pilot-handoff {selected_run_id}"
        if selected_run_id
        else f"{command_prefix}runs list --json",
    }
    blocked_reasons: list[dict[str, Any]] = []
    if readiness["state"] == "blocked":
        blocked_reasons.extend(
            {
                "source": "runtime_readiness",
                "name": str(check.get("name") or "unknown"),
                "detail": str(check.get("detail") or ""),
            }
            for check in readiness.get("blocked_checks", [])
            if isinstance(check, dict)
        )
    if watch.get("last_error"):
        blocked_reasons.append(
            {
                "source": "watch",
                "name": "watch_inputs",
                "detail": str(watch["last_error"]),
            }
        )
    explicit_action_count = 0
    safe_action_count = 0
    if pilot_readiness:
        counts = dict(pilot_readiness.get("counts") or {})
        explicit_action_count = int(counts.get("explicit_operator_required") or 0)
        safe_action_count = int(counts.get("safe_auto_available") or 0)
    if blocked_reasons:
        state = "blocked"
    elif explicit_action_count:
        state = "operator_required"
    elif safe_action_count:
        state = "safe_resume_available"
    elif readiness["state"] == "warning":
        state = "warning"
    else:
        state = "ready"
    safe_next_actions = [
        {
            "action": "inspect_runtime_readiness",
            "command": commands["runtime_status"],
            "reason": "confirm config, runtime paths, watcher, and service readiness before recovery",
            "safe_to_auto_continue": True,
            "requires_explicit_operator_action": False,
        },
        {
            "action": "inspect_watch_status",
            "command": commands["watch_status"],
            "reason": "confirm watched inputs, backlog, unsettled files, and last watcher error",
            "safe_to_auto_continue": True,
            "requires_explicit_operator_action": False,
        },
        {
            "action": "run_fixture_review_routing_drill",
            "command": commands["review_routing_drill"],
            "reason": "prove review/export/routing readiness with synthetic fixture data before private or live work",
            "safe_to_auto_continue": True,
            "requires_explicit_operator_action": False,
        },
    ]
    if selected_run_id and safe_action_count:
        safe_next_actions.append(
            {
                "action": "resume_safe_next_actions",
                "command": commands["resume"],
                "reason": "run has deterministic zero-network/zero-write actions available",
                "safe_to_auto_continue": True,
                "requires_explicit_operator_action": False,
            }
        )
    if selected_run_id:
        safe_next_actions.extend(
            [
                {
                    "action": "inspect_live_pilot_status",
                    "command": commands["live_pilot_status"],
                    "reason": "inspect selected-run live pilot state without writing artifacts or running live calls",
                    "safe_to_auto_continue": True,
                    "requires_explicit_operator_action": False,
                },
                {
                    "action": "inspect_live_pilot_handoff",
                    "command": commands["live_pilot_handoff"] + " --no-write --json",
                    "reason": "inspect selected-run live pilot handoff without writing artifacts or running live calls",
                    "safe_to_auto_continue": True,
                    "requires_explicit_operator_action": False,
                },
            ]
        )
    return {
        "schema": "business-card-watchdog.service-recovery.v1",
        "generated_at": utc_now(),
        "state": state,
        "run_id": selected_run_id,
        "network_calls_made": 0,
        "writes_attempted": 0,
        "service": service,
        "runtime_readiness": readiness,
        "watch": watch,
        "latest_runs": runs[:5],
        "run_summary": run_summary,
        "phase_dashboard_summary": (phase_report or {}).get("dashboard_summary") if phase_report else None,
        "pilot_readiness": pilot_readiness,
        "next_actions": (next_actions or {}).get("actions", []) if next_actions else [],
        "latest_review_routing_drill": latest_drill,
        "live_pilot_checklist_rollup": live_pilot_checklist_rollup,
        "blocked_reasons": blocked_reasons,
        "commands": commands,
        "safe_next_actions": safe_next_actions,
        "explicit_operator_actions": [
            action
            for action in ((next_actions or {}).get("actions", []) if next_actions else [])
            if action.get("requires_explicit_operator_action")
            or action.get("action") in _EXPLICIT_OPERATOR_ACTIONS
        ],
        "recovery_sequence": [
            {
                "step": "status",
                "command": commands["runtime_status"],
                "purpose": "confirm user-scope config, runtime directories, service unit, and watched inputs",
            },
            {
                "step": "restart",
                "command": commands["restart"],
                "purpose": "restart the user-scoped watched-folder daemon if it is installed but stale",
            },
            {
                "step": "resume",
                "command": commands["resume"],
                "purpose": "resume only deterministic zero-network/zero-write actions for the selected run",
            },
            {
                "step": "recover",
                "command": commands["recover"],
                "purpose": "re-read recovery state after any restart, config repair, or safe resume",
            },
        ],
        "explicit_stop_conditions": [
            "Do not scan or process private SyncThing images from generic recovery.",
            "Do not run public-web search or paid enrichment from recovery.",
            "Do not execute live GWS/Odollo/Odoo lookup, write, or readback without selected-target approval.",
            "Stop when next actions require review, duplicate resolution, selected target approval, live lookup, live write, or readback.",
        ],
    }



def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _live_pilot_checklist_rollup(handoff: dict[str, Any] | None) -> dict[str, Any]:
    entries = [entry for entry in list((handoff or {}).get("entries") or []) if isinstance(entry, dict)]
    actionable_entries = [entry for entry in entries if entry.get("operator_required")]
    checklist_summaries = [
        dict(entry.get("pilot_command_checklist_summary") or {})
        for entry in actionable_entries
        if isinstance(entry.get("pilot_command_checklist_summary"), dict)
    ]
    return {
        "schema": "business-card-watchdog.live-pilot-checklist-rollup.v1",
        "job_count": len(entries),
        "operator_required_job_count": len(actionable_entries),
        "checklist_job_count": len(checklist_summaries),
        "step_count": sum(_to_int(summary.get("step_count")) for summary in checklist_summaries),
        "live_call_count": sum(_to_int(summary.get("live_call_count")) for summary in checklist_summaries),
        "sink_write_step_count": sum(_to_int(summary.get("sink_write_step_count")) for summary in checklist_summaries),
        "explicit_operator_step_count": sum(
            _to_int(summary.get("explicit_operator_step_count")) for summary in checklist_summaries
        ),
        "runtime_artifact_step_count": sum(
            _to_int(summary.get("runtime_artifact_step_count")) for summary in checklist_summaries
        ),
        "sample_jobs": [
            {
                "job_id": entry.get("job_id"),
                "next_action": entry.get("next_action"),
                "step_count": _to_int((entry.get("pilot_command_checklist_summary") or {}).get("step_count")),
                "live_call_count": _to_int(
                    (entry.get("pilot_command_checklist_summary") or {}).get("live_call_count")
                ),
                "sink_write_step_count": _to_int(
                    (entry.get("pilot_command_checklist_summary") or {}).get("sink_write_step_count")
                ),
            }
            for entry in actionable_entries[:5]
        ],
    }
