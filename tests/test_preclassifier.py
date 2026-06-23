from __future__ import annotations

import json
from pathlib import Path

from business_card_watchdog.config import AppConfig
from business_card_watchdog.orchestrator import BatchOrchestrator
from business_card_watchdog.preclassifier import assess_business_card_candidate, read_image_dimensions

from synthetic_fixtures import (
    SyntheticSkillAdapter,
    latest_jobs_by_id,
    read_jsonl,
    write_multi_card_image,
    write_square_image,
    write_synthetic_image,
)


def test_preclassifier_treats_aspect_ratio_as_uncertain_hint(tmp_path: Path) -> None:
    image = write_synthetic_image(tmp_path / "card.png")

    assessment = assess_business_card_candidate(image)

    assert assessment.decision == "uncertain"
    assert assessment.score < 0.55
    assert assessment.dimensions is not None
    assert assessment.dimensions.aspect_ratio == 1.75
    assert "opencv_rectangle" in assessment.analyzers


def test_preclassifier_reports_opencv_availability_when_installed(tmp_path: Path) -> None:
    pytest = __import__("pytest")
    pytest.importorskip("cv2")
    image = write_synthetic_image(tmp_path / "card.png")

    assessment = assess_business_card_candidate(image)

    assert assessment.analyzers["opencv_rectangle"]["available"] is True


def test_preclassifier_detects_multiple_cards_in_large_photo(tmp_path: Path) -> None:
    pytest = __import__("pytest")
    pytest.importorskip("cv2")
    path = write_multi_card_image(tmp_path / "IMG_20260511_103704.jpg")

    assessment = assess_business_card_candidate(path)
    rectangle = assessment.analyzers["opencv_rectangle"]

    assert assessment.decision == "likely_business_card"
    assert rectangle["available"] is True
    assert rectangle["card_like_count"] >= 3
    assert len(rectangle["boxes"]) >= 3


