from __future__ import annotations

import json
from pathlib import Path

from business_card_watchdog.cli import main
from business_card_watchdog.config import AppConfig, PrefilterConfig, WatchConfig
from business_card_watchdog.orchestrator import BatchOrchestrator
from business_card_watchdog.service import BusinessCardService

from synthetic_fixtures import SyntheticSkillAdapter, read_jsonl, write_synthetic_image


def write_seed(path: Path, content: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def write_minimal_pdf(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "%PDF-1.4\n"
        "1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        "2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
        "3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >> endobj\n"
        "%%EOF\n",
        encoding="utf-8",
    )
    return path


def test_positive_control_preview_redacts_private_seed_paths_and_writes_nothing(tmp_path: Path) -> None:
    scanner = tmp_path / "private-scanner"
    front = write_seed(scanner / "front-card.png", b"front")
    back = write_seed(scanner / "back-card.png", b"back")
    insert = write_seed(scanner / "insert.png", b"insert")
    pdf = write_minimal_pdf(scanner / "scan.pdf")
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
        watch=WatchConfig(inputs=[str(scanner)], status_recursive=True),
    )

    payload = BusinessCardService(config).watch_positive_controls(write=False)
    raw = json.dumps(payload, sort_keys=True)

    assert payload["schema"] == "business-card-watchdog.positive-control-manifest.v1"
    assert payload["state"] == "ready_for_side_pair_ocr_training"
    assert payload["image_seed_count"] == 3
    assert payload["pdf_seed_count"] == 1
    assert payload["scenario_count"] == 5
    assert payload["runtime_artifact_written"] is False
    assert payload["generated_file_count"] == 0
    assert payload["output_root"] is None
    assert "front_then_back" in {scenario["scenario_id"] for scenario in payload["scenarios"]}
    assert "interleaved_non_card_page" in {scenario["scenario_id"] for scenario in payload["scenarios"]}
    assert str(front) not in raw
    assert str(back) not in raw
    assert str(insert) not in raw
    assert str(pdf) not in raw
    assert "front-card.png" not in raw
    assert all(seed["private_path_redacted"] is True for seed in payload["seeds"])
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    assert payload["live_sink_calls_made"] is False
    assert not (config.data_dir / "positive_controls").exists()
    assert not (config.cache_dir / "positive_controls").exists()


def test_positive_control_write_generates_runtime_only_manifest_and_files(tmp_path: Path) -> None:
    seed_dir = tmp_path / "seeds"
    write_seed(seed_dir / "a.png", b"a")
    write_seed(seed_dir / "b.png", b"b")
    write_seed(seed_dir / "c.png", b"c")
    write_seed(seed_dir / "d.png", b"d")
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
        watch=WatchConfig(inputs=[str(seed_dir)], status_recursive=True),
    )

    payload = BusinessCardService(config).watch_positive_controls(write=True)

    assert payload["runtime_artifact_written"] is True
    assert payload["scenario_count"] == 6
    assert payload["generated_file_count"] > 0
    assert Path(str(payload["manifest_path"])).exists()
    assert Path(str(payload["output_root"])).is_dir()
    assert str(payload["output_root"]).startswith(str(config.cache_dir))
    multi_card = next(scenario for scenario in payload["scenarios"] if scenario["scenario_id"] == "multi_card_no_cross_merge")
    assert multi_card["expected_pair_groups"] == [["page_001", "page_002"], ["page_003", "page_004"]]
    assert multi_card["expected_no_merge_boundaries"] == [["page_002", "page_003"]]
    assert all(Path(str(page["generated_path"])).exists() for page in multi_card["pages"])
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    assert payload["public_web_search_used"] is False
    assert payload["paid_enrichment_used"] is False


def test_positive_controls_cli_preview_json(tmp_path: Path, capsys) -> None:
    seed_dir = tmp_path / "seeds"
    write_seed(seed_dir / "front.png", b"front")
    write_seed(seed_dir / "back.png", b"back")
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f'data_dir = "{tmp_path / "data"}"\n'
        f'cache_dir = "{tmp_path / "cache"}"\n'
        "[watch]\n"
        f'inputs = ["{seed_dir}"]\n',
        encoding="utf-8",
    )

    assert (
        main(
            [
                "--config",
                str(config_path),
                "watch-positive-controls",
                "--no-write",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["state"] == "ready_for_side_pair_ocr_training"
    assert payload["scenario_count"] == 4
    assert payload["runtime_artifact_written"] is False


def test_generated_positive_control_front_back_dry_run_has_zero_live_side_effects(
    tmp_path: Path,
    monkeypatch,
) -> None:
    seed_dir = tmp_path / "seeds"
    write_synthetic_image(seed_dir / "front.png")
    write_synthetic_image(seed_dir / "back.png")
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
        prefilter=PrefilterConfig(enabled=False),
        watch=WatchConfig(inputs=[str(seed_dir)], status_recursive=True),
    )
    manifest = BusinessCardService(config).watch_positive_controls(write=True)
    scenario = next(row for row in manifest["scenarios"] if row["scenario_id"] == "front_then_back")
    scenario_dir = Path(str(scenario["pages"][0]["generated_path"])).parent
    orchestrator = BatchOrchestrator(config)
    monkeypatch.setattr(
        orchestrator,
        "adapter",
        SyntheticSkillAdapter(
            specs_by_stem={
                "page_001": {
                    "full_name": "Ada Lovelace",
                    "organization": "Example Labs",
                    "title": "Principal Engineer",
                    "email": "ada@example.test",
                    "phone": "+1 555 010 1234",
                },
                "page_002": {
                    "full_name": "",
                    "organization": "",
                    "title": "",
                    "email": "",
                    "phone": "",
                    "website": "example.test/ada",
                },
            },
            ocr_by_stem={
                "page_001": "Ada Lovelace\nPrincipal Engineer\nExample Labs\nada@example.test\n+1 555 010 1234\n",
                "page_002": "Scan QR\nlinkedin.com/in/ada\nexample.test/ada\n",
            },
        ),
    )

    run_dir = orchestrator.process_source(str(scenario_dir), dry_run=True, workers=1)
    closeout = BusinessCardService(config).dry_run_closeout(run_dir.name, write=False)
    artifacts = read_jsonl(run_dir / "artifacts.jsonl")
    graph_path = next(row["path"] for row in artifacts if row["kind"] == "side_pair_graph")
    graph = json.loads(Path(graph_path).read_text(encoding="utf-8"))

    assert graph["pair_proposal_count"] == 1
    assert graph["pair_proposals"][0]["state"] == "pair_proposed"
    assert closeout["sink_payload_count"] == 0
    assert closeout["writes_attempted"] == 0
    assert closeout["network_calls_made"] == 0
    assert closeout["live_sink_calls_made"] is False
    assert closeout["public_web_search_used"] is False
    assert closeout["paid_enrichment_used"] is False
