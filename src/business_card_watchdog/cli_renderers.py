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