def test_orchestrator_records_multi_card_candidate_manifest(tmp_path: Path, monkeypatch) -> None:
    pytest = __import__("pytest")
    pytest.importorskip("cv2")
    source_dir = tmp_path / "images"
    write_multi_card_image(source_dir / "IMG_20260511_103704.jpg")
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    adapter = SyntheticSkillAdapter()
    orchestrator = BatchOrchestrator(config)
    monkeypatch.setattr(orchestrator, "adapter", adapter)

    run_dir = orchestrator.process_source(str(source_dir), dry_run=True, workers=1)
    job = next(iter(latest_jobs_by_id(run_dir / "jobs.jsonl").values()))
    artifact_dir = Path(job["artifact_dir"])
    manifest = json.loads((artifact_dir / "card_candidates.json").read_text(encoding="utf-8"))
    crops = json.loads((artifact_dir / "candidate_crops.json").read_text(encoding="utf-8"))
    requests = json.loads((artifact_dir / "child_verification_requests.json").read_text(encoding="utf-8"))
    results = json.loads((artifact_dir / "child_verification_results.json").read_text(encoding="utf-8"))
    promotions = json.loads((artifact_dir / "child_contact_promotions.json").read_text(encoding="utf-8"))
    work_items = json.loads((artifact_dir / "candidate_work_items.json").read_text(encoding="utf-8"))
    orientation = json.loads((artifact_dir / "orientation_evidence.json").read_text(encoding="utf-8"))
    artifact_kinds = [record["kind"] for record in read_jsonl(run_dir / "artifacts.jsonl")]
    events = read_jsonl(run_dir / "events.jsonl")

    assert manifest["schema"] == "business-card-watchdog.card-candidate-boxes.v1"
    assert manifest["source_job_id"] == job["job_id"]
    assert manifest["candidate_count"] >= 3
    assert len(manifest["candidates"]) >= 3
    assert manifest["candidates"][0]["candidate_id"].startswith(job["job_id"] + "-card-")
    assert all(candidate["requires_ocr_verification"] is True for candidate in manifest["candidates"])
    assert work_items["schema"] == "business-card-watchdog.card-candidate-work-items.v1"
    assert work_items["parent_job_id"] == job["job_id"]
    assert work_items["work_item_count"] == manifest["candidate_count"]
    assert len(work_items["work_items"]) == manifest["candidate_count"]
    assert work_items["work_items"][0]["candidate_id"] == manifest["candidates"][0]["candidate_id"]
    assert work_items["work_items"][0]["phase"] == "awaiting_child_contact_review"
    assert work_items["work_items"][0]["state"] == "child_contact_candidate_ready"
    assert all(item["routing_allowed"] is False for item in work_items["work_items"])
    assert crops["schema"] == "business-card-watchdog.card-candidate-crops.v1"
    assert crops["parent_job_id"] == job["job_id"]
    assert crops["crop_count"] == manifest["candidate_count"]
    assert len(crops["crops"]) == manifest["candidate_count"]
    assert Path(crops["crops"][0]["crop_path"]).exists()
    assert Path(work_items["work_items"][0]["crop_path"]).exists()
    assert requests["schema"] == "business-card-watchdog.child-verification-requests.v1"
    assert requests["parent_job_id"] == job["job_id"]
    assert requests["dry_run"] is True
    assert requests["request_count"] == manifest["candidate_count"]
    assert len(requests["requests"]) == manifest["candidate_count"]
    assert requests["requests"][0]["work_item_id"] == work_items["work_items"][0]["work_item_id"]
    assert requests["requests"][0]["executed"] is False
    assert requests["requests"][0]["requires_explicit_execution"] is True
    assert all(request["routing_allowed"] is False for request in requests["requests"])
    assert results["schema"] == "business-card-watchdog.child-verification-results.v1"
    assert results["parent_job_id"] == job["job_id"]
    assert results["mode"] == "synthetic_offline"
    assert results["result_count"] == manifest["candidate_count"]
    assert len(results["results"]) == manifest["candidate_count"]
    assert results["results"][0]["request_id"] == requests["requests"][0]["request_id"]
    assert Path(results["results"][0]["result_path"]).exists()
    result_detail = json.loads(Path(results["results"][0]["result_path"]).read_text(encoding="utf-8"))
    assert result_detail["state"] == "verification_result_ready"
    assert result_detail["requires_review"] is True
    assert result_detail["routing_allowed"] is False
    assert result_detail["contact_spec"]["email"] == "fixture@example.test"
    assert promotions["schema"] == "business-card-watchdog.child-contact-promotions.v1"
    assert promotions["parent_job_id"] == job["job_id"]
    assert promotions["promotion_count"] == manifest["candidate_count"]
    assert len(promotions["promotions"]) == manifest["candidate_count"]
    assert promotions["promotions"][0]["state"] == "needs_review"
    assert promotions["promotions"][0]["routing_allowed"] is False
    child_candidate_path = Path(promotions["promotions"][0]["contact_candidate_path"])
    assert child_candidate_path.exists()
    child_candidate = json.loads(child_candidate_path.read_text(encoding="utf-8"))
    assert child_candidate["schema"] == "business-card-watchdog.contact-candidate.v1"
    assert child_candidate["source"] == "child_verification_result"
    assert child_candidate["normalized"]["email"]["value"] == "fixture@example.test"
    assert child_candidate["lineage"]["parent_job_id"] == job["job_id"]
    assert child_candidate["review"]["state"] == "needs_review"
    assert child_candidate["routing_allowed"] is False
    assert orientation["schema"] == "business-card-watchdog.orientation-evidence.v1"
    assert orientation["image_count"] == crops["crop_count"] + 1
    assert "card_candidates" in artifact_kinds
    assert "candidate_crops" in artifact_kinds
    assert "orientation_evidence" in artifact_kinds
    assert "child_verification_requests" in artifact_kinds
    assert "child_verification_results" in artifact_kinds
    assert "child_contact_promotions" in artifact_kinds
    assert "candidate_work_items" in artifact_kinds
    assert any(event["event_type"] == "card_candidates_recorded" for event in events)
    assert any(event["event_type"] == "candidate_crops_recorded" for event in events)
    assert any(event["event_type"] == "child_verification_requests_recorded" for event in events)
    assert any(event["event_type"] == "child_verification_results_recorded" for event in events)
    assert any(event["event_type"] == "child_contact_promotions_recorded" for event in events)
    assert any(event["event_type"] == "candidate_work_items_recorded" for event in events)
    assert adapter.apply_google_calls == [False]


def test_preclassifier_rejects_square_photo_shape(tmp_path: Path) -> None:
    image = write_square_image(tmp_path / "photo.png")

    assessment = assess_business_card_candidate(image)

    assert assessment.decision == "not_business_card"
    assert assessment.score == 0.0


def test_read_image_dimensions_from_png_header(tmp_path: Path) -> None:
    image = write_synthetic_image(tmp_path / "card.png")

    dimensions = read_image_dimensions(image)

    assert dimensions is not None
    assert dimensions.width == 350
    assert dimensions.height == 200


def test_orchestrator_skips_prefilter_rejected_image(tmp_path: Path, monkeypatch) -> None:
    source_dir = tmp_path / "images"
    write_square_image(source_dir / "photo.png")
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    adapter = SyntheticSkillAdapter()
    orchestrator = BatchOrchestrator(config)
    monkeypatch.setattr(orchestrator, "adapter", adapter)

    run_dir = orchestrator.process_source(str(source_dir), dry_run=True, workers=1)
    job = next(iter(latest_jobs_by_id(run_dir / "jobs.jsonl").values()))
    artifact_dir = Path(job["artifact_dir"])
    preclassification = json.loads((artifact_dir / "preclassification.json").read_text(encoding="utf-8"))
    events = read_jsonl(run_dir / "events.jsonl")

    assert adapter.apply_google_calls == []
    assert job["state"] == "failed"
    assert "prefilter rejected" in job["error"]
    assert preclassification["decision"] == "not_business_card"
    assert any(event["event_type"] == "job_prefilter_rejected" for event in events)
