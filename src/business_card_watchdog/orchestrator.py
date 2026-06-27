from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from .card_sides import build_pair_proposals, build_side_pair_graph, classify_card_side
from .config import AppConfig, ensure_runtime_dirs, resolve_input_path
from .contact import build_contact_candidate, contact_candidate_to_spec
from .contact_store import ContactStore
from .crop_quality import build_crop_acceptance, build_crop_quality, build_recrop_proposals
from .dedupe import assess_duplicate, remember_identity
from .document_intake import (
    build_card_side_candidate,
    build_source_page_artifact,
    is_supported_document,
    materialize_document_pages,
)
from .fanout import (
    build_candidate_work_item_manifest,
    build_child_verification_request_manifest,
    build_synthetic_child_verification_result_manifest,
    materialize_candidate_crops,
    promote_child_verification_results,
)
from .ledger import RunLedger
from .models import CardJob, utc_now
from .orientation_evidence import build_orientation_evidence
from .preclassifier import assess_business_card_candidate, build_card_candidate_box_manifest
from .quality import assess_extraction_quality, write_extraction_quality
from .qr_evidence import build_qr_evidence
from .review import assess_contact_spec, write_review_packet
from .routing import decide_sinks, load_contact_spec, selected_google_contacts_profile, selected_odollo_tenant
from .sinks import build_sink_payloads, write_sink_payloads
from .skill_adapter import BusinessCardSkillAdapter, is_supported_image


def discover_images(source: Path) -> list[Path]:
    if source.is_file():
        return [source] if is_supported_image(source) else []
    if not source.exists():
        raise FileNotFoundError(source)
    return sorted(path for path in source.rglob("*") if is_supported_image(path))


def discover_processable_sources(source: Path) -> list[Path]:
    if source.is_file():
        return [source] if is_supported_image(source) or is_supported_document(source) else []
    if not source.exists():
        raise FileNotFoundError(source)
    return sorted(
        path for path in source.rglob("*") if is_supported_image(path) or is_supported_document(path)
    )


def positive_control_page_lineage(source: Path) -> dict[str, dict[str, Any]]:
    if not source.is_dir():
        return {}
    manifest_path = source / "positive_control_scenario.json"
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if payload.get("schema") != "business-card-watchdog.positive-control-scenario.v1":
        return {}
    lineage: dict[str, dict[str, Any]] = {}
    for index, page in enumerate(list(payload.get("pages") or []), start=1):
        if not isinstance(page, dict):
            continue
        page_image = Path(str(page.get("generated_path") or ""))
        if not page_image.is_file():
            continue
        page_number = _positive_control_page_number(page, fallback=index)
        lineage[str(page_image)] = {
            "schema": "business-card-watchdog.document-page.v1",
            "source_document_path": str(manifest_path),
            "page_number": page_number,
            "page_image_path": str(page_image),
            "media_kind": "page_image",
            "rasterization_mode": "positive_control_scenario",
            "sha256": _sha256_file(page_image),
            "positive_control": {
                "scenario_id": payload.get("scenario_id"),
                "page_id": page.get("page_id"),
                "expected_role": page.get("expected_role"),
                "card_ref": page.get("card_ref"),
                "transform": page.get("transform"),
            },
        }
    return lineage


