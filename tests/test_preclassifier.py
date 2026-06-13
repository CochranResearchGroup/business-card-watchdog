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
    cv2 = pytest.importorskip("cv2")
    import numpy as np

    image = np.zeros((900, 1400, 3), dtype=np.uint8)
    cards = [
        ((100, 120), (520, 360)),
        ((650, 140), (1070, 380)),
        ((240, 520), (660, 760)),
    ]
    for top_left, bottom_right in cards:
        cv2.rectangle(image, top_left, bottom_right, (255, 255, 255), thickness=-1)
        cv2.rectangle(image, top_left, bottom_right, (0, 0, 0), thickness=4)
    path = tmp_path / "IMG_20260511_103704.jpg"
    assert cv2.imwrite(str(path), image)

    assessment = assess_business_card_candidate(path)
    rectangle = assessment.analyzers["opencv_rectangle"]

    assert assessment.decision == "likely_business_card"
    assert rectangle["available"] is True
    assert rectangle["card_like_count"] >= 3
    assert len(rectangle["boxes"]) >= 3


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
