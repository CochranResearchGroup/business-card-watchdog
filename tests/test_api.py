from __future__ import annotations

import csv
import json
from io import StringIO
from pathlib import Path

import pytest

from business_card_watchdog.config import AppConfig, EnrichmentConfig, EnrichmentProviderConfig, SinkConfig
from business_card_watchdog.contact import build_contact_candidate

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
    assert operator_dashboard["review_counts"]["needs_review"] == 1
    assert operator_dashboard["next_action_summary"]["by_action"] == {"review_contact": 1}
    assert operator_dashboard["commands"]["next_actions"] == f"actions next --run-id {run_id} --json"
    assert operator_dashboard["api_routes"]["next_actions"] == f"GET /actions/next?run_id={run_id}&limit=20"
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
    assert service_recovery["commands"]["live_pilot_handoff"].endswith(f"runs live-pilot-handoff {run_id}")
    assert service_recovery["network_calls_made"] == 0
    assert service_recovery["writes_attempted"] == 0
    live_targets = client.get("/live-target-candidates", params={"run_id": run_id}).json()
    assert live_targets["schema"] == "business-card-watchdog.live-target-candidates.v1"
    assert live_targets["network_calls_made"] == 0
    assert live_targets["writes_attempted"] == 0
    assert live_targets["commands"]["live_pilot_handoff"] == f"runs live-pilot-handoff {run_id}"
    live_audit = client.post("/live-readiness-audit", json={"run_id": run_id, "write": False}).json()
    assert live_audit["schema"] == "business-card-watchdog.live-readiness-audit.v1"
    assert live_audit["run_id"] == run_id
    assert live_audit["network_calls_made"] == 0
    assert live_audit["writes_attempted"] == 0
    assert live_audit["commands"]["live_pilot_handoff"] == f"runs live-pilot-handoff {run_id}"
    live_requirements = client.post("/live-selection-requirements", json={"run_id": run_id, "write": False}).json()
    assert live_requirements["schema"] == "business-card-watchdog.live-selection-requirements.v1"
    assert live_requirements["run_id"] == run_id
    assert live_requirements["entry_count"] == 0
    assert live_requirements["network_calls_made"] == 0
    assert live_requirements["writes_attempted"] == 0
    assert live_requirements["commands"]["live_pilot_handoff"] == f"runs live-pilot-handoff {run_id}"
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
    assert live_status["entries"][0]["selected_target_identity"] == selected["target"]["selection_id"]
    assert live_status["entries"][0]["abandonment_identity"] is None
    assert live_status["operator_response_contract"]["creates_selected_live_target"] is False
    assert live_status["entries"][0]["operator_response_template"] == (
        f"run_id={run_id} job_id={job_id} sink=google_contacts "
        "operator=api-test scope=lookup safety_confirmation=<confirmation>"
    )
    live_handoff = client.get(f"/runs/{run_id}/live-pilot-handoff", params={"write": False}).json()
    assert live_handoff["schema"] == "business-card-watchdog.live-pilot-handoff.v1"
    assert live_handoff["action_counts"]["request_live_lookup_smoke"] == 1
    assert live_handoff["writes_attempted"] == 0
    assert live_handoff["entries"][0]["selected_target_identity"] == selected["target"]["selection_id"]
    assert live_handoff["entries"][0]["abandonment_identity"] is None
    assert live_handoff["operator_response_contract"]["creates_selected_live_target"] is False
    assert live_handoff["entries"][0]["operator_response_template"] == (
        f"run_id={run_id} job_id={job_id} sink=google_contacts "
        "operator=api-test scope=lookup safety_confirmation=<confirmation>"
    )
    assert live_handoff["entries"][0]["copyable_approval_fields"]["operator"] == "api-test"
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
    assert run_next["phase_report_before"]["schema"] == "business-card-watchdog.phase-report.v1"
    assert run_next["phase_report_after"]["schema"] == "business-card-watchdog.phase-report.v1"


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
    watch_dry_run = client.post("/watch/dry-run").json()
    assert watch_dry_run["schema"] == "business-card-watchdog.watch-dry-run-harness.v1"
    assert watch_dry_run["state"] == "passed"
    assert watch_dry_run["private_sources_used"] is False


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
