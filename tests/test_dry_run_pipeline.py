from __future__ import annotations

import json
from pathlib import Path

from business_card_watchdog.config import AppConfig, PrefilterConfig, SinkConfig
from business_card_watchdog.document_intake import is_supported_document
from business_card_watchdog.orchestrator import BatchOrchestrator
from business_card_watchdog.preclassifier import CardCandidateAssessment
from business_card_watchdog.service import BusinessCardService
from business_card_watchdog.skill_adapter import is_supported_image

from synthetic_fixtures import (
    SyntheticSkillAdapter,
    latest_jobs_by_id,
    normalize_events,
    read_jsonl,
    write_synthetic_image,
)


def test_batch_dry_run_uses_synthetic_adapter_without_credentials(
    tmp_path: Path, monkeypatch
) -> None:
    source_dir = tmp_path / "synthetic-cards"
    write_synthetic_image(source_dir / "alpha.png")
    write_synthetic_image(source_dir / "nested" / "beta.jpg")

    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
        prefilter=PrefilterConfig(process_uncertain=True),
        sink=SinkConfig(google_contacts=True, odoo=True, dry_run=True),
        routing_rules=[
            {"match": "email_domain", "value": "example.test", "sinks": ["google_contacts", "odoo"]}
        ],
    )
    adapter = SyntheticSkillAdapter(
        specs_by_stem={
            "alpha": {"email": "alpha@example.test", "full_name": "Alpha Fixture"},
            "beta": {"email": "beta@example.test", "full_name": "Beta Fixture"},
        }
    )
    orchestrator = BatchOrchestrator(config)
    monkeypatch.setattr(orchestrator, "adapter", adapter)

    run_dir = orchestrator.process_source(str(source_dir), dry_run=True, workers=1)

    assert run_dir.parent == config.runs_dir
    assert adapter.apply_google_calls == [False, False]
    assert json.loads((run_dir / "run.json").read_text(encoding="utf-8"))["dry_run"] is True

    final_jobs = latest_jobs_by_id(run_dir / "jobs.jsonl")
    assert {Path(job["image_path"]).name for job in final_jobs.values()} == {"alpha.png", "beta.jpg"}
    assert {job["state"] for job in final_jobs.values()} == {"ready_to_route"}

    for job in final_jobs.values():
        artifact_dir = Path(job["artifact_dir"])
        assert artifact_dir.parent == run_dir / "artifacts"
        assert (artifact_dir / "spec.json").exists()
        assert (artifact_dir / "review.md").exists()
        assert (artifact_dir / "crop_manifest.json").exists()
        assert (artifact_dir / "ocr.txt").exists()
        assert (artifact_dir / "contact_candidate.json").exists()
        assert (artifact_dir / "extraction_quality.json").exists()
        assert (artifact_dir / "sink_payloads.json").exists()
        spec = json.loads((artifact_dir / "spec.json").read_text(encoding="utf-8"))
        assert spec["email"].endswith("@example.test")
        assert spec["notes"].startswith("Synthetic privacy-safe")
        contact_candidate = json.loads((artifact_dir / "contact_candidate.json").read_text(encoding="utf-8"))
        assert contact_candidate["schema"] == "business-card-watchdog.contact-candidate.v1"
        assert contact_candidate["normalized"]["email"]["value"].endswith("@example.test")
        sink_payloads = json.loads((artifact_dir / "sink_payloads.json").read_text(encoding="utf-8"))
        assert sink_payloads["schema"] == "business-card-watchdog.sink-payloads.v1"
        assert [payload["sink"] for payload in sink_payloads["payloads"]] == [
            "google_contacts",
            "odoo",
        ]

    dry_run_events = [
        event for event in read_jsonl(run_dir / "events.jsonl") if event["event_type"] == "sink_decision_dry_run"
    ]
    assert len(dry_run_events) == 2
    assert all(event["payload"]["decision"]["dry_run"] is True for event in dry_run_events)
    assert all(
        event["payload"]["decision"]["sinks"] == ["google_contacts", "odoo"]
        for event in dry_run_events
    )
    assert all(event["payload"]["decision"]["fingerprint"] for event in dry_run_events)
    assert all(len(event["payload"]["payloads"]) == 2 for event in dry_run_events)

    artifact_records = read_jsonl(run_dir / "artifacts.jsonl")
    assert [record["kind"] for record in artifact_records] == [
        "preclassification",
        "artifact_dir",
        "contact_spec",
        "review_report",
        "ocr_text",
        "crop_manifest",
        "contact_candidate",
        "extraction_quality",
        "duplicate_assessment",
        "sink_payloads",
        "preclassification",
        "artifact_dir",
        "contact_spec",
        "review_report",
        "ocr_text",
        "crop_manifest",
        "contact_candidate",
        "extraction_quality",
        "duplicate_assessment",
        "sink_payloads",
        "contact_store_projection",
    ]

    normalized_events = normalize_events(read_jsonl(run_dir / "events.jsonl"))
    event_types = [event["event_type"] for event in normalized_events]
    assert event_types[0] == "run_initialized"
    assert event_types.count("sink_decision_dry_run") == 2
    assert "contact_store_projected" in event_types
    assert "run_completed" in event_types
    assert normalized_events[event_types.index("run_completed")]["payload"] == {"job_count": 2}

    contact_projection = json.loads((run_dir / "contact_store_projection.json").read_text(encoding="utf-8"))
    assert contact_projection["projected_contacts"] == 2
    assert contact_projection["projected_sink_attempts"] == 4
    assert contact_projection["drift"]["state"] == "in_sync"
    contacts = BusinessCardService(config).list_contacts()["contacts"]
    assert {contact["email"] for contact in contacts} == {"alpha@example.test", "beta@example.test"}
    alpha_detail = BusinessCardService(config).get_contact(
        next(contact["contact_id"] for contact in contacts if contact["email"] == "alpha@example.test")
    )["contact"]
    assert {attempt["sink"] for attempt in alpha_detail["sink_attempts"]} == {"google_contacts", "odoo"}
    assert alpha_detail["routing_decisions"][0]["state"] == "ready_to_route"


