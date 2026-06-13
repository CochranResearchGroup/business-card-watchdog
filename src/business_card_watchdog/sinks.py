from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal


SinkName = Literal["google_contacts", "odoo"]
ReadinessStatus = Literal["ready", "blocked"]
SINK_PLAN_SCHEMA = "business-card-watchdog.sink-plan.v1"


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
) -> list[SinkPayload]:
    fingerprint = canonical_contact_fingerprint(spec)
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
        for readiness in [check_sink_readiness(sink, dry_run=dry_run)]
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
) -> dict[str, Any]:
    payloads = build_sink_payloads(sinks=sinks, spec=spec, dry_run=dry_run)
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


def check_sink_readiness(sink: str, *, dry_run: bool) -> SinkReadiness:
    if dry_run:
        return SinkReadiness(
            sink=sink,
            status="ready",
            reason="dry-run payload generation does not require external credentials",
        )

    if sink == "google_contacts":
        if shutil.which("gws") is None:
            return SinkReadiness(
                sink=sink,
                status="blocked",
                reason="gws CLI not found; cannot verify Google Contacts readiness",
            )
        return SinkReadiness(
            sink=sink,
            status="blocked",
            reason="live Google Contacts write/readback gate is not implemented yet",
        )

    if sink == "odoo":
        return SinkReadiness(
            sink=sink,
            status="blocked",
            reason="live Odoo/Odollo tenant readiness gate is not implemented yet",
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


def _normalize_value(value: Any) -> str:
    return " ".join(str(value or "").strip().split())
