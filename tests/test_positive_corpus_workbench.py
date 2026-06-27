from __future__ import annotations

import json
from pathlib import Path

from business_card_watchdog.cli import main
from business_card_watchdog.config import AppConfig
from business_card_watchdog.positive_corpus_workbench import build_positive_corpus_workbench_evaluation
from business_card_watchdog.service import BusinessCardService

from synthetic_fixtures import SyntheticSkillAdapter, write_multi_card_image, write_square_image


def write_pdf(path: Path, *, pages: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    objects = "\n".join(f"{index} 0 obj << /Type /Page >> endobj" for index in range(1, pages + 1))
    path.write_bytes(f"%PDF-1.7\n{objects}\n%%EOF\n".encode("utf-8"))
    return path


def seed_corpus(tmp_path: Path) -> tuple[AppConfig, list[Path]]:
    private_sources = tmp_path / "Private Known Positives"
    rejected_image = write_square_image(private_sources / "private-card-square.jpg")
    multi_card = write_multi_card_image(private_sources / "private-multi-card.jpg")
    pdf = write_pdf(private_sources / "private-front-back.pdf", pages=2)
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    BusinessCardService(config).known_card_intake(
        source_paths=[str(rejected_image), str(multi_card), str(pdf)],
        write=True,
    )
    return config, [rejected_image, multi_card, pdf]


def test_positive_corpus_workbench_processes_known_positives_without_sink_work(tmp_path: Path) -> None:
    config, private_sources = seed_corpus(tmp_path)
    adapter = SyntheticSkillAdapter()

    payload = build_positive_corpus_workbench_evaluation(
        config,
        write=True,
        workers=1,
        adapter=adapter,
    )
    serialized = json.dumps(payload, sort_keys=True)

    assert payload["schema"] == "business-card-watchdog.positive-corpus-crop-ocr-workbench.v1"
    assert payload["state"] == "workbench_review_required"
    assert payload["source_count"] == 3
    assert payload["counts"]["images"] == 2
    assert payload["counts"]["pdf_documents"] == 1
    assert payload["counts"]["pdf_pages_materialized"] == 2
    assert payload["counts"]["processed_jobs"] == 4
    assert payload["counts"]["ocr_artifacts"] == 4
    assert payload["counts"]["contact_drafts"] == 4
    assert payload["counts"]["review_packets"] == 4
    assert payload["counts"]["review_required_jobs"] == 4
    assert payload["counts"]["known_positive_classifier_bypass_admissions"] >= 1
    assert payload["counts"]["bounded_review_evidence_jobs"] == 4
    assert payload["known_positive_classifier_bypass_used"] is True
    assert payload["contacts_review_required"] is True
    assert payload["dry_run"] is True
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    assert payload["live_sink_calls_made"] is False
    assert payload["public_web_search_used"] is False
    assert payload["paid_enrichment_used"] is False
    assert payload["runtime_artifact_written"] is True
    assert Path(payload["report_path"]).exists()
    assert adapter.apply_google_calls == [False, False, False, False]
    assert not list(Path(payload["run_dir"]).glob("artifacts/*/sink_payloads.json"))
    assert all(job["state"] == "needs_review" for job in payload["processed_jobs"])
    assert any(job["media_kind"] == "pdf_page" and job["page_number"] == 1 for job in payload["processed_jobs"])
    for source in private_sources:
        assert str(source) not in serialized
        assert source.name not in serialized


def test_positive_corpus_workbench_preview_writes_nothing(tmp_path: Path) -> None:
    config, _ = seed_corpus(tmp_path)

    payload = build_positive_corpus_workbench_evaluation(config, write=False)

    assert payload["state"] == "ready_for_runtime_workbench"
    assert payload["runtime_artifact_written"] is False
    assert payload["run_dir"] is None
    assert payload["report_path"] is None
    assert payload["counts"]["sources_ready"] == 3
    assert not (config.data_dir / "positive_control_corpus" / "workbench_evaluations").exists()


def test_positive_corpus_workbench_cli_json_preview_redacts_private_sources(
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
                "positive-corpus-workbench-evaluation",
                "--no-write",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    serialized = json.dumps(payload, sort_keys=True)

    assert payload["state"] == "ready_for_runtime_workbench"
    assert payload["source_count"] == 3
    assert payload["runtime_artifact_written"] is False
    for source in private_sources:
        assert str(source) not in serialized
        assert source.name not in serialized