def test_incomplete_synthetic_spec_creates_review_packet(tmp_path: Path, monkeypatch) -> None:
    source_dir = tmp_path / "synthetic-cards"
    write_synthetic_image(source_dir / "incomplete.png")

    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
        prefilter=PrefilterConfig(process_uncertain=True),
        sink=SinkConfig(google_contacts=True, odoo=True, dry_run=True),
    )
    orchestrator = BatchOrchestrator(config)
    monkeypatch.setattr(
        orchestrator,
        "adapter",
        SyntheticSkillAdapter(specs_by_stem={"incomplete": {"full_name": "", "email": "", "phone": ""}}),
    )

    run_dir = orchestrator.process_source(str(source_dir), dry_run=True, workers=1)

    final_job = next(iter(latest_jobs_by_id(run_dir / "jobs.jsonl").values()))
    artifact_dir = Path(final_job["artifact_dir"])
    review_packet = json.loads((artifact_dir / "review_packet.json").read_text(encoding="utf-8"))
    events = read_jsonl(run_dir / "events.jsonl")

    assert final_job["state"] == "needs_review"
    assert review_packet["assessment"]["status"] == "needs_review"
    assert review_packet["contact_candidate"]["schema"] == "business-card-watchdog.contact-candidate.v1"
    assert review_packet["extraction_quality"]["status"] == "pass"
    assert any(event["event_type"] == "job_needs_review" for event in events)
    assert any(event["event_type"] == "contact_store_projected" for event in events)


def test_projection_failure_is_retryable_ledger_evidence(tmp_path: Path, monkeypatch) -> None:
    source_dir = tmp_path / "synthetic-cards"
    write_synthetic_image(source_dir / "alpha.png")
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
        prefilter=PrefilterConfig(process_uncertain=True),
    )
    orchestrator = BatchOrchestrator(config)
    monkeypatch.setattr(orchestrator, "adapter", SyntheticSkillAdapter())

    def broken_projection(*_args, **_kwargs):
        raise RuntimeError("synthetic projection failure")

    monkeypatch.setattr("business_card_watchdog.orchestrator.ContactStore.project_run", broken_projection)

    run_dir = orchestrator.process_source(str(source_dir), dry_run=True, workers=1)
    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    events = read_jsonl(run_dir / "events.jsonl")

    assert run_payload["state"] == "completed"
    failure = next(event for event in events if event["event_type"] == "contact_store_projection_failed")
    assert failure["payload"]["error"] == "synthetic projection failure"
    assert failure["payload"]["retry_command"] == f"contacts project-run {run_dir.name} --json"


