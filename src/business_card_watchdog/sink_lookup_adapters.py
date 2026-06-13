from __future__ import annotations

from collections.abc import Callable
import json
import subprocess
from typing import Any


GwsLookupRunner = Callable[[dict[str, Any]], Any]
OdolloLookupRunner = Callable[[dict[str, Any]], Any]


def execute_sink_lookup_adapter(
    request: dict[str, Any],
    *,
    gws_runner: GwsLookupRunner | None = None,
    odollo_runner: OdolloLookupRunner | None = None,
) -> dict[str, Any]:
    sink = str(request.get("sink") or "")
    if request.get("phase") != "lookup":
        raise ValueError("sink lookup adapter execution requires a lookup request")
    if sink == "google_contacts":
        if gws_runner is None:
            gws_runner = run_gws_lookup
        raw = gws_runner(request)
        matches = _matches_from_gws_response(raw)
    elif sink == "odoo":
        if odollo_runner is None:
            odollo_runner = run_odollo_lookup
        raw = odollo_runner(request)
        matches = _matches_from_odoo_response(raw)
    else:
        raise ValueError(f"unsupported sink lookup adapter: {sink}")
    return {
        "sink": sink,
        "status": "read_only_lookup_completed",
        "network_calls_made": 1,
        "writes_attempted": 0,
        "raw": raw,
        "matches": matches,
    }


def run_gws_lookup(
    request: dict[str, Any],
    *,
    command_runner: Callable[..., Any] | None = None,
) -> Any:
    command_runner = command_runner or subprocess.run
    command = list(request.get("gws_command") or ["gws", "people", "people", "searchContacts"])
    params = dict(request.get("request_body") or {})
    completed = command_runner(
        [*command, "--params", json.dumps(params, sort_keys=True), "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if int(getattr(completed, "returncode", 1)) != 0:
        stderr = str(getattr(completed, "stderr", "") or "").strip()
        raise RuntimeError(f"gws lookup failed with exit {completed.returncode}: {stderr[:500]}")
    stdout = str(getattr(completed, "stdout", "") or "").strip()
    return json.loads(stdout) if stdout else {}


def run_odollo_lookup(request: dict[str, Any], *, client: Any | None = None) -> Any:
    if client is None:
        try:
            from odollo.adapters.odoo_json2 import OdooClient
            from odollo.config import default_config_path, load_profile
        except ImportError as exc:
            raise RuntimeError("Odollo lookup requires odollo to be importable") from exc
        tenant = str((request.get("tenant") or {}).get("name") or "")
        if not tenant:
            raise RuntimeError("Odollo lookup requires sink.odollo_tenant")
        profile = load_profile(default_config_path(), tenant)
        client = OdooClient(profile.odoo, timeout=profile.odoo.timeout)
    return client.search_read(
        model=str(request.get("model") or "res.partner"),
        domain=list(request.get("domain") or []),
        fields=list(request.get("fields") or []),
        limit=int(request.get("limit") or 10),
    )


def _matches_from_gws_response(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        rows = raw
    elif isinstance(raw, dict):
        rows = list(raw.get("results") or raw.get("connections") or [])
    else:
        rows = []
    matches: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        person = row.get("person") if isinstance(row.get("person"), dict) else row
        resource_id = str(person.get("resourceName") or row.get("resourceName") or "")
        if not resource_id:
            continue
        names = list(person.get("names") or [])
        emails = list(person.get("emailAddresses") or [])
        phones = list(person.get("phoneNumbers") or [])
        display = _first_value(names, "displayName") or _first_value(emails, "value") or resource_id
        basis = []
        if emails:
            basis.append("email")
        if phones:
            basis.append("phone")
        if names:
            basis.append("full_name")
        matches.append(
            {
                "resource_id": resource_id,
                "confidence": 0.9 if basis else 0.5,
                "basis": basis or ["resource_id"],
                "display": display,
                "raw": row,
            }
        )
    return matches


def _matches_from_odoo_response(raw: Any) -> list[dict[str, Any]]:
    rows = raw if isinstance(raw, list) else list(raw.get("rows") or raw.get("result") or []) if isinstance(raw, dict) else []
    matches: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        record_id = row.get("id")
        if record_id is None:
            continue
        basis = []
        if row.get("email"):
            basis.append("email")
        if row.get("phone") or row.get("mobile"):
            basis.append("phone")
        if row.get("name"):
            basis.append("full_name")
        matches.append(
            {
                "resource_id": f"odoo:res.partner:{record_id}",
                "confidence": 0.9 if basis else 0.5,
                "basis": basis or ["resource_id"],
                "display": str(row.get("name") or row.get("email") or record_id),
                "raw": row,
            }
        )
    return matches


def _first_value(rows: list[Any], key: str) -> str:
    for row in rows:
        if isinstance(row, dict) and row.get(key):
            return str(row[key])
    return ""
