from pathlib import Path

from business_card_watchdog.config import AppConfig
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
    assert "business_card_watchdog_reviews_list" in names
    assert "business_card_watchdog_sinks_check" in names
    assert "business_card_watchdog_sink_plan" in names
    assert "business_card_watchdog_enrichment_check" in names
    assert "business_card_watchdog_enrichment_request" in names
    assert "business_card_watchdog_doctor" in names


def test_mcp_call_tool_dispatches_to_service(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    run_id, job_id = make_recorded_run(config)

    summary = call_tool("business_card_watchdog_run_summary", {"run_id": run_id}, config=config)
    next_actions = call_tool("business_card_watchdog_next_actions", {"run_id": run_id}, config=config)
    job = call_tool("business_card_watchdog_job_show", {"job_id": job_id, "run_id": run_id}, config=config)

    assert summary["needs_review_count"] == 1
    assert next_actions["actions"][0]["action"] == "review_contact"
    assert job["job_id"] == job_id


def test_mcp_call_tool_rejects_unknown_tool(tmp_path: Path) -> None:
    config = AppConfig(config_path=Path("config.toml"), data_dir=tmp_path / "data")

    try:
        call_tool("missing_tool", {}, config=config)
    except ValueError as exc:
        assert "unknown MCP tool" in str(exc)
    else:
        raise AssertionError("expected ValueError")
