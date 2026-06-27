from __future__ import annotations

import json
from pathlib import Path

from business_card_watchdog.cli import main
from business_card_watchdog.config import AppConfig
from business_card_watchdog.service import BusinessCardService

from synthetic_fixtures import write_synthetic_image


def write_pdf(path: Path, *, pages: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    objects = "\n".join(f"{index} 0 obj << /Type /Page >> endobj" for index in range(1, pages + 1))
    path.write_bytes(f"%PDF-1.7\n{objects}\n%%EOF\n".encode("utf-8"))
    return path


def write_png_header(path: Path, *, width: int, height: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR"
        + width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + b"\x08\x02\x00\x00\x00"
        + b"\x00\x00\x00\x00"
        + b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    return path


def seed_corpus(tmp_path: Path) -> tuple[AppConfig, list[Path]]:
    source_dir = tmp_path / "Private Cards"
    single = write_synthetic_image(source_dir / "private-single.jpg")
    multi = write_png_header(source_dir / "private-multi.png", width=3200, height=1500)
    scanner = write_pdf(source_dir / "private-scanner.pdf", pages=1)
    sequence = write_pdf(source_dir / "private-front-back.pdf", pages=4)
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    BusinessCardService(config).known_card_intake(
        source_paths=[str(single), str(multi), str(scanner), str(sequence)],
        write=True,
    )
    return config, [single, multi, scanner, sequence]


def by_source_kind(payload: dict[str, object], source_kind: str) -> dict[str, object]:
    entries = payload["entries"]
    assert isinstance(entries, list)
    matches = [entry for entry in entries if isinstance(entry, dict) and entry.get("source_kind") == source_kind]
    assert len(matches) == 1
    return matches[0]


def test_positive_control_label_inventory_normalizes_labels_and_redacts(tmp_path: Path) -> None:
    config, private_sources = seed_corpus(tmp_path)

    payload = BusinessCardService(config).positive_control_label_inventory(write=False)
    serialized = json.dumps(payload, sort_keys=True)

    assert payload["schema"] == "business-card-watchdog.positive-control-label-inventory.v1"
    assert payload["state"] == "training_inventory_ready"
    assert payload["entry_count"] == 4
    assert payload["group_summary"]["single_card_image_candidate"]["count"] == 1
    assert payload["group_summary"]["multi_card_image_candidate"]["count"] == 1
    assert payload["group_summary"]["scanner_pdf_document"]["count"] == 1
    assert payload["group_summary"]["scanner_pdf_front_back_sequence_candidate"]["count"] == 1
    assert payload["stable_replay_order"] == [entry["entry_id"] for entry in payload["entries"]]

    single = by_source_kind(payload, "single_card_image_candidate")
    multi = by_source_kind(payload, "multi_card_image_candidate")
    scanner = by_source_kind(payload, "scanner_pdf_document")
    sequence = by_source_kind(payload, "scanner_pdf_front_back_sequence_candidate")

    assert single["card_count_label"] == "single_card_candidate"
    assert multi["card_count_label"] == "multi_card_candidate"
    assert scanner["page_count"] == 1
    assert scanner["front_back_expectation"] == "front_back_expectation_unknown"
    assert "front_back_pairing" in scanner["missing_labels"]
    assert sequence["page_count"] == 4
    assert sequence["expected_pair_candidate_count"] == 2
    assert len(sequence["page_labels"]) == 4
    assert sequence["front_back_expectation"] == "likely_adjacent_front_back_sequence_order_unknown"
    assert sequence["scenario_labels"]["supports_front_first"] is True
    assert sequence["scenario_labels"]["supports_back_first"] is True
    assert sequence["scenario_labels"]["supports_dropped_blank_back"] is True

    missing_report = payload["missing_label_report"]
    assert missing_report["missing_label_count"] == 4
    assert missing_report["blocks_known_card_crop_ocr"] is False
    assert missing_report["blocks_training_promotion"] is True
    assert payload["training_promotion_allowed"] is False
    assert payload["known_card_crop_ocr_allowed"] is True
    assert payload["runtime_artifact_written"] is False
    assert payload["inventory_path"] is None
    assert payload["ocr_attempted"] == 0
    assert payload["pdfs_rasterized"] == 0
    assert payload["crops_created"] == 0
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    assert payload["live_sink_calls_made"] is False
    for source in private_sources:
        assert str(source) not in serialized
        assert source.name not in serialized
    assert not (config.data_dir / "positive_control_corpus" / "label_inventories").exists()


def test_positive_control_label_inventory_writes_runtime_inventory(tmp_path: Path) -> None:
    config, _ = seed_corpus(tmp_path)

    payload = BusinessCardService(config).positive_control_label_inventory(write=True)

    assert payload["state"] == "training_inventory_ready"
    assert payload["runtime_artifact_written"] is True
    assert Path(payload["inventory_path"]).exists()
    assert str(payload["inventory_path"]).startswith(str(config.data_dir))
    assert payload["stable_replay_order"] == [entry["entry_id"] for entry in payload["entries"]]


def test_positive_control_label_inventory_cli_json_preview(tmp_path: Path, capsys) -> None:
    config, private_sources = seed_corpus(tmp_path)
    config_path = tmp_path / "config.toml"
    config_path.write_text(f'data_dir = "{config.data_dir}"\n', encoding="utf-8")

    assert (
        main(
            [
                "--config",
                str(config_path),
                "positive-control-label-inventory",
                "--no-write",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    serialized = json.dumps(payload, sort_keys=True)

    assert payload["state"] == "training_inventory_ready"
    assert payload["entry_count"] == 4
    assert payload["runtime_artifact_written"] is False
    for source in private_sources:
        assert str(source) not in serialized
        assert source.name not in serialized
