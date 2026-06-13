from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from business_card_watchdog.cli import main
from business_card_watchdog.config import AppConfig, WatchConfig
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


def test_watch_reset_cli_requires_yes(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text("[watch]\ninputs = []\n", encoding="utf-8")

    with pytest.raises(SystemExit, match="without --yes"):
        main(["--config", str(config_path), "watch-reset"])


def test_watch_status_cli_outputs_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text("[watch]\ninputs = []\n", encoding="utf-8")

    assert main(["--config", str(config_path), "watch-status", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["inputs"] == []
    assert payload["seen_count"] == 0


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
