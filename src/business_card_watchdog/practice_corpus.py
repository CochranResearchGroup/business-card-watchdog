from __future__ import annotations

import hashlib
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

from .config import AppConfig, resolve_input_path
from .document_intake import is_supported_document
from .models import utc_now
from .skill_adapter import is_supported_image


PDF_SUFFIXES = {".pdf"}


def build_practice_corpus_manifest(
    config: AppConfig,
    *,
    write: bool = True,
    include_globs: list[str] | None = None,
) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    inputs: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    scan_truncated = False
    include_patterns = list(include_globs or [])
    recursive = config.watch.status_recursive
    filtered_glob_scan = bool(include_patterns)
    for index, raw_input in enumerate(config.watch_inputs):
        input_ref = f"input_{index}"
        source_alias = _source_alias(raw_input)
        input_summary = {
            "input_ref": input_ref,
            "configured_ref_kind": "fsr_alias" if source_alias else "path",
            "configured_ref_display": raw_input if source_alias else "<redacted-path>",
            "source_alias": source_alias,
            "source_path_redacted": True,
        }
        inputs.append(input_summary)
        try:
            source = resolve_input_path(raw_input, config)
        except KeyError as exc:
            errors.append({"input_ref": input_ref, "error": str(exc)})
            continue
        if not source.exists():
            errors.append({"input_ref": input_ref, "error": "watch input not found"})
            continue
        discovered, truncated = _discover_manifest_files(
            source,
            recursive=recursive,
            limit=config.watch.status_scan_limit,
            include_globs=include_patterns,
        )
        scan_truncated = scan_truncated or truncated
        for path in discovered:
            entries.append(
                _manifest_entry(
                    path=path,
                    source=source,
                    input_ref=input_ref,
                    source_alias=source_alias,
                    settle_seconds=config.watch.settle_seconds,
                )
            )

    entries.sort(key=lambda entry: (str(entry["input_ref"]), str(entry["relative_path"])))
    image_entries = [entry for entry in entries if entry["media_kind"] == "image"]
    pdf_entries = [entry for entry in entries if entry["media_kind"] == "pdf_document"]
    state = _manifest_state(errors=errors, entries=entries)
    manifest_path = config.data_dir / "practice_corpus_manifest.json"
    payload: dict[str, Any] = {
        "schema": "business-card-watchdog.practice-corpus-manifest.v1",
        "generated_at": utc_now(),
        "state": state,
        "input_count": len(inputs),
        "inputs": inputs,
        "entry_count": len(entries),
        "include_globs": include_patterns,
        "recursive": recursive,
        "filtered_glob_scan": filtered_glob_scan,
        "counts": {
            "images": len(image_entries),
            "pdf_documents": len(pdf_entries),
            "current_watcher_processable": sum(1 for entry in entries if entry["current_watcher_processable"]),
            "unsettled": sum(1 for entry in entries if entry["settle_state"] != "settled"),
            "errors": len(errors),
        },
        "scan_truncated": scan_truncated,
        "entries": entries,
        "errors": errors,
        "private_paths_redacted": True,
        "private_filenames_redacted": False,
        "private_sources_used": False,
        "files_processed": 0,
        "ocr_attempted": 0,
        "pdfs_rasterized": 0,
        "crops_created": 0,
        "writes_attempted": 0,
        "network_calls_made": 0,
        "runtime_artifact_written": False,
        "manifest_path": None,
        "commands": {
            "practice_corpus_manifest": "watch-practice-corpus-manifest --json",
            "practice_corpus_manifest_preview": "watch-practice-corpus-manifest --no-write --json",
            "watch_backlog_preflight": "watch-backlog-preflight --no-write --json",
            "watch_status": "watch-status --json",
        },
        "explicit_stop_conditions": [
            "This manifest inventories configured watched files only.",
            "Do not OCR, crop, rasterize PDFs, enrich, route, or write contacts from this manifest.",
            "PDF entries are document sources for scanner intake, not direct image inputs.",
            "Do not commit the runtime manifest or private card files to git.",
        ],
    }
    if write:
        config.data_dir.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(_json_dumps(payload | {"runtime_artifact_written": True, "manifest_path": str(manifest_path)}), encoding="utf-8")
        payload["runtime_artifact_written"] = True
        payload["manifest_path"] = str(manifest_path)
    return payload


