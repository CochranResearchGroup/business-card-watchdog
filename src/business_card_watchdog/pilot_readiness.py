from __future__ import annotations

from typing import Any

from .models import utc_now


def build_pilot_readiness_report(
    business_service: Any,
    run_id: str,
    *,
    safe_next_actions: set[str],
    explicit_operator_actions: set[str],
) -> dict[str, Any]:
    run_summary = business_service.run_summary(run_id)
    phase_report = business_service.phase_report(run_id)
    review_bundle = business_service.review_bundle(run_id=run_id, state="all", write=False)
    next_actions = business_service.next_actions(
        run_id=run_id,
        limit=max(1000, _int(run_summary.get("job_count")) + 10),
    )
    next_by_job = {str(action.get("job_id") or ""): action for action in next_actions["actions"]}
    phase_by_job = {str(job.get("job_id") or ""): job for job in phase_report["jobs"]}
    entries = review_bundle["entries"]

    jobs: list[dict[str, Any]] = []
    counts = {
        "blocked": 0,
        "safe_auto_available": 0,
        "explicit_operator_required": 0,
        "ready_for_write_pilot": 0,
        "write_pilot_complete": 0,
        "readback_complete": 0,
        "pilot_report_complete": 0,
        "complete": 0,
    }
    blocking_reasons_by_job: dict[str, list[dict[str, Any]]] = {}
    ready_job_ids: list[str] = []
    blocked_job_ids: list[str] = []
    safe_auto_job_ids: list[str] = []
    explicit_action_job_ids: list[str] = []
    pilot_complete_job_ids: list[str] = []

    for entry in entries:
        job_id = str(entry.get("job_id") or "")
        next_action = next_by_job.get(job_id) or entry.get("next_action") or {}
        matrix = dict(entry.get("review_matrix") or {})
        sink_pilot_status = dict(entry.get("sink_pilot_status") or {})
        phase_job = phase_by_job.get(job_id) or {}
        phase_states = dict(phase_job.get("phase_states") or {})
        blocking_reasons = business_service._pilot_readiness_blocking_reasons(
            phase_states=phase_states,
            next_action=next_action,
        )
        readiness_state = business_service._pilot_readiness_state_for_job(
            phase_states=phase_states,
            next_action=next_action,
            blocking_reasons=blocking_reasons,
        )
        if blocking_reasons:
            counts["blocked"] += 1
            blocked_job_ids.append(job_id)
            blocking_reasons_by_job[job_id] = blocking_reasons
        if next_action.get("action") in safe_next_actions:
            counts["safe_auto_available"] += 1
            safe_auto_job_ids.append(job_id)
        if next_action.get("action") in explicit_operator_actions:
            counts["explicit_operator_required"] += 1
            explicit_action_job_ids.append(job_id)
        if next_action.get("action") == "execute_sink_write_pilot":
            counts["ready_for_write_pilot"] += 1
            ready_job_ids.append(job_id)
        if phase_states.get("write_pilot") == "complete":
            counts["write_pilot_complete"] += 1
        if phase_states.get("readback_pilot") == "complete":
            counts["readback_complete"] += 1
        if phase_states.get("pilot_report") == "complete":
            counts["pilot_report_complete"] += 1
            pilot_complete_job_ids.append(job_id)
        if readiness_state == "complete":
            counts["complete"] += 1

        jobs.append(
            {
                "job_id": job_id,
                "state": entry.get("state"),
                "image_path": entry.get("image_path"),
                "readiness_state": readiness_state,
                "next_action": next_action.get("action"),
                "next_action_reason": next_action.get("reason"),
                "safe_to_auto_continue": bool(sink_pilot_status.get("safe_to_auto_continue")),
                "requires_explicit_operator_action": bool(
                    sink_pilot_status.get("requires_explicit_operator_action")
                ),
                "blocking_reasons": blocking_reasons,
                "phase_states": phase_states,
                "review_matrix": matrix,
                "sink_pilot_status": sink_pilot_status,
                "artifact_kinds": entry.get("artifact_kinds") or [],
                "artifact_paths": {
                    kind: record.get("path")
                    for kind, record in (entry.get("artifacts") or {}).items()
                    if isinstance(record, dict) and record.get("path")
                },
                "commands": {
                    "review": (entry.get("commands") or {}).get("review"),
                    "next": (entry.get("commands") or {}).get("next"),
                    "show_job": (entry.get("commands") or {}).get("show_job"),
                },
            }
        )

    job_count = len(jobs)
    if job_count == 0:
        state = "empty"
    elif counts["complete"] == job_count:
        state = "complete"
    elif counts["ready_for_write_pilot"]:
        state = "ready_for_write_pilot"
    elif counts["explicit_operator_required"]:
        state = "explicit_operator_required"
    elif counts["blocked"]:
        state = "blocked"
    elif counts["safe_auto_available"]:
        state = "safe_auto_available"
    else:
        state = "in_progress"

    return {
        "schema": "business-card-watchdog.pilot-readiness-report.v1",
        "run_id": run_id,
        "created_at": utc_now(),
        "state": state,
        "job_count": job_count,
        "counts": counts,
        "ready_job_ids": ready_job_ids,
        "blocked_job_ids": blocked_job_ids,
        "safe_auto_job_ids": safe_auto_job_ids,
        "explicit_action_job_ids": explicit_action_job_ids,
        "pilot_complete_job_ids": pilot_complete_job_ids,
        "blocking_reasons_by_job": blocking_reasons_by_job,
        "phase_dashboard_summary": phase_report["dashboard_summary"],
        "review_workbook_preview": phase_report["review_workbook_preview"],
        "sink_pilot_summary": run_summary["sink_pilot_summary"],
        "enrichment_budget": run_summary["enrichment_budget"],
        "review_groups": review_bundle["groups"],
        "next_actions": next_actions["actions"],
        "stop_rules": phase_report["stop_rules"],
        "jobs": jobs,
        "commands": {
            "phase_report": f"runs phase-report {run_id}",
            "pilot_readiness": f"runs pilot-readiness {run_id}",
            "review_bundle": f"reviews bundle --run-id {run_id} --state all",
            "review_workbook": f"reviews workbook --run-id {run_id} --state all",
            "run_next_safe": f"actions run-next --run-id {run_id}",
            "live_pilot_handoff": f"runs live-pilot-handoff {run_id}",
        },
        "writes_attempted": 0,
        "network_calls_made": 0,
    }


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
