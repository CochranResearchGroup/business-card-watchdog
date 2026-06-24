from __future__ import annotations

import hashlib
import json
from pathlib import Path

from business_card_watchdog.cli import main
from business_card_watchdog.config import AppConfig, WatchConfig
from business_card_watchdog.service import BusinessCardService


def write_minimal_pdf(path: Path, *, pages: int = 1) -> Path:
    kids = " ".join(f"{index + 3} 0 R" for index in range(pages))
    objects = [
        "1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj",
        f"2 0 obj << /Type /Pages /Kids [{kids}] /Count {pages} >> endobj",
    ]
    for index in range(pages):
        objects.append(
            f"{index + 3} 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >> endobj"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("%PDF-1.4\n" + "\n".join(objects) + "\n%%EOF\n", encoding="utf-8")
    return path


def write_config(path: Path, *, data_dir: Path, scanner_dir: Path) -> None:
    path.write_text(
        f'data_dir = "{data_dir}"\n'
        "[paths]\n"
        f'scanner = "{scanner_dir}"\n'
        "[watch]\n"
        'inputs = ["$fsr:scanner"]\n',
        encoding="utf-8",
    )


def write_training_iteration(
    data_dir: Path,
    *,
    index: int,
    source_name: str,
    source_digest: str,
    counts: dict[str, int],
    outcome: str,
    app_requests: int = 0,
) -> None:
    run_id = f"classifier-training-fixture-{index:02d}"
    run_dir = data_dir / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "business-card-watchdog.classifier-training-iteration.v1",
        "generated_at": f"2026-06-24T12:{index:02d}:00+00:00",
        "run_id": run_id,
        "source_document_name": source_name,
        "source_document_sha256": source_digest,
        "source_document_path": f"/redacted/{source_name}",
        "page_count": counts["page_count"],
        "counts": counts,
        "app_intelligence_request_count": app_requests,
        "training_outcome": outcome,
        "writes_attempted": 0,
        "network_calls_made": 0,
        "live_sink_calls_made": False,
        "public_web_search_used": False,
        "paid_enrichment_used": False,
    }
    (run_dir / "classifier_training_iteration.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def test_classifier_training_iteration_selects_one_pdf_and_writes_iteration(tmp_path: Path) -> None:
    scanner = tmp_path / "scanner"
    first = write_minimal_pdf(scanner / "2026_06_01_10_00_00.pdf", pages=2)
    write_minimal_pdf(scanner / "2026_06_02_10_00_00.pdf", pages=1)
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        watch=WatchConfig(inputs=[str(scanner)]),
    )

    payload = BusinessCardService(config).classifier_training_iteration()

    assert payload["schema"] == "business-card-watchdog.classifier-training-iteration.v1"
    assert payload["source_document_name"] == first.name
    assert payload["page_count"] == 2
    assert payload["counts"]["page_count"] == 2
    assert payload["runtime_artifact_written"] is True
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    assert Path(payload["iteration_path"]).exists()
    assert all(Path(page["preclassification_path"]).exists() for page in payload["pages"])
    artifact_kinds = [
        json.loads(line)["kind"]
        for line in (config.runs_dir / payload["run_id"] / "artifacts.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert "document_pages" in artifact_kinds
    assert "classifier_training_iteration" in artifact_kinds


def test_classifier_training_report_summarizes_exit_gate_with_positive_control(tmp_path: Path) -> None:
    positive = write_minimal_pdf(tmp_path / "positive.pdf", pages=1)
    positive_digest = hashlib.sha256(positive.read_bytes()).hexdigest()
    data_dir = tmp_path / "data"
    write_training_iteration(
        data_dir,
        index=0,
        source_name=positive.name,
        source_digest=positive_digest,
        counts={
            "business_card_high_confidence": 1,
            "indeterminate_needs_app_intelligence": 0,
            "not_business_card_high_confidence": 0,
            "page_count": 1,
        },
        outcome="contains_business_card_candidates",
    )
    for index in range(1, 7):
        write_training_iteration(
            data_dir,
            index=index,
            source_name=f"not-card-{index}.pdf",
            source_digest=f"{index:064x}",
            counts={
                "business_card_high_confidence": 0,
                "indeterminate_needs_app_intelligence": 0,
                "not_business_card_high_confidence": 2,
                "page_count": 2,
            },
            outcome="not_business_card_document",
        )
    for index in range(7, 10):
        write_training_iteration(
            data_dir,
            index=index,
            source_name=f"ambiguous-{index}.pdf",
            source_digest=f"{index:064x}",
            counts={
                "business_card_high_confidence": 0,
                "indeterminate_needs_app_intelligence": 3,
                "not_business_card_high_confidence": 0,
                "page_count": 3,
            },
            outcome="needs_app_intelligence_document_type_review",
            app_requests=3,
        )
    write_training_iteration(
        data_dir,
        index=10,
        source_name="newer-not-card.pdf",
        source_digest=f"{10:064x}",
        counts={
            "business_card_high_confidence": 0,
            "indeterminate_needs_app_intelligence": 0,
            "not_business_card_high_confidence": 1,
            "page_count": 1,
        },
        outcome="not_business_card_document",
    )
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=data_dir)

    payload = BusinessCardService(config).classifier_training_report(
        limit=10,
        positive_control_source=str(positive),
    )

    assert payload["schema"] == "business-card-watchdog.classifier-training-report.v1"
    assert payload["iteration_count"] == 10
    assert payload["source_count"] == 10
    assert payload["positive_control"]["passed"] is True
    assert any(row["source_document_name"] == positive.name for row in payload["rows"])
    assert payload["aggregate"]["coverage"] == {
        "has_app_intelligence_escalations": True,
        "has_business_card_positive": True,
        "has_not_business_card_documents": True,
        "has_zero_live_side_effects": True,
    }
    assert payload["exit_gate"]["ready_to_resume_crop_ocr"] is True
    assert payload["exit_gate"]["crop_ocr_allowed_for_classifier_states"] == ["business_card_high_confidence"]
    assert payload["exit_gate"]["missing"] == []
    assert Path(payload["report_path"]).exists()
    assert all("source_document_path" not in row for row in payload["rows"])


def test_classifier_training_report_no_write_keeps_report_unwritten(tmp_path: Path, capsys) -> None:
    data_dir = tmp_path / "data"
    write_training_iteration(
        data_dir,
        index=0,
        source_name="only.pdf",
        source_digest="a" * 64,
        counts={
            "business_card_high_confidence": 0,
            "indeterminate_needs_app_intelligence": 0,
            "not_business_card_high_confidence": 1,
            "page_count": 1,
        },
        outcome="not_business_card_document",
    )
    config_path = tmp_path / "config.toml"
    write_config(config_path, data_dir=data_dir, scanner_dir=tmp_path)

    assert (
        main(
            [
                "--config",
                str(config_path),
                "runs",
                "classifier-training-report",
                "--limit",
                "1",
                "--no-write",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["runtime_artifact_written"] is False
    assert payload["report_path"] is None
    assert payload["exit_gate"]["ready_to_resume_crop_ocr"] is False


def test_classifier_training_iteration_no_write_keeps_runtime_summary_unwritten(
    tmp_path: Path,
    capsys,
) -> None:
    scanner = tmp_path / "scanner"
    source = write_minimal_pdf(scanner / "2026_06_01_10_00_00.pdf", pages=1)
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    write_config(config_path, data_dir=data_dir, scanner_dir=scanner)

    assert (
        main(
            [
                "--config",
                str(config_path),
                "runs",
                "classifier-training-iteration",
                "--source",
                str(source),
                "--no-write",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["source_document_name"] == source.name
    assert payload["runtime_artifact_written"] is False
    assert payload["iteration_path"] is None
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
