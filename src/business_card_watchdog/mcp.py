from __future__ import annotations

import json


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
                            "enum": ["approve_for_routing", "keep_needs_review"],
                            "default": "keep_needs_review",
                        },
                        "field_corrections": {"type": "object"},
                        "crop_selection": {"type": "object"},
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
