from __future__ import annotations

from collections.abc import Callable
import json
import subprocess
from typing import Any


GwsApplyRunner = Callable[[dict[str, Any]], Any]
OdolloApplyRunner = Callable[[dict[str, Any]], Any]


def execute_sink_write_adapter(
    request: dict[str, Any],
    *,
    gws_runner: GwsApplyRunner | None = None,
    odollo_runner: OdolloApplyRunner | None = None,
) -> dict[str, Any]:
    sink = str(request.get("sink") or "")
    if request.get("phase") != "write":
        raise ValueError("sink write adapter execution requires a write request")
    if sink == "google_contacts":
        raw = (gws_runner or run_gws_write)(request)
        resource_id = _gws_resource_id(raw)
    elif sink == "odoo":
        raw = (odollo_runner or run_odollo_write)(request)
        resource_id = _odoo_resource_id(raw)
    else:
        raise ValueError(f"unsupported sink write adapter: {sink}")
    return {
        "sink": sink,
        "status": "live_write_completed",
        "network_calls_made": 1,
        "writes_attempted": 1,
        "raw": raw,
        "write": {
            "sink": sink,
            "resource_id": resource_id,
            "serialization_key": request.get("serialization_key"),
            "planned_action": request.get("planned_action"),
        },
    }


def execute_sink_readback_adapter(
    request: dict[str, Any],
    *,
    gws_runner: GwsApplyRunner | None = None,
    odollo_runner: OdolloApplyRunner | None = None,
) -> dict[str, Any]:
    sink = str(request.get("sink") or "")
    if request.get("phase") != "readback":
        raise ValueError("sink readback adapter execution requires a readback request")
    if sink == "google_contacts":
        raw = (gws_runner or run_gws_readback)(request)
        readback = _gws_readback(raw)
    elif sink == "odoo":
        raw = (odollo_runner or run_odollo_readback)(request)
        readback = _odoo_readback(raw)
    else:
        raise ValueError(f"unsupported sink readback adapter: {sink}")
    return {
        "sink": sink,
        "status": "live_readback_completed",
        "network_calls_made": 1,
        "writes_attempted": 0,
        "raw": raw,
        "readback": readback,
    }


def run_gws_write(
    request: dict[str, Any],
    *,
    command_runner: Callable[..., Any] | None = None,
) -> Any:
    command_runner = command_runner or subprocess.run
    command = list(request.get("gws_command") or ["gws", "people", "people", "createContact"])
    body = dict(request.get("request_body") or {})
    completed = command_runner(
        [*command, "--body", json.dumps(body, sort_keys=True), "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if int(getattr(completed, "returncode", 1)) != 0:
        stderr = str(getattr(completed, "stderr", "") or "").strip()
        raise RuntimeError(f"gws write failed with exit {completed.returncode}: {stderr[:500]}")
    stdout = str(getattr(completed, "stdout", "") or "").strip()
    return json.loads(stdout) if stdout else {}


def run_gws_readback(
    request: dict[str, Any],
    *,
    command_runner: Callable[..., Any] | None = None,
) -> Any:
    command_runner = command_runner or subprocess.run
    command = list(request.get("gws_command") or ["gws", "people", "people", "get"])
    body = dict(request.get("request_body") or {})
    resource_name = str(body.get("resourceName") or request.get("resource_id") or "")
    args = [*command]
    if resource_name:
        args.append(resource_name)
    args.extend(["--params", json.dumps(body, sort_keys=True), "--format", "json"])
    completed = command_runner(args, capture_output=True, text=True, check=False)
    if int(getattr(completed, "returncode", 1)) != 0:
        stderr = str(getattr(completed, "stderr", "") or "").strip()
        raise RuntimeError(f"gws readback failed with exit {completed.returncode}: {stderr[:500]}")
    stdout = str(getattr(completed, "stdout", "") or "").strip()
    return json.loads(stdout) if stdout else {}


def run_odollo_write(request: dict[str, Any], *, client: Any | None = None) -> Any:
    if client is None:
        try:
            from odollo.adapters.odoo_json2 import OdooClient
            from odollo.config import default_config_path, load_profile
        except ImportError as exc:
            raise RuntimeError("Odollo write requires odollo to be importable") from exc
        tenant = str((request.get("tenant") or {}).get("name") or "")
        if not tenant:
            raise RuntimeError("Odollo write requires sink.odollo_tenant")
        profile = load_profile(default_config_path(), tenant)
        client = OdooClient(profile.odoo, timeout=profile.odoo.timeout)
    values = dict(request.get("values") or {})
    return client.create(model=str(request.get("model") or "res.partner"), values=values)


def run_odollo_readback(request: dict[str, Any], *, client: Any | None = None) -> Any:
    if client is None:
        try:
            from odollo.adapters.odoo_json2 import OdooClient
            from odollo.config import default_config_path, load_profile
        except ImportError as exc:
            raise RuntimeError("Odollo readback requires odollo to be importable") from exc
        tenant = str((request.get("tenant") or {}).get("name") or "")
        if not tenant:
            raise RuntimeError("Odollo readback requires sink.odollo_tenant")
        profile = load_profile(default_config_path(), tenant)
        client = OdooClient(profile.odoo, timeout=profile.odoo.timeout)
    return client.read(
        model=str(request.get("model") or "res.partner"),
        ids=list(request.get("ids") or []),
        fields=list(request.get("fields") or []),
    )


def _gws_resource_id(raw: Any) -> str:
    if isinstance(raw, dict):
        person = raw.get("person") if isinstance(raw.get("person"), dict) else raw
        return str(person.get("resourceName") or raw.get("resourceName") or "")
    return ""


def _odoo_resource_id(raw: Any) -> str:
    record_id: Any = None
    if isinstance(raw, int):
        record_id = raw
    elif isinstance(raw, dict):
        record_id = raw.get("id") or raw.get("result")
    elif isinstance(raw, list) and raw:
        first = raw[0]
        record_id = first.get("id") if isinstance(first, dict) else first
    return f"odoo:res.partner:{record_id}" if record_id is not None else ""


def _gws_readback(raw: Any) -> dict[str, Any]:
    person = raw.get("person") if isinstance(raw, dict) and isinstance(raw.get("person"), dict) else raw
    if not isinstance(person, dict):
        person = {}
    emails = list(person.get("emailAddresses") or [])
    phones = list(person.get("phoneNumbers") or [])
    names = list(person.get("names") or [])
    return {
        "resource_id": str(person.get("resourceName") or ""),
        "display": _first_value(names, "displayName") or _first_value(emails, "value"),
        "emails": [_string_value(row, "value") for row in emails if _string_value(row, "value")],
        "phones": [_string_value(row, "value") for row in phones if _string_value(row, "value")],
        "matched": bool(person.get("resourceName")),
    }


def _odoo_readback(raw: Any) -> dict[str, Any]:
    rows = raw if isinstance(raw, list) else list(raw.get("result") or raw.get("rows") or []) if isinstance(raw, dict) else []
    row = rows[0] if rows and isinstance(rows[0], dict) else {}
    return {
        "resource_id": _odoo_resource_id(row),
        "display": str(row.get("name") or row.get("email") or row.get("id") or ""),
        "emails": [str(row["email"])] if row.get("email") else [],
        "phones": [str(row["phone"])] if row.get("phone") else [],
        "matched": bool(row.get("id")),
    }


def _first_value(rows: list[Any], key: str) -> str:
    for row in rows:
        value = _string_value(row, key)
        if value:
            return value
    return ""


def _string_value(row: Any, key: str) -> str:
    return str(row.get(key) or "") if isinstance(row, dict) else ""