def test_pdf_document_intake_materializes_page_jobs_and_side_candidates(
    tmp_path: Path, monkeypatch
) -> None:
    source_pdf = tmp_path / "scanner" / "batch.pdf"
    source_pdf.parent.mkdir(parents=True)
    source_pdf.write_bytes(
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Page >> endobj\n"
        b"2 0 obj << /Type /Page >> endobj\n"
        b"%%EOF\n"
    )
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
        prefilter=PrefilterConfig(enabled=False),
    )
    orchestrator = BatchOrchestrator(config)
    monkeypatch.setattr(
        orchestrator,
        "adapter",
        SyntheticSkillAdapter(
            specs_by_stem={
                "page-0001": {"email": "front@example.test", "full_name": "Front Page"},
                "page-0002": {"email": "back@example.test", "full_name": "Back Page"},
            }
        ),
    )

    run_dir = orchestrator.process_source(str(source_pdf), dry_run=True, workers=1)

    assert is_supported_document(source_pdf) is True
    assert is_supported_image(source_pdf) is False
    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert run_payload["job_count"] == 2
    artifacts = read_jsonl(run_dir / "artifacts.jsonl")
    assert any(artifact["kind"] == "document_pages" for artifact in artifacts)
    document_pages_artifact = next(artifact for artifact in artifacts if artifact["kind"] == "document_pages")
    document_pages = json.loads(Path(document_pages_artifact["path"]).read_text(encoding="utf-8"))
    assert document_pages["source_media_kind"] == "pdf_document"
    assert document_pages["page_count"] == 2
    assert {Path(page["page_image_path"]).suffix for page in document_pages["pages"]} == {".png"}

    jobs = latest_jobs_by_id(run_dir / "jobs.jsonl")
    assert len(jobs) == 2
    for job in jobs.values():
        artifact_dir = Path(job["artifact_dir"])
        source_page = json.loads((artifact_dir / "source_page.json").read_text(encoding="utf-8"))
        side = json.loads((artifact_dir / "card_side_candidate.json").read_text(encoding="utf-8"))
        assert source_page["source_document_path"] == str(source_pdf)
        assert source_page["media_kind"] == "page_image"
        assert side["side_label"] == "front"
        assert side["classification_reason"] == "contact_identity_density"
        assert side["ocr_text_sha256"]
        quality = json.loads((artifact_dir / "extraction_quality.json").read_text(encoding="utf-8"))
        assert quality["schema"] == "business-card-watchdog.extraction-quality.v1"
        assert quality["status"] == "pass"

    contacts = BusinessCardService(config).list_contacts()["contacts"]
    assert len(contacts) == 2
    detail = BusinessCardService(config).get_contact(str(contacts[0]["contact_id"]))["contact"]
    asset_kinds = {asset["asset_kind"] for asset in detail["assets"]}
    assert {"source_page", "card_side_candidate", "contact_candidate"}.issubset(asset_kinds)
    assert BusinessCardService(config).contact_projection_drift(run_dir.name)["drift"]["state"] == "in_sync"


