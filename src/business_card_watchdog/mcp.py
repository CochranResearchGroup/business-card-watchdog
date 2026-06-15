from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import AppConfig, load_config
from .service import BusinessCardService


def tool_manifest() -> dict[str, object]:
    return {
        "name": "business-card-watchdog",
        "version": "0.1.0",
        "tools": [
            {
                "name": "business_card_watchdog_process",
                "description": "Process a business card image or directory into a deterministic run ledger.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "source": {"type": "string"},
                        "dry_run": {"type": "boolean", "default": True},
                        "workers": {"type": "integer", "minimum": 1, "maximum": 16, "default": 2},
                    },
                    "required": ["source"],
                },
            },
            {
                "name": "business_card_watchdog_status",
                "description": "Report configured runtime paths, skill readiness, and watcher status.",
                "input_schema": {"type": "object", "properties": {}},
            },
            {
                "name": "business_card_watchdog_operator_dashboard",
                "description": "Compose no-live operator status, readiness, recovery, runs, review counts, next actions, and CLI/API/MCP handoff commands.",
                "input_schema": {
                    "type": "object",
                    "properties": {"run_id": {"type": "string"}},
                },
            },
            {
                "name": "business_card_watchdog_runtime_readiness",
                "description": "Report user-scope install, config, runtime directory, watcher, and service readiness without network calls.",
                "input_schema": {"type": "object", "properties": {}},
            },
            {
                "name": "business_card_watchdog_service_recovery",
                "description": "Report install/start/status/restart/resume/recover commands and recovery stop conditions without executing them.",
                "input_schema": {
                    "type": "object",
                    "properties": {"run_id": {"type": "string"}},
                },
            },
            {
                "name": "business_card_watchdog_live_target_candidates",
                "description": "List no-network candidate run/job/sink targets for explicit selected live lookup approval.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "sink": {"type": "string", "enum": ["google_contacts", "odoo"]},
                    },
                },
            },
            {
                "name": "business_card_watchdog_live_readiness_audit",
                "description": "Create or preview a no-network run-level live readiness audit before selected-target approval.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "sink": {"type": "string", "enum": ["google_contacts", "odoo"]},
                        "write": {"type": "boolean", "default": True},
                    },
                },
            },
            {
                "name": "business_card_watchdog_live_selection_requirements",
                "description": "Create or preview a no-network run-level report of required operator fields before selected-target approval.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "sink": {"type": "string", "enum": ["google_contacts", "odoo"]},
                        "write": {"type": "boolean", "default": True},
                    },
                },
            },
            {
                "name": "business_card_watchdog_operator_selected_live_smoke_preflight",
                "description": "Compose offline gap, live readiness, and selection requirements into one no-live operator-selected live smoke preflight.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "sink": {"type": "string", "enum": ["google_contacts", "odoo"]},
                        "write": {"type": "boolean", "default": True},
                    },
                },
            },
            {
                "name": "business_card_watchdog_runs_list",
                "description": "List known run records from the user-scoped run index.",
                "input_schema": {"type": "object", "properties": {}},
            },
            {
                "name": "business_card_watchdog_run_show",
                "description": "Show one run with latest jobs and artifact records.",
                "input_schema": {
                    "type": "object",
                    "properties": {"run_id": {"type": "string"}},
                    "required": ["run_id"],
                },
            },
            {
                "name": "business_card_watchdog_run_summary",
                "description": "Summarize job states and artifact counts for one run.",
                "input_schema": {
                    "type": "object",
                    "properties": {"run_id": {"type": "string"}},
                    "required": ["run_id"],
                },
            },
            {
                "name": "business_card_watchdog_phase_report",
                "description": "Report batch progress by deterministic pipeline phase for one run.",
                "input_schema": {
                    "type": "object",
                    "properties": {"run_id": {"type": "string"}},
                    "required": ["run_id"],
                },
            },
            {
                "name": "business_card_watchdog_pilot_readiness_report",
                "description": "Report whether a run is ready for sink write/readback pilots.",
                "input_schema": {
                    "type": "object",
                    "properties": {"run_id": {"type": "string"}},
                    "required": ["run_id"],
                },
            },
            {
                "name": "business_card_watchdog_live_pilot_status",
                "description": "Report run-level selected-target, live pilot evidence, and closeout status without executing live calls.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "write": {"type": "boolean", "default": True},
                    },
                    "required": ["run_id"],
                },
            },
            {
                "name": "business_card_watchdog_live_pilot_handoff",
                "description": "Create an operator handoff with exact next live-pilot commands and stop conditions without executing live calls.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "write": {"type": "boolean", "default": True},
                    },
                    "required": ["run_id"],
                },
            },
            {
                "name": "business_card_watchdog_live_pilot_approval_packet",
                "description": "Export compact no-live approval templates for one run or job without creating selected_live_target.json.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "job_id": {"type": "string"},
                    },
                    "required": ["run_id"],
                },
            },
            {
                "name": "business_card_watchdog_live_pilot_operator_response_validation",
                "description": "Validate an operator response against the current live-pilot handoff without creating selected_live_target.json.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "response": {"type": "string"},
                    },
                    "required": ["run_id", "response"],
                },
            },
            {
                "name": "business_card_watchdog_selected_live_target_preflight",
                "description": "Preflight whether an operator response would be allowed to create selected_live_target.json without writing it.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "response": {"type": "string"},
                    },
                    "required": ["run_id", "response"],
                },
            },
            {
                "name": "business_card_watchdog_selected_live_target_artifact_preview",
                "description": "Preview the selected_live_target.json artifact fields that would be written without creating it.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "response": {"type": "string"},
                    },
                    "required": ["run_id", "response"],
                },
            },
            {
                "name": "business_card_watchdog_selected_live_target_from_response",
                "description": "Preview or explicitly create selected_live_target.json from a validated operator response.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "response": {"type": "string"},
                        "write_selected_target": {"type": "boolean", "default": False},
                        "reason": {"type": "string"},
                    },
                    "required": ["run_id", "response"],
                },
            },
            {
                "name": "business_card_watchdog_selected_live_target_handoff_from_response",
                "description": "Read back the selected target and audit handoff for a validated operator response without live calls.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "response": {"type": "string"},
                        "write_audit": {"type": "boolean", "default": False},
                    },
                    "required": ["run_id", "response"],
                },
            },
            {
                "name": "business_card_watchdog_lookup_smoke_handoff_from_response",
                "description": "Preview or write the lookup-smoke handoff for an active selected target from a validated operator response without live calls.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "response": {"type": "string"},
                        "write_handoff": {"type": "boolean", "default": False},
                    },
                    "required": ["run_id", "response"],
                },
            },
            {
                "name": "business_card_watchdog_selected_lookup_smoke_execution_packet_from_response",
                "description": "Preview or explicitly execute selected lookup smoke from a validated operator response, gated by ready handoff.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "response": {"type": "string"},
                        "execute_selected_lookup_smoke": {"type": "boolean", "default": False},
                    },
                    "required": ["run_id", "response"],
                },
            },
            {
                "name": "business_card_watchdog_selected_write_pilot_execution_packet_from_response",
                "description": "Preview or explicitly execute selected sink write pilot from a validated operator response, gated by lookup and duplicate evidence.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "response": {"type": "string"},
                        "execute_write_pilot": {"type": "boolean", "default": False},
                    },
                    "required": ["run_id", "response"],
                },
            },
            {
                "name": "business_card_watchdog_selected_readback_pilot_execution_packet_from_response",
                "description": "Preview or explicitly execute selected sink readback pilot from a validated operator response, gated by write-pilot evidence.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "response": {"type": "string"},
                        "execute_readback_pilot": {"type": "boolean", "default": False},
                    },
                    "required": ["run_id", "response"],
                },
            },
            {
                "name": "business_card_watchdog_live_pilot_closeout_packet_from_response",
                "description": "Preview or explicitly write a live-pilot closeout report from a validated operator response without running live calls.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "response": {"type": "string"},
                        "write_closeout": {"type": "boolean", "default": False},
                    },
                    "required": ["run_id", "response"],
                },
            },
            {
                "name": "business_card_watchdog_live_pilot_operator_workflow_packet_from_response",
                "description": "Preview the full selected live-pilot operator workflow from a validated response without running live calls.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "response": {"type": "string"},
                    },
                    "required": ["run_id", "response"],
                },
            },
            {
                "name": "business_card_watchdog_live_pilot_operator_rehearsal_from_response",
                "description": "Preview the next safe inspection command and next explicit live-pilot command without executing either.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "response": {"type": "string"},
                    },
                    "required": ["run_id", "response"],
                },
            },
            {
                "name": "business_card_watchdog_live_pilot_readiness_export_from_response",
                "description": "Create or preview a redacted live-pilot readiness export from a validated operator response without running live calls.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "response": {"type": "string"},
                        "write": {"type": "boolean", "default": True},
                    },
                    "required": ["run_id", "response"],
                },
            },
            {
                "name": "business_card_watchdog_live_pilot_execution_checklist_from_response",
                "description": "Validate the redacted readiness export and reveal the next executable live command only when it matches current state.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "response": {"type": "string"},
                    },
                    "required": ["run_id", "response"],
                },
            },
            {
                "name": "business_card_watchdog_live_pilot_command_copy_packet_from_response",
                "description": "Return command-copy text only after the readiness checklist is ready and the operator acknowledgement matches the run context.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "response": {"type": "string"},
                        "acknowledgement": {"type": "string", "default": ""},
                    },
                    "required": ["run_id", "response"],
                },
            },
            {
                "name": "business_card_watchdog_next_actions",
                "description": "Return deterministic next actions for agent-loop batch orchestration.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
                    },
                },
            },
            {
                "name": "business_card_watchdog_run_next_actions",
                "description": "Execute safe zero-network/zero-write next actions for deterministic agent loops.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 10},
                    },
                },
            },
            {
                "name": "business_card_watchdog_offline_pilot_gap_audit",
                "description": "Inspect offline pilot drill/documentation coverage and remaining live/operator boundaries without running live calls.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "write": {"type": "boolean", "default": True},
                    },
                },
            },
            {
                "name": "business_card_watchdog_review_routing_drill",
                "description": "Run a synthetic no-live review/export/routing drill through safe agent-loop actions.",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                },
            },
            {
                "name": "business_card_watchdog_multi_card_preclassification_drill",
                "description": "Run a synthetic no-live multi-card image preclassification drill and report deterministic candidate boxes.",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                },
            },
            {
                "name": "business_card_watchdog_watch_dry_run_selection_drill",
                "description": "Run a synthetic no-processing watch dry-run selection drill and emit operator sample output.",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                },
            },
            {
                "name": "business_card_watchdog_watch_dry_run_execution_drill",
                "description": "Run a synthetic watched dry-run execution drill through the real batch orchestrator.",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                },
            },
            {
                "name": "business_card_watchdog_live_pilot_rehearsal_drill",
                "description": "Run a synthetic no-live live-pilot rehearsal through selected target, readiness export, checklist, and command-copy gates.",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                },
            },
            {
                "name": "business_card_watchdog_child_replacement_readiness_drill",
                "description": "Run a synthetic no-live child replacement stale/readiness drill and emit operator review sample outputs.",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                },
            },
            {
                "name": "business_card_watchdog_jobs_list",
                "description": "List latest job states, optionally for one run.",
                "input_schema": {
                    "type": "object",
                    "properties": {"run_id": {"type": "string"}},
                },
            },
            {
                "name": "business_card_watchdog_reviews_list",
                "description": "List review queue entries with key artifact pointers.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "state": {"type": "string", "default": "needs_review"},
                        "next_action": {"type": "string"},
                        "artifact_kind": {"type": "string"},
                    },
                },
            },
            {
                "name": "business_card_watchdog_child_reviews_list",
                "description": "List promoted child contact candidates that require review before routing.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "state": {"type": "string", "default": "needs_review"},
                    },
                },
            },
            {
                "name": "business_card_watchdog_child_review_submit",
                "description": "Approve, keep, or reject a promoted child contact candidate without live sink writes.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "candidate_id": {"type": "string"},
                        "reviewer": {"type": "string", "default": "operator"},
                        "action": {"type": "string", "default": "keep_needs_review"},
                        "field_corrections": {"type": "object"},
                        "notes": {"type": "string"},
                    },
                    "required": ["run_id", "candidate_id"],
                },
            },
            {
                "name": "business_card_watchdog_child_route_prep_queue",
                "description": "List approved child contacts ready for dry-run dedupe and routing preparation.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "state": {"type": "string", "default": "approved_for_dedupe"},
                    },
                },
            },
            {
                "name": "business_card_watchdog_child_route_prepare",
                "description": "Write dry-run child lookup and sink planning artifacts for one approved child contact.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "candidate_id": {"type": "string"},
                        "dry_run": {"type": "boolean", "default": True},
                    },
                    "required": ["run_id", "candidate_id"],
                },
            },
            {
                "name": "business_card_watchdog_child_sink_lookup_result",
                "description": "Record supplied child downstream lookup matches as a zero-network local result artifact.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "candidate_id": {"type": "string"},
                        "matches_by_sink": {"type": "object"},
                    },
                    "required": ["run_id", "candidate_id"],
                },
            },
            {
                "name": "business_card_watchdog_child_downstream_duplicate_assessment",
                "description": "Assess a child sink lookup result for downstream duplicate state without live sink calls.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "candidate_id": {"type": "string"},
                    },
                    "required": ["run_id", "candidate_id"],
                },
            },
            {
                "name": "business_card_watchdog_child_duplicate_resolution",
                "description": "Record an explicit operator child duplicate decision before sink-plan gating.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "candidate_id": {"type": "string"},
                        "reviewer": {"type": "string", "default": "operator"},
                        "decision": {"type": "string"},
                        "target_identity": {"type": "string"},
                        "reason": {"type": "string"},
                    },
                    "required": ["run_id", "candidate_id", "decision"],
                },
            },
            {
                "name": "business_card_watchdog_child_sink_plan_gate",
                "description": "Check whether child duplicate evidence clears the local child sink plan for future preflight.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "candidate_id": {"type": "string"},
                    },
                    "required": ["run_id", "candidate_id"],
                },
            },
            {
                "name": "business_card_watchdog_child_sink_apply_preflight",
                "description": "Create a child sink apply preflight preview from a cleared child sink-plan gate.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "candidate_id": {"type": "string"},
                        "apply": {"type": "boolean", "default": False},
                    },
                    "required": ["run_id", "candidate_id"],
                },
            },
            {
                "name": "business_card_watchdog_child_selected_target_handoff",
                "description": "Create a no-live child selected-target handoff packet for operator review.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "candidate_id": {"type": "string"},
                        "sink": {"type": "string"},
                        "operator": {"type": "string", "default": "operator"},
                        "scope": {"type": "string", "default": "write"},
                        "reason": {"type": "string"},
                    },
                    "required": ["run_id", "candidate_id", "sink"],
                },
            },
            {
                "name": "business_card_watchdog_child_selected_target_response_validation",
                "description": "Validate a child selected-target operator response against the current no-live child handoff.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "candidate_id": {"type": "string"},
                        "response": {"type": "string"},
                    },
                    "required": ["run_id", "candidate_id", "response"],
                },
            },
            {
                "name": "business_card_watchdog_child_selected_target_execution_checklist",
                "description": "Create a no-live child selected-target execution checklist from a validated operator response.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "candidate_id": {"type": "string"},
                        "response": {"type": "string"},
                    },
                    "required": ["run_id", "candidate_id", "response"],
                },
            },
            {
                "name": "business_card_watchdog_child_selected_target_command_copy_packet",
                "description": "Return child offline command-copy text only after the no-live checklist is ready and acknowledgement matches the child context.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "candidate_id": {"type": "string"},
                        "response": {"type": "string"},
                        "acknowledgement": {"type": "string", "default": ""},
                    },
                    "required": ["run_id", "candidate_id", "response"],
                },
            },
            {
                "name": "business_card_watchdog_child_selected_target_audit",
                "description": "Create a no-live child selected-target audit preview with replacement/abandonment guard state.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "candidate_id": {"type": "string"},
                        "sink": {"type": "string"},
                        "operator": {"type": "string"},
                        "scope": {"type": "string"},
                        "write": {"type": "boolean", "default": True},
                    },
                    "required": ["run_id", "candidate_id"],
                },
            },
            {
                "name": "business_card_watchdog_child_selected_target_abandonment",
                "description": "Record a no-live child selected-target abandonment artifact without deleting prior artifacts.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "candidate_id": {"type": "string"},
                        "operator": {"type": "string"},
                        "reason": {"type": "string"},
                    },
                    "required": ["run_id", "candidate_id", "operator", "reason"],
                },
            },
            {
                "name": "business_card_watchdog_child_selected_target_replacement_reset",
                "description": "Create a no-live child selected-target replacement reset packet after abandonment.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "candidate_id": {"type": "string"},
                        "sink": {"type": "string"},
                        "operator": {"type": "string"},
                        "scope": {"type": "string", "default": "write"},
                        "reset_by": {"type": "string", "default": "operator"},
                        "reason": {"type": "string", "default": ""},
                    },
                    "required": ["run_id", "candidate_id", "sink", "operator"],
                },
            },
            {
                "name": "business_card_watchdog_child_replacement_handoff_refresh",
                "description": "Refresh a no-live child selected-target handoff after a ready replacement reset and mark prior child target artifacts stale.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "candidate_id": {"type": "string"},
                        "sink": {"type": "string"},
                        "operator": {"type": "string"},
                        "scope": {"type": "string", "default": "write"},
                        "reason": {"type": "string", "default": ""},
                    },
                    "required": ["run_id", "candidate_id", "sink", "operator"],
                },
            },
            {
                "name": "business_card_watchdog_child_replacement_response_validation",
                "description": "Validate a no-live child replacement response only after the replacement refresh and stale marker are ready.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "candidate_id": {"type": "string"},
                        "response": {"type": "string"},
                    },
                    "required": ["run_id", "candidate_id", "response"],
                },
            },
            {
                "name": "business_card_watchdog_child_replacement_execution_checklist",
                "description": "Create a no-live child replacement execution checklist from a ready replacement response validation.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "candidate_id": {"type": "string"},
                        "response": {"type": "string"},
                    },
                    "required": ["run_id", "candidate_id", "response"],
                },
            },
            {
                "name": "business_card_watchdog_child_replacement_command_copy_packet",
                "description": "Return child replacement offline command-copy text only after the replacement checklist is ready and acknowledgement matches the child context.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "candidate_id": {"type": "string"},
                        "response": {"type": "string"},
                        "acknowledgement": {"type": "string", "default": ""},
                    },
                    "required": ["run_id", "candidate_id", "response"],
                },
            },
            {
                "name": "business_card_watchdog_child_replacement_closeout_status",
                "description": "Create a no-live child replacement closeout/status rollup from existing stale and refreshed replacement packets.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "candidate_id": {"type": "string"},
                    },
                    "required": ["run_id", "candidate_id"],
                },
            },
            {
                "name": "business_card_watchdog_review_bundle",
                "description": "Create a run-level batch review bundle with inline review-relevant artifact payloads.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "state": {"type": "string", "default": "all"},
                        "write": {"type": "boolean", "default": True},
                    },
                    "required": ["run_id"],
                },
            },
            {
                "name": "business_card_watchdog_review_html",
                "description": "Create a run-level static HTML review surface from the review bundle.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "state": {"type": "string", "default": "all"},
                        "write": {"type": "boolean", "default": True},
                    },
                    "required": ["run_id"],
                },
            },
            {
                "name": "business_card_watchdog_review_workbook",
                "description": "Create a run-level CSV review workbook from the review bundle.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "state": {"type": "string", "default": "all"},
                        "write": {"type": "boolean", "default": True},
                    },
                    "required": ["run_id"],
                },
            },
            {
                "name": "business_card_watchdog_apply_review_decisions",
                "description": "Apply a batch of run-scoped review decisions through the shared review submission path.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "reviewer": {"type": "string", "default": "operator"},
                        "decisions": {"type": "array", "items": {"type": "object"}},
                        "decisions_csv": {"type": "string"},
                        "preview": {"type": "boolean", "default": False},
                        "preview_write": {"type": "boolean", "default": False},
                    },
                    "required": ["run_id"],
                },
            },
            {
                "name": "business_card_watchdog_review_workbook_validation",
                "description": "Validate an edited review workbook CSV and return the spreadsheet-friendly validation CSV without applying decisions.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "reviewer": {"type": "string", "default": "operator"},
                        "decisions_csv": {"type": "string"},
                        "preview_write": {"type": "boolean", "default": False},
                    },
                    "required": ["run_id", "decisions_csv"],
                },
            },
            {
                "name": "business_card_watchdog_job_show",
                "description": "Show one job and its artifact records.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string"},
                        "run_id": {"type": "string"},
                    },
                    "required": ["job_id"],
                },
            },
            {
                "name": "business_card_watchdog_job_review",
                "description": "Submit structured field/crop review for one job and optionally approve it for routing.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string"},
                        "run_id": {"type": "string"},
                        "reviewer": {"type": "string", "default": "operator"},
                        "action": {
                            "type": "string",
                            "enum": [
                                "approve_for_routing",
                                "approve_enrichment_merge",
                                "keep_needs_review",
                                "request_enrichment",
                                "resolve_duplicate",
                                "reject_not_card",
                                "skip",
                            ],
                            "default": "keep_needs_review",
                        },
                        "field_corrections": {"type": "object"},
                        "crop_selection": {"type": "object"},
                        "approved_enrichment_fields": {"type": "array", "items": {"type": "string"}},
                        "duplicate_resolution": {"type": "object"},
                        "notes": {"type": "string"},
                    },
                    "required": ["job_id", "run_id"],
                },
            },
            {
                "name": "business_card_watchdog_sinks_check",
                "description": "Report dry-run/live readiness for configured sinks without performing writes.",
                "input_schema": {"type": "object", "properties": {}},
            },
            {
                "name": "business_card_watchdog_sink_plan",
                "description": "Create a dry-run sink plan artifact for one reviewed or normalized job.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string"},
                        "run_id": {"type": "string"},
                        "dry_run": {"type": "boolean", "default": True},
                    },
                    "required": ["job_id", "run_id"],
                },
            },
            {
                "name": "business_card_watchdog_sink_lookup_plan",
                "description": "Create a zero-network downstream sink lookup plan artifact for one job.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string"},
                        "run_id": {"type": "string"},
                        "dry_run": {"type": "boolean", "default": True},
                    },
                    "required": ["job_id", "run_id"],
                },
            },
            {
                "name": "business_card_watchdog_sink_apply_preflight",
                "description": "Create a zero-write sink apply preflight artifact for one planned job.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string"},
                        "run_id": {"type": "string"},
                        "apply": {"type": "boolean", "default": False},
                        "simulate": {"type": "boolean", "default": False},
                    },
                    "required": ["job_id", "run_id"],
                },
            },
            {
                "name": "business_card_watchdog_sink_apply_decision",
                "description": "Record a zero-write operator decision for sink apply: approve, reject, or noop.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string"},
                        "run_id": {"type": "string"},
                        "decision": {"type": "string", "enum": ["approve", "reject", "noop"]},
                        "reviewer": {"type": "string", "default": "operator"},
                        "reason": {"type": "string"},
                    },
                    "required": ["job_id", "run_id", "decision"],
                },
            },
            {
                "name": "business_card_watchdog_sink_apply",
                "description": "Attempt gated sink apply and write zero-write result/readback artifact while live adapters are blocked.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string"},
                        "run_id": {"type": "string"},
                        "apply": {"type": "boolean", "default": False},
                        "simulate": {"type": "boolean", "default": False},
                    },
                    "required": ["job_id", "run_id"],
                },
            },
            {
                "name": "business_card_watchdog_sink_apply_pilot_readiness",
                "description": "Create a zero-write one-job, optional selected-sink live apply pilot readiness artifact.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string"},
                        "run_id": {"type": "string"},
                        "sink": {"type": "string", "enum": ["google_contacts", "odoo"]},
                    },
                    "required": ["job_id", "run_id"],
                },
            },
            {
                "name": "business_card_watchdog_sink_apply_pilot_report",
                "description": "Create a zero-write apply pilot report from readiness, write, apply, and readback pilot artifacts.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string"},
                        "run_id": {"type": "string"},
                    },
                    "required": ["job_id", "run_id"],
                },
            },
            {
                "name": "business_card_watchdog_sink_apply_pilot_bundle",
                "description": "Create a zero-write one-job selected-sink operator pilot bundle with commands and stop conditions.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string"},
                        "run_id": {"type": "string"},
                        "sink": {"type": "string", "enum": ["google_contacts", "odoo"]},
                        "operator": {"type": "string", "default": "operator"},
                    },
                    "required": ["job_id", "run_id", "sink"],
                },
            },
            {
                "name": "business_card_watchdog_sink_adapter_request",
                "description": "Create a blocked live-adapter request artifact for lookup, write, or readback.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string"},
                        "run_id": {"type": "string"},
                        "phase": {
                            "type": "string",
                            "enum": ["lookup", "write", "readback"],
                            "default": "lookup",
                        },
                    },
                    "required": ["job_id", "run_id"],
                },
            },
            {
                "name": "business_card_watchdog_sink_lookup_result",
                "description": "Record a zero-network downstream sink lookup result artifact for one job.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string"},
                        "run_id": {"type": "string"},
                        "matches_by_sink": {
                            "type": "object",
                            "additionalProperties": {
                                "type": "array",
                                "items": {"type": "object"},
                            },
                        },
                    },
                    "required": ["job_id", "run_id"],
                },
            },
            {
                "name": "business_card_watchdog_sink_lookup_pilot",
                "description": "Execute an explicit read-only sink lookup pilot with mocked/live-supplied result rows and no writes.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string"},
                        "run_id": {"type": "string"},
                        "sink": {"type": "string", "enum": ["google_contacts", "odoo"]},
                        "approved_by": {"type": "string"},
                        "matches": {"type": "array", "items": {"type": "object"}},
                        "simulate": {"type": "boolean", "default": True},
                    },
                    "required": ["job_id", "run_id", "sink", "approved_by"],
                },
            },
            {
                "name": "business_card_watchdog_sink_lookup_readiness",
                "description": "Report selected job/sink readiness before an explicit read-only live lookup pilot.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string"},
                        "run_id": {"type": "string"},
                        "sink": {"type": "string", "enum": ["google_contacts", "odoo"]},
                    },
                    "required": ["job_id", "run_id", "sink"],
                },
            },
            {
                "name": "business_card_watchdog_sink_lookup_smoke_handoff",
                "description": "Create a zero-network selected-target handoff before an explicit read-only live lookup smoke.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string"},
                        "run_id": {"type": "string"},
                        "sink": {"type": "string", "enum": ["google_contacts", "odoo"]},
                        "approved_by": {"type": "string", "default": "operator"},
                    },
                    "required": ["job_id", "run_id", "sink"],
                },
            },
            {
                "name": "business_card_watchdog_live_selection_packet",
                "description": "Create or preview a no-network live target selection packet without approving selected_live_target.json.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string"},
                        "run_id": {"type": "string"},
                        "sink": {"type": "string", "enum": ["google_contacts", "odoo"]},
                        "operator": {"type": "string"},
                        "scope": {"type": "string", "enum": ["lookup", "write", "readback", "all"], "default": "lookup"},
                        "reason": {"type": "string"},
                        "write": {"type": "boolean", "default": True},
                    },
                    "required": ["job_id", "run_id", "sink", "operator"],
                },
            },
            {
                "name": "business_card_watchdog_selected_live_target",
                "description": "Create durable selected run/job/sink/operator approval evidence before non-simulated sink pilots.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string"},
                        "run_id": {"type": "string"},
                        "sink": {"type": "string", "enum": ["google_contacts", "odoo"]},
                        "operator": {"type": "string"},
                        "scope": {"type": "string", "enum": ["lookup", "write", "readback", "all"], "default": "lookup"},
                        "reason": {"type": "string"},
                        "safety_confirmation": {"type": "string"},
                    },
                    "required": ["job_id", "run_id", "sink", "operator", "safety_confirmation"],
                },
            },
            {
                "name": "business_card_watchdog_selected_live_target_audit",
                "description": "Verify selected_live_target.json and report allowed next live commands without executing them.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string"},
                        "run_id": {"type": "string"},
                        "scope": {"type": "string", "enum": ["lookup", "write", "readback", "all"]},
                        "write": {"type": "boolean", "default": True},
                    },
                    "required": ["job_id", "run_id"],
                },
            },
            {
                "name": "business_card_watchdog_live_pilot_abandonment",
                "description": "Record that the current selected live target is abandoned without deleting artifacts or executing live calls.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string"},
                        "run_id": {"type": "string"},
                        "operator": {"type": "string"},
                        "reason": {"type": "string"},
                    },
                    "required": ["job_id", "run_id", "operator", "reason"],
                },
            },
            {
                "name": "business_card_watchdog_selected_lookup_smoke",
                "description": "Execute the selected read-only live lookup smoke from selected_live_target.json and import redacted duplicate evidence.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string"},
                        "run_id": {"type": "string"},
                    },
                    "required": ["job_id", "run_id"],
                },
            },
            {
                "name": "business_card_watchdog_sink_write_pilot",
                "description": "Execute an explicit one-job sink write pilot, simulated by default, with approval metadata.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string"},
                        "run_id": {"type": "string"},
                        "sink": {"type": "string", "enum": ["google_contacts", "odoo"]},
                        "approved_by": {"type": "string"},
                        "simulate": {"type": "boolean", "default": True},
                    },
                    "required": ["job_id", "run_id", "sink", "approved_by"],
                },
            },
            {
                "name": "business_card_watchdog_sink_readback_pilot",
                "description": "Execute an explicit read-only sink readback pilot with mocked/live readback evidence and no writes.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string"},
                        "run_id": {"type": "string"},
                        "sink": {"type": "string", "enum": ["google_contacts", "odoo"]},
                        "approved_by": {"type": "string"},
                        "readback": {"type": "object"},
                        "simulate": {"type": "boolean", "default": True},
                    },
                    "required": ["job_id", "run_id", "sink", "approved_by"],
                },
            },
            {
                "name": "business_card_watchdog_live_pilot_closeout",
                "description": "Create or preview a no-network live pilot closeout report from selected-target, lookup, write, and readback evidence.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string"},
                        "run_id": {"type": "string"},
                        "write": {"type": "boolean", "default": True},
                    },
                    "required": ["job_id", "run_id"],
                },
            },
            {
                "name": "business_card_watchdog_downstream_duplicate_assessment",
                "description": "Assess sink lookup results into a review-blocking downstream duplicate artifact.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string"},
                        "run_id": {"type": "string"},
                    },
                    "required": ["job_id", "run_id"],
                },
            },
            {
                "name": "business_card_watchdog_enrichment_check",
                "description": "Report enrichment readiness and paid-provider gates without making provider calls.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "mode": {
                            "type": "string",
                            "enum": ["none", "public_web", "api", "all"],
                        },
                        "allow_paid_enrichment": {"type": "boolean", "default": False},
                    },
                },
            },
            {
                "name": "business_card_watchdog_enrichment_request",
                "description": "Create enrichment request/result artifacts for one job without making provider calls.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string"},
                        "run_id": {"type": "string"},
                        "mode": {
                            "type": "string",
                            "enum": ["public_web", "api", "all"],
                            "default": "public_web",
                        },
                        "requested_by": {"type": "string", "default": "operator"},
                        "allow_paid_enrichment": {"type": "boolean", "default": False},
                        "public_web_results": {"type": "array", "items": {"type": "object"}},
                        "provider_results": {"type": "array", "items": {"type": "object"}},
                    },
                    "required": ["job_id", "run_id"],
                },
            },
            {
                "name": "business_card_watchdog_public_web_enrichment_results",
                "description": "Record explicit public-web search results for one job and create reviewable enrichment result artifacts.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string"},
                        "run_id": {"type": "string"},
                        "searched_by": {"type": "string", "default": "operator"},
                        "results": {"type": "array", "items": {"type": "object"}},
                    },
                    "required": ["job_id", "run_id"],
                },
            },
            {
                "name": "business_card_watchdog_public_web_enrichment_handoff",
                "description": "Create a zero-network public-web search handoff from an existing enrichment request artifact.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string"},
                        "run_id": {"type": "string"},
                    },
                    "required": ["job_id", "run_id"],
                },
            },
            {
                "name": "business_card_watchdog_provider_enrichment_handoff",
                "description": "Create a zero-call paid-provider handoff from an existing provider enrichment request artifact.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string"},
                        "run_id": {"type": "string"},
                    },
                    "required": ["job_id", "run_id"],
                },
            },
            {
                "name": "business_card_watchdog_provider_enrichment_results",
                "description": "Record explicit paid-provider result rows for one job and create reviewable enrichment result artifacts.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string"},
                        "run_id": {"type": "string"},
                        "provider": {"type": "string", "default": "apollo"},
                        "submitted_by": {"type": "string", "default": "operator"},
                        "results": {"type": "array", "items": {"type": "object"}},
                    },
                    "required": ["job_id", "run_id"],
                },
            },
            {
                "name": "business_card_watchdog_watch_status",
                "description": "Report watched inputs, seen-file count, backlog, unsettled files, and last error.",
                "input_schema": {"type": "object", "properties": {}},
            },
            {
                "name": "business_card_watchdog_watch_backlog_preflight",
                "description": "Report redacted configured-watch backlog counts and explicit next steps without processing private files.",
                "input_schema": {
                    "type": "object",
                    "properties": {"write": {"type": "boolean", "default": True}},
                },
            },
            {
                "name": "business_card_watchdog_watch_dry_run_selection_handoff",
                "description": "Create or preview a redacted operator-response handoff before any configured private-source watch dry run.",
                "input_schema": {
                    "type": "object",
                    "properties": {"write": {"type": "boolean", "default": True}},
                },
            },
            {
                "name": "business_card_watchdog_watch_dry_run_operator_response_validation",
                "description": "Validate a watch dry-run operator response without processing watched files or storing the raw confirmation.",
                "input_schema": {
                    "type": "object",
                    "properties": {"response": {"type": "string"}},
                    "required": ["response"],
                },
            },
            {
                "name": "business_card_watchdog_watch_dry_run_command_copy_packet",
                "description": "Return the configured watch dry-run command only after response validation and acknowledgement.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "response": {"type": "string"},
                        "acknowledgement": {"type": "string", "default": ""},
                    },
                    "required": ["response"],
                },
            },
            {
                "name": "business_card_watchdog_watch_dry_run",
                "description": "Run a fixture-backed watched-folder dry-run harness without touching configured private watch inputs.",
                "input_schema": {"type": "object", "properties": {}},
            },
            {
                "name": "business_card_watchdog_doctor",
                "description": "Run user-scope runtime directory, skill, and watcher readiness checks.",
                "input_schema": {"type": "object", "properties": {}},
            },
        ],
    }


