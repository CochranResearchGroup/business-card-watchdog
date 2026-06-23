from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from .card_sides import build_pair_proposals, classify_card_side
from .config import AppConfig, ensure_runtime_dirs, resolve_input_path
from .contact import build_contact_candidate, contact_candidate_to_spec
from .contact_store import ContactStore
from .crop_quality import build_crop_quality, build_recrop_proposals
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


class BatchOrchestrator:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.adapter = BusinessCardSkillAdapter(config)

    def process_source(self, raw_source: str, *, dry_run: bool = True, workers: int = 2) -> Path:
        ensure_runtime_dirs(self.config)
        source = resolve_input_path(raw_source, self.config)
        run_dir = self.config.runs_dir / utc_now().replace(":", "-")
        ledger = RunLedger(run_dir)
        ledger.initialize(source=str(source), dry_run=dry_run)
        ledger.transition_run("discovering")

        processable_sources = discover_processable_sources(source)
        page_lineage_by_path: dict[str, dict[str, Any]] = {}
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
                ): job
                for job in jobs
            }
            for future in as_completed(futures):
                future.result()

        self._write_card_side_pair_proposals(ledger)
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
            prefilter_path.write_text(
                json.dumps(assessment.to_dict(), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            ledger.record_artifact(job_id=job.job_id, kind="preclassification", path=prefilter_path)
            ledger.record_event(
                "image_preclassified",
                {"job": job.to_dict(), "assessment": assessment.to_dict()},
            )
            candidate_manifest = build_card_candidate_box_manifest(
                assessment=assessment,
                source_image_path=Path(job.image_path),
                job_id=job.job_id,
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
                verification_request_manifest, work_item_manifest = (
                    build_child_verification_request_manifest(
                        work_item_manifest=work_item_manifest,
                        crop_manifest=crop_manifest,
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
                self._write_crop_quality(
                    ledger=ledger,
                    job=job,
                    artifact_dir=artifact_dir,
                    crop_manifest=crop_manifest,
                )
            if assessment.decision == "not_business_card" or (
                assessment.decision == "uncertain" and not self.config.prefilter.process_uncertain
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
                    {"job": job.to_dict(), "assessment": assessment.to_dict()},
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
