from __future__ import annotations

import hashlib
import json
import shutil
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

from .config import AppConfig, resolve_input_path
from .document_intake import is_supported_document
from .models import utc_now
from .skill_adapter import is_supported_image


def build_known_card_intake(
    config: AppConfig,
    *,
    source_paths: list[str],
    label: str = "known_business_card",
    write: bool = True,
    include_globs: list[str] | None = None,
) -> dict[str, Any]:
    include_patterns = list(include_globs or [])
    sources, errors = _resolve_sources(config, source_paths=source_paths, include_globs=include_patterns)
    run_id = f"known-card-intake-{utc_now().replace(':', '-')}-{_sources_digest(sources)}"
    corpus_root = config.data_dir / "positive_control_corpus"
    blob_root = corpus_root / "blobs"
    manifest_path = corpus_root / "manifests" / f"{run_id}.json"
    index_path = corpus_root / "index.jsonl"
    entries = [
        _entry(
            path=path,
            corpus_root=corpus_root,
            blob_root=blob_root,
            label=label,
            intake_run_id=run_id,
            write=write,
            index_path=index_path,
        )
        for path in sources
    ]
    state = _state(errors=errors, entries=entries)
    payload: dict[str, Any] = {
        "schema": "business-card-watchdog.known-card-intake.v1",
        "generated_at": utc_now(),
        "state": state,
        "intake_run_id": run_id,
        "operator_declared_label": label,
        "source_count": len(sources),
        "entry_count": len(entries),
        "include_globs": include_patterns,
        "entries": entries,
        "errors": errors,
        "counts": {
            "images": sum(1 for entry in entries if entry["media_kind"] == "image"),
            "pdf_documents": sum(1 for entry in entries if entry["media_kind"] == "pdf_document"),
            "stored_new": sum(1 for entry in entries if entry["stored_new"]),
            "deduped_existing": sum(1 for entry in entries if entry["deduped_existing"]),
            "errors": len(errors),
        },
        "positive_control_corpus_root": str(corpus_root),
        "private_paths_redacted": True,
        "private_filenames_redacted": True,
        "files_processed": len(entries),
        "ocr_attempted": 0,
        "pdfs_rasterized": 0,
        "crops_created": 0,
        "writes_attempted": 0,
        "network_calls_made": 0,
        "live_sink_calls_made": False,
        "public_web_search_used": False,
        "paid_enrichment_used": False,
        "runtime_artifact_written": False,
        "manifest_path": None,
        "commands": {
            "known_card_intake": "known-card-intake --source <path> --json",
            "known_card_intake_preview": "known-card-intake --source <path> --no-write --json",
        },
        "explicit_stop_conditions": [
            "Only use this surface for operator-declared known business cards.",
            "This surface files source media as positive evidence only.",
            "This surface does not OCR, crop, rasterize PDFs, enrich, route, or write contacts.",
            "Do not commit the runtime corpus, manifests, or private card files to git.",
        ],
    }
    if write:
        _ensure_runtime_output_not_repo(corpus_root)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_payload = payload | {
            "runtime_artifact_written": True,
            "manifest_path": str(manifest_path),
        }
        manifest_path.write_text(json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        payload["runtime_artifact_written"] = True
        payload["manifest_path"] = str(manifest_path)
    return payload


def _resolve_sources(
    config: AppConfig,
    *,
    source_paths: list[str],
    include_globs: list[str],
) -> tuple[list[Path], list[dict[str, Any]]]:
    errors: list[dict[str, Any]] = []
    sources: list[Path] = []
    if not source_paths:
        errors.append({"source_ref": "<missing>", "error": "at least one --source is required"})
        return [], errors
    for index, raw in enumerate(source_paths, start=1):
        source_ref = f"source_{index:03d}"
        try:
            path = resolve_input_path(raw, config) if raw.startswith("$fsr:") else Path(raw).expanduser()
        except KeyError as exc:
            errors.append({"source_ref": source_ref, "error": str(exc)})
            continue
        if not path.exists():
            errors.append({"source_ref": source_ref, "error": "source not found"})
            continue
        selected = _source_files(path, include_globs=include_globs)
        if not selected:
            errors.append({"source_ref": source_ref, "error": "no supported image or PDF sources found"})
            continue
        sources.extend(selected)
    return sorted(set(sources), key=lambda item: str(item)), errors


def _source_files(path: Path, *, include_globs: list[str]) -> list[Path]:
    if path.is_file():
        return [path] if _is_supported_source(path) and _matches(path, path.parent, include_globs) else []
    return [
        candidate
        for candidate in sorted(path.rglob("*"))
        if candidate.is_file() and _is_supported_source(candidate) and _matches(candidate, path, include_globs)
    ]


def _entry(
    *,
    path: Path,
    corpus_root: Path,
    blob_root: Path,
    label: str,
    intake_run_id: str,
    write: bool,
    index_path: Path,
) -> dict[str, Any]:
    digest = _sha256(path)
    suffix = path.suffix.lower()
    media_kind = "pdf_document" if is_supported_document(path) else "image"
    blob_relpath = Path("blobs") / digest[:2] / f"{digest}{suffix}"
    blob_path = corpus_root / blob_relpath
    stored_new = write and not blob_path.exists()
    if write:
        blob_path.parent.mkdir(parents=True, exist_ok=True)
        if stored_new:
            shutil.copy2(path, blob_path)
        _append_index_once(
            index_path,
            {
                "schema": "business-card-watchdog.positive-control-corpus-entry.v1",
                "entry_id": f"positive-{digest[:16]}",
                "sha256": digest,
                "media_kind": media_kind,
                "suffix": suffix,
                "size_bytes": path.stat().st_size,
                "operator_declared_label": label,
                "first_seen_at": utc_now(),
                "intake_run_id": intake_run_id,
                "blob_relpath": str(blob_relpath),
                "source_path_redacted": True,
                "source_filename_redacted": True,
            },
        )
    return {
        "schema": "business-card-watchdog.known-card-intake-entry.v1",
        "entry_id": f"positive-{digest[:16]}",
        "sha256": digest,
        "media_kind": media_kind,
        "suffix": suffix,
        "size_bytes": path.stat().st_size,
        "operator_declared_label": label,
        "corpus_blob_relpath": str(blob_relpath),
        "stored_new": stored_new,
        "deduped_existing": write and not stored_new,
        "source_path_redacted": True,
        "source_filename_redacted": True,
    }


def _append_index_once(index_path: Path, row: dict[str, Any]) -> None:
    index_path.parent.mkdir(parents=True, exist_ok=True)
    digest = str(row["sha256"])
    if index_path.exists():
        for line in index_path.read_text(encoding="utf-8").splitlines():
            try:
                existing = json.loads(line)
            except json.JSONDecodeError:
                continue
            if existing.get("sha256") == digest:
                return
    with index_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def _ensure_runtime_output_not_repo(output_root: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    try:
        output_root.resolve().relative_to(repo_root)
    except ValueError:
        return
    raise ValueError(f"known-card corpus output root is inside the repo: {output_root}")


def _is_supported_source(path: Path) -> bool:
    return is_supported_image(path) or is_supported_document(path)


def _matches(path: Path, source_root: Path, include_globs: list[str]) -> bool:
    if not include_globs:
        return True
    try:
        relative = str(path.relative_to(source_root))
    except ValueError:
        relative = path.name
    return any(fnmatch(path.name, pattern) or fnmatch(relative, pattern) for pattern in include_globs)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sources_digest(sources: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sources:
        digest.update(_sha256(path).encode("utf-8"))
    return digest.hexdigest()[:12] if sources else "no-sources"


def _state(*, errors: list[dict[str, Any]], entries: list[dict[str, Any]]) -> str:
    if errors and not entries:
        return "blocked"
    if errors:
        return "completed_with_errors"
    return "positive_evidence_filed" if entries else "blocked"
