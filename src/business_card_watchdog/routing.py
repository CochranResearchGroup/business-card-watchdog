from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import AppConfig
from .models import SinkDecision
from .sinks import canonical_contact_fingerprint

ROUTE_EXPLANATION_SCHEMA = "business-card-watchdog.route-explanation.v1"


def load_contact_spec(spec_path: Path | None) -> dict[str, Any]:
    if spec_path is None or not spec_path.exists():
        return {}
    return json.loads(spec_path.read_text(encoding="utf-8"))


def decide_sinks(config: AppConfig, spec: dict[str, Any]) -> SinkDecision:
    fingerprint = canonical_contact_fingerprint(spec)
    configured: list[str] = []
    if config.sink.google_contacts:
        configured.append("google_contacts")
    if config.sink.odoo:
        configured.append("odoo")
    explanation: dict[str, Any] = {
        "schema": ROUTE_EXPLANATION_SCHEMA,
        "fingerprint": fingerprint,
        "configured_sinks": configured,
        "matched_rules": [],
        "excluded_rules": [],
        "default_policy": "enabled_sinks",
        "route_context": _route_context(config, spec),
    }

    if not configured:
        return SinkDecision(
            sinks=[],
            reason="no sinks enabled in user config",
            dry_run=config.sink.dry_run,
            state="blocked",
            fingerprint=fingerprint,
            metadata={"route_explanation": explanation, "sink_eligibility": []},
        )

    for index, rule in enumerate(config.routing_rules):
        matched, reason = _rule_matches(config, spec, rule)
        rule_record = _rule_record(index, rule, reason=reason)
        if matched:
            sinks = [sink for sink in rule.get("sinks", []) if sink in configured]
            rule_record["eligible_sinks"] = sinks
            explanation["matched_rules"].append(rule_record)
            return SinkDecision(
                sinks=sinks,
                reason=reason,
                dry_run=config.sink.dry_run,
                state="dry_run" if config.sink.dry_run else "planned",
                fingerprint=fingerprint,
                matched_rule=dict(rule),
                metadata={
                    "route_explanation": explanation,
                    "sink_eligibility": _sink_eligibility(config, sinks=sinks, configured=configured),
                },
            )
        explanation["excluded_rules"].append(rule_record)

    return SinkDecision(
        sinks=configured,
        reason="default enabled sinks",
        dry_run=config.sink.dry_run,
        state="dry_run" if config.sink.dry_run else "planned",
        fingerprint=fingerprint,
        metadata={
            "route_explanation": explanation,
            "sink_eligibility": _sink_eligibility(config, sinks=configured, configured=configured),
        },
    )


def _rule_matches(config: AppConfig, spec: dict[str, Any], rule: dict[str, Any]) -> tuple[bool, str]:
    match_type = str(rule.get("match") or "")
    value = str(rule.get("value") or "")
    if match_type == "email_domain":
        domain = _email_domain(spec)
        matched = value in (domain, "*")
        return matched, f"matched email_domain={value}" if matched else f"email_domain={domain or '<missing>'} did not match {value}"
    if match_type == "organization":
        organization = str(spec.get("organization") or "").strip().lower()
        matched = bool(value) and value.lower() in {organization, "*"}
        return matched, f"matched organization={value}" if matched else f"organization={organization or '<missing>'} did not match {value}"
    if match_type == "source_folder":
        image_path = str(spec.get("_image_path") or spec.get("image_path") or "")
        matched = bool(value) and (value == "*" or value in image_path)
        return matched, f"matched source_folder={value}" if matched else f"source_path did not contain {value}"
    if match_type == "tenant":
        tenant = str(spec.get("tenant") or config.sink.odollo_tenant or "")
        matched = bool(value) and value in {tenant, "*"}
        return matched, f"matched tenant={value}" if matched else f"tenant={tenant or '<missing>'} did not match {value}"
    if match_type == "duplicate_state":
        state = str(spec.get("_duplicate_state") or "")
        matched = bool(value) and value in {state, "*"}
        return matched, f"matched duplicate_state={value}" if matched else f"duplicate_state={state or '<missing>'} did not match {value}"
    if match_type == "review_state":
        state = str(spec.get("_review_state") or "")
        matched = bool(value) and value in {state, "*"}
        return matched, f"matched review_state={value}" if matched else f"review_state={state or '<missing>'} did not match {value}"
    return False, f"unsupported route rule match={match_type}"


def _route_context(config: AppConfig, spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "email_domain": _email_domain(spec),
        "organization": str(spec.get("organization") or ""),
        "source_path": str(spec.get("_image_path") or spec.get("image_path") or ""),
        "tenant": str(spec.get("tenant") or config.sink.odollo_tenant or ""),
        "duplicate_state": str(spec.get("_duplicate_state") or ""),
        "review_state": str(spec.get("_review_state") or ""),
    }


def _rule_record(index: int, rule: dict[str, Any], *, reason: str) -> dict[str, Any]:
    return {
        "index": index,
        "rule": dict(rule),
        "reason": reason,
    }


def _sink_eligibility(config: AppConfig, *, sinks: list[str], configured: list[str]) -> list[dict[str, Any]]:
    selected = set(sinks)
    configured_set = set(configured)
    return [
        {
            "sink": sink,
            "configured": sink in configured_set,
            "route_eligible": sink in selected,
            "apply_enabled": _sink_apply_enabled(config, sink),
            "apply_approval_required": True,
            "reason": "selected by route policy"
            if sink in selected
            else "sink enabled but not selected by route policy"
            if sink in configured_set
            else "sink disabled in user config",
        }
        for sink in ("google_contacts", "odoo")
    ]


def _sink_apply_enabled(config: AppConfig, sink: str) -> bool:
    if sink == "google_contacts":
        return config.sink.google_contacts_apply_enabled
    if sink == "odoo":
        return config.sink.odoo_apply_enabled
    return False


def _email_domain(spec: dict[str, Any]) -> str:
    email = str(spec.get("email") or "")
    return email.split("@", 1)[1].lower() if "@" in email else ""
