from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal


SinkName = Literal["google_contacts", "odoo"]
SinkAdapterPhase = Literal["lookup", "write", "readback"]
ReadinessStatus = Literal["ready", "blocked"]
SINK_PLAN_SCHEMA = "business-card-watchdog.sink-plan.v1"
SINK_APPLY_PREFLIGHT_SCHEMA = "business-card-watchdog.sink-apply-preflight.v1"
SINK_LOOKUP_PLAN_SCHEMA = "business-card-watchdog.sink-lookup-plan.v1"
SINK_APPLY_DECISION_SCHEMA = "business-card-watchdog.sink-apply-decision.v1"
SINK_APPLY_RESULT_SCHEMA = "business-card-watchdog.sink-apply-result.v1"
SINK_ADAPTER_REQUEST_SCHEMA = "business-card-watchdog.sink-adapter-request.v1"
SINK_LOOKUP_PILOT_SCHEMA = "business-card-watchdog.sink-lookup-pilot.v1"
SINK_LOOKUP_RESULT_SCHEMA = "business-card-watchdog.sink-lookup-result.v1"


FINGERPRINT_FIELDS = (
    "full_name",
    "email",
    "phone",
    "organization",
    "title",
    "website",
    "notes",
)


@dataclass(frozen=True)
class SinkReadiness:
    sink: str
    status: ReadinessStatus
    reason: str
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def ready(self) -> bool:
        return self.status == "ready"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SinkPayload:
    sink: str
    state: str
    fingerprint: str
    serialization_key: str
    match_keys: dict[str, str]
    payload: dict[str, Any]
    readiness: SinkReadiness

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["readiness"] = self.readiness.to_dict()
        return data


def canonical_contact_fingerprint(spec: dict[str, Any]) -> str:
    canonical = {field: _normalize_value(spec.get(field)) for field in FINGERPRINT_FIELDS}
    body = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def build_sink_payloads(
    *,
    sinks: list[str],
    spec: dict[str, Any],
    dry_run: bool,
    apply_enabled: dict[str, bool] | None = None,
) -> list[SinkPayload]:
    fingerprint = canonical_contact_fingerprint(spec)
    apply_enabled = apply_enabled or {}
    return [
        SinkPayload(
            sink=sink,
            state="dry_run" if dry_run else ("ready" if readiness.ready else "blocked"),
            fingerprint=fingerprint,
            serialization_key=contact_serialization_key(spec, fingerprint),
            match_keys=_match_keys(spec, fingerprint),
            payload=_payload_for_sink(sink, spec, fingerprint),
            readiness=readiness,
        )
        for sink in sinks
        for readiness in [check_sink_readiness(sink, dry_run=dry_run, apply_enabled=apply_enabled.get(sink, False))]
    ]


