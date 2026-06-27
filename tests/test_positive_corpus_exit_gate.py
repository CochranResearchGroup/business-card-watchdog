from __future__ import annotations

import json
from pathlib import Path

from business_card_watchdog.cli import main
from business_card_watchdog.config import AppConfig
from business_card_watchdog.positive_corpus_exit_gate import build_positive_corpus_exit_gate


def seed_exit_gate_reports(
    config: AppConfig,
    *,
    false_negatives: int = 2,
    review_items: int = 2,
    training_candidates: int = 2,
    with_negative_controls: bool = False,
    with_negative_replay: bool = False,
    negative_false_positives: int = 0,
) -> None:
    corpus_root = config.data_dir / "positive_control_corpus"
    manifest_dir = corpus_root / "evaluation_manifests"
    recognition_dir = corpus_root / "recognition_replays" / "recognition-fixture"
    workbench_dir = corpus_root / "workbench_evaluations" / "workbench-fixture"
    side_pair_dir = corpus_root / "side_pair_evaluations" / "side-pair-fixture"
    review_loop_dir = corpus_root / "training_review_loops" / "review-loop-fixture"
    for directory in [manifest_dir, recognition_dir, workbench_dir, side_pair_dir, review_loop_dir]:
        directory.mkdir(parents=True, exist_ok=True)

    _write_json(
        manifest_dir / "manifest.json",
        {
            "schema": "business-card-watchdog.positive-corpus-evaluation-manifest.v1",
            "manifest_id": "manifest-fixture",
            "entry_count": 2,
            "groups": {
                "multi_card_image_candidate": {"count": 1},
                "likely_front_back_sequence": {"count": 1},
            },
        },
    )
    _write_json(
        recognition_dir / "recognition_replay.json",
        {
            "schema": "business-card-watchdog.positive-corpus-recognition-replay.v1",
            "replay_id": "recognition-fixture",
            "counts": {
                "pages_replayed": 4,
                "business_card_high_confidence": 4 - false_negatives,
                "false_negative_cases": false_negatives,
            },
            "candidate_tuning_reasons": ["known_positive_rejected_as_document_like"]
            if false_negatives
            else [],
        },
    )
    _write_json(
        workbench_dir / "workbench_evaluation.json",
        {
            "schema": "business-card-watchdog.positive-corpus-crop-ocr-workbench.v1",
            "workbench_id": "workbench-fixture",
            "report_path": str(workbench_dir / "workbench_evaluation.json"),
            "ocr_attempted": 4,
            "pdfs_rasterized": 2,
            "crops_created": 4,
            "counts": {
                "processed_jobs": 4,
                "contact_drafts": 4,
                "review_packets": 4,
                "ocr_artifacts": 4,
                "pdf_pages_materialized": 2,
                "image_jobs": 2,
                "multi_card_candidate_jobs": 1,
            },
            "processed_jobs": [
                {"job_id": "job-1", "ocr_text_source": "adapter"},
                {"job_id": "job-2", "ocr_text_source": "derived_from_contact_spec"},
            ],
        },
    )
    _write_json(
        side_pair_dir / "side_pair_evaluation.json",
        {
            "schema": "business-card-watchdog.positive-corpus-side-pair-evaluation.v1",
            "evaluation_id": "side-pair-fixture",
            "page_candidate_count": 2,
            "counts": {
                "scanner_page_candidates": 2,
                "deterministic_pair_proposals": 1,
                "app_intelligence_review_requests": 0,
            },
        },
    )
    _write_json(
        review_loop_dir / "training_review_loop.json",
        {
            "schema": "business-card-watchdog.positive-corpus-training-review-loop.v1",
            "loop_id": "review-loop-fixture",
            "report_path": str(review_loop_dir / "training_review_loop.json"),
            "counts": {
                "review_items": review_items,
                "training_candidates": training_candidates,
            },
        },
    )
    if with_negative_controls:
        negative_index = config.data_dir / "negative_control_corpus" / "index.jsonl"
        negative_index.parent.mkdir(parents=True, exist_ok=True)
        negative_index.write_text(
            json.dumps({"label": "pediatric_handout", "sha256_prefix": "neg001"}) + "\n",
            encoding="utf-8",
        )
    if with_negative_replay:
        replay_dir = config.data_dir / "negative_control_corpus" / "recognition_replays" / "negative-replay-fixture"
        replay_dir.mkdir(parents=True, exist_ok=True)
        _write_json(
            replay_dir / "recognition_replay.json",
            {
                "schema": "business-card-watchdog.negative-corpus-recognition-replay.v1",
                "replay_id": "negative-replay-fixture",
                "state": "false_positives_found" if negative_false_positives else "negative_controls_passed",
                "source_count": 1,
                "page_count": 1,
                "counts": {
                    "sources": 1,
                    "pages_replayed": 1,
                    "false_positive_cases": negative_false_positives,
                    "business_card_high_confidence": negative_false_positives,
                    "not_business_card_high_confidence": 1 - negative_false_positives,
                },
            },
        )


