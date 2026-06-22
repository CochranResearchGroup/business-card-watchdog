from __future__ import annotations

import json
from typing import Any

from .ledger import RunLedger
from .models import utc_now


def build_review_route_readiness(
    business_service: Any,
    run_id: str,
    *,
    safe_next_actions: set[str],
    explicit_operator_actions: set[str],
    write: bool = True,
) -> dict[str, Any]:
    closeout = business_service.dry_run_closeout(run_id, write=False)
    handoff = business_service.dry_run_review_handoff(run_id, write=False)
    bundle = business_service.review_bundle(run_id=run_id, state="all", write=False)
    entries = list(bundle.get("entries") or [])
    rows: list[dict[str, Any]] = []
    counts = {
        "needs_review": 0,
        "ready_to_route": 0,
        "rejected_not_card": 0,
        "duplicate_risky": 0,
        "enrichment_pending": 0,
        "route_ready": 0,
        "safe_auto": 0,
        "explicit_operator": 0,
        "blocked": 0,
    }
    next_action_counts: dict[str, int] = {}
    for entry in entries:
        matrix = dict(entry.get("review_matrix") or {})
        next_action = dict(entry.get("next_action") or {})
        next_action_name = str(next_action.get("action") or matrix.get("next_action") or "none")
        next_action_counts[next_action_name] = next_action_counts.get(next_action_name, 0) + 1
        review_state = str(entry.get("state") or matrix.get("review_state") or "unknown")
        duplicate_state = str(matrix.get("duplicate_state") or "not_assessed")
        enrichment_state = str(matrix.get("enrichment_state") or "not_requested")
        route_state = str(matrix.get("route_state") or "not_planned")
        lookup_state = str(matrix.get("sink_lookup_state") or "not_started")
        rejected_not_card = review_state == "rejected_not_card"
        duplicate_risky = duplicate_state in {
            "strong_duplicate",
            "possible_duplicate",
            "needs_review",
            "matches_found",
        }
        enrichment_pending = enrichment_state in {"requested", "proposed"}
        if rejected_not_card:
            duplicate_risky = False
            enrichment_pending = False
        safe_auto = bool(next_action.get("safe_to_auto_continue"))
        explicit_operator = bool(next_action.get("requires_explicit_operator_action"))
        route_ready = (
            review_state == "ready_to_route"
            and not duplicate_risky
            and not enrichment_pending
            and next_action_name in safe_next_actions | explicit_operator_actions | {"none"}
        )
        blocked = review_state in {"needs_review", "failed"} or duplicate_risky or enrichment_pending
        counts["needs_review"] += int(review_state == "needs_review")
        counts["ready_to_route"] += int(review_state == "ready_to_route")
        counts["rejected_not_card"] += int(rejected_not_card)
        counts["duplicate_risky"] += int(duplicate_risky)
        counts["enrichment_pending"] += int(enrichment_pending)
        counts["route_ready"] += int(route_ready)
        counts["safe_auto"] += int(safe_auto)
        counts["explicit_operator"] += int(explicit_operator)
        counts["blocked"] += int(blocked)
        rows.append(
            {
                "run_id": run_id,
                "job_id": entry.get("job_id"),
                "state": review_state,
                "contact": matrix.get("contact") or {},
                "contact_source": matrix.get("contact_source"),
                "normalization_warning_count": matrix.get("normalization_warning_count", 0),
                "normalization_warning_fields": matrix.get("normalization_warning_fields") or [],
                "duplicate_state": duplicate_state,
                "duplicate_match_count": matrix.get("duplicate_match_count", 0),
                "duplicate_risky": duplicate_risky,
                "enrichment_state": enrichment_state,
                "enrichment_proposal_count": matrix.get("enrichment_proposal_count", 0),
                "enrichment_pending": enrichment_pending,
                "route_state": route_state,
                "planned_sinks": matrix.get("planned_sinks") or [],
                "sink_lookup_state": lookup_state,
                "sink_lookup_match_count": matrix.get("sink_lookup_match_count", 0),
                "route_ready": route_ready,
                "rejected_not_card": rejected_not_card,
                "non_card_review": entry.get("non_card_review"),
                "safe_to_auto_continue": safe_auto,
                "requires_explicit_operator_action": explicit_operator,
                "next_action": next_action,
                "commands": entry.get("commands") or {},
            }
        )
    blocked_reasons = list(closeout.get("blocked_reasons") or [])
    if blocked_reasons:
        state = "blocked"
    elif counts["blocked"]:
        state = "operator_review_required"
    elif counts["safe_auto"]:
        state = "ready_for_safe_agent_loop"
    elif counts["explicit_operator"]:
        state = "explicit_operator_required"
    else:
        state = "ready_for_live_pilot_inspection"
    commands = {
        "review_route_readiness": f"runs review-route-readiness {run_id} --json",
        "dry_run_closeout": f"runs dry-run-closeout {run_id} --json",
        "dry_run_review_handoff": f"runs dry-run-review-handoff {run_id} --json",
        "dry_run_safe_loop": f"runs dry-run-safe-loop {run_id} --limit 5 --json",
        "review_bundle": f"reviews bundle --run-id {run_id} --state all --json",
        "review_queue": f"reviews list --run-id {run_id} --state all --json",
        "next_actions": f"actions next --run-id {run_id} --json",
        "phase_report": f"runs phase-report {run_id} --json",
        "live_pilot_status": f"runs live-pilot-status {run_id} --no-write --json",
        "live_pilot_handoff": f"runs live-pilot-handoff {run_id} --no-write --json",
    }
    payload: dict[str, Any] = {
        "schema": "business-card-watchdog.review-route-readiness.v1",
        "generated_at": utc_now(),
        "state": state,
        "run_id": run_id,
        "closeout_state": closeout.get("state"),
        "handoff_state": handoff.get("state"),
        "blocked_reasons": blocked_reasons,
        "job_count": len(rows),
        "counts": counts,
        "next_action_counts": dict(sorted(next_action_counts.items())),
        "rows": rows,
        "private_sources_used": False,
        "public_web_search_used": False,
        "paid_enrichment_used": False,
        "live_sink_calls_made": False,
        "writes_attempted": _int(closeout.get("writes_attempted")),
        "network_calls_made": _int(closeout.get("network_calls_made")),
        "runtime_artifact_written": False,
        "readiness_path": None,
        "safe_next_actions": [
            {
                "action": "inspect_review_route_readiness",
                "command": commands["review_route_readiness"],
                "safe_to_auto_continue": True,
                "requires_explicit_operator_action": False,
            },
            {
                "action": "inspect_next_actions",
                "command": commands["next_actions"],
                "safe_to_auto_continue": True,
                "requires_explicit_operator_action": False,
            },
            {
                "action": "run_dry_run_safe_loop",
                "command": commands["dry_run_safe_loop"],
                "safe_to_auto_continue": counts["safe_auto"] > 0 and not counts["blocked"],
                "requires_explicit_operator_action": False,
            },
            {
                "action": "inspect_live_pilot_status",
                "command": commands["live_pilot_status"],
                "safe_to_auto_continue": True,
                "requires_explicit_operator_action": False,
            },
        ],
        "explicit_stop_conditions": [
            "This readiness report reads local dry-run review, duplicate, enrichment, and route artifacts only.",
            "Do not run public-web search or paid enrichment from this report.",
            "Do not execute live lookup, write, or readback from this report.",
            "Use selected-target and live-pilot gates before Google Contacts, Odoo, or Odollo calls.",
        ],
        "commands": commands,
    }
    if write:
        readiness_path = business_service.config.runs_dir / run_id / "review_route_readiness.json"
        payload["runtime_artifact_written"] = True
        payload["readiness_path"] = str(readiness_path)
        readiness_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        ledger = RunLedger(business_service.config.runs_dir / run_id)
        ledger.record_artifact(job_id="__run__", kind="review_route_readiness", path=readiness_path)
        ledger.record_event(
            "review_route_readiness_created",
            {
                "run_id": run_id,
                "state": state,
                "readiness_path": str(readiness_path),
                "job_count": len(rows),
                "writes_attempted": 0,
                "network_calls_made": 0,
            },
        )
    return payload


