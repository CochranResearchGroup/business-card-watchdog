from __future__ import annotations

import json
from pathlib import Path

from business_card_watchdog.card_sides import build_pair_proposals, classify_card_side
from business_card_watchdog.config import AppConfig, PrefilterConfig
from business_card_watchdog.orchestrator import BatchOrchestrator
from business_card_watchdog.service import BusinessCardService

from synthetic_fixtures import SyntheticSkillAdapter, latest_jobs_by_id, read_jsonl


def _source_page(page_number: int) -> dict[str, object]:
    return {
        "source_document_path": "/tmp/cards.pdf",
        "page_number": page_number,
        "page_image_path": f"/tmp/page-{page_number:04d}.png",
        "media_kind": "page_image",
        "rasterization_mode": "fixture",
        "sha256": "0" * 64,
    }


def test_card_side_classifier_uses_ocr_contextual_clues() -> None:
    front = classify_card_side(
        job_id="front",
        source_page=_source_page(1),
        ocr_text="Ada Lovelace\nPrincipal Engineer\nExample Labs\nada@example.test\n+1 555 010 1234",
    )
    back = classify_card_side(
        job_id="back",
        source_page=_source_page(2),
        ocr_text="Scan QR for portfolio\nlinkedin.com/in/ada\nexample.test",
    )
    blank = classify_card_side(job_id="blank", source_page=_source_page(3), ocr_text="  \n")
    unknown = classify_card_side(
        job_id="unknown",
        source_page=_source_page(4),
        ocr_text="hello notes miscellaneous",
    )

    assert front["side_label"] == "front"
    assert front["features"]["email_count"] == 1
    assert back["side_label"] == "back"
    assert back["features"]["back_word_count"] >= 1
    assert blank["side_label"] == "blank"
    assert unknown["side_label"] == "unknown"


def test_pair_proposals_support_reversed_order_and_conflict_blocks() -> None:
    front = classify_card_side(
        job_id="front",
        source_page=_source_page(2),
        ocr_text="Ada Lovelace\nPrincipal Engineer\nada@example.test\n+1 555 010 1234",
    )
    back = classify_card_side(
        job_id="back",
        source_page=_source_page(1),
        ocr_text="linkedin.com/in/ada\nexample.test",
    )
    proposed = build_pair_proposals(run_id="run", side_candidates=[back, front])
    assert proposed["proposal_count"] == 1
    assert proposed["proposals"][0]["state"] == "proposed"
    assert proposed["proposals"][0]["front_job_id"] == "front"
    assert proposed["proposals"][0]["back_job_id"] == "back"

    conflicting_back = classify_card_side(
        job_id="bad-back",
        source_page=_source_page(3),
        ocr_text="linkedin.com/in/other\nother@example.org\n+1 555 010 9999",
    )
    blocked = build_pair_proposals(run_id="run", side_candidates=[front, conflicting_back])
    assert blocked["proposal_count"] == 1
    assert blocked["proposals"][0]["state"] == "blocked_for_review"
    assert blocked["proposals"][0]["negative_evidence"][0]["kind"] == "conflicting_email_domains"


def test_scanner_pdf_run_records_side_classification_and_pair_proposals(
    tmp_path: Path, monkeypatch
) -> None:
    source_pdf = tmp_path / "scanner" / "front-back.pdf"
    source_pdf.parent.mkdir(parents=True)
    source_pdf.write_bytes(
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Page >> endobj\n"
        b"2 0 obj << /Type /Page >> endobj\n"
        b"%%EOF\n"
    )
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
        prefilter=PrefilterConfig(enabled=False),
    )
    orchestrator = BatchOrchestrator(config)
    monkeypatch.setattr(
        orchestrator,
        "adapter",
        SyntheticSkillAdapter(
            specs_by_stem={
                "page-0001": {"email": "ada@example.test", "full_name": "Ada Lovelace"},
                "page-0002": {"email": "", "full_name": ""},
            },
            ocr_by_stem={
                "page-0001": (
                    "Ada Lovelace\nPrincipal Engineer\nExample Labs\n"
                    "ada@example.test\n+1 555 010 1234\n"
                ),
                "page-0002": "Scan QR\nlinkedin.com/in/ada\nexample.test\n",
            },
        ),
    )

    run_dir = orchestrator.process_source(str(source_pdf), dry_run=True, workers=1)

    pair_artifact = next(
        artifact for artifact in read_jsonl(run_dir / "artifacts.jsonl") if artifact["kind"] == "card_side_pair_proposals"
    )
    pairs = json.loads(Path(pair_artifact["path"]).read_text(encoding="utf-8"))
    assert pairs["proposal_count"] == 1
    assert pairs["proposals"][0]["state"] == "proposed"
    labels = set()
    for job in latest_jobs_by_id(run_dir / "jobs.jsonl").values():
        side = json.loads((Path(job["artifact_dir"]) / "card_side_candidate.json").read_text(encoding="utf-8"))
        labels.add(side["side_label"])
        assert side["ocr_text_sha256"]
    assert labels == {"front", "back"}
    detail = BusinessCardService(config).get_contact(
        BusinessCardService(config).list_contacts()["contacts"][0]["contact_id"]
    )["contact"]
    assert "card_side_classification" in {asset["asset_kind"] for asset in detail["assets"]}


def test_scanner_pdf_blank_back_does_not_create_pair_proposal(tmp_path: Path, monkeypatch) -> None:
    source_pdf = tmp_path / "scanner" / "blank-back.pdf"
    source_pdf.parent.mkdir(parents=True)
    source_pdf.write_bytes(
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Page >> endobj\n"
        b"2 0 obj << /Type /Page >> endobj\n"
        b"%%EOF\n"
    )
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
        prefilter=PrefilterConfig(enabled=False),
    )
    orchestrator = BatchOrchestrator(config)
    monkeypatch.setattr(
        orchestrator,
        "adapter",
        SyntheticSkillAdapter(
            ocr_by_stem={
                "page-0001": "Ada Lovelace\nPrincipal Engineer\nada@example.test\n+1 555 010 1234\n",
                "page-0002": "\n \n",
            }
        ),
    )

    run_dir = orchestrator.process_source(str(source_pdf), dry_run=True, workers=1)
    pair_artifact = next(
        artifact for artifact in read_jsonl(run_dir / "artifacts.jsonl") if artifact["kind"] == "card_side_pair_proposals"
    )
    pairs = json.loads(Path(pair_artifact["path"]).read_text(encoding="utf-8"))
    assert pairs["proposal_count"] == 0
    assert pairs["skipped"][0]["side_labels"] == ["front", "blank"]
