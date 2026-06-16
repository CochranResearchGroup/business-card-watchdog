from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


MCPHandler = Callable[[Any, dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class McpToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: MCPHandler

    def manifest_entry(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


def _operator_live_pilot_readiness_packet(service: Any, args: dict[str, Any]) -> dict[str, Any]:
    return service.operator_live_pilot_readiness_packet(
        run_id=str(args["run_id"]),
        sink=str(args["sink"]) if args.get("sink") else None,
        write=bool(args.get("write", True)),
    )


def _selected_target_approval_boundary(service: Any, args: dict[str, Any]) -> dict[str, Any]:
    return service.selected_target_approval_boundary(
        str(args["run_id"]),
        operator=str(args["operator"]),
        sink=str(args["sink"]) if args.get("sink") else None,
        job_id=str(args["job_id"]) if args.get("job_id") else None,
        response=str(args["response"]) if args.get("response") else None,
        write=bool(args.get("write", True)),
    )


def _selected_target_command_copy_packet(service: Any, args: dict[str, Any]) -> dict[str, Any]:
    return service.selected_target_command_copy_packet(
        str(args["run_id"]),
        operator=str(args["operator"]),
        response=str(args["response"]),
        acknowledgement=str(args["acknowledgement"]) if args.get("acknowledgement") else "",
        sink=str(args["sink"]) if args.get("sink") else None,
        job_id=str(args["job_id"]) if args.get("job_id") else None,
    )


MCP_TOOL_SPECS: dict[str, McpToolSpec] = {
    "business_card_watchdog_operator_live_pilot_readiness_packet": McpToolSpec(
        name="business_card_watchdog_operator_live_pilot_readiness_packet",
        description=(
            "Compose dashboard, operator preflight, and synthetic rehearsal gate expectations "
            "into one no-live pilot readiness packet."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "run_id": {"type": "string"},
                "sink": {"type": "string", "enum": ["google_contacts", "odoo"]},
                "write": {"type": "boolean", "default": True},
            },
            "required": ["run_id"],
        },
        handler=_operator_live_pilot_readiness_packet,
    ),
    "business_card_watchdog_selected_target_approval_boundary": McpToolSpec(
        name="business_card_watchdog_selected_target_approval_boundary",
        description=(
            "Compose approval packet, response validation, preflight, and selected-target preview "
            "without creating selected_live_target.json."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "run_id": {"type": "string"},
                "operator": {"type": "string"},
                "sink": {"type": "string"},
                "job_id": {"type": "string"},
                "response": {"type": "string"},
                "write": {"type": "boolean", "default": True},
            },
            "required": ["run_id", "operator"],
        },
        handler=_selected_target_approval_boundary,
    ),
    "business_card_watchdog_selected_target_command_copy_packet": McpToolSpec(
        name="business_card_watchdog_selected_target_command_copy_packet",
        description=(
            "Return selected-target creation command text only after response validation and "
            "matching operator acknowledgement."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "run_id": {"type": "string"},
                "operator": {"type": "string"},
                "response": {"type": "string"},
                "acknowledgement": {"type": "string"},
                "sink": {"type": "string"},
                "job_id": {"type": "string"},
            },
            "required": ["run_id", "operator", "response"],
        },
        handler=_selected_target_command_copy_packet,
    ),
}


def mcp_tool_manifest_entry(tool_name: str) -> dict[str, Any]:
    return MCP_TOOL_SPECS[tool_name].manifest_entry()


def call_registered_mcp_tool(tool_name: str, service: Any, args: dict[str, Any]) -> dict[str, Any] | None:
    spec = MCP_TOOL_SPECS.get(tool_name)
    if spec is None:
        return None
    return spec.handler(service, args)
