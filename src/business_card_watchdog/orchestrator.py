from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .config import AppConfig, ensure_runtime_dirs, resolve_input_path
from .contact import build_contact_candidate, contact_candidate_to_spec
from .dedupe import assess_duplicate, remember_identity
from .fanout import (
    build_candidate_work_item_manifest,
    build_child_verification_request_manifest,
    materialize_candidate_crops,
)
from .ledger import RunLedger
from .models import CardJob, utc_now
from .preclassifier import assess_business_card_candidate, build_card_candidate_box_manifest
from .review import assess_contact_spec, write_review_packet
from .routing import decide_sinks, load_contact_spec
from .sinks import build_sink_payloads, write_sink_payloads
from .skill_adapter import BusinessCardSkillAdapter, is_supported_image


def discover_images(source: Path) -> list[Path]:
    if source.is_file():
        return [source] if is_supported_image(source) else []
    if not source.exists():
        raise FileNotFoundError(source)
    return sorted(path for path in source.rglob("*") if is_supported_image(path))


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

        jobs = [CardJob.from_path(path) for path in discover_images(source)]
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
            futures = {pool.submit(self._process_one, job, ledger, dry_run): job for job in jobs}
            for future in as_completed(futures):
                future.result()

        ledger.record_event("run_completed", {"job_count": len(jobs)})
        ledger.transition_run("completed")
        return run_dir

    def _process_one(self, job: CardJob, ledger: RunLedger, dry_run: bool) -> None:
        job.transition_to("processing")
        ledger.record_job(job)

        artifact_dir = ledger.run_dir / "artifacts" / job.job_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
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
            if assessment.decision == "not_business_card" or (
                assessment.decision == "uncertain" and not self.config.prefilter.process_uncertain
            ):
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
        assessment = assess_contact_spec(contact_spec)
        if assessment.needs_review:
            review_packet = write_review_packet(
                packet_path=result.artifact_dir / "review_packet.json",
                image_path=Path(job.image_path),
                spec=contact_spec,
                assessment=assessment,
                contact_candidate=contact_candidate,
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
