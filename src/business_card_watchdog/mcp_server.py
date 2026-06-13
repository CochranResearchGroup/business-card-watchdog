from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, TextIO

from .config import AppConfig
from .mcp import call_tool, tool_manifest


def serve_jsonl(
    *,
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
    config: AppConfig | None = None,
    config_path: Path | None = None,
) -> None:
    input_stream = input_stream or sys.stdin
    output_stream = output_stream or sys.stdout
    for line in input_stream:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
            response = handle_jsonrpc_request(request, config=config, config_path=config_path)
        except Exception as exc:  # pragma: no cover - defensive transport boundary
            response = _error_response(None, -32603, str(exc))
        if response is None:
            continue
        output_stream.write(json.dumps(response, sort_keys=True) + "\n")
        output_stream.flush()
        if response.get("result", {}).get("shutdown") is True:
            break


def handle_jsonrpc_request(
    request: dict[str, Any],
    *,
    config: AppConfig | None = None,
    config_path: Path | None = None,
) -> dict[str, Any] | None:
    request_id = request.get("id")
    method = str(request.get("method") or "")
    params = dict(request.get("params") or {})
    if request_id is None:
        return None
    if method == "initialize":
        return _result_response(
            request_id,
            {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "business-card-watchdog", "version": tool_manifest()["version"]},
                "capabilities": {"tools": {"listChanged": False}},
            },
        )
    if method == "tools/list":
        return _result_response(request_id, {"tools": [_mcp_tool(tool) for tool in tool_manifest()["tools"]]})
    if method == "tools/call":
        name = str(params.get("name") or "")
        arguments = dict(params.get("arguments") or {})
        try:
            payload = call_tool(name, arguments, config=config, config_path=config_path)
        except Exception as exc:
            return _result_response(
                request_id,
                {
                    "content": [{"type": "text", "text": str(exc)}],
                    "isError": True,
                },
            )
        return _result_response(
            request_id,
            {
                "content": [{"type": "text", "text": json.dumps(payload, sort_keys=True)}],
                "structuredContent": payload,
                "isError": False,
            },
        )
    if method == "ping":
        return _result_response(request_id, {})
    if method == "shutdown":
        return _result_response(request_id, {"shutdown": True})
    return _error_response(request_id, -32601, f"unknown method: {method}")


def _mcp_tool(tool: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": tool["name"],
        "description": tool.get("description", ""),
        "inputSchema": tool.get("input_schema", {"type": "object", "properties": {}}),
    }


def _result_response(request_id: object, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error_response(request_id: object, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }
