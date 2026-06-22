from __future__ import annotations

import csv
import json
from io import StringIO
from pathlib import Path

from business_card_watchdog.config import (
    AppConfig,
    EnrichmentConfig,
    EnrichmentProviderConfig,
    PrefilterConfig,
    SinkConfig,
    WatchConfig,
)
from business_card_watchdog.contact import build_contact_candidate
from business_card_watchdog.ledger import RunLedger
from business_card_watchdog.models import CardJob
from business_card_watchdog.orchestrator import BatchOrchestrator
from business_card_watchdog.service import BusinessCardService
from synthetic_fixtures import SyntheticSkillAdapter, write_synthetic_image


def make_recorded_run(config: AppConfig, run_id: str = "run-001") -> tuple[str, str]:
    ledger = RunLedger(config.runs_dir / run_id)
    ledger.initialize(source="/tmp/cards", dry_run=True)
    ledger.transition_run("discovering")
    ledger.transition_run("processing")
    job = CardJob(image_path="/tmp/cards/card.png", job_id="job-001")
    ledger.set_job_count(1)
    ledger.record_job(job)
    job.transition_to("processing")
    ledger.record_job(job)
    artifact_path = ledger.run_dir / "artifacts" / job.job_id / "spec.json"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text('{"full_name": "Synthetic Fixture"}\n', encoding="utf-8")
    ledger.record_artifact(job_id=job.job_id, kind="contact_spec", path=artifact_path)
    job.artifact_dir = str(artifact_path.parent)
    job.transition_to("needs_review")
    ledger.record_job(job)
    ledger.transition_run("waiting_for_review")
    return run_id, job.job_id


def write_candidate_for_job(config: AppConfig, run_id: str, job_id: str) -> Path:
    artifact_dir = config.runs_dir / run_id / "artifacts" / job_id
    candidate = build_contact_candidate(
        {
            "full_name": "Ada Lovelace",
            "organization": "Example Labs",
            "email": "ada@example.test",
        }
    )
    (artifact_dir / "contact_candidate.json").write_text(json.dumps(candidate, indent=2), encoding="utf-8")
    return artifact_dir


def project_gws_route_contact(
    config: AppConfig,
    *,
    stored_profile: str = "ecochran76",
) -> tuple[BusinessCardService, str, str, str]:
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
    )
    service.close_lookup_prerequisites(
        run_id,
        operator="tester",
        sink="google_contacts",
        limit=4,
        write=True,
    )
    artifact_dir = config.runs_dir / run_id / "artifacts" / job_id
    sink_payload_path = artifact_dir / "sink_payloads.json"
    sink_payload_path.write_text(
        json.dumps(
            {
                "schema": "business-card-watchdog.sink-payloads.v1",
                "payloads": [
                    {
                        "sink": "google_contacts",
                        "dry_run": True,
                        "contact": {"email": "ada@example.test"},
                        "readiness": {
                            "status": "ready",
                            "details": {
                                "profile": stored_profile,
                                "target_account": stored_profile,
                                "config_key": "sink.google_contacts_profile",
                                "live_apply_requires_selected_target": True,
                            },
                        },
                    }
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    RunLedger(config.runs_dir / run_id).record_artifact(
        job_id=job_id,
        kind="sink_payloads",
        path=sink_payload_path,
    )
    service.project_contacts_from_run(run_id)
    contact_id = str(service.list_contacts()["contacts"][0]["contact_id"])
    return service, run_id, job_id, contact_id


def test_service_lists_and_shows_runs_jobs_and_artifacts(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)

    runs = service.list_runs()
    run = service.get_run(run_id)
    jobs = service.list_jobs(run_id)
    job = service.get_job(job_id, run_id=run_id)

    assert runs[0]["run_id"] == run_id
    assert run["job_count"] == 1
    assert jobs[0]["job_id"] == job_id
    assert job["artifacts"][0]["kind"] == "contact_spec"


def test_service_runtime_readiness_reports_user_scope_runtime_state(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    config_path.write_text(f'data_dir = "{data_dir}"\n[watch]\ninputs = []\n', encoding="utf-8")
    config = AppConfig(config_path=config_path, data_dir=data_dir)
    report = BusinessCardService(config).runtime_readiness()

    assert report["schema"] == "business-card-watchdog.runtime-readiness.v1"
    assert report["state"] in {"ready", "warning"}
    assert report["network_calls_made"] == 0
    assert report["writes_attempted"] == 0
    assert report["config"]["config_exists"] is True
    assert report["watch"]["inputs"] == []
    checks = {check["name"]: check for check in report["checks"]}
    assert checks["config_file"]["status"] == "ready"
    assert checks["data_dir"]["status"] == "ready"
    assert checks["business_card_skill"]["status"] == "ready"
    assert checks["watch_inputs_configured"]["status"] == "warning"
    assert any(action["action"] == "configure_watch_inputs" for action in report["safe_next_actions"])
    assert any(
        action["action"] == "run_fixture_review_routing_drill"
        and action["command"] == "drills review-routing"
        for action in report["safe_next_actions"]
    )
    assert any("Do not process private SyncThing images" in item for item in report["explicit_stop_conditions"])


def test_service_offline_pilot_gap_audit_reports_remaining_live_boundaries(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")

    audit = BusinessCardService(config).offline_pilot_gap_audit()

    assert audit["schema"] == "business-card-watchdog.offline-pilot-gap-audit.v1"
    assert audit["state"] == "ready_for_live_operator_boundary"
    assert audit["recommended_next_slice"] == "operator_selected_live_smoke"
    assert audit["coverage"]["missing_doc_count"] == 0
    assert {item["name"] for item in audit["drill_surfaces"]} >= {
        "multi_card_preclassification",
        "review_routing",
        "live_pilot_rehearsal",
        "child_replacement_readiness",
    }
    assert {item["boundary"] for item in audit["remaining_boundaries"]} >= {
        "operator_selected_live_smoke",
        "private_syncthing_source_processing",
        "paid_api_enrichment",
        "non_loopback_api_exposure",
    }
    assert audit["writes_attempted"] == 0
    assert audit["network_calls_made"] == 0
    assert audit["audit_written"] is True
    assert Path(audit["audit_path"]).exists()

    status = BusinessCardService(config).status()
    assert status["commands"]["offline_pilot_gap_audit"] == "offline-pilot-gap-audit --json"
    assert any(action["action"] == "inspect_offline_pilot_gap_audit" for action in status["safe_next_actions"])


def test_service_recovery_report_composes_status_and_recovery_commands(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    run_id, _job_id = make_recorded_run(config)

    report = BusinessCardService(config).service_recovery_report(run_id=run_id)

    assert report["schema"] == "business-card-watchdog.service-recovery.v1"
    assert report["run_id"] == run_id
    assert report["network_calls_made"] == 0
    assert report["writes_attempted"] == 0
    assert report["commands"]["install"].startswith(f"bcw --config {config.config_path} service install")
    assert report["commands"]["restart"] == "systemctl --user restart business-card-watchdog.service"
    assert f"actions run-next --run-id {run_id}" in report["commands"]["resume"]
    assert report["commands"]["live_pilot_status"] == (
        f"bcw --config {config.config_path} runs live-pilot-status {run_id} --no-write --json"
    )
    assert report["commands"]["live_pilot_handoff"] == (
        f"bcw --config {config.config_path} runs live-pilot-handoff {run_id}"
    )
    assert report["commands"]["review_routing_drill"] == (
        f"bcw --config {config.config_path} drills review-routing --json"
    )
    assert report["recovery_sequence"][0]["step"] == "status"
    assert any(action["action"] == "inspect_watch_status" for action in report["safe_next_actions"])
    assert any(
        action["action"] == "run_fixture_review_routing_drill"
        and action["command"] == report["commands"]["review_routing_drill"]
        for action in report["safe_next_actions"]
    )
    assert any(
        action["action"] == "inspect_live_pilot_status"
        and action["command"] == report["commands"]["live_pilot_status"]
        for action in report["safe_next_actions"]
    )
    assert any(
        action["action"] == "inspect_live_pilot_handoff"
        and action["command"] == report["commands"]["live_pilot_handoff"] + " --no-write --json"
        for action in report["safe_next_actions"]
    )
    assert "Do not scan or process private SyncThing images from generic recovery." in report["explicit_stop_conditions"]


def test_service_watch_backlog_preflight_redacts_private_source_paths(tmp_path: Path) -> None:
    source = tmp_path / "Private Phone Camera"
    write_synthetic_image(source / "private-card-photo.png")
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        watch=WatchConfig(inputs=[str(source)], settle_seconds=0.0),
    )

    payload = BusinessCardService(config).watch_backlog_preflight(write=True)
    serialized = json.dumps(payload, sort_keys=True)

    assert payload["schema"] == "business-card-watchdog.watch-backlog-preflight.v1"
    assert payload["state"] == "ready_for_operator_selected_dry_run"
    assert payload["recommended_next_action"] == "prepare_watch_dry_run_selection_handoff"
    assert payload["counts"]["backlog"] == 1
    assert payload["counts"]["unsettled"] == 0
    assert payload["inputs"] == [
        {
            "input_ref": "input_0",
            "configured_ref_kind": "path",
            "configured_ref_display": "<redacted-path>",
        }
    ]
    assert payload["private_paths_redacted"] is True
    assert payload["private_filenames_redacted"] is True
    assert payload["files_processed"] == 0
    assert payload["ocr_attempted"] == 0
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    assert payload["runtime_artifact_written"] is True
    assert Path(payload["preflight_path"]).exists()
    assert str(source) not in serialized
    assert "private-card-photo.png" not in serialized
    assert payload["safe_next_actions"][0]["action"] == "inspect_watch_dry_run_selection_handoff"
    assert payload["safe_next_actions"][0]["requires_explicit_operator_action"] is False
    assert payload["safe_next_actions"][1]["action"] == "operator_explicit_watch_dry_run"
    assert payload["safe_next_actions"][1]["requires_explicit_operator_action"] is True
    assert "This preflight does not process watched files." in payload["explicit_stop_conditions"][0]


def test_service_watch_backlog_preflight_can_preview_without_writing(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        watch=WatchConfig(inputs=["$fsr:sync_phone"], settle_seconds=0.0),
        path_aliases={"sync_phone": str(tmp_path / "missing")},
    )

    payload = BusinessCardService(config).watch_backlog_preflight(write=False)

    assert payload["state"] == "blocked"
    assert payload["last_error_present"] is True
    assert "missing" not in json.dumps(payload, sort_keys=True)
    assert payload["inputs"][0]["configured_ref_display"] == "$fsr:sync_phone"
    assert payload["runtime_artifact_written"] is False
    assert payload["preflight_path"] is None
    assert not (config.data_dir / "watch_backlog_preflight.json").exists()


def test_service_practice_corpus_manifest_inventories_images_and_pdfs_without_processing(
    tmp_path: Path,
) -> None:
    phone = tmp_path / "Private Phone Camera"
    scanner = tmp_path / "Private Scanner"
    write_synthetic_image(phone / "20260620_111933.jpg")
    pdf = scanner / "2026_06_20_11_21_42.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-1.4\n% synthetic scanner fixture\n")
    (scanner / "old_archive.pdf").write_bytes(b"%PDF-1.4\n% old synthetic archive\n")
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        watch=WatchConfig(inputs=["$fsr:sync_phone", "$fsr:scanner"], settle_seconds=0.0),
        path_aliases={"sync_phone": str(phone), "scanner": str(scanner)},
    )

    payload = BusinessCardService(config).watch_practice_corpus_manifest(
        write=True,
        include_globs=["20260620_11*.jpg", "2026_06_20_11_21_42.pdf"],
    )
    serialized = json.dumps(payload, sort_keys=True)

    assert payload["schema"] == "business-card-watchdog.practice-corpus-manifest.v1"
    assert payload["state"] == "ready_for_training_manifest_review"
    assert payload["input_count"] == 2
    assert payload["entry_count"] == 2
    assert payload["include_globs"] == ["20260620_11*.jpg", "2026_06_20_11_21_42.pdf"]
    assert payload["recursive"] is False
    assert payload["filtered_glob_scan"] is True
    assert payload["counts"]["images"] == 1
    assert payload["counts"]["pdf_documents"] == 1
    assert payload["counts"]["current_watcher_processable"] == 2
    assert payload["private_paths_redacted"] is True
    assert payload["files_processed"] == 0
    assert payload["ocr_attempted"] == 0
    assert payload["pdfs_rasterized"] == 0
    assert payload["crops_created"] == 0
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    assert payload["runtime_artifact_written"] is True
    assert Path(payload["manifest_path"]).exists()
    assert str(phone) not in serialized
    assert str(scanner) not in serialized
    assert "old_archive.pdf" not in serialized
    entries_by_kind = {entry["media_kind"]: entry for entry in payload["entries"]}
    assert entries_by_kind["image"]["role_hint"] == "phone_camera_image"
    assert entries_by_kind["image"]["current_watcher_processable"] is True
    assert entries_by_kind["pdf_document"]["role_hint"] == "scanner_pdf_document"
    assert entries_by_kind["pdf_document"]["current_watcher_processable"] is True
    assert entries_by_kind["pdf_document"]["current_processing_note"] == "document_intake_supported"
    assert len(entries_by_kind["image"]["sha256"]) == 64
    assert len(entries_by_kind["pdf_document"]["sha256"]) == 64


def test_service_watch_dry_run_selection_handoff_validates_response_and_command_copy(
    tmp_path: Path,
) -> None:
    source = tmp_path / "Private Phone Camera"
    write_synthetic_image(source / "private-card-photo.png")
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        watch=WatchConfig(inputs=[str(source)], settle_seconds=0.0),
    )
    service = BusinessCardService(config)

    handoff = service.watch_dry_run_selection_handoff(write=True)
    serialized_handoff = json.dumps(handoff, sort_keys=True)
    response = (
        "input_ref=input_0 operator=tester mode=dry_run "
        "safety_confirmation='private dry run approved for this configured source'"
    )
    validation = service.validate_watch_dry_run_operator_response(response=response)
    serialized_validation = json.dumps(validation, sort_keys=True)
    packet = service.watch_dry_run_command_copy_packet(
        response=response,
        acknowledgement="I understand this will dry-run the configured private watch backlog",
    )

    assert handoff["schema"] == "business-card-watchdog.watch-dry-run-selection-handoff.v1"
    assert handoff["state"] == "awaiting_operator_response"
    assert handoff["entry_count"] == 1
    assert handoff["entries"][0]["input_ref"] == "input_0"
    assert handoff["handoff_written"] is True
    assert Path(handoff["handoff_path"]).exists()
    assert str(source) not in serialized_handoff
    assert "private-card-photo.png" not in serialized_handoff
    assert validation["schema"] == "business-card-watchdog.watch-dry-run-operator-response-validation.v1"
    assert validation["state"] == "ready_for_command_copy"
    assert validation["operator_response_redacted"]["raw_response_stored"] is False
    assert validation["operator_response_redacted"]["safety_confirmation_present"] is True
    assert "private dry run approved" not in serialized_validation
    assert str(source) not in serialized_validation
    assert "private-card-photo.png" not in serialized_validation
    assert packet["schema"] == "business-card-watchdog.watch-dry-run-command-copy-packet.v1"
    assert packet["state"] == "ready_for_operator_copy"
    assert packet["selected_input_ref"] == "input_0"
    assert packet["selected_limit"] == 1
    assert packet["command_copy_text"] == "watch --once --dry-run --input-ref input_0 --limit 1"
    assert packet["processes_watched_files"] is False
    assert packet["copying_command_would_process_watched_files"] is True
    assert packet["writes_attempted"] == 0
    assert packet["network_calls_made"] == 0


def test_service_watch_dry_run_command_copy_blocks_without_acknowledgement(tmp_path: Path) -> None:
    source = tmp_path / "Private Phone Camera"
    write_synthetic_image(source / "private-card-photo.png")
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        watch=WatchConfig(inputs=[str(source)], settle_seconds=0.0),
    )
    response = (
        "input_ref=input_0 operator=tester mode=dry_run "
        "safety_confirmation='private dry run approved for this configured source'"
    )

    packet = BusinessCardService(config).watch_dry_run_command_copy_packet(response=response)

    assert packet["state"] == "blocked"
    assert packet["command_copy_text"] is None
    assert "acknowledgement does not match required text" in packet["blocked_reasons"]


def test_service_watch_dry_run_command_copy_blocks_invalid_limit(tmp_path: Path) -> None:
    source = tmp_path / "Private Phone Camera"
    write_synthetic_image(source / "private-card-photo.png")
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        watch=WatchConfig(inputs=[str(source)], settle_seconds=0.0),
    )
    response = (
        "input_ref=input_0 operator=tester mode=dry_run "
        "safety_confirmation='private dry run approved for this configured source'"
    )

    packet = BusinessCardService(config).watch_dry_run_command_copy_packet(
        response=response,
        acknowledgement="I understand this will dry-run the configured private watch backlog",
        limit=0,
    )

    assert packet["state"] == "blocked"
    assert packet["command_copy_text"] is None
    assert "limit must be greater than zero" in packet["blocked_reasons"]


def test_service_watch_dry_run_readiness_redacts_private_source_and_blocks_command(tmp_path: Path) -> None:
    source = tmp_path / "Private Phone Camera"
    write_synthetic_image(source / "private-card-photo.png")
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        watch=WatchConfig(inputs=[str(source)], settle_seconds=0.0),
    )

    payload = BusinessCardService(config).watch_dry_run_readiness(write=True)
    serialized = json.dumps(payload, sort_keys=True)

    assert payload["schema"] == "business-card-watchdog.watch-dry-run-readiness.v1"
    assert payload["state"] == "ready_for_operator_response"
    assert payload["preflight_summary"]["counts"]["backlog"] == 1
    assert payload["handoff_summary"]["entry_count"] == 1
    assert payload["handoff_summary"]["entries"][0]["configured_ref_display"] == "<redacted-path>"
    assert payload["command_copy_text"] is None
    assert payload["files_processed"] == 0
    assert payload["ocr_attempted"] == 0
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    assert payload["runtime_artifact_written"] is True
    assert Path(payload["readiness_path"]).exists()
    assert payload["operator_sequence"][-1]["command"] == "watch --once --dry-run"
    assert payload["operator_sequence"][-1]["blocked_until"] == "command_copy_packet_state_ready_for_operator_copy"
    assert str(source) not in serialized
    assert "private-card-photo.png" not in serialized


def test_service_live_target_candidates_report_blocks_unready_jobs(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
    )
    run_id, job_id = make_recorded_run(config)

    report = BusinessCardService(config).live_target_candidates(run_id=run_id, sink="google_contacts")

    assert report["schema"] == "business-card-watchdog.live-target-candidates.v1"
    assert report["run_id"] == run_id
    assert report["candidate_count"] == 1
    assert report["ready_candidate_count"] == 0
    assert report["writes_attempted"] == 0
    assert report["network_calls_made"] == 0
    candidate = report["candidates"][0]
    assert candidate["schema"] == "business-card-watchdog.live-target-candidate.v1"
    assert candidate["job_id"] == job_id
    assert candidate["sink"] == "google_contacts"
    assert candidate["state"] == "blocked"
    assert "job state is needs_review" in candidate["stop_reasons"]
    assert "sinks select-live-target" in candidate["commands"]["select_lookup_target"]
    assert candidate["commands"]["validate_operator_response"] == (
        f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
    )


def test_service_live_readiness_audit_writes_run_level_artifact(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
    )
    run_id, _job_id = make_recorded_run(config)

    audit = BusinessCardService(config).live_readiness_audit(run_id=run_id, sink="google_contacts")

    assert audit["schema"] == "business-card-watchdog.live-readiness-audit.v1"
    assert audit["run_id"] == run_id
    assert audit["sink"] == "google_contacts"
    assert audit["candidate_count"] == 1
    assert audit["writes_attempted"] == 0
    assert audit["network_calls_made"] == 0
    assert audit["commands"]["live_pilot_handoff"] == f"runs live-pilot-handoff {run_id}"
    assert audit["commands"]["validate_operator_response"] == (
        f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
    )
    assert "audit_path" in audit
    assert Path(audit["audit_path"]).exists()
    artifacts = BusinessCardService(config).list_artifacts(run_id)
    assert any(artifact["kind"] == "live_readiness_audit" for artifact in artifacts)


def test_service_live_selection_requirements_report_writes_run_level_artifact(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
    )
    run_id, job_id = make_recorded_run(config)

    report = BusinessCardService(config).live_selection_requirements(run_id=run_id, sink="google_contacts")

    assert report["schema"] == "business-card-watchdog.live-selection-requirements.v1"
    assert report["run_id"] == run_id
    assert report["sink"] == "google_contacts"
    assert report["candidate_count"] == 1
    assert report["entry_count"] == 1
    assert report["writes_attempted"] == 0
    assert report["network_calls_made"] == 0
    assert report["operator_response_contract"] == {
        "schema": "business-card-watchdog.operator-selection-response-contract.v1",
        "required_fields": ["run_id", "job_id", "sink", "operator", "scope", "safety_confirmation"],
        "allowed_sinks": ["google_contacts", "odoo"],
        "allowed_scopes": ["lookup", "write", "readback", "all"],
        "format": (
            "run_id=<run_id> job_id=<job_id> sink=<google_contacts|odoo> "
            "operator=<operator> scope=<lookup|write|readback|all> safety_confirmation=<tenant-profile-account-confirmation>"
        ),
        "default_scope": "lookup",
        "requires_human_safety_confirmation": True,
        "creates_selected_live_target": False,
    }
    assert {field["name"] for field in report["required_operator_fields"]} == {
        "run_id",
        "job_id",
        "sink",
        "operator",
        "scope",
        "safety_confirmation",
    }
    entry = report["entries"][0]
    assert entry["job_id"] == job_id
    assert entry["state"] == "blocked"
    assert entry["selected_target_identity"] is None
    assert entry["abandonment_identity"] is None
    assert entry["missing_operator_fields"] == ["operator", "scope", "safety_confirmation"]
    assert entry["operator_response_template"] == (
        f"run_id={run_id} job_id={job_id} sink=google_contacts "
        "operator=<operator> scope=lookup safety_confirmation=<tenant-profile-account-confirmation>"
    )
    assert "Reply with an explicit live target selection" in entry["operator_prompt"]
    assert entry["copyable_approval_fields"] == {
        "run_id": run_id,
        "job_id": job_id,
        "sink": "google_contacts",
        "operator": "<operator>",
        "scope": "lookup",
        "safety_confirmation": "<tenant-profile-account-confirmation>",
    }
    assert entry["commands"]["selection_packet"] == (
        f"sinks live-selection-packet {job_id} --run-id {run_id} --sink google_contacts --operator <operator>"
    )
    assert "select-live-target" in entry["commands"]["select_target"]
    assert entry["commands"]["validate_operator_response"] == (
        f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
    )
    assert entry["commands"]["validate_operator_response_prefilled"] == (
        f"runs live-pilot-validate-response {run_id} "
        f"--response 'run_id={run_id} job_id={job_id} sink=google_contacts "
        "operator=<operator> scope=lookup safety_confirmation=<tenant-profile-account-confirmation>' --json"
    )
    assert report["commands"]["live_target_candidates"] == f"live-target-candidates --run-id {run_id} --sink google_contacts"
    assert report["commands"]["live_readiness_audit"] == f"live-readiness-audit --run-id {run_id} --sink google_contacts"
    assert report["commands"]["live_selection_requirements"] == (
        f"live-selection-requirements --run-id {run_id} --sink google_contacts"
    )
    assert report["commands"]["live_pilot_handoff"] == f"runs live-pilot-handoff {run_id}"
    assert report["commands"]["validate_operator_response"] == (
        f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
    )
    assert Path(report["requirements_path"]).exists()
    artifacts = BusinessCardService(config).list_artifacts(run_id)
    assert any(artifact["kind"] == "live_selection_requirements" for artifact in artifacts)


def test_service_operator_selected_live_smoke_preflight_reports_blocked_boundary(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
    )
    run_id, _job_id = make_recorded_run(config)

    preflight = BusinessCardService(config).operator_selected_live_smoke_preflight(
        run_id=run_id,
        sink="google_contacts",
    )

    assert preflight["schema"] == "business-card-watchdog.operator-selected-live-smoke-preflight.v1"
    assert preflight["state"] == "needs_preparation"
    assert preflight["recommended_next_step"] == "prepare_ready_candidate"
    assert preflight["run_id"] == run_id
    assert preflight["sink"] == "google_contacts"
    assert preflight["offline_pilot_gap_audit"]["state"] == "ready_for_live_operator_boundary"
    assert preflight["live_readiness_audit"]["state"] == "needs_preparation"
    assert preflight["live_selection_requirements"]["schema"] == "business-card-watchdog.live-selection-requirements.v1"
    assert preflight["entry_count"] == 1
    assert preflight["ready_entry_count"] == 0
    assert preflight["blocked_entry_count"] == 1
    assert "no candidate is ready for operator selection" in preflight["blocked_reasons"]
    assert preflight["operator_response_contract"]["creates_selected_live_target"] is False
    assert preflight["operator_selection_checklist"][0]["step"] == "inspect_offline_gap_audit"
    assert preflight["operator_selection_checklist"][-1]["requires_explicit_operator_action"] is True
    assert preflight["writes_attempted"] == 0
    assert preflight["network_calls_made"] == 0
    assert preflight["preflight_written"] is True
    assert Path(preflight["preflight_path"]).exists()
    persisted = json.loads(Path(preflight["preflight_path"]).read_text(encoding="utf-8"))
    assert persisted["preflight_written"] is True
    artifacts = BusinessCardService(config).list_artifacts(run_id)
    assert any(artifact["kind"] == "operator_selected_live_smoke_preflight" for artifact in artifacts)

    status = BusinessCardService(config).status()
    assert status["commands"]["operator_selected_live_smoke_preflight"] == (
        "operator-selected-live-smoke-preflight --json"
    )
    assert any(
        action["action"] == "inspect_operator_selected_live_smoke_preflight"
        for action in status["safe_next_actions"]
    )


def test_service_operator_live_pilot_readiness_packet_reports_ready_boundary(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f'data_dir = "{tmp_path / "data"}"\n'
        f'cache_dir = "{tmp_path / "cache"}"\n\n'
        "[sink]\n"
        "google_contacts = true\n"
        "dry_run = true\n",
        encoding="utf-8",
    )
    config = AppConfig(
        config_path=config_path,
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
        sink=SinkConfig(google_contacts=True, dry_run=True),
    )
    service = BusinessCardService(config)
    routing_drill = service.review_routing_drill()
    run_id = routing_drill["run_id"]
    job_id = routing_drill["job_id"]

    packet = service.operator_live_pilot_readiness_packet(run_id=run_id, sink="google_contacts")

    assert packet["schema"] == "business-card-watchdog.operator-live-pilot-readiness-packet.v1"
    assert packet["state"] == "ready_for_operator_response"
    assert packet["recommended_next_step"] == "selected_target_approval_boundary"
    assert packet["ready_entry_count"] == 1
    assert packet["active_selected_target_count"] == 0
    assert all(check["ok"] is True for check in packet["checks"])
    assert packet["blocked_reasons"] == []
    assert packet["synthetic_rehearsal_contract"]["command"] == "drills live-pilot-rehearsal --json"
    assert packet["synthetic_rehearsal_contract"]["required_packet_states"] == {
        "selected_target_approval_boundary": "ready_for_explicit_selected_target_creation",
        "selected_target_command_copy_packet": "ready_for_operator_copy",
        "live_pilot_command_copy_packet": "ready_for_operator_copy",
    }
    assert packet["commands"]["selected_target_approval_boundary"].startswith(
        f"runs selected-target-approval-boundary {run_id}"
    )
    assert packet["commands"]["selected_target_command_copy_packet"].startswith(
        f"runs selected-target-command-copy-packet {run_id}"
    )
    assert packet["commands"]["validate_operator_response_prefilled"].startswith(
        f"runs live-pilot-validate-response {run_id}"
    )
    assert packet["writes_attempted"] == 0
    assert packet["network_calls_made"] == 0
    assert packet["packet_written"] is True
    assert Path(packet["packet_path"]).exists()
    assert not (config.runs_dir / run_id / "artifacts" / job_id / "selected_live_target.json").exists()
    artifacts = service.list_artifacts(run_id)
    assert any(artifact["kind"] == "operator_live_pilot_readiness_packet" for artifact in artifacts)


def test_service_live_selection_packet_does_not_select_target(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
    )
    run_id, job_id = make_recorded_run(config)

    packet = BusinessCardService(config).live_selection_packet(
        job_id=job_id,
        run_id=run_id,
        sink="google_contacts",
        operator="tester",
        scope="lookup",
    )

    assert packet["schema"] == "business-card-watchdog.live-selection-packet.v1"
    assert packet["state"] == "blocked"
    assert packet["approval_state"] == "pending_operator_approval"
    assert packet["run_id"] == run_id
    assert packet["job_id"] == job_id
    assert packet["sink"] == "google_contacts"
    assert packet["writes_attempted"] == 0
    assert packet["network_calls_made"] == 0
    assert "job state is needs_review" in packet["blocked_reasons"]
    assert packet["operator_response_template"] == (
        f"run_id={run_id} job_id={job_id} sink=google_contacts "
        "operator=tester scope=lookup safety_confirmation=<tenant-profile-account-confirmation>"
    )
    assert packet["copyable_approval_fields"] == {
        "run_id": run_id,
        "job_id": job_id,
        "sink": "google_contacts",
        "operator": "tester",
        "scope": "lookup",
        "safety_confirmation": "<tenant-profile-account-confirmation>",
    }
    assert Path(packet["packet_path"]).exists()
    assert not Path(packet["existing_selected_target"]["path"]).exists()
    assert packet["existing_selected_target"]["target_safety_confirmed"] is False
    assert packet["existing_selected_target"]["replacement_requires_abandonment"] is False
    assert packet["existing_selected_target"]["can_select_replacement_now"] is True
    assert packet["existing_selected_target"]["abandon_command"] is None
    assert packet["commands"]["validate_operator_response"] == (
        f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
    )
    assert packet["commands"]["validate_operator_response_prefilled"] == (
        f"runs live-pilot-validate-response {run_id} "
        f"--response 'run_id={run_id} job_id={job_id} sink=google_contacts "
        "operator=tester scope=lookup safety_confirmation=<tenant-profile-account-confirmation>' --json"
    )
    assert packet["commands"]["selected_target_audit"] == (
        f"sinks selected-target-audit {job_id} --run-id {run_id} --scope lookup --no-write --json"
    )
    assert packet["commands"]["lookup_smoke_handoff"] == (
        f"sinks lookup-smoke-handoff {job_id} --run-id {run_id} --sink google_contacts --approved-by tester --json"
    )
    checklist = packet["pilot_command_checklist"]
    assert [row["step"] for row in checklist] == [
        "validate_operator_response",
        "create_selected_target",
        "selected_target_audit",
        "lookup_smoke_handoff",
        "live_lookup_pilot",
    ]
    assert checklist[0]["live_call"] is False
    assert checklist[1]["writes_runtime_artifact"] is True
    assert checklist[2]["command"] == packet["commands"]["selected_target_audit"]
    assert checklist[3]["writes_runtime_artifact"] is True
    assert checklist[4]["live_call"] is True
    assert checklist[4]["writes_sink"] is False
    assert "select-live-target" in packet["commands"]["create_selected_target"]
    artifacts = BusinessCardService(config).list_artifacts(run_id)
    assert any(artifact["kind"] == "live_selection_packet" for artifact in artifacts)
    assert not any(artifact["kind"] == "selected_live_target" for artifact in artifacts)


def test_service_live_selection_packet_all_scope_lists_write_and_readback_checklist(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
    )
    run_id, job_id = make_recorded_run(config)

    packet = BusinessCardService(config).live_selection_packet(
        job_id=job_id,
        run_id=run_id,
        sink="google_contacts",
        operator="tester",
        scope="all",
        write=False,
    )

    checklist = packet["pilot_command_checklist"]
    assert [row["step"] for row in checklist] == [
        "validate_operator_response",
        "create_selected_target",
        "selected_target_audit",
        "lookup_smoke_handoff",
        "live_lookup_pilot",
        "live_write_pilot",
        "readback_adapter_request",
        "live_readback_pilot",
    ]
    by_step = {row["step"]: row for row in checklist}
    assert by_step["live_write_pilot"]["live_call"] is True
    assert by_step["live_write_pilot"]["writes_sink"] is True
    assert by_step["readback_adapter_request"]["live_call"] is False
    assert by_step["live_readback_pilot"]["live_call"] is True
    assert by_step["live_readback_pilot"]["writes_sink"] is False
    assert packet["commands"]["readback_request"] == (
        f"sinks adapter-request {job_id} --run-id {run_id} --phase readback --json"
    )
    assert packet["writes_attempted"] == 0
    assert packet["network_calls_made"] == 0


def test_service_live_selection_packet_reports_existing_selected_target_context(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    first = service.select_live_target_for_job(
        job_id=job_id,
        run_id=run_id,
        sink="google_contacts",
        operator="tester",
        scope="lookup",
        safety_confirmation="fixture contact is safe for google contacts test profile",
    )["target"]

    active_packet = service.live_selection_packet(
        job_id=job_id,
        run_id=run_id,
        sink="google_contacts",
        operator="tester",
        scope="lookup",
        write=False,
    )

    assert active_packet["existing_selected_target"]["exists"] is True
    assert active_packet["existing_selected_target"]["identity"] == first["selection_id"]
    assert active_packet["existing_selected_target"]["target_safety_confirmed"] is True
    assert active_packet["existing_selected_target"]["abandoned"] is False
    assert active_packet["existing_selected_target"]["abandonment_identity"] is None
    assert active_packet["existing_selected_target"]["replacement_requires_abandonment"] is True
    assert active_packet["existing_selected_target"]["can_select_replacement_now"] is False
    assert "abandon-live-pilot" in active_packet["existing_selected_target"]["abandon_command"]
    assert active_packet["state"] == "blocked"
    assert "selected live target already exists; abandon it before selecting a replacement" in active_packet["blocked_reasons"]

    service.live_pilot_abandon_for_job(
        job_id=job_id,
        run_id=run_id,
        operator="tester",
        reason="replace with broader scope",
    )
    abandoned_packet = service.live_selection_packet(
        job_id=job_id,
        run_id=run_id,
        sink="google_contacts",
        operator="tester",
        scope="all",
        write=False,
    )

    assert abandoned_packet["existing_selected_target"]["identity"] == first["selection_id"]
    assert abandoned_packet["existing_selected_target"]["abandoned"] is True
    assert abandoned_packet["existing_selected_target"]["abandonment_identity"] == first["selection_id"]
    assert abandoned_packet["existing_selected_target"]["abandonment_reason"] == "replace with broader scope"
    assert abandoned_packet["existing_selected_target"]["replacement_requires_abandonment"] is False
    assert abandoned_packet["existing_selected_target"]["can_select_replacement_now"] is True
    assert abandoned_packet["existing_selected_target"]["abandon_command"] is None

    replacement = service.select_live_target_for_job(
        job_id=job_id,
        run_id=run_id,
        sink="google_contacts",
        operator="tester",
        scope="all",
        safety_confirmation="fixture contact is safe for google contacts test profile",
    )["target"]
    replacement_packet = service.live_selection_packet(
        job_id=job_id,
        run_id=run_id,
        sink="google_contacts",
        operator="tester",
        scope="all",
        write=False,
    )

    assert replacement_packet["existing_selected_target"]["identity"] == replacement["selection_id"]
    assert replacement_packet["existing_selected_target"]["abandoned"] is False
    assert replacement_packet["existing_selected_target"]["abandonment_identity"] is None
    assert replacement_packet["existing_selected_target"]["abandonment_reason"] is None
    assert replacement_packet["existing_selected_target"]["replacement_requires_abandonment"] is True
    assert replacement_packet["existing_selected_target"]["can_select_replacement_now"] is False


def test_service_run_summary_and_review_queue(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)

    summary = service.run_summary(run_id)
    phase_report = service.phase_report(run_id)
    readiness_report = service.pilot_readiness_report(run_id)
    queue = service.review_queue(run_id=run_id)
    bundle = service.review_bundle(run_id=run_id)
    bundle_path = config.runs_dir / run_id / "review_bundle.json"

    assert summary["run_id"] == run_id
    assert summary["needs_review_count"] == 1
    assert summary["artifact_counts"]["contact_spec"] == 1
    assert summary["review_workbook_preview_summary"]["schema"] == (
        "business-card-watchdog.review-workbook-preview-summary.v1"
    )
    assert summary["review_workbook_preview_summary"]["has_preview"] is False
    assert phase_report["schema"] == "business-card-watchdog.phase-report.v1"
    assert phase_report["job_count"] == 1
    assert phase_report["review_workbook_preview"]["schema"] == (
        "business-card-watchdog.review-workbook-preview-phase.v1"
    )
    assert phase_report["review_workbook_preview"]["state"] == "not_started"
    assert phase_report["review_workbook_preview"]["counts"]["not_started"] == 1
    assert phase_report["dashboard_summary"]["schema"] == "business-card-watchdog.phase-dashboard-summary.v1"
    assert phase_report["dashboard_summary"]["review_workbook_preview_state"] == "not_started"
    assert phase_report["dashboard_summary"]["blocked_phases"] == [{"phase": "review", "count": 1}]
    assert phase_report["dashboard_summary"]["explicit_required_phase_count"] == 0
    assert phase_report["commands"]["live_pilot_handoff"] == f"runs live-pilot-handoff {run_id}"
    assert phase_report["commands"]["review_bundle"] == f"reviews bundle --run-id {run_id} --state all"
    assert phase_report["phases"][2]["phase"] == "review"
    assert phase_report["phases"][2]["counts"]["blocked"] == 1
    assert phase_report["jobs"][0]["phase_states"]["review"] == "blocked"
    assert phase_report["stop_rules"]["schema"] == "business-card-watchdog.phase-stop-rules.v1"
    assert phase_report["stop_rules"]["generic_continue_policy"]["allows_paid_api_enrichment"] is False
    assert phase_report["stop_rules"]["generic_continue_policy"]["allows_live_sink_write"] is False
    assert "prepare_sink_apply_pilot_report" in phase_report["stop_rules"]["safe_auto_actions"]
    assert "execute_sink_write_pilot" in phase_report["stop_rules"]["explicit_operator_actions"]
    assert phase_report["stop_rules"]["phase_actions"]["write_pilot"]["safe_auto_actions"] == []
    assert phase_report["stop_rules"]["phase_actions"]["write_pilot"]["explicit_operator_actions"] == [
        "execute_sink_write_pilot"
    ]
    assert readiness_report["schema"] == "business-card-watchdog.pilot-readiness-report.v1"
    assert readiness_report["state"] == "explicit_operator_required"
    assert readiness_report["counts"]["blocked"] == 1
    assert readiness_report["blocked_job_ids"] == [job_id]
    assert readiness_report["explicit_action_job_ids"] == [job_id]
    assert readiness_report["jobs"][0]["readiness_state"] == "explicit_operator_required"
    assert readiness_report["jobs"][0]["blocking_reasons"][0]["phase"] == "review"
    assert readiness_report["jobs"][0]["review_matrix"]["contact_source"] == "missing"
    assert readiness_report["writes_attempted"] == 0
    assert readiness_report["network_calls_made"] == 0
    assert readiness_report["commands"]["live_pilot_handoff"] == f"runs live-pilot-handoff {run_id}"
    assert readiness_report["commands"]["phase_report"] == f"runs phase-report {run_id}"
    assert queue[0]["job_id"] == job_id
    assert queue[0]["artifact_kinds"] == ["contact_spec"]
    assert queue[0]["next_action"]["action"] == "review_contact"
    assert service.review_queue(run_id=run_id, next_action="review_contact")[0]["job_id"] == job_id
    assert service.review_queue(run_id=run_id, artifact_kind="contact_spec")[0]["job_id"] == job_id
    assert service.review_queue(run_id=run_id, next_action="plan_sinks") == []
    assert service.review_queue(run_id=run_id, artifact_kind="reviewed_contact") == []
    assert bundle["schema"] == "business-card-watchdog.review-bundle.v1"
    assert bundle["review_bundle_path"] == str(bundle_path)
    assert bundle["entries"][0]["job_id"] == job_id
    assert bundle["entries"][0]["next_action"]["action"] == "review_contact"
    assert bundle["entries"][0]["decision_template"]["action"] == "approve_for_routing"
    assert bundle["entries"][0]["commands"]["review"] == f"jobs review {job_id} --run-id {run_id}"
    assert bundle["entries"][0]["commands"]["live_pilot_handoff"] == f"runs live-pilot-handoff {run_id}"
    assert bundle["entries"][0]["commands"]["validate_operator_response"] == (
        f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
    )
    assert bundle["entries"][0]["review_matrix"]["schema"] == "business-card-watchdog.review-matrix-entry.v1"
    assert bundle["entries"][0]["review_matrix"]["contact_source"] == "missing"
    assert bundle["entries"][0]["review_matrix"]["duplicate_state"] == "not_assessed"
    assert bundle["entries"][0]["review_matrix"]["enrichment_state"] == "not_requested"
    assert bundle["entries"][0]["review_matrix"]["route_state"] == "not_planned"
    assert bundle["entries"][0]["review_matrix"]["sink_lookup_state"] == "not_started"
    assert bundle["groups"]["by_state"]["needs_review"]["job_ids"] == [job_id]
    assert bundle["groups"]["by_next_action"]["review_contact"]["count"] == 1
    assert bundle["groups"]["by_duplicate_state"]["not_assessed"]["job_ids"] == [job_id]
    assert bundle["groups"]["by_enrichment_state"]["not_requested"]["count"] == 1
    assert bundle["groups"]["by_route_state"]["not_planned"]["count"] == 1
    assert bundle["groups"]["by_sink_lookup_state"]["not_started"]["count"] == 1
    assert bundle["decision_import_template"][0]["job_id"] == job_id
    assert bundle["commands"]["apply_decisions"] == f"reviews apply-decisions --run-id {run_id} --decisions-file <path>"
    assert bundle["commands"]["phase_report"] == f"runs phase-report {run_id}"
    assert bundle["commands"]["run_next_safe"] == f"actions run-next --run-id {run_id}"
    assert bundle["commands"]["live_pilot_handoff"] == f"runs live-pilot-handoff {run_id}"
    assert bundle["commands"]["validate_operator_response"] == (
        f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
    )
    assert bundle["commands"]["mcp_phase_report"] == (
        f"mcp-call business_card_watchdog_phase_report --arguments-json '{{\"run_id\":\"{run_id}\"}}'"
    )
    assert bundle["writes_attempted"] == 0
    assert bundle["network_calls_made"] == 0
    assert bundle_path.exists()
    assert any(artifact["kind"] == "review_bundle" for artifact in service.list_artifacts(run_id))

    html = service.review_html(run_id=run_id)
    html_path = config.runs_dir / run_id / "review_bundle.html"
    assert html["schema"] == "business-card-watchdog.review-html.v1"
    assert html["html_path"] == str(html_path)
    assert "Business Card Review" in html["html"]
    assert "Commands" in html["html"]
    assert "By Duplicate State" in html["html"]
    assert "By Enrichment State" in html["html"]
    assert "Review Matrix" in html["html"]
    assert f"runs phase-report {run_id}" in html["html"]
    assert f"actions run-next --run-id {run_id}" in html["html"]
    assert f"runs live-pilot-handoff {run_id}" in html["html"]
    assert job_id in html["html"]
    assert html_path.exists()
    assert any(artifact["kind"] == "review_html" for artifact in service.list_artifacts(run_id))

    workbook = service.review_workbook(run_id=run_id)
    workbook_path = config.runs_dir / run_id / "review_workbook.csv"
    rows = list(csv.DictReader(StringIO(workbook["csv"])))
    assert workbook["schema"] == "business-card-watchdog.review-workbook.v1"
    assert workbook["workbook_path"] == str(workbook_path)
    assert workbook["format"] == "csv"
    assert workbook["row_count"] == 1
    assert rows[0]["run_id"] == run_id
    assert rows[0]["job_id"] == job_id
    assert rows[0]["state"] == "needs_review"
    assert rows[0]["next_action"] == "review_contact"
    assert rows[0]["decision_action"] == "approve_for_routing"
    assert rows[0]["review_action"] == "approve_for_routing"
    assert rows[0]["matrix_contact_source"] == "missing"
    assert rows[0]["matrix_duplicate_state"] == "not_assessed"
    assert rows[0]["matrix_enrichment_state"] == "not_requested"
    assert rows[0]["matrix_route_state"] == "not_planned"
    assert rows[0]["matrix_sink_lookup_state"] == "not_started"
    assert rows[0]["live_pilot_handoff_command"] == f"runs live-pilot-handoff {run_id}"
    assert rows[0]["validate_operator_response_command"] == (
        f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
    )
    assert "corrected_full_name" in rows[0]
    assert "corrected_email" in rows[0]
    assert "contact_spec" in rows[0]["artifact_kinds"]
    assert workbook_path.exists()
    assert any(artifact["kind"] == "review_workbook" for artifact in service.list_artifacts(run_id))


def test_service_run_summary_includes_enrichment_budget(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    run_id, job_id = make_recorded_run(config)
    ledger = RunLedger(config.runs_dir / run_id)
    artifact_dir = config.runs_dir / run_id / "artifacts" / job_id
    artifacts = {
        "enrichment_public_web_request": {
            "max_queries": 3,
            "search_calls_attempted": 0,
            "network_calls_made": 0,
        },
        "enrichment_public_web_result": {
            "submitted_result_count": 2,
            "search_calls_attempted": 0,
            "network_calls_made": 0,
        },
        "enrichment_provider_request": {
            "max_results": 5,
            "paid_api_calls_attempted": 0,
            "network_calls_made": 0,
        },
        "enrichment_provider_result": {
            "submitted_result_count": 1,
            "paid_api_calls_attempted": 0,
            "network_calls_made": 0,
        },
    }
    for kind, payload in artifacts.items():
        path = artifact_dir / f"{kind}.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        ledger.record_artifact(job_id=job_id, kind=kind, path=path)
    malformed_path = artifact_dir / "malformed_enrichment_provider_result.json"
    malformed_path.write_text("{not-json\n", encoding="utf-8")
    ledger.record_artifact(job_id=job_id, kind="enrichment_provider_result", path=malformed_path)

    summary = BusinessCardService(config).run_summary(run_id)

    assert summary["enrichment_budget"]["schema"] == "business-card-watchdog.enrichment-budget-summary.v1"
    assert summary["enrichment_budget"]["public_web"]["request_count"] == 1
    assert summary["enrichment_budget"]["public_web"]["result_count"] == 1
    assert summary["enrichment_budget"]["public_web"]["max_queries"] == 3
    assert summary["enrichment_budget"]["public_web"]["max_queries_per_run"] == 200
    assert summary["enrichment_budget"]["public_web"]["remaining_queries"] == 197
    assert summary["enrichment_budget"]["public_web"]["submitted_result_count"] == 2
    assert summary["enrichment_budget"]["paid_provider"]["request_count"] == 1
    assert summary["enrichment_budget"]["paid_provider"]["result_count"] == 1
    assert summary["enrichment_budget"]["paid_provider"]["max_results"] == 5
    assert summary["enrichment_budget"]["paid_provider"]["max_results_per_run"] == 50
    assert summary["enrichment_budget"]["paid_provider"]["remaining_results"] == 45
    assert summary["enrichment_budget"]["paid_provider"]["submitted_result_count"] == 1
    assert summary["enrichment_budget"]["paid_provider"]["paid_api_calls_attempted"] == 0
    assert summary["enrichment_budget"]["unreadable_artifact_count"] == 1


def test_service_public_web_enrichment_request_enforces_run_budget(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        enrichment=EnrichmentConfig(
            enabled=True,
            max_public_web_queries_per_contact=3,
            max_public_web_queries_per_run=3,
        ),
    )
    run_id, job_id = make_recorded_run(config)
    artifact_dir = write_candidate_for_job(config, run_id, job_id)
    ledger = RunLedger(config.runs_dir / run_id)
    existing_request = artifact_dir / "existing_public_web_request.json"
    existing_request.write_text(
        json.dumps({"max_queries": 3, "search_calls_attempted": 0, "network_calls_made": 0}),
        encoding="utf-8",
    )
    ledger.record_artifact(job_id=job_id, kind="enrichment_public_web_request", path=existing_request)

    try:
        BusinessCardService(config).request_enrichment(
            job_id=job_id,
            run_id=run_id,
            mode="public_web",
            requested_by="tester",
        )
    except ValueError as exc:
        assert "public web enrichment request exceeds run budget" in str(exc)
    else:
        raise AssertionError("expected public-web enrichment request to exceed run budget")

    artifacts = BusinessCardService(config).list_artifacts(run_id)
    assert sum(1 for artifact in artifacts if artifact["kind"] == "enrichment_request") == 0


def test_service_paid_provider_enrichment_request_enforces_run_budget(tmp_path: Path) -> None:
    keys_path = tmp_path / "API-keys.env"
    keys_path.write_text("APOLLO_API_KEY=fixture-value-redacted\n", encoding="utf-8")
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        enrichment=EnrichmentConfig(
            enabled=True,
            allow_paid_api=True,
            api_keys_env=keys_path,
            max_paid_provider_results_per_contact=2,
            max_paid_provider_results_per_run=2,
            apollo=EnrichmentProviderConfig(enabled=True),
        ),
    )
    run_id, job_id = make_recorded_run(config)
    artifact_dir = write_candidate_for_job(config, run_id, job_id)
    ledger = RunLedger(config.runs_dir / run_id)
    existing_request = artifact_dir / "existing_provider_request.json"
    existing_request.write_text(
        json.dumps({"max_results": 2, "paid_api_calls_attempted": 0, "network_calls_made": 0}),
        encoding="utf-8",
    )
    ledger.record_artifact(job_id=job_id, kind="enrichment_provider_request", path=existing_request)

    try:
        BusinessCardService(config).request_enrichment(
            job_id=job_id,
            run_id=run_id,
            mode="api",
            requested_by="tester",
            allow_paid_enrichment=True,
        )
    except ValueError as exc:
        assert "paid provider enrichment request exceeds run budget" in str(exc)
    else:
        raise AssertionError("expected paid-provider enrichment request to exceed run budget")

    artifacts = BusinessCardService(config).list_artifacts(run_id)
    assert sum(1 for artifact in artifacts if artifact["kind"] == "enrichment_request") == 0


def test_service_next_actions_recommends_review_for_needs_review_job(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    run_id, job_id = make_recorded_run(config)

    payload = BusinessCardService(config).next_actions(run_id=run_id)

    assert payload["action_count"] == 1
    assert payload["actions"][0]["job_id"] == job_id
    assert payload["actions"][0]["action"] == "review_contact"
    assert payload["actions"][0]["safe_to_auto_continue"] is False
    assert payload["actions"][0]["requires_explicit_operator_action"] is True


def test_service_status_and_sink_readiness_are_structured(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    service = BusinessCardService(config)

    status = service.status()
    readiness = service.sink_readiness()

    assert status["schema"] == "business-card-watchdog.status.v1"
    assert status["skill_ready"] is True
    assert "watch" in status
    assert status["commands"]["runtime_readiness"] == "runtime-readiness --json"
    assert status["commands"]["service_recovery"] == "service recovery --json"
    assert status["safe_next_actions"][0]["action"] == "inspect_runtime_readiness"
    assert status["writes_attempted"] == 0
    assert status["network_calls_made"] == 0
    assert readiness["dry_run"] is True
    assert {sink["sink"] for sink in readiness["sinks"]} == {"google_contacts", "odoo"}


def test_service_operator_dashboard_composes_no_live_readiness(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    run_id, _job_id = make_recorded_run(config)
    service = BusinessCardService(config)

    dashboard = service.operator_dashboard(run_id=run_id)

    assert dashboard["schema"] == "business-card-watchdog.operator-dashboard.v1"
    assert dashboard["selected_run_id"] == run_id
    assert dashboard["run_count"] == 1
    assert dashboard["status"]["schema"] == "business-card-watchdog.status.v1"
    assert dashboard["runtime_readiness"]["schema"] == "business-card-watchdog.runtime-readiness.v1"
    assert dashboard["service_recovery"]["schema"] == "business-card-watchdog.service-recovery.v1"
    assert dashboard["run_summary"]["run_id"] == run_id
    assert dashboard["phase_dashboard_summary"]["schema"] == "business-card-watchdog.phase-dashboard-summary.v1"
    assert dashboard["review_counts"]["needs_review"] == 1
    assert dashboard["next_action_summary"]["action_count"] == 1
    assert dashboard["next_action_summary"]["explicit_operator_count"] == 1
    assert dashboard["next_action_summary"]["by_action"] == {"review_contact": 1}
    assert dashboard["next_action_summary"]["sample_actions"][0]["command"] == "jobs review"
    assert dashboard["next_action_summary"]["sample_actions"][0]["requires_explicit_operator_action"] is True
    assert dashboard["live_pilot_summary"]["state"] == "blocked"
    assert dashboard["live_pilot_handoff_summary"]["schema"] == (
        "business-card-watchdog.operator-dashboard.live-pilot-handoff-summary.v1"
    )
    assert dashboard["live_pilot_handoff_summary"]["state"] == "blocked"
    assert dashboard["live_pilot_handoff_summary"]["action_counts"] == {"no_live_candidate": 1}
    assert dashboard["live_pilot_handoff_summary"]["operator_required_count"] == 0
    assert dashboard["live_pilot_handoff_summary"]["operator_entries"] == []
    assert dashboard["live_pilot_handoff_summary"]["operator_response_template_count"] == 0
    assert dashboard["live_pilot_handoff_summary"]["operator_response_templates"] == []
    assert dashboard["live_pilot_handoff_summary"]["writes_attempted"] == 0
    assert dashboard["live_pilot_handoff_summary"]["network_calls_made"] == 0
    checklist_rollup = dashboard["live_pilot_handoff_summary"]["pilot_checklist_rollup"]
    assert checklist_rollup["schema"] == "business-card-watchdog.live-pilot-checklist-rollup.v1"
    assert checklist_rollup["operator_required_job_count"] == 0
    assert checklist_rollup["checklist_job_count"] == 0
    assert checklist_rollup["step_count"] == 0
    assert checklist_rollup["live_call_count"] == 0
    execution_packet = dashboard["live_pilot_handoff_summary"]["execution_packet"]
    assert execution_packet["schema"] == "business-card-watchdog.operator-dashboard.live-pilot-execution-packet.v1"
    assert execution_packet["state"] == "no_operator_required"
    assert execution_packet["operator_required_count"] == 0
    assert execution_packet["entries"] == []
    assert execution_packet["next_safe_command"] is None
    assert execution_packet["next_explicit_operator_command"] is None
    assert execution_packet["forbidden_live_or_sink_write_from_dashboard"] is True
    assert execution_packet["writes_attempted"] == 0
    assert execution_packet["network_calls_made"] == 0
    assert dashboard["service_recovery"]["live_pilot_checklist_rollup"]["checklist_job_count"] == 0
    assert dashboard["latest_review_routing_drill"]["schema"] == (
        "business-card-watchdog.latest-review-routing-drill.v1"
    )
    assert dashboard["latest_review_routing_drill"]["state"] == "not_run"
    assert dashboard["latest_review_routing_drill"]["has_drill"] is False
    assert dashboard["latest_review_routing_drill"]["commands"] == {
        "run_fixture_review_routing_drill": "drills review-routing --json"
    }
    assert dashboard["commands"]["review_queue"] == f"reviews list --run-id {run_id} --state all --json"
    assert dashboard["commands"]["next_actions"] == f"actions next --run-id {run_id} --json"
    assert dashboard["commands"]["run_next_safe"] == f"actions run-next --run-id {run_id} --limit 10 --json"
    assert dashboard["commands"]["multi_card_preclassification_drill"] == (
        "drills multi-card-preclassification --json"
    )
    assert dashboard["commands"]["live_pilot_approval_packet"] == (
        f"runs live-pilot-approval-packet {run_id} --json"
    )
    assert dashboard["commands"]["selected_live_target_from_response"] == (
        f"runs selected-live-target-from-response {run_id} --response <operator-response> --json"
    )
    assert dashboard["commands"]["selected_target_approval_boundary"] == (
        f"runs selected-target-approval-boundary {run_id} "
        "--operator <operator> --response <operator-response> --no-write --json"
    )
    assert dashboard["commands"]["selected_target_command_copy_packet"] == (
        f"runs selected-target-command-copy-packet {run_id} "
        "--operator <operator> --response <operator-response> "
        "--acknowledgement <operator-acknowledgement> --json"
    )
    assert dashboard["commands"]["selected_live_target_handoff_from_response"] == (
        f"runs selected-live-target-handoff-from-response {run_id} --response <operator-response> --json"
    )
    assert dashboard["commands"]["lookup_smoke_handoff_from_response"] == (
        f"runs lookup-smoke-handoff-from-response {run_id} --response <operator-response> --json"
    )
    assert dashboard["commands"]["selected_lookup_smoke_execution_packet_from_response"] == (
        f"runs selected-lookup-smoke-execution-packet-from-response {run_id} "
        "--response <operator-response> --json"
    )
    assert dashboard["commands"]["selected_write_pilot_execution_packet_from_response"] == (
        f"runs selected-write-pilot-execution-packet-from-response {run_id} "
        "--response <operator-response> --json"
    )
    assert dashboard["commands"]["selected_readback_pilot_execution_packet_from_response"] == (
        f"runs selected-readback-pilot-execution-packet-from-response {run_id} "
        "--response <operator-response> --json"
    )
    assert dashboard["commands"]["live_pilot_closeout_packet_from_response"] == (
        f"runs live-pilot-closeout-packet-from-response {run_id} "
        "--response <operator-response> --json"
    )
    assert dashboard["commands"]["live_pilot_operator_workflow_packet_from_response"] == (
        f"runs live-pilot-operator-workflow-packet-from-response {run_id} "
        "--response <operator-response> --json"
    )
    assert dashboard["commands"]["live_pilot_operator_rehearsal_from_response"] == (
        f"runs live-pilot-operator-rehearsal-from-response {run_id} --response <operator-response> --json"
    )
    assert dashboard["commands"]["live_pilot_readiness_export_from_response"] == (
        f"runs live-pilot-readiness-export-from-response {run_id} --response <operator-response> --json"
    )
    assert dashboard["commands"]["live_pilot_execution_checklist_from_response"] == (
        f"runs live-pilot-execution-checklist-from-response {run_id} --response <operator-response> --json"
    )
    assert dashboard["commands"]["live_pilot_command_copy_packet_from_response"] == (
        f"runs live-pilot-command-copy-packet-from-response {run_id} "
        "--response <operator-response> --acknowledgement <operator-acknowledgement> --json"
    )
    assert dashboard["commands"]["live_pilot_validate_response"] == (
        f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
    )
    assert dashboard["api_routes"]["next_actions"] == f"GET /actions/next?run_id={run_id}&limit=20"
    assert dashboard["api_routes"]["multi_card_preclassification_drill"] == (
        "POST /drills/multi-card-preclassification"
    )
    assert dashboard["api_routes"]["live_pilot_validate_response"] == (
        f"POST /runs/{run_id}/live-pilot-operator-response-validation"
    )
    assert dashboard["api_routes"]["selected_live_target_handoff_from_response"] == (
        f"POST /runs/{run_id}/selected-live-target-handoff-from-response"
    )
    assert dashboard["api_routes"]["selected_target_approval_boundary"] == (
        f"POST /runs/{run_id}/selected-target-approval-boundary"
    )
    assert dashboard["api_routes"]["selected_target_command_copy_packet"] == (
        f"POST /runs/{run_id}/selected-target-command-copy-packet"
    )
    assert dashboard["api_routes"]["lookup_smoke_handoff_from_response"] == (
        f"POST /runs/{run_id}/lookup-smoke-handoff-from-response"
    )
    assert dashboard["api_routes"]["selected_lookup_smoke_execution_packet_from_response"] == (
        f"POST /runs/{run_id}/selected-lookup-smoke-execution-packet-from-response"
    )
    assert dashboard["api_routes"]["selected_write_pilot_execution_packet_from_response"] == (
        f"POST /runs/{run_id}/selected-write-pilot-execution-packet-from-response"
    )
    assert dashboard["api_routes"]["selected_readback_pilot_execution_packet_from_response"] == (
        f"POST /runs/{run_id}/selected-readback-pilot-execution-packet-from-response"
    )
    assert dashboard["api_routes"]["live_pilot_closeout_packet_from_response"] == (
        f"POST /runs/{run_id}/live-pilot-closeout-packet-from-response"
    )
    assert dashboard["api_routes"]["live_pilot_operator_workflow_packet_from_response"] == (
        f"POST /runs/{run_id}/live-pilot-operator-workflow-packet-from-response"
    )
    assert dashboard["api_routes"]["live_pilot_operator_rehearsal_from_response"] == (
        f"POST /runs/{run_id}/live-pilot-operator-rehearsal-from-response"
    )
    assert dashboard["api_routes"]["live_pilot_readiness_export_from_response"] == (
        f"POST /runs/{run_id}/live-pilot-readiness-export-from-response"
    )
    assert dashboard["api_routes"]["live_pilot_execution_checklist_from_response"] == (
        f"POST /runs/{run_id}/live-pilot-execution-checklist-from-response"
    )
    assert dashboard["api_routes"]["live_pilot_command_copy_packet_from_response"] == (
        f"POST /runs/{run_id}/live-pilot-command-copy-packet-from-response"
    )
    assert dashboard["mcp_tools"]["next_actions"] == {
        "tool": "business_card_watchdog_next_actions",
        "arguments": {"run_id": run_id, "limit": 20},
    }
    assert dashboard["mcp_tools"]["multi_card_preclassification_drill"] == {
        "tool": "business_card_watchdog_multi_card_preclassification_drill",
        "arguments": {},
    }
    assert dashboard["mcp_tools"]["live_pilot_handoff"] == {
        "tool": "business_card_watchdog_live_pilot_handoff",
        "arguments": {"run_id": run_id, "write": False},
    }
    assert dashboard["mcp_tools"]["live_pilot_approval_packet"] == {
        "tool": "business_card_watchdog_live_pilot_approval_packet",
        "arguments": {"run_id": run_id},
    }
    assert dashboard["mcp_tools"]["selected_live_target_from_response"] == {
        "tool": "business_card_watchdog_selected_live_target_from_response",
        "arguments": {"run_id": run_id, "response": "<operator-response>"},
    }
    assert dashboard["mcp_tools"]["selected_target_approval_boundary"] == {
        "tool": "business_card_watchdog_selected_target_approval_boundary",
        "arguments": {
            "run_id": run_id,
            "operator": "<operator>",
            "response": "<operator-response>",
            "write": False,
        },
    }
    assert dashboard["mcp_tools"]["selected_target_command_copy_packet"] == {
        "tool": "business_card_watchdog_selected_target_command_copy_packet",
        "arguments": {
            "run_id": run_id,
            "operator": "<operator>",
            "response": "<operator-response>",
            "acknowledgement": "<operator-acknowledgement>",
        },
    }
    assert dashboard["mcp_tools"]["selected_live_target_handoff_from_response"] == {
        "tool": "business_card_watchdog_selected_live_target_handoff_from_response",
        "arguments": {"run_id": run_id, "response": "<operator-response>", "write_audit": False},
    }
    assert dashboard["mcp_tools"]["lookup_smoke_handoff_from_response"] == {
        "tool": "business_card_watchdog_lookup_smoke_handoff_from_response",
        "arguments": {"run_id": run_id, "response": "<operator-response>", "write_handoff": False},
    }
    assert dashboard["mcp_tools"]["selected_lookup_smoke_execution_packet_from_response"] == {
        "tool": "business_card_watchdog_selected_lookup_smoke_execution_packet_from_response",
        "arguments": {"run_id": run_id, "response": "<operator-response>", "execute_selected_lookup_smoke": False},
    }
    assert dashboard["mcp_tools"]["selected_write_pilot_execution_packet_from_response"] == {
        "tool": "business_card_watchdog_selected_write_pilot_execution_packet_from_response",
        "arguments": {"run_id": run_id, "response": "<operator-response>", "execute_write_pilot": False},
    }
    assert dashboard["mcp_tools"]["selected_readback_pilot_execution_packet_from_response"] == {
        "tool": "business_card_watchdog_selected_readback_pilot_execution_packet_from_response",
        "arguments": {"run_id": run_id, "response": "<operator-response>", "execute_readback_pilot": False},
    }
    assert dashboard["mcp_tools"]["live_pilot_closeout_packet_from_response"] == {
        "tool": "business_card_watchdog_live_pilot_closeout_packet_from_response",
        "arguments": {"run_id": run_id, "response": "<operator-response>", "write_closeout": False},
    }
    assert dashboard["mcp_tools"]["live_pilot_operator_workflow_packet_from_response"] == {
        "tool": "business_card_watchdog_live_pilot_operator_workflow_packet_from_response",
        "arguments": {"run_id": run_id, "response": "<operator-response>"},
    }
    assert dashboard["mcp_tools"]["live_pilot_operator_rehearsal_from_response"] == {
        "tool": "business_card_watchdog_live_pilot_operator_rehearsal_from_response",
        "arguments": {"run_id": run_id, "response": "<operator-response>"},
    }
    assert dashboard["mcp_tools"]["live_pilot_readiness_export_from_response"] == {
        "tool": "business_card_watchdog_live_pilot_readiness_export_from_response",
        "arguments": {"run_id": run_id, "response": "<operator-response>", "write": True},
    }
    assert dashboard["mcp_tools"]["live_pilot_execution_checklist_from_response"] == {
        "tool": "business_card_watchdog_live_pilot_execution_checklist_from_response",
        "arguments": {"run_id": run_id, "response": "<operator-response>"},
    }
    assert dashboard["mcp_tools"]["live_pilot_command_copy_packet_from_response"] == {
        "tool": "business_card_watchdog_live_pilot_command_copy_packet_from_response",
        "arguments": {
            "run_id": run_id,
            "response": "<operator-response>",
            "acknowledgement": "<operator-acknowledgement>",
        },
    }
    assert dashboard["mcp_tools"]["review_routing_drill"] == {
        "tool": "business_card_watchdog_review_routing_drill",
        "arguments": {},
    }
    assert dashboard["mcp_tools"]["live_pilot_rehearsal_drill"] == {
        "tool": "business_card_watchdog_live_pilot_rehearsal_drill",
        "arguments": {},
    }
    assert dashboard["mcp_tools"]["live_pilot_validate_response"] == {
        "tool": "business_card_watchdog_live_pilot_operator_response_validation",
        "arguments": {"run_id": run_id, "response": "<operator-response>"},
    }
    assert dashboard["commands"]["multi_card_preclassification_drill"] == (
        "drills multi-card-preclassification --json"
    )
    assert dashboard["commands"]["review_routing_drill"] == "drills review-routing --json"
    assert dashboard["commands"]["live_pilot_rehearsal_drill"] == "drills live-pilot-rehearsal --json"
    assert dashboard["api_routes"]["multi_card_preclassification_drill"] == (
        "POST /drills/multi-card-preclassification"
    )
    assert dashboard["api_routes"]["review_routing_drill"] == "POST /drills/review-routing"
    assert dashboard["api_routes"]["live_pilot_rehearsal_drill"] == "POST /drills/live-pilot-rehearsal"
    assert dashboard["commands"]["live_pilot_status"] == f"runs live-pilot-status {run_id} --no-write --json"
    assert dashboard["safe_next_actions"][0]["action"] == "inspect_runtime_readiness"
    assert dashboard["safe_next_actions"][3] == {
        "action": "inspect_live_pilot_status",
        "command": f"runs live-pilot-status {run_id} --no-write --json",
        "safe_to_auto_continue": True,
        "requires_explicit_operator_action": False,
    }
    assert dashboard["safe_next_actions"][4] == {
        "action": "inspect_live_pilot_handoff",
        "command": f"runs live-pilot-handoff {run_id} --no-write --json",
        "safe_to_auto_continue": True,
        "requires_explicit_operator_action": False,
    }
    assert dashboard["safe_next_actions"][5] == {
        "action": "run_fixture_review_routing_drill",
        "command": "drills review-routing --json",
        "safe_to_auto_continue": True,
        "requires_explicit_operator_action": False,
    }
    assert dashboard["writes_attempted"] == 0
    assert dashboard["network_calls_made"] == 0


def test_service_dashboard_and_recovery_report_latest_review_routing_drill(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
    )
    service = BusinessCardService(config)
    drill = service.review_routing_drill()

    dashboard = service.operator_dashboard(run_id=drill["run_id"])
    recovery = service.service_recovery_report(run_id=drill["run_id"])

    for payload in (dashboard, recovery):
        latest = payload["latest_review_routing_drill"]
        assert latest["schema"] == "business-card-watchdog.latest-review-routing-drill.v1"
        assert latest["state"] == "passed"
        assert latest["has_drill"] is True
        assert latest["selected_run_matches"] is True
        assert latest["run_id"] == drill["run_id"]
        assert latest["job_id"] == drill["job_id"]
        assert latest["agent_readback_state"] == "passed"
        assert latest["next_manual_boundary"] == "decide_sink_apply"
        assert latest["artifact_check_count"] == 7
        assert latest["artifact_check_passed_count"] == 7
        assert latest["safe_action_counts"] == {"executed": 7, "skipped": 1}
        assert latest["private_sources_used"] is False
        assert latest["public_web_search_used"] is False
        assert latest["paid_enrichment_used"] is False
        assert latest["live_sink_calls_made"] is False
        assert latest["writes_attempted"] == 0
        assert latest["network_calls_made"] == 0


def test_service_sink_readiness_reports_apply_policy(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(
            google_contacts=True,
            odoo=True,
            dry_run=False,
            google_contacts_apply_enabled=False,
            odoo_apply_enabled=True,
        ),
    )

    readiness = BusinessCardService(config).sink_readiness()

    by_sink = {sink["sink"]: sink for sink in readiness["sinks"]}
    assert readiness["dry_run"] is False
    assert "disabled" in by_sink["google_contacts"]["reason"]
    assert by_sink["odoo"]["details"]["config_key"] == "sink.odollo_tenant"


def test_service_sink_readiness_reports_configured_profile_and_tenant(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(
            google_contacts=True,
            google_contacts_profile="codex",
            odoo=True,
            odollo_tenant="saber",
            dry_run=False,
            google_contacts_apply_enabled=True,
            odoo_apply_enabled=True,
        ),
    )

    readiness = BusinessCardService(config).sink_readiness()

    by_sink = {sink["sink"]: sink for sink in readiness["sinks"]}
    assert by_sink["google_contacts"]["details"].get("profile") == "codex"
    assert by_sink["odoo"]["details"]["tenant"] == "saber"
    assert "Odollo" in by_sink["odoo"]["reason"]


def test_service_watch_reset_returns_runtime_path(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    service = BusinessCardService(config)
    config.watch_dir.mkdir(parents=True)
    (config.watch_dir / "seen-files.jsonl").write_text('{"key": "x"}\n', encoding="utf-8")

    payload = service.watch_reset()

    assert payload["schema"] == "business-card-watchdog.watch-reset.v1"
    assert payload["reset"] is True
    assert payload["watch_dir"] == str(config.watch_dir)
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    assert payload["private_sources_used"] is False
    assert payload["commands"]["watch_dry_run"] == "watch-dry-run --json"
    assert "seen-files.jsonl" in payload["reset_files"]
    assert "Run watch-dry-run before polling private SyncThing inputs after a reset." in (
        payload["explicit_stop_conditions"]
    )
    assert not (config.watch_dir / "seen-files.jsonl").exists()


def test_service_review_routing_drill_exercises_safe_fixture_route(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
    )

    payload = BusinessCardService(config).review_routing_drill()
    run_id = payload["run_id"]
    job_id = payload["job_id"]
    artifact_dir = config.runs_dir / run_id / "artifacts" / job_id

    assert payload["schema"] == "business-card-watchdog.review-routing-drill.v1"
    assert payload["private_sources_used"] is False
    assert payload["public_web_search_used"] is False
    assert payload["paid_enrichment_used"] is False
    assert payload["live_sink_calls_made"] is False
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    assert payload["configured_fixture_sinks"] == ["google_contacts", "odoo"]
    assert payload["review"]["final_state"] == "ready_to_route"
    assert payload["agent_loop_readback"]["schema"] == (
        "business-card-watchdog.review-routing-drill-agent-readback.v1"
    )
    assert payload["agent_loop_readback"]["state"] == "passed"
    assert payload["agent_loop_readback"]["next_manual_boundary"] == "decide_sink_apply"
    assert payload["agent_loop_readback"]["expected_manual_boundary"] == "decide_sink_apply"
    assert payload["agent_loop_readback"]["safe_action_counts"] == {"executed": 7, "skipped": 1}
    assert all(check["exists"] for check in payload["agent_loop_readback"]["artifact_checks"])
    assert payload["agent_loop_readback"]["writes_attempted"] == 0
    assert payload["agent_loop_readback"]["network_calls_made"] == 0
    assert payload["safe_actions"]["executed_actions"] == [
        "plan_sink_lookup",
        "prepare_sink_lookup_adapter",
        "record_sink_lookup_result",
        "assess_downstream_duplicates",
        "plan_sinks",
        "prepare_sink_write_adapter",
        "preflight_sink_apply",
    ]
    assert payload["safe_actions"]["skipped_actions"] == ["decide_sink_apply"]
    assert payload["next_actions"][0]["action"] == "decide_sink_apply"
    assert set(payload["route_artifact_kinds"]) >= {
        "sink_lookup_plan",
        "sink_adapter_request_lookup",
        "sink_lookup_result",
        "downstream_duplicate_assessment",
        "sink_plan",
        "sink_adapter_request_write",
        "sink_apply_preflight",
    }
    assert Path(payload["drill_path"]).exists()
    assert Path(payload["review_bundle_path"]).exists()
    assert Path(payload["review_workbook_path"]).exists()
    assert (artifact_dir / "reviewed_contact.json").exists()
    assert not (artifact_dir / "selected_live_target.json").exists()
    assert "Do not run public-web search, paid enrichment, live lookup" in payload["explicit_stop_conditions"][2]


def test_service_multi_card_preclassification_drill_records_candidate_boxes(tmp_path: Path) -> None:
    pytest = __import__("pytest")
    pytest.importorskip("cv2")
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
    )

    payload = BusinessCardService(config).multi_card_preclassification_drill()
    run_id = payload["run_id"]

    assert payload["schema"] == "business-card-watchdog.multi-card-preclassification-drill.v1"
    assert payload["state"] == "passed"
    assert payload["expected_card_count"] == 3
    assert payload["detected_card_like_count"] >= 3
    assert len(payload["candidate_boxes"]) >= 3
    assert payload["preclassification"]["decision"] == "likely_business_card"
    assert all(payload["assertions"].values())
    assert payload["private_sources_used"] is False
    assert payload["public_web_search_used"] is False
    assert payload["paid_enrichment_used"] is False
    assert payload["live_sink_calls_made"] is False
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    assert Path(payload["fixture_image_path"]).exists()
    assert Path(payload["drill_path"]).exists()
    assert Path(payload["preclassification_path"]).exists()
    assert (config.runs_dir / run_id / "multi_card_preclassification_drill.json").exists()
    artifacts = [json.loads(line) for line in (config.runs_dir / run_id / "artifacts.jsonl").read_text().splitlines()]
    assert {artifact["kind"] for artifact in artifacts} >= {
        "multi_card_preclassification",
        "multi_card_preclassification_drill",
    }


def test_service_watch_dry_run_selection_drill_exports_sample_output(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
    )

    payload = BusinessCardService(config).watch_dry_run_selection_drill()
    run_id = payload["run_id"]

    assert payload["schema"] == "business-card-watchdog.watch-dry-run-selection-drill.v1"
    assert payload["state"] == "passed"
    assert payload["private_sources_used"] is False
    assert payload["files_processed"] == 0
    assert payload["ocr_attempted"] == 0
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    assert payload["command_copy_ready"] is True
    assert payload["command_copy_text"] == "watch --once --dry-run"
    assert payload["packets"]["preflight"]["counts"]["backlog"] == 1
    assert payload["packets"]["handoff"]["entries"][0]["configured_ref_display"] == "<redacted-path>"
    assert payload["sample_outputs"]["raw_operator_response_stored"] is False
    assert payload["sample_outputs"]["raw_acknowledgement_stored"] is False
    sample_output_path = Path(payload["sample_outputs"]["watch_dry_run_selection_markdown_path"])
    assert sample_output_path.exists()
    sample_output = sample_output_path.read_text(encoding="utf-8")
    assert "# Watch Dry-Run Selection Sample Output" in sample_output
    assert "Command copy packet: `ready_for_operator_copy`" in sample_output
    assert "private dry run approved" not in sample_output
    artifacts = [json.loads(line) for line in (config.runs_dir / run_id / "artifacts.jsonl").read_text().splitlines()]
    assert {artifact["kind"] for artifact in artifacts} >= {
        "watch_dry_run_selection_sample_output",
        "watch_dry_run_selection_drill",
    }


def test_service_watch_dry_run_execution_drill_runs_real_dry_pipeline(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
    )

    payload = BusinessCardService(config).watch_dry_run_execution_drill()

    assert payload["schema"] == "business-card-watchdog.watch-dry-run-execution-drill.v1"
    assert payload["state"] == "passed"
    assert payload["private_sources_used"] is False
    assert payload["files_processed"] == 1
    assert payload["ocr_attempted"] == 1
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    assert payload["first_scan_processed"] == payload["synthetic_images"]
    assert payload["second_scan_processed"] == []
    assert payload["processed_run"]["state"] == "completed"
    assert payload["processed_run"]["dry_run"] is True
    assert payload["processed_run"]["job_count"] == 1
    assert "contact_candidate" in payload["processed_run"]["artifact_kinds"]
    assert "sink_payloads" in payload["processed_run"]["artifact_kinds"]
    assert "sink_decision_dry_run" in payload["processed_run"]["event_types"]
    sample_output_path = Path(payload["sample_outputs"]["watch_dry_run_execution_markdown_path"])
    assert sample_output_path.exists()
    sample_output = sample_output_path.read_text(encoding="utf-8")
    assert "# Watch Dry-Run Execution Sample Output" in sample_output
    assert "Synthetic fixture only" in sample_output


def test_service_dry_run_closeout_audits_completed_dry_run(tmp_path: Path, monkeypatch) -> None:
    source_dir = tmp_path / "cards"
    write_synthetic_image(source_dir / "card.png")
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        prefilter=PrefilterConfig(enabled=False),
        sink=SinkConfig(google_contacts=True, odoo=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts", "odoo"]}],
    )
    orchestrator = BatchOrchestrator(config)
    monkeypatch.setattr(orchestrator, "adapter", SyntheticSkillAdapter())
    run_dir = orchestrator.process_source(str(source_dir), dry_run=True, workers=1)

    payload = BusinessCardService(config).dry_run_closeout(run_dir.name, write=True)

    assert payload["schema"] == "business-card-watchdog.dry-run-closeout.v1"
    assert payload["state"] == "ready_for_review_and_routing"
    assert payload["run_state"] == "completed"
    assert payload["dry_run"] is True
    assert payload["job_count"] == 1
    assert payload["files_processed"] == 1
    assert payload["ocr_artifact_count"] == 1
    assert payload["contact_candidate_count"] == 1
    assert payload["sink_payload_count"] == 1
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    assert payload["live_sink_calls_made"] is False
    assert payload["blocked_reasons"] == []
    assert payload["runtime_artifact_written"] is True
    assert Path(payload["closeout_path"]).exists()
    assert payload["commands"]["dry_run_closeout"] == f"runs dry-run-closeout {run_dir.name} --json"
    assert payload["safe_next_actions"][0]["action"] == "inspect_run_summary"
    assert "Do not run public-web search or paid enrichment from this closeout." in (
        payload["explicit_stop_conditions"]
    )

    recorded = BusinessCardService(config).get_run(run_dir.name)
    assert any(artifact["kind"] == "dry_run_closeout" for artifact in recorded["artifacts"])
    events = (run_dir / "events.jsonl").read_text(encoding="utf-8")
    assert "dry_run_closeout_created" in events


def test_service_dry_run_review_handoff_summarizes_safe_next_steps(tmp_path: Path, monkeypatch) -> None:
    source_dir = tmp_path / "cards"
    write_synthetic_image(source_dir / "card.png")
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        prefilter=PrefilterConfig(enabled=False),
        sink=SinkConfig(google_contacts=True, odoo=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts", "odoo"]}],
    )
    orchestrator = BatchOrchestrator(config)
    monkeypatch.setattr(orchestrator, "adapter", SyntheticSkillAdapter())
    run_dir = orchestrator.process_source(str(source_dir), dry_run=True, workers=1)

    payload = BusinessCardService(config).dry_run_review_handoff(run_dir.name, write=True)

    assert payload["schema"] == "business-card-watchdog.dry-run-review-handoff.v1"
    assert payload["state"] == "ready_for_safe_agent_loop"
    assert payload["closeout_state"] == "ready_for_review_and_routing"
    assert payload["job_count"] == 1
    assert payload["ready_to_route_count"] == 1
    assert payload["safe_auto_action_count"] == 1
    assert payload["explicit_operator_action_count"] == 0
    assert payload["next_action_counts"] == {"plan_sink_lookup": 1}
    assert payload["safe_auto_actions"][0]["action"] == "plan_sink_lookup"
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    assert payload["live_sink_calls_made"] is False
    assert payload["runtime_artifact_written"] is True
    assert Path(payload["handoff_path"]).exists()
    assert payload["commands"]["dry_run_review_handoff"] == f"runs dry-run-review-handoff {run_dir.name} --json"
    assert payload["commands"]["live_pilot_status"].endswith("--no-write --json")
    assert "Do not execute live lookup, write, or readback from this handoff." in (
        payload["explicit_stop_conditions"]
    )

    recorded = BusinessCardService(config).get_run(run_dir.name)
    assert any(artifact["kind"] == "dry_run_review_handoff" for artifact in recorded["artifacts"])
    events = (run_dir / "events.jsonl").read_text(encoding="utf-8")
    assert "dry_run_review_handoff_created" in events


def test_service_dry_run_safe_loop_executes_bounded_safe_actions(tmp_path: Path, monkeypatch) -> None:
    source_dir = tmp_path / "cards"
    write_synthetic_image(source_dir / "card.png")
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        prefilter=PrefilterConfig(enabled=False),
        sink=SinkConfig(google_contacts=True, odoo=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts", "odoo"]}],
    )
    orchestrator = BatchOrchestrator(config)
    monkeypatch.setattr(orchestrator, "adapter", SyntheticSkillAdapter())
    run_dir = orchestrator.process_source(str(source_dir), dry_run=True, workers=1)

    payload = BusinessCardService(config).dry_run_safe_loop(run_dir.name, limit=3, write=True)

    assert payload["schema"] == "business-card-watchdog.dry-run-safe-loop.v1"
    assert payload["state"] == "safe_loop_executed"
    assert payload["before_handoff_state"] == "ready_for_safe_agent_loop"
    assert payload["executed_count"] == 3
    assert [action["action"] for action in payload["executed"]] == [
        "plan_sink_lookup",
        "prepare_sink_lookup_adapter",
        "record_sink_lookup_result",
    ]
    assert payload["before_next_action_counts"] == {"plan_sink_lookup": 1}
    assert payload["after_next_action_counts"] == {"assess_downstream_duplicates": 1}
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    assert payload["live_sink_calls_made"] is False
    assert payload["runtime_artifact_written"] is True
    assert Path(payload["safe_loop_path"]).exists()
    assert payload["safe_inspection_commands"]["dry_run_safe_loop"] == (
        f"runs dry-run-safe-loop {run_dir.name} --limit 3 --json"
    )
    assert "Only actions in the host-owned safe auto action allowlist may execute." in (
        payload["explicit_stop_conditions"]
    )

    recorded = BusinessCardService(config).get_run(run_dir.name)
    artifact_kinds = {artifact["kind"] for artifact in recorded["artifacts"]}
    assert {"sink_lookup_plan", "sink_adapter_request_lookup", "sink_lookup_result", "dry_run_safe_loop"} <= (
        artifact_kinds
    )
    events = (run_dir / "events.jsonl").read_text(encoding="utf-8")
    assert "dry_run_safe_loop_created" in events


def test_service_review_route_readiness_summarizes_review_and_route_state(tmp_path: Path, monkeypatch) -> None:
    source_dir = tmp_path / "cards"
    write_synthetic_image(source_dir / "card.png")
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        prefilter=PrefilterConfig(enabled=False),
        sink=SinkConfig(google_contacts=True, odoo=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts", "odoo"]}],
    )
    orchestrator = BatchOrchestrator(config)
    monkeypatch.setattr(orchestrator, "adapter", SyntheticSkillAdapter())
    run_dir = orchestrator.process_source(str(source_dir), dry_run=True, workers=1)

    payload = BusinessCardService(config).review_route_readiness(run_dir.name, write=True)

    assert payload["schema"] == "business-card-watchdog.review-route-readiness.v1"
    assert payload["state"] == "ready_for_safe_agent_loop"
    assert payload["closeout_state"] == "ready_for_review_and_routing"
    assert payload["handoff_state"] == "ready_for_safe_agent_loop"
    assert payload["counts"]["ready_to_route"] == 1
    assert payload["counts"]["route_ready"] == 1
    assert payload["counts"]["safe_auto"] == 1
    assert payload["counts"]["blocked"] == 0
    assert payload["next_action_counts"] == {"plan_sink_lookup": 1}
    assert payload["rows"][0]["duplicate_state"] == "no_match"
    assert payload["rows"][0]["enrichment_state"] == "not_requested"
    assert payload["rows"][0]["route_ready"] is True
    assert payload["rows"][0]["next_action"]["action"] == "plan_sink_lookup"
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    assert payload["live_sink_calls_made"] is False
    assert payload["runtime_artifact_written"] is True
    assert Path(payload["readiness_path"]).exists()
    assert payload["commands"]["review_route_readiness"] == f"runs review-route-readiness {run_dir.name} --json"
    assert "Do not execute live lookup, write, or readback from this report." in (
        payload["explicit_stop_conditions"]
    )

    recorded = BusinessCardService(config).get_run(run_dir.name)
    assert any(artifact["kind"] == "review_route_readiness" for artifact in recorded["artifacts"])
    events = (run_dir / "events.jsonl").read_text(encoding="utf-8")
    assert "review_route_readiness_created" in events


def test_service_lookup_selection_packet_selects_route_ready_job_without_live_calls(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source_dir = tmp_path / "cards"
    write_synthetic_image(source_dir / "card.png")
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        prefilter=PrefilterConfig(enabled=False),
        sink=SinkConfig(google_contacts=True, dry_run=True),
    )
    orchestrator = BatchOrchestrator(config)
    monkeypatch.setattr(orchestrator, "adapter", SyntheticSkillAdapter())
    run_dir = orchestrator.process_source(str(source_dir), dry_run=True, workers=1)

    payload = BusinessCardService(config).lookup_selection_packet(
        run_dir.name,
        operator="tester",
        sink="google_contacts",
        write=True,
    )

    assert payload["schema"] == "business-card-watchdog.lookup-selection-packet.v1"
    assert payload["state"] == "packet_blocked"
    assert payload["route_ready_count"] == 1
    assert payload["packet_candidate_count"] == 1
    assert payload["selected"]["job_id"] == payload["selected_packet"]["job_id"]
    assert payload["selected"]["sink"] == "google_contacts"
    assert payload["selected_packet"]["schema"] == "business-card-watchdog.live-selection-packet.v1"
    assert payload["selected_packet"]["approval_state"] == "pending_operator_approval"
    assert "lookup:reviewed_contact_exists" in payload["blocked_reasons"]
    assert payload["creates_selected_live_target"] is False
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    assert payload["live_sink_calls_made"] is False
    assert payload["runtime_artifact_written"] is True
    assert Path(payload["packet_path"]).exists()
    assert payload["commands"]["lookup_selection_packet"] == (
        f"runs lookup-selection-packet {run_dir.name} --operator tester --sink google_contacts --json"
    )
    assert payload["commands"]["validate_operator_response_prefilled"].startswith(
        f"runs live-pilot-validate-response {run_dir.name} --response"
    )
    assert "This packet does not create selected_live_target.json." in payload["explicit_stop_conditions"]

    recorded = BusinessCardService(config).get_run(run_dir.name)
    assert any(artifact["kind"] == "lookup_selection_packet" for artifact in recorded["artifacts"])
    events = (run_dir / "events.jsonl").read_text(encoding="utf-8")
    assert "lookup_selection_packet_created" in events


def test_service_close_lookup_prerequisites_executes_only_lookup_safe_actions(
    tmp_path: Path,
) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
    )

    payload = service.close_lookup_prerequisites(
        run_id,
        operator="tester",
        sink="google_contacts",
        limit=4,
        write=True,
    )

    assert payload["schema"] == "business-card-watchdog.close-lookup-prerequisites.v1"
    assert payload["state"] == "lookup_prerequisites_advanced"
    assert [row["action"] for row in payload["executed"]] == [
        "plan_sink_lookup",
        "prepare_sink_lookup_adapter",
        "record_sink_lookup_result",
        "assess_downstream_duplicates",
    ]
    assert payload["executed_count"] == 4
    assert payload["after_packet"]["selected_packet"]["readiness"]["lookup"]["missing_requirements"] == [
        "live_lookup_readiness_ready"
    ]
    assert payload["creates_selected_live_target"] is False
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    assert payload["live_sink_calls_made"] is False
    assert payload["runtime_artifact_written"] is True
    assert Path(payload["closeout_path"]).exists()
    artifact_kinds = {artifact["kind"] for artifact in service.get_run(run_id)["artifacts"]}
    assert {
        "reviewed_contact",
        "sink_lookup_plan",
        "sink_adapter_request_lookup",
        "sink_lookup_result",
        "downstream_duplicate_assessment",
        "close_lookup_prerequisites",
    } <= artifact_kinds
    assert "selected_live_target" not in artifact_kinds
    events = (config.runs_dir / run_id / "events.jsonl").read_text(encoding="utf-8")
    assert "close_lookup_prerequisites_created" in events


def test_service_selected_target_approval_boundary_previews_explicit_selection(
    tmp_path: Path,
) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
    )
    service.close_lookup_prerequisites(
        run_id,
        operator="tester",
        sink="google_contacts",
        limit=4,
        write=True,
    )

    awaiting = service.selected_target_approval_boundary(
        run_id,
        operator="tester",
        sink="google_contacts",
        job_id=job_id,
        write=False,
    )

    assert awaiting["schema"] == "business-card-watchdog.selected-target-approval-boundary.v1"
    assert awaiting["state"] == "awaiting_operator_response"
    assert awaiting["selected_entry"]["operator"] == "<operator>"
    assert awaiting["operator_response_template"].startswith(f"run_id={run_id} job_id={job_id}")
    assert awaiting["would_create_selected_live_target"] is False
    assert awaiting["creates_selected_live_target"] is False
    assert awaiting["writes_attempted"] == 0
    assert awaiting["network_calls_made"] == 0
    assert awaiting["runtime_artifact_written"] is False

    response = (
        f"run_id={run_id} job_id={job_id} sink=google_contacts "
        "operator=tester scope=lookup safety_confirmation=fixture contact is safe for google contacts test profile"
    )
    ready = service.selected_target_approval_boundary(
        run_id,
        operator="tester",
        sink="google_contacts",
        job_id=job_id,
        response=response,
        write=True,
    )

    assert ready["state"] == "ready_for_explicit_selected_target_creation"
    assert ready["blocked_reasons"] == []
    assert ready["validation"]["state"] == "ready_to_select_live_target"
    assert ready["preflight"]["state"] == "ready_to_create_selected_target"
    assert ready["preview"]["state"] == "ready"
    assert ready["commands"]["select_target"].startswith(f"sinks select-live-target {job_id}")
    assert ready["would_create_selected_live_target"] is True
    assert ready["creates_selected_live_target"] is False
    assert ready["writes_attempted"] == 0
    assert ready["network_calls_made"] == 0
    assert ready["runtime_artifact_written"] is True
    assert Path(ready["boundary_path"]).exists()
    artifact_kinds = {artifact["kind"] for artifact in service.get_run(run_id)["artifacts"]}
    assert "selected_target_approval_boundary" in artifact_kinds
    assert "selected_live_target" not in artifact_kinds


def test_service_selected_target_command_copy_packet_requires_acknowledgement(
    tmp_path: Path,
) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
    )
    service.close_lookup_prerequisites(
        run_id,
        operator="tester",
        sink="google_contacts",
        limit=4,
        write=True,
    )
    response = (
        f"run_id={run_id} job_id={job_id} sink=google_contacts "
        "operator=tester scope=lookup safety_confirmation=fixture contact is safe for google contacts test profile"
    )

    blocked = service.selected_target_command_copy_packet(
        run_id,
        operator="tester",
        sink="google_contacts",
        job_id=job_id,
        response=response,
    )

    assert blocked["schema"] == "business-card-watchdog.selected-target-command-copy-packet.v1"
    assert blocked["state"] == "blocked"
    assert blocked["boundary_state"] == "ready_for_explicit_selected_target_creation"
    assert blocked["acknowledgement_required"] is True
    assert blocked["acknowledgement_ok"] is False
    assert blocked["command_copy_text"] is None
    assert any("operator acknowledgement is required" in reason for reason in blocked["blocked_reasons"])
    assert blocked["creates_selected_live_target"] is False
    assert blocked["writes_attempted"] == 0
    assert blocked["network_calls_made"] == 0

    ready = service.selected_target_command_copy_packet(
        run_id,
        operator="tester",
        sink="google_contacts",
        job_id=job_id,
        response=response,
        acknowledgement=f"acknowledge run_id={run_id} job_id={job_id} sink=google_contacts operator=tester copy command",
    )

    assert ready["state"] == "ready_for_operator_copy"
    assert ready["acknowledgement_ok"] is True
    assert ready["blocked_reasons"] == []
    assert ready["command_copy_text"].startswith(f"runs selected-live-target-from-response {run_id}")
    assert "--write-selected-target" in ready["command_copy_text"]
    assert ready["creates_selected_live_target"] is False
    assert ready["writes_attempted"] == 0
    assert ready["network_calls_made"] == 0
    assert ready["acknowledgement_redacted"]["raw_acknowledgement_stored"] is False
    artifact_kinds = {artifact["kind"] for artifact in service.get_run(run_id)["artifacts"]}
    assert "selected_live_target" not in artifact_kinds


def test_service_contact_route_selection_packets_use_projected_gws_route(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True, google_contacts_profile="ecochran76"),
    )
    service, run_id, job_id, contact_id = project_gws_route_contact(config)

    awaiting = service.contact_route_selection_approval_boundary(
        contact_id,
        operator="tester",
        sink="google_contacts",
        write=False,
    )

    assert awaiting["schema"] == "business-card-watchdog.contact-route-selection-approval-boundary.v1"
    assert awaiting["state"] == "awaiting_operator_response"
    assert awaiting["run_id"] == run_id
    assert awaiting["job_id"] == job_id
    assert awaiting["sink"] == "google_contacts"
    assert awaiting["selection"]["selected"]["selected_target_profile"] == "ecochran76"
    assert awaiting["operator_response_template"].startswith(f"run_id={run_id} job_id={job_id}")
    assert awaiting["creates_selected_live_target"] is False
    assert awaiting["runtime_artifact_written"] is False

    response = (
        f"run_id={run_id} job_id={job_id} sink=google_contacts "
        "operator=tester scope=lookup safety_confirmation=fixture contact is safe for google contacts test profile"
    )
    ready = service.contact_route_selection_approval_boundary(
        contact_id,
        operator="tester",
        sink="google_contacts",
        response=response,
        write=True,
    )

    assert ready["state"] == "ready_for_explicit_selected_target_creation"
    assert ready["blocked_reasons"] == []
    assert ready["boundary_state"] == "ready_for_explicit_selected_target_creation"
    assert ready["would_create_selected_live_target"] is True
    assert ready["creates_selected_live_target"] is False
    assert ready["writes_attempted"] == 0
    assert ready["network_calls_made"] == 0
    assert ready["runtime_artifact_written"] is True
    assert Path(ready["boundary_path"]).exists()

    blocked_copy = service.contact_route_selection_command_copy_packet(
        contact_id,
        operator="tester",
        sink="google_contacts",
        response=response,
    )
    assert blocked_copy["state"] == "blocked"
    assert blocked_copy["approval_boundary_state"] == "ready_for_explicit_selected_target_creation"
    assert blocked_copy["command_copy_text"] is None
    assert any("operator acknowledgement is required" in reason for reason in blocked_copy["blocked_reasons"])

    ready_copy = service.contact_route_selection_command_copy_packet(
        contact_id,
        operator="tester",
        sink="google_contacts",
        response=response,
        acknowledgement=f"acknowledge run_id={run_id} job_id={job_id} sink=google_contacts operator=tester copy command",
    )
    assert ready_copy["state"] == "ready_for_operator_copy"
    assert ready_copy["command_copy_text"].startswith(f"runs selected-live-target-from-response {run_id}")
    assert "--write-selected-target" in ready_copy["command_copy_text"]
    assert ready_copy["creates_selected_live_target"] is False
    artifact_kinds = {artifact["kind"] for artifact in service.get_run(run_id)["artifacts"]}
    assert "contact_route_selection_approval_boundary" in artifact_kinds
    assert "selected_live_target" not in artifact_kinds


def test_service_contact_route_selection_blocks_gws_profile_mismatch(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True, google_contacts_profile="ecochran76"),
    )
    service, _run_id, _job_id, contact_id = project_gws_route_contact(config, stored_profile="wrong-profile")

    payload = service.contact_route_selection_approval_boundary(
        contact_id,
        operator="tester",
        sink="google_contacts",
        write=False,
    )

    assert payload["state"] == "blocked"
    assert payload["boundary"] is None
    assert payload["creates_selected_live_target"] is False
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    assert any(
        "stored selected_target_profile does not match configured sink.google_contacts_profile" in reason
        for reason in payload["blocked_reasons"]
    )


def test_service_live_pilot_rehearsal_drill_reaches_command_copy_gate(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
    )

    payload = BusinessCardService(config).live_pilot_rehearsal_drill()
    run_id = payload["run_id"]
    job_id = payload["job_id"]
    artifact_dir = config.runs_dir / run_id / "artifacts" / job_id

    assert payload["schema"] == "business-card-watchdog.live-pilot-rehearsal-drill.v1"
    assert payload["state"] == "passed"
    assert payload["sink"] == "google_contacts"
    assert payload["operator"] == "fixture-operator"
    assert payload["scope"] == "lookup"
    assert payload["private_sources_used"] is False
    assert payload["public_web_search_used"] is False
    assert payload["paid_enrichment_used"] is False
    assert payload["live_sink_calls_made"] is False
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    assert all(payload["assertions"].values())
    assert payload["routing_drill"]["state"] == "passed"
    assert payload["packets"]["selection_packet"]["schema"] == "business-card-watchdog.live-selection-packet.v1"
    assert payload["packets"]["validation"]["state"] == "ready_to_select_live_target"
    assert payload["packets"]["selected_target_approval_boundary"]["state"] == (
        "ready_for_explicit_selected_target_creation"
    )
    assert payload["packets"]["selected_target_approval_boundary"]["creates_selected_live_target"] is False
    assert payload["packets"]["selected_target_command_copy_packet"]["state"] == "ready_for_operator_copy"
    assert payload["packets"]["selected_target_command_copy_packet"]["acknowledgement_ok"] is True
    assert payload["packets"]["selected_target_command_copy_packet"]["creates_selected_live_target"] is False
    assert "--write-selected-target" in payload["packets"]["selected_target_command_copy_packet"]["command_copy_text"]
    assert payload["packets"]["selected_target"]["state"] == "created"
    assert payload["packets"]["selected_target_handoff"]["schema"] == (
        "business-card-watchdog.selected-live-target-handoff-from-response.v1"
    )
    assert payload["packets"]["lookup_handoff"]["schema"] == (
        "business-card-watchdog.lookup-smoke-handoff-from-response.v1"
    )
    assert payload["packets"]["readiness_export"]["export_written"] is True
    assert payload["packets"]["execution_checklist"]["state"] == "ready_for_explicit_operator_command"
    assert payload["packets"]["command_copy_packet"]["state"] == "ready_for_operator_copy"
    assert payload["packets"]["command_copy_packet"]["acknowledgement_ok"] is True
    assert payload["command_copy_ready"] is True
    assert payload["command_copy_text"].startswith("sinks ")
    assert job_id in payload["command_copy_text"]
    assert f"--run-id {run_id}" in payload["command_copy_text"]
    assert payload["operator_response_redacted"]["raw_response_stored"] is False
    assert payload["acknowledgement_redacted"]["raw_acknowledgement_stored"] is False
    sample_output_path = Path(payload["sample_outputs"]["live_pilot_rehearsal_markdown_path"])
    sample_output = sample_output_path.read_text(encoding="utf-8")
    preflight_sample_output_path = Path(
        payload["sample_outputs"]["operator_selected_live_smoke_preflight_markdown_path"]
    )
    preflight_sample_output = preflight_sample_output_path.read_text(encoding="utf-8")
    assert sample_output_path.exists()
    assert preflight_sample_output_path.exists()
    assert "# Live Pilot Rehearsal Sample Output" in sample_output
    assert "# Operator-Selected Live Smoke Preflight Sample Output" in preflight_sample_output
    assert payload["packets"]["operator_selected_preflight"]["schema"] == (
        "business-card-watchdog.operator-selected-live-smoke-preflight.v1"
    )
    assert payload["packets"]["operator_selected_preflight"]["writes_attempted"] == 0
    assert payload["packets"]["operator_selected_preflight"]["network_calls_made"] == 0
    assert f"State: `{payload['packets']['operator_selected_preflight']['state']}`" in preflight_sample_output
    assert "Preflight written: `True`" in preflight_sample_output
    assert "Command copy packet: `ready_for_operator_copy`" in sample_output
    assert f"Operator-selected preflight: `{payload['packets']['operator_selected_preflight']['state']}`" in sample_output
    assert "Selected target approval boundary: `ready_for_explicit_selected_target_creation`" in sample_output
    assert "Selected target command copy packet: `ready_for_operator_copy`" in sample_output
    assert "fixture contact is safe for google contacts test profile" not in sample_output
    assert "fixture contact is safe for google contacts test profile" not in preflight_sample_output
    assert Path(payload["drill_path"]).exists()
    assert (artifact_dir / "selected_live_target.json").exists()
    assert (artifact_dir / "selected_live_target_audit.json").exists()
    assert (artifact_dir / "sink_lookup_smoke_handoff.json").exists()
    assert (config.runs_dir / run_id / "selected_target_approval_boundary.json").exists()
    assert (config.runs_dir / run_id / "live_pilot_readiness_export.json").exists()
    assert (config.runs_dir / run_id / "operator_selected_live_smoke_preflight_sample_output.md").exists()
    assert (config.runs_dir / run_id / "live_pilot_rehearsal_sample_output.md").exists()
    assert (config.runs_dir / run_id / "live_pilot_rehearsal_drill.json").exists()
    artifacts = [
        json.loads(line)
        for line in (config.runs_dir / run_id / "artifacts.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert any(artifact["kind"] == "live_pilot_rehearsal_sample_output" for artifact in artifacts)
    assert any(
        artifact["kind"] == "operator_selected_live_smoke_preflight_sample_output"
        for artifact in artifacts
    )


def test_service_doctor_checks_user_scope_paths(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    payload = BusinessCardService(config).doctor()

    assert payload["ok"] is True
    assert {check["name"] for check in payload["checks"]} >= {
        "config_parent",
        "data_dir",
        "cache_dir",
        "runs_dir",
        "watch_dir",
        "business_card_skill",
        "watch_inputs",
    }


def test_service_submit_review_records_artifact_and_advances_job(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)

    result = service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
        field_corrections={"full_name": "Reviewed Fixture"},
        crop_selection={"crop_id": "c01", "reason": "face-centered"},
        notes="synthetic review",
    )
    job = service.get_job(job_id, run_id=run_id)
    events = [
        json.loads(line)
        for line in (config.runs_dir / run_id / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert result["submission"]["field_corrections"]["full_name"] == "Reviewed Fixture"
    assert job["state"] == "ready_to_route"
    assert any(artifact["kind"] == "review_submission" for artifact in job["artifacts"])
    assert any(event["event_type"] == "review_submitted" for event in events)


def test_service_apply_review_decisions_records_run_import_artifact(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)

    payload = service.apply_review_decisions(
        run_id=run_id,
        reviewer="batch-reviewer",
        decisions=[
            {
                "job_id": job_id,
                "action": "approve_for_routing",
                "field_corrections": {"full_name": "Batch Fixture", "email": "batch@example.test"},
                "notes": "batch import",
            }
        ],
    )
    job = service.get_job(job_id, run_id=run_id)
    artifacts = service.list_artifacts(run_id)
    events = [
        json.loads(line)
        for line in (config.runs_dir / run_id / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert payload["import"]["schema"] == "business-card-watchdog.review-decisions-import.v1"
    assert payload["import"]["applied_count"] == 1
    assert payload["results"][0]["action"] == "approve_for_routing"
    assert payload["results"][0]["job_state"] == "ready_to_route"
    assert job["state"] == "ready_to_route"
    assert any(artifact["kind"] == "review_decisions_import" for artifact in artifacts)
    assert any(event["event_type"] == "review_decisions_imported" for event in events)


def test_service_apply_review_workbook_csv_uses_decision_template_json(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    workbook = service.review_workbook(run_id=run_id)
    rows = list(csv.DictReader(StringIO(workbook["csv"])))
    rows[0]["review_action"] = "approve_for_routing"
    rows[0]["corrected_full_name"] = "Workbook Fixture"
    rows[0]["corrected_email"] = "workbook@example.test"
    rows[0]["review_notes"] = "csv import"
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)

    payload = service.apply_review_workbook_csv(
        run_id=run_id,
        reviewer="workbook-reviewer",
        csv_text=output.getvalue(),
    )
    job = service.get_job(job_id, run_id=run_id)

    assert payload["import"]["source_format"] == "csv"
    assert payload["import"]["source_schema"] == "business-card-watchdog.review-workbook.v1"
    assert payload["import"]["applied_count"] == 1
    assert payload["results"][0]["job_state"] == "ready_to_route"
    reviewed = json.loads(
        (config.runs_dir / run_id / "artifacts" / job_id / "reviewed_contact.json").read_text(
            encoding="utf-8"
        )
    )
    assert reviewed["flat"]["email"] == "workbook@example.test"
    assert job["state"] == "ready_to_route"


def test_service_preview_review_workbook_csv_validates_without_writes(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    workbook = service.review_workbook(run_id=run_id)
    rows = list(csv.DictReader(StringIO(workbook["csv"])))
    rows[0]["review_action"] = "approve_for_routing"
    rows[0]["corrected_full_name"] = "Previewed Contact"
    skipped = dict(rows[0])
    skipped["job_id"] = "skipped-job"
    skipped["skip_import"] = "true"
    invalid = dict(rows[0])
    invalid["review_action"] = "approve_enrichment_merge"
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows([rows[0], skipped, invalid])

    preview = service.preview_review_workbook_csv(
        run_id=run_id,
        reviewer="previewer",
        csv_text=output.getvalue(),
    )

    assert preview["schema"] == "business-card-watchdog.review-workbook-preview.v1"
    assert preview["valid"] is False
    assert preview["row_count"] == 3
    assert preview["ready_count"] == 1
    assert preview["skipped_count"] == 1
    assert preview["error_count"] == 1
    assert preview["rows"][0]["status"] == "ready"
    assert preview["rows"][0]["field_correction_count"] == 1
    assert preview["rows"][1]["status"] == "skipped"
    assert preview["rows"][2]["status"] == "error"
    assert "requires an enrichment_result artifact" in preview["rows"][2]["errors"][0]
    validation_rows = list(csv.DictReader(StringIO(preview["validation_csv"])))
    assert validation_rows[0]["status"] == "ready"
    assert validation_rows[0]["job_id"] == job_id
    assert validation_rows[1]["status"] == "skipped"
    assert validation_rows[2]["status"] == "error"
    assert "requires an enrichment_result artifact" in validation_rows[2]["errors"]
    assert preview["writes_attempted"] == 0
    assert preview["network_calls_made"] == 0
    assert not (config.runs_dir / run_id / "review_decisions_import.json").exists()


def test_service_preview_review_workbook_csv_warns_on_blocked_sink_readiness(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=False, google_contacts_apply_enabled=False),
    )
    run_id, _job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    workbook = service.review_workbook(run_id=run_id)
    rows = list(csv.DictReader(StringIO(workbook["csv"])))
    rows[0]["review_action"] = "approve_for_routing"
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)

    preview = service.preview_review_workbook_csv(
        run_id=run_id,
        reviewer="previewer",
        csv_text=output.getvalue(),
    )
    validation_rows = list(csv.DictReader(StringIO(preview["validation_csv"])))

    assert preview["rows"][0]["status"] == "ready"
    assert preview["rows"][0]["sink_readiness_warnings"][0]["sink"] == "google_contacts"
    assert any("live sink apply is disabled" in warning for warning in preview["rows"][0]["warnings"])
    assert "sink google_contacts blocked" in validation_rows[0]["sink_readiness_warnings"]
    assert preview["writes_attempted"] == 0
    assert preview["network_calls_made"] == 0


def test_service_preview_review_workbook_csv_can_persist_artifacts(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    workbook = service.review_workbook(run_id=run_id)

    preview = service.preview_review_workbook_csv(
        run_id=run_id,
        reviewer="previewer",
        csv_text=workbook["csv"],
        write=True,
    )
    preview_path = Path(preview["preview_path"])
    validation_csv_path = Path(preview["validation_csv_path"])
    artifacts = service.list_artifacts(run_id)
    persisted = json.loads(preview_path.read_text(encoding="utf-8"))

    assert preview["rows"][0]["job_id"] == job_id
    assert preview_path.exists()
    assert validation_csv_path.exists()
    assert persisted["schema"] == "business-card-watchdog.review-workbook-preview.v1"
    assert "row_number,status,run_id,job_id,action,errors,warnings" in validation_csv_path.read_text(encoding="utf-8")
    assert any(artifact["kind"] == "review_workbook_preview" for artifact in artifacts)
    assert any(artifact["kind"] == "review_workbook_preview_validation_csv" for artifact in artifacts)
    summary = service.run_summary(run_id)
    preview_summary = summary["review_workbook_preview_summary"]
    assert preview_summary["has_preview"] is True
    assert preview_summary["preview_count"] == 1
    assert preview_summary["validation_csv_count"] == 1
    assert preview_summary["latest_valid"] is True
    assert preview_summary["latest_ready_count"] == 1
    assert preview_summary["latest_error_count"] == 0
    assert preview_summary["latest_preview_path"] == str(preview_path)
    assert preview_summary["latest_validation_csv_path"] == str(validation_csv_path)
    phase_report = service.phase_report(run_id)
    preview_phase = phase_report["review_workbook_preview"]
    assert preview_phase["state"] == "valid"
    assert preview_phase["counts"]["valid"] == 1
    assert preview_phase["latest_ready_count"] == 1
    assert preview_phase["latest_preview_path"] == str(preview_path)
    assert preview_phase["latest_validation_csv_path"] == str(validation_csv_path)
    assert not (config.runs_dir / run_id / "review_decisions_import.json").exists()


def test_service_apply_review_workbook_csv_supports_enrichment_columns(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    artifact_dir = config.runs_dir / run_id / "artifacts" / job_id
    service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
        field_corrections={"full_name": "Card Name", "email": "card@example.test", "notes": "Card note"},
    )
    (artifact_dir / "enrichment_result.json").write_text(
        json.dumps(
            {
                "schema": "business-card-watchdog.enrichment-result.v1",
                "merge_proposals": [
                    {
                        "field": "notes",
                        "value": "Public-web corroboration candidate: https://example.test/card",
                        "source": "public_web",
                    }
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    workbook = service.review_workbook(run_id=run_id)
    rows = list(csv.DictReader(StringIO(workbook["csv"])))
    rows[0]["review_action"] = "approve_enrichment_merge"
    rows[0]["approved_enrichment_fields"] = "notes"
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)

    payload = service.apply_review_workbook_csv(
        run_id=run_id,
        reviewer="workbook-reviewer",
        csv_text=output.getvalue(),
    )
    reviewed = json.loads((artifact_dir / "reviewed_contact.json").read_text(encoding="utf-8"))

    assert payload["results"][0]["action"] == "approve_enrichment_merge"
    assert "Public-web corroboration candidate" in reviewed["flat"]["notes"]


def test_service_apply_review_workbook_csv_supports_duplicate_resolution_columns(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    artifact_dir = config.runs_dir / run_id / "artifacts" / job_id
    (artifact_dir / "duplicate_assessment.json").write_text(
        json.dumps(
            {
                "schema": "business-card-watchdog.duplicate-assessment.v1",
                "state": "strong_duplicate",
                "matches": [{"match_type": "email", "serialization_key": "email:card@example.test"}],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    workbook = service.review_workbook(run_id=run_id)
    rows = list(csv.DictReader(StringIO(workbook["csv"])))
    rows[0]["review_action"] = "resolve_duplicate"
    rows[0]["duplicate_decision"] = "merge_existing"
    rows[0]["duplicate_target_identity"] = "email:card@example.test"
    rows[0]["duplicate_reason"] = "same person confirmed"
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)

    payload = service.apply_review_workbook_csv(
        run_id=run_id,
        reviewer="workbook-reviewer",
        csv_text=output.getvalue(),
    )
    resolution = json.loads((artifact_dir / "duplicate_resolution.json").read_text(encoding="utf-8"))

    assert payload["results"][0]["action"] == "resolve_duplicate"
    assert payload["results"][0]["job_state"] == "ready_to_route"
    assert resolution["decision"] == "merge_existing"
    assert resolution["target_identity"] == "email:card@example.test"


def test_service_plan_sinks_for_job_writes_dry_run_plan(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, odoo=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "example.test", "sinks": ["google_contacts", "odoo"]}],
    )
    run_id, job_id = make_recorded_run(config)
    artifact_dir = config.runs_dir / run_id / "artifacts" / job_id
    candidate = build_contact_candidate({"full_name": "Ada Lovelace", "email": "ADA@EXAMPLE.TEST"})
    (artifact_dir / "contact_candidate.json").write_text(json.dumps(candidate, indent=2), encoding="utf-8")

    result = BusinessCardService(config).plan_sinks_for_job(job_id=job_id, run_id=run_id)
    job = BusinessCardService(config).get_job(job_id, run_id=run_id)

    assert result["plan"]["schema"] == "business-card-watchdog.sink-plan.v1"
    assert result["plan"]["state"] == "dry_run"
    assert [action["sink"] for action in result["plan"]["actions"]] == ["google_contacts", "odoo"]
    assert result["plan"]["actions"][0]["match_keys"]["email"] == "ada@example.test"
    assert result["plan"]["route_explanation"]["schema"] == "business-card-watchdog.route-explanation.v1"
    assert result["plan"]["route_explanation"]["matched_rules"][0]["reason"] == "matched email_domain=example.test"
    assert result["plan"]["sink_eligibility"][0]["sink"] == "google_contacts"
    assert result["plan"]["sink_eligibility"][0]["route_eligible"] is True
    assert result["plan"]["sink_eligibility"][0]["apply_approval_required"] is True
    assert any(artifact["kind"] == "sink_plan" for artifact in job["artifacts"])


def test_service_plan_sink_lookup_for_job_writes_zero_network_plan(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, odoo=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts", "odoo"]}],
    )
    run_id, job_id = make_recorded_run(config)
    artifact_dir = config.runs_dir / run_id / "artifacts" / job_id
    candidate = build_contact_candidate({"full_name": "Ada Lovelace", "email": "ada@example.test"})
    (artifact_dir / "contact_candidate.json").write_text(json.dumps(candidate, indent=2), encoding="utf-8")

    result = BusinessCardService(config).plan_sink_lookup_for_job(job_id=job_id, run_id=run_id)
    job = BusinessCardService(config).get_job(job_id, run_id=run_id)
    events = [
        json.loads(line)
        for line in (config.runs_dir / run_id / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert result["lookup_plan"]["schema"] == "business-card-watchdog.sink-lookup-plan.v1"
    assert result["lookup_plan"]["network_calls_made"] == 0
    assert [lookup["sink"] for lookup in result["lookup_plan"]["lookups"]] == ["google_contacts", "odoo"]
    assert result["lookup_plan"]["lookups"][0]["match_keys"]["email"] == "ada@example.test"
    assert any(artifact["kind"] == "sink_lookup_plan" for artifact in job["artifacts"])
    assert any(event["event_type"] == "sink_lookup_plan_created" for event in events)


def test_service_plans_use_route_selected_odollo_tenant(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(odoo=True, dry_run=True, odollo_tenant="fallback-tenant"),
        routing_rules=[
            {
                "match": "providence_context",
                "value": "saber",
                "sinks": ["odoo"],
                "odollo_tenant": "saber-prod",
            }
        ],
    )
    run_id, job_id = make_recorded_run(config)
    artifact_dir = config.runs_dir / run_id / "artifacts" / job_id
    (artifact_dir / "spec.json").write_text(
        json.dumps({"full_name": "Ada Lovelace", "email": "ada@example.test", "providence_context": "saber"}),
        encoding="utf-8",
    )

    service = BusinessCardService(config)
    lookup_result = service.plan_sink_lookup_for_job(job_id=job_id, run_id=run_id)
    sink_result = service.plan_sinks_for_job(job_id=job_id, run_id=run_id)

    lookup = lookup_result["lookup_plan"]["lookups"][0]
    action = sink_result["plan"]["actions"][0]
    assert lookup["sink"] == "odoo"
    assert lookup["readiness"]["details"]["tenant"] == "saber-prod"
    assert lookup_result["lookup_plan"]["decision"]["metadata"]["route_targets"]["odoo"]["tenant"] == "saber-prod"
    assert action["sink"] == "odoo"
    assert action["readiness"]["details"]["tenant"] == "saber-prod"
    assert sink_result["plan"]["decision"]["metadata"]["route_targets"]["odoo"]["source"] == (
        "routing.rule.odollo_tenant"
    )


def test_service_preflight_sink_apply_writes_zero_write_artifact(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
        field_corrections={"full_name": "Reviewed Fixture", "email": "fixture@example.test"},
    )
    service.plan_sink_lookup_for_job(job_id=job_id, run_id=run_id)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="lookup")
    service.record_sink_lookup_result_for_job(job_id=job_id, run_id=run_id)
    service.assess_downstream_duplicates_for_job(job_id=job_id, run_id=run_id)
    service.plan_sinks_for_job(job_id=job_id, run_id=run_id)

    preview = service.preflight_sink_apply(job_id=job_id, run_id=run_id)
    blocked = service.preflight_sink_apply(job_id=job_id, run_id=run_id, apply=True)
    job = service.get_job(job_id, run_id=run_id)
    events = [
        json.loads(line)
        for line in (config.runs_dir / run_id / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert preview["preflight"]["schema"] == "business-card-watchdog.sink-apply-preflight.v1"
    assert preview["preflight"]["state"] == "preview"
    assert preview["preflight"]["writes_attempted"] == 0
    assert preview["preflight"]["network_calls_made"] == 0
    assert blocked["preflight"]["state"] == "blocked"
    assert any(artifact["kind"] == "sink_apply_preflight" for artifact in job["artifacts"])
    assert any(event["event_type"] == "sink_apply_preflight_created" for event in events)


def test_service_decide_sink_apply_writes_zero_write_decision(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
        field_corrections={"full_name": "Reviewed Fixture", "email": "fixture@example.test"},
    )
    service.plan_sinks_for_job(job_id=job_id, run_id=run_id)
    service.preflight_sink_apply(job_id=job_id, run_id=run_id)

    result = service.decide_sink_apply(
        job_id=job_id,
        run_id=run_id,
        decision="approve",
        reviewer="tester",
        reason="pilot approved",
    )
    job = service.get_job(job_id, run_id=run_id)
    events = [
        json.loads(line)
        for line in (config.runs_dir / run_id / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert result["decision"]["schema"] == "business-card-watchdog.sink-apply-decision.v1"
    assert result["decision"]["state"] == "approved_for_apply"
    assert result["decision"]["writes_attempted"] == 0
    assert any(artifact["kind"] == "sink_apply_decision" for artifact in job["artifacts"])
    assert any(event["event_type"] == "sink_apply_decided" for event in events)


def test_service_decide_sink_apply_noop_cancels_job(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    run_id, job_id = make_recorded_run(config)

    result = BusinessCardService(config).decide_sink_apply(
        job_id=job_id,
        run_id=run_id,
        decision="noop",
        reviewer="tester",
        reason="no sink write needed",
    )

    assert result["job"]["state"] == "cancelled"
    assert result["job"]["error"] == "sink apply resolved as no-op"


def test_service_apply_sinks_for_job_writes_blocked_zero_write_result(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.plan_sinks_for_job(job_id=job_id, run_id=run_id)
    service.preflight_sink_apply(job_id=job_id, run_id=run_id)
    service.decide_sink_apply(job_id=job_id, run_id=run_id, decision="approve", reviewer="tester")

    result = service.apply_sinks_for_job(job_id=job_id, run_id=run_id, apply=True)
    job = service.get_job(job_id, run_id=run_id)
    events = [
        json.loads(line)
        for line in (config.runs_dir / run_id / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert result["result"]["schema"] == "business-card-watchdog.sink-apply-result.v1"
    assert result["result"]["state"] == "blocked"
    assert result["result"]["writes_attempted"] == 0
    assert result["result"]["network_calls_made"] == 0
    assert result["result"]["readback"] == []
    assert any(artifact["kind"] == "sink_apply_result" for artifact in job["artifacts"])
    assert any(event["event_type"] == "sink_apply_attempted" for event in events)


def test_service_apply_sinks_for_job_can_emit_mock_readback(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.plan_sinks_for_job(job_id=job_id, run_id=run_id)
    service.preflight_sink_apply(job_id=job_id, run_id=run_id)
    service.decide_sink_apply(job_id=job_id, run_id=run_id, decision="approve", reviewer="tester")

    result = service.apply_sinks_for_job(job_id=job_id, run_id=run_id, apply=True, simulate=True)
    events = [
        json.loads(line)
        for line in (config.runs_dir / run_id / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert result["result"]["state"] == "mock_applied"
    assert result["result"]["simulated"] is True
    assert result["result"]["readback"][0]["resource_id"].startswith("mock:google_contacts:")
    assert any(event["payload"]["simulated"] is True for event in events if event["event_type"] == "sink_apply_attempted")


def test_service_apply_sinks_for_job_uses_injected_write_executor(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    calls: list[dict[str, object]] = []

    def execute(request: dict[str, object]) -> dict[str, object]:
        calls.append(request)
        return {
            "sink": "google_contacts",
            "status": "live_write_completed",
            "network_calls_made": 1,
            "writes_attempted": 1,
            "write": {
                "sink": "google_contacts",
                "resource_id": "people/live123",
                "serialization_key": request.get("serialization_key"),
            },
        }

    service = BusinessCardService(config, sink_write_executor=execute)
    service.plan_sinks_for_job(job_id=job_id, run_id=run_id)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="write")
    service.preflight_sink_apply(job_id=job_id, run_id=run_id)
    service.decide_sink_apply(job_id=job_id, run_id=run_id, decision="approve", reviewer="tester")

    result = service.apply_sinks_for_job(job_id=job_id, run_id=run_id, apply=True)
    readback = service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="readback")

    assert calls[0]["sink"] == "google_contacts"
    assert result["result"]["state"] == "live_applied"
    assert result["result"]["writes_attempted"] == 1
    assert result["result"]["network_calls_made"] == 1
    assert result["result"]["readback"][0]["resource_id"] == "people/live123"
    assert result["result"]["actions"][0]["write_attempted"] is True
    assert readback["request"]["requests"][0]["resource_id"] == "people/live123"


def test_service_write_pilot_writes_simulated_apply_result(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.plan_sinks_for_job(job_id=job_id, run_id=run_id)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="write")
    service.preflight_sink_apply(job_id=job_id, run_id=run_id)
    service.decide_sink_apply(job_id=job_id, run_id=run_id, decision="approve", reviewer="tester")
    service.select_live_target_for_job(
        job_id=job_id,
        run_id=run_id,
        sink="google_contacts",
        operator="tester",
        scope="write",
        safety_confirmation="fixture contact is safe for google contacts test profile",
    )

    pilot = service.execute_sink_write_pilot_for_job(
        job_id=job_id,
        run_id=run_id,
        sink="google_contacts",
        approved_by="tester",
    )
    readback = service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="readback")
    job = service.get_job(job_id, run_id=run_id)

    assert pilot["pilot"]["schema"] == "business-card-watchdog.sink-write-pilot.v1"
    assert pilot["pilot"]["state"] == "mock_written"
    assert pilot["pilot"]["simulated"] is True
    assert pilot["pilot"]["writes_attempted"] == 0
    assert pilot["pilot"]["network_calls_made"] == 0
    assert pilot["result"]["source_write_pilot_schema"] == "business-card-watchdog.sink-write-pilot.v1"
    assert pilot["result"]["state"] == "mock_applied"
    assert pilot["result"]["readback"][0]["resource_id"].startswith("mock:google_contacts:")
    assert readback["request"]["requests"][0]["resource_id"].startswith("mock:google_contacts:")
    assert any(artifact["kind"] == "sink_write_pilot" for artifact in job["artifacts"])


def test_service_apply_pilot_readiness_can_scope_to_selected_sink(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, odoo=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts", "odoo"]}],
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.plan_sinks_for_job(job_id=job_id, run_id=run_id)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="write")
    service.preflight_sink_apply(job_id=job_id, run_id=run_id)
    service.decide_sink_apply(job_id=job_id, run_id=run_id, decision="approve", reviewer="tester")

    readiness = service.build_sink_apply_pilot_readiness_for_job(
        job_id=job_id,
        run_id=run_id,
        sink="google_contacts",
    )

    payload = readiness["readiness"]
    assert payload["schema"] == "business-card-watchdog.sink-apply-pilot-readiness.v1"
    assert payload["readiness_scope"] == "selected_sink"
    assert payload["selected_sink"] == "google_contacts"
    assert payload["can_mock_apply_pilot"] is True
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    assert {check["sink"] for check in payload["selected_sink_readiness"]} == {"google_contacts"}
    assert {action["sink"] for action in payload["selected_actions"]["preflight"]} == {"google_contacts"}
    assert {request["sink"] for request in payload["selected_actions"]["write_adapter_requests"]} == {
        "google_contacts"
    }
    assert " --sink google_contacts" in payload["commands"]["prepare"]
    assert " --sink google_contacts " in payload["commands"]["live_write"]
    assert "readback_adapter_available_after_apply" in payload["live_missing_requirements"]


def test_service_odollo_live_lookup_uses_route_selected_tenant(tmp_path: Path, monkeypatch) -> None:
    odollo_home = tmp_path / "odollo"
    tenant_home = odollo_home / "tenants" / "saber-prod"
    (tenant_home / "resources").mkdir(parents=True)
    (tenant_home / "artifacts").mkdir()
    (tenant_home / "actions.ndjson").write_text("", encoding="utf-8")
    (odollo_home / "odollo.yml").write_text("profiles: {}\n", encoding="utf-8")
    (odollo_home / "saber-prod.sqlite").write_text("", encoding="utf-8")
    monkeypatch.setenv("ODOLLO_HOME", str(odollo_home))
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(odoo=True, dry_run=True),
        routing_rules=[
            {
                "match": "email_domain",
                "value": "*",
                "sinks": ["odoo"],
                "odollo_tenant": "saber-prod",
            }
        ],
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
        field_corrections={"full_name": "Ada Lovelace", "email": "ada@example.test"},
    )
    service.plan_sink_lookup_for_job(job_id=job_id, run_id=run_id)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="lookup")

    readiness = service.live_lookup_readiness_report(job_id=job_id, run_id=run_id, sink="odoo")

    assert readiness["live_lookup_readiness"]["status"] == "ready"
    assert readiness["live_lookup_readiness"]["details"]["tenant"] == "saber-prod"
    assert readiness["selected_target_context"]["tenant"] == "saber-prod"
    assert "selected_odollo_tenant_present" not in readiness["missing_requirements"]


def test_service_odollo_selected_target_blocks_write_until_duplicate_evidence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    odollo_home = tmp_path / "odollo"
    tenant_home = odollo_home / "tenants" / "saber-prod"
    (tenant_home / "resources").mkdir(parents=True)
    (tenant_home / "artifacts").mkdir()
    (tenant_home / "actions.ndjson").write_text("", encoding="utf-8")
    (odollo_home / "odollo.yml").write_text("profiles: {}\n", encoding="utf-8")
    (odollo_home / "saber-prod.sqlite").write_text("", encoding="utf-8")
    monkeypatch.setenv("ODOLLO_HOME", str(odollo_home))
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(odoo=True, dry_run=True),
        routing_rules=[
            {
                "match": "email_domain",
                "value": "*",
                "sinks": ["odoo"],
                "odollo_tenant": "saber-prod",
            }
        ],
    )
    run_id, job_id = make_recorded_run(config)
    calls: list[dict[str, object]] = []

    def execute(request: dict[str, object]) -> dict[str, object]:
        calls.append(request)
        return {
            "sink": "odoo",
            "status": "live_write_completed",
            "network_calls_made": 1,
            "writes_attempted": 1,
            "write": {"sink": "odoo", "resource_id": "odoo/res.partner/42"},
        }

    service = BusinessCardService(config, sink_write_executor=execute)
    service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
        field_corrections={"full_name": "Ada Lovelace", "email": "ada@example.test"},
    )
    service.plan_sink_lookup_for_job(job_id=job_id, run_id=run_id)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="lookup")
    service.plan_sinks_for_job(job_id=job_id, run_id=run_id)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="write")
    service.preflight_sink_apply(job_id=job_id, run_id=run_id)
    service.decide_sink_apply(job_id=job_id, run_id=run_id, decision="approve", reviewer="tester")
    selected = service.select_live_target_for_job(
        job_id=job_id,
        run_id=run_id,
        sink="odoo",
        operator="tester",
        scope="all",
        safety_confirmation="fixture contact is safe for saber tenant write pilot",
    )

    write_packet = service.selected_write_pilot_execution_packet_from_response(
        run_id=run_id,
        response=(
            f"run_id={run_id} job_id={job_id} sink=odoo operator=tester scope=all "
            "safety_confirmation=saber tenant profile account confirmed"
        ),
    )

    assert selected["target"]["target"]["tenant"] == "saber-prod"
    assert write_packet["state"] == "blocked"
    assert write_packet["odollo_write_boundary"]["state"] == "blocked"
    assert "selected_lookup_smoke.json is required before Odollo write pilot" in write_packet["blocked_reasons"]
    try:
        service.execute_sink_write_pilot_for_job(
            job_id=job_id,
            run_id=run_id,
            sink="odoo",
            approved_by="tester",
            simulate=False,
        )
    except ValueError as exc:
        assert "Odollo write pilot boundary blocked" in str(exc)
    else:
        raise AssertionError("expected Odollo write pilot to require duplicate evidence")
    assert calls == []


def test_service_write_pilot_uses_injected_executor(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    calls: list[dict[str, object]] = []

    def execute(request: dict[str, object]) -> dict[str, object]:
        calls.append(request)
        return {
            "sink": "google_contacts",
            "status": "live_write_completed",
            "network_calls_made": 1,
            "writes_attempted": 1,
            "write": {
                "sink": "google_contacts",
                "resource_id": "people/live123",
                "serialization_key": request.get("serialization_key"),
            },
        }

    service = BusinessCardService(config, sink_write_executor=execute)
    service.plan_sinks_for_job(job_id=job_id, run_id=run_id)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="write")
    service.preflight_sink_apply(job_id=job_id, run_id=run_id)
    service.decide_sink_apply(job_id=job_id, run_id=run_id, decision="approve", reviewer="tester")
    service.select_live_target_for_job(
        job_id=job_id,
        run_id=run_id,
        sink="google_contacts",
        operator="tester",
        scope="write",
        safety_confirmation="fixture contact is safe for google contacts test profile",
    )

    pilot = service.execute_sink_write_pilot_for_job(
        job_id=job_id,
        run_id=run_id,
        sink="google_contacts",
        approved_by="tester",
        simulate=False,
    )

    assert calls[0]["sink"] == "google_contacts"
    assert pilot["pilot"]["state"] == "live_written"
    assert pilot["pilot"]["simulated"] is False
    assert pilot["pilot"]["writes_attempted"] == 1
    assert pilot["pilot"]["network_calls_made"] == 1
    assert pilot["result"]["state"] == "live_applied"
    assert pilot["result"]["readback"][0]["resource_id"] == "people/live123"


def test_service_readback_pilot_writes_simulated_evidence(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.plan_sinks_for_job(job_id=job_id, run_id=run_id)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="write")
    service.preflight_sink_apply(job_id=job_id, run_id=run_id)
    service.decide_sink_apply(job_id=job_id, run_id=run_id, decision="approve", reviewer="tester")
    service.apply_sinks_for_job(job_id=job_id, run_id=run_id, apply=True, simulate=True)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="readback")

    try:
        service.execute_sink_readback_pilot_for_job(
            job_id=job_id,
            run_id=run_id,
            sink="google_contacts",
            approved_by="tester",
        )
    except ValueError as exc:
        assert "sink_write_pilot.json" in str(exc)
    else:
        raise AssertionError("expected readback pilot to require write pilot evidence")

    service.execute_sink_write_pilot_for_job(
        job_id=job_id,
        run_id=run_id,
        sink="google_contacts",
        approved_by="tester",
    )
    pilot = service.execute_sink_readback_pilot_for_job(
        job_id=job_id,
        run_id=run_id,
        sink="google_contacts",
        approved_by="tester",
    )
    job = service.get_job(job_id, run_id=run_id)

    assert pilot["pilot"]["schema"] == "business-card-watchdog.sink-readback-pilot.v1"
    assert pilot["pilot"]["state"] == "verified"
    assert pilot["pilot"]["simulated"] is True
    assert pilot["pilot"]["writes_attempted"] == 0
    assert pilot["pilot"]["network_calls_made"] == 0
    assert pilot["pilot"]["readback"]["resource_id"].startswith("mock:google_contacts:")
    assert pilot["pilot"]["source_write_pilot"]["state"] == "mock_written"
    assert any(artifact["kind"] == "sink_readback_pilot" for artifact in job["artifacts"])


def test_service_apply_pilot_report_summarizes_write_and_readback(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
        field_corrections={"full_name": "Reviewed Fixture", "email": "fixture@example.test"},
    )
    service.plan_sinks_for_job(job_id=job_id, run_id=run_id)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="write")
    service.preflight_sink_apply(job_id=job_id, run_id=run_id)
    service.decide_sink_apply(job_id=job_id, run_id=run_id, decision="approve", reviewer="tester")
    service.build_sink_apply_pilot_readiness_for_job(job_id=job_id, run_id=run_id)
    service.execute_sink_write_pilot_for_job(job_id=job_id, run_id=run_id, sink="google_contacts", approved_by="tester")
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="readback")
    service.execute_sink_readback_pilot_for_job(job_id=job_id, run_id=run_id, sink="google_contacts", approved_by="tester")

    report = service.build_sink_apply_pilot_report_for_job(job_id=job_id, run_id=run_id)
    job = service.get_job(job_id, run_id=run_id)

    assert report["report"]["schema"] == "business-card-watchdog.sink-apply-pilot-report.v1"
    assert report["report"]["state"] == "complete"
    assert report["report"]["writes_attempted"] == 0
    assert report["report"]["network_calls_made"] == 0
    assert report["report"]["missing_artifacts"] == []
    assert report["report"]["consistency_errors"] == []
    assert report["report"]["sinks"][0]["readback_matched"] is True
    assert any(artifact["kind"] == "sink_apply_pilot_report" for artifact in job["artifacts"])


def test_service_apply_pilot_report_blocks_inconsistent_write_readback(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, odoo=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts", "odoo"]}],
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
        field_corrections={"full_name": "Reviewed Fixture", "email": "fixture@example.test"},
    )
    service.plan_sinks_for_job(job_id=job_id, run_id=run_id)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="write")
    service.preflight_sink_apply(job_id=job_id, run_id=run_id)
    service.decide_sink_apply(job_id=job_id, run_id=run_id, decision="approve", reviewer="tester")
    service.build_sink_apply_pilot_readiness_for_job(job_id=job_id, run_id=run_id, sink="google_contacts")
    service.execute_sink_write_pilot_for_job(
        job_id=job_id,
        run_id=run_id,
        sink="google_contacts",
        approved_by="tester",
    )
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="readback")
    service.execute_sink_readback_pilot_for_job(
        job_id=job_id,
        run_id=run_id,
        sink="google_contacts",
        approved_by="tester",
    )
    readback_path = config.runs_dir / run_id / "artifacts" / job_id / "sink_readback_pilot.json"
    readback = json.loads(readback_path.read_text(encoding="utf-8"))
    readback["sink"] = "odoo"
    readback["source_write_pilot"]["resource_id"] = "mock:odoo:wrong"
    readback["source_write_pilot"]["selected_target"] = {"selection_id": "stale-target"}
    readback_path.write_text(json.dumps(readback, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_path = config.runs_dir / run_id / "artifacts" / job_id / "sink_write_pilot.json"
    write = json.loads(write_path.read_text(encoding="utf-8"))
    write["selected_target"] = {"selection_id": "current-target"}
    write_path.write_text(json.dumps(write, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    report = service.build_sink_apply_pilot_report_for_job(job_id=job_id, run_id=run_id)

    assert report["report"]["state"] == "incomplete"
    assert any("sink_mismatch" in error for error in report["report"]["consistency_errors"])
    assert any("source_write_resource_mismatch" in error for error in report["report"]["consistency_errors"])
    assert any("source_write_selected_target_mismatch" in error for error in report["report"]["consistency_errors"])


def test_service_apply_pilot_bundle_collects_selected_sink_commands_and_stops(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
        field_corrections={"full_name": "Reviewed Fixture", "email": "fixture@example.test"},
    )
    service.plan_sink_lookup_for_job(job_id=job_id, run_id=run_id)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="lookup")
    service.record_sink_lookup_result_for_job(job_id=job_id, run_id=run_id)
    service.assess_downstream_duplicates_for_job(job_id=job_id, run_id=run_id)
    service.plan_sinks_for_job(job_id=job_id, run_id=run_id)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="write")
    service.preflight_sink_apply(job_id=job_id, run_id=run_id)
    service.decide_sink_apply(job_id=job_id, run_id=run_id, decision="approve", reviewer="tester")

    bundle = service.build_sink_apply_pilot_bundle_for_job(
        job_id=job_id,
        run_id=run_id,
        sink="google_contacts",
        operator="tester",
    )
    job = service.get_job(job_id, run_id=run_id)
    review_bundle = service.review_bundle(run_id=run_id)

    payload = bundle["bundle"]
    assert payload["schema"] == "business-card-watchdog.sink-apply-pilot-bundle.v1"
    assert payload["state"] == "ready_for_mock_pilot"
    assert payload["sink"] == "google_contacts"
    assert payload["operator"] == "tester"
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    assert payload["can_attempt_mock_pilot"] is True
    assert payload["can_attempt_live_pilot"] is False
    assert payload["artifacts"]["sink_apply_pilot_readiness"]["exists"] is True
    assert payload["artifacts"]["sink_apply_pilot_readiness"]["selected"] is True
    assert payload["commands"]["live_write"].startswith(
        f"sinks write-pilot {job_id} --run-id {run_id} --sink google_contacts"
    )
    assert any("second write pilot" in condition for condition in payload["stop_conditions"])
    assert payload["remediation"]["sink"] == "google_contacts"
    assert payload["remediation"]["rollback_guaranteed"] is False
    assert "live_apply_ready" in payload["missing_requirements"]
    assert Path(bundle["bundle_path"]).exists()
    assert any(artifact["kind"] == "sink_apply_pilot_bundle" for artifact in job["artifacts"])
    assert "sink_apply_pilot_bundle" in review_bundle["entries"][0]["artifact_kinds"]


def test_service_review_bundle_includes_sink_pilot_status(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
        field_corrections={"full_name": "Reviewed Fixture", "email": "fixture@example.test"},
    )
    service.plan_sink_lookup_for_job(job_id=job_id, run_id=run_id)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="lookup")
    service.record_sink_lookup_result_for_job(job_id=job_id, run_id=run_id)
    service.assess_downstream_duplicates_for_job(job_id=job_id, run_id=run_id)
    service.plan_sinks_for_job(job_id=job_id, run_id=run_id)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="write")
    service.preflight_sink_apply(job_id=job_id, run_id=run_id)
    service.decide_sink_apply(job_id=job_id, run_id=run_id, decision="approve", reviewer="tester")
    service.build_sink_apply_pilot_readiness_for_job(job_id=job_id, run_id=run_id)
    service.execute_sink_write_pilot_for_job(job_id=job_id, run_id=run_id, sink="google_contacts", approved_by="tester")
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="readback")
    service.execute_sink_readback_pilot_for_job(job_id=job_id, run_id=run_id, sink="google_contacts", approved_by="tester")
    service.build_sink_apply_pilot_report_for_job(job_id=job_id, run_id=run_id)

    bundle = service.review_bundle(run_id=run_id)
    status = bundle["entries"][0]["sink_pilot_status"]
    matrix = bundle["entries"][0]["review_matrix"]
    summary = service.run_summary(run_id)
    pilot_summary = summary["sink_pilot_summary"]
    html = service.review_html(run_id=run_id)

    assert status["schema"] == "business-card-watchdog.sink-pilot-status.v1"
    assert status["state"] == "pilot_report_complete"
    assert status["report_complete"] is True
    assert status["has_write_pilot"] is True
    assert status["has_readback_pilot"] is True
    assert status["has_pilot_report"] is True
    assert status["readback_verified"] is True
    assert status["safe_to_auto_continue"] is False
    assert status["requires_explicit_operator_action"] is False
    assert matrix["contact_source"] == "reviewed_contact"
    assert matrix["contact"]["full_name"] == "Reviewed Fixture"
    assert matrix["duplicate_state"] == "no_match"
    assert matrix["route_state"] == "dry_run"
    assert matrix["planned_sinks"] == "google_contacts"
    assert matrix["sink_lookup_state"] == "no_match"
    assert matrix["sink_pilot_state"] == "pilot_report_complete"
    assert bundle["groups"]["by_sink_pilot_state"]["pilot_report_complete"]["job_ids"] == [job_id]
    assert bundle["groups"]["by_duplicate_state"]["no_match"]["job_ids"] == [job_id]
    assert bundle["groups"]["by_route_state"]["dry_run"]["job_ids"] == [job_id]
    assert bundle["groups"]["by_sink_lookup_state"]["no_match"]["job_ids"] == [job_id]
    assert pilot_summary["schema"] == "business-card-watchdog.sink-pilot-summary.v1"
    assert pilot_summary["by_state"]["pilot_report_complete"] == 1
    assert pilot_summary["write_pilot_count"] == 1
    assert pilot_summary["readback_pilot_count"] == 1
    assert pilot_summary["pilot_report_count"] == 1
    assert pilot_summary["complete_report_count"] == 1
    assert pilot_summary["jobs"][0]["job_id"] == job_id
    assert pilot_summary["jobs"][0]["state"] == "pilot_report_complete"
    phase_report = service.phase_report(run_id)
    readiness_report = service.pilot_readiness_report(run_id)
    phase_counts = {phase["phase"]: phase["counts"] for phase in phase_report["phases"]}
    assert phase_counts["pilot_report"]["complete"] == 1
    assert phase_counts["write_pilot"]["complete"] == 1
    assert phase_counts["readback_pilot"]["complete"] == 1
    assert phase_report["jobs"][0]["phase_states"]["pilot_report"] == "complete"
    assert phase_report["dashboard_summary"]["complete_phase_count"] >= 3
    assert phase_report["dashboard_summary"]["explicit_required_phase_count"] == 0
    assert readiness_report["schema"] == "business-card-watchdog.pilot-readiness-report.v1"
    assert readiness_report["state"] == "complete"
    assert readiness_report["counts"]["complete"] == 1
    assert readiness_report["counts"]["pilot_report_complete"] == 1
    assert readiness_report["pilot_complete_job_ids"] == [job_id]
    assert readiness_report["jobs"][0]["readiness_state"] == "complete"
    assert readiness_report["jobs"][0]["artifact_paths"]["sink_apply_pilot_report"].endswith(
        "sink_apply_pilot_report.json"
    )
    assert readiness_report["sink_pilot_summary"]["complete_report_count"] == 1
    assert "By Sink Pilot State" in html["html"]
    assert "By Route State" in html["html"]
    assert "pilot_report_complete" in html["html"]
    assert "Reviewed Fixture" in html["html"]


def test_service_readback_pilot_uses_injected_executor(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    calls: list[dict[str, object]] = []

    def write(request: dict[str, object]) -> dict[str, object]:
        return {
            "sink": "google_contacts",
            "network_calls_made": 1,
            "writes_attempted": 1,
            "write": {"resource_id": "people/live123", "serialization_key": request.get("serialization_key")},
        }

    def readback(request: dict[str, object]) -> dict[str, object]:
        calls.append(request)
        return {
            "sink": "google_contacts",
            "status": "live_readback_completed",
            "network_calls_made": 1,
            "writes_attempted": 0,
            "readback": {
                "resource_id": "people/live123",
                "display": "Live Fixture",
                "emails": ["fixture@example.test"],
                "matched": True,
            },
        }

    service = BusinessCardService(config, sink_write_executor=write, sink_readback_executor=readback)
    service.plan_sinks_for_job(job_id=job_id, run_id=run_id)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="write")
    service.preflight_sink_apply(job_id=job_id, run_id=run_id)
    service.decide_sink_apply(job_id=job_id, run_id=run_id, decision="approve", reviewer="tester")
    service.select_live_target_for_job(
        job_id=job_id,
        run_id=run_id,
        sink="google_contacts",
        operator="tester",
        scope="all",
        safety_confirmation="fixture contact is safe for google contacts test profile",
    )
    service.execute_sink_write_pilot_for_job(
        job_id=job_id,
        run_id=run_id,
        sink="google_contacts",
        approved_by="tester",
        simulate=False,
    )
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="readback")

    pilot = service.execute_sink_readback_pilot_for_job(
        job_id=job_id,
        run_id=run_id,
        sink="google_contacts",
        approved_by="tester",
        simulate=False,
    )

    assert calls[0]["sink"] == "google_contacts"
    assert calls[0]["resource_id"] == "people/live123"
    assert pilot["pilot"]["status"] == "live_readback_completed"
    assert pilot["pilot"]["simulated"] is False
    assert pilot["pilot"]["network_calls_made"] == 1
    assert pilot["pilot"]["writes_attempted"] == 0
    assert pilot["pilot"]["readback"]["emails"] == ["fixture@example.test"]
    assert pilot["pilot"]["source_write_pilot"]["state"] == "live_written"
    write_pilot_path = config.runs_dir / run_id / "artifacts" / job_id / "sink_write_pilot.json"
    write_pilot = json.loads(write_pilot_path.read_text(encoding="utf-8"))
    assert write_pilot["selected_target"]["selection_id"]


def test_service_readback_pilot_rejects_executor_writes_attempted(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)

    def write(request: dict[str, object]) -> dict[str, object]:
        return {
            "sink": "google_contacts",
            "network_calls_made": 1,
            "writes_attempted": 1,
            "write": {"resource_id": "people/live123", "serialization_key": request.get("serialization_key")},
        }

    def readback(request: dict[str, object]) -> dict[str, object]:
        return {
            "sink": "google_contacts",
            "status": "unexpected_readback_write_attempt",
            "network_calls_made": 1,
            "writes_attempted": 1,
            "readback": {"resource_id": "people/live123", "matched": True},
        }

    service = BusinessCardService(config, sink_write_executor=write, sink_readback_executor=readback)
    service.plan_sinks_for_job(job_id=job_id, run_id=run_id)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="write")
    service.preflight_sink_apply(job_id=job_id, run_id=run_id)
    service.decide_sink_apply(job_id=job_id, run_id=run_id, decision="approve", reviewer="tester")
    service.select_live_target_for_job(
        job_id=job_id,
        run_id=run_id,
        sink="google_contacts",
        operator="tester",
        scope="all",
        safety_confirmation="fixture contact is safe for google contacts test profile",
    )
    service.execute_sink_write_pilot_for_job(
        job_id=job_id,
        run_id=run_id,
        sink="google_contacts",
        approved_by="tester",
        simulate=False,
    )
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="readback")

    try:
        service.execute_sink_readback_pilot_for_job(
            job_id=job_id,
            run_id=run_id,
            sink="google_contacts",
            approved_by="tester",
            simulate=False,
        )
    except ValueError as exc:
        assert "writes attempted" in str(exc)
    else:
        raise AssertionError("expected readback pilot to reject write-attempting readback executor")

    artifact_dir = config.runs_dir / run_id / "artifacts" / job_id
    assert not (artifact_dir / "sink_readback_pilot.json").exists()


def test_service_readback_pilot_rejects_stale_selected_target_write(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    readback_calls: list[dict[str, object]] = []

    def write(request: dict[str, object]) -> dict[str, object]:
        return {
            "sink": "google_contacts",
            "network_calls_made": 1,
            "writes_attempted": 1,
            "write": {"resource_id": "people/live123", "serialization_key": request.get("serialization_key")},
        }

    def readback(request: dict[str, object]) -> dict[str, object]:
        readback_calls.append(request)
        return {
            "sink": "google_contacts",
            "status": "live_readback_completed",
            "network_calls_made": 1,
            "writes_attempted": 0,
            "readback": {"resource_id": "people/live123", "matched": True},
        }

    service = BusinessCardService(config, sink_write_executor=write, sink_readback_executor=readback)
    service.plan_sinks_for_job(job_id=job_id, run_id=run_id)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="write")
    service.preflight_sink_apply(job_id=job_id, run_id=run_id)
    service.decide_sink_apply(job_id=job_id, run_id=run_id, decision="approve", reviewer="tester")
    first_target = service.select_live_target_for_job(
        job_id=job_id,
        run_id=run_id,
        sink="google_contacts",
        operator="tester",
        scope="all",
        safety_confirmation="fixture contact is safe for google contacts test profile",
    )
    service.execute_sink_write_pilot_for_job(
        job_id=job_id,
        run_id=run_id,
        sink="google_contacts",
        approved_by="tester",
        simulate=False,
    )
    service.live_pilot_abandon_for_job(
        job_id=job_id,
        run_id=run_id,
        operator="tester",
        reason="replace target before readback",
    )
    replacement_target = service.select_live_target_for_job(
        job_id=job_id,
        run_id=run_id,
        sink="google_contacts",
        operator="tester",
        scope="all",
        safety_confirmation="fixture contact is safe for google contacts test profile",
    )
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="readback")

    try:
        service.execute_sink_readback_pilot_for_job(
            job_id=job_id,
            run_id=run_id,
            sink="google_contacts",
            approved_by="tester",
            simulate=False,
        )
    except ValueError as exc:
        assert "current selected live target" in str(exc)
    else:
        raise AssertionError("expected stale selected target write evidence to block readback")

    assert first_target["target"]["selection_id"] != replacement_target["target"]["selection_id"]
    assert readback_calls == []
    artifact_dir = config.runs_dir / run_id / "artifacts" / job_id
    assert not (artifact_dir / "sink_readback_pilot.json").exists()


def test_service_build_sink_adapter_request_writes_phase_artifact(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(
            google_contacts=True,
            google_contacts_profile="codex",
            odoo=True,
            odollo_tenant="saber",
            dry_run=True,
        ),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts", "odoo"]}],
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)

    lookup = service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="lookup")
    write = service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="write")
    readback = service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="readback")
    job = service.get_job(job_id, run_id=run_id)
    events = [
        json.loads(line)
        for line in (config.runs_dir / run_id / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert lookup["request"]["schema"] == "business-card-watchdog.sink-adapter-request.v1"
    assert lookup["request"]["phase"] == "lookup"
    assert lookup["request"]["network_calls_made"] == 0
    assert lookup["request"]["requests"][0]["profile"]["name"] == "codex"
    assert lookup["request"]["requests"][1]["tenant"]["name"] == "saber"
    assert write["request"]["phase"] == "write"
    assert write["request"]["requests"][0]["profile"]["name"] == "codex"
    assert write["request"]["requests"][1]["tenant"]["name"] == "saber"
    assert readback["request"]["phase"] == "readback"
    assert readback["request"]["requests"][0]["profile"]["name"] == "codex"
    assert readback["request"]["requests"][1]["tenant"]["name"] == "saber"
    assert any(artifact["kind"] == "sink_adapter_request_lookup" for artifact in job["artifacts"])
    assert any(artifact["kind"] == "sink_adapter_request_write" for artifact in job["artifacts"])
    assert any(artifact["kind"] == "sink_adapter_request_readback" for artifact in job["artifacts"])
    assert any(event["event_type"] == "sink_adapter_request_created" for event in events)


def test_service_record_sink_lookup_result_writes_zero_network_artifact(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)

    result = service.record_sink_lookup_result_for_job(
        job_id=job_id,
        run_id=run_id,
        matches_by_sink={
            "google_contacts": [
                {
                    "resource_id": "people/c123",
                    "confidence": 0.9,
                    "basis": ["email"],
                    "display": "Reviewed Fixture",
                }
            ]
        },
    )
    job = service.get_job(job_id, run_id=run_id)
    events = [
        json.loads(line)
        for line in (config.runs_dir / run_id / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert result["result"]["schema"] == "business-card-watchdog.sink-lookup-result.v1"
    assert result["result"]["state"] == "possible_duplicate"
    assert result["result"]["network_calls_made"] == 0
    assert result["result"]["writes_attempted"] == 0
    assert result["result"]["match_count"] == 1
    assert any(artifact["kind"] == "sink_lookup_result" for artifact in job["artifacts"])
    assert any(event["event_type"] == "sink_lookup_result_recorded" for event in events)


def test_service_lookup_pilot_writes_result_and_blocks_duplicate_review(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="lookup")

    pilot = service.execute_sink_lookup_pilot_for_job(
        job_id=job_id,
        run_id=run_id,
        sink="google_contacts",
        approved_by="operator",
        matches=[
            {
                "resource_id": "people/c123",
                "confidence": 0.92,
                "basis": ["email"],
                "display": "Reviewed Fixture",
            }
        ],
    )
    assessment = service.assess_downstream_duplicates_for_job(job_id=job_id, run_id=run_id)
    job = service.get_job(job_id, run_id=run_id)
    events = [
        json.loads(line)
        for line in (config.runs_dir / run_id / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert pilot["pilot"]["schema"] == "business-card-watchdog.sink-lookup-pilot.v1"
    assert pilot["pilot"]["sink"] == "google_contacts"
    assert pilot["pilot"]["network_calls_made"] == 0
    assert pilot["pilot"]["writes_attempted"] == 0
    assert pilot["result"]["source_pilot_schema"] == "business-card-watchdog.sink-lookup-pilot.v1"
    assert pilot["result"]["state"] == "possible_duplicate"
    assert assessment["assessment"]["state"] == "strong_duplicate"
    assert any(artifact["kind"] == "sink_lookup_pilot" for artifact in job["artifacts"])
    assert any(artifact["kind"] == "sink_lookup_result" for artifact in job["artifacts"])
    assert any(event["event_type"] == "sink_lookup_pilot_executed" for event in events)


def test_service_lookup_smoke_handoff_packages_selected_target_without_network(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
        field_corrections={"full_name": "Reviewed Fixture", "email": "fixture@example.test"},
    )
    service.plan_sink_lookup_for_job(job_id=job_id, run_id=run_id)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="lookup")

    handoff = service.build_sink_lookup_smoke_handoff_for_job(
        job_id=job_id,
        run_id=run_id,
        sink="google_contacts",
        approved_by="tester",
    )
    job = service.get_job(job_id, run_id=run_id)
    review_bundle = service.review_bundle(run_id=run_id)
    events = [
        json.loads(line)
        for line in (config.runs_dir / run_id / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    payload = handoff["handoff"]
    assert payload["schema"] == "business-card-watchdog.sink-lookup-smoke-handoff.v1"
    assert payload["state"] == "blocked"
    assert payload["sink"] == "google_contacts"
    assert payload["approved_by"] == "tester"
    assert payload["read_only"] is True
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    assert payload["readiness"]["schema"] == "business-card-watchdog.live-lookup-readiness.v1"
    assert "live_lookup_readiness_ready" in payload["missing_requirements"]
    assert payload["artifacts"]["sink_lookup_plan"]["exists"] is True
    assert payload["artifacts"]["sink_adapter_request_lookup"]["exists"] is True
    assert "--no-simulate" in payload["commands"]["live_lookup_pilot"]
    assert payload["mcp"]["live_lookup_pilot"] == "business_card_watchdog_sink_lookup_pilot"
    assert "not live approval" in payload["operator_note"]
    assert Path(handoff["handoff_path"]).exists()
    assert any(artifact["kind"] == "sink_lookup_smoke_handoff" for artifact in job["artifacts"])
    assert "sink_lookup_smoke_handoff" in review_bundle["entries"][0]["artifact_kinds"]
    assert any(event["event_type"] == "sink_lookup_smoke_handoff_created" for event in events)


def test_service_lookup_pilot_uses_injected_read_only_executor(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    calls: list[dict[str, object]] = []

    def execute(request: dict[str, object]) -> dict[str, object]:
        calls.append(request)
        return {
            "sink": "google_contacts",
            "status": "read_only_lookup_completed",
            "network_calls_made": 1,
            "writes_attempted": 0,
            "raw": {
                "results": [
                    {
                        "person": {
                            "resourceName": "people/live123",
                            "names": [{"displayName": "Live Fixture"}],
                            "emailAddresses": [{"value": "live@example.test"}],
                        }
                    }
                ]
            },
            "matches": [
                {
                    "resource_id": "people/live123",
                    "confidence": 0.91,
                    "basis": ["email"],
                    "display": "Live Fixture",
                    "raw": {
                        "person": {
                            "resourceName": "people/live123",
                            "names": [{"displayName": "Live Fixture"}],
                            "emailAddresses": [{"value": "live@example.test"}],
                        }
                    },
                }
            ],
        }

    service = BusinessCardService(config, sink_lookup_executor=execute)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="lookup")
    service.select_live_target_for_job(
        job_id=job_id,
        run_id=run_id,
        sink="google_contacts",
        operator="operator",
        scope="lookup",
        safety_confirmation="fixture contact is safe for google contacts test profile",
    )

    payload = service.execute_sink_lookup_pilot_for_job(
        job_id=job_id,
        run_id=run_id,
        sink="google_contacts",
        approved_by="operator",
        simulate=False,
    )

    assert calls[0]["sink"] == "google_contacts"
    assert payload["pilot"]["status"] == "read_only_lookup_completed"
    assert payload["pilot"]["simulated"] is False
    assert payload["pilot"]["network_calls_made"] == 1
    assert payload["pilot"]["writes_attempted"] == 0
    assert payload["pilot"]["execution_redacted"] is True
    assert payload["pilot"]["execution"]["raw_present"] is True
    assert payload["pilot"]["execution"]["raw_redacted"]["results"][0]["person"]["names"] == "[redacted]"
    assert "raw" not in payload["pilot"]["matches"][0]
    assert payload["pilot"]["matches"][0]["display"] == "[redacted]"
    assert payload["pilot"]["matches"][0]["raw_present"] is True
    assert payload["result"]["status"] == "read_only_lookup_matches"
    assert payload["result"]["network_calls_made"] == 1
    assert payload["result"]["results"][0]["matches"][0]["resource_id"] == "people/live123"
    assert payload["result"]["results"][0]["matches"][0]["display"] == "[redacted]"
    assert "raw" not in payload["result"]["results"][0]["matches"][0]


def test_service_selected_live_target_gates_non_simulated_lookup(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    calls: list[dict[str, object]] = []

    def execute(request: dict[str, object]) -> dict[str, object]:
        calls.append(request)
        return {"matches": [], "network_calls_made": 1, "writes_attempted": 0}

    service = BusinessCardService(config, sink_lookup_executor=execute)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="lookup")

    try:
        service.select_live_target_for_job(
            job_id=job_id,
            run_id=run_id,
            sink="google_contacts",
            operator="tester",
            scope="lookup",
        )
    except ValueError as exc:
        assert "safety confirmation" in str(exc)
    else:
        raise AssertionError("expected safety confirmation gate")

    try:
        service.select_live_target_for_job(
            job_id=job_id,
            run_id=run_id,
            sink="google_contacts",
            operator="tester",
            scope="lookup",
            safety_confirmation="yes",
        )
    except ValueError as exc:
        assert "tenant/profile/account" in str(exc)
    else:
        raise AssertionError("expected meaningful safety confirmation gate")

    try:
        service.select_live_target_for_job(
            job_id=job_id,
            run_id=run_id,
            sink="google_contacts",
            operator="tester",
            scope="lookup",
            safety_confirmation="<tenant-profile-account-confirmation>",
        )
    except ValueError as exc:
        assert "replace the tenant/profile/account placeholder" in str(exc)
    else:
        raise AssertionError("expected placeholder safety confirmation gate")

    try:
        service.execute_sink_lookup_pilot_for_job(
            job_id=job_id,
            run_id=run_id,
            sink="google_contacts",
            approved_by="tester",
            simulate=False,
        )
    except ValueError as exc:
        assert "selected_live_target.json" in str(exc)
    else:
        raise AssertionError("expected selected target gate")

    preselection_response = (
        f"run_id={run_id} job_id={job_id} sink=google_contacts "
        "operator=tester scope=lookup safety_confirmation=fixture contact is safe for google contacts test profile"
    )
    preselection_validation = service.validate_live_pilot_operator_response(
        run_id=run_id,
        response=preselection_response,
    )
    assert preselection_validation["state"] == "ready_to_select_live_target"
    assert preselection_validation["next_validation_step"] == "select_target"
    assert preselection_validation["select_target_command"].startswith(f"sinks select-live-target {job_id}")
    assert [item["step"] for item in preselection_validation["post_selection_sequence"]] == [
        "select_target",
        "selected_target_audit",
        "lookup_smoke_handoff",
    ]
    assert any("Run the select_target command" in item for item in preselection_validation["explicit_stop_conditions"])
    preselection_preflight = service.selected_live_target_preflight(run_id=run_id, response=preselection_response)
    assert preselection_preflight["schema"] == "business-card-watchdog.selected-live-target-preflight.v1"
    assert preselection_preflight["state"] == "ready_to_create_selected_target"
    assert preselection_preflight["would_create_selected_live_target"] is True
    assert preselection_preflight["creates_selected_live_target"] is False
    assert preselection_preflight["select_target_command"] == preselection_validation["select_target_command"]
    assert preselection_preflight["blocked_reasons"] == []
    assert preselection_preflight["approval_readback"]["response_matches_template"] is True
    assert preselection_preflight["writes_attempted"] == 0
    assert preselection_preflight["network_calls_made"] == 0
    preselection_preview = service.selected_live_target_artifact_preview(run_id=run_id, response=preselection_response)
    assert preselection_preview["schema"] == "business-card-watchdog.selected-live-target-artifact-preview.v1"
    assert preselection_preview["state"] == "ready"
    assert preselection_preview["would_create_selected_live_target"] is True
    assert preselection_preview["creates_selected_live_target"] is False
    assert preselection_preview["would_write_path"].endswith(f"{job_id}/selected_live_target.json")
    assert preselection_preview["volatile_fields"] == ["selection_id", "created_at"]
    artifact_preview = preselection_preview["artifact_preview"]
    assert artifact_preview["schema"] == "business-card-watchdog.selected-live-target.v1"
    assert artifact_preview["selection_id"] == "<generated-on-write>"
    assert artifact_preview["created_at"] == "<generated-on-write>"
    assert artifact_preview["sink"] == "google_contacts"
    assert artifact_preview["operator"] == "tester"
    assert artifact_preview["target_safety_confirmed"] is True
    assert artifact_preview["scope_allows"] == {"lookup": True, "write": False, "readback": False}
    assert artifact_preview["writes_attempted"] == 0
    assert artifact_preview["network_calls_made"] == 0
    assert preselection_preview["writes_attempted"] == 0
    assert preselection_preview["network_calls_made"] == 0
    assert not (Path(preselection_preview["would_write_path"])).exists()

    default_from_response = service.selected_live_target_from_response(
        run_id=run_id,
        response=preselection_response,
    )
    assert default_from_response["schema"] == "business-card-watchdog.selected-live-target-from-response.v1"
    assert default_from_response["state"] == "preview"
    assert default_from_response["write_selected_target"] is False
    assert default_from_response["creates_selected_live_target"] is False
    assert default_from_response["target"] is None
    assert default_from_response["target_path"] is None
    assert default_from_response["preview"]["state"] == "ready"
    assert default_from_response["writes_attempted"] == 0
    assert default_from_response["network_calls_made"] == 0
    assert not (Path(preselection_preview["would_write_path"])).exists()

    created_from_response = service.selected_live_target_from_response(
        run_id=run_id,
        response=preselection_response,
        write_selected_target=True,
        reason="fixture live lookup approval",
    )
    assert created_from_response["state"] == "created"
    assert created_from_response["write_selected_target"] is True
    assert created_from_response["creates_selected_live_target"] is True
    assert created_from_response["writes_attempted"] == 1
    assert created_from_response["network_calls_made"] == 0
    target = {"target": created_from_response["target"], "target_path": created_from_response["target_path"]}
    payload = target["target"]
    job = service.get_job(job_id, run_id=run_id)
    review_bundle = service.review_bundle(run_id=run_id)

    assert payload["schema"] == "business-card-watchdog.selected-live-target.v1"
    assert payload["scope_allows"]["lookup"] is True
    assert payload["scope_allows"]["write"] is False
    assert payload["operator"] == "tester"
    assert payload["target_safety_confirmed"] is True
    assert payload["target_safety_confirmation"] == "fixture contact is safe for google contacts test profile"
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    assert Path(target["target_path"]).exists()
    assert any(artifact["kind"] == "selected_live_target" for artifact in job["artifacts"])
    assert "selected_live_target" in review_bundle["entries"][0]["artifact_kinds"]

    preview_handoff = service.selected_live_target_handoff_from_response(
        run_id=run_id,
        response=preselection_response,
    )
    assert preview_handoff["schema"] == "business-card-watchdog.selected-live-target-handoff-from-response.v1"
    assert preview_handoff["state"] == "audit_blocked"
    assert preview_handoff["job_id"] == job_id
    assert preview_handoff["validation_state"] == "ready_for_live_lookup_request"
    assert preview_handoff["selected_target_identity"] == payload["selection_id"]
    assert preview_handoff["selected_target_audit"]["state"] == "blocked"
    assert "lookup:reviewed_contact_exists" in preview_handoff["blocked_reasons"]
    assert preview_handoff["write_audit"] is False
    assert preview_handoff["audit_written"] is False
    assert "selected-target-audit" in preview_handoff["next_safe_command"]
    assert preview_handoff["next_explicit_operator_command"] is None
    assert preview_handoff["creates_selected_live_target"] is False
    assert preview_handoff["writes_attempted"] == 0
    assert preview_handoff["network_calls_made"] == 0
    assert not (config.runs_dir / run_id / "artifacts" / job_id / "selected_live_target_audit.json").exists()

    written_handoff = service.selected_live_target_handoff_from_response(
        run_id=run_id,
        response=preselection_response,
        write_audit=True,
    )
    assert written_handoff["state"] == "audit_blocked"
    assert written_handoff["write_audit"] is True
    assert written_handoff["audit_written"] is True
    assert written_handoff["writes_attempted"] == 0
    assert written_handoff["network_calls_made"] == 0
    assert Path(written_handoff["selected_target_audit"]["audit_path"]).exists()

    lookup_handoff_preview = service.lookup_smoke_handoff_from_response(
        run_id=run_id,
        response=preselection_response,
    )
    assert lookup_handoff_preview["schema"] == "business-card-watchdog.lookup-smoke-handoff-from-response.v1"
    assert lookup_handoff_preview["state"] == "handoff_blocked"
    assert lookup_handoff_preview["job_id"] == job_id
    assert lookup_handoff_preview["sink"] == "google_contacts"
    assert lookup_handoff_preview["operator"] == "tester"
    assert lookup_handoff_preview["validation_state"] == "ready_for_live_lookup_request"
    assert lookup_handoff_preview["lookup_smoke_handoff"]["schema"] == (
        "business-card-watchdog.sink-lookup-smoke-handoff.v1"
    )
    assert lookup_handoff_preview["lookup_smoke_handoff"]["state"] == "blocked"
    assert "reviewed_contact_exists" in lookup_handoff_preview["blocked_reasons"]
    assert lookup_handoff_preview["write_handoff"] is False
    assert lookup_handoff_preview["handoff_written"] is False
    assert lookup_handoff_preview["next_explicit_operator_command"] is None
    assert lookup_handoff_preview["writes_attempted"] == 0
    assert lookup_handoff_preview["network_calls_made"] == 0
    assert not (config.runs_dir / run_id / "artifacts" / job_id / "sink_lookup_smoke_handoff.json").exists()

    lookup_handoff_written = service.lookup_smoke_handoff_from_response(
        run_id=run_id,
        response=preselection_response,
        write_handoff=True,
    )
    assert lookup_handoff_written["state"] == "handoff_blocked"
    assert lookup_handoff_written["write_handoff"] is True
    assert lookup_handoff_written["handoff_written"] is True
    assert lookup_handoff_written["writes_attempted"] == 0
    assert lookup_handoff_written["network_calls_made"] == 0
    assert Path(lookup_handoff_written["handoff_path"]).exists()

    execution_packet = service.selected_lookup_smoke_execution_packet_from_response(
        run_id=run_id,
        response=preselection_response,
    )
    assert execution_packet["schema"] == (
        "business-card-watchdog.selected-lookup-smoke-execution-packet-from-response.v1"
    )
    assert execution_packet["state"] == "blocked"
    assert execution_packet["job_id"] == job_id
    assert execution_packet["sink"] == "google_contacts"
    assert execution_packet["operator"] == "tester"
    assert execution_packet["execute_selected_lookup_smoke"] is False
    assert execution_packet["would_execute_selected_lookup_smoke"] is False
    assert execution_packet["smoke"] is None
    assert execution_packet["smoke_path"] is None
    assert "reviewed_contact_exists" in execution_packet["blocked_reasons"]
    assert execution_packet["writes_attempted"] == 0
    assert execution_packet["network_calls_made"] == 0

    blocked_execution = service.selected_lookup_smoke_execution_packet_from_response(
        run_id=run_id,
        response=preselection_response,
        execute_selected_lookup_smoke=True,
    )
    assert blocked_execution["state"] == "blocked"
    assert blocked_execution["execute_selected_lookup_smoke"] is True
    assert blocked_execution["would_execute_selected_lookup_smoke"] is False
    assert blocked_execution["smoke"] is None
    assert blocked_execution["smoke_path"] is None
    assert blocked_execution["writes_attempted"] == 0
    assert blocked_execution["network_calls_made"] == 0
    assert not (config.runs_dir / run_id / "artifacts" / job_id / "selected_lookup_smoke.json").exists()

    write_packet = service.selected_write_pilot_execution_packet_from_response(
        run_id=run_id,
        response=preselection_response,
    )
    assert write_packet["schema"] == (
        "business-card-watchdog.selected-write-pilot-execution-packet-from-response.v1"
    )
    assert write_packet["state"] == "blocked"
    assert write_packet["job_id"] == job_id
    assert write_packet["sink"] == "google_contacts"
    assert write_packet["operator"] == "tester"
    assert write_packet["execute_write_pilot"] is False
    assert write_packet["would_execute_write_pilot"] is False
    assert write_packet["write_pilot"] is None
    assert write_packet["write_pilot_path"] is None
    assert "selected target scope does not allow write" in write_packet["blocked_reasons"]
    assert "selected_lookup_smoke.json is required before write pilot" in write_packet["blocked_reasons"]
    assert "downstream_duplicate_assessment.json is required before write pilot" in write_packet["blocked_reasons"]
    assert write_packet["writes_attempted"] == 0
    assert write_packet["network_calls_made"] == 0

    blocked_write = service.selected_write_pilot_execution_packet_from_response(
        run_id=run_id,
        response=preselection_response,
        execute_write_pilot=True,
    )
    assert blocked_write["state"] == "blocked"
    assert blocked_write["execute_write_pilot"] is True
    assert blocked_write["would_execute_write_pilot"] is False
    assert blocked_write["write_pilot"] is None
    assert blocked_write["write_pilot_path"] is None
    assert blocked_write["writes_attempted"] == 0
    assert blocked_write["network_calls_made"] == 0
    assert not (config.runs_dir / run_id / "artifacts" / job_id / "sink_write_pilot.json").exists()

    readback_packet = service.selected_readback_pilot_execution_packet_from_response(
        run_id=run_id,
        response=preselection_response,
    )
    assert readback_packet["schema"] == (
        "business-card-watchdog.selected-readback-pilot-execution-packet-from-response.v1"
    )
    assert readback_packet["state"] == "blocked"
    assert readback_packet["job_id"] == job_id
    assert readback_packet["sink"] == "google_contacts"
    assert readback_packet["operator"] == "tester"
    assert readback_packet["execute_readback_pilot"] is False
    assert readback_packet["would_execute_readback_pilot"] is False
    assert readback_packet["readback_pilot"] is None
    assert readback_packet["readback_pilot_path"] is None
    assert "selected target scope does not allow readback" in readback_packet["blocked_reasons"]
    assert "sink_write_pilot.json is required before readback pilot" in readback_packet["blocked_reasons"]
    assert "sink_adapter_request_readback.json is required before readback pilot" in readback_packet[
        "blocked_reasons"
    ]
    assert readback_packet["writes_attempted"] == 0
    assert readback_packet["network_calls_made"] == 0

    blocked_readback = service.selected_readback_pilot_execution_packet_from_response(
        run_id=run_id,
        response=preselection_response,
        execute_readback_pilot=True,
    )
    assert blocked_readback["state"] == "blocked"
    assert blocked_readback["execute_readback_pilot"] is True
    assert blocked_readback["would_execute_readback_pilot"] is False
    assert blocked_readback["readback_pilot"] is None
    assert blocked_readback["readback_pilot_path"] is None
    assert blocked_readback["writes_attempted"] == 0
    assert blocked_readback["network_calls_made"] == 0
    assert not (config.runs_dir / run_id / "artifacts" / job_id / "sink_readback_pilot.json").exists()

    closeout_packet = service.live_pilot_closeout_packet_from_response(
        run_id=run_id,
        response=preselection_response,
    )
    assert closeout_packet["schema"] == "business-card-watchdog.live-pilot-closeout-packet-from-response.v1"
    assert closeout_packet["state"] == "closeout_incomplete"
    assert closeout_packet["job_id"] == job_id
    assert closeout_packet["sink"] == "google_contacts"
    assert closeout_packet["operator"] == "tester"
    assert closeout_packet["write_closeout"] is False
    assert closeout_packet["closeout_written"] is False
    assert closeout_packet["closeout_path"] is None
    assert closeout_packet["closeout_report"]["schema"] == "business-card-watchdog.live-pilot-closeout.v1"
    assert closeout_packet["closeout_report"]["state"] == "incomplete"
    assert "selected_lookup_smoke" in closeout_packet["closeout_report"]["missing_artifacts"]
    assert "downstream_duplicate_assessment" in closeout_packet["closeout_report"]["missing_artifacts"]
    assert closeout_packet["writes_attempted"] == 0
    assert closeout_packet["network_calls_made"] == 0

    workflow_packet = service.live_pilot_operator_workflow_packet_from_response(
        run_id=run_id,
        response=preselection_response,
    )
    assert workflow_packet["schema"] == (
        "business-card-watchdog.live-pilot-operator-workflow-packet-from-response.v1"
    )
    assert workflow_packet["state"] == "workflow_blocked"
    assert workflow_packet["job_id"] == job_id
    assert workflow_packet["sink"] == "google_contacts"
    assert workflow_packet["operator"] == "tester"
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

    rehearsal = service.live_pilot_operator_rehearsal_from_response(
        run_id=run_id,
        response=preselection_response,
    )
    assert rehearsal["schema"] == "business-card-watchdog.live-pilot-operator-rehearsal-from-response.v1"
    assert rehearsal["state"] == "ready_for_explicit_operator_step"
    assert rehearsal["workflow_state"] == "workflow_blocked"
    assert rehearsal["job_id"] == job_id
    assert rehearsal["sink"] == "google_contacts"
    assert rehearsal["operator"] == "tester"
    assert rehearsal["workflow_packet"]["schema"] == (
        "business-card-watchdog.live-pilot-operator-workflow-packet-from-response.v1"
    )
    assert rehearsal["next_safe_command"].startswith("runs live-pilot-operator-workflow-packet-from-response")
    assert rehearsal["next_explicit_operator_command"]
    assert rehearsal["rehearsal_steps"][0]["safe_to_auto_continue"] is True
    assert rehearsal["rehearsal_steps"][0]["executes_live_call"] is False
    assert rehearsal["rehearsal_steps"][1]["requires_explicit_operator_action"] is True
    assert rehearsal["writes_attempted"] == 0
    assert rehearsal["network_calls_made"] == 0

    preview_export = service.live_pilot_readiness_export_from_response(
        run_id=run_id,
        response=preselection_response,
        write=False,
    )
    assert preview_export["schema"] == "business-card-watchdog.live-pilot-readiness-export-from-response.v1"
    assert preview_export["state"] == "ready_for_explicit_operator_step"
    assert preview_export["write"] is False
    assert preview_export["export_written"] is False
    assert preview_export["export_path"] is None
    assert preview_export["operator_response_redacted"]["raw_response_stored"] is False
    assert "safety_confirmation" not in preview_export["operator_response_redacted"]["fields"]
    assert preselection_response not in json.dumps(preview_export, sort_keys=True)

    blocked_checklist = service.live_pilot_execution_checklist_from_response(
        run_id=run_id,
        response=preselection_response,
    )
    assert blocked_checklist["schema"] == "business-card-watchdog.live-pilot-execution-checklist-from-response.v1"
    assert blocked_checklist["state"] == "blocked"
    assert blocked_checklist["readiness_export_loaded"] is False
    assert blocked_checklist["executable_live_command"] is None
    assert "live_pilot_readiness_export.json is required before showing executable live command" in blocked_checklist[
        "blocked_reasons"
    ]
    assert blocked_checklist["writes_attempted"] == 0
    assert blocked_checklist["network_calls_made"] == 0

    readiness_export = service.live_pilot_readiness_export_from_response(
        run_id=run_id,
        response=preselection_response,
    )
    assert readiness_export["schema"] == "business-card-watchdog.live-pilot-readiness-export-from-response.v1"
    assert readiness_export["write"] is True
    assert readiness_export["export_written"] is True
    assert readiness_export["export_path"]
    export_path = Path(readiness_export["export_path"])
    assert export_path.exists()
    export_text = export_path.read_text(encoding="utf-8")
    assert preselection_response not in export_text
    assert "fixture contact is safe for google contacts test profile" not in export_text
    assert "<operator-response-redacted>" in export_text
    assert any(artifact["kind"] == "live_pilot_readiness_export" for artifact in service.list_artifacts(run_id))
    assert readiness_export["writes_attempted"] == 0
    assert readiness_export["network_calls_made"] == 0

    ready_checklist = service.live_pilot_execution_checklist_from_response(
        run_id=run_id,
        response=preselection_response,
    )
    assert ready_checklist["state"] == "ready_for_explicit_operator_command"
    assert ready_checklist["readiness_export_loaded"] is True
    assert ready_checklist["blocked_reasons"] == []
    assert ready_checklist["executable_live_command"] == rehearsal["next_explicit_operator_command"]
    assert all(item["ok"] for item in ready_checklist["checklist_items"])
    assert ready_checklist["writes_attempted"] == 0
    assert ready_checklist["network_calls_made"] == 0

    blocked_copy_packet = service.live_pilot_command_copy_packet_from_response(
        run_id=run_id,
        response=preselection_response,
    )
    assert blocked_copy_packet["schema"] == "business-card-watchdog.live-pilot-command-copy-packet-from-response.v1"
    assert blocked_copy_packet["state"] == "blocked"
    assert blocked_copy_packet["checklist_state"] == "ready_for_explicit_operator_command"
    assert blocked_copy_packet["acknowledgement_required"] is True
    assert blocked_copy_packet["acknowledgement_ok"] is False
    assert blocked_copy_packet["command_copy_text"] is None
    assert blocked_copy_packet["executable_live_command"] is None
    assert "operator acknowledgement is required before command copy text is shown" in blocked_copy_packet[
        "blocked_reasons"
    ]
    assert blocked_copy_packet["writes_attempted"] == 0
    assert blocked_copy_packet["network_calls_made"] == 0

    ready_copy_packet = service.live_pilot_command_copy_packet_from_response(
        run_id=run_id,
        response=preselection_response,
        acknowledgement=(
            f"acknowledge run_id={run_id} job_id={job_id} sink=google_contacts operator=tester copy command"
        ),
    )
    assert ready_copy_packet["state"] == "ready_for_operator_copy"
    assert ready_copy_packet["checklist_state"] == "ready_for_explicit_operator_command"
    assert ready_copy_packet["acknowledgement_ok"] is True
    assert ready_copy_packet["blocked_reasons"] == []
    assert ready_copy_packet["command_copy_text"] == ready_checklist["executable_live_command"]
    assert ready_copy_packet["executable_live_command"] == ready_checklist["executable_live_command"]
    assert ready_copy_packet["writes_attempted"] == 0
    assert ready_copy_packet["network_calls_made"] == 0

    blocked_closeout_write = service.live_pilot_closeout_packet_from_response(
        run_id=run_id,
        response=preselection_response,
        write_closeout=True,
    )
    assert blocked_closeout_write["state"] == "closeout_incomplete"
    assert blocked_closeout_write["write_closeout"] is True
    assert blocked_closeout_write["closeout_written"] is True
    assert blocked_closeout_write["closeout_path"]
    assert (config.runs_dir / run_id / "artifacts" / job_id / "live_pilot_closeout.json").exists()

    audit = service.selected_live_target_audit(job_id=job_id, run_id=run_id, scope="lookup")
    assert audit["schema"] == "business-card-watchdog.selected-live-target-audit.v1"
    assert audit["state"] == "blocked"
    assert audit["selected_target_exists"] is True
    assert audit["sink"] == "google_contacts"
    assert audit["operator"] == "tester"
    assert audit["target_safety_confirmed"] is True
    assert audit["writes_attempted"] == 0
    assert audit["network_calls_made"] == 0
    assert "lookup:reviewed_contact_exists" in audit["blocked_reasons"]
    assert "execute-lookup-smoke" in audit["commands"]["lookup_smoke"]
    assert Path(audit["audit_path"]).exists()
    assert any(artifact["kind"] == "selected_live_target_audit" for artifact in service.list_artifacts(run_id))

    closeout = service.build_live_pilot_closeout_for_job(job_id=job_id, run_id=run_id)
    assert closeout["report"]["schema"] == "business-card-watchdog.live-pilot-closeout.v1"
    assert closeout["report"]["state"] == "incomplete"
    assert closeout["report"]["sink"] == "google_contacts"
    assert closeout["report"]["operator"] == "tester"
    assert "selected_live_target_audit" not in closeout["report"]["missing_artifacts"]
    assert "selected_lookup_smoke" in closeout["report"]["missing_artifacts"]
    assert closeout["report"]["writes_attempted"] == 0
    assert closeout["report"]["network_calls_made"] == 0
    assert Path(closeout["closeout_path"]).exists()
    assert any(artifact["kind"] == "live_pilot_closeout" for artifact in service.list_artifacts(run_id))

    live_status = service.live_pilot_status(run_id=run_id)
    assert live_status["schema"] == "business-card-watchdog.live-pilot-status.v1"
    assert live_status["run_id"] == run_id
    assert live_status["job_count"] == 1
    assert live_status["counts"]["selected_target_active"] == 1
    assert live_status["writes_attempted"] == 0
    assert live_status["network_calls_made"] == 0
    assert live_status["observed_writes_attempted"] == 0
    assert live_status["commands"]["live_pilot_handoff"] == f"runs live-pilot-handoff {run_id}"
    assert live_status["commands"]["validate_operator_response"] == (
        f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
    )
    assert live_status["operator_response_contract"]["creates_selected_live_target"] is False
    assert live_status["entries"][0]["operator_response_template"] == (
        f"run_id={run_id} job_id={job_id} sink=google_contacts "
        "operator=tester scope=lookup safety_confirmation=<tenant-profile-account-confirmation>"
    )
    assert live_status["entries"][0]["commands"]["validate_operator_response"] == (
        f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
    )
    assert live_status["entries"][0]["commands"]["validate_operator_response_prefilled"] == (
        f"runs live-pilot-validate-response {run_id} "
        f"--response 'run_id={run_id} job_id={job_id} sink=google_contacts "
        "operator=tester scope=lookup safety_confirmation=<tenant-profile-account-confirmation>' --json"
    )
    assert live_status["entries"][0]["copyable_approval_fields"] == {
        "run_id": run_id,
        "job_id": job_id,
        "sink": "google_contacts",
        "operator": "tester",
        "scope": "lookup",
        "safety_confirmation": "<tenant-profile-account-confirmation>",
    }
    status_checklist = live_status["entries"][0]["pilot_command_checklist_summary"]
    assert status_checklist["schema"] == "business-card-watchdog.pilot-command-checklist-summary.v1"
    assert status_checklist["step_count"] == 5
    assert status_checklist["live_call_count"] == 1
    assert status_checklist["sink_write_step_count"] == 0
    assert [row["step"] for row in status_checklist["steps"]] == [
        "validate_operator_response",
        "create_selected_target",
        "selected_target_audit",
        "lookup_smoke_handoff",
        "live_lookup_pilot",
    ]
    status_sequence = live_status["entries"][0]["pilot_command_sequence"]
    assert status_sequence["schema"] == "business-card-watchdog.pilot-command-sequence.v1"
    assert status_sequence["safe_inspection_step_count"] == 3
    assert status_sequence["explicit_operator_step_count"] == 2
    assert status_sequence["live_call_step_count"] == 1
    assert status_sequence["sink_write_step_count"] == 0
    assert [row["step"] for row in status_sequence["safe_inspection_steps"]] == [
        "validate_operator_response",
        "selected_target_audit",
        "lookup_smoke_handoff",
    ]
    assert [row["step"] for row in status_sequence["explicit_operator_steps"]] == [
        "create_selected_target",
        "live_lookup_pilot",
    ]
    assert status_sequence["next_safe_inspection_step"]["step"] == "validate_operator_response"
    assert status_sequence["next_explicit_operator_step"]["step"] == "create_selected_target"
    assert status_sequence["execution_policy"]["do_not_run_live_or_sink_write_from_handoff"] is True
    assert Path(live_status["status_path"]).exists()

    handoff = service.live_pilot_handoff(run_id=run_id)
    assert handoff["schema"] == "business-card-watchdog.live-pilot-handoff.v1"
    assert handoff["state"] == "ready_for_live_lookup_request"
    assert handoff["action_counts"]["request_live_lookup_smoke"] == 1
    assert handoff["entries"][0]["operator_required"] is True
    assert handoff["entries"][0]["command"].startswith("sinks execute-lookup-smoke")
    assert handoff["commands"]["validate_operator_response"] == (
        f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
    )
    assert handoff["operator_response_contract"]["creates_selected_live_target"] is False
    assert handoff["entries"][0]["operator_response_template"] == (
        f"run_id={run_id} job_id={job_id} sink=google_contacts "
        "operator=tester scope=lookup safety_confirmation=<tenant-profile-account-confirmation>"
    )
    assert handoff["entries"][0]["pilot_command_checklist_summary"]["step_count"] == 5
    assert handoff["entries"][0]["pilot_command_checklist_summary"]["live_call_count"] == 1
    assert handoff["entries"][0]["pilot_command_checklist_summary"]["sink_write_step_count"] == 0
    assert handoff["entries"][0]["pilot_command_sequence"]["live_call_step_count"] == 1
    assert handoff["entries"][0]["pilot_command_sequence"]["sink_write_step_count"] == 0
    assert handoff["entries"][0]["pilot_command_sequence"]["live_call_steps"][0]["step"] == "live_lookup_pilot"
    assert handoff["operator_response_template_count"] == 1
    assert handoff["operator_response_templates"][0]["schema"] == (
        "business-card-watchdog.operator-response-template.v1"
    )
    assert handoff["operator_response_templates"][0]["template"] == (
        f"run_id={run_id} job_id={job_id} sink=google_contacts "
        "operator=tester scope=lookup safety_confirmation=<tenant-profile-account-confirmation>"
    )
    assert handoff["operator_response_templates"][0]["copyable_approval_fields"] == {
        "run_id": run_id,
        "job_id": job_id,
        "sink": "google_contacts",
        "operator": "tester",
        "scope": "lookup",
        "safety_confirmation": "<tenant-profile-account-confirmation>",
    }
    assert handoff["operator_response_templates"][0]["validation_command"] == (
        f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
    )
    assert handoff["operator_response_templates"][0]["validation_command_prefilled"] == (
        f"runs live-pilot-validate-response {run_id} "
        f"--response 'run_id={run_id} job_id={job_id} sink=google_contacts "
        "operator=tester scope=lookup safety_confirmation=<tenant-profile-account-confirmation>' --json"
    )
    assert handoff["writes_attempted"] == 0
    assert handoff["network_calls_made"] == 0
    assert Path(handoff["handoff_path"]).exists()

    approval_packet = service.live_pilot_approval_packet(run_id=run_id, job_id=job_id)
    assert approval_packet["schema"] == "business-card-watchdog.live-pilot-approval-packet.v1"
    assert approval_packet["state"] == "ready"
    assert approval_packet["run_id"] == run_id
    assert approval_packet["job_id"] == job_id
    assert approval_packet["entry_count"] == 1
    assert approval_packet["creates_selected_live_target"] is False
    assert approval_packet["writes_attempted"] == 0
    assert approval_packet["network_calls_made"] == 0
    assert approval_packet["commands"]["approval_packet"] == (
        f"runs live-pilot-approval-packet {run_id} --job-id {job_id} --json"
    )
    approval_entry = approval_packet["entries"][0]
    assert approval_entry["schema"] == "business-card-watchdog.live-pilot-approval-packet-entry.v1"
    assert approval_entry["job_id"] == job_id
    assert approval_entry["sink"] == "google_contacts"
    assert approval_entry["operator"] == "tester"
    assert approval_entry["scope"] == "lookup"
    assert approval_entry["operator_response_template"] == handoff["operator_response_templates"][0]["template"]
    assert approval_entry["copyable_approval_fields"] == handoff["operator_response_templates"][0][
        "copyable_approval_fields"
    ]
    assert approval_entry["validation_command_prefilled"] == handoff["operator_response_templates"][0][
        "validation_command_prefilled"
    ]
    assert approval_entry["next_explicit_command"] == handoff["operator_response_templates"][0]["command"]
    assert "does not create selected_live_target.json" in approval_packet["explicit_stop_conditions"][0]

    response = (
        f"run_id={run_id} job_id={job_id} sink=google_contacts "
        "operator=tester scope=lookup safety_confirmation=fixture contact is safe for google contacts test profile"
    )
    validation = service.validate_live_pilot_operator_response(run_id=run_id, response=response)
    assert validation["schema"] == "business-card-watchdog.live-pilot-operator-response-validation.v1"
    assert validation["state"] == "ready_for_live_lookup_request"
    assert validation["next_validation_step"] == "selected_target_audit"
    assert validation["missing_fields"] == []
    assert validation["mismatches"] == []
    assert validation["parsed_response"]["safety_confirmation"] == (
        "fixture contact is safe for google contacts test profile"
    )
    assert validation["matching_template"]["job_id"] == job_id
    assert validation["select_target_command"] is None
    assert validation["commands"]["select_target"] is None
    assert validation["selected_target_audit_command"] == (
        f"sinks selected-target-audit {job_id} --run-id {run_id} --scope lookup --no-write --json"
    )
    assert validation["commands"]["selected_target_audit"] == validation["selected_target_audit_command"]
    assert validation["lookup_smoke_handoff_command"] == (
        f"sinks lookup-smoke-handoff {job_id} --run-id {run_id} --sink google_contacts --approved-by tester --json"
    )
    assert validation["commands"]["lookup_smoke_handoff"] == validation["lookup_smoke_handoff_command"]
    assert [item["step"] for item in validation["post_selection_sequence"]] == [
        "selected_target_audit",
        "lookup_smoke_handoff",
    ]
    assert validation["post_selection_sequence"][0]["command"] == validation["selected_target_audit_command"]
    assert validation["post_selection_sequence"][0]["writes_runtime_artifact"] is False
    assert validation["post_selection_sequence"][1]["command"] == validation["lookup_smoke_handoff_command"]
    assert validation["post_selection_sequence"][1]["network_calls_made"] == 0
    validation_sequence = validation["validation_command_sequence"]
    assert validation_sequence["schema"] == "business-card-watchdog.pilot-command-sequence.v1"
    assert validation_sequence["safe_inspection_step_count"] == 2
    assert validation_sequence["explicit_operator_step_count"] == 0
    assert validation_sequence["live_call_step_count"] == 0
    assert validation_sequence["sink_write_step_count"] == 0
    assert [item["step"] for item in validation_sequence["safe_inspection_steps"]] == [
        "selected_target_audit",
        "lookup_smoke_handoff",
    ]
    assert validation_sequence["execution_policy"]["do_not_run_live_or_sink_write_from_handoff"] is True
    approval_readback = validation["approval_readback"]
    assert approval_readback["schema"] == "business-card-watchdog.live-pilot-operator-approval-readback.v1"
    assert approval_readback["state"] == "ready"
    assert approval_readback["validation_state"] == "ready_for_live_lookup_request"
    assert approval_readback["response_matches_template"] is True
    assert approval_readback["matched_template_job_id"] == job_id
    assert approval_readback["parsed_fields"] == {
        "run_id": run_id,
        "job_id": job_id,
        "sink": "google_contacts",
        "operator": "tester",
        "scope": "lookup",
        "safety_confirmation_present": True,
    }
    assert approval_readback["template_fields"]["operator"] == "tester"
    assert approval_readback["missing_field_count"] == 0
    assert approval_readback["mismatch_count"] == 0
    assert approval_readback["next_safe_step"] == "selected_target_audit"
    assert approval_readback["next_safe_command"] == validation["selected_target_audit_command"]
    assert approval_readback["select_target_command"] is None
    assert approval_readback["selected_target_audit_command"] == validation["selected_target_audit_command"]
    assert approval_readback["lookup_smoke_handoff_command"] == validation["lookup_smoke_handoff_command"]
    assert approval_readback["creates_selected_live_target"] is False
    assert approval_readback["writes_attempted"] == 0
    assert approval_readback["network_calls_made"] == 0
    assert any("do not run select_target again" in item for item in validation["explicit_stop_conditions"])
    assert any("lookup-smoke handoff" in item for item in validation["explicit_stop_conditions"])
    assert validation["creates_selected_live_target"] is False
    assert validation["writes_attempted"] == 0
    assert validation["network_calls_made"] == 0
    selected_preflight = service.selected_live_target_preflight(run_id=run_id, response=response)
    assert selected_preflight["state"] == "blocked"
    assert selected_preflight["would_create_selected_live_target"] is False
    assert selected_preflight["creates_selected_live_target"] is False
    assert selected_preflight["select_target_command"] is None
    assert "selected_live_target already exists" in selected_preflight["blocked_reasons"][0]
    assert selected_preflight["writes_attempted"] == 0
    assert selected_preflight["network_calls_made"] == 0
    selected_preview = service.selected_live_target_artifact_preview(run_id=run_id, response=response)
    assert selected_preview["state"] == "blocked"
    assert selected_preview["artifact_preview"] is None
    assert selected_preview["would_create_selected_live_target"] is False
    assert selected_preview["creates_selected_live_target"] is False
    assert "selected_live_target already exists" in selected_preview["blocked_reasons"][0]
    assert selected_preview["writes_attempted"] == 0
    assert selected_preview["network_calls_made"] == 0
    assert not (Path(target["target_path"]).parent / "selected_live_target_validation.json").exists()

    blocked_validation = service.validate_live_pilot_operator_response(
        run_id=run_id,
        response=f"run_id={run_id} job_id={job_id} sink=google_contacts operator=<operator> scope=lookup",
    )
    assert blocked_validation["state"] == "blocked"
    assert blocked_validation["next_validation_step"] == "fix_response"
    assert blocked_validation["select_target_command"] is None
    assert blocked_validation["selected_target_audit_command"] is None
    assert blocked_validation["lookup_smoke_handoff_command"] is None
    assert blocked_validation["post_selection_sequence"] == []
    assert blocked_validation["validation_command_sequence"]["step_count"] == 0
    assert set(blocked_validation["missing_fields"]) == {"operator", "safety_confirmation"}

    weak_safety_validation = service.validate_live_pilot_operator_response(
        run_id=run_id,
        response=(
            f"run_id={run_id} job_id={job_id} sink=google_contacts operator=tester "
            "scope=lookup safety_confirmation=yes"
        ),
    )
    assert weak_safety_validation["state"] == "blocked"
    assert weak_safety_validation["select_target_command"] is None
    assert weak_safety_validation["mismatches"] == [
        "safety_confirmation must describe the intended tenant/profile/account context"
    ]

    placeholder_safety_validation = service.validate_live_pilot_operator_response(
        run_id=run_id,
        response=(
            f"run_id={run_id} job_id={job_id} sink=google_contacts operator=tester "
            "scope=lookup safety_confirmation=<tenant-profile-account-confirmation>"
        ),
    )
    assert placeholder_safety_validation["state"] == "blocked"
    assert placeholder_safety_validation["select_target_command"] is None
    assert placeholder_safety_validation["missing_fields"] == ["safety_confirmation"]

    wrong_scope_validation = service.validate_live_pilot_operator_response(
        run_id=run_id,
        response=(
            f"run_id={run_id} job_id={job_id} sink=google_contacts operator=tester "
            "scope=all safety_confirmation=fixture contact is safe for google contacts test profile"
        ),
    )
    assert wrong_scope_validation["state"] == "blocked"
    assert wrong_scope_validation["select_target_command"] is None
    assert wrong_scope_validation["mismatches"] == ["scope does not match current operator response template"]

    requirements = service.live_selection_requirements(run_id=run_id, sink="google_contacts", write=False)
    assert requirements["state"] == "selected_target_active"
    assert requirements["entries"][0]["missing_operator_fields"] == []
    assert requirements["entries"][0]["selected_target_identity"] == payload["selection_id"]
    assert requirements["entries"][0]["selected_target_safety_confirmed"] is True

    result = service.execute_sink_lookup_pilot_for_job(
        job_id=job_id,
        run_id=run_id,
        sink="google_contacts",
        approved_by="tester",
        simulate=False,
    )
    assert result["pilot"]["simulated"] is False
    assert calls


def test_service_live_pilot_closeout_requires_selected_target_audit(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.select_live_target_for_job(
        job_id=job_id,
        run_id=run_id,
        sink="google_contacts",
        operator="tester",
        scope="lookup",
        safety_confirmation="fixture contact is safe for google contacts test profile",
    )

    missing_audit = service.build_live_pilot_closeout_for_job(job_id=job_id, run_id=run_id, write=False)

    assert missing_audit["report"]["state"] == "incomplete"
    assert "selected_live_target_audit" in missing_audit["report"]["missing_artifacts"]

    service.selected_live_target_audit(job_id=job_id, run_id=run_id, scope="lookup")
    audited = service.build_live_pilot_closeout_for_job(job_id=job_id, run_id=run_id, write=False)

    assert "selected_live_target_audit" not in audited["report"]["missing_artifacts"]
    assert audited["report"]["selected_target_audit"]["target_safety_confirmed"] is True


def test_service_live_pilot_closeout_rejects_stale_selected_target_audit_scope(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.select_live_target_for_job(
        job_id=job_id,
        run_id=run_id,
        sink="google_contacts",
        operator="tester",
        scope="all",
        safety_confirmation="fixture contact is safe for google contacts test profile",
    )
    service.selected_live_target_audit(job_id=job_id, run_id=run_id, scope="lookup")

    stale_audit = service.build_live_pilot_closeout_for_job(job_id=job_id, run_id=run_id, write=False)
    status = service.live_pilot_status(run_id=run_id, write=False)
    handoff = service.live_pilot_handoff(run_id=run_id, write=False)

    assert "selected_target_audit:scope='lookup'" in stale_audit["report"]["blocked_reasons"]
    assert status["counts"]["selected_target_audit_blocked"] == 1
    assert status["entries"][0]["selected_target_audit_blockers"] == ["scope='lookup'"]
    assert handoff["state"] == "blocked"
    assert handoff["action_counts"]["review_selected_target_audit"] == 1
    assert handoff["entries"][0]["command"].startswith("sinks selected-target-audit")

    service.selected_live_target_audit(job_id=job_id, run_id=run_id, scope="all")
    aligned_audit = service.build_live_pilot_closeout_for_job(job_id=job_id, run_id=run_id, write=False)
    aligned_status = service.live_pilot_status(run_id=run_id, write=False)

    assert "selected_target_audit:scope='lookup'" not in aligned_audit["report"]["blocked_reasons"]
    assert "selected_target_audit_blocked" not in aligned_status["counts"]


def test_service_live_pilot_closeout_rejects_stale_selected_target_evidence(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    selected = service.select_live_target_for_job(
        job_id=job_id,
        run_id=run_id,
        sink="google_contacts",
        operator="tester",
        scope="all",
        safety_confirmation="fixture contact is safe for google contacts test profile",
    )["target"]
    service.selected_live_target_audit(job_id=job_id, run_id=run_id, scope="all")
    service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
        field_corrections={"full_name": "Reviewed Fixture", "email": "fixture@example.test"},
    )
    service.plan_sinks_for_job(job_id=job_id, run_id=run_id)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="write")
    service.preflight_sink_apply(job_id=job_id, run_id=run_id)
    service.decide_sink_apply(job_id=job_id, run_id=run_id, decision="approve", reviewer="tester")
    service.build_sink_apply_pilot_readiness_for_job(job_id=job_id, run_id=run_id, sink="google_contacts")
    service.execute_sink_write_pilot_for_job(
        job_id=job_id,
        run_id=run_id,
        sink="google_contacts",
        approved_by="tester",
    )
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="readback")
    service.execute_sink_readback_pilot_for_job(
        job_id=job_id,
        run_id=run_id,
        sink="google_contacts",
        approved_by="tester",
    )
    artifact_dir = config.runs_dir / run_id / "artifacts" / job_id
    write_path = artifact_dir / "sink_write_pilot.json"
    write = json.loads(write_path.read_text(encoding="utf-8"))
    write["selected_target"] = {"selection_id": "stale-write-target"}
    write_path.write_text(json.dumps(write, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    readback_path = artifact_dir / "sink_readback_pilot.json"
    readback = json.loads(readback_path.read_text(encoding="utf-8"))
    readback["source_write_pilot"]["selected_target"] = {"selection_id": "stale-readback-target"}
    readback_path.write_text(json.dumps(readback, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report = service.build_sink_apply_pilot_report_for_job(job_id=job_id, run_id=run_id)["report"]
    report["state"] = "complete"
    report_path = artifact_dir / "sink_apply_pilot_report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    closeout = service.build_live_pilot_closeout_for_job(job_id=job_id, run_id=run_id)
    status = service.live_pilot_status(run_id=run_id, write=False)
    handoff = service.live_pilot_handoff(run_id=run_id, write=False)

    selected_identity = selected["selection_id"]
    blocked_reasons = closeout["report"]["blocked_reasons"]
    assert closeout["report"]["state"] == "incomplete"
    assert (
        f"write_pilot_selected_target_mismatch:current={selected_identity} write=stale-write-target"
        in blocked_reasons
    )
    assert (
        f"readback_source_selected_target_mismatch:current={selected_identity} readback=stale-readback-target"
        in blocked_reasons
    )
    assert any("sink_apply_pilot_report:source_write_selected_target_mismatch" in reason for reason in blocked_reasons)
    assert closeout["report"]["apply_report"]["consistency_errors"]
    assert closeout["report"]["apply_report"]["closeout_consistency_errors"]
    assert status["counts"]["live_pilot_closeout_blocked"] == 1
    closeout_blockers = [
        reason for reason in blocked_reasons if reason not in closeout["report"]["missing_artifacts"]
    ]
    assert status["entries"][0]["closeout_blockers"] == closeout_blockers
    assert handoff["state"] == "blocked"
    assert handoff["action_counts"]["review_live_pilot_closeout"] == 1
    assert handoff["entries"][0]["command"] == f"sinks live-pilot-closeout {job_id} --run-id {run_id}"
    assert handoff["entries"][0]["closeout_blockers"] == closeout_blockers


def test_service_selected_lookup_smoke_imports_redacted_duplicate_evidence(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)

    def execute(request: dict[str, object]) -> dict[str, object]:
        return {
            "status": "read_only_lookup_completed",
            "network_calls_made": 1,
            "writes_attempted": 0,
            "matches": [
                {
                    "resource_id": "people/live-smoke",
                    "confidence": 0.94,
                    "basis": ["email"],
                    "display": "Live Smoke",
                    "raw": {"person": {"names": [{"displayName": "Live Smoke"}]}},
                }
            ],
            "raw": {"results": [{"person": {"names": [{"displayName": "Live Smoke"}]}}]},
        }

    service = BusinessCardService(config, sink_lookup_executor=execute)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="lookup")
    service.select_live_target_for_job(
        job_id=job_id,
        run_id=run_id,
        sink="google_contacts",
        operator="tester",
        scope="lookup",
        safety_confirmation="fixture contact is safe for google contacts test profile",
    )

    smoke = service.execute_selected_lookup_smoke_for_job(job_id=job_id, run_id=run_id)
    job = service.get_job(job_id, run_id=run_id)
    review_bundle = service.review_bundle(run_id=run_id)

    assert smoke["smoke"]["schema"] == "business-card-watchdog.selected-lookup-smoke.v1"
    assert smoke["smoke"]["state"] == "complete"
    assert smoke["smoke"]["writes_attempted"] == 0
    assert smoke["smoke"]["network_calls_made"] == 1
    assert smoke["smoke"]["result_redacted"] is True
    assert smoke["smoke"]["downstream_duplicate_state"] == "strong_duplicate"
    assert smoke["pilot"]["execution"]["raw_present"] is True
    assert smoke["result"]["results"][0]["matches"][0]["display"] == "[redacted]"
    assert smoke["assessment"]["state"] == "strong_duplicate"
    assert any(artifact["kind"] == "selected_lookup_smoke" for artifact in job["artifacts"])
    assert "selected_lookup_smoke" in review_bundle["entries"][0]["artifact_kinds"]


def test_service_selected_lookup_smoke_rejects_lookup_writes_attempted(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)

    def execute(request: dict[str, object]) -> dict[str, object]:
        return {
            "status": "unexpected_write_attempt",
            "network_calls_made": 1,
            "writes_attempted": 1,
            "matches": [],
            "raw": {"results": []},
        }

    service = BusinessCardService(config, sink_lookup_executor=execute)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="lookup")
    service.select_live_target_for_job(
        job_id=job_id,
        run_id=run_id,
        sink="google_contacts",
        operator="tester",
        scope="lookup",
        safety_confirmation="fixture contact is safe for google contacts test profile",
    )

    try:
        service.execute_selected_lookup_smoke_for_job(job_id=job_id, run_id=run_id)
    except ValueError as exc:
        assert "writes attempted" in str(exc)
    else:
        raise AssertionError("expected lookup smoke to reject write-attempting lookup executor")

    artifact_dir = config.runs_dir / run_id / "artifacts" / job_id
    assert not (artifact_dir / "selected_lookup_smoke.json").exists()
    assert not (artifact_dir / "sink_lookup_pilot.json").exists()
    assert not (artifact_dir / "sink_lookup_result.json").exists()


def test_service_live_pilot_abandonment_blocks_abandoned_selected_target(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="lookup")
    service.select_live_target_for_job(
        job_id=job_id,
        run_id=run_id,
        sink="google_contacts",
        operator="tester",
        scope="lookup",
        safety_confirmation="fixture contact is safe for google contacts test profile",
    )

    abandonment = service.live_pilot_abandon_for_job(
        job_id=job_id,
        run_id=run_id,
        operator="tester",
        reason="wrong target profile selected",
    )
    status = service.live_pilot_status(run_id=run_id, write=False)
    handoff = service.live_pilot_handoff(run_id=run_id, write=False)

    assert abandonment["abandonment"]["schema"] == "business-card-watchdog.live-pilot-abandonment.v1"
    assert Path(abandonment["abandonment_path"]).exists()
    assert status["entries"][0]["selected_target_identity"] == abandonment["abandonment"]["selected_target_identity"]
    assert status["entries"][0]["abandonment_identity"] == abandonment["abandonment"]["selected_target_identity"]
    assert handoff["entries"][0]["selected_target_identity"] == abandonment["abandonment"]["selected_target_identity"]
    assert handoff["entries"][0]["abandonment_identity"] == abandonment["abandonment"]["selected_target_identity"]
    assert status["counts"]["abandoned"] == 1
    assert handoff["action_counts"]["select_new_live_target"] == 1
    try:
        service.execute_sink_lookup_pilot_for_job(
            job_id=job_id,
            run_id=run_id,
            sink="google_contacts",
            approved_by="tester",
            simulate=False,
        )
    except ValueError as exc:
        assert "selected target was abandoned" in str(exc)
    else:
        raise AssertionError("expected abandoned selected target to block non-simulated lookup")


def test_service_select_live_target_requires_abandonment_before_replacement(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    first = service.select_live_target_for_job(
        job_id=job_id,
        run_id=run_id,
        sink="google_contacts",
        operator="tester",
        scope="lookup",
        safety_confirmation="fixture contact is safe for google contacts test profile",
    )

    try:
        service.select_live_target_for_job(
            job_id=job_id,
            run_id=run_id,
            sink="google_contacts",
            operator="tester",
            scope="all",
            safety_confirmation="fixture contact is safe for google contacts test profile",
        )
    except ValueError as exc:
        assert "already exists" in str(exc)
    else:
        raise AssertionError("expected active selected target to block replacement")

    service.live_pilot_abandon_for_job(
        job_id=job_id,
        run_id=run_id,
        operator="tester",
        reason="replace with broader scope",
    )
    replacement = service.select_live_target_for_job(
        job_id=job_id,
        run_id=run_id,
        sink="google_contacts",
        operator="tester",
        scope="all",
        safety_confirmation="fixture contact is safe for google contacts test profile",
    )

    assert first["target"]["scope"] == "lookup"
    assert replacement["target"]["scope"] == "all"
    artifact_dir = config.runs_dir / run_id / "artifacts" / job_id
    persisted = json.loads((artifact_dir / "selected_live_target.json").read_text(encoding="utf-8"))
    assert persisted["scope"] == "all"
    requirements = service.live_selection_requirements(run_id=run_id, sink="google_contacts", write=False)
    status = service.live_pilot_status(run_id=run_id, write=False)
    handoff = service.live_pilot_handoff(run_id=run_id, write=False)
    assert requirements["entries"][0]["selected_target_identity"] == replacement["target"]["selection_id"]
    assert requirements["entries"][0]["selected_target_abandoned"] is False
    assert requirements["entries"][0]["abandonment_identity"] is None
    assert requirements["entries"][0]["abandonment_reason"] is None
    assert status["entries"][0]["selected_target_identity"] == replacement["target"]["selection_id"]
    assert status["entries"][0]["abandonment_state"] is None
    assert status["entries"][0]["abandonment_identity"] is None
    assert status["entries"][0]["abandonment_reason"] is None
    assert handoff["entries"][0]["selected_target_identity"] == replacement["target"]["selection_id"]
    assert handoff["entries"][0]["abandonment_state"] is None
    assert handoff["entries"][0]["abandonment_identity"] is None
    assert handoff["entries"][0]["abandonment_reason"] is None


def test_service_live_pilot_status_does_not_double_count_closeout_totals(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    run_id, job_id = make_recorded_run(config)
    artifact_dir = config.runs_dir / run_id / "artifacts" / job_id
    artifacts = {
        "selected_lookup_smoke": {"state": "complete", "network_calls_made": 1, "writes_attempted": 0},
        "sink_write_pilot": {"state": "complete", "network_calls_made": 1, "writes_attempted": 1},
        "sink_readback_pilot": {"state": "complete", "network_calls_made": 1, "writes_attempted": 0},
        "live_pilot_closeout": {"state": "complete", "network_calls_made": 3, "writes_attempted": 1},
    }
    for name, payload in artifacts.items():
        (artifact_dir / f"{name}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    live_status = BusinessCardService(config).live_pilot_status(run_id=run_id, write=False)

    assert live_status["counts"]["complete"] == 1
    assert live_status["observed_writes_attempted"] == 1
    assert live_status["observed_network_calls_made"] == 3


def test_service_assess_downstream_duplicates_blocks_review_and_can_resolve(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
        field_corrections={"full_name": "Reviewed Fixture", "email": "fixture@example.test"},
    )
    service.plan_sink_lookup_for_job(job_id=job_id, run_id=run_id)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="lookup")
    service.record_sink_lookup_result_for_job(
        job_id=job_id,
        run_id=run_id,
        matches_by_sink={
            "google_contacts": [
                {
                    "resource_id": "people/c123",
                    "confidence": 0.91,
                    "basis": ["email"],
                    "display": "Reviewed Fixture",
                }
            ]
        },
    )

    assessment = service.assess_downstream_duplicates_for_job(job_id=job_id, run_id=run_id)
    job = service.get_job(job_id, run_id=run_id)
    resolved = service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="resolve_duplicate",
        duplicate_resolution={"decision": "merge_existing", "target_identity": "people/c123"},
    )
    events = [
        json.loads(line)
        for line in (config.runs_dir / run_id / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert assessment["assessment"]["state"] == "strong_duplicate"
    assert assessment["job"]["state"] == "needs_review"
    assert job["state"] == "needs_review"
    assert resolved["job"]["state"] == "ready_to_route"
    assert any(artifact["kind"] == "downstream_duplicate_assessment" for artifact in job["artifacts"])
    assert any(event["event_type"] == "downstream_duplicate_assessed" for event in events)


def test_service_write_pilot_blocks_unresolved_downstream_duplicate(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
        field_corrections={"full_name": "Reviewed Fixture", "email": "fixture@example.test"},
    )
    service.plan_sink_lookup_for_job(job_id=job_id, run_id=run_id)
    service.record_sink_lookup_result_for_job(
        job_id=job_id,
        run_id=run_id,
        matches_by_sink={
            "google_contacts": [
                {
                    "resource_id": "people/c123",
                    "confidence": 0.91,
                    "basis": ["email"],
                    "display": "Reviewed Fixture",
                }
            ]
        },
    )
    service.assess_downstream_duplicates_for_job(job_id=job_id, run_id=run_id)
    service.plan_sinks_for_job(job_id=job_id, run_id=run_id)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="write")
    service.preflight_sink_apply(job_id=job_id, run_id=run_id)
    service.decide_sink_apply(job_id=job_id, run_id=run_id, decision="approve", reviewer="tester")

    try:
        service.execute_sink_write_pilot_for_job(
            job_id=job_id,
            run_id=run_id,
            sink="google_contacts",
            approved_by="tester",
        )
    except ValueError as exc:
        assert "downstream duplicate assessment" in str(exc)
    else:
        raise AssertionError("expected unresolved downstream duplicate to block write pilot")

    service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="resolve_duplicate",
        duplicate_resolution={"decision": "create_new", "reason": "verified separate contact"},
    )
    pilot = service.execute_sink_write_pilot_for_job(
        job_id=job_id,
        run_id=run_id,
        sink="google_contacts",
        approved_by="tester",
    )

    assert pilot["pilot"]["schema"] == "business-card-watchdog.sink-write-pilot.v1"
    assert pilot["pilot"]["simulated"] is True
    assert pilot["pilot"]["writes_attempted"] == 0


def test_service_next_actions_recommends_sink_lookup_for_ready_job(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
        field_corrections={"full_name": "Reviewed Fixture", "email": "fixture@example.test"},
    )

    payload = service.next_actions(run_id=run_id)

    assert payload["actions"][0]["action"] == "plan_sink_lookup"
    assert payload["actions"][0]["command"] == "sinks lookup-plan"


def test_service_next_actions_recommends_lookup_adapter_request_after_lookup_plan(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
        field_corrections={"full_name": "Reviewed Fixture", "email": "fixture@example.test"},
    )
    service.plan_sink_lookup_for_job(job_id=job_id, run_id=run_id)

    payload = service.next_actions(run_id=run_id)

    assert payload["actions"][0]["action"] == "prepare_sink_lookup_adapter"
    assert payload["actions"][0]["command"] == "sinks adapter-request --phase lookup"


def test_service_next_actions_recommends_lookup_result_after_lookup_adapter_request(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
        field_corrections={"full_name": "Reviewed Fixture", "email": "fixture@example.test"},
    )
    service.plan_sink_lookup_for_job(job_id=job_id, run_id=run_id)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="lookup")

    payload = service.next_actions(run_id=run_id)

    assert payload["actions"][0]["action"] == "record_sink_lookup_result"
    assert payload["actions"][0]["command"] == "sinks lookup-result"


def test_service_next_actions_recommends_downstream_duplicate_assessment_after_lookup_result(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
        field_corrections={"full_name": "Reviewed Fixture", "email": "fixture@example.test"},
    )
    service.plan_sink_lookup_for_job(job_id=job_id, run_id=run_id)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="lookup")
    service.record_sink_lookup_result_for_job(job_id=job_id, run_id=run_id)

    payload = service.next_actions(run_id=run_id)

    assert payload["actions"][0]["action"] == "assess_downstream_duplicates"
    assert payload["actions"][0]["command"] == "sinks assess-duplicates"


def test_service_next_actions_recommends_sink_plan_after_downstream_duplicate_assessment(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
        field_corrections={"full_name": "Reviewed Fixture", "email": "fixture@example.test"},
    )
    service.plan_sink_lookup_for_job(job_id=job_id, run_id=run_id)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="lookup")
    service.record_sink_lookup_result_for_job(job_id=job_id, run_id=run_id)
    service.assess_downstream_duplicates_for_job(job_id=job_id, run_id=run_id)

    payload = service.next_actions(run_id=run_id)

    assert payload["actions"][0]["action"] == "plan_sinks"


def test_service_next_actions_recommends_write_adapter_request_after_sink_plan(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
        field_corrections={"full_name": "Reviewed Fixture", "email": "fixture@example.test"},
    )
    service.plan_sink_lookup_for_job(job_id=job_id, run_id=run_id)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="lookup")
    service.record_sink_lookup_result_for_job(job_id=job_id, run_id=run_id)
    service.assess_downstream_duplicates_for_job(job_id=job_id, run_id=run_id)
    service.plan_sinks_for_job(job_id=job_id, run_id=run_id)

    payload = service.next_actions(run_id=run_id)

    assert payload["actions"][0]["action"] == "prepare_sink_write_adapter"
    assert payload["actions"][0]["command"] == "sinks adapter-request --phase write"


def test_service_next_actions_recommends_apply_preflight_after_write_adapter_request(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
        field_corrections={"full_name": "Reviewed Fixture", "email": "fixture@example.test"},
    )
    service.plan_sink_lookup_for_job(job_id=job_id, run_id=run_id)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="lookup")
    service.record_sink_lookup_result_for_job(job_id=job_id, run_id=run_id)
    service.assess_downstream_duplicates_for_job(job_id=job_id, run_id=run_id)
    service.plan_sinks_for_job(job_id=job_id, run_id=run_id)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="write")

    payload = service.next_actions(run_id=run_id)

    assert payload["actions"][0]["action"] == "preflight_sink_apply"
    assert payload["actions"][0]["command"] == "sinks apply-preflight"


def test_service_next_actions_recommends_apply_decision_after_preflight(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
        field_corrections={"full_name": "Reviewed Fixture", "email": "fixture@example.test"},
    )
    service.plan_sink_lookup_for_job(job_id=job_id, run_id=run_id)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="lookup")
    service.record_sink_lookup_result_for_job(job_id=job_id, run_id=run_id)
    service.assess_downstream_duplicates_for_job(job_id=job_id, run_id=run_id)
    service.plan_sinks_for_job(job_id=job_id, run_id=run_id)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="write")
    service.preflight_sink_apply(job_id=job_id, run_id=run_id)

    payload = service.next_actions(run_id=run_id)

    assert payload["actions"][0]["action"] == "decide_sink_apply"
    assert payload["actions"][0]["command"] == "sinks apply-decision"


def test_service_run_next_actions_executes_safe_steps_until_manual_decision(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
        field_corrections={"full_name": "Reviewed Fixture", "email": "fixture@example.test"},
    )

    payload = service.run_next_actions(run_id=run_id, limit=10)
    job = service.get_job(job_id, run_id=run_id)

    assert [item["action"] for item in payload["executed"]] == [
        "plan_sink_lookup",
        "prepare_sink_lookup_adapter",
        "record_sink_lookup_result",
        "assess_downstream_duplicates",
        "plan_sinks",
        "prepare_sink_write_adapter",
        "preflight_sink_apply",
    ]
    assert payload["skipped"][0]["action"] == "decide_sink_apply"
    assert payload["skipped"][0]["status"] == "skipped"
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    assert "plan_sink_lookup" in payload["safe_auto_actions"]
    assert "execute_sink_write_pilot" in payload["explicit_operator_actions"]
    assert payload["safe_inspection_commands"] == {
        "live_pilot_status": f"runs live-pilot-status {run_id} --no-write --json",
        "live_pilot_handoff": f"runs live-pilot-handoff {run_id} --no-write --json",
        "operator_dashboard": f"operator-dashboard --run-id {run_id} --json",
        "service_recovery": f"service recovery --run-id {run_id} --json",
    }
    assert any("Do not run live lookup" in condition for condition in payload["operator_stop_conditions"])
    assert all(item["safe_to_auto_continue"] is True for item in payload["executed"])
    assert payload["skipped"][0]["safe_to_auto_continue"] is False
    assert payload["skipped"][0]["requires_explicit_operator_action"] is True
    assert payload["phase_report_before"]["schema"] == "business-card-watchdog.phase-report.v1"
    assert payload["phase_report_before"]["phases"][5]["phase"] == "route"
    assert payload["phase_report_after"]["schema"] == "business-card-watchdog.phase-report.v1"
    assert payload["phase_report_after"]["phases"][5]["counts"]["complete"] == 1
    assert payload["phase_report_after"]["phases"][7]["counts"]["explicit_required"] == 1
    assert {artifact["kind"] for artifact in job["artifacts"]} >= {
        "sink_lookup_plan",
        "sink_adapter_request_lookup",
        "sink_lookup_result",
        "downstream_duplicate_assessment",
        "sink_plan",
        "sink_adapter_request_write",
        "sink_apply_preflight",
    }


def test_service_review_update_refreshes_stale_route_artifacts(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
        field_corrections={"full_name": "Old Fixture", "email": "old@example.test"},
    )
    service.run_next_actions(run_id=run_id, limit=10)
    artifact_dir = config.runs_dir / run_id / "artifacts" / job_id
    stale_artifact_payloads = {
        kind: json.loads((artifact_dir / filename).read_text(encoding="utf-8"))
        for kind, filename in {
            "sink_lookup_plan": "sink_lookup_plan.json",
            "sink_adapter_request_lookup": "sink_adapter_request_lookup.json",
            "sink_lookup_result": "sink_lookup_result.json",
            "downstream_duplicate_assessment": "downstream_duplicate_assessment.json",
            "sink_plan": "sink_plan.json",
            "sink_adapter_request_write": "sink_adapter_request_write.json",
            "sink_apply_preflight": "sink_apply_preflight.json",
        }.items()
    }

    result = service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
        field_corrections={"full_name": "Reviewed Fixture", "email": "new@example.test"},
    )
    next_action = service.next_actions(run_id=run_id)["actions"][0]
    rerun = service.run_next_actions(run_id=run_id, limit=10)
    route_refresh = json.loads((artifact_dir / "route_refresh.json").read_text(encoding="utf-8"))
    lookup_plan = json.loads((artifact_dir / "sink_lookup_plan.json").read_text(encoding="utf-8"))
    sink_plan = json.loads((artifact_dir / "sink_plan.json").read_text(encoding="utf-8"))
    events = [
        json.loads(line)
        for line in (config.runs_dir / run_id / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert result["route_refresh"]["schema"] == "business-card-watchdog.route-refresh.v1"
    assert result["route_refresh"]["stale_artifact_kinds"] == [
        "sink_lookup_plan",
        "sink_adapter_request_lookup",
        "sink_lookup_result",
        "downstream_duplicate_assessment",
        "sink_plan",
        "sink_adapter_request_write",
        "sink_apply_preflight",
    ]
    assert result["route_refresh"]["pending_artifact_kinds"] == result["route_refresh"]["stale_artifact_kinds"]
    assert next_action["action"] == "plan_sink_lookup"
    assert next_action["route_refresh_path"].endswith("route_refresh.json")
    assert [item["action"] for item in rerun["executed"]] == [
        "plan_sink_lookup",
        "prepare_sink_lookup_adapter",
        "record_sink_lookup_result",
        "assess_downstream_duplicates",
        "plan_sinks",
        "prepare_sink_write_adapter",
        "preflight_sink_apply",
    ]
    assert route_refresh["state"] == "complete"
    assert route_refresh["pending_artifact_kinds"] == []
    assert route_refresh["refreshed_artifact_kinds"] == result["route_refresh"]["stale_artifact_kinds"]
    assert stale_artifact_payloads["sink_lookup_plan"]["lookups"][0]["match_keys"]["email"] == "old@example.test"
    assert stale_artifact_payloads["sink_plan"]["actions"][0]["match_keys"]["email"] == "old@example.test"
    assert lookup_plan["lookups"][0]["match_keys"]["email"] == "new@example.test"
    assert sink_plan["actions"][0]["match_keys"]["email"] == "new@example.test"
    assert any(event["event_type"] == "route_refresh_requested" for event in events)
    assert any(event["event_type"] == "route_refresh_updated" for event in events)


def test_service_review_update_stales_full_pilot_chain_and_safe_refresh_stops_at_pilot(
    tmp_path: Path,
) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
        field_corrections={"full_name": "Old Fixture", "email": "old@example.test"},
    )
    service.plan_sink_lookup_for_job(job_id=job_id, run_id=run_id)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="lookup")
    service.execute_sink_lookup_pilot_for_job(
        job_id=job_id,
        run_id=run_id,
        sink="google_contacts",
        approved_by="tester",
        matches=[],
    )
    service.assess_downstream_duplicates_for_job(job_id=job_id, run_id=run_id)
    service.plan_sinks_for_job(job_id=job_id, run_id=run_id)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="write")
    service.preflight_sink_apply(job_id=job_id, run_id=run_id)
    service.decide_sink_apply(job_id=job_id, run_id=run_id, decision="approve", reviewer="tester")
    service.build_sink_apply_pilot_readiness_for_job(job_id=job_id, run_id=run_id)
    service.execute_sink_write_pilot_for_job(
        job_id=job_id,
        run_id=run_id,
        sink="google_contacts",
        approved_by="tester",
    )
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="readback")
    service.execute_sink_readback_pilot_for_job(
        job_id=job_id,
        run_id=run_id,
        sink="google_contacts",
        approved_by="tester",
    )
    service.build_sink_apply_pilot_report_for_job(job_id=job_id, run_id=run_id)
    artifact_dir = config.runs_dir / run_id / "artifacts" / job_id

    result = service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
        field_corrections={"full_name": "Reviewed Fixture", "email": "new@example.test"},
    )
    safe_refresh = service.run_next_actions(run_id=run_id, limit=10)
    route_refresh = json.loads((artifact_dir / "route_refresh.json").read_text(encoding="utf-8"))
    lookup_plan = json.loads((artifact_dir / "sink_lookup_plan.json").read_text(encoding="utf-8"))

    assert result["route_refresh"]["stale_artifact_kinds"] == [
        "sink_lookup_plan",
        "sink_adapter_request_lookup",
        "sink_lookup_pilot",
        "sink_lookup_result",
        "downstream_duplicate_assessment",
        "sink_plan",
        "sink_adapter_request_write",
        "sink_apply_preflight",
        "sink_apply_decision",
        "sink_apply_pilot_readiness",
        "sink_write_pilot",
        "sink_apply_result",
        "sink_adapter_request_readback",
        "sink_readback_pilot",
        "sink_apply_pilot_report",
    ]
    assert [item["action"] for item in safe_refresh["executed"]] == [
        "plan_sink_lookup",
        "prepare_sink_lookup_adapter",
    ]
    assert safe_refresh["skipped"][0]["action"] == "execute_sink_lookup_pilot"
    assert safe_refresh["skipped"][0]["route_refresh_path"].endswith("route_refresh.json")
    assert route_refresh["state"] == "pending"
    assert route_refresh["refreshed_artifact_kinds"] == [
        "sink_lookup_plan",
        "sink_adapter_request_lookup",
    ]
    assert route_refresh["pending_artifact_kinds"][0] == "sink_lookup_pilot"
    assert "sink_write_pilot" in route_refresh["pending_artifact_kinds"]
    assert "sink_readback_pilot" in route_refresh["pending_artifact_kinds"]
    assert lookup_plan["lookups"][0]["match_keys"]["email"] == "new@example.test"


