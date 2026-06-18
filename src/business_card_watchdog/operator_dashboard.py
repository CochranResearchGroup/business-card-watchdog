from __future__ import annotations

from typing import Any

from .models import utc_now


def build_operator_dashboard(service: Any, *, run_id: str | None = None) -> dict[str, Any]:
    status = service.status()
    runtime = service.runtime_readiness()
    runs = service.list_runs()
    selected_run_id = run_id or (str(runs[0]["run_id"]) if runs else None)
    recovery = service.service_recovery_report(run_id=selected_run_id)
    latest_drill = service.latest_review_routing_drill(selected_run_id=selected_run_id)
    run_summary: dict[str, Any] | None = None
    phase_dashboard: dict[str, Any] | None = None
    review_counts: dict[str, int] = {}
    live_pilot_summary: dict[str, Any] | None = None
    live_pilot_handoff_summary: dict[str, Any] | None = None
    child_replacement_summary: dict[str, Any] | None = None
    next_action_summary: dict[str, Any] = {
        "action_count": 0,
        "safe_auto_count": 0,
        "explicit_operator_count": 0,
        "by_action": {},
        "sample_actions": [],
    }

    if selected_run_id:
        run_summary = service.run_summary(selected_run_id)
        phase_dashboard = service.phase_report(selected_run_id)["dashboard_summary"]
        review_entries = service.review_queue(run_id=selected_run_id, state="all")
        for entry in review_entries:
            state = str(entry.get("state") or "unknown")
            review_counts[state] = review_counts.get(state, 0) + 1
        live_status = service.live_pilot_status(run_id=selected_run_id, write=False)
        live_pilot_summary = {
            "state": live_status.get("state"),
            "job_count": live_status.get("job_count", 0),
            "counts": live_status.get("counts") or {},
            "observed_writes_attempted": live_status.get("observed_writes_attempted", 0),
            "observed_network_calls_made": live_status.get("observed_network_calls_made", 0),
            "commands": live_status.get("commands") or {},
            "explicit_stop_conditions": live_status.get("explicit_stop_conditions") or [],
        }
        handoff = service.live_pilot_handoff(run_id=selected_run_id, write=False)
        pilot_checklist_rollup = _live_pilot_checklist_rollup(handoff)
        operator_entries = [
            {
                "job_id": entry.get("job_id"),
                "next_action": entry.get("next_action"),
                "command": entry.get("command"),
                "operator_response_template": entry.get("operator_response_template"),
                "operator_prompt": entry.get("operator_prompt"),
                "pilot_command_sequence_summary": _pilot_command_sequence_summary(
                    dict(entry.get("pilot_command_sequence") or {})
                ),
                "validation_command": (entry.get("commands") or {}).get("validate_operator_response"),
                "validation_command_prefilled": (entry.get("commands") or {}).get(
                    "validate_operator_response_prefilled"
                ),
            }
            for entry in handoff.get("entries") or []
            if isinstance(entry, dict) and entry.get("operator_required")
        ]
        operator_response_templates = list(handoff.get("operator_response_templates") or [])
        live_pilot_execution_packet = _operator_dashboard_live_pilot_execution_packet(
            selected_run_id,
            handoff,
        )
        live_pilot_handoff_summary = {
            "schema": "business-card-watchdog.operator-dashboard.live-pilot-handoff-summary.v1",
            "state": handoff.get("state"),
            "job_count": handoff.get("job_count", 0),
            "action_counts": handoff.get("action_counts") or {},
            "operator_required_count": len(operator_entries),
            "operator_entries": operator_entries[:5],
            "operator_response_template_count": len(operator_response_templates),
            "operator_response_templates": operator_response_templates[:5],
            "operator_response_contract": handoff.get("operator_response_contract"),
            "writes_attempted": handoff.get("writes_attempted", 0),
            "network_calls_made": handoff.get("network_calls_made", 0),
            "observed_writes_attempted": handoff.get("observed_writes_attempted", 0),
            "observed_network_calls_made": handoff.get("observed_network_calls_made", 0),
            "pilot_checklist_rollup": pilot_checklist_rollup,
            "execution_packet": live_pilot_execution_packet,
            "operator_stop_conditions": handoff.get("operator_stop_conditions") or [],
        }
        review_bundle = service.review_bundle(run_id=selected_run_id, state="all", write=False)
        child_replacement_entries = [
            {
                "job_id": entry.get("job_id"),
                "candidate_id": (entry.get("child_replacement_status") or {}).get("candidate_id"),
                "state": (entry.get("child_replacement_status") or {}).get("state"),
                "sink": (entry.get("child_replacement_status") or {}).get("sink"),
                "operator": (entry.get("child_replacement_status") or {}).get("operator"),
                "predecessor_artifacts_stale": (entry.get("child_replacement_status") or {}).get(
                    "predecessor_artifacts_stale"
                ),
                "replacement_copy_ready": (entry.get("child_replacement_status") or {}).get(
                    "replacement_copy_ready"
                ),
                "closeout_command": (
                    (entry.get("child_replacement_status") or {}).get("commands") or {}
                ).get("closeout_status"),
            }
            for entry in review_bundle.get("entries") or []
            if (entry.get("child_replacement_status") or {}).get("has_closeout")
        ]
        child_replacement_summary = {
            "schema": "business-card-watchdog.operator-dashboard.child-replacement-summary.v1",
            "state_counts": (review_bundle.get("groups") or {}).get("by_child_replacement_state") or {},
            "closeout_count": len(child_replacement_entries),
            "ready_count": sum(
                1
                for entry in child_replacement_entries
                if entry.get("state") == "ready_for_operator_closeout"
            ),
            "entries": child_replacement_entries[:5],
            "writes_attempted": 0,
            "network_calls_made": 0,
        }
        next_actions = service.next_actions(run_id=selected_run_id, limit=20)
        action_counts: dict[str, int] = {}
        safe_auto_count = 0
        explicit_operator_count = 0
        sample_actions: list[dict[str, Any]] = []
        for action in next_actions["actions"]:
            action_name = str(action.get("action") or "unknown")
            action_counts[action_name] = action_counts.get(action_name, 0) + 1
            if action.get("safe_to_auto_continue"):
                safe_auto_count += 1
            if action.get("requires_explicit_operator_action"):
                explicit_operator_count += 1
            sample_actions.append(
                {
                    "run_id": action.get("run_id"),
                    "job_id": action.get("job_id"),
                    "action": action_name,
                    "command": action.get("command"),
                    "safe_to_auto_continue": action.get("safe_to_auto_continue", False),
                    "requires_explicit_operator_action": action.get(
                        "requires_explicit_operator_action",
                        False,
                    ),
                }
            )
        next_action_summary = {
            "action_count": next_actions["action_count"],
            "safe_auto_count": safe_auto_count,
            "explicit_operator_count": explicit_operator_count,
            "by_action": dict(sorted(action_counts.items())),
            "sample_actions": sample_actions,
        }

    blocked_reasons: list[str] = []
    if runtime.get("state") == "blocked":
        blocked_reasons.append("runtime readiness is blocked")
    if recovery.get("state") == "blocked":
        blocked_reasons.extend(str(item) for item in recovery.get("blocked_reasons") or [])
    if not selected_run_id:
        blocked_reasons.append("no run selected or available for review/routing/live-pilot inspection")

    return {
        "schema": "business-card-watchdog.operator-dashboard.v1",
        "created_at": utc_now(),
        "state": "blocked" if blocked_reasons else "ready",
        "config_path": status.get("config_path"),
        "data_dir": status.get("data_dir"),
        "cache_dir": status.get("cache_dir"),
        "selected_run_id": selected_run_id,
        "run_count": len(runs),
        "recent_runs": runs[:5],
        "status": status,
        "runtime_readiness": runtime,
        "service_recovery": recovery,
        "run_summary": run_summary,
        "phase_dashboard_summary": phase_dashboard,
        "review_counts": review_counts,
        "next_action_summary": next_action_summary,
        "live_pilot_summary": live_pilot_summary,
        "live_pilot_handoff_summary": live_pilot_handoff_summary,
        "child_replacement_summary": child_replacement_summary,
        "latest_review_routing_drill": latest_drill,
        "blocked_reasons": blocked_reasons,
        "commands": {
            "operator_dashboard": (
                f"operator-dashboard --run-id {selected_run_id} --json"
                if selected_run_id
                else "operator-dashboard --json"
            ),
            "status": "status --json",
            "runtime_readiness": "runtime-readiness --json",
            "service_recovery": (
                f"service recovery --run-id {selected_run_id} --json"
                if selected_run_id
                else "service recovery --json"
            ),
            "runs_list": "runs list --json",
            "review_queue": (
                f"reviews list --run-id {selected_run_id} --state all --json"
                if selected_run_id
                else "runs list --json"
            ),
            "child_review_queue": (
                f"reviews children --run-id {selected_run_id} --state needs_review --json"
                if selected_run_id
                else "runs list --json"
            ),
            "phase_report": (
                f"runs phase-report {selected_run_id} --json" if selected_run_id else "runs list --json"
            ),
            "next_actions": (
                f"actions next --run-id {selected_run_id} --json" if selected_run_id else "runs list --json"
            ),
            "run_next_safe": (
                f"actions run-next --run-id {selected_run_id} --limit 10 --json"
                if selected_run_id
                else "runs list --json"
            ),
            "multi_card_preclassification_drill": "drills multi-card-preclassification --json",
            "review_routing_drill": "drills review-routing --json",
            "live_pilot_rehearsal_drill": "drills live-pilot-rehearsal --json",
            "child_replacement_readiness_drill": "drills child-replacement-readiness --json",
            "live_pilot_status": (
                f"runs live-pilot-status {selected_run_id} --no-write --json"
                if selected_run_id
                else "runs list --json"
            ),
            "live_pilot_handoff": (
                f"runs live-pilot-handoff {selected_run_id} --no-write --json"
                if selected_run_id
                else "runs list --json"
            ),
            "live_pilot_approval_packet": (
                f"runs live-pilot-approval-packet {selected_run_id} --json"
                if selected_run_id
                else "runs list --json"
            ),
            "live_pilot_validate_response": (
                f"runs live-pilot-validate-response {selected_run_id} --response <operator-response> --json"
                if selected_run_id
                else "runs list --json"
            ),
            "selected_live_target_preflight": (
                f"runs selected-live-target-preflight {selected_run_id} --response <operator-response> --json"
                if selected_run_id
                else "runs list --json"
            ),
            "selected_target_approval_boundary": (
                f"runs selected-target-approval-boundary {selected_run_id} "
                "--operator <operator> --response <operator-response> --no-write --json"
                if selected_run_id
                else "runs list --json"
            ),
            "selected_target_command_copy_packet": (
                f"runs selected-target-command-copy-packet {selected_run_id} "
                "--operator <operator> --response <operator-response> "
                "--acknowledgement <operator-acknowledgement> --json"
                if selected_run_id
                else "runs list --json"
            ),
            "selected_live_target_preview": (
                f"runs selected-live-target-preview {selected_run_id} --response <operator-response> --json"
                if selected_run_id
                else "runs list --json"
            ),
            "selected_live_target_from_response": (
                f"runs selected-live-target-from-response {selected_run_id} "
                "--response <operator-response> --json"
                if selected_run_id
                else "runs list --json"
            ),
            "selected_live_target_handoff_from_response": (
                f"runs selected-live-target-handoff-from-response {selected_run_id} "
                "--response <operator-response> --json"
                if selected_run_id
                else "runs list --json"
            ),
            "lookup_smoke_handoff_from_response": (
                f"runs lookup-smoke-handoff-from-response {selected_run_id} "
                "--response <operator-response> --json"
                if selected_run_id
                else "runs list --json"
            ),
            "selected_lookup_smoke_execution_packet_from_response": (
                f"runs selected-lookup-smoke-execution-packet-from-response {selected_run_id} "
                "--response <operator-response> --json"
                if selected_run_id
                else "runs list --json"
            ),
            "selected_write_pilot_execution_packet_from_response": (
                f"runs selected-write-pilot-execution-packet-from-response {selected_run_id} "
                "--response <operator-response> --json"
                if selected_run_id
                else "runs list --json"
            ),
            "selected_readback_pilot_execution_packet_from_response": (
                f"runs selected-readback-pilot-execution-packet-from-response {selected_run_id} "
                "--response <operator-response> --json"
                if selected_run_id
                else "runs list --json"
            ),
            "live_pilot_closeout_packet_from_response": (
                f"runs live-pilot-closeout-packet-from-response {selected_run_id} "
                "--response <operator-response> --json"
                if selected_run_id
                else "runs list --json"
            ),
            "live_pilot_operator_workflow_packet_from_response": (
                f"runs live-pilot-operator-workflow-packet-from-response {selected_run_id} "
                "--response <operator-response> --json"
                if selected_run_id
                else "runs list --json"
            ),
            "live_pilot_operator_rehearsal_from_response": (
                f"runs live-pilot-operator-rehearsal-from-response {selected_run_id} "
                "--response <operator-response> --json"
                if selected_run_id
                else "runs list --json"
            ),
            "live_pilot_readiness_export_from_response": (
                f"runs live-pilot-readiness-export-from-response {selected_run_id} "
                "--response <operator-response> --json"
                if selected_run_id
                else "runs list --json"
            ),
            "live_pilot_execution_checklist_from_response": (
                f"runs live-pilot-execution-checklist-from-response {selected_run_id} "
                "--response <operator-response> --json"
                if selected_run_id
                else "runs list --json"
            ),
            "live_pilot_command_copy_packet_from_response": (
                f"runs live-pilot-command-copy-packet-from-response {selected_run_id} "
                "--response <operator-response> --acknowledgement <operator-acknowledgement> --json"
                if selected_run_id
                else "runs list --json"
            ),
            "mcp_manifest": "mcp-manifest",
        },
        "api_routes": {
            "operator_dashboard": (
                f"GET /operator/dashboard?run_id={selected_run_id}"
                if selected_run_id
                else "GET /operator/dashboard"
            ),
            "next_actions": (
                f"GET /actions/next?run_id={selected_run_id}&limit=20"
                if selected_run_id
                else "GET /actions/next?limit=20"
            ),
            "child_review_queue": (
                f"GET /reviews/children?run_id={selected_run_id}&state=needs_review"
                if selected_run_id
                else "GET /reviews/children?state=needs_review"
            ),
            "run_next_safe": "POST /actions/run-next",
            "multi_card_preclassification_drill": "POST /drills/multi-card-preclassification",
            "review_routing_drill": "POST /drills/review-routing",
            "live_pilot_rehearsal_drill": "POST /drills/live-pilot-rehearsal",
            "child_replacement_readiness_drill": "POST /drills/child-replacement-readiness",
            "live_pilot_status": (
                f"GET /runs/{selected_run_id}/live-pilot-status?write=false"
                if selected_run_id
                else "GET /runs/{run_id}/live-pilot-status?write=false"
            ),
            "live_pilot_handoff": (
                f"GET /runs/{selected_run_id}/live-pilot-handoff?write=false"
                if selected_run_id
                else "GET /runs/{run_id}/live-pilot-handoff?write=false"
            ),
            "live_pilot_approval_packet": (
                f"GET /runs/{selected_run_id}/live-pilot-approval-packet"
                if selected_run_id
                else "GET /runs/{run_id}/live-pilot-approval-packet"
            ),
            "live_pilot_validate_response": (
                f"POST /runs/{selected_run_id}/live-pilot-operator-response-validation"
                if selected_run_id
                else "POST /runs/{run_id}/live-pilot-operator-response-validation"
            ),
            "selected_live_target_preflight": (
                f"POST /runs/{selected_run_id}/selected-live-target-preflight"
                if selected_run_id
                else "POST /runs/{run_id}/selected-live-target-preflight"
            ),
            "selected_target_approval_boundary": (
                f"POST /runs/{selected_run_id}/selected-target-approval-boundary"
                if selected_run_id
                else "POST /runs/{run_id}/selected-target-approval-boundary"
            ),
            "selected_target_command_copy_packet": (
                f"POST /runs/{selected_run_id}/selected-target-command-copy-packet"
                if selected_run_id
                else "POST /runs/{run_id}/selected-target-command-copy-packet"
            ),
            "selected_live_target_preview": (
                f"POST /runs/{selected_run_id}/selected-live-target-preview"
                if selected_run_id
                else "POST /runs/{run_id}/selected-live-target-preview"
            ),
            "selected_live_target_from_response": (
                f"POST /runs/{selected_run_id}/selected-live-target-from-response"
                if selected_run_id
                else "POST /runs/{run_id}/selected-live-target-from-response"
            ),
            "selected_live_target_handoff_from_response": (
                f"POST /runs/{selected_run_id}/selected-live-target-handoff-from-response"
                if selected_run_id
                else "POST /runs/{run_id}/selected-live-target-handoff-from-response"
            ),
            "lookup_smoke_handoff_from_response": (
                f"POST /runs/{selected_run_id}/lookup-smoke-handoff-from-response"
                if selected_run_id
                else "POST /runs/{run_id}/lookup-smoke-handoff-from-response"
            ),
            "selected_lookup_smoke_execution_packet_from_response": (
                f"POST /runs/{selected_run_id}/selected-lookup-smoke-execution-packet-from-response"
                if selected_run_id
                else "POST /runs/{run_id}/selected-lookup-smoke-execution-packet-from-response"
            ),
            "selected_write_pilot_execution_packet_from_response": (
                f"POST /runs/{selected_run_id}/selected-write-pilot-execution-packet-from-response"
                if selected_run_id
                else "POST /runs/{run_id}/selected-write-pilot-execution-packet-from-response"
            ),
            "selected_readback_pilot_execution_packet_from_response": (
                f"POST /runs/{selected_run_id}/selected-readback-pilot-execution-packet-from-response"
                if selected_run_id
                else "POST /runs/{run_id}/selected-readback-pilot-execution-packet-from-response"
            ),
            "live_pilot_closeout_packet_from_response": (
                f"POST /runs/{selected_run_id}/live-pilot-closeout-packet-from-response"
                if selected_run_id
                else "POST /runs/{run_id}/live-pilot-closeout-packet-from-response"
            ),
            "live_pilot_operator_workflow_packet_from_response": (
                f"POST /runs/{selected_run_id}/live-pilot-operator-workflow-packet-from-response"
                if selected_run_id
                else "POST /runs/{run_id}/live-pilot-operator-workflow-packet-from-response"
            ),
            "live_pilot_operator_rehearsal_from_response": (
                f"POST /runs/{selected_run_id}/live-pilot-operator-rehearsal-from-response"
                if selected_run_id
                else "POST /runs/{run_id}/live-pilot-operator-rehearsal-from-response"
            ),
            "live_pilot_readiness_export_from_response": (
                f"POST /runs/{selected_run_id}/live-pilot-readiness-export-from-response"
                if selected_run_id
                else "POST /runs/{run_id}/live-pilot-readiness-export-from-response"
            ),
            "live_pilot_execution_checklist_from_response": (
                f"POST /runs/{selected_run_id}/live-pilot-execution-checklist-from-response"
                if selected_run_id
                else "POST /runs/{run_id}/live-pilot-execution-checklist-from-response"
            ),
            "live_pilot_command_copy_packet_from_response": (
                f"POST /runs/{selected_run_id}/live-pilot-command-copy-packet-from-response"
                if selected_run_id
                else "POST /runs/{run_id}/live-pilot-command-copy-packet-from-response"
            ),
        },
        "mcp_tools": {
            "operator_dashboard": {
                "tool": "business_card_watchdog_operator_dashboard",
                "arguments": {"run_id": selected_run_id} if selected_run_id else {},
            },
            "next_actions": {
                "tool": "business_card_watchdog_next_actions",
                "arguments": {"run_id": selected_run_id, "limit": 20}
                if selected_run_id
                else {"limit": 20},
            },
            "run_next_safe": {
                "tool": "business_card_watchdog_run_next_actions",
                "arguments": {"run_id": selected_run_id, "limit": 10}
                if selected_run_id
                else {"limit": 10},
            },
            "child_review_queue": {
                "tool": "business_card_watchdog_child_reviews_list",
                "arguments": {"run_id": selected_run_id, "state": "needs_review"}
                if selected_run_id
                else {"state": "needs_review"},
            },
            "multi_card_preclassification_drill": {
                "tool": "business_card_watchdog_multi_card_preclassification_drill",
                "arguments": {},
            },
            "review_routing_drill": {
                "tool": "business_card_watchdog_review_routing_drill",
                "arguments": {},
            },
            "live_pilot_rehearsal_drill": {
                "tool": "business_card_watchdog_live_pilot_rehearsal_drill",
                "arguments": {},
            },
            "child_replacement_readiness_drill": {
                "tool": "business_card_watchdog_child_replacement_readiness_drill",
                "arguments": {},
            },
            "live_pilot_status": {
                "tool": "business_card_watchdog_live_pilot_status",
                "arguments": {"run_id": selected_run_id, "write": False}
                if selected_run_id
                else {"run_id": "<run-id>", "write": False},
            },
            "live_pilot_handoff": {
                "tool": "business_card_watchdog_live_pilot_handoff",
                "arguments": {"run_id": selected_run_id, "write": False}
                if selected_run_id
                else {"run_id": "<run-id>", "write": False},
            },
            "live_pilot_approval_packet": {
                "tool": "business_card_watchdog_live_pilot_approval_packet",
                "arguments": {"run_id": selected_run_id} if selected_run_id else {"run_id": "<run-id>"},
            },
            "live_pilot_validate_response": {
                "tool": "business_card_watchdog_live_pilot_operator_response_validation",
                "arguments": {"run_id": selected_run_id, "response": "<operator-response>"}
                if selected_run_id
                else {"run_id": "<run-id>", "response": "<operator-response>"},
            },
            "selected_live_target_preflight": {
                "tool": "business_card_watchdog_selected_live_target_preflight",
                "arguments": {"run_id": selected_run_id, "response": "<operator-response>"}
                if selected_run_id
                else {"run_id": "<run-id>", "response": "<operator-response>"},
            },
            "selected_target_approval_boundary": {
                "tool": "business_card_watchdog_selected_target_approval_boundary",
                "arguments": {
                    "run_id": selected_run_id,
                    "operator": "<operator>",
                    "response": "<operator-response>",
                    "write": False,
                }
                if selected_run_id
                else {
                    "run_id": "<run-id>",
                    "operator": "<operator>",
                    "response": "<operator-response>",
                    "write": False,
                },
            },
            "selected_target_command_copy_packet": {
                "tool": "business_card_watchdog_selected_target_command_copy_packet",
                "arguments": {
                    "run_id": selected_run_id,
                    "operator": "<operator>",
                    "response": "<operator-response>",
                    "acknowledgement": "<operator-acknowledgement>",
                }
                if selected_run_id
                else {
                    "run_id": "<run-id>",
                    "operator": "<operator>",
                    "response": "<operator-response>",
                    "acknowledgement": "<operator-acknowledgement>",
                },
            },
            "selected_live_target_preview": {
                "tool": "business_card_watchdog_selected_live_target_artifact_preview",
                "arguments": {"run_id": selected_run_id, "response": "<operator-response>"}
                if selected_run_id
                else {"run_id": "<run-id>", "response": "<operator-response>"},
            },
            "selected_live_target_from_response": {
                "tool": "business_card_watchdog_selected_live_target_from_response",
                "arguments": {"run_id": selected_run_id, "response": "<operator-response>"}
                if selected_run_id
                else {"run_id": "<run-id>", "response": "<operator-response>"},
            },
            "selected_live_target_handoff_from_response": {
                "tool": "business_card_watchdog_selected_live_target_handoff_from_response",
                "arguments": {"run_id": selected_run_id, "response": "<operator-response>", "write_audit": False}
                if selected_run_id
                else {"run_id": "<run-id>", "response": "<operator-response>", "write_audit": False},
            },
            "lookup_smoke_handoff_from_response": {
                "tool": "business_card_watchdog_lookup_smoke_handoff_from_response",
                "arguments": {
                    "run_id": selected_run_id,
                    "response": "<operator-response>",
                    "write_handoff": False,
                }
                if selected_run_id
                else {"run_id": "<run-id>", "response": "<operator-response>", "write_handoff": False},
            },
            "selected_lookup_smoke_execution_packet_from_response": {
                "tool": "business_card_watchdog_selected_lookup_smoke_execution_packet_from_response",
                "arguments": {
                    "run_id": selected_run_id,
                    "response": "<operator-response>",
                    "execute_selected_lookup_smoke": False,
                }
                if selected_run_id
                else {
                    "run_id": "<run-id>",
                    "response": "<operator-response>",
                    "execute_selected_lookup_smoke": False,
                },
            },
            "selected_write_pilot_execution_packet_from_response": {
                "tool": "business_card_watchdog_selected_write_pilot_execution_packet_from_response",
                "arguments": {
                    "run_id": selected_run_id,
                    "response": "<operator-response>",
                    "execute_write_pilot": False,
                }
                if selected_run_id
                else {
                    "run_id": "<run-id>",
                    "response": "<operator-response>",
                    "execute_write_pilot": False,
                },
            },
            "selected_readback_pilot_execution_packet_from_response": {
                "tool": "business_card_watchdog_selected_readback_pilot_execution_packet_from_response",
                "arguments": {
                    "run_id": selected_run_id,
                    "response": "<operator-response>",
                    "execute_readback_pilot": False,
                }
                if selected_run_id
                else {
                    "run_id": "<run-id>",
                    "response": "<operator-response>",
                    "execute_readback_pilot": False,
                },
            },
            "live_pilot_closeout_packet_from_response": {
                "tool": "business_card_watchdog_live_pilot_closeout_packet_from_response",
                "arguments": {
                    "run_id": selected_run_id,
                    "response": "<operator-response>",
                    "write_closeout": False,
                }
                if selected_run_id
                else {
                    "run_id": "<run-id>",
                    "response": "<operator-response>",
                    "write_closeout": False,
                },
            },
            "live_pilot_operator_workflow_packet_from_response": {
                "tool": "business_card_watchdog_live_pilot_operator_workflow_packet_from_response",
                "arguments": {"run_id": selected_run_id, "response": "<operator-response>"}
                if selected_run_id
                else {"run_id": "<run-id>", "response": "<operator-response>"},
            },
            "live_pilot_operator_rehearsal_from_response": {
                "tool": "business_card_watchdog_live_pilot_operator_rehearsal_from_response",
                "arguments": {"run_id": selected_run_id, "response": "<operator-response>"}
                if selected_run_id
                else {"run_id": "<run-id>", "response": "<operator-response>"},
            },
            "live_pilot_readiness_export_from_response": {
                "tool": "business_card_watchdog_live_pilot_readiness_export_from_response",
                "arguments": {"run_id": selected_run_id, "response": "<operator-response>", "write": True}
                if selected_run_id
                else {"run_id": "<run-id>", "response": "<operator-response>", "write": True},
            },
            "live_pilot_execution_checklist_from_response": {
                "tool": "business_card_watchdog_live_pilot_execution_checklist_from_response",
                "arguments": {"run_id": selected_run_id, "response": "<operator-response>"}
                if selected_run_id
                else {"run_id": "<run-id>", "response": "<operator-response>"},
            },
            "live_pilot_command_copy_packet_from_response": {
                "tool": "business_card_watchdog_live_pilot_command_copy_packet_from_response",
                "arguments": {
                    "run_id": selected_run_id,
                    "response": "<operator-response>",
                    "acknowledgement": "<operator-acknowledgement>",
                }
                if selected_run_id
                else {
                    "run_id": "<run-id>",
                    "response": "<operator-response>",
                    "acknowledgement": "<operator-acknowledgement>",
                },
            },
        },
        "safe_next_actions": [
            {
                "action": "inspect_runtime_readiness",
                "command": "runtime-readiness --json",
                "safe_to_auto_continue": True,
                "requires_explicit_operator_action": False,
            },
            {
                "action": "inspect_service_recovery",
                "command": (
                    f"service recovery --run-id {selected_run_id} --json"
                    if selected_run_id
                    else "service recovery --json"
                ),
                "safe_to_auto_continue": True,
                "requires_explicit_operator_action": False,
            },
            {
                "action": "inspect_review_queue" if selected_run_id else "inspect_runs",
                "command": (
                    f"reviews list --run-id {selected_run_id} --state all --json"
                    if selected_run_id
                    else "runs list --json"
                ),
                "safe_to_auto_continue": True,
                "requires_explicit_operator_action": False,
            },
            {
                "action": "inspect_live_pilot_status" if selected_run_id else "inspect_runs",
                "command": (
                    f"runs live-pilot-status {selected_run_id} --no-write --json"
                    if selected_run_id
                    else "runs list --json"
                ),
                "safe_to_auto_continue": True,
                "requires_explicit_operator_action": False,
            },
            {
                "action": "inspect_live_pilot_handoff" if selected_run_id else "inspect_runs",
                "command": (
                    f"runs live-pilot-handoff {selected_run_id} --no-write --json"
                    if selected_run_id
                    else "runs list --json"
                ),
                "safe_to_auto_continue": True,
                "requires_explicit_operator_action": False,
            },
            {
                "action": "run_fixture_review_routing_drill",
                "command": "drills review-routing --json",
                "safe_to_auto_continue": True,
                "requires_explicit_operator_action": False,
            },
        ],
        "explicit_stop_conditions": [
            "Do not process private SyncThing images from the operator dashboard.",
            "Do not run public-web search or paid API enrichment from the operator dashboard.",
            "Do not run live GWS/Odollo/Odoo lookup, write, or readback without selected target approval.",
        ],
        "writes_attempted": 0,
        "network_calls_made": 0,
    }



