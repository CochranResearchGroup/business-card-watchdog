from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from business_card_watchdog.cli import main
from business_card_watchdog.config import AppConfig, WatchConfig
from business_card_watchdog.service import BusinessCardService
from business_card_watchdog.watcher import PollingWatcher, WatchStateStore

from synthetic_fixtures import write_synthetic_image


def make_config(tmp_path: Path, source: Path, *, settle_seconds: float = 0.0) -> AppConfig:
    return AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
        watch=WatchConfig(inputs=[str(source)], settle_seconds=settle_seconds),
    )


def fake_process(watcher: PollingWatcher, processed: list[str], tmp_path: Path) -> None:
    def process_source(source: str, *, dry_run: bool = True, workers: int = 1) -> Path:
        processed.append(Path(source).name)
        run_dir = tmp_path / "data" / "runs" / f"run-{len(processed)}"
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    watcher.orchestrator.process_source = process_source  # type: ignore[method-assign]


def set_mtime(path: Path, timestamp: float) -> None:
    os.utime(path, (timestamp, timestamp))


def test_watcher_defers_unsettled_file_until_snapshot_stabilizes(tmp_path: Path) -> None:
    source = tmp_path / "cards"
    card = write_synthetic_image(source / "partial.png")
    config = make_config(tmp_path, source, settle_seconds=60.0)
    watcher = PollingWatcher(config)
    processed: list[str] = []
    fake_process(watcher, processed, tmp_path)

    set_mtime(card, time.time())
    assert watcher.scan_once(dry_run=True) == []
    assert processed == []

    old = time.time() - 120
    card.write_bytes(card.read_bytes() + b"more")
    set_mtime(card, old)
    assert watcher.scan_once(dry_run=True) == []
    assert processed == []

    assert [path.name for path in watcher.scan_once(dry_run=True)] == ["partial.png"]
    assert processed == ["partial.png"]

    status = watcher.status()
    assert status.seen_count == 1
    assert status.backlog_count == 0
    assert status.unsettled_count == 0


def test_seen_files_persist_across_watcher_restart(tmp_path: Path) -> None:
    source = tmp_path / "cards"
    write_synthetic_image(source / "card.png")
    config = make_config(tmp_path, source, settle_seconds=0.0)
    processed: list[str] = []

    first = PollingWatcher(config)
    fake_process(first, processed, tmp_path)
    assert [path.name for path in first.scan_once(dry_run=True)] == ["card.png"]

    second = PollingWatcher(config)
    fake_process(second, processed, tmp_path)
    assert second.scan_once(dry_run=True) == []
    assert processed == ["card.png"]

    seen_path = config.watch_dir / "seen-files.jsonl"
    seen_rows = [json.loads(line) for line in seen_path.read_text(encoding="utf-8").splitlines()]
    assert seen_rows[0]["key"].endswith("card.png")


def test_watcher_processes_pdf_document_sources(tmp_path: Path) -> None:
    source = tmp_path / "scanner"
    source.mkdir()
    pdf = source / "scan.pdf"
    pdf.write_bytes(b"%PDF-1.4\n1 0 obj << /Type /Page >> endobj\n%%EOF\n")
    config = make_config(tmp_path, source, settle_seconds=0.0)
    watcher = PollingWatcher(config)
    processed: list[str] = []
    fake_process(watcher, processed, tmp_path)

    assert [path.name for path in watcher.scan_once(dry_run=True)] == ["scan.pdf"]
    assert processed == ["scan.pdf"]
    assert PollingWatcher(config).status().backlog_count == 0


def test_watcher_scan_once_can_scope_to_input_ref(tmp_path: Path) -> None:
    phone = tmp_path / "phone"
    scanner = tmp_path / "scanner"
    write_synthetic_image(phone / "phone-card.png")
    write_synthetic_image(scanner / "scanner-card.png")
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
        watch=WatchConfig(inputs=[str(phone), str(scanner)], settle_seconds=0.0),
    )
    watcher = PollingWatcher(config)
    processed: list[str] = []
    fake_process(watcher, processed, tmp_path)

    assert [path.name for path in watcher.scan_once(dry_run=True, input_refs=["input_1"])] == [
        "scanner-card.png"
    ]
    assert processed == ["scanner-card.png"]
    status = watcher.state.read_status()
    assert status.inputs == [str(scanner)]

    with pytest.raises(ValueError, match="watch input_ref not available"):
        watcher.scan_once(dry_run=True, input_refs=["input_9"])


