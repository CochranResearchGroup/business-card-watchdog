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


def test_positive_corpus_evaluation_manifest_groups_redacts_and_writes_nothing(
    tmp_path: Path,
) -> None:
    config, private_sources = seed_corpus(tmp_path)

    payload = BusinessCardService(config).positive_corpus_evaluation_manifest(write=False)
    serialized = json.dumps(payload, sort_keys=True)

    assert payload["schema"] == "business-card-watchdog.positive-corpus-evaluation-manifest.v1"
    assert payload["state"] == "ready_for_positive_corpus_replay"
    assert payload["entry_count"] == 4
    assert payload["groups"]["single_card_image_candidate"]["count"] == 1
    assert payload["groups"]["multi_card_image_candidate"]["count"] == 1
    assert payload["groups"]["scanner_pdf_document"]["count"] == 1
    assert payload["groups"]["likely_front_back_sequence"]["count"] == 1
    assert payload["stable_replay_order"] == [entry["entry_id"] for entry in payload["entries"]]
    assert payload["runtime_artifact_written"] is False
    assert payload["manifest_path"] is None
    assert payload["ocr_attempted"] == 0
    assert payload["pdfs_rasterized"] == 0
    assert payload["crops_created"] == 0
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    for source in private_sources:
        assert str(source) not in serialized
        assert source.name not in serialized
    assert not (config.data_dir / "positive_control_corpus" / "evaluation_manifests").exists()


def test_positive_corpus_evaluation_manifest_writes_runtime_manifest(tmp_path: Path) -> None:
    config, _ = seed_corpus(tmp_path)

    payload = BusinessCardService(config).positive_corpus_evaluation_manifest(write=True)

    assert payload["state"] == "ready_for_positive_corpus_replay"
    assert payload["runtime_artifact_written"] is True
    assert Path(payload["manifest_path"]).exists()
    assert str(payload["manifest_path"]).startswith(str(config.data_dir))
    assert payload["stable_replay_order"] == [entry["entry_id"] for entry in payload["entries"]]


def test_positive_corpus_evaluation_manifest_cli_json(tmp_path: Path, capsys) -> None:
    config, private_sources = seed_corpus(tmp_path)
    config_path = tmp_path / "config.toml"
    config_path.write_text(f'data_dir = "{config.data_dir}"\n', encoding="utf-8")

    assert (
        main(
            [
                "--config",
                str(config_path),
                "positive-corpus-evaluation-manifest",
                "--no-write",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    serialized = json.dumps(payload, sort_keys=True)

    assert payload["state"] == "ready_for_positive_corpus_replay"
    assert payload["entry_count"] == 4
    assert payload["runtime_artifact_written"] is False
    for source in private_sources:
        assert str(source) not in serialized
        assert source.name not in serialized