def write_sink_payloads(path: Path, payloads: list[SinkPayload]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema": "business-card-watchdog.sink-payloads.v1",
                "payloads": [payload.to_dict() for payload in payloads],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def build_sink_plan(
    *,
    sinks: list[str],
    spec: dict[str, Any],
    dry_run: bool,
    reason: str,
    apply_enabled: dict[str, bool] | None = None,
) -> dict[str, Any]:
    payloads = build_sink_payloads(sinks=sinks, spec=spec, dry_run=dry_run, apply_enabled=apply_enabled)
    return {
        "schema": SINK_PLAN_SCHEMA,
        "state": "dry_run" if dry_run else ("ready" if all(payload.readiness.ready for payload in payloads) else "blocked"),
        "reason": reason,
        "dry_run": dry_run,
        "payloads": [payload.to_dict() for payload in payloads],
        "actions": [
            {
                "sink": payload.sink,
                "action": "plan_upsert",
                "state": payload.state,
                "match_keys": payload.match_keys,
                "serialization_key": payload.serialization_key,
                "readiness": payload.readiness.to_dict(),
            }
            for payload in payloads
        ],
    }


def build_sink_lookup_plan(
    *,
    sinks: list[str],
    spec: dict[str, Any],
    dry_run: bool,
    reason: str,
) -> dict[str, Any]:
    fingerprint = canonical_contact_fingerprint(spec)
    match_keys = _match_keys(spec, fingerprint)
    lookups = [
        {
            "sink": sink,
            "state": "dry_run" if dry_run else "blocked",
            "readiness": check_sink_lookup_readiness(sink, dry_run=dry_run).to_dict(),
            "match_keys": match_keys,
            "queries": _lookup_queries_for_sink(sink, match_keys),
        }
        for sink in sinks
    ]
    blocked = [lookup for lookup in lookups if lookup["readiness"]["status"] != "ready"]
    return {
        "schema": SINK_LOOKUP_PLAN_SCHEMA,
        "state": "dry_run" if dry_run else ("blocked" if blocked else "ready"),
        "reason": reason,
        "dry_run": dry_run,
        "network_calls_made": 0,
        "fingerprint": fingerprint,
        "lookups": lookups,
    }


def build_sink_apply_preflight(
    *,
    plan: dict[str, Any],
    apply: bool,
) -> dict[str, Any]:
    actions = list(plan.get("actions") or [])
    blocked_actions = [
        action
        for action in actions
        if action.get("readiness", {}).get("status") != "ready"
        or action.get("state") not in {"dry_run", "ready"}
    ]
    reasons = [
        str(action.get("readiness", {}).get("reason") or "sink action is not ready")
        for action in blocked_actions
    ]
    if apply:
        state = "blocked"
        reasons.append("live sink apply/readback is not implemented yet")
    elif blocked_actions:
        state = "blocked"
    else:
        state = "preview"
        reasons.append("apply flag not set; no live write attempted")

    return {
        "schema": SINK_APPLY_PREFLIGHT_SCHEMA,
        "state": state,
        "apply_requested": apply,
        "can_apply": False,
        "writes_attempted": 0,
        "network_calls_made": 0,
        "reason": "; ".join(dict.fromkeys(reason for reason in reasons if reason)),
        "plan_schema": plan.get("schema"),
        "plan_state": plan.get("state"),
        "job_id": plan.get("job_id"),
        "run_id": plan.get("run_id"),
        "actions": [
            {
                "sink": action.get("sink"),
                "action": "preflight_apply",
                "planned_action": action.get("action"),
                "planned_state": action.get("state"),
                "readiness": action.get("readiness", {}),
                "serialization_key": action.get("serialization_key"),
                "match_keys": action.get("match_keys", {}),
            }
            for action in actions
        ],
    }


def build_sink_apply_decision(
    *,
    preflight: dict[str, Any],
    decision: str,
    reviewer: str,
    reason: str = "",
) -> dict[str, Any]:
    if decision not in {"approve", "reject", "noop"}:
        raise ValueError("sink apply decision must be approve, reject, or noop")
    state = {
        "approve": "approved_for_apply",
        "reject": "rejected",
        "noop": "noop",
    }[decision]
    return {
        "schema": SINK_APPLY_DECISION_SCHEMA,
        "state": state,
        "decision": decision,
        "reviewer": reviewer,
        "reason": reason,
        "writes_attempted": 0,
        "network_calls_made": 0,
        "preflight_schema": preflight.get("schema"),
        "preflight_state": preflight.get("state"),
        "job_id": preflight.get("job_id"),
        "run_id": preflight.get("run_id"),
        "actions": [
            {
                "sink": action.get("sink"),
                "decision": decision,
                "planned_action": action.get("planned_action"),
                "serialization_key": action.get("serialization_key"),
                "match_keys": action.get("match_keys", {}),
            }
            for action in list(preflight.get("actions") or [])
        ],
    }


def build_sink_apply_result(
    *,
    preflight: dict[str, Any],
    decision: dict[str, Any],
    apply: bool,
    simulate: bool = False,
) -> dict[str, Any]:
    decision_value = str(decision.get("decision") or "")
    reasons: list[str] = []
    if not apply:
        state = "preview"
        reasons.append("apply flag not set; no live write attempted")
    elif decision_value != "approve":
        state = "blocked"
        reasons.append("sink apply requires an approved sink apply decision")
    elif simulate:
        state = "mock_applied"
        reasons.append("mock sink adapter produced readback evidence; no live write attempted")
    else:
        state = "blocked"
        reasons.append("live sink write/readback adapters are not implemented yet")
    actions = [
        {
            "sink": action.get("sink"),
            "state": state,
            "decision": decision_value,
            "planned_action": action.get("planned_action"),
            "serialization_key": action.get("serialization_key"),
            "write_attempted": False,
            "readback_attempted": False,
            "simulated": bool(simulate and state == "mock_applied"),
        }
        for action in list(preflight.get("actions") or [])
    ]
    return {
        "schema": SINK_APPLY_RESULT_SCHEMA,
        "state": state,
        "apply_requested": apply,
        "simulated": bool(simulate and state == "mock_applied"),
        "decision": decision_value,
        "writes_attempted": 0,
        "network_calls_made": 0,
        "reason": "; ".join(reasons),
        "preflight_schema": preflight.get("schema"),
        "preflight_state": preflight.get("state"),
        "decision_schema": decision.get("schema"),
        "decision_state": decision.get("state"),
        "job_id": preflight.get("job_id") or decision.get("job_id"),
        "run_id": preflight.get("run_id") or decision.get("run_id"),
        "readback": _mock_readback(actions) if simulate and state == "mock_applied" else [],
        "actions": actions,
    }


def build_sink_adapter_request(
    *,
    phase: SinkAdapterPhase,
    lookup_plan: dict[str, Any] | None = None,
    sink_plan: dict[str, Any] | None = None,
    apply_result: dict[str, Any] | None = None,
    sink_context: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    sink_context = sink_context or {}
    if phase == "lookup":
        source = lookup_plan or {}
        source_schema = source.get("schema")
        requests = [
            _lookup_adapter_request(lookup, context=sink_context.get(str(lookup.get("sink") or ""), {}))
            for lookup in list(source.get("lookups") or [])
        ]
    elif phase == "write":
        source = sink_plan or {}
        source_schema = source.get("schema")
        payloads = {payload.get("sink"): payload for payload in list(source.get("payloads") or [])}
        requests = [
            _write_adapter_request(
                action,
                payloads.get(action.get("sink"), {}),
                context=sink_context.get(str(action.get("sink") or ""), {}),
            )
            for action in list(source.get("actions") or [])
        ]
    elif phase == "readback":
        source = apply_result or {}
        source_schema = source.get("schema")
        readback_by_sink = {row.get("sink"): row for row in list(source.get("readback") or [])}
        requests = [
            _readback_adapter_request(
                action,
                readback_by_sink.get(action.get("sink"), {}),
                context=sink_context.get(str(action.get("sink") or ""), {}),
            )
            for action in list(source.get("actions") or [])
        ]
    else:
        raise ValueError("sink adapter phase must be lookup, write, or readback")

    return {
        "schema": SINK_ADAPTER_REQUEST_SCHEMA,
        "phase": phase,
        "state": "blocked",
        "status": "blocked",
        "reason": "live sink adapters require explicit implementation and operator approval",
        "requires_live_adapter": True,
        "network_calls_made": 0,
        "writes_attempted": 0,
        "source_schema": source_schema,
        "job_id": source.get("job_id"),
        "run_id": source.get("run_id"),
        "request_count": len(requests),
        "requests": requests,
    }


def build_sink_lookup_result(
    *,
    adapter_request: dict[str, Any],
    matches_by_sink: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    matches_by_sink = matches_by_sink or {}
    results = [
        _lookup_result_for_request(request, matches_by_sink.get(str(request.get("sink") or ""), []))
        for request in list(adapter_request.get("requests") or [])
        if request.get("phase") == "lookup"
    ]
    match_count = sum(len(result["matches"]) for result in results)
    return {
        "schema": SINK_LOOKUP_RESULT_SCHEMA,
        "state": "possible_duplicate" if match_count else "no_match",
        "status": "fixture_matches" if match_count else "not_executed",
        "reason": (
            "fixture-provided downstream matches require review"
            if match_count
            else "live downstream lookup adapter was not invoked"
        ),
        "source_schema": adapter_request.get("schema"),
        "job_id": adapter_request.get("job_id"),
        "run_id": adapter_request.get("run_id"),
        "requires_live_adapter": True,
        "duplicate_review_required": bool(match_count),
        "network_calls_made": 0,
        "writes_attempted": 0,
        "match_count": match_count,
        "results": results,
    }


def build_sink_lookup_pilot(
    *,
    adapter_request: dict[str, Any],
    sink: str,
    approved_by: str,
    matches: list[dict[str, Any]] | None = None,
    simulate: bool = True,
    execution: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not approved_by.strip():
        raise ValueError("sink lookup pilot requires approved_by")
    requests = [
        request
        for request in list(adapter_request.get("requests") or [])
        if request.get("phase") == "lookup" and request.get("sink") == sink
    ]
    if not requests:
        raise ValueError(f"sink lookup pilot request not found for sink: {sink}")
    if not simulate and execution is None:
        raise ValueError("live sink lookup execution requires adapter execution evidence")
    matches = matches or []
    network_calls_made = int((execution or {}).get("network_calls_made") or 0)
    return {
        "schema": SINK_LOOKUP_PILOT_SCHEMA,
        "state": ("simulated_match" if matches else "simulated_no_match")
        if simulate
        else ("read_only_match" if matches else "read_only_no_match"),
        "status": "mock_read_only_lookup_completed" if simulate else "read_only_lookup_completed",
        "reason": (
            "mock read-only lookup pilot completed; no downstream writes attempted"
            if simulate
            else "read-only lookup adapter completed; no downstream writes attempted"
        ),
        "source_schema": adapter_request.get("schema"),
        "source_phase": adapter_request.get("phase"),
        "job_id": adapter_request.get("job_id"),
        "run_id": adapter_request.get("run_id"),
        "sink": sink,
        "approved_by": approved_by,
        "simulated": bool(simulate),
        "read_only": True,
        "requires_live_adapter": True,
        "network_calls_made": network_calls_made,
        "writes_attempted": 0,
        "request": requests[0],
        "match_count": len(matches),
        "execution": execution or {},
        "matches": [
            {
                "resource_id": str(match.get("resource_id") or ""),
                "confidence": float(match.get("confidence", 0)),
                "basis": list(match.get("basis") or []),
                "display": str(match.get("display") or ""),
                "raw": dict(match.get("raw") or {}),
            }
            for match in matches
        ],
        "result_schema": SINK_LOOKUP_RESULT_SCHEMA,
    }


def check_sink_readiness(
    sink: str,
    *,
    dry_run: bool,
    apply_enabled: bool = False,
    google_contacts_profile: str = "",
    odollo_tenant: str = "",
) -> SinkReadiness:
    if dry_run:
        return SinkReadiness(
            sink=sink,
            status="ready",
            reason="dry-run payload generation does not require external credentials",
        )
    if not apply_enabled:
        return SinkReadiness(
            sink=sink,
            status="blocked",
            reason="live sink apply is disabled in user config",
            details={"apply_enabled": False},
        )

    if sink == "google_contacts":
        if not google_contacts_profile.strip():
            return SinkReadiness(
                sink=sink,
                status="blocked",
                reason="missing sink.google_contacts_profile for live Google Contacts apply",
                details={"config_key": "sink.google_contacts_profile"},
            )
        if shutil.which("gws") is None:
            return SinkReadiness(
                sink=sink,
                status="blocked",
                reason="gws CLI not found; cannot verify Google Contacts readiness",
                details={"profile": google_contacts_profile},
            )
        gws_details = _gws_local_readiness_details(profile=google_contacts_profile)
        if not gws_details["auth_evidence_present"]:
            return SinkReadiness(
                sink=sink,
                status="blocked",
                reason="missing Google Workspace auth evidence for live Contacts apply",
                details=gws_details,
            )
        if not gws_details["people_discovery_cache_present"]:
            return SinkReadiness(
                sink=sink,
                status="blocked",
                reason="missing gws People API discovery cache for live Contacts apply",
                details=gws_details,
            )
        return SinkReadiness(
            sink=sink,
            status="blocked",
            reason="gws local readiness evidence exists; live Google Contacts write/readback gate is not implemented yet",
            details=gws_details,
        )

    if sink == "odoo":
        if not odollo_tenant.strip():
            return SinkReadiness(
                sink=sink,
                status="blocked",
                reason="missing sink.odollo_tenant for live Odoo/Odollo apply",
                details={"config_key": "sink.odollo_tenant"},
            )
        odollo_details = _odollo_local_readiness_details(tenant=odollo_tenant)
        if not odollo_details["config_present"]:
            return SinkReadiness(
                sink=sink,
                status="blocked",
                reason="missing Odollo user config for live Odoo/Odollo apply",
                details=odollo_details,
            )
        if not odollo_details["tenant_home_present"]:
            return SinkReadiness(
                sink=sink,
                status="blocked",
                reason="missing Odollo tenant home for live Odoo/Odollo apply",
                details=odollo_details,
            )
        if not odollo_details["state_evidence_present"]:
            return SinkReadiness(
                sink=sink,
                status="blocked",
                reason="missing Odollo tenant state evidence for live Odoo/Odollo apply",
                details=odollo_details,
            )
        return SinkReadiness(
            sink=sink,
            status="blocked",
            reason="Odollo local readiness evidence exists; live Odoo/Odollo tenant readiness gate is not implemented yet",
            details=odollo_details,
        )

    return SinkReadiness(sink=sink, status="blocked", reason=f"unknown sink: {sink}")


def _gws_local_readiness_details(*, profile: str) -> dict[str, Any]:
    config_dir = Path(os.environ.get("GOOGLE_WORKSPACE_CLI_CONFIG_DIR", Path.home() / ".config" / "gws")).expanduser()
    auth_files = {
        "credentials": config_dir / "credentials.enc",
        "token_cache": config_dir / "token_cache.json",
        "auth_state": config_dir / "auth_state.json",
    }
    discovery_cache = config_dir / "cache" / "people_v1.json"
    return {
        "profile": profile,
        "gws_path": shutil.which("gws"),
        "config_dir": str(config_dir),
        "auth_evidence_present": any(path.exists() for path in auth_files.values()),
        "auth_evidence_files": {name: path.exists() for name, path in auth_files.items()},
        "people_discovery_cache_present": discovery_cache.exists(),
        "required_scopes": [
            "https://www.googleapis.com/auth/contacts",
            "https://www.googleapis.com/auth/contacts.readonly",
        ],
        "scope_evidence": "not verified without a live Google API call",
        "dry_run_probe": {
            "lookup": "gws people people searchContacts --dry-run --params ...",
            "write": "gws people people createContact --dry-run --json ...",
            "network_calls_made": 0,
        },
    }


def _odollo_local_readiness_details(*, tenant: str) -> dict[str, Any]:
    home = Path(os.environ.get("ODOLLO_HOME", Path.home() / ".odollo")).expanduser()
    tenant_home = home / "tenants" / tenant
    state_candidates = [
        home / f"{tenant}.sqlite",
        home / f"{tenant}.sqlite3",
        home / f"{tenant}.db",
        home / "state.sqlite",
        home / "state.sqlite3",
        home / "state.db",
    ]
    return {
        "tenant": tenant,
        "odollo_home": str(home),
        "config_path": str(home / "odollo.yml"),
        "config_present": (home / "odollo.yml").exists(),
        "tenant_home": str(tenant_home),
        "tenant_home_present": tenant_home.exists(),
        "tenant_resources_present": (tenant_home / "resources").exists(),
        "tenant_artifacts_present": (tenant_home / "artifacts").exists(),
        "tenant_actions_log_present": (tenant_home / "actions.ndjson").exists(),
        "state_evidence_present": any(path.exists() for path in state_candidates),
        "state_candidates": {path.name: path.exists() for path in state_candidates},
        "live_probe": {
            "source": "odollo.core.odoo_readiness.odoo_readiness_report",
            "network_calls_made": 0,
            "status": "not_invoked_without_operator_approval",
        },
    }


def check_sink_lookup_readiness(sink: str, *, dry_run: bool) -> SinkReadiness:
    if dry_run:
        return SinkReadiness(
            sink=sink,
            status="ready",
            reason="dry-run lookup planning does not call downstream sinks",
        )
    if sink == "google_contacts":
        if shutil.which("gws") is None:
            return SinkReadiness(
                sink=sink,
                status="blocked",
                reason="gws CLI not found; cannot perform Google Contacts lookup",
            )
        return SinkReadiness(
            sink=sink,
            status="blocked",
            reason="live Google Contacts lookup adapter is not implemented yet",
        )
    if sink == "odoo":
        return SinkReadiness(
            sink=sink,
            status="blocked",
            reason="live Odoo/Odollo lookup adapter is not implemented yet",
        )
    return SinkReadiness(sink=sink, status="blocked", reason=f"unknown sink: {sink}")


def contact_serialization_key(spec: dict[str, Any], fingerprint: str | None = None) -> str:
    fingerprint = fingerprint or canonical_contact_fingerprint(spec)
    for field in ("email", "phone", "full_name"):
        value = _normalize_value(spec.get(field)).lower()
        if value:
            return f"{field}:{value}"
    return f"fingerprint:{fingerprint}"


def _payload_for_sink(sink: str, spec: dict[str, Any], fingerprint: str) -> dict[str, Any]:
    common = {
        "fingerprint": fingerprint,
        "full_name": _normalize_value(spec.get("full_name")),
        "email": _normalize_value(spec.get("email")),
        "phone": _normalize_value(spec.get("phone")),
        "organization": _normalize_value(spec.get("organization")),
        "title": _normalize_value(spec.get("title")),
        "website": _normalize_value(spec.get("website")),
        "notes": _normalize_value(spec.get("notes")),
    }
    contact_points = _contact_points_from_spec(spec)
    if contact_points:
        common["contact_points"] = contact_points
    if sink == "odoo":
        return {
            "model": "res.partner",
            "operation": "upsert",
            "values": common,
        }
    return {
        "operation": "upsert_contact",
        "values": common,
    }


def _match_keys(spec: dict[str, Any], fingerprint: str) -> dict[str, str]:
    keys = {"fingerprint": fingerprint}
    for field in ("email", "phone", "full_name"):
        value = _normalize_value(spec.get(field))
        if value:
            keys[field] = value
    return keys


def _lookup_queries_for_sink(sink: str, match_keys: dict[str, str]) -> list[dict[str, Any]]:
    if sink == "odoo":
        return [
            {
                "model": "res.partner",
                "operation": "search_read",
                "field": field,
                "value": value,
            }
            for field, value in match_keys.items()
            if field in {"email", "phone", "full_name", "fingerprint"}
        ]
    return [
        {
            "operation": "lookup_contact",
            "field": field,
            "value": value,
        }
        for field, value in match_keys.items()
        if field in {"email", "phone", "full_name", "fingerprint"}
    ]


def _lookup_adapter_request(lookup: dict[str, Any], *, context: dict[str, Any]) -> dict[str, Any]:
    sink = str(lookup.get("sink") or "")
    request = _adapter_base(sink=sink, phase="lookup")
    match_keys = lookup.get("match_keys", {})
    request.update(
        {
            "operation": "lookup_contact",
            "match_keys": match_keys,
            "queries": list(lookup.get("queries") or []),
        }
    )
    if sink == "odoo":
        request.update(_odollo_lookup_contract(match_keys=match_keys, tenant=str(context.get("tenant") or "")))
    else:
        request.update(_gws_lookup_contract(match_keys=match_keys, profile=str(context.get("profile") or "")))
    return request


def _write_adapter_request(action: dict[str, Any], payload: dict[str, Any], *, context: dict[str, Any]) -> dict[str, Any]:
    sink = str(action.get("sink") or "")
    request = _adapter_base(sink=sink, phase="write")
    values = dict(payload.get("payload", {}).get("values") or {})
    request.update(
        {
            "operation": "upsert_contact",
            "planned_action": action.get("action"),
            "serialization_key": action.get("serialization_key"),
            "match_keys": action.get("match_keys", {}),
            "payload": payload.get("payload", {}),
        }
    )
    if sink == "odoo":
        request.update(_odollo_write_contract(values=values, tenant=str(context.get("tenant") or "")))
    else:
        request.update(_gws_write_contract(values=values, profile=str(context.get("profile") or "")))
    return request


def _readback_adapter_request(action: dict[str, Any], readback: dict[str, Any], *, context: dict[str, Any]) -> dict[str, Any]:
    sink = str(action.get("sink") or "")
    request = _adapter_base(sink=sink, phase="readback")
    resource_id = readback.get("resource_id")
    request.update(
        {
            "operation": "readback_contact",
            "serialization_key": action.get("serialization_key"),
            "resource_id": resource_id,
            "simulated_readback": bool(readback.get("simulated", False)),
        }
    )
    if sink == "odoo":
        request.update(_odollo_readback_contract(resource_id=resource_id, tenant=str(context.get("tenant") or "")))
    else:
        request.update(_gws_readback_contract(resource_id=resource_id, profile=str(context.get("profile") or "")))
    return request


def _adapter_base(*, sink: str, phase: SinkAdapterPhase) -> dict[str, Any]:
    return {
        "sink": sink,
        "phase": phase,
        "status": "blocked",
        "requires_live_adapter": True,
        "network_calls_made": 0,
        "writes_attempted": 0,
        "reason": "adapter request prepared only; no live adapter invoked",
    }


def _gws_lookup_contract(*, match_keys: dict[str, str], profile: str) -> dict[str, Any]:
    query_terms = [match_keys[field] for field in ("email", "phone", "full_name") if match_keys.get(field)]
    return {
        "adapter": "gws.people",
        "profile": {
            "source": "user_config",
            "config_key": "sink.google_contacts_profile",
            "name": profile,
            "required_for_live": True,
        },
        "api": "people.googleapis.com",
        "resource": "people.connections",
        "method": "people.searchContacts",
        "gws_command": ["gws", "people", "people", "searchContacts"],
        "request_body": {
            "query": " ".join(query_terms),
            "readMask": "names,emailAddresses,phoneNumbers,organizations,metadata,biographies",
            "sources": ["READ_SOURCE_TYPE_CONTACT"],
        },
        "match_strategy": ["email", "phone", "full_name", "fingerprint_note"],
        "expected_response_keys": ["results.person.resourceName", "results.person.names"],
    }


def _gws_write_contract(*, values: dict[str, Any], profile: str) -> dict[str, Any]:
    return {
        "adapter": "gws.people",
        "profile": {
            "source": "user_config",
            "config_key": "sink.google_contacts_profile",
            "name": profile,
            "required_for_live": True,
        },
        "api": "people.googleapis.com",
        "resource": "people.connections",
        "method": "people.createContact_or_people.updateContact",
        "gws_command": ["gws", "people", "people", "createContact"],
        "request_body": {
            "names": [{"displayName": values.get("full_name")}] if values.get("full_name") else [],
            "emailAddresses": [{"value": values.get("email")}] if values.get("email") else [],
            "phoneNumbers": [{"value": values.get("phone")}] if values.get("phone") else [],
            "organizations": [
                {
                    "name": values.get("organization"),
                    "title": values.get("title"),
                }
            ]
            if values.get("organization") or values.get("title")
            else [],
            "biographies": [{"value": values.get("notes")}] if values.get("notes") else [],
            "urls": _gws_urls(values),
        },
        "idempotency": {
            "lookup_required_before_write": True,
            "duplicate_policy": "noop_or_update_existing",
        },
        "expected_response_keys": ["resourceName", "etag"],
    }


def _gws_readback_contract(*, resource_id: Any, profile: str) -> dict[str, Any]:
    return {
        "adapter": "gws.people",
        "profile": {
            "source": "user_config",
            "config_key": "sink.google_contacts_profile",
            "name": profile,
            "required_for_live": True,
        },
        "api": "people.googleapis.com",
        "resource": "people.connections",
        "method": "people.get",
        "gws_command": ["gws", "people", "people", "get"],
        "request_body": {
            "resourceName": resource_id,
            "personFields": "names,emailAddresses,phoneNumbers,organizations,metadata,biographies",
        },
        "expected_response_keys": ["resourceName", "names", "emailAddresses"],
    }


def _odollo_lookup_contract(*, match_keys: dict[str, str], tenant: str) -> dict[str, Any]:
    return {
        "adapter": "odollo.odoo",
        "tenant": {
            "source": "user_config",
            "config_key": "sink.odollo_tenant",
            "name": tenant,
            "required_for_live": True,
        },
        "model": "res.partner",
        "method": "search_read",
        "domain": _odoo_lookup_domain(match_keys),
        "fields": ["id", "name", "email", "phone", "mobile", "parent_id", "company_name", "function"],
        "limit": 10,
        "match_strategy": ["email", "phone", "full_name", "fingerprint_contact_point"],
        "contact_point_plan": {
            "enabled": True,
            "mode": "lookup_only",
            "overwrite_canonical_slots": False,
        },
        "expected_response_keys": ["id", "name"],
    }


def _odollo_write_contract(*, values: dict[str, Any], tenant: str) -> dict[str, Any]:
    return {
        "adapter": "odollo.odoo",
        "tenant": {
            "source": "user_config",
            "config_key": "sink.odollo_tenant",
            "name": tenant,
            "required_for_live": True,
        },
        "model": "res.partner",
        "method": "create_or_write",
        "values": {
            "name": values.get("full_name") or values.get("organization"),
            "email": values.get("email"),
            "phone": values.get("phone"),
            "function": values.get("title"),
            "website": values.get("website"),
            "comment": values.get("notes"),
            "company_name": values.get("organization"),
        },
        "contact_point_plan": {
            "enabled": True,
            "mode": "additive_after_partner_write",
            "overwrite_canonical_slots": False,
            "points": _odollo_contact_points(values),
        },
        "idempotency": {
            "lookup_required_before_write": True,
            "duplicate_policy": "noop_or_update_existing",
        },
        "expected_response_keys": ["id"],
    }


def _odollo_readback_contract(*, resource_id: Any, tenant: str) -> dict[str, Any]:
    return {
        "adapter": "odollo.odoo",
        "tenant": {
            "source": "user_config",
            "config_key": "sink.odollo_tenant",
            "name": tenant,
            "required_for_live": True,
        },
        "model": "res.partner",
        "method": "read",
        "ids": [_odoo_id_from_resource(resource_id)] if _odoo_id_from_resource(resource_id) is not None else [],
        "fields": ["id", "name", "email", "phone", "mobile", "parent_id", "company_name", "function"],
        "expected_response_keys": ["id", "name"],
    }


def _odoo_lookup_domain(match_keys: dict[str, str]) -> list[Any]:
    clauses: list[list[Any]] = []
    if match_keys.get("email"):
        clauses.append(["email", "=", match_keys["email"]])
    if match_keys.get("phone"):
        clauses.extend([["phone", "=", match_keys["phone"]], ["mobile", "=", match_keys["phone"]]])
    if match_keys.get("full_name"):
        clauses.append(["name", "ilike", match_keys["full_name"]])
    if not clauses:
        return []
    if len(clauses) == 1:
        return clauses
    return ["|"] * (len(clauses) - 1) + clauses


def _odollo_contact_points(values: dict[str, Any]) -> list[dict[str, str]]:
    points: list[dict[str, str]] = []
    if values.get("email"):
        points.append({"kind": "email", "value": str(values["email"])})
    if values.get("phone"):
        points.append({"kind": "phone", "value": str(values["phone"])})
    if values.get("website"):
        points.append({"kind": "website", "value": str(values["website"])})
    for point in values.get("contact_points") or []:
        if not isinstance(point, dict):
            continue
        kind = str(point.get("kind") or "")
        value = str(point.get("value") or "")
        if kind == "profile_url" and value:
            points.append({"kind": "profile_url", "value": value, "label": str(point.get("label") or "")})
    return points


def _contact_points_from_spec(spec: dict[str, Any]) -> list[dict[str, str]]:
    points: list[dict[str, str]] = []
    for point in spec.get("contact_points") or []:
        if not isinstance(point, dict):
            continue
        kind = str(point.get("kind") or "")
        value = str(point.get("value") or "")
        if not kind or not value:
            continue
        clean = {"kind": kind, "value": value}
        if point.get("label"):
            clean["label"] = str(point["label"])
        points.append(clean)
    return points


def _gws_urls(values: dict[str, Any]) -> list[dict[str, str]]:
    urls: list[dict[str, str]] = []
    if values.get("website"):
        urls.append({"value": str(values["website"]), "type": "work"})
    for point in values.get("contact_points") or []:
        if not isinstance(point, dict):
            continue
        if point.get("kind") != "profile_url" or not point.get("value"):
            continue
        urls.append({"value": str(point["value"]), "type": "profile"})
    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    for url in urls:
        if url["value"] in seen:
            continue
        deduped.append(url)
        seen.add(url["value"])
    return deduped


def _odoo_id_from_resource(resource_id: Any) -> int | None:
    if isinstance(resource_id, int):
        return resource_id
    raw = str(resource_id or "")
    if raw.isdigit():
        return int(raw)
    if raw.startswith("odoo:res.partner:"):
        tail = raw.rsplit(":", maxsplit=1)[-1]
        if tail.isdigit():
            return int(tail)
    return None


def _lookup_result_for_request(request: dict[str, Any], matches: list[dict[str, Any]]) -> dict[str, Any]:
    sink = str(request.get("sink") or "")
    normalized_matches = [
        {
            "sink": sink,
            "resource_id": str(match.get("resource_id") or ""),
            "confidence": float(match.get("confidence", 0)),
            "basis": list(match.get("basis") or []),
            "display": str(match.get("display") or ""),
            "raw": dict(match.get("raw") or {}),
        }
        for match in matches
    ]
    return {
        "sink": sink,
        "status": "fixture_matches" if normalized_matches else "not_executed",
        "requires_live_adapter": True,
        "network_calls_made": 0,
        "writes_attempted": 0,
        "match_keys": request.get("match_keys", {}),
        "query_count": len(list(request.get("queries") or [])),
        "matches": normalized_matches,
    }


def _mock_readback(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "sink": str(action.get("sink") or ""),
            "resource_id": f"mock:{action.get('sink')}:{action.get('serialization_key') or 'unknown'}",
            "serialization_key": action.get("serialization_key"),
            "matched": True,
            "simulated": True,
        }
        for action in actions
    ]


def _normalize_value(value: Any) -> str:
    return " ".join(str(value or "").strip().split())