def test_service_enrichment_merge_refreshes_existing_sink_plan(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    artifact_dir = config.runs_dir / run_id / "artifacts" / job_id
    service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
        field_corrections={"full_name": "Ada Lovelace", "email": "ada@example.test", "notes": "Card note"},
    )
    service.plan_sinks_for_job(job_id=job_id, run_id=run_id)
    (artifact_dir / "enrichment_result.json").write_text(
        json.dumps(
            {
                "schema": "business-card-watchdog.enrichment-result.v1",
                "merge_proposals": [
                    {
                        "field": "notes",
                        "value": "Public-web corroboration candidate: https://example.test/ada",
                        "source": "public_web",
                        "requires_review": True,
                    }
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    result = service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_enrichment_merge",
        approved_enrichment_fields=["notes"],
    )
    next_action = service.next_actions(run_id=run_id)["actions"][0]
    refreshed = service.plan_sinks_for_job(job_id=job_id, run_id=run_id)
    route_refresh = json.loads((artifact_dir / "route_refresh.json").read_text(encoding="utf-8"))

    assert result["route_refresh"]["reason"] == "enrichment_merge_updated_reviewed_contact"
    assert result["route_refresh"]["pending_artifact_kinds"] == ["sink_plan"]
    assert next_action["action"] == "plan_sinks"
    assert route_refresh["state"] == "complete"
    assert "Public-web corroboration candidate" in refreshed["plan"]["payloads"][0]["payload"]["values"]["notes"]


def test_service_sink_plan_preserves_profile_url_contact_points(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, odoo=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts", "odoo"]}],
    )
    run_id, job_id = make_recorded_run(config)
    artifact_dir = config.runs_dir / run_id / "artifacts" / job_id
    candidate = build_contact_candidate(
        {
            "full_name": "Ada Lovelace",
            "email": "ada@example.test",
            "linkedin_url": "linkedin.com/in/ada-lovelace",
        }
    )
    (artifact_dir / "contact_candidate.json").write_text(json.dumps(candidate, indent=2), encoding="utf-8")

    plan = BusinessCardService(config).plan_sinks_for_job(job_id=job_id, run_id=run_id)["plan"]

    for payload in plan["payloads"]:
        assert {
            "kind": "profile_url",
            "value": "https://linkedin.com/in/ada-lovelace",
            "label": "linkedin_url",
        } in payload["payload"]["values"]["contact_points"]


def test_service_duplicate_resolution_refreshes_existing_sink_plan(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    artifact_dir = config.runs_dir / run_id / "artifacts" / job_id
    service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
        field_corrections={"full_name": "Ada Lovelace", "email": "ada@example.test"},
    )
    service.plan_sinks_for_job(job_id=job_id, run_id=run_id)
    (artifact_dir / "duplicate_assessment.json").write_text(
        json.dumps(
            {
                "schema": "business-card-watchdog.duplicate-assessment.v1",
                "state": "strong_duplicate",
                "matches": [{"match_type": "email", "serialization_key": "email:ada@example.test"}],
                "reasons": ["email match"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    result = service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="resolve_duplicate",
        duplicate_resolution={
            "decision": "merge_existing",
            "target_identity": "email:ada@example.test",
            "reason": "same contact",
        },
    )
    next_action = service.next_actions(run_id=run_id)["actions"][0]
    refreshed = service.plan_sinks_for_job(job_id=job_id, run_id=run_id)
    route_refresh = json.loads((artifact_dir / "route_refresh.json").read_text(encoding="utf-8"))

    assert result["route_refresh"]["reason"] == "duplicate_resolution_updated_route_context"
    assert result["route_refresh"]["pending_artifact_kinds"] == ["sink_plan"]
    assert next_action["action"] == "plan_sinks"
    assert route_refresh["state"] == "complete"
    assert refreshed["plan"]["duplicate_resolution"]["decision"] == "merge_existing"


def test_service_next_actions_recommends_live_apply_after_decision(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
        field_corrections={"full_name": "Reviewed Fixture", "email": "fixture@example.test"},
    )
    service.plan_sink_lookup_for_job(job_id=job_id, run_id=run_id)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="lookup")
    service.record_sink_lookup_result_for_job(job_id=job_id, run_id=run_id)
    service.assess_downstream_duplicates_for_job(job_id=job_id, run_id=run_id)
    service.plan_sinks_for_job(job_id=job_id, run_id=run_id)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="write")
    service.preflight_sink_apply(job_id=job_id, run_id=run_id)
    service.decide_sink_apply(job_id=job_id, run_id=run_id, decision="approve", reviewer="tester")

    payload = service.next_actions(run_id=run_id)

    assert payload["actions"][0]["action"] == "prepare_sink_apply_pilot_readiness"
    assert payload["actions"][0]["command"] == "sinks apply-pilot-readiness"
    assert payload["actions"][0]["safe_to_auto_continue"] is True
    assert payload["actions"][0]["requires_explicit_operator_action"] is False

    readiness = service.build_sink_apply_pilot_readiness_for_job(job_id=job_id, run_id=run_id)
    next_payload = service.next_actions(run_id=run_id)

    assert readiness["readiness"]["schema"] == "business-card-watchdog.sink-apply-pilot-readiness.v1"
    assert readiness["readiness"]["can_apply_pilot"] is True
    assert readiness["readiness"]["can_mock_apply_pilot"] is True
    assert readiness["readiness"]["can_live_apply_pilot"] is False
    assert readiness["readiness"]["state"] == "ready_for_mock_apply"
    assert readiness["readiness"]["writes_attempted"] == 0
    assert readiness["readiness"]["network_calls_made"] == 0
    assert "readback_adapter_available_after_apply" in readiness["readiness"]["missing_requirements"]
    assert readiness["readiness"]["mock_missing_requirements"] == []
    assert "readback_adapter_available_after_apply" in readiness["readiness"]["live_missing_requirements"]
    assert next_payload["actions"][0]["action"] == "execute_sink_write_pilot"
    assert next_payload["actions"][0]["command"] == "sinks write-pilot"
    assert next_payload["actions"][0]["safe_to_auto_continue"] is False
    assert next_payload["actions"][0]["requires_explicit_operator_action"] is True


def test_service_next_actions_recommends_readback_adapter_request_after_apply_result(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
        field_corrections={"full_name": "Reviewed Fixture", "email": "fixture@example.test"},
    )
    service.plan_sink_lookup_for_job(job_id=job_id, run_id=run_id)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="lookup")
    service.record_sink_lookup_result_for_job(job_id=job_id, run_id=run_id)
    service.assess_downstream_duplicates_for_job(job_id=job_id, run_id=run_id)
    service.plan_sinks_for_job(job_id=job_id, run_id=run_id)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="write")
    service.preflight_sink_apply(job_id=job_id, run_id=run_id)
    service.decide_sink_apply(job_id=job_id, run_id=run_id, decision="approve", reviewer="tester")
    service.apply_sinks_for_job(job_id=job_id, run_id=run_id, apply=True, simulate=True)

    payload = service.next_actions(run_id=run_id)

    assert payload["actions"][0]["action"] == "prepare_sink_readback_adapter"
    assert payload["actions"][0]["command"] == "sinks adapter-request --phase readback"


def test_service_simulated_apply_requires_ready_pilot_readiness(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
        field_corrections={"full_name": "Reviewed Fixture", "email": "fixture@example.test"},
    )
    service.plan_sink_lookup_for_job(job_id=job_id, run_id=run_id)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="lookup")
    service.record_sink_lookup_result_for_job(job_id=job_id, run_id=run_id)
    service.assess_downstream_duplicates_for_job(job_id=job_id, run_id=run_id)
    service.plan_sinks_for_job(job_id=job_id, run_id=run_id)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="write")
    service.preflight_sink_apply(job_id=job_id, run_id=run_id)
    service.decide_sink_apply(job_id=job_id, run_id=run_id, decision="approve", reviewer="tester")

    result = service.apply_sinks_for_job(job_id=job_id, run_id=run_id, apply=True, simulate=True)
    readiness_path = config.runs_dir / run_id / "artifacts" / job_id / "sink_apply_pilot_readiness.json"

    assert readiness_path.exists()
    assert result["result"]["state"] == "mock_applied"
    assert result["result"]["simulated"] is True
    assert result["result"]["writes_attempted"] == 0
    assert result["result"]["readback"][0]["simulated"] is True


