from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import AppConfig
from .models import SinkDecision
from .sinks import canonical_contact_fingerprint


def load_contact_spec(spec_path: Path | None) -> dict[str, Any]:
    if spec_path is None or not spec_path.exists():
        return {}
    return json.loads(spec_path.read_text(encoding="utf-8"))


def decide_sinks(config: AppConfig, spec: dict[str, Any]) -> SinkDecision:
    fingerprint = canonical_contact_fingerprint(spec)
    configured = []
    if config.sink.google_contacts:
        configured.append("google_contacts")
    if config.sink.odoo:
        configured.append("odoo")

    if not configured:
        return SinkDecision(
            sinks=[],
            reason="no sinks enabled in user config",
            dry_run=config.sink.dry_run,
            state="blocked",
            fingerprint=fingerprint,
        )

    email = str(spec.get("email") or "")
    domain = email.split("@", 1)[1].lower() if "@" in email else ""
    for rule in config.routing_rules:
        if rule.get("match") == "email_domain" and rule.get("value") in (domain, "*"):
            sinks = [sink for sink in rule.get("sinks", []) if sink in configured]
            return SinkDecision(
                sinks=sinks,
                reason=f"matched email_domain={rule.get('value')}",
                dry_run=config.sink.dry_run,
                state="dry_run" if config.sink.dry_run else "planned",
                fingerprint=fingerprint,
                matched_rule=dict(rule),
            )

    return SinkDecision(
        sinks=configured,
        reason="default enabled sinks",
        dry_run=config.sink.dry_run,
        state="dry_run" if config.sink.dry_run else "planned",
        fingerprint=fingerprint,
    )
