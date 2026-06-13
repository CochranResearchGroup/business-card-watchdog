import json
from pathlib import Path

from business_card_watchdog.config import AppConfig, SinkConfig
from business_card_watchdog.mcp import call_tool, tool_manifest

from test_service import make_recorded_run


def test_manifest_has_process_tool() -> None:
    manifest = tool_manifest()
    names = {tool["name"] for tool in manifest["tools"]}
    assert "business_card_watchdog_process" in names
    assert "business_card_watchdog_runs_list" in names
    assert "business_card_watchdog_job_show" in names
    assert "business_card_watchdog_job_review" in names
    assert "business_card_watchdog_run_summary" in names
    assert "business_card_watchdog_next_actions" in names
    assert "business_card_watchdog_run_next_actions" in names
    assert "business_card_watchdog_reviews_list" in names
    assert "business_card_watchdog_sinks_check" in names
    assert "business_card_watchdog_sink_plan" in names
    assert "business_card_watchdog_sink_lookup_plan" in names
    assert "business_card_watchdog_sink_apply_preflight" in names
    assert "business_card_watchdog_sink_apply_decision" in names
    assert "business_card_watchdog_sink_apply" in names
    assert "business_card_watchdog_sink_adapter_request" in names
    assert "business_card_watchdog_sink_lookup_result" in names
    assert "business_card_watchdog_downstream_duplicate_assessment" in names
    assert "business_card_watchdog_enrichment_check" in names
    assert "business_card_watchdog_enrichment_request" in names
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
    next_actions = call_tool("business_card_watchdog_next_actions", {"run_id": run_id}, config=config)
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
    adapter_request = call_tool(
        "business_card_watchdog_sink_adapter_request",
        {"job_id": job_id, "run_id": run_id, "phase": "readback"},
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
    assert adapter_request["request"]["phase"] == "readback"
    assert adapter_request["request"]["network_calls_made"] == 0
    assert lookup_result["result"]["state"] == "possible_duplicate"
    assert lookup_result["result"]["network_calls_made"] == 0
    assert downstream_duplicate["assessment"]["state"] == "strong_duplicate"
    assert downstream_duplicate["job"]["state"] == "needs_review"
    assert merge["submission"]["approved_enrichment_fields"] == ["notes"]
    assert duplicate["submission"]["duplicate_resolution"]["decision"] == "create_new"
    assert run_next["executed_count"] == 1
    assert run_next["executed"][0]["action"].startswith(("plan_", "prepare_", "record_", "assess_"))


def test_mcp_call_tool_rejects_unknown_tool(tmp_path: Path) -> None:
    config = AppConfig(config_path=Path("config.toml"), data_dir=tmp_path / "data")

    try:
        call_tool("missing_tool", {}, config=config)
    except ValueError as exc:
        assert "unknown MCP tool" in str(exc)
    else:
        raise AssertionError("expected ValueError")
