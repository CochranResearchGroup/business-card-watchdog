from __future__ import annotations

import json
from pathlib import Path

from business_card_watchdog.cli import main
from business_card_watchdog.config import AppConfig
from business_card_watchdog.positive_control_side_pair_evidence import build_positive_control_side_pair_evidence
from business_card_watchdog.service import BusinessCardService


def write_pdf(path: Path, *, pages: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    objects = "\n".join(f"{index} 0 obj << /Type /Page >> endobj" for index in range(1, pages + 1))
    path.write_bytes(f"%PDF-1.7\n{objects}\n%%EOF\n".encode("utf-8"))
    return path


def seed_pdf_corpus(tmp_path: Path, *, pages: int) -> tuple[AppConfig, Path]:
    source_dir = tmp_path / "Private Side Pair Positives"
    pdf = write_pdf(source_dir / "private-front-back.pdf", pages=pages)
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    BusinessCardService(config).known_card_intake(source_paths=[str(pdf)], write=True)
    return config, pdf


def accepted_pdf_candidate_ids(config: AppConfig) -> dict[int, str]:
    preview = BusinessCardService(config).positive_control_crop_workbench(write=False)
    return {
        int(unit["page_number"]): f"{unit['unit_id']}-crop-001"
        for source in preview["source_results"]
        for unit in source["processing_units"]
        if unit["media_kind"] == "pdf_page"
    }


FRONT_TEXT = "Ada Lovelace\nada@example.test\n+1 555 010 1234\n"
BACK_TEXT = "Scan QR\nExample Labs\nlinkedin.com/in/ada\nexample.test/ada\n"


def test_positive_control_side_pair_evidence_pairs_front_back_and_augments(
    tmp_path: Path,
) -> None:
    config, private_pdf = seed_pdf_corpus(tmp_path, pages=2)
    candidate_ids = accepted_pdf_candidate_ids(config)

    payload = build_positive_control_side_pair_evidence(
        config,
        write=False,
        ocr_text_by_candidate_id={
            candidate_ids[1]: FRONT_TEXT,
            candidate_ids[2]: BACK_TEXT,
        },
    )
    serialized = json.dumps(payload, sort_keys=True)
    edge = payload["edges"][0]

    assert payload["schema"] == "business-card-watchdog.positive-control-side-pair-evidence.v1"
    assert payload["state"] == "ready_for_runtime_side_pair_evidence"
    assert edge["state"] == "pair_proposed"
    assert edge["front_back_order"] == "front_back"
    assert edge["reason"] in {"shared_domain", "identity_plus_backside_contextual_cues"}
    assert "organization" in edge["merge_evidence"]["backside_augmented_fields"]
    assert edge["merge_evidence"]["direct_sink_update_allowed"] is False
    assert payload["counts"]["pair_proposed"] == 1
    assert payload["counts"]["backside_augmented_edges"] == 1
    assert payload["sink_payloads_created"] == 0
    assert payload["routing_allowed"] is False
    assert payload["enrichment_allowed"] is False
    assert payload["public_web_search_used"] is False
    assert payload["paid_enrichment_used"] is False
    assert payload["runtime_artifact_written"] is False
    assert payload["report_path"] is None
    assert str(private_pdf) not in serialized
    assert private_pdf.name not in serialized


def test_positive_control_side_pair_evidence_pairs_back_front_order(
    tmp_path: Path,
) -> None:
    config, _ = seed_pdf_corpus(tmp_path, pages=2)
    candidate_ids = accepted_pdf_candidate_ids(config)

    payload = build_positive_control_side_pair_evidence(
        config,
        write=False,
        ocr_text_by_candidate_id={
            candidate_ids[1]: BACK_TEXT,
            candidate_ids[2]: FRONT_TEXT,
        },
    )
    edge = payload["edges"][0]

    assert edge["state"] == "pair_proposed"
    assert edge["front_back_order"] == "back_front"
    assert edge["front_draft_id"] == f"draft-{candidate_ids[2]}"
    assert edge["back_draft_id"] == f"draft-{candidate_ids[1]}"


def test_positive_control_side_pair_evidence_handles_front_only_and_dropped_blank_back(
    tmp_path: Path,
) -> None:
    front_only_config, _ = seed_pdf_corpus(tmp_path / "front-only", pages=1)
    front_only_ids = accepted_pdf_candidate_ids(front_only_config)
    front_only_payload = build_positive_control_side_pair_evidence(
        front_only_config,
        write=False,
        ocr_text_by_candidate_id={front_only_ids[1]: FRONT_TEXT},
    )

    dropped_back_config, _ = seed_pdf_corpus(tmp_path / "dropped-back", pages=2)
    dropped_back_ids = accepted_pdf_candidate_ids(dropped_back_config)
    dropped_back_payload = build_positive_control_side_pair_evidence(
        dropped_back_config,
        write=False,
        ocr_text_by_candidate_id={dropped_back_ids[1]: FRONT_TEXT},
    )

    assert front_only_payload["edges"][0]["state"] == "front_only"
    assert front_only_payload["edges"][0]["front_back_order"] == "front_only"
    assert dropped_back_payload["edges"][0]["state"] == "blank_or_dropped_back"
    assert dropped_back_payload["edges"][0]["merge_evidence"]["state"] == "blank_or_dropped_back"


def test_positive_control_side_pair_evidence_blocks_conflicting_adjacent_pages(
    tmp_path: Path,
) -> None:
    config, _ = seed_pdf_corpus(tmp_path, pages=2)
    candidate_ids = accepted_pdf_candidate_ids(config)

    payload = build_positive_control_side_pair_evidence(
        config,
        write=False,
        ocr_text_by_candidate_id={
            candidate_ids[1]: "Ada Lovelace\nExample Labs\nada@example.test\n+1 555 010 1234\n",
            candidate_ids[2]: "Bob Stone\nOther Org\nbob@other.example\n+1 555 999 8888\n",
        },
    )
    edge = payload["edges"][0]

    assert payload["state"] == "ready_for_runtime_side_pair_evidence"
    assert edge["state"] == "blocked_conflict"
    assert set(edge["conflict_evidence"]["conflict_fields"]) >= {"email", "phone", "domain"}
    assert edge["merge_evidence"]["state"] == "blocked_conflict"
    assert len(payload["review_requests"]) == 1
    assert payload["review_requests"][0]["allowed_outputs"] == [
        "same_card_pair",
        "not_same_card",
        "blank_or_dropped_back",
        "front_only",
        "needs_more_ocr_or_visual_evidence",
    ]


def test_positive_control_side_pair_evidence_cli_preview_redacts_and_writes_nothing(
    tmp_path: Path,
    capsys,
) -> None:
    config, private_pdf = seed_pdf_corpus(tmp_path, pages=2)
    config_path = tmp_path / "config.toml"
    config_path.write_text(f'data_dir = "{config.data_dir}"\n', encoding="utf-8")

    assert (
        main(
            [
                "--config",
                str(config_path),
                "positive-control-side-pair-evidence",
                "--no-write",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    serialized = json.dumps(payload, sort_keys=True)

    assert payload["state"] == "ready_for_runtime_side_pair_evidence"
    assert payload["runtime_artifact_written"] is False
    assert payload["report_path"] is None
    assert payload["counts"]["edges"] == 1
    assert payload["counts"]["app_intelligence_review_requests"] == 1
    assert payload["sink_payloads_created"] == 0
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    assert payload["live_sink_calls_made"] is False
    assert not (config.data_dir / "positive_control_corpus" / "side_pair_evidence").exists()
    assert str(private_pdf) not in serialized
    assert private_pdf.name not in serialized
