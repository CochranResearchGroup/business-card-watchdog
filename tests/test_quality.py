from __future__ import annotations

import json
from pathlib import Path

from business_card_watchdog.quality import assess_extraction_quality


def test_extraction_quality_passes_with_ocr_and_crop_manifest(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    (artifact_dir / "ocr.txt").write_text("Ada Lovelace\nExample Labs\nada@example.test\n", encoding="utf-8")
    (artifact_dir / "crop_manifest.json").write_text(
        json.dumps({"schema": "test", "crops": [{"id": "crop-1"}]}),
        encoding="utf-8",
    )

    assessment = assess_extraction_quality(artifact_dir=artifact_dir)

    assert assessment.status == "pass"
    assert assessment.route_ready_allowed is True
    assert assessment.metrics["ocr_token_count"] >= 3
    assert assessment.metrics["crop_count"] == 1


def test_extraction_quality_blocks_missing_ocr_and_empty_crops(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    (artifact_dir / "crop_manifest.json").write_text(
        json.dumps({"schema": "test", "crops": []}),
        encoding="utf-8",
    )

    assessment = assess_extraction_quality(artifact_dir=artifact_dir)

    assert assessment.status == "needs_review"
    assert assessment.route_ready_allowed is False
    assert assessment.reasons == ["missing_ocr_text", "empty_crop_manifest"]
    assert assessment.checks["ocr_text"]["exists"] is False
    assert assessment.checks["crop_manifest"]["crop_count"] == 0


def test_extraction_quality_blocks_non_front_scanner_side(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    (artifact_dir / "ocr.txt").write_text("Scan QR\nexample.test\nlinkedin.com/in/ada\n", encoding="utf-8")
    (artifact_dir / "crop_manifest.json").write_text(
        json.dumps({"schema": "test", "crop_count": 1}),
        encoding="utf-8",
    )

    assessment = assess_extraction_quality(
        artifact_dir=artifact_dir,
        source_page={"media_kind": "page_image"},
        side_candidate={"side_label": "back"},
    )

    assert assessment.status == "needs_review"
    assert assessment.reasons == ["side_not_route_ready"]
    assert assessment.checks["scanner_side"]["side_label"] == "back"
