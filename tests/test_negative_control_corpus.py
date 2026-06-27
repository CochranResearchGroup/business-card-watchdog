from __future__ import annotations

import json
from pathlib import Path

from business_card_watchdog.cli import main
from business_card_watchdog.config import AppConfig
from business_card_watchdog.service import BusinessCardService

from synthetic_fixtures import write_synthetic_image


def write_pdf(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"%PDF-1.7\n1 0 obj << /Type /Page >> endobj\n%%EOF\n")
    return path


def test_negative_control_intake_preview_redacts_and_writes_nothing(tmp_path: Path) -> None:
    private_sources = tmp_path / "Private Scanner"
    image = write_synthetic_image(private_sources / "private-flyer.jpg")
    pdf = write_pdf(private_sources / "private-handout.pdf")
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")

    payload = BusinessCardService(config).negative_control_intake(
        source_paths=[str(private_sources)],
        label="known_non_business_card",
        category="handout_or_flyer",
        write=False,
    )
    serialized = json.dumps(payload, sort_keys=True)

    assert payload["schema"] == "business-card-watchdog.negative-control-intake.v1"
    assert payload["state"] == "negative_evidence_filed"
    assert payload["entry_count"] == 2
    assert payload["counts"]["images"] == 1
    assert payload["counts"]["pdf_documents"] == 1
    assert payload["counts"]["stored_new"] == 0
    assert payload["runtime_artifact_written"] is False
    assert payload["manifest_path"] is None
    assert payload["ocr_attempted"] == 0
    assert payload["pdfs_rasterized"] == 0
    assert payload["crops_created"] == 0
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    assert str(image) not in serialized
    assert str(pdf) not in serialized
    assert "private-flyer.jpg" not in serialized
    assert "private-handout.pdf" not in serialized
    assert not (config.data_dir / "negative_control_corpus").exists()


def test_negative_control_intake_writes_runtime_corpus_dedupes_and_limits(
    tmp_path: Path,
) -> None:
    private_sources = tmp_path / "Private Scanner"
    image = write_synthetic_image(private_sources / "private-flyer.jpg")
    pdf = write_pdf(private_sources / "private-handout.pdf")
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    service = BusinessCardService(config)

    first = service.negative_control_intake(
        source_paths=[str(private_sources)],
        category="scanner_non_card",
        write=True,
        limit=1,
    )
    second = service.negative_control_intake(
        source_paths=[str(image), str(pdf)],
        category="scanner_non_card",
        write=True,
    )

    assert first["state"] == "negative_evidence_filed"
    assert first["entry_count"] == 1
    assert first["selection_truncated"] is True
    assert first["counts"]["stored_new"] == 1
    assert second["entry_count"] == 2
    assert second["counts"]["stored_new"] == 1
    assert second["counts"]["deduped_existing"] == 1
    assert Path(str(first["manifest_path"])).exists()
    assert Path(str(second["manifest_path"])).exists()
    for entry in second["entries"]:
        blob_path = config.data_dir / "negative_control_corpus" / entry["corpus_blob_relpath"]
        assert blob_path.exists()
        assert not str(blob_path).startswith(str(Path.cwd()))
    index_path = config.data_dir / "negative_control_corpus" / "index.jsonl"
    assert len(index_path.read_text(encoding="utf-8").splitlines()) == 2


def test_negative_control_intake_cli_json(tmp_path: Path, capsys) -> None:
    private_sources = tmp_path / "Private Scanner"
    image = write_synthetic_image(private_sources / "private-safety-flyer.jpg")
    config_path = tmp_path / "config.toml"
    config_path.write_text(f'data_dir = "{tmp_path / "data"}"\n', encoding="utf-8")

    assert (
        main(
            [
                "--config",
                str(config_path),
                "negative-control-intake",
                "--source",
                str(image),
                "--category",
                "safety_flyer",
                "--no-write",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    serialized = json.dumps(payload, sort_keys=True)

    assert payload["state"] == "negative_evidence_filed"
    assert payload["entry_count"] == 1
    assert payload["category"] == "safety_flyer"
    assert payload["runtime_artifact_written"] is False
    assert str(image) not in serialized
    assert "private-safety-flyer.jpg" not in serialized
