import csv
import json
from io import StringIO
from pathlib import Path

from business_card_watchdog.config import AppConfig, EnrichmentConfig, EnrichmentProviderConfig, SinkConfig
from business_card_watchdog.contact import build_contact_candidate
from business_card_watchdog.mcp import call_tool, tool_manifest
from business_card_watchdog.mcp_server import serve_jsonl

from test_service import make_recorded_run


def test_manifest_has_process_tool() -> None:
    manifest = tool_manifest()
    names = {tool["name"] for tool in manifest["tools"]}
    assert "business_card_watchdog_process" in names
    assert "business_card_watchdog_runs_list" in names
    assert "business_card_watchdog_job_show" in names
    assert "business_card_watchdog_job_review" in names
    assert "business_card_watchdog_run_summary" in names
    assert "business_card_watchdog_phase_report" in names
    assert "business_card_watchdog_pilot_readiness_report" in names
    assert "business_card_watchdog_next_actions" in names
    assert "business_card_watchdog_run_next_actions" in names
    assert "business_card_watchdog_reviews_list" in names
    assert "business_card_watchdog_review_bundle" in names
    assert "business_card_watchdog_review_html" in names
    assert "business_card_watchdog_review_workbook" in names
    assert "business_card_watchdog_review_workbook_validation" in names
    assert "business_card_watchdog_apply_review_decisions" in names
    assert "business_card_watchdog_sinks_check" in names
    assert "business_card_watchdog_sink_plan" in names
    assert "business_card_watchdog_sink_lookup_plan" in names
    assert "business_card_watchdog_sink_apply_preflight" in names
    assert "business_card_watchdog_sink_apply_decision" in names
    assert "business_card_watchdog_sink_apply" in names
    assert "business_card_watchdog_sink_apply_pilot_readiness" in names
    assert "business_card_watchdog_sink_apply_pilot_report" in names
    assert "business_card_watchdog_sink_adapter_request" in names
    assert "business_card_watchdog_sink_lookup_pilot" in names
    assert "business_card_watchdog_sink_lookup_readiness" in names
    assert "business_card_watchdog_sink_write_pilot" in names
    assert "business_card_watchdog_sink_readback_pilot" in names
    assert "business_card_watchdog_sink_lookup_result" in names
    assert "business_card_watchdog_downstream_duplicate_assessment" in names
    assert "business_card_watchdog_enrichment_check" in names
    assert "business_card_watchdog_enrichment_request" in names
    assert "business_card_watchdog_public_web_enrichment_handoff" in names
    assert "business_card_watchdog_public_web_enrichment_results" in names
    assert "business_card_watchdog_provider_enrichment_handoff" in names
    assert "business_card_watchdog_provider_enrichment_results" in names
    assert "business_card_watchdog_doctor" in names
    review_tool = next(tool for tool in manifest["tools"] if tool["name"] == "business_card_watchdog_job_review")
    assert "approve_enrichment_merge" in review_tool["input_schema"]["properties"]["action"]["enum"]
    assert "request_enrichment" in review_tool["input_schema"]["properties"]["action"]["enum"]
    assert "resolve_duplicate" in review_tool["input_schema"]["properties"]["action"]["enum"]
    assert "reject_not_card" in review_tool["input_schema"]["properties"]["action"]["enum"]
    assert "skip" in review_tool["input_schema"]["properties"]["action"]["enum"]


