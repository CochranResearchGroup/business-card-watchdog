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


def test_known_card_intake_preview_redacts_and_writes_nothing(tmp_path: Path) -> None:
    private_sources = tmp_path / "Private Sources"
    image = write_synthetic_image(private_sources / "private-card-front.jpg")
    pdf = write_pdf(private_sources / "private-card-scan.pdf")
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")

    payload = BusinessCardService(config).known_card_intake(
        source_paths=[str(image), str(pdf)],
        write=False,
    )
    serialized = json.dumps(payload, sort_keys=True)

    assert payload["schema"] == "business-card-watchdog.known-card-intake.v1"
    assert payload["state"] == "positive_evidence_filed"
    assert payload["entry_count"] == 2
    assert payload["counts"]["images"] == 1
    assert payload["counts"]["pdf_documents"] == 1
    assert payload["counts"]["stored_new"] == 0
    assert payload["runtime_artifact_written"] is False
    assert payload["manifest_path"] is None
    assert payload["files_processed"] == 2
    assert payload["ocr_attempted"] == 0
    assert payload["pdfs_rasterized"] == 0
    assert payload["crops_created"] == 0
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    assert str(image) not in serialized
    assert str(pdf) not in serialized
    assert "private-card-front.jpg" not in serialized
    assert "private-card-scan.pdf" not in serialized
    assert not (config.data_dir / "positive_control_corpus").exists()


def test_known_card_intake_writes_runtime_corpus_and_dedupes(tmp_path: Path) -> None:
    private_sources = tmp_path / "Private Sources"
    image = write_synthetic_image(private_sources / "private-card-front.jpg")
    pdf = write_pdf(private_sources / "private-card-scan.pdf")
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    service = BusinessCardService(config)

    first = service.known_card_intake(source_paths=[str(image), str(pdf)], write=True)
    second = service.known_card_intake(source_paths=[str(image), str(pdf)], write=True)

    assert first["state"] == "positive_evidence_filed"
    assert first["counts"]["stored_new"] == 2
    assert first["counts"]["deduped_existing"] == 0
    assert second["counts"]["stored_new"] == 0
    assert second["counts"]["deduped_existing"] == 2
    assert Path(first["manifest_path"]).exists()
    for entry in first["entries"]:
        blob_path = config.data_dir / "positive_control_corpus" / entry["corpus_blob_relpath"]
        assert blob_path.exists()
        assert not str(blob_path).startswith(str(Path.cwd()))
    index_path = config.data_dir / "positive_control_corpus" / "index.jsonl"
    assert len(index_path.read_text(encoding="utf-8").splitlines()) == 2


def test_known_card_intake_cli_json(tmp_path: Path, capsys) -> None:
    private_sources = tmp_path / "Private Sources"
    image = write_synthetic_image(private_sources / "private-card-front.jpg")
    config_path = tmp_path / "config.toml"
    config_path.write_text(f'data_dir = "{tmp_path / "data"}"\n', encoding="utf-8")

    assert (
        main(
            [
                "--config",
                str(config_path),
                "known-card-intake",
                "--source",
                str(image),
                "--no-write",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    serialized = json.dumps(payload, sort_keys=True)

    assert payload["state"] == "positive_evidence_filed"
    assert payload["entry_count"] == 1
    assert payload["runtime_artifact_written"] is False
    assert str(image) not in serialized
    assert "private-card-front.jpg" not in serialized
