from __future__ import annotations

import json
from pathlib import Path

from business_card_watchdog.cli import main
from business_card_watchdog.config import AppConfig
from business_card_watchdog.positive_control_ocr_drafts import build_positive_control_ocr_contact_drafts
from business_card_watchdog.service import BusinessCardService

from synthetic_fixtures import write_synthetic_image


def write_pdf(path: Path, *, pages: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    objects = "\n".join(f"{index} 0 obj << /Type /Page >> endobj" for index in range(1, pages + 1))
    path.write_bytes(f"%PDF-1.7\n{objects}\n%%EOF\n".encode("utf-8"))
    return path


def seed_corpus(tmp_path: Path) -> tuple[AppConfig, list[Path]]:
    source_dir = tmp_path / "Private OCR Positives"
    image = write_synthetic_image(source_dir / "private-card-photo.jpg")
    pdf = write_pdf(source_dir / "private-front-back.pdf", pages=2)
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    BusinessCardService(config).known_card_intake(source_paths=[str(image), str(pdf)], write=True)
    return config, [image, pdf]


def test_positive_control_ocr_contact_drafts_extracts_adapter_text_and_normalizes(
    tmp_path: Path,
) -> None:
    config, private_sources = seed_corpus(tmp_path)
    preview = BusinessCardService(config).positive_control_crop_workbench(write=False)
    candidates = [
        candidate
        for source in preview["source_results"]
        for unit in source["processing_units"]
        for candidate in unit["crop_candidates"]
        if candidate["state"] == "accepted_for_ocr_workbench"
    ]
    assert candidates
    first_id = candidates[0]["candidate_id"]

    payload = build_positive_control_ocr_contact_drafts(
        config,
        write=True,
        ocr_text_by_candidate_id={
            first_id: "Ada Lovelace\nExample Labs\nada@example.test\n+1 555 010 1234\nexample.test/ada\n"
        },
    )
    serialized = json.dumps(payload, sort_keys=True)
    first_draft = next(draft for draft in payload["contact_drafts"] if draft["candidate_id"] == first_id)

    assert payload["schema"] == "business-card-watchdog.positive-control-ocr-contact-drafts.v1"
    assert payload["state"] == "contact_drafts_review_required"
    assert payload["counts"]["ocr_text_available"] == 1
    assert payload["counts"]["missing_ocr"] == payload["contact_draft_count"] - 1
    assert first_draft["ocr_provenance"]["source"] == "adapter_raw_text"
    assert first_draft["extracted_fields"]["email"] == "ada@example.test"
    assert first_draft["normalized_contact"]["normalized"]["email"]["value"] == "ada@example.test"
    assert first_draft["field_confidence"]["needs_review"] is True
    assert first_draft["review_required"] is True
    assert first_draft["routing_allowed"] is False
    assert payload["sink_payloads_created"] == 0
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    assert payload["live_sink_calls_made"] is False
    assert payload["runtime_artifact_written"] is True
    assert Path(payload["report_path"]).exists()
    assert Path(payload["contact_draft_dir"]).is_dir()
    for source in private_sources:
        assert str(source) not in serialized
        assert source.name not in serialized


def test_positive_control_ocr_contact_drafts_cli_preview_records_missing_ocr(
    tmp_path: Path,
    capsys,
) -> None:
    config, private_sources = seed_corpus(tmp_path)
    config_path = tmp_path / "config.toml"
    config_path.write_text(f'data_dir = "{config.data_dir}"\n', encoding="utf-8")

    assert (
        main(
            [
                "--config",
                str(config_path),
                "positive-control-ocr-contact-drafts",
                "--no-write",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    serialized = json.dumps(payload, sort_keys=True)

    assert payload["state"] == "ready_for_runtime_ocr_contact_drafts"
    assert payload["runtime_artifact_written"] is False
    assert payload["report_path"] is None
    assert payload["contact_draft_dir"] is None
    assert payload["contact_draft_count"] == payload["accepted_crop_candidate_count"]
    assert payload["counts"]["missing_ocr"] == payload["contact_draft_count"]
    assert payload["counts"]["review_required_drafts"] == payload["contact_draft_count"]
    assert payload["sink_payloads_created"] == 0
    assert payload["routing_allowed"] is False
    assert payload["enrichment_allowed"] is False
    assert payload["public_web_search_used"] is False
    assert payload["paid_enrichment_used"] is False
    for draft in payload["contact_drafts"]:
        assert draft["ocr_provenance"]["state"] == "ocr_missing"
        assert draft["review_required"] is True
        assert draft["sink_write_allowed"] is False
    for source in private_sources:
        assert str(source) not in serialized
        assert source.name not in serialized
    assert not (config.data_dir / "positive_control_corpus" / "ocr_contact_drafts").exists()
