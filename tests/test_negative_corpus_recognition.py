from __future__ import annotations

import json
from pathlib import Path

from business_card_watchdog.cli import main
from business_card_watchdog.config import AppConfig
from business_card_watchdog.service import BusinessCardService

from synthetic_fixtures import write_multi_card_image, write_square_image


def write_pdf(path: Path, *, pages: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    objects = "\n".join(f"{index} 0 obj << /Type /Page >> endobj" for index in range(1, pages + 1))
    path.write_bytes(f"%PDF-1.7\n{objects}\n%%EOF\n".encode("utf-8"))
    return path


def test_negative_corpus_recognition_replay_reports_false_positives_without_live_actions(
    tmp_path: Path,
) -> None:
    private_sources = tmp_path / "Private Negatives"
    bad_negative = write_multi_card_image(private_sources / "private-card-shaped-flyer.png")
    true_negative = write_square_image(private_sources / "private-square-handout.png")
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    BusinessCardService(config).negative_control_intake(
        source_paths=[str(bad_negative), str(true_negative)],
        category="fixture_non_card",
        write=True,
    )

    payload = BusinessCardService(config).negative_corpus_recognition_replay(write=True)
    serialized = json.dumps(payload, sort_keys=True)

    assert payload["schema"] == "business-card-watchdog.negative-corpus-recognition-replay.v1"
    assert payload["state"] == "false_positives_found"
    assert payload["source_count"] == 2
    assert payload["counts"]["images"] == 2
    assert payload["counts"]["false_positive_cases"] == 1
    assert payload["false_positive_cases"]
    assert payload["candidate_tuning_reasons"]
    assert payload["category_summary"]["fixture_non_card"]["false_positive_cases"] == 1
    assert payload["replay_only_no_promotion"] is True
    assert payload["runtime_artifact_written"] is True
    assert Path(str(payload["report_path"])).exists()
    assert payload["ocr_attempted"] == 0
    assert payload["crops_created"] == 0
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    assert payload["live_sink_calls_made"] is False
    assert payload["public_web_search_used"] is False
    assert payload["paid_enrichment_used"] is False
    for source in [bad_negative, true_negative]:
        assert str(source) not in serialized
        assert source.name not in serialized


def test_negative_corpus_recognition_replay_preview_does_not_write_runtime_report(
    tmp_path: Path,
) -> None:
    private_sources = tmp_path / "Private Negatives"
    pdf = write_pdf(private_sources / "private-handout.pdf", pages=2)
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    BusinessCardService(config).negative_control_intake(
        source_paths=[str(pdf)],
        category="fixture_pdf_non_card",
        write=True,
    )

    payload = BusinessCardService(config).negative_corpus_recognition_replay(write=False)

    assert payload["state"] == "negative_controls_passed"
    assert payload["runtime_artifact_written"] is False
    assert payload["report_path"] is None
    assert payload["counts"]["pdf_documents"] == 1
    assert payload["counts"]["pages_replayed"] == 1
    assert payload["counts"]["indeterminate_needs_app_intelligence"] == 1
    assert not (config.data_dir / "negative_control_corpus" / "recognition_replays").exists()


def test_negative_corpus_recognition_replay_cli_json(tmp_path: Path, capsys) -> None:
    private_sources = tmp_path / "Private Negatives"
    image = write_square_image(private_sources / "private-handout.png")
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    BusinessCardService(config).negative_control_intake(
        source_paths=[str(image)],
        category="fixture_non_card",
        write=True,
    )
    config_path = tmp_path / "config.toml"
    config_path.write_text(f'data_dir = "{config.data_dir}"\n', encoding="utf-8")

    assert (
        main(
            [
                "--config",
                str(config_path),
                "negative-control-recognition-replay",
                "--no-write",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    serialized = json.dumps(payload, sort_keys=True)

    assert payload["state"] == "negative_controls_passed"
    assert payload["source_count"] == 1
    assert payload["runtime_artifact_written"] is False
    assert str(image) not in serialized
    assert image.name not in serialized
