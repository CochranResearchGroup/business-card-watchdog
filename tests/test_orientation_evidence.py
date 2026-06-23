from __future__ import annotations

from pathlib import Path

import pytest

from business_card_watchdog.orientation_evidence import (
    build_orientation_evidence,
    redacted_orientation_summary,
)


def write_text_card(path: Path) -> Path:
    cv2 = pytest.importorskip("cv2")
    import numpy as np

    image = np.full((220, 380, 3), 255, dtype=np.uint8)
    cv2.rectangle(image, (8, 8), (372, 212), (0, 0, 0), 2)
    cv2.putText(image, "GALLAGHER", (28, 58), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 3)
    cv2.putText(image, "ASPHALT", (28, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.85, (0, 0, 0), 2)
    cv2.putText(image, "555 0100", (28, 142), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)
    path.parent.mkdir(parents=True, exist_ok=True)
    assert cv2.imwrite(str(path), image)
    return path


def rotate_clockwise(source: Path, target: Path) -> Path:
    cv2 = pytest.importorskip("cv2")
    image = cv2.imread(str(source))
    assert image is not None
    rotated = cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
    assert cv2.imwrite(str(target), rotated)
    return target


def write_blank_image(path: Path) -> Path:
    cv2 = pytest.importorskip("cv2")
    import numpy as np

    image = np.full((260, 260, 3), 255, dtype=np.uint8)
    path.parent.mkdir(parents=True, exist_ok=True)
    assert cv2.imwrite(str(path), image)
    return path


def test_orientation_evidence_creates_normalized_derivative_for_wrong_rotation(tmp_path: Path) -> None:
    upright = write_text_card(tmp_path / "upright.jpg")
    wrong = rotate_clockwise(upright, tmp_path / "wrong.jpg")

    evidence = build_orientation_evidence(
        run_id="run-orientation",
        job_id="job-orientation",
        source_image_path=wrong,
        output_dir=tmp_path / "artifacts",
    )
    summary = redacted_orientation_summary(evidence)

    assert evidence["schema"] == "business-card-watchdog.orientation-evidence.v1"
    assert evidence["state"] == "normalized"
    assert evidence["normalized_count"] == 1
    assert evidence["needs_review_count"] == 0
    assert evidence["items"][0]["state"] == "normalized_derivative_created"
    assert evidence["items"][0]["selected_rotation_degrees"] in {90, 270}
    assert Path(evidence["items"][0]["normalized_image_path"]).exists()
    assert summary["normalized_count"] == 1
    assert summary["needs_review_count"] == 0
    assert "normalized_image_path" not in summary
    assert evidence["writes_attempted"] == 0
    assert evidence["network_calls_made"] == 0


def test_orientation_evidence_marks_ambiguous_blank_for_app_intelligence(tmp_path: Path) -> None:
    blank = write_blank_image(tmp_path / "blank.jpg")

    evidence = build_orientation_evidence(
        run_id="run-blank",
        job_id="job-blank",
        source_image_path=blank,
        output_dir=tmp_path / "artifacts",
    )

    assert evidence["state"] == "needs_app_intelligence_review"
    assert evidence["normalized_count"] == 0
    assert evidence["needs_review_count"] == 1
    assert evidence["items"][0]["normalized_image_path"] == ""
