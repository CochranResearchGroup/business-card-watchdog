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
                    },
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
                "name": "business_card_watchdog_apply_review_decisions",
                "description": "Apply a batch of run-scoped review decisions through the shared review submission path.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "reviewer": {"type": "string", "default": "operator"},
                        "decisions": {"type": "array", "items": {"type": "object"}},
                    },
                    "required": ["run_id", "decisions"],
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
                "description": "Create a zero-write one-job live apply pilot readiness artifact.",
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
                "name": "business_card_watchdog_watch_status",
                "description": "Report watched inputs, seen-file count, backlog, unsettled files, and last error.",
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
    if tool_name == "business_card_watchdog_runs_list":
        return service.list_runs()
    if tool_name == "business_card_watchdog_run_show":
        return service.get_run(str(args["run_id"]))
    if tool_name == "business_card_watchdog_run_summary":
        return service.run_summary(str(args["run_id"]))
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
    if tool_name == "business_card_watchdog_jobs_list":
        return service.list_jobs(str(args["run_id"]) if args.get("run_id") else None)
    if tool_name == "business_card_watchdog_reviews_list":
        return service.review_queue(
            run_id=str(args["run_id"]) if args.get("run_id") else None,
            state=str(args.get("state") or "needs_review"),
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
    if tool_name == "business_card_watchdog_apply_review_decisions":
        return service.apply_review_decisions(
            run_id=str(args["run_id"]),
            reviewer=str(args.get("reviewer") or "operator"),
            decisions=list(args.get("decisions") or []),
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
    if tool_name == "business_card_watchdog_watch_status":
        return service.watch_status()
    if tool_name == "business_card_watchdog_doctor":
        return service.doctor()
    raise ValueError(f"unknown MCP tool: {tool_name}")