def manifest_json() -> str:
    return json.dumps(tool_manifest(), indent=2) + "\n"


def call_tool(
    tool_name: str,
    arguments: dict[str, Any] | None = None,
    *,
    config: AppConfig | None = None,
    config_path: Path | None = None,
) -> Any:
    args = arguments or {}
    service = BusinessCardService(config or load_config(config_path))
    if tool_name == "business_card_watchdog_process":
        return service.process_source(
            str(args["source"]),
            dry_run=bool(args.get("dry_run", True)),
            workers=int(args.get("workers", 2)),
        )
    if tool_name == "business_card_watchdog_status":
        return service.status()
    if tool_name == "business_card_watchdog_operator_dashboard":
        return service.operator_dashboard(
            run_id=str(args["run_id"]) if args.get("run_id") else None,
        )
    if tool_name == "business_card_watchdog_runtime_readiness":
        return service.runtime_readiness()
    if tool_name == "business_card_watchdog_service_recovery":
        return service.service_recovery_report(
            run_id=str(args["run_id"]) if args.get("run_id") else None,
        )
    if tool_name == "business_card_watchdog_live_target_candidates":
        return service.live_target_candidates(
            run_id=str(args["run_id"]) if args.get("run_id") else None,
            sink=str(args["sink"]) if args.get("sink") else None,
        )
    if tool_name == "business_card_watchdog_live_readiness_audit":
        return service.live_readiness_audit(
            run_id=str(args["run_id"]) if args.get("run_id") else None,
            sink=str(args["sink"]) if args.get("sink") else None,
            write=bool(args.get("write", True)),
        )
    if tool_name == "business_card_watchdog_live_selection_requirements":
        return service.live_selection_requirements(
            run_id=str(args["run_id"]) if args.get("run_id") else None,
            sink=str(args["sink"]) if args.get("sink") else None,
            write=bool(args.get("write", True)),
        )
    if tool_name == "business_card_watchdog_operator_selected_live_smoke_preflight":
        return service.operator_selected_live_smoke_preflight(
            run_id=str(args["run_id"]) if args.get("run_id") else None,
            sink=str(args["sink"]) if args.get("sink") else None,
            write=bool(args.get("write", True)),
        )
    if tool_name == "business_card_watchdog_runs_list":
        return service.list_runs()
    if tool_name == "business_card_watchdog_run_show":
        return service.get_run(str(args["run_id"]))
    if tool_name == "business_card_watchdog_run_summary":
        return service.run_summary(str(args["run_id"]))
    if tool_name == "business_card_watchdog_phase_report":
        return service.phase_report(str(args["run_id"]))
    if tool_name == "business_card_watchdog_pilot_readiness_report":
        return service.pilot_readiness_report(str(args["run_id"]))
    if tool_name == "business_card_watchdog_live_pilot_status":
        return service.live_pilot_status(
            run_id=str(args["run_id"]),
            write=bool(args.get("write", True)),
        )
    if tool_name == "business_card_watchdog_live_pilot_handoff":
        return service.live_pilot_handoff(
            run_id=str(args["run_id"]),
            write=bool(args.get("write", True)),
        )
    if tool_name == "business_card_watchdog_live_pilot_approval_packet":
        return service.live_pilot_approval_packet(
            run_id=str(args["run_id"]),
            job_id=str(args["job_id"]) if args.get("job_id") else None,
        )
    if tool_name == "business_card_watchdog_live_pilot_operator_response_validation":
        return service.validate_live_pilot_operator_response(
            run_id=str(args["run_id"]),
            response=str(args["response"]),
        )
    if tool_name == "business_card_watchdog_selected_live_target_preflight":
        return service.selected_live_target_preflight(
            run_id=str(args["run_id"]),
            response=str(args["response"]),
        )
    if tool_name == "business_card_watchdog_selected_live_target_artifact_preview":
        return service.selected_live_target_artifact_preview(
            run_id=str(args["run_id"]),
            response=str(args["response"]),
        )
    if tool_name == "business_card_watchdog_selected_live_target_from_response":
        return service.selected_live_target_from_response(
            run_id=str(args["run_id"]),
            response=str(args["response"]),
            write_selected_target=bool(args.get("write_selected_target", False)),
            reason=str(args.get("reason") or ""),
        )
    if tool_name == "business_card_watchdog_selected_live_target_handoff_from_response":
        return service.selected_live_target_handoff_from_response(
            run_id=str(args["run_id"]),
            response=str(args["response"]),
            write_audit=bool(args.get("write_audit", False)),
        )
    if tool_name == "business_card_watchdog_lookup_smoke_handoff_from_response":
        return service.lookup_smoke_handoff_from_response(
            run_id=str(args["run_id"]),
            response=str(args["response"]),
            write_handoff=bool(args.get("write_handoff", False)),
        )
    if tool_name == "business_card_watchdog_selected_lookup_smoke_execution_packet_from_response":
        return service.selected_lookup_smoke_execution_packet_from_response(
            run_id=str(args["run_id"]),
            response=str(args["response"]),
            execute_selected_lookup_smoke=bool(args.get("execute_selected_lookup_smoke", False)),
        )
    if tool_name == "business_card_watchdog_selected_write_pilot_execution_packet_from_response":
        return service.selected_write_pilot_execution_packet_from_response(
            run_id=str(args["run_id"]),
            response=str(args["response"]),
            execute_write_pilot=bool(args.get("execute_write_pilot", False)),
        )
    if tool_name == "business_card_watchdog_selected_readback_pilot_execution_packet_from_response":
        return service.selected_readback_pilot_execution_packet_from_response(
            run_id=str(args["run_id"]),
            response=str(args["response"]),
            execute_readback_pilot=bool(args.get("execute_readback_pilot", False)),
        )
    if tool_name == "business_card_watchdog_live_pilot_closeout_packet_from_response":
        return service.live_pilot_closeout_packet_from_response(
            run_id=str(args["run_id"]),
            response=str(args["response"]),
            write_closeout=bool(args.get("write_closeout", False)),
        )
    if tool_name == "business_card_watchdog_live_pilot_operator_workflow_packet_from_response":
        return service.live_pilot_operator_workflow_packet_from_response(
            run_id=str(args["run_id"]),
            response=str(args["response"]),
        )
    if tool_name == "business_card_watchdog_live_pilot_operator_rehearsal_from_response":
        return service.live_pilot_operator_rehearsal_from_response(
            run_id=str(args["run_id"]),
            response=str(args["response"]),
        )
    if tool_name == "business_card_watchdog_live_pilot_readiness_export_from_response":
        return service.live_pilot_readiness_export_from_response(
            run_id=str(args["run_id"]),
            response=str(args["response"]),
            write=bool(args.get("write", True)),
        )
    if tool_name == "business_card_watchdog_live_pilot_execution_checklist_from_response":
        return service.live_pilot_execution_checklist_from_response(
            run_id=str(args["run_id"]),
            response=str(args["response"]),
        )
    if tool_name == "business_card_watchdog_live_pilot_command_copy_packet_from_response":
        return service.live_pilot_command_copy_packet_from_response(
            run_id=str(args["run_id"]),
            response=str(args["response"]),
            acknowledgement=str(args.get("acknowledgement") or ""),
        )
    if tool_name == "business_card_watchdog_next_actions":
        return service.next_actions(
            run_id=str(args["run_id"]) if args.get("run_id") else None,
            limit=int(args.get("limit", 20)),
        )
    if tool_name == "business_card_watchdog_run_next_actions":
        return service.run_next_actions(
            run_id=str(args["run_id"]) if args.get("run_id") else None,
            limit=int(args.get("limit", 10)),
        )
    if tool_name == "business_card_watchdog_offline_pilot_gap_audit":
        return service.offline_pilot_gap_audit(write=bool(args.get("write", True)))
    if tool_name == "business_card_watchdog_multi_card_preclassification_drill":
        return service.multi_card_preclassification_drill()
    if tool_name == "business_card_watchdog_watch_dry_run_selection_drill":
        return service.watch_dry_run_selection_drill()
    if tool_name == "business_card_watchdog_watch_dry_run_execution_drill":
        return service.watch_dry_run_execution_drill()
    if tool_name == "business_card_watchdog_review_routing_drill":
        return service.review_routing_drill()
    if tool_name == "business_card_watchdog_live_pilot_rehearsal_drill":
        return service.live_pilot_rehearsal_drill()
    if tool_name == "business_card_watchdog_child_replacement_readiness_drill":
        return service.child_replacement_readiness_drill()
    if tool_name == "business_card_watchdog_jobs_list":
        return service.list_jobs(str(args["run_id"]) if args.get("run_id") else None)
    if tool_name == "business_card_watchdog_reviews_list":
        return service.review_queue(
            run_id=str(args["run_id"]) if args.get("run_id") else None,
            state=str(args.get("state") or "needs_review"),
            next_action=str(args["next_action"]) if args.get("next_action") else None,
            artifact_kind=str(args["artifact_kind"]) if args.get("artifact_kind") else None,
        )
    if tool_name == "business_card_watchdog_child_reviews_list":
        return service.child_review_queue(
            run_id=str(args["run_id"]) if args.get("run_id") else None,
            state=str(args.get("state") or "needs_review"),
        )
    if tool_name == "business_card_watchdog_child_review_submit":
        return service.submit_child_review(
            run_id=str(args["run_id"]),
            candidate_id=str(args["candidate_id"]),
            reviewer=str(args.get("reviewer") or "operator"),
            action=str(args.get("action") or "keep_needs_review"),
            field_corrections=dict(args.get("field_corrections") or {}),
            notes=str(args.get("notes") or ""),
        )
    if tool_name == "business_card_watchdog_child_route_prep_queue":
        return service.child_route_prep_queue(
            run_id=str(args["run_id"]) if args.get("run_id") else None,
            state=str(args.get("state") or "approved_for_dedupe"),
        )
    if tool_name == "business_card_watchdog_child_route_prepare":
        return service.prepare_child_route(
            run_id=str(args["run_id"]),
            candidate_id=str(args["candidate_id"]),
            dry_run=bool(args.get("dry_run", True)),
        )
    if tool_name == "business_card_watchdog_child_sink_lookup_result":
        return service.record_child_sink_lookup_result(
            run_id=str(args["run_id"]),
            candidate_id=str(args["candidate_id"]),
            matches_by_sink=dict(args.get("matches_by_sink") or {}),
        )
    if tool_name == "business_card_watchdog_child_downstream_duplicate_assessment":
        return service.assess_child_downstream_duplicates(
            run_id=str(args["run_id"]),
            candidate_id=str(args["candidate_id"]),
        )
    if tool_name == "business_card_watchdog_child_duplicate_resolution":
        return service.resolve_child_duplicate(
            run_id=str(args["run_id"]),
            candidate_id=str(args["candidate_id"]),
            reviewer=str(args.get("reviewer") or "operator"),
            decision=str(args["decision"]),
            target_identity=str(args.get("target_identity") or ""),
            reason=str(args.get("reason") or ""),
        )
    if tool_name == "business_card_watchdog_child_sink_plan_gate":
        return service.child_sink_plan_gate(
            run_id=str(args["run_id"]),
            candidate_id=str(args["candidate_id"]),
        )
    if tool_name == "business_card_watchdog_child_sink_apply_preflight":
        return service.child_sink_apply_preflight(
            run_id=str(args["run_id"]),
            candidate_id=str(args["candidate_id"]),
            apply=bool(args.get("apply", False)),
        )
    if tool_name == "business_card_watchdog_child_selected_target_handoff":
        return service.child_selected_target_handoff(
            run_id=str(args["run_id"]),
            candidate_id=str(args["candidate_id"]),
            sink=str(args["sink"]),
            operator=str(args.get("operator") or "operator"),
            scope=str(args.get("scope") or "write"),
            reason=str(args.get("reason") or ""),
        )
    if tool_name == "business_card_watchdog_child_selected_target_response_validation":
        return service.validate_child_selected_target_response(
            run_id=str(args["run_id"]),
            candidate_id=str(args["candidate_id"]),
            response=str(args["response"]),
        )
    if tool_name == "business_card_watchdog_child_selected_target_execution_checklist":
        return service.child_selected_target_execution_checklist(
            run_id=str(args["run_id"]),
            candidate_id=str(args["candidate_id"]),
            response=str(args["response"]),
        )
    if tool_name == "business_card_watchdog_child_selected_target_command_copy_packet":
        return service.child_selected_target_command_copy_packet(
            run_id=str(args["run_id"]),
            candidate_id=str(args["candidate_id"]),
            response=str(args["response"]),
            acknowledgement=str(args.get("acknowledgement") or ""),
        )
    if tool_name == "business_card_watchdog_child_selected_target_audit":
        return service.child_selected_target_audit(
            run_id=str(args["run_id"]),
            candidate_id=str(args["candidate_id"]),
            sink=str(args["sink"]) if args.get("sink") is not None else None,
            operator=str(args["operator"]) if args.get("operator") is not None else None,
            scope=str(args["scope"]) if args.get("scope") is not None else None,
            write=bool(args.get("write", True)),
        )
    if tool_name == "business_card_watchdog_child_selected_target_abandonment":
        return service.abandon_child_selected_target(
            run_id=str(args["run_id"]),
            candidate_id=str(args["candidate_id"]),
            operator=str(args["operator"]),
            reason=str(args["reason"]),
        )
    if tool_name == "business_card_watchdog_child_selected_target_replacement_reset":
        return service.child_selected_target_replacement_reset(
            run_id=str(args["run_id"]),
            candidate_id=str(args["candidate_id"]),
            sink=str(args["sink"]),
            operator=str(args["operator"]),
            scope=str(args.get("scope") or "write"),
            reset_by=str(args.get("reset_by") or "operator"),
            reason=str(args.get("reason") or ""),
        )
    if tool_name == "business_card_watchdog_child_replacement_handoff_refresh":
        return service.refresh_child_replacement_handoff(
            run_id=str(args["run_id"]),
            candidate_id=str(args["candidate_id"]),
            sink=str(args["sink"]),
            operator=str(args["operator"]),
            scope=str(args.get("scope") or "write"),
            reason=str(args.get("reason") or ""),
        )
    if tool_name == "business_card_watchdog_child_replacement_response_validation":
        return service.validate_child_replacement_response(
            run_id=str(args["run_id"]),
            candidate_id=str(args["candidate_id"]),
            response=str(args["response"]),
        )
    if tool_name == "business_card_watchdog_child_replacement_execution_checklist":
        return service.child_replacement_execution_checklist(
            run_id=str(args["run_id"]),
            candidate_id=str(args["candidate_id"]),
            response=str(args["response"]),
        )
    if tool_name == "business_card_watchdog_child_replacement_command_copy_packet":
        return service.child_replacement_command_copy_packet(
            run_id=str(args["run_id"]),
            candidate_id=str(args["candidate_id"]),
            response=str(args["response"]),
            acknowledgement=str(args.get("acknowledgement") or ""),
        )
    if tool_name == "business_card_watchdog_child_replacement_closeout_status":
        return service.child_replacement_closeout_status(
            run_id=str(args["run_id"]),
            candidate_id=str(args["candidate_id"]),
        )
    if tool_name == "business_card_watchdog_review_bundle":
        return service.review_bundle(
            run_id=str(args["run_id"]),
            state=str(args.get("state") or "all"),
            write=bool(args.get("write", True)),
        )
    if tool_name == "business_card_watchdog_review_html":
        return service.review_html(
            run_id=str(args["run_id"]),
            state=str(args.get("state") or "all"),
            write=bool(args.get("write", True)),
        )
    if tool_name == "business_card_watchdog_review_workbook":
        return service.review_workbook(
            run_id=str(args["run_id"]),
            state=str(args.get("state") or "all"),
            write=bool(args.get("write", True)),
        )
    if tool_name == "business_card_watchdog_apply_review_decisions":
        if args.get("decisions_csv"):
            if bool(args.get("preview", False)):
                return service.preview_review_workbook_csv(
                    run_id=str(args["run_id"]),
                    reviewer=str(args.get("reviewer") or "operator"),
                    csv_text=str(args["decisions_csv"]),
                    write=bool(args.get("preview_write", False)),
                )
            return service.apply_review_workbook_csv(
                run_id=str(args["run_id"]),
                reviewer=str(args.get("reviewer") or "operator"),
                csv_text=str(args["decisions_csv"]),
            )
        return service.apply_review_decisions(
            run_id=str(args["run_id"]),
            reviewer=str(args.get("reviewer") or "operator"),
            decisions=list(args.get("decisions") or []),
        )
    if tool_name == "business_card_watchdog_review_workbook_validation":
        return service.preview_review_workbook_csv(
            run_id=str(args["run_id"]),
            reviewer=str(args.get("reviewer") or "operator"),
            csv_text=str(args["decisions_csv"]),
            write=bool(args.get("preview_write", False)),
        )
    if tool_name == "business_card_watchdog_job_show":
        return service.get_job(
            str(args["job_id"]),
            run_id=str(args["run_id"]) if args.get("run_id") else None,
        )
    if tool_name == "business_card_watchdog_job_review":
        return service.submit_review(
            job_id=str(args["job_id"]),
            run_id=str(args["run_id"]),
            reviewer=str(args.get("reviewer") or "operator"),
            action=str(args.get("action") or "keep_needs_review"),
            field_corrections=dict(args.get("field_corrections") or {}),
            crop_selection=dict(args.get("crop_selection") or {}),
            approved_enrichment_fields=list(args.get("approved_enrichment_fields") or []),
            duplicate_resolution=dict(args.get("duplicate_resolution") or {}),
            notes=str(args.get("notes") or ""),
        )
    if tool_name == "business_card_watchdog_sinks_check":
        return service.sink_readiness()
    if tool_name == "business_card_watchdog_sink_plan":
        return service.plan_sinks_for_job(
            job_id=str(args["job_id"]),
            run_id=str(args["run_id"]),
            dry_run=bool(args.get("dry_run", True)),
        )
    if tool_name == "business_card_watchdog_sink_lookup_plan":
        return service.plan_sink_lookup_for_job(
            job_id=str(args["job_id"]),
            run_id=str(args["run_id"]),
            dry_run=bool(args.get("dry_run", True)),
        )
    if tool_name == "business_card_watchdog_sink_apply_preflight":
        return service.preflight_sink_apply(
            job_id=str(args["job_id"]),
            run_id=str(args["run_id"]),
            apply=bool(args.get("apply", False)),
        )
    if tool_name == "business_card_watchdog_sink_apply_decision":
        return service.decide_sink_apply(
            job_id=str(args["job_id"]),
            run_id=str(args["run_id"]),
            decision=str(args["decision"]),
            reviewer=str(args.get("reviewer") or "operator"),
            reason=str(args.get("reason") or ""),
        )
    if tool_name == "business_card_watchdog_sink_apply":
        return service.apply_sinks_for_job(
            job_id=str(args["job_id"]),
            run_id=str(args["run_id"]),
            apply=bool(args.get("apply", False)),
            simulate=bool(args.get("simulate", False)),
        )
    if tool_name == "business_card_watchdog_sink_apply_pilot_readiness":
        return service.build_sink_apply_pilot_readiness_for_job(
            job_id=str(args["job_id"]),
            run_id=str(args["run_id"]),
            sink=str(args["sink"]) if args.get("sink") else None,
        )
    if tool_name == "business_card_watchdog_sink_apply_pilot_report":
        return service.build_sink_apply_pilot_report_for_job(
            job_id=str(args["job_id"]),
            run_id=str(args["run_id"]),
        )
    if tool_name == "business_card_watchdog_sink_apply_pilot_bundle":
        return service.build_sink_apply_pilot_bundle_for_job(
            job_id=str(args["job_id"]),
            run_id=str(args["run_id"]),
            sink=str(args["sink"]),
            operator=str(args.get("operator") or "operator"),
        )
    if tool_name == "business_card_watchdog_sink_adapter_request":
        return service.build_sink_adapter_request_for_job(
            job_id=str(args["job_id"]),
            run_id=str(args["run_id"]),
            phase=str(args.get("phase") or "lookup"),  # type: ignore[arg-type]
        )
    if tool_name == "business_card_watchdog_sink_lookup_result":
        return service.record_sink_lookup_result_for_job(
            job_id=str(args["job_id"]),
            run_id=str(args["run_id"]),
            matches_by_sink=dict(args.get("matches_by_sink") or {}),
        )
    if tool_name == "business_card_watchdog_sink_lookup_pilot":
        return service.execute_sink_lookup_pilot_for_job(
            job_id=str(args["job_id"]),
            run_id=str(args["run_id"]),
            sink=str(args["sink"]),
            approved_by=str(args["approved_by"]),
            matches=list(args.get("matches") or []),
            simulate=bool(args.get("simulate", True)),
        )
    if tool_name == "business_card_watchdog_sink_lookup_readiness":
        return service.live_lookup_readiness_report(
            job_id=str(args["job_id"]),
            run_id=str(args["run_id"]),
            sink=str(args["sink"]),
        )
    if tool_name == "business_card_watchdog_sink_lookup_smoke_handoff":
        return service.build_sink_lookup_smoke_handoff_for_job(
            job_id=str(args["job_id"]),
            run_id=str(args["run_id"]),
            sink=str(args["sink"]),
            approved_by=str(args.get("approved_by") or "operator"),
        )
    if tool_name == "business_card_watchdog_live_selection_packet":
        return service.live_selection_packet(
            job_id=str(args["job_id"]),
            run_id=str(args["run_id"]),
            sink=str(args["sink"]),
            operator=str(args["operator"]),
            scope=str(args.get("scope") or "lookup"),
            reason=str(args.get("reason") or ""),
            write=bool(args.get("write", True)),
        )
    if tool_name == "business_card_watchdog_selected_live_target":
        return service.select_live_target_for_job(
            job_id=str(args["job_id"]),
            run_id=str(args["run_id"]),
            sink=str(args["sink"]),
            operator=str(args["operator"]),
            scope=str(args.get("scope") or "lookup"),
            reason=str(args.get("reason") or ""),
            safety_confirmation=str(args["safety_confirmation"]),
        )
    if tool_name == "business_card_watchdog_selected_live_target_audit":
        return service.selected_live_target_audit(
            job_id=str(args["job_id"]),
            run_id=str(args["run_id"]),
            scope=str(args["scope"]) if args.get("scope") else None,
            write=bool(args.get("write", True)),
        )
    if tool_name == "business_card_watchdog_live_pilot_abandonment":
        return service.live_pilot_abandon_for_job(
            job_id=str(args["job_id"]),
            run_id=str(args["run_id"]),
            operator=str(args["operator"]),
            reason=str(args["reason"]),
        )
    if tool_name == "business_card_watchdog_selected_lookup_smoke":
        return service.execute_selected_lookup_smoke_for_job(
            job_id=str(args["job_id"]),
            run_id=str(args["run_id"]),
        )
    if tool_name == "business_card_watchdog_sink_write_pilot":
        return service.execute_sink_write_pilot_for_job(
            job_id=str(args["job_id"]),
            run_id=str(args["run_id"]),
            sink=str(args["sink"]),
            approved_by=str(args["approved_by"]),
            simulate=bool(args.get("simulate", True)),
        )
    if tool_name == "business_card_watchdog_sink_readback_pilot":
        return service.execute_sink_readback_pilot_for_job(
            job_id=str(args["job_id"]),
            run_id=str(args["run_id"]),
            sink=str(args["sink"]),
            approved_by=str(args["approved_by"]),
            readback=dict(args.get("readback") or {}),
            simulate=bool(args.get("simulate", True)),
        )
    if tool_name == "business_card_watchdog_live_pilot_closeout":
        return service.build_live_pilot_closeout_for_job(
            job_id=str(args["job_id"]),
            run_id=str(args["run_id"]),
            write=bool(args.get("write", True)),
        )
    if tool_name == "business_card_watchdog_downstream_duplicate_assessment":
        return service.assess_downstream_duplicates_for_job(
            job_id=str(args["job_id"]),
            run_id=str(args["run_id"]),
        )
    if tool_name == "business_card_watchdog_enrichment_check":
        return service.enrichment_readiness(
            mode=str(args["mode"]) if args.get("mode") else None,
            allow_paid_enrichment=bool(args.get("allow_paid_enrichment", False)),
        )
    if tool_name == "business_card_watchdog_enrichment_request":
        return service.request_enrichment(
            job_id=str(args["job_id"]),
            run_id=str(args["run_id"]),
            mode=str(args.get("mode") or "public_web"),
            requested_by=str(args.get("requested_by") or "operator"),
            allow_paid_enrichment=bool(args.get("allow_paid_enrichment", False)),
            public_web_results=list(args.get("public_web_results") or []),
            provider_results=list(args.get("provider_results") or []),
        )
    if tool_name == "business_card_watchdog_public_web_enrichment_results":
        return service.record_public_web_enrichment_results(
            job_id=str(args["job_id"]),
            run_id=str(args["run_id"]),
            searched_by=str(args.get("searched_by") or "operator"),
            results=list(args.get("results") or []),
        )
    if tool_name == "business_card_watchdog_public_web_enrichment_handoff":
        return service.build_public_web_enrichment_handoff(
            job_id=str(args["job_id"]),
            run_id=str(args["run_id"]),
        )
    if tool_name == "business_card_watchdog_provider_enrichment_handoff":
        return service.build_provider_enrichment_handoff(
            job_id=str(args["job_id"]),
            run_id=str(args["run_id"]),
        )
    if tool_name == "business_card_watchdog_provider_enrichment_results":
        return service.record_provider_enrichment_results(
            job_id=str(args["job_id"]),
            run_id=str(args["run_id"]),
            provider=str(args.get("provider") or "apollo"),
            submitted_by=str(args.get("submitted_by") or "operator"),
            results=list(args.get("results") or []),
        )
    if tool_name == "business_card_watchdog_watch_status":
        return service.watch_status()
    if tool_name == "business_card_watchdog_watch_backlog_preflight":
        return service.watch_backlog_preflight(write=bool(args.get("write", True)))
    if tool_name == "business_card_watchdog_watch_dry_run_selection_handoff":
        return service.watch_dry_run_selection_handoff(write=bool(args.get("write", True)))
    if tool_name == "business_card_watchdog_watch_dry_run_operator_response_validation":
        return service.validate_watch_dry_run_operator_response(response=str(args["response"]))
    if tool_name == "business_card_watchdog_watch_dry_run_command_copy_packet":
        return service.watch_dry_run_command_copy_packet(
            response=str(args["response"]),
            acknowledgement=str(args.get("acknowledgement") or ""),
        )
    if tool_name == "business_card_watchdog_watch_dry_run":
        return service.watch_dry_run_harness()
    if tool_name == "business_card_watchdog_doctor":
        return service.doctor()
    raise ValueError(f"unknown MCP tool: {tool_name}")
