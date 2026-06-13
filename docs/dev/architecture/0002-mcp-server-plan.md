# MCP Server Plan

Status: Planned implementation contract  
Authority: `PRODUCT_SPEC.md`, Plan 0002

## Purpose

Business Card Watchdog currently exposes an MCP tool manifest. The production MCP server should execute the same shared service-layer methods used by CLI and API so agent-facing behavior cannot bypass ledger, review, watcher, or sink-readiness policy.

## Tool-To-Service Mapping

- `business_card_watchdog_process` -> `BusinessCardService.process_source`
- `business_card_watchdog_status` -> `BusinessCardService.status`
- `business_card_watchdog_runs_list` -> `BusinessCardService.list_runs`
- `business_card_watchdog_run_show` -> `BusinessCardService.get_run`
- `business_card_watchdog_jobs_list` -> `BusinessCardService.list_jobs`
- `business_card_watchdog_job_show` -> `BusinessCardService.get_job`
- `business_card_watchdog_job_review` -> `BusinessCardService.submit_review`
- `business_card_watchdog_sinks_check` -> `BusinessCardService.sink_readiness`
- `business_card_watchdog_watch_status` -> `BusinessCardService.watch_status`
- `business_card_watchdog_doctor` -> `BusinessCardService.doctor`

## Runtime Rules

- Load config from the same user-scope config path as CLI unless the MCP host passes an explicit config path.
- Keep external writes dry-run by default.
- Never expose private image or OCR content inline by default; return artifact paths and run/job IDs.
- Validate review submissions through the same schema used by CLI/API.
- Return structured errors for missing runs/jobs, unsupported correction fields, and blocked sink readiness.

## Implementation Shape

Future implementation should add a transport module such as `business_card_watchdog.mcp_server` that:

- imports `BusinessCardService`
- registers each tool in `mcp.py`
- delegates directly to the matching service method
- serializes responses as JSON-compatible dict/list primitives
- includes tests proving the manifest schema and handler map stay in sync

The static manifest remains useful for clients that need schema discovery before the server transport is installed.