def test_service_safe_loop_and_manual_steps_complete_simulated_pilot_chain(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
        field_corrections={"full_name": "Reviewed Fixture", "email": "fixture@example.test"},
    )

    safe_prefix = service.run_next_actions(run_id=run_id, limit=10)
    assert [item["action"] for item in safe_prefix["executed"]] == [
        "plan_sink_lookup",
        "prepare_sink_lookup_adapter",
        "record_sink_lookup_result",
        "assess_downstream_duplicates",
        "plan_sinks",
        "prepare_sink_write_adapter",
        "preflight_sink_apply",
    ]
    assert safe_prefix["skipped"][0]["action"] == "decide_sink_apply"

    service.decide_sink_apply(job_id=job_id, run_id=run_id, decision="approve", reviewer="tester")
    readiness_prefix = service.run_next_actions(run_id=run_id, limit=10)
    assert [item["action"] for item in readiness_prefix["executed"]] == [
        "prepare_sink_apply_pilot_readiness"
    ]
    assert readiness_prefix["skipped"][0]["action"] == "execute_sink_write_pilot"
    before_pilot = service.pilot_readiness_report(run_id)
    assert before_pilot["state"] == "ready_for_write_pilot"
    assert before_pilot["ready_job_ids"] == [job_id]
    assert before_pilot["explicit_action_job_ids"] == [job_id]

    write_pilot = service.execute_sink_write_pilot_for_job(
        job_id=job_id,
        run_id=run_id,
        sink="google_contacts",
        approved_by="tester",
    )
    apply_result = service.apply_sinks_for_job(job_id=job_id, run_id=run_id, apply=True, simulate=True)
    readback_prefix = service.run_next_actions(run_id=run_id, limit=10)
    assert write_pilot["pilot"]["simulated"] is True
    assert write_pilot["pilot"]["writes_attempted"] == 0
    assert apply_result["result"]["state"] == "mock_applied"
    assert apply_result["result"]["writes_attempted"] == 0
    assert [item["action"] for item in readback_prefix["executed"]] == [
        "prepare_sink_readback_adapter"
    ]
    assert readback_prefix["skipped"][0]["action"] == "execute_sink_readback_pilot"

    readback_pilot = service.execute_sink_readback_pilot_for_job(
        job_id=job_id,
        run_id=run_id,
        sink="google_contacts",
        approved_by="tester",
    )
    report_prefix = service.run_next_actions(run_id=run_id, limit=10)
    final_readiness = service.pilot_readiness_report(run_id)
    final_phase_report = service.phase_report(run_id)
    job = service.get_job(job_id, run_id=run_id)

    assert readback_pilot["pilot"]["state"] == "verified"
    assert readback_pilot["pilot"]["writes_attempted"] == 0
    assert [item["action"] for item in report_prefix["executed"]] == [
        "prepare_sink_apply_pilot_report"
    ]
    assert final_readiness["state"] == "complete"
    assert final_readiness["counts"]["complete"] == 1
    assert final_readiness["counts"]["pilot_report_complete"] == 1
    assert final_readiness["pilot_complete_job_ids"] == [job_id]
    assert final_readiness["writes_attempted"] == 0
    assert final_readiness["network_calls_made"] == 0
    assert final_phase_report["jobs"][0]["phase_states"]["pilot_report"] == "complete"
    assert {artifact["kind"] for artifact in job["artifacts"]} >= {
        "sink_lookup_plan",
        "sink_adapter_request_lookup",
        "sink_lookup_result",
        "downstream_duplicate_assessment",
        "sink_plan",
        "sink_adapter_request_write",
        "sink_apply_preflight",
        "sink_apply_decision",
        "sink_apply_pilot_readiness",
        "sink_write_pilot",
        "sink_apply_result",
        "sink_adapter_request_readback",
        "sink_readback_pilot",
        "sink_apply_pilot_report",
    }