def test_watcher_scan_once_can_limit_processed_sources(tmp_path: Path) -> None:
    source = tmp_path / "scanner"
    write_synthetic_image(source / "scanner-card-1.png")
    write_synthetic_image(source / "scanner-card-2.png")
    config = make_config(tmp_path, source, settle_seconds=0.0)
    watcher = PollingWatcher(config)
    processed: list[str] = []
    fake_process(watcher, processed, tmp_path)

    assert len(watcher.scan_once(dry_run=True, limit=1)) == 1
    assert len(processed) == 1

    with pytest.raises(ValueError, match="watch scan limit must be greater than zero"):
        watcher.scan_once(dry_run=True, limit=0)


def test_watch_state_reset_allows_reprocessing(tmp_path: Path) -> None:
    source = tmp_path / "cards"
    write_synthetic_image(source / "card.png")
    config = make_config(tmp_path, source, settle_seconds=0.0)
    processed: list[str] = []

    watcher = PollingWatcher(config)
    fake_process(watcher, processed, tmp_path)
    watcher.scan_once(dry_run=True)
    watcher.reset()

    restarted = PollingWatcher(config)
    fake_process(restarted, processed, tmp_path)
    restarted.scan_once(dry_run=True)

    assert processed == ["card.png", "card.png"]


def test_watch_status_reports_missing_input_error(tmp_path: Path) -> None:
    config = make_config(tmp_path, tmp_path / "missing", settle_seconds=0.0)
    status = PollingWatcher(config).status()

    assert status.last_error
    assert "watch input not found" in status.last_error


def test_service_watch_dry_run_harness_uses_synthetic_source_only(tmp_path: Path) -> None:
    private_source = tmp_path / "private-sync"
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
        watch=WatchConfig(inputs=[str(private_source)], settle_seconds=0.0),
    )

    payload = BusinessCardService(config).watch_dry_run_harness()

    assert payload["schema"] == "business-card-watchdog.watch-dry-run-harness.v1"
    assert payload["state"] == "passed"
    assert payload["network_calls_made"] == 0
    assert payload["writes_attempted"] == 0
    assert payload["private_sources_used"] is False
    assert payload["first_scan_processed"] == payload["synthetic_images"]
    assert payload["second_scan_processed"] == []
    assert payload["final_status"]["seen_count"] == 1
    assert payload["final_status"]["inputs"] == [payload["source_dir"]]
    assert all(payload["assertions"].values())
    assert not private_source.exists()


def test_watch_status_scan_can_be_bounded_and_non_recursive(tmp_path: Path) -> None:
    source = tmp_path / "cards"
    nested = source / "nested"
    for index in range(3):
        write_synthetic_image(source / f"top-{index}.png")
    write_synthetic_image(nested / "nested-card.png")
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
        watch=WatchConfig(inputs=[str(source)], settle_seconds=0.0, status_scan_limit=2),
    )

    status = PollingWatcher(config).status()

    assert status.backlog_count == 2
    assert status.scan_truncated is True
    assert status.last_error is None


