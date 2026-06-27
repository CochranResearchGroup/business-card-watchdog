from __future__ import annotations

import json
from pathlib import Path

from business_card_watchdog.cli import main
from business_card_watchdog.config import AppConfig
from business_card_watchdog.positive_corpus_side_pair import build_positive_corpus_side_pair_evaluation
from business_card_watchdog.positive_corpus_workbench import build_positive_corpus_workbench_evaluation
from business_card_watchdog.service import BusinessCardService

from synthetic_fixtures import SyntheticSkillAdapter


def write_pdf(path: Path, *, pages: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    objects = "\n".join(f"{index} 0 obj << /Type /Page >> endobj" for index in range(1, pages + 1))
    path.write_bytes(f"%PDF-1.7\n{objects}\n%%EOF\n".encode("utf-8"))
    return path


def seed_workbench(tmp_path: Path) -> tuple[AppConfig, Path, Path]:
    private_sources = tmp_path / "Private Known Positives"
    pdf = write_pdf(private_sources / "private-side-pair-scan.pdf", pages=8)
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    BusinessCardService(config).known_card_intake(source_paths=[str(pdf)], write=True)
    adapter = SyntheticSkillAdapter(
        specs_by_stem={
            "page-0001": {
                "full_name": "Ada Lovelace",
                "organization": "Example Labs",
                "email": "ada@example.test",
                "phone": "+1-555-0101",
                "website": "",
            },
            "page-0002": {
                "full_name": "",
                "organization": "Example Labs",
                "email": "",
                "phone": "",
                "website": "example.test/ada",
                "notes": "Backside QR and portfolio.",
            },
            "page-0003": {
                "full_name": "",
                "organization": "Second Labs",
                "email": "",
                "phone": "",
                "website": "second.test/grace",
                "notes": "Backside QR and portfolio.",
            },
            "page-0004": {
                "full_name": "Grace Hopper",
                "organization": "Second Labs",
                "email": "grace@second.test",
                "phone": "+1-555-0102",
                "website": "",
            },
            "page-0005": {
                "full_name": "Alan Turing",
                "organization": "Conflict Labs",
                "email": "alan@example.test",
                "phone": "+1-555-0103",
                "website": "",
            },
            "page-0006": {
                "full_name": "",
                "organization": "Other Labs",
                "email": "other@other.test",
                "phone": "",
                "website": "other.test/alan",
                "notes": "Backside QR but conflicting domain.",
            },
            "page-0007": {
                "full_name": "Blank Back",
                "organization": "Blank Labs",
                "email": "blank@example.test",
                "phone": "+1-555-0104",
                "website": "",
            },
            "page-0008": {
                "full_name": "",
                "organization": "",
                "email": "",
                "phone": "",
                "website": "",
                "notes": "",
            },
        },
        ocr_by_stem={
            "page-0001": "Ada Lovelace\nPrincipal Engineer\nExample Labs\nada@example.test\n+1 555 0101\n",
            "page-0002": "Scan QR\nexample.test/ada\nExample Labs portfolio\n",
            "page-0003": "Scan QR\nsecond.test/grace\nSecond Labs portfolio\n",
            "page-0004": "Grace Hopper\nOperations Manager\nSecond Labs\ngrace@second.test\n+1 555 0102\n",
            "page-0005": "Alan Turing\nDirector\nConflict Labs\nalan@example.test\n+1 555 0103\n",
            "page-0006": "Scan QR\nother@other.test\nother.test/alan\nOther Labs portfolio\n",
            "page-0007": "Blank Back\nBlank Labs\nblank@example.test\n+1 555 0104\n",
            "page-0008": "",
        },
    )
    workbench = build_positive_corpus_workbench_evaluation(config, write=True, workers=1, adapter=adapter)
    return config, Path(str(workbench["report_path"])), pdf


def test_positive_corpus_side_pair_evaluation_reports_pairs_and_review_cases(tmp_path: Path) -> None:
    config, workbench_report, private_pdf = seed_workbench(tmp_path)

    payload = build_positive_corpus_side_pair_evaluation(
        config,
        write=True,
        workbench_report_path=workbench_report,
    )
    serialized = json.dumps(payload, sort_keys=True)

    assert payload["schema"] == "business-card-watchdog.positive-corpus-side-pair-evaluation.v1"
    assert payload["state"] == "front_back_review_required"
    assert payload["scanner_pdf_count"] == 1
    assert payload["page_candidate_count"] == 8
    assert payload["counts"]["front_candidates"] == 4
    assert payload["counts"]["back_candidates"] >= 3
    assert payload["counts"]["blank_candidates"] == 1
    assert payload["counts"]["deterministic_pair_proposals"] >= 2
    assert payload["counts"]["blocked_pair_proposals"] >= 1
    assert payload["counts"]["blank_back_candidates"] >= 1
    assert payload["counts"]["backside_augmented_merges"] >= 1
    assert payload["counts"]["app_intelligence_review_requests"] >= 1
    assert payload["runtime_artifact_written"] is True
    assert Path(str(payload["report_path"])).exists()
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    assert payload["live_sink_calls_made"] is False
    assert payload["public_web_search_used"] is False
    assert payload["paid_enrichment_used"] is False
    proposed_pages = {
        (row["front_page_number"], row["back_page_number"])
        for row in payload["pair_proposal_summary"]["proposed"]
    }
    assert (1, 2) in proposed_pages
    assert (4, 3) in proposed_pages
    blocked = payload["pair_proposal_summary"]["blocked_for_review"]
    assert any("conflicting_contact_domains" in row["negative_evidence_kinds"] for row in blocked)
    assert str(private_pdf) not in serialized
    assert private_pdf.name not in serialized


def test_positive_corpus_side_pair_evaluation_preview_uses_latest_workbench_without_writing(
    tmp_path: Path,
) -> None:
    config, _, _ = seed_workbench(tmp_path)

    payload = build_positive_corpus_side_pair_evaluation(config, write=False)

    assert payload["state"] == "front_back_review_required"
    assert payload["runtime_artifact_written"] is False
    assert payload["report_path"] is None
    assert payload["counts"]["scanner_page_candidates"] == 8
    assert not (config.data_dir / "positive_control_corpus" / "side_pair_evaluations").exists()


def test_positive_corpus_side_pair_cli_json_preview_redacts_private_sources(
    tmp_path: Path,
    capsys,
) -> None:
    config, _, private_pdf = seed_workbench(tmp_path)
    config_path = tmp_path / "config.toml"
    config_path.write_text(f'data_dir = "{config.data_dir}"\n', encoding="utf-8")

    assert (
        main(
            [
                "--config",
                str(config_path),
                "positive-corpus-side-pair-evaluation",
                "--no-write",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    serialized = json.dumps(payload, sort_keys=True)

    assert payload["state"] == "front_back_review_required"
    assert payload["page_candidate_count"] == 8
    assert payload["runtime_artifact_written"] is False
    assert str(private_pdf) not in serialized
    assert private_pdf.name not in serialized
