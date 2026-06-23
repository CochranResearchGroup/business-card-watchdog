from __future__ import annotations

from pathlib import Path

import pytest

from business_card_watchdog.crop_quality import (
    build_crop_quality,
    build_recrop_proposals,
    redacted_crop_quality_summary,
)


def write_card_image(path: Path, *, qr_only: bool = False) -> Path:
    cv2 = pytest.importorskip("cv2")
    import numpy as np

    image = np.full((220, 380, 3), 255, dtype=np.uint8)
    cv2.rectangle(image, (4, 4), (376, 216), (0, 0, 0), 2)
    if qr_only:
        cv2.rectangle(image, (150, 55), (230, 135), (0, 0, 0), 5)
        cv2.line(image, (150, 95), (230, 95), (0, 0, 0), 4)
        cv2.line(image, (190, 55), (190, 135), (0, 0, 0), 4)
    else:
        cv2.putText(image, "GALLAGHER", (24, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 3)
        cv2.putText(image, "ASPHALT", (24, 108), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 2)
        cv2.putText(image, "555 0100", (24, 154), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)
    path.parent.mkdir(parents=True, exist_ok=True)
    assert cv2.imwrite(str(path), image)
    return path


def crop_manifest(source: Path, crop: Path, bounds: dict[str, int]) -> dict[str, object]:
    return {
        "schema": "business-card-watchdog.card-candidate-crops.v1",
        "parent_job_id": "job-crop",
        "source_image_path": str(source),
        "image_dimensions": {"width": 500, "height": 300},
        "crop_count": 1,
        "crops": [
            {
                "candidate_id": "candidate-001",
                "work_item_id": "work-001",
                "crop_path": str(crop),
                "source_image_path": str(source),
                "bounds": bounds,
                "state": "crop_ready",
            }
        ],
    }


def test_crop_quality_marks_text_card_crop_good(tmp_path: Path) -> None:
    source = write_card_image(tmp_path / "source.jpg")
    crop = write_card_image(tmp_path / "crop.jpg")

    quality = build_crop_quality(
        run_id="run-crop",
        job_id="job-crop",
        source_image_path=source,
        crop_manifest=crop_manifest(source, crop, {"x": 60, "y": 40, "width": 380, "height": 220}),
    )
    summary = redacted_crop_quality_summary(quality)

    assert quality["schema"] == "business-card-watchdog.crop-quality.v1"
    assert quality["state"] == "good"
    assert quality["good_count"] == 1
    assert quality["bad_count"] == 0
    assert summary == {
        "state": "good",
        "crop_count": 1,
        "good_count": 1,
        "bad_count": 0,
        "qr_only_count": 0,
    }
    assert quality["writes_attempted"] == 0
    assert quality["network_calls_made"] == 0


def test_crop_quality_flags_clipped_crop_and_proposes_recrop(tmp_path: Path) -> None:
    source = write_card_image(tmp_path / "source.jpg")
    crop = write_card_image(tmp_path / "crop.jpg")

    quality = build_crop_quality(
        run_id="run-crop",
        job_id="job-crop",
        source_image_path=source,
        crop_manifest=crop_manifest(source, crop, {"x": 0, "y": 20, "width": 380, "height": 220}),
    )
    proposals = build_recrop_proposals(
        run_id="run-crop",
        job_id="job-crop",
        source_image_path=source,
        crop_quality=quality,
    )

    assert quality["state"] == "bad"
    assert quality["bad_count"] == 1
    assert "crop touches source edge" in quality["crops"][0]["reasons"]
    assert proposals["state"] == "proposed"
    assert proposals["proposal_count"] == 1
    assert proposals["proposals"][0]["routing_allowed"] is False


def test_crop_quality_flags_qr_only_crop(tmp_path: Path) -> None:
    source = write_card_image(tmp_path / "source.jpg", qr_only=True)
    crop = write_card_image(tmp_path / "crop.jpg", qr_only=True)
    qr_evidence = {
        "detections": [
            {
                "role": "candidate_crop",
                "path": str(crop),
                "qr_found": True,
                "decode_count": 1,
                "payload_types": ["url"],
            }
        ]
    }

    quality = build_crop_quality(
        run_id="run-crop",
        job_id="job-crop",
        source_image_path=source,
        crop_manifest=crop_manifest(source, crop, {"x": 60, "y": 40, "width": 380, "height": 220}),
        qr_evidence=qr_evidence,
    )

    assert quality["state"] == "qr_only"
    assert quality["qr_only_count"] == 1
    assert "crop appears QR-only" in quality["crops"][0]["reasons"]


def test_crop_quality_records_no_crops_for_no_card_case(tmp_path: Path) -> None:
    source = write_card_image(tmp_path / "source.jpg")

    quality = build_crop_quality(
        run_id="run-crop",
        job_id="job-crop",
        source_image_path=source,
        crop_manifest=None,
    )

    assert quality["state"] == "no_crops"
    assert quality["crop_count"] == 0
    assert quality["good_count"] == 0
