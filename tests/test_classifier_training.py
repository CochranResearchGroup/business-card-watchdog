from __future__ import annotations

import json
from pathlib import Path

from business_card_watchdog.cli import main
from business_card_watchdog.config import AppConfig, WatchConfig
from business_card_watchdog.service import BusinessCardService


def write_minimal_pdf(path: Path, *, pages: int = 1) -> Path:
    kids = " ".join(f"{index + 3} 0 R" for index in range(pages))
    objects = [
        "1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj",
        f"2 0 obj << /Type /Pages /Kids [{kids}] /Count {pages} >> endobj",
    ]
    for index in range(pages):
        objects.append(
            f"{index + 3} 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >> endobj"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("%PDF-1.4\n" + "\n".join(objects) + "\n%%EOF\n", encoding="utf-8")
    return path


def write_config(path: Path, *, data_dir: Path, scanner_dir: Path) -> None:
    path.write_text(
        f'data_dir = "{data_dir}"\n'
        "[paths]\n"
        f'scanner = "{scanner_dir}"\n'
        "[watch]\n"
        'inputs = ["$fsr:scanner"]\n',
        encoding="utf-8",
    )


def test_classifier_training_iteration_selects_one_pdf_and_writes_iteration(tmp_path: Path) -> None:
    scanner = tmp_path / "scanner"
    first = write_minimal_pdf(scanner / "2026_06_01_10_00_00.pdf", pages=2)
    write_minimal_pdf(scanner / "2026_06_02_10_00_00.pdf", pages=1)
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        watch=WatchConfig(inputs=[str(scanner)]),
    )

    payload = BusinessCardService(config).classifier_training_iteration()

    assert payload["schema"] == "business-card-watchdog.classifier-training-iteration.v1"
    assert payload["source_document_name"] == first.name
    assert payload["page_count"] == 2
    assert payload["counts"]["page_count"] == 2
    assert payload["runtime_artifact_written"] is True
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    assert Path(payload["iteration_path"]).exists()
    assert all(Path(page["preclassification_path"]).exists() for page in payload["pages"])
    artifact_kinds = [
        json.loads(line)["kind"]
        for line in (config.runs_dir / payload["run_id"] / "artifacts.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert "document_pages" in artifact_kinds
    assert "classifier_training_iteration" in artifact_kinds


def test_classifier_training_iteration_no_write_keeps_runtime_summary_unwritten(
    tmp_path: Path,
    capsys,
) -> None:
    scanner = tmp_path / "scanner"
    source = write_minimal_pdf(scanner / "2026_06_01_10_00_00.pdf", pages=1)
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    write_config(config_path, data_dir=data_dir, scanner_dir=scanner)

    assert (
        main(
            [
                "--config",
                str(config_path),
                "runs",
                "classifier-training-iteration",
                "--source",
                str(source),
                "--no-write",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["source_document_name"] == source.name
    assert payload["runtime_artifact_written"] is False
    assert payload["iteration_path"] is None
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
