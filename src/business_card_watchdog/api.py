from pathlib import Path

from .config import load_config
from .service import BusinessCardService


def create_app(config_path: Path | None = None):
    try:
        from fastapi import Body, FastAPI
        from pydantic import BaseModel, Field
    except ImportError as exc:
        raise RuntimeError("Install with the api extra: pip install -e '.[api]'") from exc

    class ProcessRequest(BaseModel):
        source: str
        dry_run: bool = True
        workers: int = 2

    class ReviewRequest(BaseModel):
        run_id: str
        reviewer: str = "operator"
        action: str = "keep_needs_review"
        field_corrections: dict[str, object] = Field(default_factory=dict)
        crop_selection: dict[str, object] = Field(default_factory=dict)
        approved_enrichment_fields: list[str] = Field(default_factory=list)
        duplicate_resolution: dict[str, object] = Field(default_factory=dict)
        notes: str = ""

    class ReviewDecisionsRequest(BaseModel):
        reviewer: str = "operator"
        decisions: list[dict[str, object]] = Field(default_factory=list)
        decisions_csv: str = ""
        preview: bool = False
        preview_write: bool = False

    class EnrichmentRequest(BaseModel):
        run_id: str
        mode: str = "public_web"
        requested_by: str = "operator"
        allow_paid_enrichment: bool = False
        public_web_results: list[dict[str, object]] = Field(default_factory=list)
        provider_results: list[dict[str, object]] = Field(default_factory=list)

    class PublicWebResultsRequest(BaseModel):
        run_id: str
        searched_by: str = "operator"
        results: list[dict[str, object]] = Field(default_factory=list)

    class PublicWebHandoffRequest(BaseModel):
        run_id: str

    class ProviderResultsRequest(BaseModel):
        run_id: str
        provider: str = "apollo"
        submitted_by: str = "operator"
        results: list[dict[str, object]] = Field(default_factory=list)

    class ProviderHandoffRequest(BaseModel):
        run_id: str

    class SinkApplyPreflightRequest(BaseModel):
        run_id: str
        apply: bool = False
        simulate: bool = False
        sink: str | None = None

    class SinkApplyPilotBundleRequest(BaseModel):
        run_id: str
        sink: str
        operator: str = "operator"

    class SinkApplyDecisionRequest(BaseModel):
        run_id: str
        decision: str
        reviewer: str = "operator"
        reason: str = ""

    class SinkAdapterRequest(BaseModel):
        run_id: str
        phase: str = "lookup"

    class SinkLookupResultRequest(BaseModel):
        run_id: str
        matches_by_sink: dict[str, list[dict[str, object]]] = Field(default_factory=dict)

    class SinkLookupPilotRequest(BaseModel):
        run_id: str
        sink: str
        approved_by: str
        matches: list[dict[str, object]] = Field(default_factory=list)
        simulate: bool = True

    class SinkLookupReadinessRequest(BaseModel):
        run_id: str
        sink: str

    class SinkWritePilotRequest(BaseModel):
        run_id: str
        sink: str
        approved_by: str
        simulate: bool = True

    class SinkReadbackPilotRequest(BaseModel):
        run_id: str
        sink: str
        approved_by: str
        readback: dict[str, object] = Field(default_factory=dict)
        simulate: bool = True

    class RunNextActionsRequest(BaseModel):
        run_id: str | None = None
        limit: int = 10

    app = FastAPI(title="Business Card Watchdog")

    def service() -> BusinessCardService:
        return BusinessCardService(load_config(config_path))

    @app.get("/health")
    def health() -> dict[str, object]:
        status = service().status()
        return {"ok": bool(status["skill_ready"]), "skill": status["skill_message"]}

    @app.get("/status")
    def status() -> dict[str, object]:
        return service().status()

    @app.post("/runs")
    def create_run(request: ProcessRequest) -> dict[str, object]:
        return service().process_source(
            request.source,
            dry_run=request.dry_run,
            workers=request.workers,
        )

    @app.get("/runs")
    def list_runs() -> list[dict[str, object]]:
        return service().list_runs()

    @app.get("/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, object]:
        return service().get_run(run_id)

    @app.get("/runs/{run_id}/summary")
    def get_run_summary(run_id: str) -> dict[str, object]:
        return service().run_summary(run_id)

    @app.get("/runs/{run_id}/phase-report")
    def get_run_phase_report(run_id: str) -> dict[str, object]:
        return service().phase_report(run_id)

    @app.get("/runs/{run_id}/pilot-readiness")
    def get_run_pilot_readiness(run_id: str) -> dict[str, object]:
        return service().pilot_readiness_report(run_id)

    @app.get("/runs/{run_id}/jobs")
    def list_run_jobs(run_id: str) -> list[dict[str, object]]:
        return service().list_jobs(run_id)

    @app.get("/reviews")
    def list_reviews(
        run_id: str | None = None,
        state: str = "needs_review",
        next_action: str | None = None,
        artifact_kind: str | None = None,
    ) -> list[dict[str, object]]:
        return service().review_queue(
            run_id=run_id,
            state=state,
            next_action=next_action,
            artifact_kind=artifact_kind,
        )

    @app.post("/runs/{run_id}/review-bundle")
    def create_review_bundle(run_id: str, state: str = "all", write: bool = True) -> dict[str, object]:
        return service().review_bundle(run_id=run_id, state=state, write=write)

    @app.post("/runs/{run_id}/review-html")
    def create_review_html(run_id: str, state: str = "all", write: bool = True) -> dict[str, object]:
        return service().review_html(run_id=run_id, state=state, write=write)

    @app.post("/runs/{run_id}/review-workbook")
    def create_review_workbook(run_id: str, state: str = "all", write: bool = True) -> dict[str, object]:
        return service().review_workbook(run_id=run_id, state=state, write=write)

    @app.post("/runs/{run_id}/review-workbook-validation")
    def create_review_workbook_validation(
        run_id: str,
        request: ReviewDecisionsRequest = Body(...),
    ) -> dict[str, object]:
        return service().preview_review_workbook_csv(
            run_id=run_id,
            reviewer=request.reviewer,
            csv_text=request.decisions_csv,
            write=request.preview_write,
        )

    @app.post("/runs/{run_id}/review-decisions")
    def apply_review_decisions(run_id: str, request: ReviewDecisionsRequest = Body(...)) -> dict[str, object]:
        if request.decisions_csv:
            if request.preview:
                return service().preview_review_workbook_csv(
                    run_id=run_id,
                    reviewer=request.reviewer,
                    csv_text=request.decisions_csv,
                    write=request.preview_write,
                )
            return service().apply_review_workbook_csv(
                run_id=run_id,
                reviewer=request.reviewer,
                csv_text=request.decisions_csv,
            )
        return service().apply_review_decisions(
            run_id=run_id,
            reviewer=request.reviewer,
            decisions=[dict(decision) for decision in request.decisions],
        )

    @app.post("/actions/run-next")
    def run_next_actions(request: RunNextActionsRequest = Body(default=RunNextActionsRequest())) -> dict[str, object]:
        return service().run_next_actions(run_id=request.run_id, limit=request.limit)

    @app.get("/jobs/{job_id}")
    def get_job(job_id: str, run_id: str | None = None) -> dict[str, object]:
        return service().get_job(job_id, run_id=run_id)

    @app.post("/jobs/{job_id}/review")
    def submit_review(job_id: str, request: ReviewRequest = Body(...)) -> dict[str, object]:
        return service().submit_review(
            job_id=job_id,
            run_id=request.run_id,
            reviewer=request.reviewer,
            action=request.action,
            field_corrections=dict(request.field_corrections),
            crop_selection=dict(request.crop_selection),
            approved_enrichment_fields=list(request.approved_enrichment_fields),
            duplicate_resolution=dict(request.duplicate_resolution),
            notes=request.notes,
        )

    @app.post("/jobs/{job_id}/enrichment")
    def request_enrichment(job_id: str, request: EnrichmentRequest = Body(...)) -> dict[str, object]:
        return service().request_enrichment(
            job_id=job_id,
            run_id=request.run_id,
            mode=request.mode,
            requested_by=request.requested_by,
            allow_paid_enrichment=request.allow_paid_enrichment,
            public_web_results=[dict(row) for row in request.public_web_results],
            provider_results=[dict(row) for row in request.provider_results],
        )

    @app.post("/jobs/{job_id}/enrichment/public-web-results")
    def record_public_web_results(job_id: str, request: PublicWebResultsRequest = Body(...)) -> dict[str, object]:
        return service().record_public_web_enrichment_results(
            job_id=job_id,
            run_id=request.run_id,
            searched_by=request.searched_by,
            results=[dict(row) for row in request.results],
        )

    @app.post("/jobs/{job_id}/enrichment/public-web-handoff")
    def create_public_web_handoff(job_id: str, request: PublicWebHandoffRequest = Body(...)) -> dict[str, object]:
        return service().build_public_web_enrichment_handoff(
            job_id=job_id,
            run_id=request.run_id,
        )

    @app.post("/jobs/{job_id}/enrichment/provider-handoff")
    def create_provider_handoff(job_id: str, request: ProviderHandoffRequest = Body(...)) -> dict[str, object]:
        return service().build_provider_enrichment_handoff(
            job_id=job_id,
            run_id=request.run_id,
        )

    @app.post("/jobs/{job_id}/enrichment/provider-results")
    def record_provider_results(job_id: str, request: ProviderResultsRequest = Body(...)) -> dict[str, object]:
        return service().record_provider_enrichment_results(
            job_id=job_id,
            run_id=request.run_id,
            provider=request.provider,
            submitted_by=request.submitted_by,
            results=[dict(row) for row in request.results],
        )

    @app.post("/sinks/check")
    def sink_check() -> dict[str, object]:
        return service().sink_readiness()

    @app.post("/jobs/{job_id}/sink-plan")
    def create_sink_plan(job_id: str, run_id: str, dry_run: bool = True) -> dict[str, object]:
        return service().plan_sinks_for_job(job_id=job_id, run_id=run_id, dry_run=dry_run)

    @app.post("/jobs/{job_id}/sink-lookup-plan")
    def create_sink_lookup_plan(job_id: str, run_id: str, dry_run: bool = True) -> dict[str, object]:
        return service().plan_sink_lookup_for_job(job_id=job_id, run_id=run_id, dry_run=dry_run)

    @app.post("/jobs/{job_id}/sink-apply-preflight")
    def create_sink_apply_preflight(
        job_id: str,
        request: SinkApplyPreflightRequest = Body(...),
    ) -> dict[str, object]:
        return service().preflight_sink_apply(job_id=job_id, run_id=request.run_id, apply=request.apply)

    @app.post("/jobs/{job_id}/sink-apply-decision")
    def create_sink_apply_decision(
        job_id: str,
        request: SinkApplyDecisionRequest = Body(...),
    ) -> dict[str, object]:
        return service().decide_sink_apply(
            job_id=job_id,
            run_id=request.run_id,
            decision=request.decision,
            reviewer=request.reviewer,
            reason=request.reason,
        )

    @app.post("/jobs/{job_id}/sink-apply")
    def apply_sinks(job_id: str, request: SinkApplyPreflightRequest = Body(...)) -> dict[str, object]:
        return service().apply_sinks_for_job(
            job_id=job_id,
            run_id=request.run_id,
            apply=request.apply,
            simulate=request.simulate,
        )

    @app.post("/jobs/{job_id}/sink-apply-pilot-readiness")
    def create_sink_apply_pilot_readiness(
        job_id: str,
        request: SinkApplyPreflightRequest = Body(...),
    ) -> dict[str, object]:
        return service().build_sink_apply_pilot_readiness_for_job(
            job_id=job_id,
            run_id=request.run_id,
            sink=request.sink,
        )

    @app.post("/jobs/{job_id}/sink-apply-pilot-report")
    def create_sink_apply_pilot_report(
        job_id: str,
        request: SinkApplyPreflightRequest = Body(...),
    ) -> dict[str, object]:
        return service().build_sink_apply_pilot_report_for_job(job_id=job_id, run_id=request.run_id)

    @app.post("/jobs/{job_id}/sink-apply-pilot-bundle")
    def create_sink_apply_pilot_bundle(
        job_id: str,
        request: SinkApplyPilotBundleRequest = Body(...),
    ) -> dict[str, object]:
        return service().build_sink_apply_pilot_bundle_for_job(
            job_id=job_id,
            run_id=request.run_id,
            sink=request.sink,
            operator=request.operator,
        )

    @app.post("/jobs/{job_id}/sink-adapter-request")
    def create_sink_adapter_request(job_id: str, request: SinkAdapterRequest = Body(...)) -> dict[str, object]:
        return service().build_sink_adapter_request_for_job(
            job_id=job_id,
            run_id=request.run_id,
            phase=request.phase,  # type: ignore[arg-type]
        )

    @app.post("/jobs/{job_id}/sink-lookup-result")
    def create_sink_lookup_result(job_id: str, request: SinkLookupResultRequest = Body(...)) -> dict[str, object]:
        return service().record_sink_lookup_result_for_job(
            job_id=job_id,
            run_id=request.run_id,
            matches_by_sink={sink: [dict(match) for match in matches] for sink, matches in request.matches_by_sink.items()},
        )

    @app.post("/jobs/{job_id}/sink-lookup-pilot")
    def create_sink_lookup_pilot(job_id: str, request: SinkLookupPilotRequest = Body(...)) -> dict[str, object]:
        return service().execute_sink_lookup_pilot_for_job(
            job_id=job_id,
            run_id=request.run_id,
            sink=request.sink,
            approved_by=request.approved_by,
            matches=[dict(match) for match in request.matches],
            simulate=request.simulate,
        )

    @app.post("/jobs/{job_id}/sink-lookup-readiness")
    def create_sink_lookup_readiness(
        job_id: str,
        request: SinkLookupReadinessRequest = Body(...),
    ) -> dict[str, object]:
        return service().live_lookup_readiness_report(
            job_id=job_id,
            run_id=request.run_id,
            sink=request.sink,
        )

    @app.post("/jobs/{job_id}/sink-write-pilot")
    def create_sink_write_pilot(job_id: str, request: SinkWritePilotRequest = Body(...)) -> dict[str, object]:
        return service().execute_sink_write_pilot_for_job(
            job_id=job_id,
            run_id=request.run_id,
            sink=request.sink,
            approved_by=request.approved_by,
            simulate=request.simulate,
        )

    @app.post("/jobs/{job_id}/sink-readback-pilot")
    def create_sink_readback_pilot(job_id: str, request: SinkReadbackPilotRequest = Body(...)) -> dict[str, object]:
        return service().execute_sink_readback_pilot_for_job(
            job_id=job_id,
            run_id=request.run_id,
            sink=request.sink,
            approved_by=request.approved_by,
            readback=dict(request.readback),
            simulate=request.simulate,
        )

    @app.post("/jobs/{job_id}/downstream-duplicate-assessment")
    def create_downstream_duplicate_assessment(job_id: str, run_id: str) -> dict[str, object]:
        return service().assess_downstream_duplicates_for_job(job_id=job_id, run_id=run_id)

    @app.post("/enrichment/check")
    def enrichment_check(request: EnrichmentRequest = Body(default=EnrichmentRequest(run_id=""))) -> dict[str, object]:
        return service().enrichment_readiness(
            mode=request.mode,
            allow_paid_enrichment=request.allow_paid_enrichment,
        )

    @app.get("/watch/status")
    def watch_status() -> dict[str, object]:
        return service().watch_status()

    return app
