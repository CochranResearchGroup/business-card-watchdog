from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from .config import AppConfig
from .models import utc_now
from .orchestrator import BatchOrchestrator
from .positive_corpus_evaluation import build_positive_corpus_evaluation_manifest
from .positive_corpus_recognition import build_positive_corpus_recognition_replay


WORKBENCH_SCHEMA = "business-card-watchdog.positive-corpus-crop-ocr-workbench.v1"


def build_positive_corpus_workbench_evaluation(
    config: AppConfig,
    *,
    write: bool = True,
    workers: int = 1,
    adapter: Any | None = None,
) -> dict[str, Any]:
    corpus_root = config.data_dir / "positive_control_corpus"
    rows, errors = _read_corpus_index(corpus_root / "index.jsonl")
    evaluation = build_positive_corpus_evaluation_manifest(config, write=False)
    recognition = build_positive_corpus_recognition_replay(config, write=False)
    workbench_id = f"positive-corpus-workbench-{utc_now().replace(':', '-')}-{_rows_digest(rows)}"
    workbench_dir = corpus_root / "workbench_evaluations" / workbench_id
    source_bundle_dir = workbench_dir / "source_bundle"
    report_path = workbench_dir / "workbench_evaluation.json"

    payload: dict[str, Any] = {
        "schema": WORKBENCH_SCHEMA,
        "generated_at": utc_now(),
        "state": "blocked" if errors or not rows else "preview",
        "workbench_id": workbench_id,
        "evaluation_manifest_state": evaluation.get("state"),
        "recognition_replay_state": recognition.get("state"),
        "source_count": len(rows),
        "source_entries": [_redacted_source_entry(row) for row in rows],
        "run_id": None,
        "run_dir": None,
        "report_path": None,
        "processed_job_count": 0,
        "processed_jobs": [],
        "counts": _empty_counts(rows=rows, errors=errors),
        "errors": errors,
        "private_paths_redacted": True,
        "private_filenames_redacted": True,
        "operator_declared_known_positive_only": True,
        "known_positive_classifier_bypass_used": False,
        "broad_autodetection_promoted": False,
        "contacts_review_required": True,
        "dry_run": True,
        "ocr_attempted": 0,
        "pdfs_rasterized": 0,
        "crops_created": 0,
        "writes_attempted": 0,
        "network_calls_made": 0,
        "live_sink_calls_made": False,
        "public_web_search_used": False,
        "paid_enrichment_used": False,
        "runtime_artifact_written": False,
        "commands": {
            "positive_corpus_workbench": "positive-corpus-workbench-evaluation --json",
            "positive_corpus_workbench_preview": "positive-corpus-workbench-evaluation --no-write --json",
        },
        "explicit_stop_conditions": [
            "This workbench processes operator-declared positive controls only.",
            "Known-positive classifier bypass does not reopen broad unknown-document autodetection.",
            "All contacts remain review-required and dry-run.",
            "Do not route, enrich, write contacts, read back sinks, search the public web, or call paid providers.",
            "Do not commit runtime workbench artifacts, private source media, OCR text, crops, or contact data.",
        ],
    }
    if payload["state"] == "blocked":
        return payload
    if not write:
        payload["state"] = "ready_for_runtime_workbench"
        payload["counts"]["sources_ready"] = len(rows)
        return payload

    _ensure_runtime_output_not_repo(corpus_root)
    source_bundle_dir.mkdir(parents=True, exist_ok=True)
    copy_errors = _copy_redacted_sources(rows=rows, corpus_root=corpus_root, source_bundle_dir=source_bundle_dir)
    if copy_errors:
        payload["state"] = "blocked"
        payload["errors"] = [*errors, *copy_errors]
        payload["counts"]["errors"] = len(payload["errors"])
        return payload

    orchestrator = BatchOrchestrator(config)
    if adapter is not None:
        orchestrator.adapter = adapter
    run_dir = orchestrator.process_source(
        str(source_bundle_dir),
        dry_run=True,
        workers=workers,
        known_positive=True,
    )
    processed_jobs = _summarize_run_jobs(run_dir)
    counts = _counts(rows=rows, processed_jobs=processed_jobs, run_dir=run_dir, errors=errors)
    state = "workbench_review_required" if processed_jobs else "blocked"
    written_payload = payload | {
        "state": state,
        "run_id": run_dir.name,
        "run_dir": str(run_dir),
        "report_path": str(report_path),
        "processed_job_count": len(processed_jobs),
        "processed_jobs": processed_jobs,
        "counts": counts,
        "known_positive_classifier_bypass_used": counts["known_positive_classifier_bypass_admissions"] > 0,
        "ocr_attempted": counts["ocr_artifacts"],
        "pdfs_rasterized": counts["pdf_pages_materialized"],
        "crops_created": counts["candidate_crops_created"] + counts["adapter_crop_manifests"],
        "runtime_artifact_written": True,
    }
    workbench_dir.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(written_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return written_payload


def _read_corpus_index(index_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not index_path.exists():
        return [], [{"error": "positive control corpus index not found"}]
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for line_number, line in enumerate(index_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            errors.append({"line_number": line_number, "error": "invalid corpus index JSON"})
            continue
        if not isinstance(row, dict):
            errors.append({"line_number": line_number, "error": "corpus index row is not an object"})
            continue
        rows.append(row)
    return rows, errors


def _copy_redacted_sources(
    *,
    rows: list[dict[str, Any]],
    corpus_root: Path,
    source_bundle_dir: Path,
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    for row in rows:
        entry_id = str(row.get("entry_id") or f"positive-{str(row.get('sha256') or '')[:16]}")
        suffix = str(row.get("suffix") or "")
        source_path = corpus_root / str(row.get("blob_relpath") or "")
        target_path = source_bundle_dir / f"{_safe_name(entry_id)}{suffix}"
        if not source_path.exists():
            errors.append({"entry_id": entry_id, "error": "corpus blob not found"})
            continue
        shutil.copy2(source_path, target_path)
    return errors


def _summarize_run_jobs(run_dir: Path) -> list[dict[str, Any]]:
    jobs = _latest_jobs(run_dir / "jobs.jsonl")
    artifacts_by_job = _artifacts_by_job(run_dir / "artifacts.jsonl")
    summaries: list[dict[str, Any]] = []
    for job_id, job in sorted(jobs.items()):
        artifact_dir = Path(str(job.get("artifact_dir") or run_dir / "artifacts" / job_id))
        artifacts = artifacts_by_job.get(job_id, {})
        preclassification = _read_json(artifact_dir / "preclassification.json")
        classifier_gate = _read_json(artifact_dir / "scanner_page_classifier_gate.json")
        source_page = _read_json(artifact_dir / "source_page.json")
        candidate_crops = _read_json(artifact_dir / "candidate_crops.json")
        crop_quality = _read_json(artifact_dir / "crop_quality.json")
        crop_acceptance = _read_json(artifact_dir / "crop_acceptance.json")
        extraction_quality = _read_json(artifact_dir / "extraction_quality.json")
        ocr_quality_gate = _read_json(artifact_dir / "ocr_quality_gate.json")
        child_promotions = _read_json(artifact_dir / "child_contact_promotions.json")
        candidate_work_items = _read_json(artifact_dir / "candidate_work_items.json")
        review_packet_present = (artifact_dir / "review_packet.json").exists()
        crop_count = int(candidate_crops.get("crop_count") or 0)
        work_item_count = int(candidate_work_items.get("work_item_count") or 0)
        child_candidate_count = int(child_promotions.get("promotion_count") or 0)
        app_request_count = int(crop_acceptance.get("app_intelligence_request_count") or 0) + int(
            ocr_quality_gate.get("app_intelligence_request_count") or 0
        )
        ocr_artifact = _first_artifact(artifacts, "ocr_text")
        summaries.append(
            {
                "job_id": job_id,
                "state": job.get("state"),
                "media_kind": "pdf_page" if source_page else "image",
                "page_number": source_page.get("page_number"),
                "rasterization_mode": source_page.get("rasterization_mode"),
                "classifier_training_state": preclassification.get("classifier_training_state")
                or classifier_gate.get("classifier_training_state")
                or "",
                "classifier_admitted_to_crop_ocr": classifier_gate.get("admitted_to_crop_ocr"),
                "known_positive_bypass_admission": _known_positive_bypass(classifier_gate),
                "candidate_crop_count": crop_count,
                "candidate_work_item_count": work_item_count,
                "child_candidate_count": child_candidate_count,
                "bounded_review_evidence": bool(review_packet_present or app_request_count or crop_quality),
                "review_packet_present": review_packet_present,
                "ocr_text_present": "ocr_text" in artifacts,
                "ocr_text_source": str(dict(ocr_artifact.get("metadata") or {}).get("source") or "adapter")
                if ocr_artifact
                else "",
                "contact_draft_present": (artifact_dir / "contact_candidate.json").exists(),
                "adapter_crop_manifest_present": "crop_manifest" in artifacts,
                "crop_quality_state": crop_quality.get("state") or "missing",
                "crop_acceptance_state": crop_acceptance.get("state") or "missing",
                "extraction_quality_status": extraction_quality.get("status") or "missing",
                "ocr_quality_gate_state": ocr_quality_gate.get("state") or "missing",
                "app_intelligence_request_count": app_request_count,
                "routing_allowed": False,
                "enrichment_allowed": False,
                "sink_write_allowed": False,
                "source_path_redacted": True,
                "source_filename_redacted": True,
            }
        )
    return summaries


def _latest_jobs(path: Path) -> dict[str, dict[str, Any]]:
    jobs: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return jobs
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if isinstance(row, dict):
            jobs[str(row["job_id"])] = row
    return jobs


def _artifacts_by_job(path: Path) -> dict[str, dict[str, list[dict[str, Any]]]]:
    artifacts: dict[str, dict[str, list[dict[str, Any]]]] = {}
    if not path.exists():
        return artifacts
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            continue
        artifacts.setdefault(str(row.get("job_id")), {}).setdefault(str(row.get("kind")), []).append(row)
    return artifacts


def _first_artifact(artifacts: dict[str, list[dict[str, Any]]], kind: str) -> dict[str, Any]:
    rows = artifacts.get(kind) or []
    row = rows[0] if rows else {}
    return row if isinstance(row, dict) else {}


def _counts(
    *,
    rows: list[dict[str, Any]],
    processed_jobs: list[dict[str, Any]],
    run_dir: Path,
    errors: list[dict[str, Any]],
) -> dict[str, int]:
    artifact_counts = _artifact_counts(run_dir / "artifacts.jsonl")
    pdf_pages = sum(int(row.get("metadata", {}).get("page_count") or 0) for row in artifact_counts["document_pages"])
    candidate_crops_created = sum(int(job.get("candidate_crop_count") or 0) for job in processed_jobs)
    return {
        "sources": len(rows),
        "sources_ready": len(rows),
        "images": sum(1 for row in rows if row.get("media_kind") == "image"),
        "pdf_documents": sum(1 for row in rows if row.get("media_kind") == "pdf_document"),
        "processed_jobs": len(processed_jobs),
        "pdf_pages_materialized": pdf_pages,
        "image_jobs": sum(1 for job in processed_jobs if job.get("media_kind") == "image"),
        "pdf_page_jobs": sum(1 for job in processed_jobs if job.get("media_kind") == "pdf_page"),
        "ocr_artifacts": sum(1 for job in processed_jobs if job.get("ocr_text_present") is True),
        "contact_drafts": sum(1 for job in processed_jobs if job.get("contact_draft_present") is True),
        "review_packets": sum(1 for job in processed_jobs if job.get("review_packet_present") is True),
        "review_required_jobs": sum(1 for job in processed_jobs if job.get("state") == "needs_review"),
        "candidate_crops_created": candidate_crops_created,
        "adapter_crop_manifests": sum(1 for job in processed_jobs if job.get("adapter_crop_manifest_present") is True),
        "child_candidate_records": sum(int(job.get("child_candidate_count") or 0) for job in processed_jobs),
        "multi_card_candidate_jobs": sum(1 for job in processed_jobs if int(job.get("candidate_work_item_count") or 0) > 1),
        "bounded_review_evidence_jobs": sum(1 for job in processed_jobs if job.get("bounded_review_evidence") is True),
        "app_intelligence_request_count": sum(int(job.get("app_intelligence_request_count") or 0) for job in processed_jobs),
        "known_positive_classifier_bypass_admissions": sum(
            1 for job in processed_jobs if job.get("known_positive_bypass_admission") is True
        ),
        "errors": len(errors),
    }


def _artifact_counts(path: Path) -> dict[str, list[dict[str, Any]]]:
    rows: dict[str, list[dict[str, Any]]] = {"document_pages": []}
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if isinstance(row, dict):
            rows.setdefault(str(row.get("kind")), []).append(row)
    return rows


def _empty_counts(*, rows: list[dict[str, Any]], errors: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "sources": len(rows),
        "sources_ready": 0,
        "images": sum(1 for row in rows if row.get("media_kind") == "image"),
        "pdf_documents": sum(1 for row in rows if row.get("media_kind") == "pdf_document"),
        "processed_jobs": 0,
        "pdf_pages_materialized": 0,
        "image_jobs": 0,
        "pdf_page_jobs": 0,
        "ocr_artifacts": 0,
        "contact_drafts": 0,
        "review_packets": 0,
        "review_required_jobs": 0,
        "candidate_crops_created": 0,
        "adapter_crop_manifests": 0,
        "child_candidate_records": 0,
        "multi_card_candidate_jobs": 0,
        "bounded_review_evidence_jobs": 0,
        "app_intelligence_request_count": 0,
        "known_positive_classifier_bypass_admissions": 0,
        "errors": len(errors),
    }


def _redacted_source_entry(row: dict[str, Any]) -> dict[str, Any]:
    sha256 = str(row.get("sha256") or "")
    return {
        "entry_id": str(row.get("entry_id") or f"positive-{sha256[:16]}"),
        "sha256": sha256,
        "sha256_prefix": sha256[:12],
        "media_kind": str(row.get("media_kind") or "unknown"),
        "suffix": str(row.get("suffix") or ""),
        "size_bytes": int(row.get("size_bytes") or 0),
        "operator_declared_label": str(row.get("operator_declared_label") or ""),
        "source_path_redacted": True,
        "source_filename_redacted": True,
    }


def _known_positive_bypass(classifier_gate: dict[str, Any]) -> bool:
    if classifier_gate.get("admitted_to_crop_ocr") is not True:
        return False
    return str(classifier_gate.get("classifier_training_state") or "") != "business_card_high_confidence"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _ensure_runtime_output_not_repo(output_root: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    try:
        output_root.resolve().relative_to(repo_root)
    except ValueError:
        return
    raise ValueError(f"positive corpus workbench output root is inside the repo: {output_root}")


def _rows_digest(rows: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        digest.update(str(row.get("sha256") or "").encode("utf-8"))
    return digest.hexdigest()[:12] if rows else "no-corpus"


def _safe_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in "-_" else "-" for char in value).strip("-") or "source"