def test_mcp_call_tool_dispatches_to_service(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    artifact_dir = config.runs_dir / run_id / "artifacts" / job_id
    (artifact_dir / "enrichment_result.json").write_text(
        json.dumps(
            {
                "schema": "business-card-watchdog.enrichment-result.v1",
                "merge_proposals": [
                    {
                        "field": "notes",
                        "value": "Public-web corroboration candidate: https://example.test/mcp",
                        "source": "public_web",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (artifact_dir / "duplicate_assessment.json").write_text(
        '{"schema": "business-card-watchdog.duplicate-assessment.v1", "state": "possible_duplicate"}\n',
        encoding="utf-8",
    )

    summary = call_tool("business_card_watchdog_run_summary", {"run_id": run_id}, config=config)
    phase_report = call_tool("business_card_watchdog_phase_report", {"run_id": run_id}, config=config)
    readiness_report = call_tool("business_card_watchdog_pilot_readiness_report", {"run_id": run_id}, config=config)
    reviews = call_tool(
        "business_card_watchdog_reviews_list",
        {
            "run_id": run_id,
            "next_action": "review_contact",
            "artifact_kind": "contact_spec",
        },
        config=config,
    )
    review_bundle = call_tool("business_card_watchdog_review_bundle", {"run_id": run_id}, config=config)
    review_html = call_tool("business_card_watchdog_review_html", {"run_id": run_id}, config=config)
    review_workbook = call_tool("business_card_watchdog_review_workbook", {"run_id": run_id}, config=config)
    next_actions = call_tool("business_card_watchdog_next_actions", {"run_id": run_id}, config=config)
    review_import = call_tool(
        "business_card_watchdog_apply_review_decisions",
        {
            "run_id": run_id,
            "reviewer": "mcp-batch",
            "decisions": [
                {
                    "job_id": job_id,
                    "action": "approve_for_routing",
                    "field_corrections": {"full_name": "MCP Batch"},
                }
            ],
        },
        config=config,
    )
    job = call_tool("business_card_watchdog_job_show", {"job_id": job_id, "run_id": run_id}, config=config)
    lookup = call_tool(
        "business_card_watchdog_sink_lookup_plan",
        {"job_id": job_id, "run_id": run_id},
        config=config,
    )
    preflight = call_tool(
        "business_card_watchdog_sink_apply_preflight",
        {"job_id": job_id, "run_id": run_id},
        config=config,
    )
    apply_decision = call_tool(
        "business_card_watchdog_sink_apply_decision",
        {"job_id": job_id, "run_id": run_id, "decision": "approve", "reviewer": "mcp-test"},
        config=config,
    )
    apply_result = call_tool(
        "business_card_watchdog_sink_apply",
        {"job_id": job_id, "run_id": run_id, "apply": True, "simulate": True},
        config=config,
    )
    pilot_readiness = call_tool(
        "business_card_watchdog_sink_apply_pilot_readiness",
        {"job_id": job_id, "run_id": run_id, "sink": "google_contacts"},
        config=config,
    )
    write_pilot = call_tool(
        "business_card_watchdog_sink_write_pilot",
        {
            "job_id": job_id,
            "run_id": run_id,
            "sink": "google_contacts",
            "approved_by": "mcp-operator",
        },
        config=config,
    )
    adapter_request = call_tool(
        "business_card_watchdog_sink_adapter_request",
        {"job_id": job_id, "run_id": run_id, "phase": "readback"},
        config=config,
    )
    readback_pilot = call_tool(
        "business_card_watchdog_sink_readback_pilot",
        {
            "job_id": job_id,
            "run_id": run_id,
            "sink": "google_contacts",
            "approved_by": "mcp-operator",
        },
        config=config,
    )
    pilot_report = call_tool(
        "business_card_watchdog_sink_apply_pilot_report",
        {"job_id": job_id, "run_id": run_id},
        config=config,
    )
    lookup_pilot = call_tool(
        "business_card_watchdog_sink_lookup_pilot",
        {
            "job_id": job_id,
            "run_id": run_id,
            "sink": "google_contacts",
            "approved_by": "mcp-operator",
            "matches": [
                {"resource_id": "people/c456", "confidence": 0.93, "basis": ["email"]}
            ],
        },
        config=config,
    )
    lookup_readiness = call_tool(
        "business_card_watchdog_sink_lookup_readiness",
        {"job_id": job_id, "run_id": run_id, "sink": "google_contacts"},
        config=config,
    )
    lookup_result = call_tool(
        "business_card_watchdog_sink_lookup_result",
        {
            "job_id": job_id,
            "run_id": run_id,
            "matches_by_sink": {
                "google_contacts": [
                    {"resource_id": "people/c123", "confidence": 0.91, "basis": ["email"]}
                ]
            },
        },
        config=config,
    )
    downstream_duplicate = call_tool(
        "business_card_watchdog_downstream_duplicate_assessment",
        {"job_id": job_id, "run_id": run_id},
        config=config,
    )
    merge = call_tool(
        "business_card_watchdog_job_review",
        {
            "job_id": job_id,
            "run_id": run_id,
            "action": "approve_enrichment_merge",
            "approved_enrichment_fields": ["notes"],
        },
        config=config,
    )
    duplicate = call_tool(
        "business_card_watchdog_job_review",
        {
            "job_id": job_id,
            "run_id": run_id,
            "action": "resolve_duplicate",
            "duplicate_resolution": {"decision": "create_new", "reason": "separate contact"},
        },
        config=config,
    )
    run_next = call_tool(
        "business_card_watchdog_run_next_actions",
        {"run_id": run_id, "limit": 1},
        config=config,
    )

    assert summary["needs_review_count"] == 1
    assert phase_report["schema"] == "business-card-watchdog.phase-report.v1"
    assert phase_report["review_workbook_preview"]["schema"] == (
        "business-card-watchdog.review-workbook-preview-phase.v1"
    )
    assert phase_report["review_workbook_preview"]["state"] == "not_started"
    assert phase_report["dashboard_summary"]["schema"] == "business-card-watchdog.phase-dashboard-summary.v1"
    assert phase_report["dashboard_summary"]["blocked_phases"] == [{"phase": "review", "count": 1}]
    assert phase_report["phases"][2]["phase"] == "review"
    assert phase_report["phases"][2]["counts"]["blocked"] == 1
    assert readiness_report["schema"] == "business-card-watchdog.pilot-readiness-report.v1"
    assert readiness_report["blocked_job_ids"] == [job_id]
    assert [entry["job_id"] for entry in reviews] == [job_id]
    assert review_bundle["schema"] == "business-card-watchdog.review-bundle.v1"
    assert review_bundle["entries"][0]["job_id"] == job_id
    assert review_bundle["entries"][0]["next_action"]["action"] == "review_contact"
    assert review_bundle["groups"]["by_next_action"]["review_contact"]["count"] == 1
    assert review_bundle["decision_import_template"][0]["job_id"] == job_id
    assert review_html["schema"] == "business-card-watchdog.review-html.v1"
    assert "Business Card Review" in review_html["html"]
    assert review_workbook["schema"] == "business-card-watchdog.review-workbook.v1"
    workbook_rows = list(csv.DictReader(StringIO(review_workbook["csv"])))
    assert workbook_rows[0]["job_id"] == job_id
    assert workbook_rows[0]["next_action"] == "review_contact"
    assert workbook_rows[0]["review_action"] == "approve_for_routing"
    workbook_rows[0]["review_action"] = "approve_for_routing"
    workbook_rows[0]["corrected_full_name"] = "MCP Workbook"
    workbook_csv = StringIO()
    workbook_writer = csv.DictWriter(workbook_csv, fieldnames=list(workbook_rows[0]))
    workbook_writer.writeheader()
    workbook_writer.writerows(workbook_rows)
    workbook_preview = call_tool(
        "business_card_watchdog_apply_review_decisions",
        {
            "run_id": run_id,
            "reviewer": "mcp-workbook",
            "decisions_csv": workbook_csv.getvalue(),
            "preview": True,
            "preview_write": True,
        },
        config=config,
    )
    assert workbook_preview["schema"] == "business-card-watchdog.review-workbook-preview.v1"
    assert workbook_preview["ready_count"] == 1
    assert "row_number,status,run_id,job_id,action,errors,warnings" in workbook_preview["validation_csv"]
    assert Path(workbook_preview["validation_csv_path"]).exists()
    assert workbook_preview["writes_attempted"] == 0
    workbook_validation = call_tool(
        "business_card_watchdog_review_workbook_validation",
        {"run_id": run_id, "reviewer": "mcp-workbook", "decisions_csv": workbook_csv.getvalue()},
        config=config,
    )
    assert workbook_validation["schema"] == "business-card-watchdog.review-workbook-preview.v1"
    assert workbook_validation["ready_count"] == 1
    assert "row_number,status,run_id,job_id,action,errors,warnings" in workbook_validation["validation_csv"]
    assert "validation_csv_path" not in workbook_validation
    workbook_import = call_tool(
        "business_card_watchdog_apply_review_decisions",
        {"run_id": run_id, "reviewer": "mcp-workbook", "decisions_csv": workbook_csv.getvalue()},
        config=config,
    )
    assert workbook_import["import"]["source_format"] == "csv"
    assert workbook_import["results"][0]["job_state"] == "ready_to_route"
    assert review_import["import"]["schema"] == "business-card-watchdog.review-decisions-import.v1"
    assert review_import["results"][0]["job_state"] == "ready_to_route"
    assert next_actions["actions"][0]["action"] == "review_contact"
    assert job["job_id"] == job_id
    assert lookup["lookup_plan"]["network_calls_made"] == 0
    assert preflight["preflight"]["state"] == "preview"
    assert preflight["preflight"]["writes_attempted"] == 0
    assert apply_decision["decision"]["state"] == "approved_for_apply"
    assert apply_decision["decision"]["network_calls_made"] == 0
    assert apply_result["result"]["state"] == "mock_applied"
    assert apply_result["result"]["writes_attempted"] == 0
    assert apply_result["result"]["readback"][0]["simulated"] is True
    assert pilot_readiness["readiness"]["schema"] == "business-card-watchdog.sink-apply-pilot-readiness.v1"
    assert pilot_readiness["readiness"]["selected_sink"] == "google_contacts"
    assert write_pilot["pilot"]["schema"] == "business-card-watchdog.sink-write-pilot.v1"
    assert write_pilot["pilot"]["writes_attempted"] == 0
    assert write_pilot["result"]["state"] == "mock_applied"
    assert adapter_request["request"]["phase"] == "readback"
    assert adapter_request["request"]["network_calls_made"] == 0
    assert readback_pilot["pilot"]["schema"] == "business-card-watchdog.sink-readback-pilot.v1"
    assert readback_pilot["pilot"]["writes_attempted"] == 0
    assert readback_pilot["pilot"]["network_calls_made"] == 0
    assert pilot_report["report"]["schema"] == "business-card-watchdog.sink-apply-pilot-report.v1"
    assert pilot_report["report"]["state"] == "complete"
    assert lookup_pilot["pilot"]["schema"] == "business-card-watchdog.sink-lookup-pilot.v1"
    assert lookup_pilot["pilot"]["approved_by"] == "mcp-operator"
    assert lookup_pilot["pilot"]["writes_attempted"] == 0
    assert lookup_readiness["schema"] == "business-card-watchdog.live-lookup-readiness.v1"
    assert lookup_readiness["state"] == "blocked"
    assert lookup_result["result"]["state"] == "possible_duplicate"
    assert lookup_result["result"]["network_calls_made"] == 0
    assert downstream_duplicate["assessment"]["state"] == "strong_duplicate"
    assert downstream_duplicate["job"]["state"] == "needs_review"
    assert merge["submission"]["approved_enrichment_fields"] == ["notes"]
    assert duplicate["submission"]["duplicate_resolution"]["decision"] == "create_new"
    assert run_next["executed_count"] == 1
    assert run_next["executed"][0]["action"].startswith(("plan_", "prepare_", "record_", "assess_"))
    assert run_next["phase_report_before"]["schema"] == "business-card-watchdog.phase-report.v1"
    assert run_next["phase_report_after"]["schema"] == "business-card-watchdog.phase-report.v1"


def test_mcp_enrichment_request_can_prepare_paid_provider_without_call(tmp_path: Path) -> None:
    keys_path = tmp_path / "API-keys.env"
    keys_path.write_text("APOLLO_API_KEY=fixture-value-redacted\n", encoding="utf-8")
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        enrichment=EnrichmentConfig(
            enabled=True,
            allow_paid_api=True,
            api_keys_env=keys_path,
            apollo=EnrichmentProviderConfig(enabled=True),
        ),
    )
    run_id, job_id = make_recorded_run(config)
    artifact_dir = config.runs_dir / run_id / "artifacts" / job_id
    (artifact_dir / "contact_candidate.json").write_text(
        json.dumps(build_contact_candidate({"full_name": "Ada Lovelace", "email": "ada@example.test"}))
        + "\n",
        encoding="utf-8",
    )

    payload = call_tool(
        "business_card_watchdog_enrichment_request",
        {
            "job_id": job_id,
            "run_id": run_id,
            "mode": "api",
            "allow_paid_enrichment": True,
            "provider_results": [
                {
                    "person": {
                        "name": "Ada Lovelace",
                        "email": "ada@example.test",
                        "title": "Principal",
                    },
                    "organization": {"name": "Example Labs"},
                }
            ],
        },
        config=config,
    )

    assert payload["status"] == "ok"
    assert payload["provider_request"]["status"] == "prepared"
    assert payload["provider_request"]["network_calls_made"] == 0
    assert payload["provider_result"]["schema"] == "business-card-watchdog.enrichment-provider-result.v1"
    assert payload["provider_result"]["network_calls_made"] == 0
    assert "secret" not in json.dumps(payload)
    handoff = call_tool(
        "business_card_watchdog_provider_enrichment_handoff",
        {"job_id": job_id, "run_id": run_id},
        config=config,
    )
    result = call_tool(
        "business_card_watchdog_provider_enrichment_results",
        {
            "job_id": job_id,
            "run_id": run_id,
            "provider": "apollo",
            "submitted_by": "mcp-agent",
            "results": [
                {
                    "person": {
                        "name": "Ada Lovelace",
                        "email": "ada@example.test",
                        "title": "Principal",
                    },
                    "organization": {"name": "Example Labs"},
                }
            ],
        },
        config=config,
    )
    assert handoff["handoff"]["schema"] == "business-card-watchdog.enrichment-provider-handoff.v1"
    assert handoff["handoff"]["paid_api_calls_attempted"] == 0
    assert "secret" not in json.dumps(handoff)
    assert result["provider_result"]["submitted_by"] == "mcp-agent"
    assert result["provider_result"]["paid_api_calls_attempted"] == 0


def test_mcp_public_web_enrichment_results_are_explicit(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        enrichment=EnrichmentConfig(enabled=True),
    )
    run_id, job_id = make_recorded_run(config)
    artifact_dir = config.runs_dir / run_id / "artifacts" / job_id
    (artifact_dir / "contact_candidate.json").write_text(
        json.dumps(
            build_contact_candidate(
                {
                    "full_name": "Ada Lovelace",
                    "organization": "Example Labs",
                    "email": "ada@example.test",
                }
            )
        )
        + "\n",
        encoding="utf-8",
    )
    request = call_tool(
        "business_card_watchdog_enrichment_request",
        {"job_id": job_id, "run_id": run_id, "mode": "public_web"},
        config=config,
    )
    handoff = call_tool(
        "business_card_watchdog_public_web_enrichment_handoff",
        {"job_id": job_id, "run_id": run_id},
        config=config,
    )
    payload = call_tool(
        "business_card_watchdog_public_web_enrichment_results",
        {
            "job_id": job_id,
            "run_id": run_id,
            "searched_by": "mcp-search",
            "results": [
                {
                    "title": "Ada Lovelace - Example Labs",
                    "url": "https://example.test/team/ada",
                    "snippet": "Contact Ada at ada@example.test",
                }
            ],
        },
        config=config,
    )

    assert request["public_web_request"]["network_calls_made"] == 0
    assert handoff["handoff"]["schema"] == "business-card-watchdog.enrichment-public-web-search-handoff.v1"
    assert handoff["handoff"]["search_calls_attempted"] == 0
    assert payload["public_web_result"]["schema"] == "business-card-watchdog.enrichment-public-web-result.v1"
    assert payload["public_web_result"]["searched_by"] == "mcp-search"
    assert payload["public_web_result"]["network_calls_made"] == 0
    assert payload["result"]["merge_proposals"][0]["field"] == "notes"


def test_mcp_call_tool_rejects_unknown_tool(tmp_path: Path) -> None:
    config = AppConfig(config_path=Path("config.toml"), data_dir=tmp_path / "data")

    try:
        call_tool("missing_tool", {}, config=config)
    except ValueError as exc:
        assert "unknown MCP tool" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_mcp_jsonl_server_lists_and_calls_tools(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    run_id, job_id = make_recorded_run(config)
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "business_card_watchdog_status", "arguments": {}},
        },
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "business_card_watchdog_phase_report",
                "arguments": {"run_id": run_id},
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "business_card_watchdog_pilot_readiness_report",
                "arguments": {"run_id": run_id},
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {
                "name": "business_card_watchdog_reviews_list",
                "arguments": {
                    "run_id": run_id,
                    "next_action": "review_contact",
                    "artifact_kind": "contact_spec",
                },
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {
                "name": "business_card_watchdog_apply_review_decisions",
                "arguments": {
                    "run_id": run_id,
                    "reviewer": "mcp-jsonl",
                    "decisions": [
                        {
                            "job_id": job_id,
                            "action": "approve_for_routing",
                            "field_corrections": {"full_name": "JSONL Transport"},
                        }
                    ],
                },
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 8,
            "method": "tools/call",
            "params": {
                "name": "business_card_watchdog_run_next_actions",
                "arguments": {"run_id": run_id, "limit": 1},
            },
        },
        {"jsonrpc": "2.0", "id": 9, "method": "shutdown", "params": {}},
    ]
    input_stream = StringIO(
        "\n".join(json.dumps(request, sort_keys=True) for request in requests) + "\n"
    )
    output_stream = StringIO()

    serve_jsonl(input_stream=input_stream, output_stream=output_stream, config=config)
    responses = [json.loads(line) for line in output_stream.getvalue().splitlines()]

    assert responses[0]["result"]["serverInfo"]["name"] == "business-card-watchdog"
    assert responses[1]["result"]["tools"][0]["inputSchema"]["type"] == "object"
    assert any(tool["name"] == "business_card_watchdog_status" for tool in responses[1]["result"]["tools"])
    assert any(
        tool["name"] == "business_card_watchdog_pilot_readiness_report"
        for tool in responses[1]["result"]["tools"]
    )
    assert responses[2]["result"]["isError"] is False
    assert responses[2]["result"]["structuredContent"]["skill_ready"] is True
    phase_report = responses[3]["result"]["structuredContent"]
    assert phase_report["schema"] == "business-card-watchdog.phase-report.v1"
    assert phase_report["review_workbook_preview"]["schema"] == (
        "business-card-watchdog.review-workbook-preview-phase.v1"
    )
    assert phase_report["review_workbook_preview"]["state"] == "not_started"
    assert phase_report["dashboard_summary"]["schema"] == "business-card-watchdog.phase-dashboard-summary.v1"
    assert phase_report["dashboard_summary"]["blocked_phases"] == [{"phase": "review", "count": 1}]
    assert phase_report["phases"][2]["phase"] == "review"
    assert phase_report["phases"][2]["counts"]["blocked"] == 1
    readiness_report = responses[4]["result"]["structuredContent"]
    assert readiness_report["schema"] == "business-card-watchdog.pilot-readiness-report.v1"
    assert readiness_report["blocked_job_ids"] == [job_id]
    reviews = responses[5]["result"]["structuredContent"]
    assert [entry["job_id"] for entry in reviews] == [job_id]
    assert reviews[0]["next_action"]["action"] == "review_contact"
    review_import = responses[6]["result"]["structuredContent"]
    assert review_import["import"]["schema"] == "business-card-watchdog.review-decisions-import.v1"
    assert review_import["results"][0]["job_state"] == "ready_to_route"
    run_next = responses[7]["result"]["structuredContent"]
    assert run_next["executed_count"] == 1
    assert run_next["executed"][0]["action"] == "plan_sink_lookup"
    assert run_next["phase_report_before"]["schema"] == "business-card-watchdog.phase-report.v1"
    assert run_next["phase_report_after"]["schema"] == "business-card-watchdog.phase-report.v1"
    assert responses[8]["result"]["shutdown"] is True