def test_positive_corpus_exit_gate_pauses_broad_autodetection(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    seed_exit_gate_reports(config)

    payload = build_positive_corpus_exit_gate(config, write=True)

    assert payload["schema"] == "business-card-watchdog.positive-corpus-exit-gate.v1"
    assert payload["state"] == "broad_autodetection_paused"
    assert payload["runtime_artifact_written"] is True
    assert Path(str(payload["report_path"])).exists()
    assert payload["counts"]["positive_sources"] == 2
    assert payload["counts"]["positive_pages_or_images"] == 4
    assert payload["counts"]["false_negative_cases"] == 2
    assert payload["counts"]["negative_false_positive_cases"] == 0
    assert payload["false_negative_summary"]["false_negative_rate"] == 0.5
    assert payload["reproducibility"]["known_positive_crop_ocr_reproducible"] is True
    assert payload["reproducibility"]["side_pair_evidence_reproducible"] is True
    assert payload["negative_control_summary"]["state"] == "missing"
    assert payload["gate_decision"]["broad_autodetection_resume_allowed"] is False
    assert payload["gate_decision"]["broad_autodetection_state"] == "paused"
    assert payload["broad_autodetection_promoted"] is False
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    assert payload["live_sink_calls_made"] is False
    assert payload["public_web_search_used"] is False
    assert payload["paid_enrichment_used"] is False
    blockers = payload["gate_decision"]["blocking_requirements"]
    assert "known-positive false negatives remain unresolved" in blockers
    assert "separate negative-control corpus is required before broad promotion thresholds change" in blockers
    assert "training candidates require targeted tests before deterministic rule changes" in blockers


def test_positive_corpus_exit_gate_preview_writes_nothing(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    seed_exit_gate_reports(config)

    payload = build_positive_corpus_exit_gate(config, write=False)

    assert payload["state"] == "broad_autodetection_paused"
    assert payload["runtime_artifact_written"] is False
    assert payload["report_path"] is None
    assert not (config.data_dir / "positive_control_corpus" / "exit_gates").exists()


def test_positive_corpus_exit_gate_ready_requires_negative_controls_and_no_open_training(
    tmp_path: Path,
) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    seed_exit_gate_reports(
        config,
        false_negatives=0,
        review_items=0,
        training_candidates=0,
        with_negative_controls=True,
    )

    payload = build_positive_corpus_exit_gate(config, write=False)

    assert payload["state"] == "broad_autodetection_paused"
    assert payload["gate_decision"]["broad_autodetection_resume_allowed"] is False
    assert payload["negative_replay_summary"]["state"] == "missing"
    assert "negative-control recognition replay is required before broad promotion thresholds change" in payload[
        "gate_decision"
    ]["blocking_requirements"]


def test_positive_corpus_exit_gate_ready_requires_passing_negative_replay(
    tmp_path: Path,
) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    seed_exit_gate_reports(
        config,
        false_negatives=0,
        review_items=0,
        training_candidates=0,
        with_negative_controls=True,
        with_negative_replay=True,
    )

    payload = build_positive_corpus_exit_gate(config, write=False)

    assert payload["state"] == "ready_for_bounded_autodetection_reconsideration"
    assert payload["gate_decision"]["broad_autodetection_resume_allowed"] is True
    assert payload["gate_decision"]["threshold_change_allowed"] is True
    assert payload["negative_control_summary"]["source_count"] == 1
    assert payload["negative_replay_summary"]["false_positive_cases"] == 0
    assert payload["counts"]["blocking_requirements"] == 0
    assert payload["broad_autodetection_promoted"] is False


def test_positive_corpus_exit_gate_cli_json_preview(tmp_path: Path, capsys) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    seed_exit_gate_reports(config)
    config_path = tmp_path / "config.toml"
    config_path.write_text(f'data_dir = "{config.data_dir}"\n', encoding="utf-8")

    assert (
        main(
            [
                "--config",
                str(config_path),
                "positive-corpus-exit-gate",
                "--no-write",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["state"] == "broad_autodetection_paused"
    assert payload["runtime_artifact_written"] is False
    assert payload["gate_decision"]["broad_autodetection_resume_allowed"] is False


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