def _positive_control_page_number(page: dict[str, Any], *, fallback: int) -> int:
    page_id = str(page.get("page_id") or "")
    digits = "".join(char for char in page_id if char.isdigit())
    return int(digits) if digits else fallback


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class BatchOrchestrator:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.adapter = BusinessCardSkillAdapter(config)

    def process_source(
        self,
        raw_source: str,
        *,
        dry_run: bool = True,
        workers: int = 2,
        known_positive: bool = False,
    ) -> Path:
        ensure_runtime_dirs(self.config)
        source = resolve_input_path(raw_source, self.config)
        run_dir = self.config.runs_dir / utc_now().replace(":", "-")
        ledger = RunLedger(run_dir)
        ledger.initialize(source=str(source), dry_run=dry_run)
        ledger.transition_run("discovering")

        processable_sources = discover_processable_sources(source)
        page_lineage_by_path: dict[str, dict[str, Any]] = {}
        page_lineage_by_path.update(positive_control_page_lineage(source))
        job_sources: list[Path] = []
        for path in processable_sources:
            if is_supported_document(path):
                document_manifest = materialize_document_pages(path, run_dir / "document_intake")
                manifest_path = Path(str(document_manifest["manifest_path"]))
                ledger.record_artifact(
                    job_id="__run__",
                    kind="document_pages",
                    path=manifest_path,
                    metadata={
                        "source_document_path": str(path),
                        "page_count": document_manifest["page_count"],
                    },
                )
                ledger.record_event(
                    "document_pages_materialized",
                    {
                        "source_document_path": str(path),
                        "page_count": document_manifest["page_count"],
                        "manifest_path": str(manifest_path),
                    },
                )
                for page in document_manifest["pages"]:
                    page_image = Path(str(page["page_image_path"]))
                    page_lineage_by_path[str(page_image)] = page
                    job_sources.append(page_image)
            else:
                job_sources.append(path)

        jobs = [CardJob.from_path(path) for path in job_sources]
        ledger.set_job_count(len(jobs))
        for job in jobs:
            ledger.record_job(job)

        if not jobs:
            ledger.record_event("no_supported_images", {"source": str(source)})
            ledger.transition_run("completed")
            return run_dir

        ledger.transition_run("processing")
        max_workers = max(1, workers)
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {
                pool.submit(
                    self._process_one,
                    job,
                    ledger,
                    dry_run,
                    page_lineage_by_path.get(job.image_path),
                    known_positive,
                ): job
                for job in jobs
            }
            for future in as_completed(futures):
                future.result()

        self._write_card_side_pair_proposals(ledger)
        self._write_side_pair_graph(ledger)
        self._project_contact_store(ledger)
        ledger.record_event("run_completed", {"job_count": len(jobs)})
        ledger.transition_run("completed")
        return run_dir

    def _write_card_side_pair_proposals(self, ledger: RunLedger) -> None:
        candidates: list[dict[str, Any]] = []
        for side_path in sorted((ledger.run_dir / "artifacts").glob("*/card_side_candidate.json")):
            try:
                payload = json.loads(side_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                candidates.append(payload)
        if not candidates:
            return
        proposals = build_pair_proposals(run_id=ledger.run_dir.name, side_candidates=candidates)
        proposal_path = ledger.run_dir / "card_side_pair_proposals.json"
        proposal_path.write_text(json.dumps(proposals, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        ledger.record_artifact(
            job_id="__run__",
            kind="card_side_pair_proposals",
            path=proposal_path,
            metadata={"proposal_count": proposals["proposal_count"]},
        )
        ledger.record_event("card_side_pair_proposals_recorded", proposals)

    def _write_side_pair_graph(self, ledger: RunLedger) -> None:
        candidates: list[dict[str, Any]] = []
        evidence_by_job: dict[str, dict[str, Any]] = {}
        for artifact_dir in sorted((ledger.run_dir / "artifacts").glob("*")):
            if not artifact_dir.is_dir():
                continue
            job_id = artifact_dir.name
            side_path = artifact_dir / "card_side_candidate.json"
            try:
                side_payload = json.loads(side_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(side_payload, dict):
                candidates.append(side_payload)
            evidence_by_job[job_id] = {
                "qr_evidence": _read_artifact_json(artifact_dir / "qr_evidence.json"),
                "orientation_evidence": _read_artifact_json(artifact_dir / "orientation_evidence.json"),
                "crop_quality": _read_artifact_json(artifact_dir / "crop_quality.json"),
                "recrop_proposals": _read_artifact_json(artifact_dir / "recrop_proposals.json"),
            }
        if not candidates:
            return
        graph = build_side_pair_graph(
            run_id=ledger.run_dir.name,
            side_candidates=candidates,
            evidence_by_job=evidence_by_job,
        )
        graph_path = ledger.run_dir / "side_pair_graph.json"
        graph_path.write_text(json.dumps(graph, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        ledger.record_artifact(
            job_id="__run__",
            kind="side_pair_graph",
            path=graph_path,
            metadata={
                "node_count": graph["node_count"],
                "edge_count": graph["edge_count"],
                "pair_proposal_count": graph["pair_proposal_count"],
            },
        )
        ledger.record_event("side_pair_graph_recorded", graph)

    def _project_contact_store(self, ledger: RunLedger) -> None:
        store = ContactStore.from_config(self.config)
        projection_path = ledger.run_dir / "contact_store_projection.json"
        try:
            projection = store.project_run(run_id=ledger.run_dir.name, run_dir=ledger.run_dir).to_dict()
            projection["drift"] = store.run_projection_status(run_id=ledger.run_dir.name, run_dir=ledger.run_dir)
            projection["projection_path"] = str(projection_path)
            projection["writes_attempted"] = 0
            projection["network_calls_made"] = 0
            projection_path.write_text(
                json.dumps(projection, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            ledger.record_artifact(
                job_id="__run__",
                kind="contact_store_projection",
                path=projection_path,
                metadata={
                    "projected_contacts": projection["projected_contacts"],
                    "drift_state": projection["drift"]["state"],
                },
            )
            ledger.record_event("contact_store_projected", projection)
        except Exception as exc:
            ledger.record_event(
                "contact_store_projection_failed",
                {
                    "run_id": ledger.run_dir.name,
                    "error": str(exc),
                    "retry_command": f"contacts project-run {ledger.run_dir.name} --json",
                    "writes_attempted": 0,
                    "network_calls_made": 0,
                },
            )

    def _process_one(
        self,
        job: CardJob,
        ledger: RunLedger,
        dry_run: bool,
        source_page: dict[str, Any] | None = None,
        known_positive: bool = False,
    ) -> None:
        job.transition_to("processing")
        ledger.record_job(job)

        artifact_dir = ledger.run_dir / "artifacts" / job.job_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        if source_page is not None:
            source_page_payload = build_source_page_artifact(source_page, job_id=job.job_id)
            source_page_path = artifact_dir / "source_page.json"
            source_page_path.write_text(
                json.dumps(source_page_payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            ledger.record_artifact(job_id=job.job_id, kind="source_page", path=source_page_path)
            side_candidate = build_card_side_candidate(source_page, job_id=job.job_id)
            side_candidate_path = artifact_dir / "card_side_candidate.json"
            side_candidate_path.write_text(
                json.dumps(side_candidate, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            ledger.record_artifact(
                job_id=job.job_id,
                kind="card_side_candidate",
                path=side_candidate_path,
                metadata={"side_label": side_candidate["side_label"]},
            )
            ledger.record_event(
                "card_side_candidate_recorded",
                {"job": job.to_dict(), "card_side_candidate": side_candidate},
            )
        if self.config.prefilter.enabled:
            assessment = assess_business_card_candidate(
                Path(job.image_path),
                min_score=self.config.prefilter.min_score,
            )
            prefilter_path = artifact_dir / "preclassification.json"
            assessment_payload = assessment.to_dict()
            classifier_training_state = _classifier_training_state(assessment_payload)
            assessment_payload["classifier_training_state"] = classifier_training_state
            prefilter_path.write_text(
                json.dumps(assessment_payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            ledger.record_artifact(job_id=job.job_id, kind="preclassification", path=prefilter_path)
            ledger.record_event(
                "image_preclassified",
                {"job": job.to_dict(), "assessment": assessment_payload},
            )
            candidate_manifest = build_card_candidate_box_manifest(
                assessment=assessment,
                source_image_path=Path(job.image_path),
                job_id=job.job_id,
            )
            if (
                source_page is not None
                and classifier_training_state != "business_card_high_confidence"
                and not known_positive
            ):
                if not (artifact_dir / "orientation_evidence.json").exists():
                    self._write_orientation_evidence(
                        ledger=ledger,
                        job=job,
                        artifact_dir=artifact_dir,
                        crop_manifest=None,
                    )
                if not (artifact_dir / "qr_evidence.json").exists():
                    self._write_qr_evidence(
                        ledger=ledger,
                        job=job,
                        artifact_dir=artifact_dir,
                        crop_manifest=None,
                    )
                if not (artifact_dir / "crop_quality.json").exists():
                    self._write_crop_quality(
                        ledger=ledger,
                        job=job,
                        artifact_dir=artifact_dir,
                        crop_manifest=None,
                    )
                self._write_classifier_gate(
                    ledger=ledger,
                    job=job,
                    artifact_dir=artifact_dir,
                    classifier_training_state=classifier_training_state,
                    assessment=assessment_payload,
                    admitted=False,
                )
                job.artifact_dir = str(artifact_dir)
                job.transition_to(
                    "failed",
                    error=f"classifier gate blocked scanner page: {classifier_training_state}",
                )
                ledger.record_job(job)
                ledger.record_event(
                    "scanner_page_classifier_gate_blocked",
                    {
                        "job": job.to_dict(),
                        "classifier_training_state": classifier_training_state,
                        "writes_attempted": 0,
                        "network_calls_made": 0,
                    },
                )
                return
            if source_page is not None:
                self._write_classifier_gate(
                    ledger=ledger,
                    job=job,
                    artifact_dir=artifact_dir,
                    classifier_training_state=classifier_training_state,
                    assessment=assessment_payload,
                    admitted=True,
                    admission_reason=(
                        "operator-declared known-positive corpus page admitted for crop/OCR workbench"
                        if known_positive and classifier_training_state != "business_card_high_confidence"
                        else "scanner page passed classifier gate"
                    ),
                )
            elif known_positive:
                self._write_classifier_gate(
                    ledger=ledger,
                    job=job,
                    artifact_dir=artifact_dir,
                    classifier_training_state=classifier_training_state,
                    assessment=assessment_payload,
                    admitted=True,
                    admission_reason=(
                        "operator-declared known-positive corpus image admitted for crop/OCR workbench"
                    ),
                )
            if candidate_manifest["candidate_count"]:
                candidate_manifest_path = artifact_dir / "card_candidates.json"
                candidate_manifest_path.write_text(
                    json.dumps(candidate_manifest, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                ledger.record_artifact(
                    job_id=job.job_id,
                    kind="card_candidates",
                    path=candidate_manifest_path,
                    metadata={"candidate_count": candidate_manifest["candidate_count"]},
                )
                ledger.record_event(
                    "card_candidates_recorded",
                    {"job": job.to_dict(), "candidate_manifest": candidate_manifest},
                )
                work_item_manifest = build_candidate_work_item_manifest(candidate_manifest)
                crop_manifest, work_item_manifest = materialize_candidate_crops(
                    source_image_path=Path(job.image_path),
                    work_item_manifest=work_item_manifest,
                    crop_dir=artifact_dir / "candidate_crops",
                )
                crop_manifest_path = artifact_dir / "candidate_crops.json"
                crop_manifest_path.write_text(
                    json.dumps(crop_manifest, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                ledger.record_artifact(
                    job_id=job.job_id,
                    kind="candidate_crops",
                    path=crop_manifest_path,
                    metadata={"crop_count": crop_manifest["crop_count"]},
                )
                ledger.record_event(
                    "candidate_crops_recorded",
                    {"job": job.to_dict(), "crop_manifest": crop_manifest},
                )
                self._write_orientation_evidence(
                    ledger=ledger,
                    job=job,
                    artifact_dir=artifact_dir,
                    crop_manifest=crop_manifest,
                )
                self._write_qr_evidence(
                    ledger=ledger,
                    job=job,
                    artifact_dir=artifact_dir,
                    crop_manifest=crop_manifest,
                )
                crop_quality, _ = self._write_crop_quality(
                    ledger=ledger,
                    job=job,
                    artifact_dir=artifact_dir,
                    crop_manifest=crop_manifest,
                )
                _, accepted_crop_manifest, work_item_manifest = self._write_crop_acceptance(
                    ledger=ledger,
                    job=job,
                    artifact_dir=artifact_dir,
                    crop_manifest=crop_manifest,
                    crop_quality=crop_quality,
                    work_item_manifest=work_item_manifest,
                )
                verification_request_manifest, work_item_manifest = (
                    build_child_verification_request_manifest(
                        work_item_manifest=work_item_manifest,
                        crop_manifest=accepted_crop_manifest,
                        dry_run=dry_run,
                    )
                )
                verification_request_manifest_path = artifact_dir / "child_verification_requests.json"
                verification_request_manifest_path.write_text(
                    json.dumps(verification_request_manifest, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                ledger.record_artifact(
                    job_id=job.job_id,
                    kind="child_verification_requests",
                    path=verification_request_manifest_path,
                    metadata={"request_count": verification_request_manifest["request_count"]},
                )
                ledger.record_event(
                    "child_verification_requests_recorded",
                    {
                        "job": job.to_dict(),
                        "verification_request_manifest": verification_request_manifest,
                    },
                )
                verification_result_manifest, work_item_manifest = (
                    build_synthetic_child_verification_result_manifest(
                        request_manifest=verification_request_manifest,
                        work_item_manifest=work_item_manifest,
                        result_dir=artifact_dir / "child_verification_results",
                    )
                )
                verification_result_manifest_path = artifact_dir / "child_verification_results.json"
                verification_result_manifest_path.write_text(
                    json.dumps(verification_result_manifest, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                ledger.record_artifact(
                    job_id=job.job_id,
                    kind="child_verification_results",
                    path=verification_result_manifest_path,
                    metadata={"result_count": verification_result_manifest["result_count"]},
                )
                ledger.record_event(
                    "child_verification_results_recorded",
                    {
                        "job": job.to_dict(),
                        "verification_result_manifest": verification_result_manifest,
                    },
                )
                child_promotion_manifest, work_item_manifest = promote_child_verification_results(
                    result_manifest=verification_result_manifest,
                    work_item_manifest=work_item_manifest,
                    promotion_dir=artifact_dir / "child_contact_candidates",
                    default_country=self.config.normalization.default_country,
                )
                child_promotion_manifest_path = artifact_dir / "child_contact_promotions.json"
                child_promotion_manifest_path.write_text(
                    json.dumps(child_promotion_manifest, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                ledger.record_artifact(
                    job_id=job.job_id,
                    kind="child_contact_promotions",
                    path=child_promotion_manifest_path,
                    metadata={"promotion_count": child_promotion_manifest["promotion_count"]},
                )
                ledger.record_event(
                    "child_contact_promotions_recorded",
                    {"job": job.to_dict(), "child_promotion_manifest": child_promotion_manifest},
                )
                work_item_manifest_path = artifact_dir / "candidate_work_items.json"
                work_item_manifest_path.write_text(
                    json.dumps(work_item_manifest, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                ledger.record_artifact(
                    job_id=job.job_id,
                    kind="candidate_work_items",
                    path=work_item_manifest_path,
                    metadata={"work_item_count": work_item_manifest["work_item_count"]},
                )
                ledger.record_event(
                    "candidate_work_items_recorded",
                    {"job": job.to_dict(), "work_item_manifest": work_item_manifest},
                )
            if not known_positive and (
                assessment.decision == "not_business_card"
                or (assessment.decision == "uncertain" and not self.config.prefilter.process_uncertain)
            ):
                if not (artifact_dir / "orientation_evidence.json").exists():
                    self._write_orientation_evidence(
                        ledger=ledger,
                        job=job,
                        artifact_dir=artifact_dir,
                        crop_manifest=None,
                    )
                if not (artifact_dir / "qr_evidence.json").exists():
                    self._write_qr_evidence(
                        ledger=ledger,
                        job=job,
                        artifact_dir=artifact_dir,
                        crop_manifest=None,
                    )
                if not (artifact_dir / "crop_quality.json").exists():
                    self._write_crop_quality(
                        ledger=ledger,
                        job=job,
                        artifact_dir=artifact_dir,
                        crop_manifest=None,
                    )
                job.artifact_dir = str(artifact_dir)
                job.transition_to(
                    "failed",
                    error=f"prefilter rejected image: {assessment.decision}",
                )
                ledger.record_job(job)
                ledger.record_event(
                    "job_prefilter_rejected",
                    {"job": job.to_dict(), "assessment": assessment_payload},
                )
                return

        if not (artifact_dir / "orientation_evidence.json").exists():
            self._write_orientation_evidence(
                ledger=ledger,
                job=job,
                artifact_dir=artifact_dir,
                crop_manifest=None,
            )
        if not (artifact_dir / "qr_evidence.json").exists():
            self._write_qr_evidence(
                ledger=ledger,
                job=job,
                artifact_dir=artifact_dir,
                crop_manifest=None,
            )
        if not (artifact_dir / "crop_quality.json").exists():
            self._write_crop_quality(
                ledger=ledger,
                job=job,
                artifact_dir=artifact_dir,
                crop_manifest=None,
            )

        result = self.adapter.run_pipeline(
            Path(job.image_path),
            artifact_dir,
            apply_google=not dry_run and self.config.sink.google_contacts,
        )
        job.artifact_dir = str(result.artifact_dir)
        ledger.record_artifact(job_id=job.job_id, kind="artifact_dir", path=result.artifact_dir)
        if result.spec_path is not None:
            ledger.record_artifact(job_id=job.job_id, kind="contact_spec", path=result.spec_path)
        if result.review_path is not None:
            ledger.record_artifact(job_id=job.job_id, kind="review_report", path=result.review_path)
        for kind, path in _optional_adapter_artifacts(result.artifact_dir).items():
            ledger.record_artifact(job_id=job.job_id, kind=kind, path=path)

        if result.status != "ok":
            job.transition_to("failed", error=result.error)
            ledger.record_job(job)
            ledger.record_event("job_failed", {"job": job.to_dict(), "stderr": result.stderr[-4000:]})
            return

        side_candidate: dict[str, Any] | None = None
        if source_page is not None:
            ocr_path = result.artifact_dir / "ocr.txt"
            ocr_text = ocr_path.read_text(encoding="utf-8") if ocr_path.exists() else ""
            side_candidate = classify_card_side(
                job_id=job.job_id,
                source_page=source_page,
                ocr_text=ocr_text,
            )
            side_candidate_path = result.artifact_dir / "card_side_candidate.json"
            side_candidate_path.write_text(
                json.dumps(side_candidate, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            ledger.record_artifact(
                job_id=job.job_id,
                kind="card_side_classification",
                path=side_candidate_path,
                metadata={
                    "side_label": side_candidate["side_label"],
                    "confidence": side_candidate["confidence"],
                },
            )
            ledger.record_event(
                "card_side_classified",
                {"job": job.to_dict(), "card_side_candidate": side_candidate},
            )

        spec = load_contact_spec(result.spec_path)
        contact_candidate = build_contact_candidate(
            spec,
            default_country=self.config.normalization.default_country,
        )
        contact_candidate_path = result.artifact_dir / "contact_candidate.json"
        contact_candidate_path.write_text(
            json.dumps(contact_candidate, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        ledger.record_artifact(job_id=job.job_id, kind="contact_candidate", path=contact_candidate_path)
        ledger.record_event(
            "contact_candidate_normalized",
            {"job": job.to_dict(), "contact_candidate_path": str(contact_candidate_path)},
        )

        contact_spec = contact_candidate_to_spec(contact_candidate)
        extraction_quality = assess_extraction_quality(
            artifact_dir=result.artifact_dir,
            source_page=source_page,
            side_candidate=side_candidate,
        )
        extraction_quality_path = write_extraction_quality(
            result.artifact_dir / "extraction_quality.json",
            extraction_quality,
        )
        ledger.record_artifact(
            job_id=job.job_id,
            kind="extraction_quality",
            path=extraction_quality_path,
            metadata={
                "status": extraction_quality.status,
                "route_ready_allowed": extraction_quality.route_ready_allowed,
            },
        )
        ledger.record_event(
            "extraction_quality_assessed",
            {"job": job.to_dict(), "assessment": extraction_quality.to_dict()},
        )
        self._write_ocr_quality_gate(
            ledger=ledger,
            job=job,
            artifact_dir=result.artifact_dir,
            extraction_quality=extraction_quality.to_dict(),
        )
        if known_positive:
            self._write_known_positive_ocr_text_fallback(
                ledger=ledger,
                job=job,
                artifact_dir=result.artifact_dir,
                spec=contact_spec,
            )
            review_packet = write_review_packet(
                packet_path=result.artifact_dir / "review_packet.json",
                image_path=Path(job.image_path),
                spec=contact_spec,
                assessment=assess_contact_spec(contact_spec),
                contact_candidate=contact_candidate,
                extraction_quality=extraction_quality.to_dict(),
            )
            ledger.record_artifact(job_id=job.job_id, kind="review_packet", path=review_packet)
            job.transition_to("needs_review")
            ledger.record_job(job)
            ledger.record_event(
                "known_positive_workbench_review_required",
                {
                    "job": job.to_dict(),
                    "reason": "operator-declared known-positive workbench keeps crop/OCR output review-required",
                    "writes_attempted": 0,
                    "network_calls_made": 0,
                    "live_sink_calls_made": False,
                    "public_web_search_used": False,
                    "paid_enrichment_used": False,
                },
            )
            return
        if extraction_quality.needs_review:
            review_packet = write_review_packet(
                packet_path=result.artifact_dir / "review_packet.json",
                image_path=Path(job.image_path),
                spec=contact_spec,
                assessment=assess_contact_spec(contact_spec),
                contact_candidate=contact_candidate,
                extraction_quality=extraction_quality.to_dict(),
            )
            ledger.record_artifact(job_id=job.job_id, kind="review_packet", path=review_packet)
            job.transition_to("needs_review")
            ledger.record_job(job)
            ledger.record_event(
                "job_quality_needs_review",
                {"job": job.to_dict(), "assessment": extraction_quality.to_dict()},
            )
            return

        assessment = assess_contact_spec(contact_spec)
        if assessment.needs_review:
            review_packet = write_review_packet(
                packet_path=result.artifact_dir / "review_packet.json",
                image_path=Path(job.image_path),
                spec=contact_spec,
                assessment=assessment,
                contact_candidate=contact_candidate,
                extraction_quality=extraction_quality.to_dict(),
            )
            ledger.record_artifact(job_id=job.job_id, kind="review_packet", path=review_packet)
            job.transition_to("needs_review")
            ledger.record_job(job)
            ledger.record_event(
                "job_needs_review",
                {"job": job.to_dict(), "assessment": assessment.to_dict()},
            )
            return

        duplicate = assess_duplicate(
            self.config,
            spec=contact_spec,
            job_id=job.job_id,
            run_id=ledger.run_dir.name,
            image_path=job.image_path,
        )
        duplicate_path = result.artifact_dir / "duplicate_assessment.json"
        duplicate_path.write_text(
            json.dumps(duplicate.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        ledger.record_artifact(job_id=job.job_id, kind="duplicate_assessment", path=duplicate_path)
        ledger.record_event(
            "duplicate_assessed",
            {"job": job.to_dict(), "assessment": duplicate.to_dict()},
        )
        if duplicate.blocks_routing:
            job.transition_to("needs_review")
            ledger.record_job(job)
            ledger.record_event(
                "job_duplicate_needs_review",
                {"job": job.to_dict(), "assessment": duplicate.to_dict()},
            )
            return

        decision = decide_sinks(self.config, contact_spec)
        payloads = build_sink_payloads(
            sinks=decision.sinks,
            spec=contact_spec,
            dry_run=dry_run or decision.dry_run,
            google_contacts_profile=selected_google_contacts_profile(self.config, decision),
            odollo_tenant=selected_odollo_tenant(self.config, decision),
        )
        if payloads:
            sink_payload_path = write_sink_payloads(result.artifact_dir / "sink_payloads.json", payloads)
            ledger.record_artifact(job_id=job.job_id, kind="sink_payloads", path=sink_payload_path)

        job.transition_to("ready_to_route" if decision.sinks else "needs_review")
        if dry_run or decision.dry_run:
            ledger.record_event(
                "sink_decision_dry_run",
                {
                    "job": job.to_dict(),
                    "decision": decision.to_dict(),
                    "payloads": [payload.to_dict() for payload in payloads],
                },
            )
        else:
            ledger.record_event(
                "sink_decision_pending_live_adapter",
                {
                    "job": job.to_dict(),
                    "decision": decision.to_dict(),
                    "payloads": [payload.to_dict() for payload in payloads],
                },
            )
        remember_identity(
            self.config,
            spec=contact_spec,
            job_id=job.job_id,
            run_id=ledger.run_dir.name,
            image_path=job.image_path,
        )
        ledger.record_job(job)

    def _write_orientation_evidence(
        self,
        *,
        ledger: RunLedger,
        job: CardJob,
        artifact_dir: Path,
        crop_manifest: dict[str, Any] | None,
    ) -> dict[str, Any]:
        orientation_evidence = build_orientation_evidence(
            run_id=ledger.run_dir.name,
            job_id=job.job_id,
            source_image_path=Path(job.image_path),
            output_dir=artifact_dir,
            crop_manifest=crop_manifest,
        )
        orientation_evidence_path = artifact_dir / "orientation_evidence.json"
        orientation_evidence_path.write_text(
            json.dumps(orientation_evidence, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        ledger.record_artifact(
            job_id=job.job_id,
            kind="orientation_evidence",
            path=orientation_evidence_path,
            metadata={
                "state": orientation_evidence["state"],
                "normalized_count": orientation_evidence["normalized_count"],
                "needs_review_count": orientation_evidence["needs_review_count"],
            },
        )
        ledger.record_event(
            "orientation_evidence_recorded",
            {
                "job": job.to_dict(),
                "state": orientation_evidence["state"],
                "normalized_count": orientation_evidence["normalized_count"],
                "needs_review_count": orientation_evidence["needs_review_count"],
                "writes_attempted": 0,
                "network_calls_made": 0,
            },
        )
        return orientation_evidence

    def _write_crop_quality(
        self,
        *,
        ledger: RunLedger,
        job: CardJob,
        artifact_dir: Path,
        crop_manifest: dict[str, Any] | None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        qr_evidence_path = artifact_dir / "qr_evidence.json"
        qr_evidence = (
            json.loads(qr_evidence_path.read_text(encoding="utf-8"))
            if qr_evidence_path.exists()
            else {}
        )
        crop_quality = build_crop_quality(
            run_id=ledger.run_dir.name,
            job_id=job.job_id,
            source_image_path=Path(job.image_path),
            crop_manifest=crop_manifest,
            qr_evidence=qr_evidence,
        )
        crop_quality_path = artifact_dir / "crop_quality.json"
        crop_quality_path.write_text(
            json.dumps(crop_quality, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        ledger.record_artifact(
            job_id=job.job_id,
            kind="crop_quality",
            path=crop_quality_path,
            metadata={
                "state": crop_quality["state"],
                "crop_count": crop_quality["crop_count"],
                "bad_count": crop_quality["bad_count"],
                "qr_only_count": crop_quality["qr_only_count"],
            },
        )
        ledger.record_event(
            "crop_quality_recorded",
            {
                "job": job.to_dict(),
                "state": crop_quality["state"],
                "crop_count": crop_quality["crop_count"],
                "bad_count": crop_quality["bad_count"],
                "qr_only_count": crop_quality["qr_only_count"],
                "writes_attempted": 0,
                "network_calls_made": 0,
            },
        )
        recrop_proposals = build_recrop_proposals(
            run_id=ledger.run_dir.name,
            job_id=job.job_id,
            source_image_path=Path(job.image_path),
            crop_quality=crop_quality,
        )
        recrop_path = artifact_dir / "recrop_proposals.json"
        recrop_path.write_text(
            json.dumps(recrop_proposals, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        ledger.record_artifact(
            job_id=job.job_id,
            kind="recrop_proposals",
            path=recrop_path,
            metadata={
                "state": recrop_proposals["state"],
                "proposal_count": recrop_proposals["proposal_count"],
            },
        )
        ledger.record_event(
            "recrop_proposals_recorded",
            {
                "job": job.to_dict(),
                "state": recrop_proposals["state"],
                "proposal_count": recrop_proposals["proposal_count"],
                "writes_attempted": 0,
                "network_calls_made": 0,
            },
        )
        return crop_quality, recrop_proposals

    def _write_crop_acceptance(
        self,
        *,
        ledger: RunLedger,
        job: CardJob,
        artifact_dir: Path,
        crop_manifest: dict[str, Any],
        crop_quality: dict[str, Any],
        work_item_manifest: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        crop_acceptance = build_crop_acceptance(
            run_id=ledger.run_dir.name,
            job_id=job.job_id,
            crop_quality=crop_quality,
        )
        crop_acceptance_path = artifact_dir / "crop_acceptance.json"
        crop_acceptance_path.write_text(
            json.dumps(crop_acceptance, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        ledger.record_artifact(
            job_id=job.job_id,
            kind="crop_acceptance",
            path=crop_acceptance_path,
            metadata={
                "state": crop_acceptance["state"],
                "accepted_count": crop_acceptance["accepted_count"],
                "blocked_count": crop_acceptance["blocked_count"],
                "app_intelligence_request_count": crop_acceptance["app_intelligence_request_count"],
            },
        )
        ledger.record_event(
            "crop_acceptance_recorded",
            {
                "job": job.to_dict(),
                "state": crop_acceptance["state"],
                "accepted_count": crop_acceptance["accepted_count"],
                "blocked_count": crop_acceptance["blocked_count"],
                "app_intelligence_request_count": crop_acceptance["app_intelligence_request_count"],
                "writes_attempted": 0,
                "network_calls_made": 0,
            },
        )
        accepted_work_item_ids = {
            str(crop.get("work_item_id"))
            for crop in crop_acceptance["accepted_crops"]
            if isinstance(crop, dict)
        }
        blocked_by_work_item = {
            str(crop.get("work_item_id")): crop
            for crop in crop_acceptance["blocked_crops"]
            if isinstance(crop, dict)
        }
        accepted_crop_manifest = deepcopy(crop_manifest)
        accepted_crop_manifest["crops"] = [
            crop
            for crop in list(crop_manifest.get("crops") or [])
            if str(crop.get("work_item_id")) in accepted_work_item_ids
        ]
        accepted_crop_manifest["crop_count"] = len(accepted_crop_manifest["crops"])
        updated_work_items = deepcopy(work_item_manifest)
        for item in updated_work_items.get("work_items", []):
            if not isinstance(item, dict):
                continue
            work_item_id = str(item.get("work_item_id") or "")
            if work_item_id in accepted_work_item_ids:
                item["crop_acceptance_state"] = "accepted_for_ocr"
                item["ocr_allowed"] = True
                continue
            blocked = blocked_by_work_item.get(work_item_id)
            if blocked is None:
                continue
            item["state"] = "blocked_needs_crop_quality_review"
            item["phase"] = "awaiting_crop_quality_review"
            item["crop_acceptance_state"] = "blocked_needs_crop_quality_review"
            item["ocr_allowed"] = False
            item["crop_quality"] = blocked.get("quality")
            item["crop_quality_reasons"] = list(blocked.get("reasons") or [])
            item["app_intelligence_request_id"] = blocked.get("app_intelligence_request_id")
        updated_work_items["crop_acceptance_state"] = crop_acceptance["state"]
        updated_work_items["crop_accepted_count"] = crop_acceptance["accepted_count"]
        updated_work_items["crop_blocked_count"] = crop_acceptance["blocked_count"]
        return crop_acceptance, accepted_crop_manifest, updated_work_items

    def _write_classifier_gate(
        self,
        *,
        ledger: RunLedger,
        job: CardJob,
        artifact_dir: Path,
        classifier_training_state: str,
        assessment: dict[str, Any],
        admitted: bool,
        admission_reason: str | None = None,
    ) -> dict[str, Any]:
        payload = {
            "schema": "business-card-watchdog.scanner-page-classifier-gate.v1",
            "run_id": ledger.run_dir.name,
            "job_id": job.job_id,
            "source_image_path": job.image_path,
            "classifier_training_state": classifier_training_state,
            "admitted_to_crop_ocr": admitted,
            "downstream_allowed": admitted,
            "crop_ocr_allowed_for_classifier_states": ["business_card_high_confidence"],
            "crop_ocr_blocked_for_classifier_states": [
                "not_business_card_high_confidence",
                "indeterminate_needs_app_intelligence",
            ],
            "app_intelligence_required_for_classifier_states": ["indeterminate_needs_app_intelligence"],
            "reason": (
                admission_reason
                or "scanner page passed classifier gate"
                if admitted
                else "scanner page blocked before crop/OCR/contact extraction"
            ),
            "deterministic_evidence": {
                "preclassification": assessment,
            },
            "stop_rules": [
                "Do not crop, OCR, side-pair, normalize contacts, route, enrich, or write scanner pages unless admitted_to_crop_ocr is true.",
                "Non-card pages remain blocked from contact extraction.",
                "Indeterminate pages require bounded classify_document_type evidence before downstream card work.",
            ],
            "writes_attempted": 0,
            "network_calls_made": 0,
            "live_sink_calls_made": False,
            "public_web_search_used": False,
            "paid_enrichment_used": False,
        }
        gate_path = artifact_dir / "scanner_page_classifier_gate.json"
        gate_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        ledger.record_artifact(
            job_id=job.job_id,
            kind="scanner_page_classifier_gate",
            path=gate_path,
            metadata={
                "classifier_training_state": classifier_training_state,
                "admitted_to_crop_ocr": admitted,
                "writes_attempted": 0,
                "network_calls_made": 0,
            },
        )
        ledger.record_event(
            "scanner_page_classifier_gate_recorded",
            {
                "job": job.to_dict(),
                "classifier_training_state": classifier_training_state,
                "admitted_to_crop_ocr": admitted,
                "writes_attempted": 0,
                "network_calls_made": 0,
            },
        )
        return payload

    def _write_ocr_quality_gate(
        self,
        *,
        ledger: RunLedger,
        job: CardJob,
        artifact_dir: Path,
        extraction_quality: dict[str, Any],
    ) -> dict[str, Any]:
        classifier_gate = _read_artifact_json(artifact_dir / "scanner_page_classifier_gate.json")
        crop_acceptance = _read_artifact_json(artifact_dir / "crop_acceptance.json")
        needs_review = str(extraction_quality.get("status") or "") == "needs_review"
        request = (
            {
                "request_id": f"{job.job_id}-ocr-quality-review",
                "request_type": "verify_contact_fields",
                "status": "planned",
                "job_id": job.job_id,
                "reason": "OCR or extraction quality is not route-ready",
                "deterministic_evidence": {
                    "extraction_quality": extraction_quality,
                    "classifier_gate": classifier_gate,
                    "crop_acceptance": crop_acceptance,
                },
                "allowed_response_schema": {
                    "type": "object",
                    "required": ["recommendation", "confidence", "rationale", "evidence"],
                    "properties": {
                        "recommendation": {
                            "type": "string",
                            "enum": [
                                "fields_verified",
                                "fields_need_correction",
                                "needs_more_deterministic_evidence",
                            ],
                        },
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "rationale": {"type": "string"},
                        "evidence": {"type": "object"},
                        "training_hint": {"type": "string"},
                    },
                    "forbidden_actions": [
                        "route_contact",
                        "write_sink",
                        "readback_sink",
                        "run_enrichment",
                        "select_live_target",
                    ],
                },
                "stop_rules": [
                    "Return OCR/contact-field evidence only; do not route, enrich, write, or read back.",
                    "Accepted App Intelligence evidence must become reviewed deterministic field evidence before routing.",
                ],
                "writes_attempted": 0,
                "network_calls_made": 0,
            }
            if needs_review
            else None
        )
        payload = {
            "schema": "business-card-watchdog.ocr-quality-gate.v1",
            "run_id": ledger.run_dir.name,
            "job_id": job.job_id,
            "state": "needs_app_intelligence_review" if needs_review else "passed",
            "route_ready_allowed": bool(extraction_quality.get("route_ready_allowed")) and not needs_review,
            "classifier_training_state": classifier_gate.get("classifier_training_state") or "",
            "classifier_gate_admitted": classifier_gate.get("admitted_to_crop_ocr"),
            "crop_acceptance_state": crop_acceptance.get("state") or "",
            "crop_accepted_count": int(crop_acceptance.get("accepted_count") or 0),
            "extraction_quality_status": extraction_quality.get("status"),
            "extraction_quality_reasons": list(extraction_quality.get("reasons") or []),
            "lineage": {
                "ocr_text_path": str(artifact_dir / "ocr.txt"),
                "extraction_quality_path": str(artifact_dir / "extraction_quality.json"),
                "scanner_page_classifier_gate_path": str(artifact_dir / "scanner_page_classifier_gate.json")
                if classifier_gate
                else "",
                "crop_acceptance_path": str(artifact_dir / "crop_acceptance.json") if crop_acceptance else "",
            },
            "app_intelligence_request_count": 1 if request else 0,
            "app_intelligence_requests": [request] if request else [],
            "routing_allowed": False,
            "enrichment_allowed": False,
            "sink_write_allowed": False,
            "explicit_stop_conditions": [
                "OCR quality gates produce evidence only.",
                "Do not route, enrich, write, or read back contacts from OCR quality evidence.",
                "Contacts remain review-required until extraction and field quality gates pass.",
            ],
            "writes_attempted": 0,
            "network_calls_made": 0,
            "live_sink_calls_made": False,
            "public_web_search_used": False,
            "paid_enrichment_used": False,
        }
        gate_path = artifact_dir / "ocr_quality_gate.json"
        gate_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        ledger.record_artifact(
            job_id=job.job_id,
            kind="ocr_quality_gate",
            path=gate_path,
            metadata={
                "state": payload["state"],
                "route_ready_allowed": payload["route_ready_allowed"],
                "app_intelligence_request_count": payload["app_intelligence_request_count"],
            },
        )
        ledger.record_event(
            "ocr_quality_gate_recorded",
            {
                "job": job.to_dict(),
                "state": payload["state"],
                "route_ready_allowed": payload["route_ready_allowed"],
                "app_intelligence_request_count": payload["app_intelligence_request_count"],
                "writes_attempted": 0,
                "network_calls_made": 0,
            },
        )
        return payload

    def _write_known_positive_ocr_text_fallback(
        self,
        *,
        ledger: RunLedger,
        job: CardJob,
        artifact_dir: Path,
        spec: dict[str, Any],
    ) -> Path | None:
        ocr_path = artifact_dir / "ocr.txt"
        if ocr_path.exists():
            return None
        lines = [
            "OCR text unavailable from adapter.",
            "Derived review text from normalized contact spec for known-positive crop/OCR workbench.",
        ]
        for key in ("full_name", "organization", "title", "email", "phone", "website", "notes"):
            value = spec.get(key)
            if value:
                lines.append(f"{key}: {value}")
        ocr_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
        ledger.record_artifact(
            job_id=job.job_id,
            kind="ocr_text",
            path=ocr_path,
            metadata={
                "source": "derived_from_contact_spec",
                "raw_adapter_ocr_available": False,
                "known_positive_workbench_only": True,
            },
        )
        ledger.record_event(
            "known_positive_ocr_text_fallback_recorded",
            {
                "job": job.to_dict(),
                "source": "derived_from_contact_spec",
                "raw_adapter_ocr_available": False,
                "writes_attempted": 0,
                "network_calls_made": 0,
            },
        )
        return ocr_path

    def _write_qr_evidence(
        self,
        *,
        ledger: RunLedger,
        job: CardJob,
        artifact_dir: Path,
        crop_manifest: dict[str, Any] | None,
    ) -> dict[str, Any]:
        qr_evidence = build_qr_evidence(
            run_id=ledger.run_dir.name,
            job_id=job.job_id,
            source_image_path=Path(job.image_path),
            crop_manifest=crop_manifest,
        )
        qr_evidence_path = artifact_dir / "qr_evidence.json"
        qr_evidence_path.write_text(
            json.dumps(qr_evidence, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        ledger.record_artifact(
            job_id=job.job_id,
            kind="qr_evidence",
            path=qr_evidence_path,
            metadata={
                "state": qr_evidence["state"],
                "qr_found": qr_evidence["qr_found"],
                "decode_count": qr_evidence["decode_count"],
                "payload_types": qr_evidence["payload_types"],
            },
        )
        ledger.record_event(
            "qr_evidence_recorded",
            {
                "job": job.to_dict(),
                "state": qr_evidence["state"],
                "qr_found": qr_evidence["qr_found"],
                "decode_count": qr_evidence["decode_count"],
                "payload_types": qr_evidence["payload_types"],
                "writes_attempted": 0,
                "network_calls_made": 0,
            },
        )
        return qr_evidence


def _optional_adapter_artifacts(artifact_dir: Path) -> dict[str, Path]:
    candidates = [
        ("ocr_text", artifact_dir / "ocr.txt"),
        ("crop_manifest", artifact_dir / "manifest.json"),
        ("crop_manifest", artifact_dir / "crop_manifest.json"),
        ("contact_sheet", artifact_dir / "contact_sheet.jpg"),
    ]
    artifacts: dict[str, Path] = {}
    for kind, path in candidates:
        if kind not in artifacts and path.exists():
            artifacts[kind] = path
    return artifacts


def _classifier_training_state(assessment: dict[str, Any]) -> str:
    decision = str(assessment.get("decision") or "")
    score = float(assessment.get("score") or 0.0)
    if decision == "likely_business_card" and score >= 0.55:
        return "business_card_high_confidence"
    if decision == "not_business_card" and score <= 0.05:
        return "not_business_card_high_confidence"
    return "indeterminate_needs_app_intelligence"


def _read_artifact_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}
