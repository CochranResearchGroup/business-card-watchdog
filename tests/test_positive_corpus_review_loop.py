from __future__ import annotations

import json
from pathlib import Path

from business_card_watchdog.cli import main
from business_card_watchdog.config import AppConfig
from business_card_watchdog.positive_corpus_review_loop import build_positive_corpus_training_review_loop


def seed_reports(config: AppConfig) -> None:
    corpus_root = config.data_dir / "positive_control_corpus"
    recognition_dir = corpus_root / "recognition_replays" / "recognition-fixture"
    workbench_dir = corpus_root / "workbench_evaluations" / "workbench-fixture"
    side_pair_dir = corpus_root / "side_pair_evaluations" / "side-pair-fixture"
    recognition_dir.mkdir(parents=True, exist_ok=True)
    workbench_dir.mkdir(parents=True, exist_ok=True)
    side_pair_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        recognition_dir / "recognition_replay.json",
        {
            "schema": "business-card-watchdog.positive-corpus-recognition-replay.v1",
            "replay_id": "recognition-fixture",
            "report_path": str(recognition_dir / "recognition_replay.json"),
            "false_negative_cases": [
                {
                    "entry_id": "positive-abc123",
                    "sha256_prefix": "abc123",
                    "media_kind": "image",
                    "group": "multi_card_image_candidate",
                    "page_number": 1,
                    "classifier_training_state": "not_business_card_high_confidence",
                    "decision": "not_business_card",
                    "score": 0.0,
                    "reasons": ["full-page document-like text layout"],
                    "candidate_tuning_reason": "known_positive_rejected_as_document_like",
                }
            ],
        },
    )
    _write_json(
        workbench_dir / "workbench_evaluation.json",
        {
            "schema": "business-card-watchdog.positive-corpus-crop-ocr-workbench.v1",
            "workbench_id": "workbench-fixture",
            "report_path": str(workbench_dir / "workbench_evaluation.json"),
            "crops_created": 1,
            "counts": {"ocr_artifacts": 2, "pdf_pages_materialized": 2},
            "processed_jobs": [
                {
                    "job_id": "job-1",
                    "media_kind": "pdf_page",
                    "page_number": 1,
                    "rasterization_mode": "fixture",
                    "classifier_training_state": "indeterminate_needs_app_intelligence",
                    "known_positive_bypass_admission": True,
                    "candidate_crop_count": 0,
                    "crop_quality_state": "no_crops",
                    "crop_acceptance_state": "missing",
                    "extraction_quality_status": "needs_review",
                    "ocr_quality_gate_state": "needs_app_intelligence_review",
                    "ocr_text_present": True,
                    "ocr_text_source": "derived_from_contact_spec",
                    "app_intelligence_request_count": 1,
                }
            ],
        },
    )
    _write_json(
        side_pair_dir / "side_pair_evaluation.json",
        {
            "schema": "business-card-watchdog.positive-corpus-side-pair-evaluation.v1",
            "evaluation_id": "side-pair-fixture",
            "report_path": str(side_pair_dir / "side_pair_evaluation.json"),
            "app_intelligence_review_requests": [
                {
                    "request_id": "side-pair-request-1",
                    "request_type": "pair_card_sides",
                    "reason": "conflicting OCR/domain evidence",
                    "page_numbers": [1, 2],
                    "side_labels": ["front", "back"],
                    "deterministic_evidence": {
                        "score": 2,
                        "negative_evidence_kinds": ["conflicting_contact_domains"],
                    },
                }
            ],
        },
    )


def test_positive_corpus_training_review_loop_builds_queue_without_live_actions(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    seed_reports(config)

    payload = build_positive_corpus_training_review_loop(config, write=True)

    assert payload["schema"] == "business-card-watchdog.positive-corpus-training-review-loop.v1"
    assert payload["state"] == "agent_review_ready"
    assert payload["review_item_count"] == 3
    assert payload["counts"]["recognition_items"] == 1
    assert payload["counts"]["crop_ocr_items"] == 1
    assert payload["counts"]["side_pair_items"] == 1
    assert payload["app_intelligence_request_count"] == 3
    assert payload["training_candidate_count"] == 3
    assert payload["counts"]["routing_allowed_items"] == 0
    assert payload["counts"]["sink_write_allowed_items"] == 0
    assert payload["counts"]["public_web_allowed_items"] == 0
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    assert payload["live_sink_calls_made"] is False
    assert payload["public_web_search_used"] is False
    assert payload["paid_enrichment_used"] is False
    assert payload["runtime_artifact_written"] is True
    assert Path(str(payload["report_path"])).exists()
    assert all(item["stop_conditions"] for item in payload["review_items"])
    assert all(request["allowed_answer_shape"] == "evidence_only_no_state_transition" for request in payload["app_intelligence_requests"])
    assert all(candidate["state"] == "candidate_requires_test_before_apply" for candidate in payload["training_candidates"])


def test_positive_corpus_training_review_loop_preview_writes_nothing(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    seed_reports(config)

    payload = build_positive_corpus_training_review_loop(config, write=False)

    assert payload["state"] == "agent_review_ready"
    assert payload["runtime_artifact_written"] is False
    assert payload["report_path"] is None
    assert not (config.data_dir / "positive_control_corpus" / "training_review_loops").exists()


def test_positive_corpus_training_review_loop_cli_json(tmp_path: Path, capsys) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    seed_reports(config)
    config_path = tmp_path / "config.toml"
    config_path.write_text(f'data_dir = "{config.data_dir}"\n', encoding="utf-8")

    assert (
        main(
            [
                "--config",
                str(config_path),
                "positive-corpus-training-review-loop",
                "--no-write",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["state"] == "agent_review_ready"
    assert payload["review_item_count"] == 3
    assert payload["runtime_artifact_written"] is False


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
