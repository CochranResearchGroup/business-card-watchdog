from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .config import AppConfig, ensure_runtime_dirs, resolve_input_path
from .document_intake import is_supported_document
from .orchestrator import BatchOrchestrator, discover_processable_sources
from .skill_adapter import is_supported_image


_UNSET = object()


@dataclass(frozen=True)
class FileSnapshot:
    path: str
    size: int
    mtime_ns: int
    observed_at: float

    @classmethod
    def from_path(cls, path: Path, *, now: float | None = None) -> "FileSnapshot":
        stat = path.stat()
        return cls(
            path=str(path),
            size=stat.st_size,
            mtime_ns=stat.st_mtime_ns,
            observed_at=now if now is not None else time.time(),
        )

    def stable_identity(self) -> tuple[str, int, int]:
        return (self.path, self.size, self.mtime_ns)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "FileSnapshot":
        return cls(
            path=str(payload["path"]),
            size=int(payload["size"]),
            mtime_ns=int(payload["mtime_ns"]),
            observed_at=float(payload["observed_at"]),
        )


@dataclass(frozen=True)
class WatchStatus:
    inputs: list[str]
    seen_count: int
    backlog_count: int
    unsettled_count: int
    last_processed_path: str | None = None
    last_error: str | None = None
    scan_truncated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class WatchStateStore:
    def __init__(self, watch_dir: Path) -> None:
        self.watch_dir = watch_dir
        self.seen_path = watch_dir / "seen-files.jsonl"
        self.pending_path = watch_dir / "pending-files.json"
        self.status_path = watch_dir / "status.json"
        self.watch_dir.mkdir(parents=True, exist_ok=True)

    def seen_keys(self) -> set[str]:
        if not self.seen_path.exists():
            return set()
        keys: set[str] = set()
        for line in self.seen_path.read_text(encoding="utf-8").splitlines():
            if not line:
                continue
            keys.add(str(json.loads(line)["key"]))
        return keys

    def mark_seen(self, snapshot: FileSnapshot, *, run_dir: Path) -> None:
        record = {
            "key": snapshot.path,
            "snapshot": snapshot.to_dict(),
            "run_dir": str(run_dir),
            "processed_at": time.time(),
        }
        with self.seen_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
        self.write_status(last_processed_path=snapshot.path, last_error=None)

    def pending_snapshots(self) -> dict[str, FileSnapshot]:
        if not self.pending_path.exists():
            return {}
        payload = json.loads(self.pending_path.read_text(encoding="utf-8"))
        return {key: FileSnapshot.from_dict(value) for key, value in payload.items()}

    def write_pending(self, snapshots: dict[str, FileSnapshot]) -> None:
        self.pending_path.write_text(
            json.dumps(
                {key: snapshot.to_dict() for key, snapshot in snapshots.items()},
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    def write_status(
        self,
        *,
        inputs: list[str] | None = None,
        seen_count: int | None = None,
        backlog_count: int | None = None,
        unsettled_count: int | None = None,
        last_processed_path: str | None | object = _UNSET,
        last_error: str | None | object = _UNSET,
        scan_truncated: bool | None = None,
    ) -> None:
        current = self.read_status().to_dict() if self.status_path.exists() else {}
        payload = {
            "inputs": inputs if inputs is not None else current.get("inputs", []),
            "seen_count": seen_count if seen_count is not None else current.get("seen_count", 0),
            "backlog_count": backlog_count if backlog_count is not None else current.get("backlog_count", 0),
            "unsettled_count": unsettled_count
            if unsettled_count is not None
            else current.get("unsettled_count", 0),
            "last_processed_path": last_processed_path
            if last_processed_path is not _UNSET
            else current.get("last_processed_path"),
            "last_error": last_error if last_error is not _UNSET else current.get("last_error"),
            "scan_truncated": scan_truncated
            if scan_truncated is not None
            else current.get("scan_truncated", False),
        }
        self._write_json_atomic(self.status_path, payload)

    def read_status(self) -> WatchStatus:
        if not self.status_path.exists():
            return self._default_status()
        try:
            payload = json.loads(self.status_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return self._default_status()
        return WatchStatus(
            inputs=[str(item) for item in payload.get("inputs", [])],
            seen_count=int(payload.get("seen_count", 0)),
            backlog_count=int(payload.get("backlog_count", 0)),
            unsettled_count=int(payload.get("unsettled_count", 0)),
            last_processed_path=payload.get("last_processed_path"),
            last_error=payload.get("last_error"),
            scan_truncated=bool(payload.get("scan_truncated", False)),
        )

    def _default_status(self) -> WatchStatus:
        return WatchStatus(inputs=[], seen_count=len(self.seen_keys()), backlog_count=0, unsettled_count=0)

    def _write_json_atomic(self, path: Path, payload: dict[str, Any]) -> None:
        temp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temp_path, path)

    def reset(self) -> None:
        for path in (self.seen_path, self.pending_path, self.status_path):
            if path.exists():
                path.unlink()


@dataclass
class PollingWatcher:
    config: AppConfig
    interval_seconds: float = 10.0
    settle_seconds: float | None = None
    orchestrator: BatchOrchestrator = field(init=False)
    state: WatchStateStore = field(init=False)

    def __post_init__(self) -> None:
        ensure_runtime_dirs(self.config)
        self.orchestrator = BatchOrchestrator(self.config)
        self.state = WatchStateStore(self.config.watch_dir)
        if self.settle_seconds is None:
            self.settle_seconds = self.config.watch.settle_seconds

    def scan_once(self, *, dry_run: bool = True) -> list[Path]:
        processed: list[Path] = []
        seen = self.state.seen_keys()
        pending = self.state.pending_snapshots()
        next_pending: dict[str, FileSnapshot] = {}
        last_error: str | None = None
        backlog_count = 0
        unsettled_count = 0

        for raw_input in self.config.watch_inputs:
            try:
                source = resolve_input_path(raw_input, self.config)
                images = discover_processable_sources(source)
            except (FileNotFoundError, KeyError) as exc:
                last_error = str(exc)
                continue

            for image in images:
                snapshot = FileSnapshot.from_path(_stable_path(image))
                key = snapshot.path
                if key in seen:
                    continue

                previous = pending.get(key)
                if not self._is_settled(snapshot, previous):
                    next_pending[key] = snapshot
                    backlog_count += 1
                    unsettled_count += 1
                    continue

                run_dir = self.orchestrator.process_source(str(image), dry_run=dry_run, workers=1)
                self.state.mark_seen(snapshot, run_dir=run_dir)
                seen.add(key)
                processed.append(image)

        self.state.write_pending(next_pending)
        self.state.write_status(
            inputs=self.config.watch_inputs,
            seen_count=len(seen),
            backlog_count=backlog_count,
            unsettled_count=unsettled_count,
            last_error=last_error,
        )
        return processed

    def status(self) -> WatchStatus:
        seen = self.state.seen_keys()
        backlog_count = 0
        unsettled_count = 0
        last_error: str | None = None
        scan_truncated = False

        for raw_input in self.config.watch_inputs:
            try:
                source = resolve_input_path(raw_input, self.config)
            except KeyError as exc:
                last_error = str(exc)
                continue
            if not source.exists():
                last_error = f"watch input not found: {source}"
                continue
            images, truncated = _discover_status_images(
                source,
                seen=seen,
                limit=self.config.watch.status_scan_limit,
                recursive=self.config.watch.status_recursive,
            )
            scan_truncated = scan_truncated or truncated
            backlog_count += len(images)
            settle_seconds = float(self.settle_seconds or 0)
            if settle_seconds > 0:
                now = time.time()
                unsettled_count += sum(
                    1
                    for path in images
                    if now - (path.stat().st_mtime_ns / 1_000_000_000) < settle_seconds
                )

        status = WatchStatus(
            inputs=self.config.watch_inputs,
            seen_count=len(seen),
            backlog_count=backlog_count,
            unsettled_count=unsettled_count,
            last_processed_path=self.state.read_status().last_processed_path,
            last_error=last_error,
            scan_truncated=scan_truncated,
        )
        self.state.write_status(**status.to_dict())
        return status

    def reset(self) -> None:
        self.state.reset()

    def run(self, *, dry_run: bool = True, once: bool = False) -> None:
        while True:
            self.scan_once(dry_run=dry_run)
            if once:
                return
            time.sleep(self.interval_seconds)

    def _is_settled(self, current: FileSnapshot, previous: FileSnapshot | None) -> bool:
        settle_seconds = float(self.settle_seconds or 0)
        if settle_seconds <= 0:
            return True
        age_seconds = time.time() - (current.mtime_ns / 1_000_000_000)
        if age_seconds < settle_seconds:
            return False
        return previous is None or current.stable_identity() == previous.stable_identity()


def _stable_path(path: Path) -> Path:
    if path.exists():
        return path.resolve()
    return path


def _discover_status_images(
    source: Path,
    *,
    seen: set[str],
    limit: int,
    recursive: bool,
) -> tuple[list[Path], bool]:
    if source.is_file():
        path = _stable_path(source)
        return (
            [source]
            if (is_supported_image(source) or is_supported_document(source)) and str(path) not in seen
            else []
        ), False

    images: list[Path] = []
    truncated = False
    paths = source.rglob("*") if recursive else source.iterdir()
    for path in paths:
        if not path.is_file():
            continue
        if str(_stable_path(path)) in seen:
            continue
        if not is_supported_image(path) and not is_supported_document(path):
            continue
        if len(images) >= limit:
            truncated = True
            break
        images.append(path)
    return images, truncated