def test_service_live_lookup_readiness_blocks_until_requirements_exist(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    run_id, job_id = make_recorded_run(config)
    report = BusinessCardService(config).live_lookup_readiness_report(
        job_id=job_id,
        run_id=run_id,
        sink="google_contacts",
    )

    assert report["schema"] == "business-card-watchdog.live-lookup-readiness.v1"
    assert report["state"] == "blocked"
    assert report["writes_attempted"] == 0
    assert report["network_calls_made"] == 0
    assert "job_ready_to_route" in report["missing_requirements"]
    assert "reviewed_contact_exists" in report["missing_requirements"]
    assert "selected_sink_enabled" in report["missing_requirements"]
    assert "lookup_adapter_request_exists" in report["missing_requirements"]
    assert report["commands"]["live_lookup_pilot"].endswith("--no-simulate")


def test_service_live_lookup_readiness_ready_with_local_gws_evidence(tmp_path: Path, monkeypatch) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gws = bin_dir / "gws"
    gws.write_text("#!/bin/sh\nprintf '{}\\n'\n", encoding="utf-8")
    gws.chmod(0o755)
    gws_config = tmp_path / "gws-config"
    gws_config.mkdir()
    (gws_config / "credentials.enc").write_text("fixture\n", encoding="utf-8")
    monkeypatch.setenv("PATH", f"{bin_dir}:{str(Path('/usr/bin'))}")
    monkeypatch.setenv("GOOGLE_WORKSPACE_CLI_CONFIG_DIR", str(gws_config))
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, google_contacts_profile="codex", dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
        field_corrections={"full_name": "Reviewed Fixture", "email": "fixture@example.test"},
    )
    service.run_next_actions(run_id=run_id, limit=2)

    report = service.live_lookup_readiness_report(job_id=job_id, run_id=run_id, sink="google_contacts")

    assert report["state"] == "ready"
    assert report["missing_requirements"] == []
    assert report["live_lookup_readiness"]["status"] == "ready"
    assert report["live_lookup_readiness"]["details"]["auth_evidence_present"] is True
    assert report["lookup_plan_state"] == "dry_run"
    assert report["writes_attempted"] == 0
    assert report["network_calls_made"] == 0