def test_scanner_pdf_pages_must_pass_classifier_gate_before_ocr(
    tmp_path: Path, monkeypatch
) -> None:
    source_pdf = tmp_path / "scanner" / "mixed.pdf"
    source_pdf.parent.mkdir(parents=True)
    source_pdf.write_bytes(
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Page >> endobj\n"
        b"2 0 obj << /Type /Page >> endobj\n"
        b"%%EOF\n"
    )
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
        prefilter=PrefilterConfig(process_uncertain=True),
    )
    adapter = SyntheticSkillAdapter(
        specs_by_stem={"page-0001": {"email": "front@example.test", "full_name": "Front Page"}}
    )
    orchestrator = BatchOrchestrator(config)
    monkeypatch.setattr(orchestrator, "adapter", adapter)

    def classify(path: Path, *, min_score: float = 0.55) -> CardCandidateAssessment:
        if path.stem == "page-0001":
            return CardCandidateAssessment(
                decision="likely_business_card",
                score=min_score,
                reasons=["synthetic high-confidence card"],
            )
        return CardCandidateAssessment(
            decision="uncertain",
            score=0.35,
            reasons=["synthetic indeterminate scanner page"],
        )

    monkeypatch.setattr("business_card_watchdog.orchestrator.assess_business_card_candidate", classify)

    run_dir = orchestrator.process_source(str(source_pdf), dry_run=True, workers=1)

    assert adapter.apply_google_calls == [False]
    jobs = latest_jobs_by_id(run_dir / "jobs.jsonl")
    by_page = {Path(job["image_path"]).stem: job for job in jobs.values()}
    assert by_page["page-0001"]["state"] in {"needs_review", "ready_to_route"}
    assert by_page["page-0002"]["state"] == "failed"
    assert "classifier gate blocked scanner page" in by_page["page-0002"]["error"]

    admitted_dir = Path(by_page["page-0001"]["artifact_dir"])
    blocked_dir = Path(by_page["page-0002"]["artifact_dir"])
    admitted_gate = json.loads((admitted_dir / "scanner_page_classifier_gate.json").read_text(encoding="utf-8"))
    admitted_ocr_gate = json.loads((admitted_dir / "ocr_quality_gate.json").read_text(encoding="utf-8"))
    blocked_gate = json.loads((blocked_dir / "scanner_page_classifier_gate.json").read_text(encoding="utf-8"))
    blocked_preclassification = json.loads((blocked_dir / "preclassification.json").read_text(encoding="utf-8"))
    events = read_jsonl(run_dir / "events.jsonl")

    assert admitted_gate["classifier_training_state"] == "business_card_high_confidence"
    assert admitted_gate["admitted_to_crop_ocr"] is True
    assert admitted_ocr_gate["classifier_training_state"] == "business_card_high_confidence"
    assert admitted_ocr_gate["lineage"]["scanner_page_classifier_gate_path"].endswith(
        "scanner_page_classifier_gate.json"
    )
    assert (admitted_dir / "contact_candidate.json").exists()
    assert blocked_gate["classifier_training_state"] == "indeterminate_needs_app_intelligence"
    assert blocked_gate["admitted_to_crop_ocr"] is False
    assert blocked_preclassification["classifier_training_state"] == "indeterminate_needs_app_intelligence"
    assert not (blocked_dir / "contact_candidate.json").exists()
    assert not (blocked_dir / "spec.json").exists()
    assert any(event["event_type"] == "scanner_page_classifier_gate_blocked" for event in events)
    assert any(event["event_type"] == "ocr_quality_gate_recorded" for event in events)
    artifact_kinds = [record["kind"] for record in read_jsonl(run_dir / "artifacts.jsonl")]
    assert artifact_kinds.count("scanner_page_classifier_gate") == 2
    assert artifact_kinds.count("ocr_quality_gate") == 1

    service = BusinessCardService(config)
    bundle = service.review_bundle(run_id=run_dir.name, state="all", write=False)
    bundle_by_page = {Path(entry["image_path"]).stem: entry for entry in bundle["entries"]}
    admitted_matrix = bundle_by_page["page-0001"]["review_matrix"]
    blocked_matrix = bundle_by_page["page-0002"]["review_matrix"]
    assert admitted_matrix["quality_gates"]["classifier_state"] == "business_card_high_confidence"
    assert admitted_matrix["quality_gates"]["classifier_admitted_to_crop_ocr"] is True
    assert admitted_matrix["quality_gates"]["ocr_quality_state"] == "passed"
    assert blocked_matrix["contact_source"] == "missing"
    assert blocked_matrix["quality_gates"]["classifier_state"] == "indeterminate_needs_app_intelligence"
    assert blocked_matrix["quality_gates"]["classifier_admitted_to_crop_ocr"] is False
    assert blocked_matrix["quality_gates"]["ocr_quality_state"] == "missing"

    review_surface = service.contact_review_surface(limit=10)
    assert review_surface["count"] == 1
    row = review_surface["rows"][0]
    assert row["scanner_page_classifier_gate"]["classifier_training_states"] == [
        "business_card_high_confidence"
    ]
    assert row["crop_acceptance"]["states"] == ["missing"]
    assert row["ocr_quality_gate"]["states"] == ["passed"]
    assert row["app_intelligence_status"]["request_count"] == 0


def test_short_ocr_quality_creates_review_packet_before_routing(tmp_path: Path, monkeypatch) -> None:
    source_dir = tmp_path / "synthetic-cards"
    write_synthetic_image(source_dir / "short-ocr.png")

    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
        prefilter=PrefilterConfig(process_uncertain=True),
        sink=SinkConfig(google_contacts=True, odoo=True, dry_run=True),
    )
    orchestrator = BatchOrchestrator(config)
    monkeypatch.setattr(
        orchestrator,
        "adapter",
        SyntheticSkillAdapter(ocr_by_stem={"short-ocr": "Ada\n"}),
    )

    run_dir = orchestrator.process_source(str(source_dir), dry_run=True, workers=1)
    final_job = next(iter(latest_jobs_by_id(run_dir / "jobs.jsonl").values()))
    artifact_dir = Path(final_job["artifact_dir"])
    quality = json.loads((artifact_dir / "extraction_quality.json").read_text(encoding="utf-8"))
    ocr_gate = json.loads((artifact_dir / "ocr_quality_gate.json").read_text(encoding="utf-8"))
    review_packet = json.loads((artifact_dir / "review_packet.json").read_text(encoding="utf-8"))
    events = read_jsonl(run_dir / "events.jsonl")

    assert final_job["state"] == "needs_review"
    assert quality["status"] == "needs_review"
    assert quality["reasons"] == ["ocr_text_too_short"]
    assert ocr_gate["state"] == "needs_app_intelligence_review"
    assert ocr_gate["route_ready_allowed"] is False
    assert ocr_gate["app_intelligence_request_count"] == 1
    assert ocr_gate["app_intelligence_requests"][0]["request_type"] == "verify_contact_fields"
    assert review_packet["extraction_quality"]["reasons"] == ["ocr_text_too_short"]
    assert not (artifact_dir / "sink_payloads.json").exists()
    assert any(event["event_type"] == "job_quality_needs_review" for event in events)