def test_watch_reset_cli_requires_yes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    watch_dir = data_dir / "watch"
    watch_dir.mkdir(parents=True)
    (watch_dir / "seen-files.jsonl").write_text('{"key": "x"}\n', encoding="utf-8")
    config_path.write_text(f'data_dir = "{data_dir}"\n[watch]\ninputs = []\n', encoding="utf-8")

    with pytest.raises(SystemExit, match="without --yes"):
        main(["--config", str(config_path), "watch-reset"])

    assert main(["--config", str(config_path), "watch-reset", "--yes"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "business-card-watchdog.watch-reset.v1"
    assert payload["reset"] is True
    assert payload["private_sources_used"] is False
    assert payload["commands"]["watch_status"] == "watch-status --json"
    assert "Do not run public-web search" in payload["explicit_stop_conditions"][2]
    assert not (watch_dir / "seen-files.jsonl").exists()


def test_watch_status_cli_outputs_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text("[watch]\ninputs = []\n", encoding="utf-8")

    assert main(["--config", str(config_path), "watch-status", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["inputs"] == []
    assert payload["seen_count"] == 0

    assert main(["--config", str(config_path), "watch-status"]) == 0
    text = capsys.readouterr().out
    assert "Watch status:" in text
    assert "Inputs: 0" in text
    assert "Seen: 0" in text
    assert "Last error: none" in text
    assert "{" not in text


def test_watch_dry_run_cli_outputs_fixture_harness(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config_path = tmp_path / "config.toml"
    cache_dir = tmp_path / "cache"
    config_path.write_text(f'cache_dir = "{cache_dir}"\n[watch]\ninputs = []\n', encoding="utf-8")

    assert main(["--config", str(config_path), "watch-dry-run", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "business-card-watchdog.watch-dry-run-harness.v1"
    assert payload["state"] == "passed"
    assert payload["private_sources_used"] is False
    assert payload["commands"]["watch_status"] == "watch-status --json"
    assert payload["commands"]["service_recovery"] == "service recovery --json"
    assert payload["safe_next_actions"][0]["command"] == "watch-dry-run --json"

    assert main(["--config", str(config_path), "watch-dry-run"]) == 0
    text = capsys.readouterr().out
    assert "Watch dry run: passed" in text
    assert "Private sources used: False" in text
    assert "Observed: writes=0 network=0" in text
    assert "Watch status: watch-status --json" in text
    assert "Safe next actions: 1" in text
    assert "Stop conditions: 2" in text
    assert "Do not process private SyncThing images from generic continuation." in text
    assert "{" not in text


def test_watch_backlog_preflight_cli_outputs_redacted_counts(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "Private Phone Camera"
    write_synthetic_image(source / "private-card-photo.png")
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    config_path.write_text(
        f'data_dir = "{data_dir}"\n[watch]\ninputs = ["{source}"]\nsettle_seconds = 0.0\n',
        encoding="utf-8",
    )

    assert main(["--config", str(config_path), "watch-backlog-preflight", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    serialized = json.dumps(payload, sort_keys=True)
    assert payload["schema"] == "business-card-watchdog.watch-backlog-preflight.v1"
    assert payload["counts"]["backlog"] == 1
    assert payload["inputs"][0]["configured_ref_display"] == "<redacted-path>"
    assert payload["commands"]["watch_once_dry_run"] == "watch --once --dry-run"
    assert Path(payload["preflight_path"]).exists()
    assert str(source) not in serialized
    assert "private-card-photo.png" not in serialized

    assert main(["--config", str(config_path), "watch-backlog-preflight", "--no-write"]) == 0
    text = capsys.readouterr().out
    assert "Watch backlog preflight: ready_for_operator_selected_dry_run" in text
    assert "Backlog: 1" in text
    assert "Observed: files=0 ocr=0 writes=0 network=0" in text
    assert "Watch once dry run: watch --once --dry-run" in text
    assert str(source) not in text
    assert "private-card-photo.png" not in text
    assert "{" not in text


def test_watch_practice_corpus_manifest_cli_previews_images_and_pdfs(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    phone = tmp_path / "Private Phone Camera"
    scanner = tmp_path / "Private Scanner"
    write_synthetic_image(phone / "20260620_111933.jpg")
    pdf = scanner / "2026_06_20_11_21_42.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-1.4\n% synthetic scanner fixture\n")
    (scanner / "old_archive.pdf").write_bytes(b"%PDF-1.4\n% old synthetic archive\n")
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    config_path.write_text(
        f'data_dir = "{data_dir}"\n'
        "[paths]\n"
        f'sync_phone = "{phone}"\n'
        f'scanner = "{scanner}"\n'
        "[watch]\n"
        'inputs = ["$fsr:sync_phone", "$fsr:scanner"]\n'
        "settle_seconds = 0.0\n",
        encoding="utf-8",
    )

    assert (
        main(
            [
                "--config",
                str(config_path),
                "watch-practice-corpus-manifest",
                "--no-write",
                "--include-glob",
                "20260620_11*.jpg",
                "--include-glob",
                "2026_06_20_11_21_42.pdf",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    serialized = json.dumps(payload, sort_keys=True)

    assert payload["schema"] == "business-card-watchdog.practice-corpus-manifest.v1"
    assert payload["entry_count"] == 2
    assert payload["include_globs"] == ["20260620_11*.jpg", "2026_06_20_11_21_42.pdf"]
    assert payload["recursive"] is False
    assert payload["filtered_glob_scan"] is True
    assert payload["counts"]["images"] == 1
    assert payload["counts"]["pdf_documents"] == 1
    assert payload["runtime_artifact_written"] is False
    assert payload["manifest_path"] is None
    assert payload["files_processed"] == 0
    assert payload["ocr_attempted"] == 0
    assert payload["pdfs_rasterized"] == 0
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    assert str(phone) not in serialized
    assert str(scanner) not in serialized
    assert "old_archive.pdf" not in serialized
    assert not (data_dir / "practice_corpus_manifest.json").exists()

    assert (
        main(
            [
                "--config",
                str(config_path),
                "watch-practice-corpus-manifest",
                "--no-write",
                "--include-glob",
                "20260620_11*.jpg",
                "--include-glob",
                "2026_06_20_11_21_42.pdf",
            ]
        )
        == 0
    )
    text = capsys.readouterr().out
    assert "Practice corpus manifest: ready_for_training_manifest_review" in text
    assert "Images: 1" in text
    assert "Include globs: 2" in text
    assert "PDF documents: 1" in text
    assert "Observed: files=0 ocr=0 pdfs=0 crops=0 writes=0 network=0" in text
    assert str(phone) not in text
    assert str(scanner) not in text
    assert "{" not in text


def test_watch_dry_run_selection_cli_validates_and_builds_command_copy(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "Private Phone Camera"
    write_synthetic_image(source / "private-card-photo.png")
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    config_path.write_text(
        f'data_dir = "{data_dir}"\n[watch]\ninputs = ["{source}"]\nsettle_seconds = 0.0\n',
        encoding="utf-8",
    )
    response = (
        "input_ref=input_0 operator=tester mode=dry_run "
        "safety_confirmation='private dry run approved for this configured source'"
    )

    assert main(["--config", str(config_path), "watch-dry-run-selection-handoff", "--json"]) == 0
    handoff = json.loads(capsys.readouterr().out)
    assert handoff["state"] == "awaiting_operator_response"
    assert handoff["entries"][0]["commands"]["validate_operator_response"].startswith(
        "watch-dry-run-validate-response"
    )
    assert str(source) not in json.dumps(handoff, sort_keys=True)

    assert main(["--config", str(config_path), "watch-dry-run-validate-response", "--response", response]) == 0
    validation_text = capsys.readouterr().out
    assert "Watch dry-run response validation: ready_for_command_copy" in validation_text
    assert "Safety confirmation present: True" in validation_text
    assert "private dry run approved" not in validation_text

    assert (
        main(
            [
                "--config",
                str(config_path),
                "watch-dry-run-command-copy-packet",
                "--response",
                response,
                "--acknowledgement",
                "I understand this will dry-run the configured private watch backlog",
                "--json",
            ]
        )
        == 0
    )
    packet = json.loads(capsys.readouterr().out)
    assert packet["state"] == "ready_for_operator_copy"
    assert packet["command_copy_text"] == "watch --once --dry-run"
    assert packet["files_processed"] == 0
    assert "private-card-photo.png" not in json.dumps(packet, sort_keys=True)


def test_watch_dry_run_readiness_cli_redacts_and_blocks_command_copy(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "Private Phone Camera"
    write_synthetic_image(source / "private-card-photo.png")
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    config_path.write_text(
        f'data_dir = "{data_dir}"\n[watch]\ninputs = ["{source}"]\nsettle_seconds = 0.0\n',
        encoding="utf-8",
    )

    assert main(["--config", str(config_path), "watch-dry-run-readiness", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    serialized = json.dumps(payload, sort_keys=True)

    assert payload["schema"] == "business-card-watchdog.watch-dry-run-readiness.v1"
    assert payload["state"] == "ready_for_operator_response"
    assert payload["command_copy_text"] is None
    assert payload["preflight_summary"]["counts"]["backlog"] == 1
    assert payload["runtime_artifact_written"] is True
    assert str(source) not in serialized
    assert "private-card-photo.png" not in serialized

    assert main(["--config", str(config_path), "watch-dry-run-readiness", "--no-write"]) == 0
    text = capsys.readouterr().out
    assert "Watch dry-run readiness: ready_for_operator_response" in text
    assert "Backlog: 1" in text
    assert "Observed: files=0 ocr=0 writes=0 network=0" in text
    assert "Watch once dry run: watch --once --dry-run" in text
    assert str(source) not in text
    assert "private-card-photo.png" not in text
    assert "{" not in text


def test_main_status_includes_watch_status(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text("[watch]\ninputs = []\n", encoding="utf-8")

    assert main(["--config", str(config_path), "status", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["skill_ready"] is True
    assert payload["watch"]["inputs"] == []


def test_state_store_reset_removes_runtime_files(tmp_path: Path) -> None:
    store = WatchStateStore(tmp_path / "watch")
    store.write_status(inputs=["/tmp/cards"], seen_count=1, backlog_count=2, unsettled_count=1)
    store.write_pending({})
    store.seen_path.write_text('{"key": "x"}\n', encoding="utf-8")

    store.reset()

    assert not store.status_path.exists()
    assert not store.pending_path.exists()
    assert not store.seen_path.exists()


def test_state_store_read_status_tolerates_empty_status_file(tmp_path: Path) -> None:
    store = WatchStateStore(tmp_path / "watch")
    store.status_path.write_text("", encoding="utf-8")

    status = store.read_status()

    assert status.inputs == []
    assert status.seen_count == 0
    assert status.backlog_count == 0
    assert status.unsettled_count == 0


def test_state_store_write_status_replaces_with_valid_json(tmp_path: Path) -> None:
    store = WatchStateStore(tmp_path / "watch")
    store.status_path.write_text("", encoding="utf-8")

    store.write_status(inputs=["/tmp/cards"], seen_count=1, backlog_count=2, unsettled_count=1)

    payload = json.loads(store.status_path.read_text(encoding="utf-8"))
    assert payload["inputs"] == ["/tmp/cards"]
    assert payload["seen_count"] == 1
    assert payload["backlog_count"] == 2
    assert payload["unsettled_count"] == 1
    assert not list(store.watch_dir.glob(".status.json.*.tmp"))