def test_service_submit_review_rejects_unknown_fields(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)

    try:
        service.submit_review(
            job_id=job_id,
            run_id=run_id,
            reviewer="tester",
            action="keep_needs_review",
            field_corrections={"linkedin": "invented"},
        )
    except ValueError as exc:
        assert "unsupported field corrections" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_service_submit_review_supports_request_enrichment_reject_and_skip(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    service = BusinessCardService(config)

    enrich_run_id, enrich_job_id = make_recorded_run(config, run_id="run-enrich")
    enrich = service.submit_review(
        job_id=enrich_job_id,
        run_id=enrich_run_id,
        reviewer="tester",
        action="request_enrichment",
        notes="needs public web corroboration",
    )
    assert enrich["job"]["state"] == "needs_review"

    reject_run_id, reject_job_id = make_recorded_run(config, run_id="run-reject")
    rejected = service.submit_review(
        job_id=reject_job_id,
        run_id=reject_run_id,
        reviewer="tester",
        action="reject_not_card",
    )
    assert rejected["job"]["state"] == "failed"
    assert "not a business card" in str(rejected["job"]["error"])

    skip_run_id, skip_job_id = make_recorded_run(config, run_id="run-skip")
    skipped = service.submit_review(
        job_id=skip_job_id,
        run_id=skip_run_id,
        reviewer="tester",
        action="skip",
    )
    assert skipped["job"]["state"] == "cancelled"


def test_service_submit_review_approves_enrichment_merge(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    run_id, job_id = make_recorded_run(config)
    artifact_dir = config.runs_dir / run_id / "artifacts" / job_id
    candidate = build_contact_candidate({"full_name": "Ada Lovelace", "notes": "Card note"})
    (artifact_dir / "contact_candidate.json").write_text(json.dumps(candidate, indent=2), encoding="utf-8")
    enrichment_result_path = artifact_dir / "enrichment_result.json"
    enrichment_result_path.write_text(
        json.dumps(
            {
                "schema": "business-card-watchdog.enrichment-result.v1",
                "provider": "public_web",
                "merge_proposals": [
                    {
                        "field": "notes",
                        "value": "Public-web corroboration candidate: https://example.test/ada",
                        "source": "public_web",
                        "requires_review": True,
                    },
                    {
                        "field": "title",
                        "value": "Principal Engineer",
                        "source": "public_web",
                        "requires_review": True,
                    }
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    RunLedger(config.runs_dir / run_id).record_artifact(
        job_id=job_id,
        kind="enrichment_result",
        path=enrichment_result_path,
    )
    service = BusinessCardService(config)

    result = service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_enrichment_merge",
        approved_enrichment_fields=["notes"],
    )
    reviewed = json.loads((artifact_dir / "reviewed_contact.json").read_text(encoding="utf-8"))
    merge_review = json.loads((artifact_dir / "enrichment_merge_review.json").read_text(encoding="utf-8"))
    proposal_review = json.loads(
        (artifact_dir / "enrichment_proposal_review.json").read_text(encoding="utf-8")
    )
    job = service.get_job(job_id, run_id=run_id)
    bundle = service.review_bundle(run_id=run_id)
    workbook = service.review_workbook(run_id=run_id, write=False)
    workbook_rows = list(csv.DictReader(StringIO(workbook["csv"])))
    events = [
        json.loads(line)
        for line in (config.runs_dir / run_id / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert result["submission"]["approved_enrichment_fields"] == ["notes"]
    assert job["state"] == "ready_to_route"
    assert reviewed["observed"]["notes"]["source"] == "approved_enrichment"
    assert "Card note" in reviewed["flat"]["notes"]
    assert merge_review["applied"][0]["field"] == "notes"
    assert proposal_review["schema"] == "business-card-watchdog.enrichment-proposal-review.v1"
    assert proposal_review["accepted_count"] == 1
    assert proposal_review["rejected_count"] == 1
    assert proposal_review["proposals"][0]["decision"] == "accepted"
    assert proposal_review["proposals"][1]["decision"] == "rejected"
    assert bundle["entries"][0]["review_matrix"]["enrichment_state"] == "reviewed"
    assert bundle["entries"][0]["review_matrix"]["enrichment_accepted_count"] == 1
    assert bundle["entries"][0]["review_matrix"]["enrichment_rejected_count"] == 1
    assert workbook_rows[0]["matrix_enrichment_accepted_count"] == "1"
    assert workbook_rows[0]["matrix_enrichment_rejected_count"] == "1"
    assert any(artifact["kind"] == "enrichment_merge_review" for artifact in job["artifacts"])
    assert any(artifact["kind"] == "enrichment_proposal_review" for artifact in job["artifacts"])
    assert any(event["event_type"] == "enrichment_merge_reviewed" for event in events)
    assert any(event["payload"].get("rejected_count") == 1 for event in events if event["event_type"] == "enrichment_merge_reviewed")


def test_service_submit_review_resolves_duplicate_for_routing(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    artifact_dir = config.runs_dir / run_id / "artifacts" / job_id
    (artifact_dir / "duplicate_assessment.json").write_text(
        json.dumps(
            {
                "schema": "business-card-watchdog.duplicate-assessment.v1",
                "state": "strong_duplicate",
                "matches": [{"match_type": "email", "serialization_key": "email:ada@example.test"}],
                "reasons": ["email match"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    service = BusinessCardService(config)

    result = service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="resolve_duplicate",
        duplicate_resolution={
            "decision": "merge_existing",
            "target_identity": "email:ada@example.test",
            "reason": "same contact",
        },
    )
    plan = service.plan_sinks_for_job(job_id=job_id, run_id=run_id)
    resolution = json.loads((artifact_dir / "duplicate_resolution.json").read_text(encoding="utf-8"))
    resolution_index = config.data_dir / "identity" / "duplicate-resolutions.jsonl"
    job = service.get_job(job_id, run_id=run_id)
    events = [
        json.loads(line)
        for line in (config.runs_dir / run_id / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert result["job"]["state"] == "ready_to_route"
    assert resolution["decision"] == "merge_existing"
    assert resolution_index.exists()
    assert json.loads(resolution_index.read_text(encoding="utf-8").splitlines()[0])["decision"] == "merge_existing"
    assert job["state"] == "ready_to_route"
    assert plan["plan"]["duplicate_resolution"]["decision"] == "merge_existing"
    assert any(artifact["kind"] == "duplicate_resolution" for artifact in job["artifacts"])
    assert any(event["event_type"] == "duplicate_resolved" for event in events)


def test_service_submit_review_resolves_duplicate_noop_as_cancelled(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    run_id, job_id = make_recorded_run(config)
    artifact_dir = config.runs_dir / run_id / "artifacts" / job_id
    (artifact_dir / "duplicate_assessment.json").write_text(
        '{"schema": "business-card-watchdog.duplicate-assessment.v1", "state": "strong_duplicate"}\n',
        encoding="utf-8",
    )

    result = BusinessCardService(config).submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="resolve_duplicate",
        duplicate_resolution={"decision": "noop", "reason": "already imported"},
    )

    assert result["job"]["state"] == "cancelled"
    assert result["job"]["error"] == "duplicate resolved as no-op"


def test_service_get_missing_run_raises(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    service = BusinessCardService(config)

    try:
        service.get_run("missing")
    except FileNotFoundError as exc:
        assert "run not found" in str(exc)
    else:
        raise AssertionError("expected FileNotFoundError")
