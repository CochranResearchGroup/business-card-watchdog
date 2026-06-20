from __future__ import annotations


def render_pilot_readiness_report_text(payload: dict[str, object]) -> str:
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


def render_review_route_readiness_text(payload: dict[str, object]) -> str:
    counts = dict(payload.get("counts") or {})
    action_counts = dict(payload.get("next_action_counts") or {})
    rows = payload.get("rows") or []
    commands = dict(payload.get("commands") or {})
    stop_conditions = payload.get("explicit_stop_conditions") or []
    lines = [
        f"Review-route readiness: {payload.get('state')}",
        f"Run: {payload.get('run_id')}",
        f"Closeout: {payload.get('closeout_state')}",
        f"Handoff: {payload.get('handoff_state')}",
        f"Jobs: {payload.get('job_count', 0)}",
        f"Needs review: {counts.get('needs_review', 0)}",
        f"Ready to route: {counts.get('ready_to_route', 0)}",
        f"Duplicate risky: {counts.get('duplicate_risky', 0)}",
        f"Enrichment pending: {counts.get('enrichment_pending', 0)}",
        f"Safe auto: {counts.get('safe_auto', 0)}",
        f"Explicit operator: {counts.get('explicit_operator', 0)}",
        "Observed: "
        f"writes={payload.get('writes_attempted', 0)} "
        f"network={payload.get('network_calls_made', 0)} "
        f"live_sinks={payload.get('live_sink_calls_made', False)}",
        f"Runtime artifact written: {payload.get('runtime_artifact_written', False)}",
    ]
    if payload.get("readiness_path"):
        lines.append(f"Readiness path: {payload.get('readiness_path')}")
    if action_counts:
        lines.append("Next action counts:")
        for action, count in sorted(action_counts.items()):
            lines.append(f" - {action}: {count}")
    row_entries = rows if isinstance(rows, list) else []
    lines.append(f"Rows: {len(row_entries)}")
    for row in row_entries[:10]:
        if isinstance(row, dict):
            next_action = dict(row.get("next_action") or {})
            lines.append(
                " - "
                f"{row.get('job_id')}: {row.get('state')} "
                f"dup={row.get('duplicate_state')} enrich={row.get('enrichment_state')} "
                f"route={row.get('route_state')} next={next_action.get('action')}"
            )
    lines.append("Commands:")
    for label, key in [
        ("Readiness", "review_route_readiness"),
        ("Safe loop", "dry_run_safe_loop"),
        ("Handoff", "dry_run_review_handoff"),
        ("Review bundle", "review_bundle"),
        ("Next actions", "next_actions"),
        ("Phase report", "phase_report"),
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


def render_lookup_selection_packet_text(payload: dict[str, object]) -> str:
    selected = dict(payload.get("selected") or {})
    selected_packet = dict(payload.get("selected_packet") or {})
    commands = dict(payload.get("commands") or {})
    blocked_reasons = payload.get("blocked_reasons") or []
    stop_conditions = payload.get("explicit_stop_conditions") or []
    lines = [
        f"Lookup selection packet: {payload.get('state')}",
        f"Run: {payload.get('run_id')}",
        f"Sink: {payload.get('sink') or 'auto'}",
        f"Operator: {payload.get('operator')}",
        f"Route-ready rows: {payload.get('route_ready_count', 0)}",
        f"Packet candidates: {payload.get('packet_candidate_count', 0)}",
        f"Selected job: {selected.get('job_id') or 'none'}",
        f"Selected sink: {selected.get('sink') or 'none'}",
        f"Selected packet: {selected_packet.get('state') or 'none'}",
        "Observed: "
        f"writes={payload.get('writes_attempted', 0)} "
        f"network={payload.get('network_calls_made', 0)} "
        f"live_sinks={payload.get('live_sink_calls_made', False)} "
        f"creates_selected_target={payload.get('creates_selected_live_target', False)}",
        f"Runtime artifact written: {payload.get('runtime_artifact_written', False)}",
    ]
    if payload.get("packet_path"):
        lines.append(f"Packet path: {payload.get('packet_path')}")
    blocked_rows = blocked_reasons if isinstance(blocked_reasons, list) else []
    if blocked_rows:
        lines.append("Blocked reasons:")
        for reason in blocked_rows:
            lines.append(f" - {reason}")
    lines.append("Commands:")
    for label, key in [
        ("Lookup selection packet", "lookup_selection_packet"),
        ("Review-route readiness", "review_route_readiness"),
        ("Live selection requirements", "live_selection_requirements"),
        ("Validate operator response", "validate_operator_response"),
        ("Validate prefilled response", "validate_operator_response_prefilled"),
        ("Selected target audit", "selected_target_audit"),
        ("Lookup smoke handoff", "lookup_smoke_handoff"),
    ]:
        command = commands.get(key)
        if command:
            lines.append(f" - {label}: {command}")
    stop_rows = stop_conditions if isinstance(stop_conditions, list) else []
    lines.append(f"Stop conditions: {len(stop_rows)}")
    for condition in stop_rows:
        lines.append(f" - {condition}")
    return "\n".join(lines) + "\n"
