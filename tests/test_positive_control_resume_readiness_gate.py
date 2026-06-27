from __future__ import annotations

import json
from pathlib import Path

from business_card_watchdog.cli import main
from business_card_watchdog.config import AppConfig
from business_card_watchdog.positive_control_resume_readiness_gate import build_positive_control_resume_readiness_gate


def seed_gate_reports(
    config: AppConfig,
    *,
    open_training: bool = True,
    with_negative_controls: bool = True,
    with_negative_replay: bool = True,
    negative_false_positives: int = 0,
) -> None:
    corpus_root = config.data_dir / "positive_control_corpus"
    label_dir = corpus_root / "label_inventories"
    scenario_dir = corpus_root / "scenario_manifests"
    recognition_dir = corpus_root / "recognition_training_replays" / "recognition-fixture"
    crop_dir = corpus_root / "crop_workbenches" / "crop-fixture"
    ocr_dir = corpus_root / "ocr_contact_drafts" / "ocr-fixture"
    side_pair_dir = corpus_root / "side_pair_evidence" / "side-pair-fixture"
    review_loop_dir = corpus_root / "training_review_loops" / "review-loop-fixture"
    for directory in [label_dir, scenario_dir, recognition_dir, crop_dir, ocr_dir, side_pair_dir, review_loop_dir]:
        directory.mkdir(parents=True, exist_ok=True)
    _write_json(
        label_dir / "label_inventory.json",
        {
            "schema": "business-card-watchdog.positive-control-label-inventory.v1",
            "inventory_id": "label-fixture",
            "source_count": 3,
        },
    )
    _write_json(
        scenario_dir / "scenario_manifest.json",
        {
            "schema": "business-card-watchdog.positive-control-scenario-manifest.v1",
            "manifest_id": "scenario-fixture",
            "scenario_count": 8,
        },
    )
    review_cases = 2 if open_training else 0
    _write_json(
        recognition_dir / "recognition_training_replay.json",
        {
            "schema": "business-card-watchdog.positive-control-recognition-training-replay.v1",
            "replay_id": "recognition-fixture",
            "after_counts": {
                "business_card_high_confidence": 4,
                "indeterminate_needs_app_intelligence": review_cases,
                "not_business_card_high_confidence": 0,
            },
        },
    )
    _write_json(
        crop_dir / "crop_workbench.json",
        {
            "schema": "business-card-watchdog.positive-control-crop-workbench.v1",
            "workbench_id": "crop-fixture",
            "pdfs_rasterized": 2,
            "crops_created": 4,
            "counts": {
                "accepted_for_ocr_workbench": 4,
                "crop_review_requests": 1 if open_training else 0,
            },
        },
    )
    _write_json(
        ocr_dir / "ocr_contact_drafts.json",
        {
            "schema": "business-card-watchdog.positive-control-ocr-contact-drafts.v1",
            "draft_id": "ocr-fixture",
            "ocr_attempted": 4,
            "pdfs_rasterized": 2,
            "counts": {"missing_ocr": 2 if open_training else 0},
        },
    )
    _write_json(
        side_pair_dir / "side_pair_evidence.json",
        {
            "schema": "business-card-watchdog.positive-control-side-pair-evidence.v1",
            "report_id": "side-pair-fixture",
            "counts": {"app_intelligence_review_requests": 1 if open_training else 0},
        },
    )
    _write_json(
        review_loop_dir / "training_review_loop.json",
        {
            "schema": "business-card-watchdog.positive-control-training-review-loop.v1",
            "loop_id": "review-loop-fixture",
            "counts": {
                "review_items": 6 if open_training else 0,
                "training_candidates": 6 if open_training else 0,
            },
        },
    )
    if with_negative_controls:
        negative_index = config.data_dir / "negative_control_corpus" / "index.jsonl"
        negative_index.parent.mkdir(parents=True, exist_ok=True)
        negative_index.write_text(
            json.dumps({"label": "safety_flyer", "sha256_prefix": "neg001"}) + "\n",
            encoding="utf-8",
        )
    if with_negative_replay:
        replay_dir = config.data_dir / "negative_control_corpus" / "recognition_replays" / "negative-fixture"
        replay_dir.mkdir(parents=True, exist_ok=True)
        _write_json(
            replay_dir / "recognition_replay.json",
            {
                "schema": "business-card-watchdog.negative-corpus-recognition-replay.v1",
                "replay_id": "negative-fixture",
                "state": "false_positives_found" if negative_false_positives else "negative_controls_passed",
                "source_count": 1,
                "page_count": 1,
                "counts": {
                    "sources": 1,
                    "pages_replayed": 1,
                    "false_positive_cases": negative_false_positives,
                },
            },
        )


def test_positive_control_resume_readiness_gate_keeps_known_card_only_when_training_open(
    tmp_path: Path,
) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    seed_gate_reports(config, open_training=True)

    payload = build_positive_control_resume_readiness_gate(config, write=True)

    assert payload["schema"] == "business-card-watchdog.positive-control-resume-readiness-gate.v1"
    assert payload["state"] == "known_card_only_training_required"
    assert payload["operating_mode"] == "known_card_only"
    assert payload["decision"]["known_card_crop_ocr_allowed"] is True
    assert payload["decision"]["broad_autodetection_resume_allowed"] is False
    assert payload["counts"]["positive_sources"] == 3
    assert payload["counts"]["scenario_plans"] == 8
    assert payload["counts"]["known_positive_false_negative_or_review_cases"] == 2
    assert payload["counts"]["crop_review_requests"] == 1
    assert payload["counts"]["missing_ocr"] == 2
    assert payload["counts"]["side_pair_review_requests"] == 1
    assert payload["counts"]["training_candidates"] == 6
    assert payload["counts"]["negative_control_sources"] == 1
    assert payload["counts"]["negative_false_positive_cases"] == 0
    assert payload["broad_autodetection_promoted"] is False
    assert payload["sink_payloads_created"] == 0
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    assert payload["live_sink_calls_made"] is False
    assert payload["public_web_search_used"] is False
    assert payload["paid_enrichment_used"] is False
    assert payload["runtime_artifact_written"] is True
    assert Path(payload["report_path"]).exists()


def test_positive_control_resume_readiness_gate_ready_requires_clean_positive_and_negative_evidence(
    tmp_path: Path,
) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    seed_gate_reports(config, open_training=False)

    payload = build_positive_control_resume_readiness_gate(config, write=False)

    assert payload["state"] == "ready_for_runtime_resume_readiness_gate"
    assert payload["decision"]["state"] == "ready_for_bounded_autodetection_pilot_plan"
    assert payload["operating_mode"] == "bounded_autodetection_pilot_candidate"
    assert payload["decision"]["broad_autodetection_resume_allowed"] is True
    assert payload["decision"]["threshold_change_allowed"] is True
    assert payload["counts"]["blocking_requirements"] == 0
    assert payload["runtime_artifact_written"] is False


def test_positive_control_resume_readiness_gate_cli_preview(tmp_path: Path, capsys) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    seed_gate_reports(config, open_training=True)
    config_path = tmp_path / "config.toml"
    config_path.write_text(f'data_dir = "{config.data_dir}"\n', encoding="utf-8")

    assert (
        main(
            [
                "--config",
                str(config_path),
                "positive-control-resume-readiness-gate",
                "--no-write",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["state"] == "ready_for_runtime_resume_readiness_gate"
    assert payload["decision"]["state"] == "known_card_only_training_required"
    assert payload["runtime_artifact_written"] is False
    assert payload["report_path"] is None


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
