from __future__ import annotations

from pathlib import Path

import pytest

from business_card_watchdog.qr_evidence import build_qr_evidence, redacted_qr_summary

from synthetic_fixtures import write_synthetic_image


def write_qr_image(path: Path, payload: str) -> Path:
    cv2 = pytest.importorskip("cv2")
    encoder = cv2.QRCodeEncoder_create()
    image = encoder.encode(payload)
    image = cv2.resize(image, (290, 290), interpolation=cv2.INTER_NEAREST)
    image = cv2.copyMakeBorder(image, 40, 40, 40, 40, cv2.BORDER_CONSTANT, value=255)
    path.parent.mkdir(parents=True, exist_ok=True)
    assert cv2.imwrite(str(path), image)
    return path


def test_qr_evidence_decodes_qr_payload_and_redacts_summary(tmp_path: Path) -> None:
    image_path = write_qr_image(tmp_path / "qr.png", "https://example.test/bcw")

    evidence = build_qr_evidence(
        run_id="run-qr",
        job_id="job-qr",
        source_image_path=image_path,
    )
    summary = redacted_qr_summary(evidence)

    assert evidence["schema"] == "business-card-watchdog.qr-evidence.v1"
    assert evidence["state"] == "found"
    assert evidence["qr_found"] is True
    assert evidence["decode_count"] == 1
    assert evidence["payload_types"] == ["url"]
    assert evidence["detections"][0]["detections"][0]["payload"] == "https://example.test/bcw"
    assert summary == {
        "state": "found",
        "qr_found": True,
        "decode_count": 1,
        "payload_types": ["url"],
        "decoder_state": "available",
        "image_count": 1,
    }
    assert "payload" not in summary
    assert evidence["writes_attempted"] == 0
    assert evidence["network_calls_made"] == 0


def test_qr_evidence_records_explicit_none_found(tmp_path: Path) -> None:
    image_path = write_synthetic_image(tmp_path / "card.png")

    evidence = build_qr_evidence(
        run_id="run-no-qr",
        job_id="job-no-qr",
        source_image_path=image_path,
    )

    assert evidence["state"] == "none_found"
    assert evidence["qr_found"] is False
    assert evidence["decode_count"] == 0
    assert evidence["payload_types"] == []
