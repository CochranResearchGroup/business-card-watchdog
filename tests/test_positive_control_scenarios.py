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


def seed_corpus(tmp_path: Path, *, multi_count: int = 2) -> tuple[AppConfig, list[Path]]:
    source_dir = tmp_path / "Private Cards"
    single = write_synthetic_image(source_dir / "private-single.jpg")
    multi_one = write_png_header(source_dir / "private-multi-one.png", width=3200, height=1500)
    scanner = write_pdf(source_dir / "private-scanner.pdf", pages=1)
    sequence = write_pdf(source_dir / "private-front-back.pdf", pages=4)
    sources = [single, multi_one, scanner, sequence]
    if multi_count > 1:
        sources.append(write_png_header(source_dir / "private-multi-two.png", width=3400, height=1600))
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    BusinessCardService(config).known_card_intake(
        source_paths=[str(source) for source in sources],
        write=True,
    )
    return config, sources


def test_positive_control_scenario_manifest_covers_plan_0099_variants_and_redacts(tmp_path: Path) -> None:
    config, private_sources = seed_corpus(tmp_path)

    payload = BusinessCardService(config).positive_control_scenario_manifest(write=False)
    serialized = json.dumps(payload, sort_keys=True)
    scenario_kinds = {scenario["scenario_kind"] for scenario in payload["scenarios"]}
    operations = {
        operation["operation"]
        for scenario in payload["scenarios"]
        for operation in scenario["operations"]
    }

    assert payload["schema"] == "business-card-watchdog.positive-control-scenario-manifest.v1"
    assert payload["state"] == "ready_for_scenario_replay"
    assert payload["source_count"] == 5
    assert payload["scenario_count"] > 0
    assert payload["stable_replay_order"] == [scenario["scenario_id"] for scenario in payload["scenarios"]]
    assert payload["coverage"]["covers_page_order_swaps"] is True
    assert payload["coverage"]["covers_rotations"] is True
    assert payload["coverage"]["covers_omitted_pages"] is True
    assert payload["coverage"]["covers_duplicated_pages"] is True
    assert payload["coverage"]["covers_front_only_scans"] is True
    assert payload["coverage"]["covers_back_only_scans"] is True
    assert payload["coverage"]["covers_front_back_pdfs"] is True
    assert payload["coverage"]["covers_mixed_multi_card_images"] is True
    assert "scanner_pdf_order_variant" in scenario_kinds
    assert "scanner_pdf_missing_back_variant" in scenario_kinds
    assert "scanner_pdf_back_only_variant" in scenario_kinds
    assert "scanner_pdf_duplicate_page_variant" in scenario_kinds
    assert "mixed_multi_card_image_variant" in scenario_kinds
    assert "swap_adjacent_front_back_pages" in operations
    assert "rotate_pages" in operations
    assert "rotate_image" in operations
    assert "duplicate_first_page" in operations
    assert all("recognition" in scenario["replay_targets"] for scenario in payload["scenarios"])
    assert all("crop_ocr" in scenario["replay_targets"] for scenario in payload["scenarios"])
    assert all("side_pair" in scenario["replay_targets"] for scenario in payload["scenarios"])
    assert all(scenario["materialization"]["state"] == "plan_only_not_materialized" for scenario in payload["scenarios"])
    assert payload["runtime_artifact_written"] is False
    assert payload["manifest_path"] is None
    assert payload["generated_file_count"] == 0
    assert payload["materialized_artifact_count"] == 0
    assert payload["ocr_attempted"] == 0
    assert payload["pdfs_rasterized"] == 0
    assert payload["crops_created"] == 0
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    assert payload["live_sink_calls_made"] is False
    for source in private_sources:
        assert str(source) not in serialized
        assert source.name not in serialized
    assert not (config.data_dir / "positive_control_corpus" / "scenario_manifests").exists()


def test_positive_control_scenario_manifest_writes_runtime_manifest(tmp_path: Path) -> None:
    config, _ = seed_corpus(tmp_path)

    payload = BusinessCardService(config).positive_control_scenario_manifest(write=True)

    assert payload["state"] == "ready_for_scenario_replay"
    assert payload["runtime_artifact_written"] is True
    assert Path(payload["manifest_path"]).exists()
    assert str(payload["manifest_path"]).startswith(str(config.data_dir))
    assert payload["generated_file_count"] == 0
    assert payload["materialized_artifact_count"] == 0


def test_positive_control_scenario_manifest_cli_json_preview(tmp_path: Path, capsys) -> None:
    config, private_sources = seed_corpus(tmp_path)
    config_path = tmp_path / "config.toml"
    config_path.write_text(f'data_dir = "{config.data_dir}"\n', encoding="utf-8")

    assert (
        main(
            [
                "--config",
                str(config_path),
                "positive-control-scenario-manifest",
                "--no-write",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    serialized = json.dumps(payload, sort_keys=True)

    assert payload["state"] == "ready_for_scenario_replay"
    assert payload["runtime_artifact_written"] is False
    assert payload["coverage"]["covers_page_order_swaps"] is True
    for source in private_sources:
        assert str(source) not in serialized
        assert source.name not in serialized