def _discover_manifest_files(
    source: Path,
    *,
    recursive: bool,
    limit: int,
    include_globs: list[str],
) -> tuple[list[Path], bool]:
    if source.is_file():
        return ([source] if _is_manifest_file(source) and _matches_include_globs(source, source, include_globs) else []), False
    if include_globs:
        return _discover_manifest_files_by_glob(source, include_globs=include_globs, limit=limit)
    paths = source.rglob("*") if recursive else source.iterdir()
    files: list[Path] = []
    truncated = False
    for path in paths:
        if not path.is_file():
            continue
        if not _is_manifest_file(path):
            continue
        if not _matches_include_globs(path, source, include_globs):
            continue
        if len(files) >= limit:
            truncated = True
            break
        files.append(path)
    return files, truncated


def _discover_manifest_files_by_glob(source: Path, *, include_globs: list[str], limit: int) -> tuple[list[Path], bool]:
    files: list[Path] = []
    seen: set[Path] = set()
    truncated = False
    for pattern in include_globs:
        for path in source.glob(pattern):
            if path in seen:
                continue
            if not path.is_file() or not _is_manifest_file(path):
                continue
            if len(files) >= limit:
                truncated = True
                break
            files.append(path)
            seen.add(path)
        if truncated:
            break
    return files, truncated


def _manifest_entry(
    *,
    path: Path,
    source: Path,
    input_ref: str,
    source_alias: str | None,
    settle_seconds: float,
) -> dict[str, Any]:
    stat = path.stat()
    suffix = path.suffix.lower()
    media_kind = "pdf_document" if suffix in PDF_SUFFIXES else "image"
    processable = is_supported_image(path) or is_supported_document(path)
    return {
        "schema": "business-card-watchdog.practice-corpus-entry.v1",
        "entry_id": _entry_id(path),
        "input_ref": input_ref,
        "source_alias": source_alias,
        "relative_path": _relative_path(path, source),
        "suffix": suffix,
        "media_kind": media_kind,
        "role_hint": _role_hint(media_kind=media_kind, source_alias=source_alias),
        "current_watcher_processable": processable,
        "current_processing_note": _processing_note(media_kind=media_kind, processable=processable),
        "size_bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "mtime_epoch_seconds": stat.st_mtime_ns / 1_000_000_000,
        "sha256": _sha256(path),
        "settle_state": _settle_state(stat.st_mtime_ns, settle_seconds=settle_seconds),
        "private_path_redacted": True,
    }


def _source_alias(raw_input: str) -> str | None:
    if raw_input.startswith("$fsr:"):
        return raw_input.removeprefix("$fsr:")
    return None


def _is_manifest_file(path: Path) -> bool:
    return is_supported_image(path) or path.suffix.lower() in PDF_SUFFIXES


def _matches_include_globs(path: Path, source: Path, include_globs: list[str]) -> bool:
    if not include_globs:
        return True
    relative = _relative_path(path, source)
    return any(fnmatch(path.name, pattern) or fnmatch(relative, pattern) for pattern in include_globs)


def _entry_id(path: Path) -> str:
    digest = hashlib.sha256(str(path).encode("utf-8")).hexdigest()
    return f"entry-{digest[:16]}"


def _relative_path(path: Path, source: Path) -> str:
    if source.is_file():
        return path.name
    try:
        return str(path.relative_to(source))
    except ValueError:
        return path.name


def _role_hint(*, media_kind: str, source_alias: str | None) -> str:
    if media_kind == "pdf_document":
        return "scanner_pdf_document"
    if source_alias == "scanner":
        return "scanner_image"
    if source_alias == "sync_phone":
        return "phone_camera_image"
    return "watched_image"


def _processing_note(*, media_kind: str, processable: bool) -> str:
    if media_kind == "pdf_document" and processable:
        return "document_intake_supported"
    if processable:
        return "image_input_supported"
    return "unsupported_manifest_entry"


def _settle_state(mtime_ns: int, *, settle_seconds: float) -> str:
    if settle_seconds <= 0:
        return "settled"
    import time

    age_seconds = time.time() - (mtime_ns / 1_000_000_000)
    return "settled" if age_seconds >= settle_seconds else "unsettled"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_state(*, errors: list[dict[str, Any]], entries: list[dict[str, Any]]) -> str:
    if errors:
        return "blocked"
    if not entries:
        return "empty"
    if any(entry["settle_state"] != "settled" for entry in entries):
        return "waiting_for_settle"
    return "ready_for_training_manifest_review"


def _json_dumps(payload: dict[str, Any]) -> str:
    import json

    return json.dumps(payload, indent=2, sort_keys=True) + "\n"
