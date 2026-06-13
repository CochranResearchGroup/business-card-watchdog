from business_card_watchdog.mcp import tool_manifest


def test_manifest_has_process_tool() -> None:
    manifest = tool_manifest()
    names = {tool["name"] for tool in manifest["tools"]}
    assert "business_card_watchdog_process" in names
    assert "business_card_watchdog_runs_list" in names
    assert "business_card_watchdog_job_show" in names
    assert "business_card_watchdog_job_review" in names
    assert "business_card_watchdog_run_summary" in names
    assert "business_card_watchdog_reviews_list" in names
    assert "business_card_watchdog_sinks_check" in names
    assert "business_card_watchdog_enrichment_check" in names
    assert "business_card_watchdog_enrichment_request" in names
    assert "business_card_watchdog_doctor" in names
