from __future__ import annotations

import json
from pathlib import Path

from business_card_watchdog.cli import main
from business_card_watchdog.config import AppConfig
from business_card_watchdog.positive_control_training_review_loop import build_positive_control_training_review_loop


def seed_reports(config: AppConfig) -> None:
    corpus_root = config.data_dir / "positive_control_corpus"
    recognition_dir = corpus_root / "recognition_training_replays" / "recognition-training-fixture"
    crop_dir = corpus_root / "crop_workbenches" / "crop-fixture"
    ocr_dir = corpus_root / "ocr_contact_drafts" / "ocr-fixture"
    side_pair_dir = corpus_root / "side_pair_evidence" / "side-pair-fixture"
    recognition_dir.mkdir(parents=True, exist_ok=True)
    crop_dir.mkdir(parents=True, exist_ok=True)
    ocr_dir.mkdir(parents=True, exist_ok=True)
    side_pair_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        recognition_dir / "recognition_training_replay.json",
        {
            "schema": "business-card-watchdog.positive-control-recognition-training-replay.v1",
            "replay_id": "recognition-training-fixture",
            "page_cases": [
                {
                    "case_id": "positive-abc-page-001",
                    "entry_id": "positive-abc",
                    "sha256_prefix": "abc123",
                    "media_kind": "pdf_page",
                    "page_number": 1,
                    "baseline_training_state": "not_business_card_high_confidence",
                    "tuned_training_state": "indeterminate_needs_app_intelligence",
                    "decision": "not_business_card",
                    "score": 0.0,
                    "reasons": ["document-like page"],
                    "tuning_reason": "known_positive_pdf_page_requires_vision_or_ocr_context",
                }
            ],
            "scenario_results": [
                {
                    "scenario_id": "scenario-1",
                    "scenario_kind": "front_back_swapped_pdf",
                    "source_entry_id": "positive-abc",
                    "source_kind": "scanner_pdf_front_back_sequence_candidate",
                    "operation_names": ["swap_adjacent_front_back_pages"],
                    "baseline_page_states": ["indeterminate_needs_app_intelligence"],
                    "app_intelligence_review_required": True,
                }
            ],
        },
    )
    _write_json(
        crop_dir / "crop_workbench.json",
        {
            "schema": "business-card-watchdog.positive-control-crop-workbench.v1",
            "workbench_id": "crop-fixture",
            "pdfs_rasterized": 2,
            "crops_created": 0,
            "review_requests": [
                {
                    "request_id": "crop-review-1",
                    "reason": "multi_card_image_needs_child_crop_review",
                    "evidence": {
                        "entry_id": "positive-multi",
                        "source_kind": "multi_card_image_candidate",
                        "page_number": None,
                    },
                }
            ],
        },
    )
    _write_json(
        ocr_dir / "ocr_contact_drafts.json",
        {
            "schema": "business-card-watchdog.positive-control-ocr-contact-drafts.v1",
            "draft_id": "ocr-fixture",
            "ocr_attempted": 2,
            "pdfs_rasterized": 2,
            "review_items": [
                {
                    "review_item_id": "candidate-1-missing-ocr",
                    "kind": "missing_ocr",
                    "severity": "blocking",
                    "message": "OCR text is missing.",
                },
                {
                    "review_item_id": "candidate-1-missing-contact-points",
                    "kind": "missing_contact_points",
                    "severity": "review",
                    "message": "No email or phone was extracted.",
                },
            ],
        },
    )
    _write_json(
        side_pair_dir / "side_pair_evidence.json",
        {
            "schema": "business-card-watchdog.positive-control-side-pair-evidence.v1",
            "report_id": "side-pair-fixture",
            "edges": [
                {
                    "edge_id": "edge-1",
                    "entry_id": "positive-abc",
                    "state": "review_required",
                    "reason": "insufficient deterministic side-pair evidence",
                    "page_numbers": [1, 2],
                    "deterministic_clues": {"left_ocr_missing": True, "right_ocr_missing": True},
                    "conflict_evidence": {},
                }
            ],
        },
    )


def test_positive_control_training_review_loop_builds_agent_queue_without_live_actions(
    tmp_path: Path,
) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    seed_reports(config)

    payload = build_positive_control_training_review_loop(config, write=True)

    assert payload["schema"] == "business-card-watchdog.positive-control-training-review-loop.v1"
    assert payload["state"] == "agent_review_ready"
    assert payload["review_item_count"] == 6
    assert payload["training_candidate_count"] == 6
    assert payload["app_intelligence_request_count"] == 2
    assert payload["counts"]["recognition_items"] == 1
    assert payload["counts"]["recognition_scenario_items"] == 1
    assert payload["counts"]["crop_items"] == 1
    assert payload["counts"]["ocr_items"] == 2
    assert payload["counts"]["side_pair_items"] == 1
    assert payload["counts"]["routing_allowed_items"] == 0
    assert payload["counts"]["sink_write_allowed_items"] == 0
    assert payload["counts"]["public_web_allowed_items"] == 0
    assert {item["agent_next_output"] for item in payload["review_items"]} >= {
        "fixture_or_test_proposal",
        "deterministic_rule_proposal",
        "bounded_app_intelligence_evidence_request",
        "explicit_stop_condition",
    }
    assert all(item["state"] == "agent_review_required" for item in payload["review_items"])
    assert all(candidate["state"] == "candidate_requires_test_before_apply" for candidate in payload["training_candidates"])
    assert all(request["allowed_answer_shape"] == "evidence_only_no_state_transition" for request in payload["app_intelligence_requests"])
    assert payload["sink_payloads_created"] == 0
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    assert payload["live_sink_calls_made"] is False
    assert payload["public_web_search_used"] is False
    assert payload["paid_enrichment_used"] is False
    assert payload["runtime_artifact_written"] is True
    assert Path(payload["report_path"]).exists()


def test_positive_control_training_review_loop_preview_writes_nothing(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    seed_reports(config)

    payload = build_positive_control_training_review_loop(config, write=False)

    assert payload["state"] == "ready_for_runtime_training_review_loop"
    assert payload["runtime_artifact_written"] is False
    assert payload["report_path"] is None
    assert payload["review_item_count"] == 6
    assert not (config.data_dir / "positive_control_corpus" / "training_review_loops").exists()


def test_positive_control_training_review_loop_cli_json(tmp_path: Path, capsys) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    seed_reports(config)
    config_path = tmp_path / "config.toml"
    config_path.write_text(f'data_dir = "{config.data_dir}"\n', encoding="utf-8")

    assert (
        main(
            [
                "--config",
                str(config_path),
                "positive-control-training-review-loop",
                "--no-write",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["state"] == "ready_for_runtime_training_review_loop"
    assert payload["review_item_count"] == 6
    assert payload["runtime_artifact_written"] is False


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
