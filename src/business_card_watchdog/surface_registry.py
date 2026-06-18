from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


MCPHandler = Callable[[Any, dict[str, Any]], dict[str, Any]]
SINK_CHOICES = ("google_contacts", "odoo")
OPERATOR_LIVE_PILOT_READINESS_COMMAND = "operator-live-pilot-readiness-packet"
SELECTED_TARGET_APPROVAL_BOUNDARY_COMMAND = "selected-target-approval-boundary"
SELECTED_TARGET_COMMAND_COPY_PACKET_COMMAND = "selected-target-command-copy-packet"
OPERATOR_LIVE_PILOT_READINESS_API_PATH = "/operator/live-pilot-readiness-packet"
SELECTED_TARGET_APPROVAL_BOUNDARY_API_PATH = "/runs/{run_id}/selected-target-approval-boundary"
SELECTED_TARGET_COMMAND_COPY_PACKET_API_PATH = "/runs/{run_id}/selected-target-command-copy-packet"


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


def add_operator_live_pilot_readiness_parser(subparsers: Any) -> None:
    parser = subparsers.add_parser(OPERATOR_LIVE_PILOT_READINESS_COMMAND)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--sink", choices=list(SINK_CHOICES), default=None)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")


def add_selected_target_runs_parsers(runs_subparsers: Any) -> None:
    approval = runs_subparsers.add_parser(SELECTED_TARGET_APPROVAL_BOUNDARY_COMMAND)
    approval.add_argument("run_id")
    approval.add_argument("--operator", required=True)
    approval.add_argument("--sink", choices=list(SINK_CHOICES), default=None)
    approval.add_argument("--job-id", default=None)
    approval.add_argument("--response", default=None)
    approval.add_argument("--no-write", action="store_true")
    approval.add_argument("--json", action="store_true")

    command_copy = runs_subparsers.add_parser(SELECTED_TARGET_COMMAND_COPY_PACKET_COMMAND)
    command_copy.add_argument("run_id")
    command_copy.add_argument("--operator", required=True)
    command_copy.add_argument("--response", required=True)
    command_copy.add_argument("--acknowledgement", default="")
    command_copy.add_argument("--sink", choices=list(SINK_CHOICES), default=None)
    command_copy.add_argument("--job-id", default=None)
    command_copy.add_argument("--json", action="store_true")


def call_registered_cli_command(service: Any, args: Any) -> dict[str, Any] | None:
    if getattr(args, "command", None) == OPERATOR_LIVE_PILOT_READINESS_COMMAND:
        return service.operator_live_pilot_readiness_packet(
            run_id=args.run_id,
            sink=args.sink,
            write=not args.no_write,
        )
    if getattr(args, "command", None) != "runs":
        return None
    if getattr(args, "runs_command", None) == SELECTED_TARGET_APPROVAL_BOUNDARY_COMMAND:
        return service.selected_target_approval_boundary(
            args.run_id,
            operator=args.operator,
            sink=args.sink,
            job_id=args.job_id,
            response=args.response,
            write=not args.no_write,
        )
    if getattr(args, "runs_command", None) == SELECTED_TARGET_COMMAND_COPY_PACKET_COMMAND:
        return service.selected_target_command_copy_packet(
            args.run_id,
            operator=args.operator,
            response=args.response,
            acknowledgement=args.acknowledgement,
            sink=args.sink,
            job_id=args.job_id,
        )
    return None
