from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .config import AppConfig, ensure_runtime_dirs, resolve_input_path
from .ledger import RunLedger
from .models import CardJob, utc_now
from .preclassifier import assess_business_card_candidate
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
        assessment = assess_contact_spec(spec)
        if assessment.needs_review:
            review_packet = write_review_packet(
                packet_path=result.artifact_dir / "review_packet.json",
                image_path=Path(job.image_path),
                spec=spec,
                assessment=assessment,
            )
            ledger.record_artifact(job_id=job.job_id, kind="review_packet", path=review_packet)
            job.transition_to("needs_review")
            ledger.record_job(job)
            ledger.record_event(
                "job_needs_review",
                {"job": job.to_dict(), "assessment": assessment.to_dict()},
            )
            return

        decision = decide_sinks(self.config, spec)
        payloads = build_sink_payloads(
            sinks=decision.sinks,
            spec=spec,
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
