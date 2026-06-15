from __future__ import annotations

import csv
import json
from io import StringIO
from pathlib import Path

import pytest

from business_card_watchdog.config import AppConfig, EnrichmentConfig, EnrichmentProviderConfig, PrefilterConfig, SinkConfig
from business_card_watchdog.contact import build_contact_candidate
from business_card_watchdog.orchestrator import BatchOrchestrator
from business_card_watchdog.service import BusinessCardService

from synthetic_fixtures import SyntheticSkillAdapter, write_multi_card_image, write_synthetic_image
from test_service import make_recorded_run


fastapi_testclient = pytest.importorskip("fastapi.testclient")
TestClient = fastapi_testclient.TestClient


def write_config(path: Path, data_dir: Path) -> None:
    path.write_text(f'data_dir = "{data_dir}"\n[watch]\ninputs = []\n', encoding="utf-8")


def test_api_health_status_runs_and_jobs(tmp_path: Path) -> None:
    from business_card_watchdog.api import create_app

    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    write_config(config_path, data_dir)
    run_id, job_id = make_recorded_run(AppConfig(config_path=config_path, data_dir=data_dir))
    client = TestClient(create_app(config_path))

    assert client.get("/health").json()["ok"] is True
    status = client.get("/status").json()
    assert status["schema"] == "business-card-watchdog.status.v1"
    assert status["watch"]["inputs"] == []
    assert status["commands"]["runtime_readiness"] == "runtime-readiness --json"
    assert status["safe_next_actions"][0]["action"] == "inspect_runtime_readiness"
    assert status["writes_attempted"] == 0
    assert status["network_calls_made"] == 0
    operator_dashboard = client.get("/operator/dashboard", params={"run_id": run_id}).json()
    assert operator_dashboard["schema"] == "business-card-watchdog.operator-dashboard.v1"
    assert operator_dashboard["selected_run_id"] == run_id
    assert operator_dashboard["commands"]["live_pilot_status"] == f"runs live-pilot-status {run_id} --no-write --json"
    assert operator_dashboard["commands"]["live_pilot_approval_packet"] == (
        f"runs live-pilot-approval-packet {run_id} --json"
    )
    assert operator_dashboard["safe_next_actions"][3]["action"] == "inspect_live_pilot_status"
    assert operator_dashboard["safe_next_actions"][3]["command"] == (
        f"runs live-pilot-status {run_id} --no-write --json"
    )
    assert operator_dashboard["safe_next_actions"][4]["action"] == "inspect_live_pilot_handoff"
    assert operator_dashboard["safe_next_actions"][4]["command"] == (
        f"runs live-pilot-handoff {run_id} --no-write --json"
    )
    assert operator_dashboard["review_counts"]["needs_review"] == 1
    assert operator_dashboard["next_action_summary"]["by_action"] == {"review_contact": 1}
    assert operator_dashboard["live_pilot_handoff_summary"]["action_counts"] == {"no_live_candidate": 1}
    assert operator_dashboard["live_pilot_handoff_summary"]["operator_required_count"] == 0
    assert len(operator_dashboard["live_pilot_summary"]["explicit_stop_conditions"]) == 3
    assert "This status report does not create selected_live_target.json." in (
        operator_dashboard["live_pilot_summary"]["explicit_stop_conditions"]
    )
    assert len(operator_dashboard["live_pilot_handoff_summary"]["operator_stop_conditions"]) == 4
    assert "Do not run live lookup, live write, or live readback from this handoff artifact." in (
        operator_dashboard["live_pilot_handoff_summary"]["operator_stop_conditions"]
    )
    assert operator_dashboard["commands"]["next_actions"] == f"actions next --run-id {run_id} --json"
    assert operator_dashboard["api_routes"]["next_actions"] == f"GET /actions/next?run_id={run_id}&limit=20"
    assert operator_dashboard["commands"]["multi_card_preclassification_drill"] == (
        "drills multi-card-preclassification --json"
    )
    assert operator_dashboard["commands"]["review_routing_drill"] == "drills review-routing --json"
    assert operator_dashboard["commands"]["live_pilot_rehearsal_drill"] == "drills live-pilot-rehearsal --json"
    assert operator_dashboard["api_routes"]["multi_card_preclassification_drill"] == (
        "POST /drills/multi-card-preclassification"
    )
    assert operator_dashboard["api_routes"]["review_routing_drill"] == "POST /drills/review-routing"
    assert operator_dashboard["api_routes"]["live_pilot_rehearsal_drill"] == "POST /drills/live-pilot-rehearsal"
    assert operator_dashboard["mcp_tools"]["review_routing_drill"] == {
        "tool": "business_card_watchdog_review_routing_drill",
        "arguments": {},
    }
    assert operator_dashboard["mcp_tools"]["multi_card_preclassification_drill"] == {
        "tool": "business_card_watchdog_multi_card_preclassification_drill",
        "arguments": {},
    }
    assert operator_dashboard["mcp_tools"]["live_pilot_rehearsal_drill"] == {
        "tool": "business_card_watchdog_live_pilot_rehearsal_drill",
        "arguments": {},
    }
    assert operator_dashboard["commands"]["live_pilot_validate_response"] == (
        f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
    )
    assert operator_dashboard["commands"]["selected_live_target_preflight"] == (
        f"runs selected-live-target-preflight {run_id} --response <operator-response> --json"
    )
    assert operator_dashboard["commands"]["selected_live_target_preview"] == (
        f"runs selected-live-target-preview {run_id} --response <operator-response> --json"
    )
    assert operator_dashboard["commands"]["selected_live_target_from_response"] == (
        f"runs selected-live-target-from-response {run_id} --response <operator-response> --json"
    )
    assert operator_dashboard["commands"]["selected_live_target_handoff_from_response"] == (
        f"runs selected-live-target-handoff-from-response {run_id} --response <operator-response> --json"
    )
    assert operator_dashboard["commands"]["lookup_smoke_handoff_from_response"] == (
        f"runs lookup-smoke-handoff-from-response {run_id} --response <operator-response> --json"
    )
    assert operator_dashboard["commands"]["selected_lookup_smoke_execution_packet_from_response"] == (
        f"runs selected-lookup-smoke-execution-packet-from-response {run_id} "
        "--response <operator-response> --json"
    )
    assert operator_dashboard["commands"]["selected_write_pilot_execution_packet_from_response"] == (
        f"runs selected-write-pilot-execution-packet-from-response {run_id} "
        "--response <operator-response> --json"
    )
    assert operator_dashboard["commands"]["selected_readback_pilot_execution_packet_from_response"] == (
        f"runs selected-readback-pilot-execution-packet-from-response {run_id} "
        "--response <operator-response> --json"
    )
    assert operator_dashboard["commands"]["live_pilot_closeout_packet_from_response"] == (
        f"runs live-pilot-closeout-packet-from-response {run_id} "
        "--response <operator-response> --json"
    )
    assert operator_dashboard["commands"]["live_pilot_operator_workflow_packet_from_response"] == (
        f"runs live-pilot-operator-workflow-packet-from-response {run_id} "
        "--response <operator-response> --json"
    )
    assert operator_dashboard["commands"]["live_pilot_operator_rehearsal_from_response"] == (
        f"runs live-pilot-operator-rehearsal-from-response {run_id} --response <operator-response> --json"
    )
    assert operator_dashboard["commands"]["live_pilot_readiness_export_from_response"] == (
        f"runs live-pilot-readiness-export-from-response {run_id} --response <operator-response> --json"
    )
    assert operator_dashboard["commands"]["live_pilot_execution_checklist_from_response"] == (
        f"runs live-pilot-execution-checklist-from-response {run_id} --response <operator-response> --json"
    )
    assert operator_dashboard["commands"]["live_pilot_command_copy_packet_from_response"] == (
        f"runs live-pilot-command-copy-packet-from-response {run_id} "
        "--response <operator-response> --acknowledgement <operator-acknowledgement> --json"
    )
    assert operator_dashboard["api_routes"]["live_pilot_validate_response"] == (
        f"POST /runs/{run_id}/live-pilot-operator-response-validation"
    )
    assert operator_dashboard["api_routes"]["selected_live_target_preflight"] == (
        f"POST /runs/{run_id}/selected-live-target-preflight"
    )
    assert operator_dashboard["api_routes"]["selected_live_target_preview"] == (
        f"POST /runs/{run_id}/selected-live-target-preview"
    )
    assert operator_dashboard["api_routes"]["selected_live_target_from_response"] == (
        f"POST /runs/{run_id}/selected-live-target-from-response"
    )
    assert operator_dashboard["api_routes"]["selected_live_target_handoff_from_response"] == (
        f"POST /runs/{run_id}/selected-live-target-handoff-from-response"
    )
    assert operator_dashboard["api_routes"]["lookup_smoke_handoff_from_response"] == (
        f"POST /runs/{run_id}/lookup-smoke-handoff-from-response"
    )
    assert operator_dashboard["api_routes"]["selected_lookup_smoke_execution_packet_from_response"] == (
        f"POST /runs/{run_id}/selected-lookup-smoke-execution-packet-from-response"
    )
    assert operator_dashboard["api_routes"]["selected_write_pilot_execution_packet_from_response"] == (
        f"POST /runs/{run_id}/selected-write-pilot-execution-packet-from-response"
    )
    assert operator_dashboard["api_routes"]["selected_readback_pilot_execution_packet_from_response"] == (
        f"POST /runs/{run_id}/selected-readback-pilot-execution-packet-from-response"
    )
    assert operator_dashboard["api_routes"]["live_pilot_closeout_packet_from_response"] == (
        f"POST /runs/{run_id}/live-pilot-closeout-packet-from-response"
    )
    assert operator_dashboard["api_routes"]["live_pilot_operator_workflow_packet_from_response"] == (
        f"POST /runs/{run_id}/live-pilot-operator-workflow-packet-from-response"
    )
    assert operator_dashboard["api_routes"]["live_pilot_operator_rehearsal_from_response"] == (
        f"POST /runs/{run_id}/live-pilot-operator-rehearsal-from-response"
    )
    assert operator_dashboard["api_routes"]["live_pilot_readiness_export_from_response"] == (
        f"POST /runs/{run_id}/live-pilot-readiness-export-from-response"
    )
    assert operator_dashboard["api_routes"]["live_pilot_execution_checklist_from_response"] == (
        f"POST /runs/{run_id}/live-pilot-execution-checklist-from-response"
    )
    assert operator_dashboard["api_routes"]["live_pilot_command_copy_packet_from_response"] == (
        f"POST /runs/{run_id}/live-pilot-command-copy-packet-from-response"
    )
    assert operator_dashboard["api_routes"]["live_pilot_approval_packet"] == (
        f"GET /runs/{run_id}/live-pilot-approval-packet"
    )
    assert operator_dashboard["mcp_tools"]["next_actions"] == {
        "tool": "business_card_watchdog_next_actions",
        "arguments": {"run_id": run_id, "limit": 20},
    }
    assert operator_dashboard["mcp_tools"]["live_pilot_validate_response"] == {
        "tool": "business_card_watchdog_live_pilot_operator_response_validation",
        "arguments": {"run_id": run_id, "response": "<operator-response>"},
    }
    assert operator_dashboard["mcp_tools"]["live_pilot_approval_packet"] == {
        "tool": "business_card_watchdog_live_pilot_approval_packet",
        "arguments": {"run_id": run_id},
    }
    assert operator_dashboard["mcp_tools"]["selected_live_target_preflight"] == {
        "tool": "business_card_watchdog_selected_live_target_preflight",
        "arguments": {"run_id": run_id, "response": "<operator-response>"},
    }
    assert operator_dashboard["mcp_tools"]["selected_live_target_preview"] == {
        "tool": "business_card_watchdog_selected_live_target_artifact_preview",
        "arguments": {"run_id": run_id, "response": "<operator-response>"},
    }
    assert operator_dashboard["mcp_tools"]["selected_live_target_from_response"] == {
        "tool": "business_card_watchdog_selected_live_target_from_response",
        "arguments": {"run_id": run_id, "response": "<operator-response>"},
    }
    assert operator_dashboard["mcp_tools"]["selected_live_target_handoff_from_response"] == {
        "tool": "business_card_watchdog_selected_live_target_handoff_from_response",
        "arguments": {"run_id": run_id, "response": "<operator-response>", "write_audit": False},
    }
    assert operator_dashboard["mcp_tools"]["lookup_smoke_handoff_from_response"] == {
        "tool": "business_card_watchdog_lookup_smoke_handoff_from_response",
        "arguments": {"run_id": run_id, "response": "<operator-response>", "write_handoff": False},
    }
    assert operator_dashboard["mcp_tools"]["selected_lookup_smoke_execution_packet_from_response"] == {
        "tool": "business_card_watchdog_selected_lookup_smoke_execution_packet_from_response",
        "arguments": {"run_id": run_id, "response": "<operator-response>", "execute_selected_lookup_smoke": False},
    }
    assert operator_dashboard["mcp_tools"]["selected_write_pilot_execution_packet_from_response"] == {
        "tool": "business_card_watchdog_selected_write_pilot_execution_packet_from_response",
        "arguments": {"run_id": run_id, "response": "<operator-response>", "execute_write_pilot": False},
    }
    assert operator_dashboard["mcp_tools"]["selected_readback_pilot_execution_packet_from_response"] == {
        "tool": "business_card_watchdog_selected_readback_pilot_execution_packet_from_response",
        "arguments": {"run_id": run_id, "response": "<operator-response>", "execute_readback_pilot": False},
    }
    assert operator_dashboard["mcp_tools"]["live_pilot_closeout_packet_from_response"] == {
        "tool": "business_card_watchdog_live_pilot_closeout_packet_from_response",
        "arguments": {"run_id": run_id, "response": "<operator-response>", "write_closeout": False},
    }
    assert operator_dashboard["mcp_tools"]["live_pilot_operator_workflow_packet_from_response"] == {
        "tool": "business_card_watchdog_live_pilot_operator_workflow_packet_from_response",
        "arguments": {"run_id": run_id, "response": "<operator-response>"},
    }
    assert operator_dashboard["mcp_tools"]["live_pilot_operator_rehearsal_from_response"] == {
        "tool": "business_card_watchdog_live_pilot_operator_rehearsal_from_response",
        "arguments": {"run_id": run_id, "response": "<operator-response>"},
    }
    assert operator_dashboard["mcp_tools"]["live_pilot_readiness_export_from_response"] == {
        "tool": "business_card_watchdog_live_pilot_readiness_export_from_response",
        "arguments": {"run_id": run_id, "response": "<operator-response>", "write": True},
    }
    assert operator_dashboard["mcp_tools"]["live_pilot_execution_checklist_from_response"] == {
        "tool": "business_card_watchdog_live_pilot_execution_checklist_from_response",
        "arguments": {"run_id": run_id, "response": "<operator-response>"},
    }
    assert operator_dashboard["mcp_tools"]["live_pilot_command_copy_packet_from_response"] == {
        "tool": "business_card_watchdog_live_pilot_command_copy_packet_from_response",
        "arguments": {
            "run_id": run_id,
            "response": "<operator-response>",
            "acknowledgement": "<operator-acknowledgement>",
        },
    }
    assert operator_dashboard["writes_attempted"] == 0
    assert operator_dashboard["network_calls_made"] == 0
    next_actions_get = client.get("/actions/next", params={"run_id": run_id, "limit": 5}).json()
    assert next_actions_get["run_id"] == run_id
    assert next_actions_get["action_count"] == 1
    assert next_actions_get["actions"][0]["action"] == "review_contact"
    assert next_actions_get["actions"][0]["requires_explicit_operator_action"] is True
    next_actions_post = client.post("/actions/next", json={"run_id": run_id, "limit": 5}).json()
    assert next_actions_post["actions"][0]["action"] == "review_contact"
    assert next_actions_post["actions"][0]["safe_to_auto_continue"] is False
    runtime_readiness = client.get("/runtime/readiness").json()
    assert runtime_readiness["schema"] == "business-card-watchdog.runtime-readiness.v1"
    assert runtime_readiness["config"]["config_exists"] is True
    assert runtime_readiness["network_calls_made"] == 0
    assert runtime_readiness["writes_attempted"] == 0
    service_recovery = client.get("/service/recovery", params={"run_id": run_id}).json()
    assert service_recovery["schema"] == "business-card-watchdog.service-recovery.v1"
    assert service_recovery["run_id"] == run_id
    assert service_recovery["commands"]["restart"] == "systemctl --user restart business-card-watchdog.service"
    assert service_recovery["commands"]["live_pilot_status"].endswith(
        f"runs live-pilot-status {run_id} --no-write --json"
    )
    assert service_recovery["commands"]["live_pilot_handoff"].endswith(f"runs live-pilot-handoff {run_id}")
    assert service_recovery["commands"]["review_routing_drill"].endswith("drills review-routing --json")
    assert any(action["action"] == "inspect_live_pilot_status" for action in service_recovery["safe_next_actions"])
    assert any(action["action"] == "inspect_live_pilot_handoff" for action in service_recovery["safe_next_actions"])
    assert any(
        action["action"] == "run_fixture_review_routing_drill"
        for action in service_recovery["safe_next_actions"]
    )
    assert service_recovery["network_calls_made"] == 0
    assert service_recovery["writes_attempted"] == 0
    live_targets = client.get("/live-target-candidates", params={"run_id": run_id}).json()
    assert live_targets["schema"] == "business-card-watchdog.live-target-candidates.v1"
    assert live_targets["network_calls_made"] == 0
    assert live_targets["writes_attempted"] == 0
    assert live_targets["commands"]["live_pilot_handoff"] == f"runs live-pilot-handoff {run_id}"
    assert live_targets["commands"]["validate_operator_response"] == (
        f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
    )
    live_audit = client.post("/live-readiness-audit", json={"run_id": run_id, "write": False}).json()
    assert live_audit["schema"] == "business-card-watchdog.live-readiness-audit.v1"
    assert live_audit["run_id"] == run_id
    assert live_audit["network_calls_made"] == 0
    assert live_audit["writes_attempted"] == 0
    assert live_audit["commands"]["live_pilot_handoff"] == f"runs live-pilot-handoff {run_id}"
    assert live_audit["commands"]["validate_operator_response"] == (
        f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
    )
    live_requirements = client.post("/live-selection-requirements", json={"run_id": run_id, "write": False}).json()
    assert live_requirements["schema"] == "business-card-watchdog.live-selection-requirements.v1"
    assert live_requirements["run_id"] == run_id
    assert live_requirements["entry_count"] == 0
    assert live_requirements["network_calls_made"] == 0
    assert live_requirements["writes_attempted"] == 0
    assert live_requirements["commands"]["live_pilot_handoff"] == f"runs live-pilot-handoff {run_id}"
    assert live_requirements["commands"]["validate_operator_response"] == (
        f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
    )
    assert live_requirements["operator_response_contract"]["schema"] == (
        "business-card-watchdog.operator-selection-response-contract.v1"
    )
    assert live_requirements["operator_response_contract"]["required_fields"] == [
        "run_id",
        "job_id",
        "sink",
        "operator",
        "scope",
        "safety_confirmation",
    ]
    assert live_requirements["operator_response_contract"]["creates_selected_live_target"] is False
    live_packet = client.post(
        f"/jobs/{job_id}/live-selection-packet",
        json={"run_id": run_id, "sink": "google_contacts", "operator": "api-test", "write": False},
    ).json()
    assert live_packet["schema"] == "business-card-watchdog.live-selection-packet.v1"
    assert live_packet["job_id"] == job_id
    assert live_packet["approval_state"] == "pending_operator_approval"
    assert live_packet["writes_attempted"] == 0
    assert live_packet["existing_selected_target"]["exists"] is False
    assert live_packet["existing_selected_target"]["identity"] is None
    assert live_packet["existing_selected_target"]["abandoned"] is False
    assert live_packet["operator_response_template"] == (
        f"run_id={run_id} job_id={job_id} sink=google_contacts "
        "operator=api-test scope=lookup safety_confirmation=<tenant-profile-account-confirmation>"
    )
    assert live_packet["copyable_approval_fields"]["operator"] == "api-test"
    assert live_packet["commands"]["validate_operator_response"] == (
        f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
    )
    assert live_packet["commands"]["validate_operator_response_prefilled"] == (
        f"runs live-pilot-validate-response {run_id} "
        f"--response 'run_id={run_id} job_id={job_id} sink=google_contacts "
        "operator=api-test scope=lookup safety_confirmation=<tenant-profile-account-confirmation>' --json"
    )
    selected = client.post(
        f"/jobs/{job_id}/selected-live-target",
        json={
            "run_id": run_id,
            "sink": "google_contacts",
            "operator": "api-test",
            "scope": "lookup",
            "safety_confirmation": "fixture contact is safe for google contacts test profile",
        },
    ).json()
    assert selected["target"]["schema"] == "business-card-watchdog.selected-live-target.v1"
    active_live_packet = client.post(
        f"/jobs/{job_id}/live-selection-packet",
        json={"run_id": run_id, "sink": "google_contacts", "operator": "api-test", "write": False},
    ).json()
    assert active_live_packet["state"] == "blocked"
    assert active_live_packet["existing_selected_target"]["exists"] is True
    assert active_live_packet["existing_selected_target"]["identity"] == selected["target"]["selection_id"]
    assert active_live_packet["existing_selected_target"]["target_safety_confirmed"] is True
    assert active_live_packet["existing_selected_target"]["replacement_requires_abandonment"] is True
    assert active_live_packet["existing_selected_target"]["can_select_replacement_now"] is False
    assert "abandon-live-pilot" in active_live_packet["existing_selected_target"]["abandon_command"]
    selected_audit = client.post(
        f"/jobs/{job_id}/selected-live-target-audit",
        json={"run_id": run_id, "scope": "lookup", "write": False},
    ).json()
    assert selected_audit["schema"] == "business-card-watchdog.selected-live-target-audit.v1"
    assert selected_audit["selected_target_exists"] is True
    assert selected_audit["writes_attempted"] == 0
    closeout = client.post(
        f"/jobs/{job_id}/live-pilot-closeout",
        json={"run_id": run_id, "write": False},
    ).json()
    assert closeout["report"]["schema"] == "business-card-watchdog.live-pilot-closeout.v1"
    assert closeout["report"]["state"] == "incomplete"
    assert closeout["report"]["writes_attempted"] == 0
    live_status = client.get(f"/runs/{run_id}/live-pilot-status", params={"write": False}).json()
    assert live_status["schema"] == "business-card-watchdog.live-pilot-status.v1"
    assert live_status["job_count"] == 1
    assert live_status["writes_attempted"] == 0
    assert live_status["commands"]["live_pilot_handoff"] == f"runs live-pilot-handoff {run_id}"
    assert live_status["commands"]["validate_operator_response"] == (
        f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
    )
    assert live_status["entries"][0]["selected_target_identity"] == selected["target"]["selection_id"]
    assert live_status["entries"][0]["abandonment_identity"] is None
    assert live_status["operator_response_contract"]["creates_selected_live_target"] is False
    assert live_status["entries"][0]["operator_response_template"] == (
        f"run_id={run_id} job_id={job_id} sink=google_contacts "
        "operator=api-test scope=lookup safety_confirmation=<tenant-profile-account-confirmation>"
    )
    assert live_status["entries"][0]["commands"]["validate_operator_response"] == (
        f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
    )
    live_handoff = client.get(f"/runs/{run_id}/live-pilot-handoff", params={"write": False}).json()
    assert live_handoff["schema"] == "business-card-watchdog.live-pilot-handoff.v1"
    assert live_handoff["action_counts"]["request_live_lookup_smoke"] == 1
    assert live_handoff["writes_attempted"] == 0
    assert live_handoff["entries"][0]["selected_target_identity"] == selected["target"]["selection_id"]
    assert live_handoff["entries"][0]["abandonment_identity"] is None
    assert live_handoff["commands"]["validate_operator_response"] == (
        f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
    )
    assert live_handoff["operator_response_contract"]["creates_selected_live_target"] is False
    assert live_handoff["entries"][0]["operator_response_template"] == (
        f"run_id={run_id} job_id={job_id} sink=google_contacts "
        "operator=api-test scope=lookup safety_confirmation=<tenant-profile-account-confirmation>"
    )
    assert live_handoff["entries"][0]["pilot_command_checklist_summary"]["step_count"] == 5
    assert live_handoff["entries"][0]["pilot_command_checklist_summary"]["live_call_count"] == 1
    api_sequence = live_handoff["entries"][0]["pilot_command_sequence"]
    assert api_sequence["safe_inspection_step_count"] == 3
    assert api_sequence["explicit_operator_step_count"] == 2
    assert api_sequence["live_call_step_count"] == 1
    assert api_sequence["sink_write_step_count"] == 0
    assert api_sequence["execution_policy"]["do_not_run_live_or_sink_write_from_handoff"] is True
    assert live_handoff["operator_response_templates"][0]["validation_command"] == (
        f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
    )
    assert live_handoff["operator_response_templates"][0]["validation_command_prefilled"] == (
        f"runs live-pilot-validate-response {run_id} "
        f"--response 'run_id={run_id} job_id={job_id} sink=google_contacts "
        "operator=api-test scope=lookup safety_confirmation=<tenant-profile-account-confirmation>' --json"
    )
    assert live_handoff["entries"][0]["copyable_approval_fields"]["operator"] == "api-test"
    active_dashboard = client.get("/operator/dashboard", params={"run_id": run_id}).json()
    dashboard_sequence = active_dashboard["live_pilot_handoff_summary"]["operator_entries"][0][
        "pilot_command_sequence_summary"
    ]
    assert dashboard_sequence["safe_inspection_step_count"] == 3
    assert dashboard_sequence["explicit_operator_step_count"] == 2
    assert dashboard_sequence["live_call_step_count"] == 1
    assert dashboard_sequence["sink_write_step_count"] == 0
    assert dashboard_sequence["next_safe_inspection_step"] == "validate_operator_response"
    assert dashboard_sequence["next_explicit_operator_step"] == "create_selected_target"
    dashboard_packet = active_dashboard["live_pilot_handoff_summary"]["execution_packet"]
    assert dashboard_packet["schema"] == "business-card-watchdog.operator-dashboard.live-pilot-execution-packet.v1"
    assert dashboard_packet["state"] == "operator_required"
    assert dashboard_packet["operator_required_count"] == 1
    assert dashboard_packet["next_safe_command"] == live_handoff["entries"][0]["commands"][
        "validate_operator_response_prefilled"
    ]
    assert dashboard_packet["next_explicit_operator_command"] == live_handoff["entries"][0]["pilot_command_sequence"][
        "next_explicit_operator_step"
    ]["command"]
    assert dashboard_packet["forbidden_live_or_sink_write_from_dashboard"] is True
    assert dashboard_packet["writes_attempted"] == 0
    assert dashboard_packet["network_calls_made"] == 0
    approval_packet = client.get(
        f"/runs/{run_id}/live-pilot-approval-packet",
        params={"job_id": job_id},
    ).json()
    assert approval_packet["schema"] == "business-card-watchdog.live-pilot-approval-packet.v1"
    assert approval_packet["state"] == "ready"
    assert approval_packet["entry_count"] == 1
    assert approval_packet["entries"][0]["job_id"] == job_id
    assert approval_packet["entries"][0]["sink"] == "google_contacts"
    assert approval_packet["entries"][0]["operator"] == "api-test"
    assert approval_packet["entries"][0]["scope"] == "lookup"
    assert approval_packet["entries"][0]["validation_command_prefilled"] == live_handoff["entries"][0]["commands"][
        "validate_operator_response_prefilled"
    ]
    assert approval_packet["creates_selected_live_target"] is False
    assert approval_packet["writes_attempted"] == 0
    assert approval_packet["network_calls_made"] == 0
    response = (
        f"run_id={run_id} job_id={job_id} sink=google_contacts "
        "operator=api-test scope=lookup safety_confirmation=fixture contact is safe for google contacts test profile"
    )
    selected_target_preflight = client.post(
        f"/runs/{run_id}/selected-live-target-preflight",
        json={"response": response},
    ).json()
    assert selected_target_preflight["schema"] == "business-card-watchdog.selected-live-target-preflight.v1"
    assert selected_target_preflight["state"] == "blocked"
    assert selected_target_preflight["would_create_selected_live_target"] is False
    assert selected_target_preflight["creates_selected_live_target"] is False
    assert selected_target_preflight["select_target_command"] is None
    assert "selected_live_target already exists" in selected_target_preflight["blocked_reasons"][0]
    assert selected_target_preflight["writes_attempted"] == 0
    assert selected_target_preflight["network_calls_made"] == 0
    selected_target_preview = client.post(
        f"/runs/{run_id}/selected-live-target-preview",
        json={"response": response},
    ).json()
    assert selected_target_preview["schema"] == "business-card-watchdog.selected-live-target-artifact-preview.v1"
    assert selected_target_preview["state"] == "blocked"
    assert selected_target_preview["artifact_preview"] is None
    assert selected_target_preview["would_create_selected_live_target"] is False
    assert selected_target_preview["creates_selected_live_target"] is False
    assert "selected_live_target already exists" in selected_target_preview["blocked_reasons"][0]
    assert selected_target_preview["writes_attempted"] == 0
    assert selected_target_preview["network_calls_made"] == 0
    selected_target_from_response = client.post(
        f"/runs/{run_id}/selected-live-target-from-response",
        json={"response": response},
    ).json()
    assert selected_target_from_response["schema"] == "business-card-watchdog.selected-live-target-from-response.v1"
    assert selected_target_from_response["state"] == "preview"
    assert selected_target_from_response["write_selected_target"] is False
    assert selected_target_from_response["preview"]["state"] == "blocked"
    assert selected_target_from_response["target"] is None
    assert selected_target_from_response["target_path"] is None
    assert selected_target_from_response["creates_selected_live_target"] is False
    assert selected_target_from_response["writes_attempted"] == 0
    assert selected_target_from_response["network_calls_made"] == 0
    selected_target_handoff = client.post(
        f"/runs/{run_id}/selected-live-target-handoff-from-response",
        json={"response": response},
    ).json()
    assert selected_target_handoff["schema"] == (
        "business-card-watchdog.selected-live-target-handoff-from-response.v1"
    )
    assert selected_target_handoff["state"] == "audit_blocked"
    assert selected_target_handoff["job_id"] == job_id
    assert selected_target_handoff["validation_state"] == "ready_for_live_lookup_request"
    assert selected_target_handoff["selected_target_audit"]["state"] == "blocked"
    assert selected_target_handoff["write_audit"] is False
    assert selected_target_handoff["audit_written"] is False
    assert selected_target_handoff["creates_selected_live_target"] is False
    assert selected_target_handoff["writes_attempted"] == 0
    assert selected_target_handoff["network_calls_made"] == 0
    lookup_smoke_handoff_from_response = client.post(
        f"/runs/{run_id}/lookup-smoke-handoff-from-response",
        json={"response": response},
    ).json()
    assert lookup_smoke_handoff_from_response["schema"] == (
        "business-card-watchdog.lookup-smoke-handoff-from-response.v1"
    )
    assert lookup_smoke_handoff_from_response["state"] == "handoff_blocked"
    assert lookup_smoke_handoff_from_response["job_id"] == job_id
    assert lookup_smoke_handoff_from_response["sink"] == "google_contacts"
    assert lookup_smoke_handoff_from_response["operator"] == "api-test"
    assert lookup_smoke_handoff_from_response["lookup_smoke_handoff"]["state"] == "blocked"
    assert lookup_smoke_handoff_from_response["write_handoff"] is False
    assert lookup_smoke_handoff_from_response["handoff_written"] is False
    assert lookup_smoke_handoff_from_response["writes_attempted"] == 0
    assert lookup_smoke_handoff_from_response["network_calls_made"] == 0
    execution_packet = client.post(
        f"/runs/{run_id}/selected-lookup-smoke-execution-packet-from-response",
        json={"response": response},
    ).json()
    assert execution_packet["schema"] == (
        "business-card-watchdog.selected-lookup-smoke-execution-packet-from-response.v1"
    )
    assert execution_packet["state"] == "blocked"
    assert execution_packet["job_id"] == job_id
    assert execution_packet["sink"] == "google_contacts"
    assert execution_packet["operator"] == "api-test"
    assert execution_packet["execute_selected_lookup_smoke"] is False
    assert execution_packet["would_execute_selected_lookup_smoke"] is False
    assert execution_packet["smoke"] is None
    assert execution_packet["smoke_path"] is None
    assert execution_packet["writes_attempted"] == 0
    assert execution_packet["network_calls_made"] == 0
    write_packet = client.post(
        f"/runs/{run_id}/selected-write-pilot-execution-packet-from-response",
        json={"response": response},
    ).json()
    assert write_packet["schema"] == (
        "business-card-watchdog.selected-write-pilot-execution-packet-from-response.v1"
    )
    assert write_packet["state"] == "blocked"
    assert write_packet["job_id"] == job_id
    assert write_packet["sink"] == "google_contacts"
    assert write_packet["operator"] == "api-test"
    assert write_packet["execute_write_pilot"] is False
    assert write_packet["would_execute_write_pilot"] is False
    assert write_packet["write_pilot"] is None
    assert write_packet["write_pilot_path"] is None
    assert write_packet["writes_attempted"] == 0
    assert write_packet["network_calls_made"] == 0
    readback_packet = client.post(
        f"/runs/{run_id}/selected-readback-pilot-execution-packet-from-response",
        json={"response": response},
    ).json()
    assert readback_packet["schema"] == (
        "business-card-watchdog.selected-readback-pilot-execution-packet-from-response.v1"
    )
    assert readback_packet["state"] == "blocked"
    assert readback_packet["job_id"] == job_id
    assert readback_packet["sink"] == "google_contacts"
    assert readback_packet["operator"] == "api-test"
    assert readback_packet["execute_readback_pilot"] is False
    assert readback_packet["would_execute_readback_pilot"] is False
    assert readback_packet["readback_pilot"] is None
    assert readback_packet["readback_pilot_path"] is None
    assert readback_packet["writes_attempted"] == 0
    assert readback_packet["network_calls_made"] == 0
    closeout_packet = client.post(
        f"/runs/{run_id}/live-pilot-closeout-packet-from-response",
        json={"response": response},
    ).json()
    assert closeout_packet["schema"] == "business-card-watchdog.live-pilot-closeout-packet-from-response.v1"
    assert closeout_packet["state"] == "closeout_incomplete"
    assert closeout_packet["job_id"] == job_id
    assert closeout_packet["sink"] == "google_contacts"
    assert closeout_packet["operator"] == "api-test"
    assert closeout_packet["write_closeout"] is False
    assert closeout_packet["closeout_written"] is False
    assert closeout_packet["closeout_path"] is None
    assert closeout_packet["closeout_report"]["state"] == "incomplete"
    assert closeout_packet["writes_attempted"] == 0
    assert closeout_packet["network_calls_made"] == 0
    workflow_packet = client.post(
        f"/runs/{run_id}/live-pilot-operator-workflow-packet-from-response",
        json={"response": response},
    ).json()
    assert workflow_packet["schema"] == (
        "business-card-watchdog.live-pilot-operator-workflow-packet-from-response.v1"
    )
    assert workflow_packet["state"] == "workflow_blocked"
    assert workflow_packet["job_id"] == job_id
    assert workflow_packet["sink"] == "google_contacts"
    assert workflow_packet["operator"] == "api-test"
    assert workflow_packet["blocked_step_count"] >= 1
    assert workflow_packet["packets"]["live_pilot_closeout"]["state"] == "closeout_incomplete"
    assert [step["step"] for step in workflow_packet["step_summary"]] == [
        "selected_target",
        "lookup_handoff",
        "lookup_smoke",
        "write_pilot",
        "readback_pilot",
        "closeout",
    ]
    assert workflow_packet["writes_attempted"] == 0
    assert workflow_packet["network_calls_made"] == 0
    rehearsal = client.post(
        f"/runs/{run_id}/live-pilot-operator-rehearsal-from-response",
        json={"response": response},
    ).json()
    assert rehearsal["schema"] == "business-card-watchdog.live-pilot-operator-rehearsal-from-response.v1"
    assert rehearsal["state"] == "ready_for_explicit_operator_step"
    assert rehearsal["workflow_state"] == "workflow_blocked"
    assert rehearsal["job_id"] == job_id
    assert rehearsal["sink"] == "google_contacts"
    assert rehearsal["operator"] == "api-test"
    assert rehearsal["workflow_packet"]["schema"] == (
        "business-card-watchdog.live-pilot-operator-workflow-packet-from-response.v1"
    )
    assert rehearsal["next_safe_command"].startswith("runs live-pilot-operator-workflow-packet-from-response")
    assert rehearsal["next_explicit_operator_command"]
    assert rehearsal["rehearsal_steps"][0]["safe_to_auto_continue"] is True
    assert rehearsal["rehearsal_steps"][1]["requires_explicit_operator_action"] is True
    assert rehearsal["writes_attempted"] == 0
    assert rehearsal["network_calls_made"] == 0
    readiness_export = client.post(
        f"/runs/{run_id}/live-pilot-readiness-export-from-response",
        json={"response": response, "write": False},
    ).json()
    assert readiness_export["schema"] == "business-card-watchdog.live-pilot-readiness-export-from-response.v1"
    assert readiness_export["state"] == "ready_for_explicit_operator_step"
    assert readiness_export["write"] is False
    assert readiness_export["export_written"] is False
    assert readiness_export["export_path"] is None
    assert readiness_export["operator_response_redacted"]["raw_response_stored"] is False
    assert "safety_confirmation" not in readiness_export["operator_response_redacted"]["fields"]
    assert response not in json.dumps(readiness_export, sort_keys=True)
    assert readiness_export["writes_attempted"] == 0
    assert readiness_export["network_calls_made"] == 0
    checklist = client.post(
        f"/runs/{run_id}/live-pilot-execution-checklist-from-response",
        json={"response": response},
    ).json()
    assert checklist["schema"] == "business-card-watchdog.live-pilot-execution-checklist-from-response.v1"
    assert checklist["state"] == "blocked"
    assert checklist["readiness_export_loaded"] is False
    assert checklist["executable_live_command"] is None
    assert "live_pilot_readiness_export.json is required before showing executable live command" in checklist[
        "blocked_reasons"
    ]
    assert checklist["writes_attempted"] == 0
    assert checklist["network_calls_made"] == 0
    command_copy_packet = client.post(
        f"/runs/{run_id}/live-pilot-command-copy-packet-from-response",
        json={"response": response},
    ).json()
    assert command_copy_packet["schema"] == (
        "business-card-watchdog.live-pilot-command-copy-packet-from-response.v1"
    )
    assert command_copy_packet["state"] == "blocked"
    assert command_copy_packet["checklist_state"] == "blocked"
    assert command_copy_packet["acknowledgement_required"] is True
    assert command_copy_packet["acknowledgement_ok"] is False
    assert command_copy_packet["command_copy_text"] is None
    assert command_copy_packet["executable_live_command"] is None
    assert "operator acknowledgement is required before command copy text is shown" in command_copy_packet[
        "blocked_reasons"
    ]
    assert command_copy_packet["writes_attempted"] == 0
    assert command_copy_packet["network_calls_made"] == 0
    validation = client.post(
        f"/runs/{run_id}/live-pilot-operator-response-validation",
        json={"response": response},
    ).json()
    assert validation["schema"] == "business-card-watchdog.live-pilot-operator-response-validation.v1"
    assert validation["state"] == "ready_for_live_lookup_request"
    assert validation["next_validation_step"] == "selected_target_audit"
    assert validation["matching_template"]["job_id"] == job_id
    assert validation["select_target_command"] is None
    assert validation["commands"]["select_target"] is None
    assert validation["selected_target_audit_command"] == (
        f"sinks selected-target-audit {job_id} --run-id {run_id} --scope lookup --no-write --json"
    )
    assert validation["lookup_smoke_handoff_command"] == (
        f"sinks lookup-smoke-handoff {job_id} --run-id {run_id} --sink google_contacts --approved-by api-test --json"
    )
    assert [item["step"] for item in validation["post_selection_sequence"]] == [
        "selected_target_audit",
        "lookup_smoke_handoff",
    ]
    assert validation["post_selection_sequence"][0]["command"] == validation["selected_target_audit_command"]
    assert validation["validation_command_sequence"]["safe_inspection_step_count"] == 2
    assert validation["validation_command_sequence"]["explicit_operator_step_count"] == 0
    assert validation["validation_command_sequence"]["live_call_step_count"] == 0
    assert validation["validation_command_sequence"]["sink_write_step_count"] == 0
    api_approval_readback = validation["approval_readback"]
    assert api_approval_readback["schema"] == "business-card-watchdog.live-pilot-operator-approval-readback.v1"
    assert api_approval_readback["state"] == "ready"
    assert api_approval_readback["validation_state"] == "ready_for_live_lookup_request"
    assert api_approval_readback["response_matches_template"] is True
    assert api_approval_readback["matched_template_job_id"] == job_id
    assert api_approval_readback["parsed_fields"]["operator"] == "api-test"
    assert api_approval_readback["parsed_fields"]["safety_confirmation_present"] is True
    assert api_approval_readback["missing_field_count"] == 0
    assert api_approval_readback["mismatch_count"] == 0
    assert api_approval_readback["next_safe_step"] == "selected_target_audit"
    assert api_approval_readback["next_safe_command"] == validation["selected_target_audit_command"]
    assert api_approval_readback["creates_selected_live_target"] is False
    assert api_approval_readback["writes_attempted"] == 0
    assert api_approval_readback["network_calls_made"] == 0
    assert validation["creates_selected_live_target"] is False
    assert validation["writes_attempted"] == 0
    assert validation["network_calls_made"] == 0
    abandonment = client.post(
        f"/jobs/{job_id}/live-pilot-abandonment",
        json={"run_id": run_id, "operator": "api-test", "reason": "wrong target profile selected"},
    ).json()
    assert abandonment["abandonment"]["schema"] == "business-card-watchdog.live-pilot-abandonment.v1"
    assert abandonment["abandonment"]["writes_attempted"] == 0
    abandoned_status = client.get(f"/runs/{run_id}/live-pilot-status", params={"write": False}).json()
    assert abandoned_status["entries"][0]["selected_target_identity"] == selected["target"]["selection_id"]
    assert abandoned_status["entries"][0]["abandonment_identity"] == selected["target"]["selection_id"]
    abandoned_live_packet = client.post(
        f"/jobs/{job_id}/live-selection-packet",
        json={"run_id": run_id, "sink": "google_contacts", "operator": "api-test", "write": False},
    ).json()
    assert abandoned_live_packet["existing_selected_target"]["identity"] == selected["target"]["selection_id"]
    assert abandoned_live_packet["existing_selected_target"]["abandoned"] is True
    assert abandoned_live_packet["existing_selected_target"]["replacement_requires_abandonment"] is False
    assert abandoned_live_packet["existing_selected_target"]["can_select_replacement_now"] is True
    assert abandoned_live_packet["existing_selected_target"]["abandon_command"] is None
    assert client.get("/runs").json()[0]["run_id"] == run_id
    assert client.get(f"/runs/{run_id}").json()["run_id"] == run_id
    assert client.get(f"/runs/{run_id}/summary").json()["needs_review_count"] == 1
    phase_report = client.get(f"/runs/{run_id}/phase-report").json()
    assert phase_report["schema"] == "business-card-watchdog.phase-report.v1"
    assert phase_report["review_workbook_preview"]["schema"] == (
        "business-card-watchdog.review-workbook-preview-phase.v1"
    )
    assert phase_report["review_workbook_preview"]["state"] == "not_started"
    assert phase_report["dashboard_summary"]["schema"] == "business-card-watchdog.phase-dashboard-summary.v1"
    assert phase_report["dashboard_summary"]["blocked_phases"] == [{"phase": "review", "count": 1}]
    assert phase_report["commands"]["live_pilot_handoff"] == f"runs live-pilot-handoff {run_id}"
    assert phase_report["phases"][2]["phase"] == "review"
    assert phase_report["phases"][2]["counts"]["blocked"] == 1
    readiness_report = client.get(f"/runs/{run_id}/pilot-readiness").json()
    assert readiness_report["schema"] == "business-card-watchdog.pilot-readiness-report.v1"
    assert readiness_report["state"] == "explicit_operator_required"
    assert readiness_report["commands"]["live_pilot_handoff"] == f"runs live-pilot-handoff {run_id}"
    assert readiness_report["blocked_job_ids"] == [job_id]
    assert client.get(f"/runs/{run_id}/jobs").json()[0]["job_id"] == job_id
    assert client.get(f"/jobs/{job_id}", params={"run_id": run_id}).json()["job_id"] == job_id
    assert client.get("/reviews", params={"run_id": run_id}).json()[0]["job_id"] == job_id
    filtered_reviews = client.get(
        "/reviews",
        params={"run_id": run_id, "next_action": "review_contact", "artifact_kind": "contact_spec"},
    ).json()
    assert [entry["job_id"] for entry in filtered_reviews] == [job_id]

    review_bundle = client.post(f"/runs/{run_id}/review-bundle").json()
    assert review_bundle["schema"] == "business-card-watchdog.review-bundle.v1"
    assert review_bundle["entries"][0]["job_id"] == job_id
    assert review_bundle["entries"][0]["next_action"]["action"] == "review_contact"
    assert review_bundle["groups"]["by_state"]["needs_review"]["count"] == 1
    assert review_bundle["decision_import_template"][0]["action"] == "approve_for_routing"
    assert review_bundle["commands"]["live_pilot_handoff"] == f"runs live-pilot-handoff {run_id}"
    assert review_bundle["commands"]["validate_operator_response"] == (
        f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
    )
    assert review_bundle["entries"][0]["commands"]["validate_operator_response"] == (
        f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
    )
    review_html = client.post(f"/runs/{run_id}/review-html").json()
    assert review_html["schema"] == "business-card-watchdog.review-html.v1"
    assert "Business Card Review" in review_html["html"]
    assert f"runs live-pilot-handoff {run_id}" in review_html["html"]
    review_workbook = client.post(f"/runs/{run_id}/review-workbook").json()
    assert review_workbook["schema"] == "business-card-watchdog.review-workbook.v1"
    workbook_rows = list(csv.DictReader(StringIO(review_workbook["csv"])))
    assert workbook_rows[0]["job_id"] == job_id
    assert workbook_rows[0]["next_action"] == "review_contact"
    assert workbook_rows[0]["review_action"] == "approve_for_routing"
    assert workbook_rows[0]["live_pilot_handoff_command"] == f"runs live-pilot-handoff {run_id}"
    assert workbook_rows[0]["validate_operator_response_command"] == (
        f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
    )
    workbook_rows[0]["review_action"] = "approve_for_routing"
    workbook_rows[0]["corrected_full_name"] = "API Workbook"
    workbook_csv = StringIO()
    workbook_writer = csv.DictWriter(workbook_csv, fieldnames=list(workbook_rows[0]))
    workbook_writer.writeheader()
    workbook_writer.writerows(workbook_rows)
    workbook_preview = client.post(
        f"/runs/{run_id}/review-decisions",
        json={
            "reviewer": "api-workbook",
            "decisions_csv": workbook_csv.getvalue(),
            "preview": True,
            "preview_write": True,
        },
    ).json()
    assert workbook_preview["schema"] == "business-card-watchdog.review-workbook-preview.v1"
    assert workbook_preview["ready_count"] == 1
    assert "row_number,status,run_id,job_id,action,errors,warnings" in workbook_preview["validation_csv"]
    assert Path(workbook_preview["validation_csv_path"]).exists()
    assert workbook_preview["writes_attempted"] == 0
    workbook_validation = client.post(
        f"/runs/{run_id}/review-workbook-validation",
        json={"reviewer": "api-workbook", "decisions_csv": workbook_csv.getvalue()},
    ).json()
    assert workbook_validation["schema"] == "business-card-watchdog.review-workbook-preview.v1"
    assert workbook_validation["ready_count"] == 1
    assert "row_number,status,run_id,job_id,action,errors,warnings" in workbook_validation["validation_csv"]
    assert "validation_csv_path" not in workbook_validation
    workbook_import = client.post(
        f"/runs/{run_id}/review-decisions",
        json={"reviewer": "api-workbook", "decisions_csv": workbook_csv.getvalue()},
    ).json()
    assert workbook_import["import"]["source_format"] == "csv"
    assert workbook_import["results"][0]["job_state"] == "ready_to_route"
    review_import = client.post(
        f"/runs/{run_id}/review-decisions",
        json={
            "reviewer": "api-batch",
            "decisions": [
                {
                    "job_id": job_id,
                    "action": "approve_for_routing",
                    "field_corrections": {"full_name": "API Batch"},
                }
            ],
        },
    ).json()
    assert review_import["import"]["schema"] == "business-card-watchdog.review-decisions-import.v1"
    assert review_import["results"][0]["job_state"] == "ready_to_route"
    assert client.post("/enrichment/check", json={"mode": "api", "run_id": run_id}).json()["checks"][0]["status"] == "blocked"
    lookup = client.post(f"/jobs/{job_id}/sink-lookup-plan", params={"run_id": run_id}).json()
    assert lookup["lookup_plan"]["schema"] == "business-card-watchdog.sink-lookup-plan.v1"
    assert lookup["lookup_plan"]["network_calls_made"] == 0
    lookup_readiness = client.post(
        f"/jobs/{job_id}/sink-lookup-readiness",
        json={"run_id": run_id, "sink": "google_contacts"},
    ).json()
    assert lookup_readiness["schema"] == "business-card-watchdog.live-lookup-readiness.v1"
    assert lookup_readiness["state"] == "blocked"
    assert lookup_readiness["writes_attempted"] == 0
    assert lookup_readiness["network_calls_made"] == 0
    assert client.post(f"/jobs/{job_id}/sink-plan", params={"run_id": run_id}).json()["plan"]["schema"] == "business-card-watchdog.sink-plan.v1"
    preflight = client.post(f"/jobs/{job_id}/sink-apply-preflight", json={"run_id": run_id}).json()
    assert preflight["preflight"]["schema"] == "business-card-watchdog.sink-apply-preflight.v1"
    assert preflight["preflight"]["writes_attempted"] == 0
    apply_decision = client.post(
        f"/jobs/{job_id}/sink-apply-decision",
        json={"run_id": run_id, "decision": "approve", "reviewer": "api-test"},
    ).json()
    assert apply_decision["decision"]["schema"] == "business-card-watchdog.sink-apply-decision.v1"
    assert apply_decision["decision"]["network_calls_made"] == 0
    pilot_readiness = client.post(
        f"/jobs/{job_id}/sink-apply-pilot-readiness",
        json={"run_id": run_id},
    ).json()
    assert pilot_readiness["readiness"]["schema"] == "business-card-watchdog.sink-apply-pilot-readiness.v1"
    assert pilot_readiness["readiness"]["network_calls_made"] == 0
    apply_result = client.post(
        f"/jobs/{job_id}/sink-apply",
        json={"run_id": run_id, "apply": True, "simulate": True},
    ).json()
    assert apply_result["result"]["schema"] == "business-card-watchdog.sink-apply-result.v1"
    assert apply_result["result"]["state"] == "mock_applied"
    assert apply_result["result"]["writes_attempted"] == 0
    adapter_request = client.post(
        f"/jobs/{job_id}/sink-adapter-request",
        json={"run_id": run_id, "phase": "readback"},
    ).json()
    assert adapter_request["request"]["schema"] == "business-card-watchdog.sink-adapter-request.v1"
    assert adapter_request["request"]["phase"] == "readback"
    assert adapter_request["request"]["network_calls_made"] == 0
    lookup_result = client.post(
        f"/jobs/{job_id}/sink-lookup-result",
        json={
            "run_id": run_id,
            "matches_by_sink": {
                "google_contacts": [
                    {"resource_id": "people/c123", "confidence": 0.91, "basis": ["email"]}
                ]
            },
        },
    ).json()
    assert lookup_result["result"]["schema"] == "business-card-watchdog.sink-lookup-result.v1"
    assert lookup_result["result"]["state"] == "no_match"
    assert lookup_result["result"]["network_calls_made"] == 0
    downstream_duplicate = client.post(
        f"/jobs/{job_id}/downstream-duplicate-assessment",
        params={"run_id": run_id},
    ).json()
    assert downstream_duplicate["assessment"]["schema"] == "business-card-watchdog.duplicate-assessment.v1"
    assert downstream_duplicate["assessment"]["state"] == "no_match"
    artifact_dir = data_dir / "runs" / run_id / "artifacts" / job_id
    (artifact_dir / "enrichment_result.json").write_text(
        json.dumps(
            {
                "schema": "business-card-watchdog.enrichment-result.v1",
                "merge_proposals": [
                    {
                        "field": "notes",
                        "value": "Public-web corroboration candidate: https://example.test/api",
                        "source": "public_web",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    merge = client.post(
        f"/jobs/{job_id}/review",
        json={
            "run_id": run_id,
            "reviewer": "api-test",
            "action": "approve_enrichment_merge",
            "approved_enrichment_fields": ["notes"],
        },
    ).json()
    assert merge["submission"]["approved_enrichment_fields"] == ["notes"]
    (artifact_dir / "duplicate_assessment.json").write_text(
        '{"schema": "business-card-watchdog.duplicate-assessment.v1", "state": "possible_duplicate"}\n',
        encoding="utf-8",
    )
    duplicate = client.post(
        f"/jobs/{job_id}/review",
        json={
            "run_id": run_id,
            "reviewer": "api-test",
            "action": "resolve_duplicate",
            "duplicate_resolution": {"decision": "create_new", "reason": "confirmed separate contact"},
        },
    ).json()
    assert duplicate["submission"]["duplicate_resolution"]["decision"] == "create_new"
    review = client.post(
        f"/jobs/{job_id}/review",
        json={
            "run_id": run_id,
            "reviewer": "api-test",
            "action": "approve_for_routing",
            "field_corrections": {"full_name": "API Fixture"},
            "crop_selection": {"crop_id": "c01"},
        },
    ).json()
    assert review["job"]["state"] == "ready_to_route"
    run_next = client.post("/actions/run-next", json={"run_id": run_id, "limit": 2}).json()
    assert run_next["executed_count"] >= 1
    assert run_next["executed"][0]["action"].startswith(("plan_", "prepare_", "record_", "assess_"))
    assert run_next["safe_inspection_commands"]["live_pilot_status"] == (
        f"runs live-pilot-status {run_id} --no-write --json"
    )
    assert run_next["safe_inspection_commands"]["operator_dashboard"] == (
        f"operator-dashboard --run-id {run_id} --json"
    )
    assert run_next["phase_report_before"]["schema"] == "business-card-watchdog.phase-report.v1"
    assert run_next["phase_report_after"]["schema"] == "business-card-watchdog.phase-report.v1"


def test_api_run_dry_run_closeout_reports_no_live(tmp_path: Path, monkeypatch) -> None:
    from business_card_watchdog.api import create_app

    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    write_config(config_path, data_dir)
    source_dir = tmp_path / "cards"
    write_synthetic_image(source_dir / "card.png")
    config = AppConfig(
        config_path=config_path,
        data_dir=data_dir,
        prefilter=PrefilterConfig(enabled=False),
        sink=SinkConfig(google_contacts=True, odoo=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts", "odoo"]}],
    )
    orchestrator = BatchOrchestrator(config)
    monkeypatch.setattr(orchestrator, "adapter", SyntheticSkillAdapter())
    run_dir = orchestrator.process_source(str(source_dir), dry_run=True, workers=1)
    client = TestClient(create_app(config_path))

    payload = client.get(f"/runs/{run_dir.name}/dry-run-closeout", params={"write": "false"}).json()

    assert payload["schema"] == "business-card-watchdog.dry-run-closeout.v1"
    assert payload["state"] == "ready_for_review_and_routing"
    assert payload["dry_run"] is True
    assert payload["run_state"] == "completed"
    assert payload["job_count"] == 1
    assert payload["contact_candidate_count"] == 1
    assert payload["sink_payload_count"] == 1
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    assert payload["live_sink_calls_made"] is False
    assert payload["runtime_artifact_written"] is False


def test_api_run_dry_run_review_handoff_reports_safe_next_steps(tmp_path: Path, monkeypatch) -> None:
    from business_card_watchdog.api import create_app

    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    write_config(config_path, data_dir)
    source_dir = tmp_path / "cards"
    write_synthetic_image(source_dir / "card.png")
    config = AppConfig(
        config_path=config_path,
        data_dir=data_dir,
        prefilter=PrefilterConfig(enabled=False),
        sink=SinkConfig(google_contacts=True, odoo=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts", "odoo"]}],
    )
    orchestrator = BatchOrchestrator(config)
    monkeypatch.setattr(orchestrator, "adapter", SyntheticSkillAdapter())
    run_dir = orchestrator.process_source(str(source_dir), dry_run=True, workers=1)
    client = TestClient(create_app(config_path))

    payload = client.get(f"/runs/{run_dir.name}/dry-run-review-handoff", params={"write": "false"}).json()

    assert payload["schema"] == "business-card-watchdog.dry-run-review-handoff.v1"
    assert payload["state"] == "ready_for_safe_agent_loop"
    assert payload["closeout_state"] == "ready_for_review_and_routing"
    assert payload["ready_to_route_count"] == 1
    assert payload["safe_auto_action_count"] == 1
    assert payload["explicit_operator_action_count"] == 0
    assert payload["next_action_counts"] == {"plan_sink_lookup": 1}
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    assert payload["runtime_artifact_written"] is False


def test_api_run_dry_run_safe_loop_executes_bounded_safe_actions(tmp_path: Path, monkeypatch) -> None:
    from business_card_watchdog.api import create_app

    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    write_config(config_path, data_dir)
    source_dir = tmp_path / "cards"
    write_synthetic_image(source_dir / "card.png")
    config = AppConfig(
        config_path=config_path,
        data_dir=data_dir,
        prefilter=PrefilterConfig(enabled=False),
        sink=SinkConfig(google_contacts=True, odoo=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts", "odoo"]}],
    )
    orchestrator = BatchOrchestrator(config)
    monkeypatch.setattr(orchestrator, "adapter", SyntheticSkillAdapter())
    run_dir = orchestrator.process_source(str(source_dir), dry_run=True, workers=1)
    client = TestClient(create_app(config_path))

    payload = client.get(
        f"/runs/{run_dir.name}/dry-run-safe-loop",
        params={"limit": 2, "write": "false"},
    ).json()

    assert payload["schema"] == "business-card-watchdog.dry-run-safe-loop.v1"
    assert payload["state"] == "safe_loop_executed"
    assert payload["executed_count"] == 2
    assert [action["action"] for action in payload["executed"]] == [
        "plan_sink_lookup",
        "prepare_sink_lookup_adapter",
    ]
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    assert payload["runtime_artifact_written"] is False


def test_api_offline_pilot_gap_audit_reports_remaining_boundaries(tmp_path: Path) -> None:
    from business_card_watchdog.api import create_app

    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    write_config(config_path, data_dir)
    client = TestClient(create_app(config_path))

    audit = client.get("/offline-pilot-gap-audit").json()

    assert audit["schema"] == "business-card-watchdog.offline-pilot-gap-audit.v1"
    assert audit["state"] == "ready_for_live_operator_boundary"
    assert audit["recommended_next_slice"] == "operator_selected_live_smoke"
    assert audit["coverage"]["missing_doc_count"] == 0
    assert audit["writes_attempted"] == 0
    assert audit["network_calls_made"] == 0
    assert Path(audit["audit_path"]).exists()


def test_api_operator_selected_live_smoke_preflight_reports_blocked_boundary(tmp_path: Path) -> None:
    from business_card_watchdog.api import create_app

    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    config_path.write_text(
        f'data_dir = "{data_dir}"\n[watch]\ninputs = []\n[sink]\ngoogle_contacts = true\n',
        encoding="utf-8",
    )
    run_id, _job_id = make_recorded_run(
        AppConfig(
            config_path=config_path,
            data_dir=data_dir,
            sink=SinkConfig(google_contacts=True, dry_run=True),
        )
    )
    client = TestClient(create_app(config_path))

    preflight = client.post(
        "/operator-selected-live-smoke-preflight",
        json={"run_id": run_id, "sink": "google_contacts"},
    ).json()

    assert preflight["schema"] == "business-card-watchdog.operator-selected-live-smoke-preflight.v1"
    assert preflight["state"] == "needs_preparation"
    assert preflight["run_id"] == run_id
    assert preflight["sink"] == "google_contacts"
    assert preflight["entry_count"] == 1
    assert preflight["blocked_entry_count"] == 1
    assert preflight["writes_attempted"] == 0
    assert preflight["network_calls_made"] == 0
    assert Path(preflight["preflight_path"]).exists()


def test_api_review_routing_drill_outputs_fixture_artifact(tmp_path: Path) -> None:
    from business_card_watchdog.api import create_app

    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    write_config(config_path, data_dir)
    client = TestClient(create_app(config_path))

    drill = client.post("/drills/review-routing").json()

    assert drill["schema"] == "business-card-watchdog.review-routing-drill.v1"
    assert drill["private_sources_used"] is False
    assert drill["agent_loop_readback"]["state"] == "passed"
    assert drill["agent_loop_readback"]["next_manual_boundary"] == "decide_sink_apply"
    assert drill["safe_actions"]["skipped_actions"] == ["decide_sink_apply"]
    assert drill["network_calls_made"] == 0
    assert drill["writes_attempted"] == 0
    assert Path(drill["drill_path"]).exists()


def test_api_child_reviews_lists_promoted_child_candidates(tmp_path: Path, monkeypatch) -> None:
    pytest.importorskip("cv2")
    from business_card_watchdog.api import create_app

    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    write_config(config_path, data_dir)
    source_dir = tmp_path / "images"
    write_multi_card_image(source_dir / "multi.jpg")
    config = AppConfig(config_path=config_path, data_dir=data_dir)
    orchestrator = BatchOrchestrator(config)
    monkeypatch.setattr(orchestrator, "adapter", SyntheticSkillAdapter())
    run_dir = orchestrator.process_source(str(source_dir), dry_run=True, workers=1)
    client = TestClient(create_app(config_path))

    payload = client.get("/reviews/children", params={"run_id": run_dir.name}).json()

    assert len(payload) >= 3
    assert payload[0]["state"] == "needs_review"
    assert payload[0]["next_action"]["action"] == "review_child_contact"
    assert payload[0]["contact_candidate"]["source"] == "child_verification_result"


def test_api_child_review_approves_promoted_child_candidate(tmp_path: Path, monkeypatch) -> None:
    pytest.importorskip("cv2")
    from business_card_watchdog.api import create_app

    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    write_config(config_path, data_dir)
    source_dir = tmp_path / "images"
    write_multi_card_image(source_dir / "multi.jpg")
    config = AppConfig(config_path=config_path, data_dir=data_dir)
    orchestrator = BatchOrchestrator(config)
    monkeypatch.setattr(orchestrator, "adapter", SyntheticSkillAdapter())
    run_dir = orchestrator.process_source(str(source_dir), dry_run=True, workers=1)
    service = BusinessCardService(config)
    candidate_id = str(service.child_review_queue(run_id=run_dir.name)[0]["candidate_id"])
    client = TestClient(create_app(config_path))

    payload = client.post(
        f"/reviews/children/{candidate_id}",
        json={
            "run_id": run_dir.name,
            "reviewer": "operator",
            "action": "approve_child_for_routing",
            "field_corrections": {"email": "api-child@example.test"},
        },
    ).json()

    assert payload["candidate_id"] == candidate_id
    assert payload["state"] == "approved_for_dedupe"
    assert payload["reviewed_contact"]["flat"]["email"] == "api-child@example.test"
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0


def test_api_child_route_prep_writes_dry_run_plans(tmp_path: Path, monkeypatch) -> None:
    pytest.importorskip("cv2")
    from business_card_watchdog.api import create_app

    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    write_config(config_path, data_dir)
    source_dir = tmp_path / "images"
    write_multi_card_image(source_dir / "multi.jpg")
    config = AppConfig(
        config_path=config_path,
        data_dir=data_dir,
        sink=SinkConfig(google_contacts=True, dry_run=True),
    )
    orchestrator = BatchOrchestrator(config)
    monkeypatch.setattr(orchestrator, "adapter", SyntheticSkillAdapter())
    run_dir = orchestrator.process_source(str(source_dir), dry_run=True, workers=1)
    service = BusinessCardService(config)
    candidate_id = str(service.child_review_queue(run_id=run_dir.name)[0]["candidate_id"])
    service.submit_child_review(
        run_id=run_dir.name,
        candidate_id=candidate_id,
        reviewer="operator",
        action="approve_child_for_routing",
    )
    client = TestClient(create_app(config_path))

    queue = client.get("/reviews/children/route-prep", params={"run_id": run_dir.name}).json()
    payload = client.post(
        f"/reviews/children/{candidate_id}/route-prep",
        json={"run_id": run_dir.name},
    ).json()

    assert any(entry["candidate_id"] == candidate_id for entry in queue)
    assert payload["state"] == "routing_prepared"
    assert payload["lookup_plan"]["dry_run"] is True
    assert payload["sink_plan"]["dry_run"] is True
    assert payload["result"]["sink_write_allowed"] is False
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0


def test_api_child_lookup_result_and_duplicate_assessment(tmp_path: Path, monkeypatch) -> None:
    pytest.importorskip("cv2")
    from business_card_watchdog.api import create_app

    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    write_config(config_path, data_dir)
    source_dir = tmp_path / "images"
    write_multi_card_image(source_dir / "multi.jpg")
    config = AppConfig(
        config_path=config_path,
        data_dir=data_dir,
        sink=SinkConfig(google_contacts=True, dry_run=True),
    )
    orchestrator = BatchOrchestrator(config)
    monkeypatch.setattr(orchestrator, "adapter", SyntheticSkillAdapter())
    run_dir = orchestrator.process_source(str(source_dir), dry_run=True, workers=1)
    service = BusinessCardService(config)
    candidate_id = str(service.child_review_queue(run_id=run_dir.name)[0]["candidate_id"])
    service.submit_child_review(
        run_id=run_dir.name,
        candidate_id=candidate_id,
        reviewer="operator",
        action="approve_child_for_routing",
    )
    service.prepare_child_route(run_id=run_dir.name, candidate_id=candidate_id)
    client = TestClient(create_app(config_path))

    lookup = client.post(
        f"/reviews/children/{candidate_id}/sink-lookup-result",
        json={
            "run_id": run_dir.name,
            "matches_by_sink": {
                "google_contacts": [
                    {"resource_id": "people/api-child", "confidence": 0.9, "basis": ["email"]}
                ]
            },
        },
    ).json()
    assessment = client.post(
        f"/reviews/children/{candidate_id}/downstream-duplicate-assessment",
        json={"run_id": run_dir.name},
    ).json()

    assert lookup["result"]["match_count"] == 1
    assert lookup["writes_attempted"] == 0
    assert lookup["network_calls_made"] == 0
    assert assessment["assessment"]["state"] == "strong_duplicate"
    assert assessment["writes_attempted"] == 0
    assert assessment["network_calls_made"] == 0


def test_api_child_duplicate_resolution_clears_gate(tmp_path: Path, monkeypatch) -> None:
    pytest.importorskip("cv2")
    from business_card_watchdog.api import create_app

    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    write_config(config_path, data_dir)
    source_dir = tmp_path / "images"
    write_multi_card_image(source_dir / "multi.jpg")
    config = AppConfig(
        config_path=config_path,
        data_dir=data_dir,
        sink=SinkConfig(google_contacts=True, dry_run=True),
    )
    orchestrator = BatchOrchestrator(config)
    monkeypatch.setattr(orchestrator, "adapter", SyntheticSkillAdapter())
    run_dir = orchestrator.process_source(str(source_dir), dry_run=True, workers=1)
    service = BusinessCardService(config)
    candidate_id = str(service.child_review_queue(run_id=run_dir.name)[0]["candidate_id"])
    service.submit_child_review(
        run_id=run_dir.name,
        candidate_id=candidate_id,
        reviewer="operator",
        action="approve_child_for_routing",
    )
    service.prepare_child_route(run_id=run_dir.name, candidate_id=candidate_id)
    service.record_child_sink_lookup_result(
        run_id=run_dir.name,
        candidate_id=candidate_id,
        matches_by_sink={"google_contacts": [{"resource_id": "people/api-existing", "basis": ["email"]}]},
    )
    service.assess_child_downstream_duplicates(run_id=run_dir.name, candidate_id=candidate_id)
    client = TestClient(create_app(config_path))

    resolution = client.post(
        f"/reviews/children/{candidate_id}/duplicate-resolution",
        json={
            "run_id": run_dir.name,
            "reviewer": "operator",
            "decision": "create_new",
            "reason": "separate person",
        },
    ).json()
    gate = client.post(
        f"/reviews/children/{candidate_id}/sink-plan-gate",
        json={"run_id": run_dir.name},
    ).json()

    assert resolution["resolution"]["decision"] == "create_new"
    assert resolution["writes_attempted"] == 0
    assert resolution["network_calls_made"] == 0
    assert gate["gate"]["state"] == "ready_for_sink_plan"
    assert gate["gate"]["sink_write_allowed"] is False


def test_api_child_sink_apply_preflight_and_handoff(tmp_path: Path, monkeypatch) -> None:
    pytest.importorskip("cv2")
    from business_card_watchdog.api import create_app

    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    write_config(config_path, data_dir)
    source_dir = tmp_path / "images"
    write_multi_card_image(source_dir / "multi.jpg")
    config = AppConfig(
        config_path=config_path,
        data_dir=data_dir,
        sink=SinkConfig(google_contacts=True, dry_run=True),
    )
    orchestrator = BatchOrchestrator(config)
    monkeypatch.setattr(orchestrator, "adapter", SyntheticSkillAdapter())
    run_dir = orchestrator.process_source(str(source_dir), dry_run=True, workers=1)
    service = BusinessCardService(config)
    candidate_id = str(service.child_review_queue(run_id=run_dir.name)[0]["candidate_id"])
    service.submit_child_review(
        run_id=run_dir.name,
        candidate_id=candidate_id,
        reviewer="operator",
        action="approve_child_for_routing",
    )
    service.prepare_child_route(run_id=run_dir.name, candidate_id=candidate_id)
    service.record_child_sink_lookup_result(run_id=run_dir.name, candidate_id=candidate_id)
    service.assess_child_downstream_duplicates(run_id=run_dir.name, candidate_id=candidate_id)
    service.child_sink_plan_gate(run_id=run_dir.name, candidate_id=candidate_id)
    client = TestClient(create_app(config_path))

    preflight = client.post(
        f"/reviews/children/{candidate_id}/sink-apply-preflight",
        json={"run_id": run_dir.name},
    ).json()
    handoff = client.post(
        f"/reviews/children/{candidate_id}/selected-target-handoff",
        json={"run_id": run_dir.name, "sink": "google_contacts", "operator": "operator"},
    ).json()

    assert preflight["preflight"]["state"] == "preview"
    assert preflight["preflight"]["sink_write_allowed"] is False
    assert handoff["handoff"]["state"] == "ready_for_operator_selection"
    assert handoff["handoff"]["selected_target_created"] is False
    assert handoff["writes_attempted"] == 0
    assert handoff["network_calls_made"] == 0


def test_api_child_selected_target_response_validation_and_checklist(tmp_path: Path, monkeypatch) -> None:
    pytest.importorskip("cv2")
    from business_card_watchdog.api import create_app

    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    write_config(config_path, data_dir)
    source_dir = tmp_path / "images"
    write_multi_card_image(source_dir / "multi.jpg")
    config = AppConfig(
        config_path=config_path,
        data_dir=data_dir,
        sink=SinkConfig(google_contacts=True, dry_run=True),
    )
    orchestrator = BatchOrchestrator(config)
    monkeypatch.setattr(orchestrator, "adapter", SyntheticSkillAdapter())
    run_dir = orchestrator.process_source(str(source_dir), dry_run=True, workers=1)
    service = BusinessCardService(config)
    candidate_id = str(service.child_review_queue(run_id=run_dir.name)[0]["candidate_id"])
    service.submit_child_review(
        run_id=run_dir.name,
        candidate_id=candidate_id,
        reviewer="operator",
        action="approve_child_for_routing",
    )
    service.prepare_child_route(run_id=run_dir.name, candidate_id=candidate_id)
    service.record_child_sink_lookup_result(run_id=run_dir.name, candidate_id=candidate_id)
    service.assess_child_downstream_duplicates(run_id=run_dir.name, candidate_id=candidate_id)
    service.child_sink_plan_gate(run_id=run_dir.name, candidate_id=candidate_id)
    handoff = service.child_selected_target_handoff(
        run_id=run_dir.name,
        candidate_id=candidate_id,
        sink="google_contacts",
        operator="operator",
    )["handoff"]
    template = handoff["operator_response_template"]
    response = (
        f"run_id={template['run_id']} job_id={template['job_id']} "
        f"candidate_id={template['candidate_id']} work_item_id={template['work_item_id']} "
        "sink=google_contacts operator=operator scope=write "
        "safety_confirmation='approved google contacts target profile'"
    )
    client = TestClient(create_app(config_path))

    validation = client.post(
        f"/reviews/children/{candidate_id}/selected-target-response-validation",
        json={"run_id": run_dir.name, "response": response},
    ).json()
    checklist = client.post(
        f"/reviews/children/{candidate_id}/selected-target-execution-checklist",
        json={"run_id": run_dir.name, "response": response},
    ).json()
    command_copy = client.post(
        f"/reviews/children/{candidate_id}/selected-target-command-copy-packet",
        json={
            "run_id": run_dir.name,
            "response": response,
            "acknowledgement": (
                f"I acknowledge run_id={run_dir.name} candidate_id={candidate_id} "
                "sink=google_contacts operator=operator ready to copy"
            ),
        },
    ).json()
    audit = client.post(
        f"/reviews/children/{candidate_id}/selected-target-audit",
        json={"run_id": run_dir.name},
    ).json()
    abandonment = client.post(
        f"/reviews/children/{candidate_id}/selected-target-abandonment",
        json={"run_id": run_dir.name, "operator": "operator", "reason": "replace child target"},
    ).json()
    reset = client.post(
        f"/reviews/children/{candidate_id}/selected-target-replacement-reset",
        json={
            "run_id": run_dir.name,
            "sink": "google_contacts",
            "operator": "replacement-operator",
            "scope": "write",
        },
    ).json()
    refresh = client.post(
        f"/reviews/children/{candidate_id}/replacement-handoff-refresh",
        json={
            "run_id": run_dir.name,
            "sink": "google_contacts",
            "operator": "replacement-operator",
            "scope": "write",
        },
    ).json()
    replacement_template = refresh["refreshed_handoff"]["operator_response_template"]
    replacement_response = (
        f"run_id={replacement_template['run_id']} job_id={replacement_template['job_id']} "
        f"candidate_id={replacement_template['candidate_id']} "
        f"work_item_id={replacement_template['work_item_id']} "
        "sink=google_contacts operator=replacement-operator scope=write "
        "safety_confirmation='approved replacement google contacts target profile'"
    )
    replacement_validation = client.post(
        f"/reviews/children/{candidate_id}/replacement-response-validation",
        json={"run_id": run_dir.name, "response": replacement_response},
    ).json()
    replacement_checklist = client.post(
        f"/reviews/children/{candidate_id}/replacement-execution-checklist",
        json={"run_id": run_dir.name, "response": replacement_response},
    ).json()
    replacement_command_copy = client.post(
        f"/reviews/children/{candidate_id}/replacement-command-copy-packet",
        json={
            "run_id": run_dir.name,
            "response": replacement_response,
            "acknowledgement": (
                f"I acknowledge run_id={run_dir.name} candidate_id={candidate_id} "
                "sink=google_contacts operator=replacement-operator ready to copy"
            ),
        },
    ).json()
    closeout = client.post(
        f"/reviews/children/{candidate_id}/replacement-closeout-status",
        json={"run_id": run_dir.name},
    ).json()
    review_bundle = client.post(f"/runs/{run_dir.name}/review-bundle").json()
    operator_dashboard = client.get("/operator/dashboard", params={"run_id": run_dir.name}).json()

    assert validation["schema"] == "business-card-watchdog.child-selected-target-response-validation.v1"
    assert validation["state"] == "ready_for_no_live_child_checklist"
    assert validation["writes_attempted"] == 0
    assert validation["network_calls_made"] == 0
    assert checklist["schema"] == "business-card-watchdog.child-selected-target-execution-checklist.v1"
    assert checklist["state"] == "ready_for_operator_review"
    assert checklist["selected_target_created"] is False
    assert checklist["executable_live_command"] is None
    assert checklist["writes_attempted"] == 0
    assert checklist["network_calls_made"] == 0
    assert command_copy["schema"] == "business-card-watchdog.child-selected-target-command-copy-packet.v1"
    assert command_copy["state"] == "ready_for_operator_copy"
    assert command_copy["acknowledgement_ok"] is True
    assert command_copy["command_copy_text"].startswith("reviews child-selected-target-execution-checklist")
    assert command_copy["executable_live_command"] is None
    assert command_copy["writes_attempted"] == 0
    assert command_copy["network_calls_made"] == 0
    assert audit["schema"] == "business-card-watchdog.child-selected-target-audit.v1"
    assert audit["state"] == "ready"
    assert audit["selected_target_exists"] is True
    assert audit["replacement_requires_abandonment"] is False
    assert audit["writes_attempted"] == 0
    assert audit["network_calls_made"] == 0
    assert abandonment["schema"] == "business-card-watchdog.child-selected-target-abandonment.v1"
    assert abandonment["state"] == "abandoned"
    assert abandonment["writes_attempted"] == 0
    assert abandonment["network_calls_made"] == 0
    assert reset["schema"] == "business-card-watchdog.child-selected-target-replacement-reset.v1"
    assert reset["state"] == "ready_for_replacement_preview"
    assert reset["replacement_unblocked"] is True
    assert reset["replacement_requires_abandonment"] is False
    assert reset["writes_attempted"] == 0
    assert reset["network_calls_made"] == 0
    assert refresh["schema"] == "business-card-watchdog.child-replacement-handoff-refresh.v1"
    assert refresh["state"] == "ready_for_replacement_handoff"
    assert refresh["refreshed_handoff"]["operator"] == "replacement-operator"
    assert refresh["staleness"]["state"] == "stale"
    assert refresh["writes_attempted"] == 0
    assert refresh["network_calls_made"] == 0
    assert replacement_validation["schema"] == "business-card-watchdog.child-replacement-response-validation.v1"
    assert replacement_validation["state"] == "ready_for_no_live_replacement_checklist"
    assert replacement_validation["stale_enforcement"]["staleness_state"] == "stale"
    assert replacement_validation["parsed_response"]["operator"] == "replacement-operator"
    assert replacement_validation["selected_target_created"] is False
    assert replacement_validation["writes_attempted"] == 0
    assert replacement_validation["network_calls_made"] == 0
    assert replacement_checklist["schema"] == "business-card-watchdog.child-replacement-execution-checklist.v1"
    assert replacement_checklist["state"] == "ready_for_replacement_operator_review"
    assert replacement_checklist["executable_live_command"] is None
    assert replacement_checklist["writes_attempted"] == 0
    assert replacement_checklist["network_calls_made"] == 0
    assert replacement_command_copy["schema"] == "business-card-watchdog.child-replacement-command-copy-packet.v1"
    assert replacement_command_copy["state"] == "ready_for_replacement_operator_copy"
    assert replacement_command_copy["command_copy_text"].startswith("reviews child-replacement-execution-checklist")
    assert replacement_command_copy["executable_live_command"] is None
    assert replacement_command_copy["writes_attempted"] == 0
    assert replacement_command_copy["network_calls_made"] == 0
    assert closeout["schema"] == "business-card-watchdog.child-replacement-closeout-status.v1"
    assert closeout["state"] == "ready_for_operator_closeout"
    assert closeout["rollup"]["predecessor_artifacts_stale"] is True
    assert closeout["rollup"]["replacement_copy_ready"] is True
    assert closeout["rollup"]["executable_live_command"] is None
    assert closeout["writes_attempted"] == 0
    assert closeout["network_calls_made"] == 0
    bundle_entry = next(entry for entry in review_bundle["entries"] if entry["job_id"] == closeout["job_id"])
    assert bundle_entry["child_replacement_status"]["state"] == "ready_for_operator_closeout"
    assert review_bundle["groups"]["by_child_replacement_state"]["ready_for_operator_closeout"]["count"] == 1
    assert operator_dashboard["child_replacement_summary"]["closeout_count"] == 1
    assert operator_dashboard["child_replacement_summary"]["ready_count"] == 1


def test_api_multi_card_preclassification_drill_records_candidate_boxes(tmp_path: Path) -> None:
    pytest.importorskip("cv2")
    from business_card_watchdog.api import create_app

    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    write_config(config_path, data_dir)
    client = TestClient(create_app(config_path))

    drill = client.post("/drills/multi-card-preclassification").json()

    assert drill["schema"] == "business-card-watchdog.multi-card-preclassification-drill.v1"
    assert drill["state"] == "passed"
    assert drill["expected_card_count"] == 3
    assert drill["detected_card_like_count"] >= 3
    assert len(drill["candidate_boxes"]) >= 3
    assert drill["preclassification"]["decision"] == "likely_business_card"
    assert drill["private_sources_used"] is False
    assert drill["live_sink_calls_made"] is False
    assert drill["writes_attempted"] == 0
    assert drill["network_calls_made"] == 0
    assert Path(drill["drill_path"]).exists()


def test_api_watch_dry_run_selection_drill_exports_sample_output(tmp_path: Path) -> None:
    from business_card_watchdog.api import create_app

    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    write_config(config_path, data_dir)
    client = TestClient(create_app(config_path))

    drill = client.post("/drills/watch-dry-run-selection").json()

    assert drill["schema"] == "business-card-watchdog.watch-dry-run-selection-drill.v1"
    assert drill["state"] == "passed"
    assert drill["command_copy_ready"] is True
    assert drill["files_processed"] == 0
    assert drill["ocr_attempted"] == 0
    assert drill["network_calls_made"] == 0
    sample_output_path = Path(drill["sample_outputs"]["watch_dry_run_selection_markdown_path"])
    assert sample_output_path.exists()
    assert "Command copy packet: `ready_for_operator_copy`" in sample_output_path.read_text(encoding="utf-8")


def test_api_watch_dry_run_execution_drill_runs_real_dry_pipeline(tmp_path: Path) -> None:
    from business_card_watchdog.api import create_app

    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    write_config(config_path, data_dir)
    client = TestClient(create_app(config_path))

    drill = client.post("/drills/watch-dry-run-execution").json()

    assert drill["schema"] == "business-card-watchdog.watch-dry-run-execution-drill.v1"
    assert drill["state"] == "passed"
    assert drill["files_processed"] == 1
    assert drill["ocr_attempted"] == 1
    assert drill["network_calls_made"] == 0
    assert drill["processed_run"]["state"] == "completed"
    assert "contact_candidate" in drill["processed_run"]["artifact_kinds"]
    sample_output_path = Path(drill["sample_outputs"]["watch_dry_run_execution_markdown_path"])
    assert sample_output_path.exists()


def test_api_live_pilot_rehearsal_drill_reaches_command_copy_gate(tmp_path: Path) -> None:
    from business_card_watchdog.api import create_app

    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    write_config(config_path, data_dir)
    client = TestClient(create_app(config_path))

    drill = client.post("/drills/live-pilot-rehearsal").json()

    assert drill["schema"] == "business-card-watchdog.live-pilot-rehearsal-drill.v1"
    assert drill["state"] == "passed"
    assert drill["private_sources_used"] is False
    assert drill["public_web_search_used"] is False
    assert drill["paid_enrichment_used"] is False
    assert drill["live_sink_calls_made"] is False
    assert drill["command_copy_ready"] is True
    assert drill["packets"]["command_copy_packet"]["state"] == "ready_for_operator_copy"
    assert drill["writes_attempted"] == 0
    assert drill["network_calls_made"] == 0
    sample_output_path = Path(drill["sample_outputs"]["live_pilot_rehearsal_markdown_path"])
    preflight_sample_output_path = Path(
        drill["sample_outputs"]["operator_selected_live_smoke_preflight_markdown_path"]
    )
    assert sample_output_path.exists()
    assert preflight_sample_output_path.exists()
    assert "Command copy packet: `ready_for_operator_copy`" in sample_output_path.read_text(encoding="utf-8")
    assert drill["packets"]["operator_selected_preflight"]["schema"] == (
        "business-card-watchdog.operator-selected-live-smoke-preflight.v1"
    )
    assert f"State: `{drill['packets']['operator_selected_preflight']['state']}`" in (
        preflight_sample_output_path.read_text(encoding="utf-8")
    )
    assert Path(drill["drill_path"]).exists()


def test_api_child_replacement_readiness_drill_exports_operator_samples(tmp_path: Path) -> None:
    from business_card_watchdog.api import create_app

    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    write_config(config_path, data_dir)
    client = TestClient(create_app(config_path))

    drill = client.post("/drills/child-replacement-readiness").json()

    assert drill["schema"] == "business-card-watchdog.child-replacement-readiness-drill.v1"
    assert drill["state"] == "passed"
    assert drill["private_sources_used"] is False
    assert drill["public_web_search_used"] is False
    assert drill["paid_enrichment_used"] is False
    assert drill["live_sink_calls_made"] is False
    assert drill["readiness_states"]["closeout"] == "ready_for_operator_closeout"
    assert drill["review_bundle_child_replacement_groups"]["ready_for_operator_closeout"]["count"] == 1
    assert drill["operator_dashboard_child_replacement_summary"]["ready_count"] == 1
    assert drill["writes_attempted"] == 0
    assert drill["network_calls_made"] == 0
    sample_output_path = Path(drill["sample_outputs"]["child_replacement_readiness_markdown_path"])
    assert sample_output_path.exists()
    assert "Closeout Rollup" in sample_output_path.read_text(encoding="utf-8")
    assert Path(drill["sample_outputs"]["review_workbook_path"]).exists()
    assert Path(drill["drill_path"]).exists()


def test_api_sink_readback_pilot_writes_zero_write_artifact(tmp_path: Path) -> None:
    from business_card_watchdog.api import create_app

    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    config_path.write_text(
        f'data_dir = "{data_dir}"\n'
        "[watch]\ninputs = []\n"
        "[sink]\ndry_run = true\ngoogle_contacts = true\n"
        "[routing]\nrules = [{ match = \"email_domain\", value = \"*\", sinks = [\"google_contacts\"] }]\n",
        encoding="utf-8",
    )
    run_id, job_id = make_recorded_run(
        AppConfig(
            config_path=config_path,
            data_dir=data_dir,
            sink=SinkConfig(google_contacts=True, dry_run=True),
            routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
        )
    )
    client = TestClient(create_app(config_path))

    client.post(
        f"/runs/{run_id}/review-decisions",
        json={
            "reviewer": "api-batch",
            "decisions": [
                {
                    "job_id": job_id,
                    "action": "approve_for_routing",
                    "field_corrections": {"full_name": "API Batch", "email": "api@example.test"},
                }
            ],
        },
    )
    client.post(f"/jobs/{job_id}/sink-plan", params={"run_id": run_id})
    client.post(f"/jobs/{job_id}/sink-apply-preflight", json={"run_id": run_id})
    client.post(
        f"/jobs/{job_id}/sink-apply-decision",
        json={"run_id": run_id, "decision": "approve", "reviewer": "api-test"},
    )
    readiness = client.post(
        f"/jobs/{job_id}/sink-apply-pilot-readiness",
        json={"run_id": run_id, "sink": "google_contacts"},
    ).json()
    assert readiness["readiness"]["selected_sink"] == "google_contacts"
    bundle = client.post(
        f"/jobs/{job_id}/sink-apply-pilot-bundle",
        json={"run_id": run_id, "sink": "google_contacts", "operator": "api-test"},
    ).json()
    assert bundle["bundle"]["schema"] == "business-card-watchdog.sink-apply-pilot-bundle.v1"
    assert bundle["bundle"]["sink"] == "google_contacts"
    assert bundle["bundle"]["writes_attempted"] == 0
    selected_target = client.post(
        f"/jobs/{job_id}/selected-live-target",
        json={
            "run_id": run_id,
            "sink": "google_contacts",
            "operator": "api-test",
            "scope": "all",
            "safety_confirmation": "fixture contact is safe for google contacts test profile",
        },
    ).json()
    assert selected_target["target"]["schema"] == "business-card-watchdog.selected-live-target.v1"
    assert selected_target["target"]["operator"] == "api-test"
    assert selected_target["target"]["scope_allows"]["readback"] is True
    write_pilot = client.post(
        f"/jobs/{job_id}/sink-write-pilot",
        json={"run_id": run_id, "sink": "google_contacts", "approved_by": "api-test"},
    ).json()
    assert write_pilot["pilot"]["schema"] == "business-card-watchdog.sink-write-pilot.v1"
    assert write_pilot["pilot"]["writes_attempted"] == 0
    assert write_pilot["result"]["state"] == "mock_applied"
    client.post(f"/jobs/{job_id}/sink-adapter-request", json={"run_id": run_id, "phase": "readback"})
    readback_pilot = client.post(
        f"/jobs/{job_id}/sink-readback-pilot",
        json={"run_id": run_id, "sink": "google_contacts", "approved_by": "api-test"},
    ).json()

    assert readback_pilot["pilot"]["schema"] == "business-card-watchdog.sink-readback-pilot.v1"
    assert readback_pilot["pilot"]["state"] == "verified"
    assert readback_pilot["pilot"]["writes_attempted"] == 0
    assert readback_pilot["pilot"]["network_calls_made"] == 0
    report = client.post(f"/jobs/{job_id}/sink-apply-pilot-report", json={"run_id": run_id}).json()
    assert report["report"]["schema"] == "business-card-watchdog.sink-apply-pilot-report.v1"
    assert report["report"]["state"] == "complete"
    assert report["report"]["writes_attempted"] == 0


def test_api_enrichment_request_accepts_paid_provider_results(tmp_path: Path) -> None:
    from business_card_watchdog.api import create_app

    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    keys_path = tmp_path / "API-keys.env"
    keys_path.write_text("APOLLO_API_KEY=fixture-value-redacted\n", encoding="utf-8")
    config_path.write_text(
        f'data_dir = "{data_dir}"\n'
        "[watch]\ninputs = []\n"
        "[enrichment]\nenabled = true\nallow_paid_api = true\n"
        f'api_keys_env = "{keys_path}"\n'
        "[enrichment.providers.apollo]\nenabled = true\napi_key_env = \"APOLLO_API_KEY\"\n",
        encoding="utf-8",
    )
    config = AppConfig(
        config_path=config_path,
        data_dir=data_dir,
        enrichment=EnrichmentConfig(
            enabled=True,
            allow_paid_api=True,
            api_keys_env=keys_path,
            apollo=EnrichmentProviderConfig(enabled=True),
        ),
    )
    run_id, job_id = make_recorded_run(config)
    artifact_dir = data_dir / "runs" / run_id / "artifacts" / job_id
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
    client = TestClient(create_app(config_path))

    payload = client.post(
        f"/jobs/{job_id}/enrichment",
        json={
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
    ).json()

    assert payload["status"] == "ok"
    assert payload["provider_result"]["schema"] == "business-card-watchdog.enrichment-provider-result.v1"
    assert payload["provider_result"]["network_calls_made"] == 0
    handoff = client.post(
        f"/jobs/{job_id}/enrichment/provider-handoff",
        json={"run_id": run_id},
    ).json()
    assert handoff["handoff"]["schema"] == "business-card-watchdog.enrichment-provider-handoff.v1"
    assert handoff["handoff"]["paid_api_calls_attempted"] == 0
    assert "secret" not in json.dumps(handoff)

    result = client.post(
        f"/jobs/{job_id}/enrichment/provider-results",
        json={
            "run_id": run_id,
            "provider": "apollo",
            "submitted_by": "api-agent",
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
    ).json()
    assert result["provider_result"]["schema"] == "business-card-watchdog.enrichment-provider-result.v1"
    assert result["provider_result"]["submitted_by"] == "api-agent"
    assert result["provider_result"]["paid_api_calls_attempted"] == 0
    assert client.post("/sinks/check").json()["dry_run"] is True
    assert client.get("/watch/status").json()["seen_count"] == 0
    source = tmp_path / "Private Phone Camera"
    write_synthetic_image(source / "private-card-photo.png")
    config_path.write_text(
        f'data_dir = "{data_dir}"\n[watch]\ninputs = ["{source}"]\nsettle_seconds = 0.0\n',
        encoding="utf-8",
    )
    watch_preflight = client.post("/watch/backlog-preflight", json={"write": False}).json()
    serialized_preflight = json.dumps(watch_preflight, sort_keys=True)
    assert watch_preflight["schema"] == "business-card-watchdog.watch-backlog-preflight.v1"
    assert watch_preflight["counts"]["backlog"] == 1
    assert watch_preflight["runtime_artifact_written"] is False
    assert str(source) not in serialized_preflight
    assert "private-card-photo.png" not in serialized_preflight
    response = (
        "input_ref=input_0 operator=api-test mode=dry_run "
        "safety_confirmation='private dry run approved for this configured source'"
    )
    watch_handoff = client.post("/watch/dry-run-selection-handoff", json={"write": False}).json()
    assert watch_handoff["schema"] == "business-card-watchdog.watch-dry-run-selection-handoff.v1"
    assert watch_handoff["state"] == "awaiting_operator_response"
    watch_validation = client.post("/watch/dry-run-validate-response", json={"response": response}).json()
    assert watch_validation["state"] == "ready_for_command_copy"
    watch_command_copy = client.post(
        "/watch/dry-run-command-copy-packet",
        json={
            "response": response,
            "acknowledgement": "I understand this will dry-run the configured private watch backlog",
        },
    ).json()
    assert watch_command_copy["state"] == "ready_for_operator_copy"
    assert watch_command_copy["command_copy_text"] == "watch --once --dry-run"
    assert watch_command_copy["files_processed"] == 0
    watch_readiness = client.post("/watch/dry-run-readiness", json={"write": False}).json()
    serialized_readiness = json.dumps(watch_readiness, sort_keys=True)
    assert watch_readiness["schema"] == "business-card-watchdog.watch-dry-run-readiness.v1"
    assert watch_readiness["state"] == "ready_for_operator_response"
    assert watch_readiness["command_copy_text"] is None
    assert watch_readiness["runtime_artifact_written"] is False
    assert str(source) not in serialized_readiness
    assert "private-card-photo.png" not in serialized_readiness
    watch_dry_run = client.post("/watch/dry-run").json()
    assert watch_dry_run["schema"] == "business-card-watchdog.watch-dry-run-harness.v1"
    assert watch_dry_run["state"] == "passed"
    assert watch_dry_run["private_sources_used"] is False
    assert watch_dry_run["commands"]["watch_status"] == "watch-status --json"
    assert watch_dry_run["safe_next_actions"][0]["action"] == "inspect_watch_harness"
    assert "Do not process private SyncThing images" in watch_dry_run["explicit_stop_conditions"][0]


def test_api_executes_sink_lookup_pilot_with_mocked_matches(tmp_path: Path, monkeypatch) -> None:
    from business_card_watchdog.api import create_app
    import business_card_watchdog.service as service_module

    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    config_path.write_text(
        f'data_dir = "{data_dir}"\n'
        "[watch]\ninputs = []\n"
        "[sink]\ndry_run = true\ngoogle_contacts = true\n",
        encoding="utf-8",
    )
    config = AppConfig(
        config_path=config_path,
        data_dir=data_dir,
        sink=SinkConfig(google_contacts=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    client = TestClient(create_app(config_path))
    client.post(f"/jobs/{job_id}/sink-lookup-plan", params={"run_id": run_id})
    client.post(f"/jobs/{job_id}/sink-adapter-request", json={"run_id": run_id, "phase": "lookup"})
    handoff = client.post(
        f"/jobs/{job_id}/sink-lookup-smoke-handoff",
        json={"run_id": run_id, "sink": "google_contacts", "approved_by": "api-operator"},
    ).json()
    assert handoff["handoff"]["schema"] == "business-card-watchdog.sink-lookup-smoke-handoff.v1"
    assert handoff["handoff"]["writes_attempted"] == 0
    assert handoff["handoff"]["network_calls_made"] == 0

    payload = client.post(
        f"/jobs/{job_id}/sink-lookup-pilot",
        json={
            "run_id": run_id,
            "sink": "google_contacts",
            "approved_by": "api-operator",
            "matches": [
                {"resource_id": "people/c456", "confidence": 0.93, "basis": ["email"]}
            ],
        },
    ).json()

    assert payload["pilot"]["schema"] == "business-card-watchdog.sink-lookup-pilot.v1"
    assert payload["pilot"]["approved_by"] == "api-operator"
    assert payload["pilot"]["network_calls_made"] == 0
    assert payload["pilot"]["writes_attempted"] == 0
    assert payload["result"]["state"] == "possible_duplicate"

    def execute_lookup(request: dict[str, object]) -> dict[str, object]:
        return {
            "status": "read_only_lookup_completed",
            "network_calls_made": 1,
            "writes_attempted": 0,
            "matches": [{"resource_id": "people/api-smoke", "confidence": 0.9, "basis": ["email"], "raw": {"x": 1}}],
            "raw": {"results": [{"person": {"names": [{"displayName": "API Smoke"}]}}]},
        }

    monkeypatch.setattr(service_module, "execute_sink_lookup_adapter", execute_lookup)
    selected = client.post(
        f"/jobs/{job_id}/selected-live-target",
        json={
            "run_id": run_id,
            "sink": "google_contacts",
            "operator": "api-operator",
            "scope": "lookup",
            "safety_confirmation": "fixture contact is safe for google contacts test profile",
        },
    ).json()
    smoke = client.post(f"/jobs/{job_id}/selected-lookup-smoke", json={"run_id": run_id}).json()
    assert selected["target"]["schema"] == "business-card-watchdog.selected-live-target.v1"
    assert smoke["smoke"]["schema"] == "business-card-watchdog.selected-lookup-smoke.v1"
    assert smoke["smoke"]["writes_attempted"] == 0
    assert smoke["smoke"]["network_calls_made"] == 1
    assert smoke["smoke"]["downstream_duplicate_state"] == "strong_duplicate"


def test_api_records_public_web_enrichment_results(tmp_path: Path) -> None:
    from business_card_watchdog.api import create_app

    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    config_path.write_text(
        f'data_dir = "{data_dir}"\n'
        "[watch]\ninputs = []\n"
        "[enrichment]\nenabled = true\n",
        encoding="utf-8",
    )
    config = AppConfig(
        config_path=config_path,
        data_dir=data_dir,
        enrichment=EnrichmentConfig(enabled=True),
    )
    run_id, job_id = make_recorded_run(config)
    artifact_dir = data_dir / "runs" / run_id / "artifacts" / job_id
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
    client = TestClient(create_app(config_path))
    request = client.post(
        f"/jobs/{job_id}/enrichment",
        json={"run_id": run_id, "mode": "public_web", "requested_by": "api-test"},
    ).json()
    assert request["public_web_request"]["schema"] == "business-card-watchdog.enrichment-public-web-request.v1"

    handoff = client.post(
        f"/jobs/{job_id}/enrichment/public-web-handoff",
        json={"run_id": run_id},
    ).json()
    assert handoff["handoff"]["schema"] == "business-card-watchdog.enrichment-public-web-search-handoff.v1"
    assert handoff["handoff"]["network_calls_made"] == 0
    assert handoff["handoff"]["result_import"]["api"] == f"POST /jobs/{job_id}/enrichment/public-web-results"

    payload = client.post(
        f"/jobs/{job_id}/enrichment/public-web-results",
        json={
            "run_id": run_id,
            "searched_by": "api-search",
            "results": [
                {
                    "title": "Ada Lovelace - Example Labs",
                    "url": "https://example.test/team/ada",
                    "snippet": "Contact Ada at ada@example.test",
                }
            ],
        },
    ).json()

    assert payload["public_web_result"]["schema"] == "business-card-watchdog.enrichment-public-web-result.v1"
    assert payload["public_web_result"]["searched_by"] == "api-search"
    assert payload["public_web_result"]["network_calls_made"] == 0
    assert payload["result"]["schema"] == "business-card-watchdog.enrichment-result.v1"