def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _pilot_command_sequence_summary(sequence: dict[str, Any]) -> dict[str, Any]:
    next_safe = dict(sequence.get("next_safe_inspection_step") or {})
    next_explicit = dict(sequence.get("next_explicit_operator_step") or {})
    return {
        "schema": "business-card-watchdog.pilot-command-sequence-summary.v1",
        "step_count": _to_int(sequence.get("step_count")),
        "safe_inspection_step_count": _to_int(sequence.get("safe_inspection_step_count")),
        "explicit_operator_step_count": _to_int(sequence.get("explicit_operator_step_count")),
        "live_call_step_count": _to_int(sequence.get("live_call_step_count")),
        "sink_write_step_count": _to_int(sequence.get("sink_write_step_count")),
        "next_safe_inspection_step": next_safe.get("step"),
        "next_explicit_operator_step": next_explicit.get("step"),
        "execution_policy": sequence.get("execution_policy") or {},
    }


def _operator_dashboard_live_pilot_execution_packet(run_id: str, handoff: dict[str, Any]) -> dict[str, Any]:
    operator_entries = [
        entry
        for entry in list(handoff.get("entries") or [])
        if isinstance(entry, dict) and entry.get("operator_required")
    ]
    packet_entries: list[dict[str, Any]] = []
    for entry in operator_entries[:5]:
        sequence = dict(entry.get("pilot_command_sequence") or {})
        next_safe = dict(sequence.get("next_safe_inspection_step") or {})
        next_explicit = dict(sequence.get("next_explicit_operator_step") or {})
        commands = dict(entry.get("commands") or {})
        packet_entries.append(
            {
                "job_id": entry.get("job_id"),
                "next_action": entry.get("next_action"),
                "next_safe_step": next_safe.get("step"),
                "next_safe_command": next_safe.get("command") or commands.get("validate_operator_response_prefilled"),
                "next_explicit_step": next_explicit.get("step"),
                "next_explicit_command": next_explicit.get("command"),
                "operator_response_template": entry.get("operator_response_template"),
                "operator_prompt": entry.get("operator_prompt"),
                "forbidden_live_command_count": _to_int(sequence.get("live_call_step_count")),
                "forbidden_sink_write_command_count": _to_int(sequence.get("sink_write_step_count")),
            }
        )

    state = "operator_required" if operator_entries else "no_operator_required"
    return {
        "schema": "business-card-watchdog.operator-dashboard.live-pilot-execution-packet.v1",
        "run_id": run_id,
        "state": state,
        "operator_required_count": len(operator_entries),
        "entries": packet_entries,
        "next_safe_command": packet_entries[0]["next_safe_command"] if packet_entries else None,
        "next_explicit_operator_command": packet_entries[0]["next_explicit_command"] if packet_entries else None,
        "forbidden_live_or_sink_write_from_dashboard": True,
        "execution_policy": {
            "safe_to_auto_execute_next_safe_command": True,
            "requires_operator_before_explicit_command": True,
            "requires_operator_before_live_call": True,
            "requires_operator_before_sink_write": True,
            "do_not_run_live_or_sink_write_from_dashboard": True,
        },
        "stop_conditions": handoff.get("operator_stop_conditions") or [],
        "writes_attempted": 0,
        "network_calls_made": 0,
    }


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
