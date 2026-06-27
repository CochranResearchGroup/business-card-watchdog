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


def seed_corpus(tmp_path: Path) -> tuple[AppConfig, list[Path]]:
    source_dir = tmp_path / "Private Known Positives"
    image = write_synthetic_image(source_dir / "private-card-photo.jpg")
    pdf = write_pdf(source_dir / "private-front-back.pdf", pages=2)
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    BusinessCardService(config).known_card_intake(source_paths=[str(image), str(pdf)], write=True)
    return config, [image, pdf]


def test_positive_corpus_recognition_replay_records_false_negatives_without_sink_work(
    tmp_path: Path,
) -> None:
    config, private_sources = seed_corpus(tmp_path)

    payload = BusinessCardService(config).positive_corpus_recognition_replay(write=True)
    serialized = json.dumps(payload, sort_keys=True)

    assert payload["schema"] == "business-card-watchdog.positive-corpus-recognition-replay.v1"
    assert payload["state"] == "needs_recognition_tuning"
    assert payload["source_count"] == 2
    assert payload["counts"]["images"] == 1
    assert payload["counts"]["pdf_documents"] == 1
    assert payload["counts"]["false_negative_cases"] >= 1
    assert payload["false_negative_cases"]
    assert payload["candidate_tuning_reasons"]
    assert payload["replay_only_no_promotion"] is True
    assert payload["runtime_artifact_written"] is True
    assert Path(payload["report_path"]).exists()
    assert payload["ocr_attempted"] == 0
    assert payload["crops_created"] == 0
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    assert payload["live_sink_calls_made"] is False
    assert payload["public_web_search_used"] is False
    assert payload["paid_enrichment_used"] is False
    for source in private_sources:
        assert str(source) not in serialized
        assert source.name not in serialized


def test_positive_corpus_recognition_replay_preview_does_not_write_runtime_report(
    tmp_path: Path,
) -> None:
    config, _ = seed_corpus(tmp_path)

    payload = BusinessCardService(config).positive_corpus_recognition_replay(write=False)

    assert payload["state"] == "needs_recognition_tuning"
    assert payload["runtime_artifact_written"] is False
    assert payload["report_path"] is None
    assert payload["counts"]["pdf_documents"] == 1
    assert payload["counts"]["indeterminate_needs_app_intelligence"] >= 1
    assert not (config.data_dir / "positive_control_corpus" / "recognition_replays").exists()


def test_positive_corpus_recognition_replay_cli_json(tmp_path: Path, capsys) -> None:
    config, private_sources = seed_corpus(tmp_path)
    config_path = tmp_path / "config.toml"
    config_path.write_text(f'data_dir = "{config.data_dir}"\n', encoding="utf-8")

    assert (
        main(
            [
                "--config",
                str(config_path),
                "positive-corpus-recognition-replay",
                "--no-write",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    serialized = json.dumps(payload, sort_keys=True)

    assert payload["state"] == "needs_recognition_tuning"
    assert payload["source_count"] == 2
    assert payload["runtime_artifact_written"] is False
    for source in private_sources:
        assert str(source) not in serialized
        assert source.name not in serialized