def build_lookup_selection_packet(
    business_service: Any,
    run_id: str,
    *,
    operator: str,
    sink: str | None = None,
    write: bool = True,
) -> dict[str, Any]:
    selected_sink = str(sink or "").strip()
    if selected_sink and selected_sink not in {"google_contacts", "odoo"}:
        raise ValueError("lookup selection packet requires sink google_contacts or odoo")
    if not operator.strip():
        raise ValueError("lookup selection packet requires an operator")
    readiness = business_service.review_route_readiness(run_id, write=False)
    route_ready_rows = [
        row
        for row in list(readiness.get("rows") or [])
        if isinstance(row, dict) and row.get("route_ready")
    ]
    packet_candidates: list[dict[str, Any]] = []
    for row in route_ready_rows:
        job_id = str(row.get("job_id") or "")
        if not job_id:
            continue
        candidate_sinks = [selected_sink] if selected_sink else business_service._lookup_selection_candidate_sinks(row)
        for candidate_sink in candidate_sinks:
            try:
                packet = business_service.live_selection_packet(
                    job_id=job_id,
                    run_id=run_id,
                    sink=candidate_sink,
                    operator=operator,
                    scope="lookup",
                    reason="run-level lookup selection packet prepared from review-route readiness",
                    write=False,
                )
            except (FileNotFoundError, ValueError) as exc:
                packet = {
                    "schema": "business-card-watchdog.live-selection-packet.v1",
                    "state": "blocked",
                    "run_id": run_id,
                    "job_id": job_id,
                    "sink": candidate_sink,
                    "operator": operator,
                    "scope": "lookup",
                    "blocked_reasons": [str(exc)],
                    "writes_attempted": 0,
                    "network_calls_made": 0,
                }
            packet_candidates.append(
                {
                    "run_id": run_id,
                    "job_id": job_id,
                    "sink": candidate_sink,
                    "row": row,
                    "packet_state": packet.get("state"),
                    "blocked_reasons": list(packet.get("blocked_reasons") or []),
                    "packet": packet,
                }
            )
    selected = next(
        (
            candidate
            for candidate in packet_candidates
            if dict(candidate.get("packet") or {}).get("state") == "ready_for_operator_approval"
        ),
        packet_candidates[0] if packet_candidates else None,
    )
    if selected is None:
        state = "blocked"
        blocked_reasons = ["no route-ready review row is available for lookup selection"]
        selected_packet = None
    else:
        selected_packet = dict(selected.get("packet") or {})
        blocked_reasons = list(selected_packet.get("blocked_reasons") or [])
        state = (
            "ready_for_operator_approval"
            if selected_packet.get("state") == "ready_for_operator_approval"
            else "packet_blocked"
        )
    commands = {
        "lookup_selection_packet": (
            f"runs lookup-selection-packet {run_id} --operator {operator}"
            + (f" --sink {selected_sink}" if selected_sink else "")
            + " --json"
        ),
        "review_route_readiness": f"runs review-route-readiness {run_id} --json",
        "dry_run_safe_loop": f"runs dry-run-safe-loop {run_id} --limit 5 --json",
        "live_selection_requirements": (
            f"live-selection-requirements --run-id {run_id}"
            + (f" --sink {selected_sink}" if selected_sink else "")
            + " --no-write --json"
        ),
        "live_pilot_status": f"runs live-pilot-status {run_id} --no-write --json",
        "live_pilot_handoff": f"runs live-pilot-handoff {run_id} --no-write --json",
    }
    if selected_packet:
        packet_commands = dict(selected_packet.get("commands") or {})
        commands.update(
            {
                "validate_operator_response": packet_commands.get("validate_operator_response"),
                "validate_operator_response_prefilled": packet_commands.get("validate_operator_response_prefilled"),
                "selected_target_audit": packet_commands.get("selected_target_audit"),
                "lookup_smoke_handoff": packet_commands.get("lookup_smoke_handoff"),
            }
        )
    payload: dict[str, Any] = {
        "schema": "business-card-watchdog.lookup-selection-packet.v1",
        "generated_at": utc_now(),
        "state": state,
        "run_id": run_id,
        "sink": selected_sink or None,
        "operator": operator,
        "scope": "lookup",
        "review_route_readiness_state": readiness.get("state"),
        "route_ready_count": len(route_ready_rows),
        "packet_candidate_count": len(packet_candidates),
        "selected": selected,
        "selected_packet": selected_packet,
        "blocked_reasons": blocked_reasons,
        "packet_candidates": [
            {
                "run_id": candidate.get("run_id"),
                "job_id": candidate.get("job_id"),
                "sink": candidate.get("sink"),
                "packet_state": candidate.get("packet_state"),
                "blocked_reasons": candidate.get("blocked_reasons"),
            }
            for candidate in packet_candidates
        ],
        "private_sources_used": False,
        "public_web_search_used": False,
        "paid_enrichment_used": False,
        "live_sink_calls_made": False,
        "creates_selected_live_target": False,
        "writes_attempted": 0,
        "network_calls_made": 0,
        "runtime_artifact_written": False,
        "packet_path": None,
        "commands": commands,
        "explicit_stop_conditions": [
            "This packet chooses a lookup-selection candidate from local review-route readiness only.",
            "This packet does not create selected_live_target.json.",
            "Validate the operator response before selecting a live target.",
            "Do not run live lookup, write, or readback from this packet.",
            "Do not process private SyncThing images, run public-web search, or call paid enrichment from this packet.",
        ],
    }
    if write:
        packet_path = business_service.config.runs_dir / run_id / "lookup_selection_packet.json"
        payload["runtime_artifact_written"] = True
        payload["packet_path"] = str(packet_path)
        packet_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        ledger = RunLedger(business_service.config.runs_dir / run_id)
        ledger.record_artifact(job_id="__run__", kind="lookup_selection_packet", path=packet_path)
        ledger.record_event(
            "lookup_selection_packet_created",
            {
                "run_id": run_id,
                "state": state,
                "sink": selected_sink or None,
                "operator": operator,
                "packet_path": str(packet_path),
                "writes_attempted": 0,
                "network_calls_made": 0,
            },
        )
    return payload


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
