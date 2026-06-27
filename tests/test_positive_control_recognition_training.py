from __future__ import annotations

import json
from pathlib import Path

from business_card_watchdog.cli import main
from business_card_watchdog.config import AppConfig
from business_card_watchdog.service import BusinessCardService

import business_card_watchdog.positive_control_recognition_training as training

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


def fake_label_inventory() -> dict[str, object]:
    return {
        "state": "training_inventory_ready",
        "entries": [
            {
                "entry_id": "positive-multi",
                "sha256_prefix": "abc123",
                "source_kind": "multi_card_image_candidate",
                "media_kind": "image",
                "capture_mode": "camera_or_scanner_image_unknown",
                "card_count_label": "multi_card_candidate",
                "orientation_label": "landscape",
                "page_labels": [
                    {
                        "page_number": 1,
                        "side_expectation": "front_or_back_or_composite_unknown",
                    }
                ],
            }
        ],
    }


def fake_scenario_manifest() -> dict[str, object]:
    return {
        "state": "ready_for_scenario_replay",
        "scenario_count": 1,
        "scenarios": [
            {
                "scenario_id": "positive-multi-mixed",
                "scenario_kind": "mixed_multi_card_image_variant",
                "source_entry_id": "positive-multi",
                "source_kind": "multi_card_image_candidate",
                "operations": [{"operation": "compose_mixed_multi_card_image_plan"}],
                "replay_targets": ["recognition", "crop_ocr", "side_pair"],
            }
        ],
    }


def fake_baseline() -> dict[str, object]:
    return {
        "state": "needs_recognition_tuning",
        "replay_id": "baseline-replay",
        "source_count": 1,
        "pdfs_rasterized": 0,
        "source_results": [
            {
                "entry_id": "positive-multi",
                "sha256_prefix": "abc123",
                "media_kind": "image",
                "group": "multi_card_image_candidate",
                "state": "false_negative",
                "pages": [
                    {
                        "page_number": 1,
                        "classifier_training_state": "not_business_card_high_confidence",
                        "decision": "not_business_card",
                        "score": 0.0,
                        "reasons": [
                            "image aspect ratio is compatible with a business card crop",
                            "document-like dense text layout requires App Intelligence review",
                        ],
                        "analyzer_summary": {"document_like": True},
                    }
                ],
            }
        ],
    }


def test_positive_control_recognition_training_demotes_known_positive_high_confidence_negative(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    monkeypatch.setattr(training, "build_positive_control_label_inventory", lambda config, write=False: fake_label_inventory())
    monkeypatch.setattr(training, "build_positive_control_scenario_manifest", lambda config, write=False: fake_scenario_manifest())
    monkeypatch.setattr(training, "build_positive_corpus_recognition_replay", lambda config, write=True: fake_baseline())

    payload = training.build_positive_control_recognition_training_replay(config, write=True)

    assert payload["schema"] == "business-card-watchdog.positive-control-recognition-training-replay.v1"
    assert payload["state"] == "needs_app_intelligence_or_feature_tuning"
    assert payload["before_counts"]["high_confidence_negative_known_positive_cases"] == 1
    assert payload["after_counts"]["high_confidence_negative_known_positive_cases"] == 0
    assert payload["after_counts"]["indeterminate_needs_app_intelligence"] == 1
    assert payload["improvement_summary"]["high_confidence_negative_known_positive_reduction"] == 1
    assert payload["unknown_document_threshold_changed"] is False
    assert payload["negative_regression_required_before_threshold_change"] is True
    assert payload["tuning_changes"][0]["scope"] == "operator_declared_positive_controls_only"
    assert payload["false_negative_groups"][0]["tuning_reason"] == (
        "known_positive_multi_card_document_like_requires_crop_or_vision_review"
    )
    assert payload["app_intelligence_request_count"] >= 1
    assert payload["app_intelligence_requests"][0]["bounded_question"]
    assert payload["runtime_artifact_written"] is True
    assert Path(payload["report_path"]).exists()
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    assert payload["live_sink_calls_made"] is False


def test_positive_control_recognition_training_cli_preview_redacts_and_writes_nothing(
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
                "positive-control-recognition-training-replay",
                "--no-write",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    serialized = json.dumps(payload, sort_keys=True)

    assert payload["state"] != "blocked"
    assert payload["runtime_artifact_written"] is False
    assert payload["report_path"] is None
    assert payload["unknown_document_threshold_changed"] is False
    assert payload["replay_only_no_promotion"] is True
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    for source in private_sources:
        assert str(source) not in serialized
        assert source.name not in serialized
    assert not (config.data_dir / "positive_control_corpus" / "recognition_training_replays").exists()
