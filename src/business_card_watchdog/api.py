from pathlib import Path

from .config import load_config
from .service import BusinessCardService
from .surface_registry import (
    LOOKUP_SELECTION_PACKET_API_PATH,
    OPERATOR_LIVE_PILOT_READINESS_API_PATH,
    PILOT_READINESS_API_PATH,
    REVIEW_ROUTE_READINESS_API_PATH,
    SELECTED_TARGET_APPROVAL_BOUNDARY_API_PATH,
    SELECTED_TARGET_COMMAND_COPY_PACKET_API_PATH,
)


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

    class ChildReviewRequest(BaseModel):
        run_id: str
        reviewer: str = "operator"
        action: str = "keep_needs_review"
        field_corrections: dict[str, object] = Field(default_factory=dict)
        notes: str = ""

    class ChildRoutePrepRequest(BaseModel):
        run_id: str
        dry_run: bool = True

    class ChildLookupResultRequest(BaseModel):
        run_id: str
        matches_by_sink: dict[str, list[dict[str, object]]] = Field(default_factory=dict)

    class ChildDuplicateResolutionRequest(BaseModel):
        run_id: str
        reviewer: str = "operator"
        decision: str
        target_identity: str = ""
        reason: str = ""

    class ChildSinkApplyPreflightRequest(BaseModel):
        run_id: str
        apply: bool = False

    class ChildSelectedTargetHandoffRequest(BaseModel):
        run_id: str
        sink: str
        operator: str = "operator"
        scope: str = "write"
        reason: str = ""

    class ChildSelectedTargetResponseRequest(BaseModel):
        run_id: str
        response: str

    class ChildSelectedTargetCommandCopyRequest(BaseModel):
        run_id: str
        response: str
        acknowledgement: str = ""

    class ContactReviewRecommendationRequest(BaseModel):
        source: str = "app_intelligence"
        category: str
        recommendation: str
        rationale: str = ""
        confidence: float | None = None
        evidence: dict[str, object] = Field(default_factory=dict)

    class ContactReviewDecisionRequest(BaseModel):
        reviewer: str = "operator"
        decision: str
        notes: str = ""

    class ContactReviewSafeLoopRequest(BaseModel):
        limit: int = 10
        reviewer: str = "safe-loop"
        apply: bool = False

    class ContactRouteSelectionApprovalBoundaryRequest(BaseModel):
        operator: str = "operator"
        sink: str | None = None
        response: str | None = None
        write: bool = True

    class ContactRouteSelectionCommandCopyRequest(BaseModel):
        operator: str = "operator"
        response: str
        acknowledgement: str = ""
        sink: str | None = None

    class ChildSelectedTargetAuditRequest(BaseModel):
        run_id: str
        sink: str | None = None
        operator: str | None = None
        scope: str | None = None
        write: bool = True

    class ChildSelectedTargetAbandonmentRequest(BaseModel):
        run_id: str
        operator: str
        reason: str

    class ChildSelectedTargetReplacementResetRequest(BaseModel):
        run_id: str
        sink: str
        operator: str
        scope: str = "write"
        reset_by: str = "operator"
        reason: str = ""

    class ChildReplacementHandoffRefreshRequest(BaseModel):
        run_id: str
        sink: str
        operator: str
        scope: str = "write"
        reason: str = ""

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
        provider: str = "apollo"
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

    class SinkLookupSmokeHandoffRequest(BaseModel):
        run_id: str
        sink: str
        approved_by: str = "operator"

    class LiveSelectionPacketRequest(BaseModel):
        run_id: str
        sink: str
        operator: str
        scope: str = "lookup"
        reason: str = ""
        write: bool = True

    class LookupSelectionPacketRequest(BaseModel):
        operator: str
        sink: str | None = None
        write: bool = True

    class CloseLookupPrerequisitesRequest(BaseModel):
        operator: str
        sink: str | None = None
        limit: int = 5
        write: bool = True

    class SelectedTargetApprovalBoundaryRequest(BaseModel):
        operator: str
        sink: str | None = None
        job_id: str | None = None
        response: str | None = None
        write: bool = True

    class SelectedTargetCommandCopyPacketRequest(BaseModel):
        operator: str
        response: str
        acknowledgement: str = ""
        sink: str | None = None
        job_id: str | None = None

    class SelectedLiveTargetRequest(BaseModel):
        run_id: str
        sink: str
        operator: str
        scope: str = "lookup"
        reason: str = ""
        safety_confirmation: str

    class SelectedLiveTargetPreflightRequest(BaseModel):
        response: str

    class SelectedLiveTargetFromResponseRequest(BaseModel):
        response: str
        write_selected_target: bool = False
        reason: str = ""

    class SelectedLiveTargetHandoffFromResponseRequest(BaseModel):
        response: str
        write_audit: bool = False

    class LookupSmokeHandoffFromResponseRequest(BaseModel):
        response: str
        write_handoff: bool = False

    class SelectedLookupSmokeExecutionPacketFromResponseRequest(BaseModel):
        response: str
        execute_selected_lookup_smoke: bool = False

    class SelectedWritePilotExecutionPacketFromResponseRequest(BaseModel):
        response: str
        execute_write_pilot: bool = False

    class SelectedReadbackPilotExecutionPacketFromResponseRequest(BaseModel):
        response: str
        execute_readback_pilot: bool = False

    class LivePilotCloseoutPacketFromResponseRequest(BaseModel):
        response: str
        write_closeout: bool = False

    class LivePilotOperatorWorkflowPacketFromResponseRequest(BaseModel):
        response: str

    class LivePilotOperatorRehearsalFromResponseRequest(BaseModel):
        response: str

    class LivePilotReadinessExportFromResponseRequest(BaseModel):
        response: str
        write: bool = True

    class LivePilotExecutionChecklistFromResponseRequest(BaseModel):
        response: str

    class LivePilotCommandCopyPacketFromResponseRequest(BaseModel):
        response: str
        acknowledgement: str = ""

    class SelectedLiveTargetAuditRequest(BaseModel):
        run_id: str
        scope: str | None = None
        write: bool = True

    class LivePilotAbandonRequest(BaseModel):
        run_id: str
        operator: str
        reason: str

    class SelectedLookupSmokeRequest(BaseModel):
        run_id: str

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

    class LivePilotCloseoutRequest(BaseModel):
        run_id: str
        write: bool = True

    class LivePilotOperatorResponseValidationRequest(BaseModel):
        response: str

    class RunNextActionsRequest(BaseModel):
        run_id: str | None = None
        limit: int = 10

    class NextActionsRequest(BaseModel):
        run_id: str | None = None
        limit: int = 20

    class LiveReadinessAuditRequest(BaseModel):
        run_id: str | None = None
        sink: str | None = None
        write: bool = True

    class LiveSelectionRequirementsRequest(BaseModel):
        run_id: str | None = None
        sink: str | None = None
        write: bool = True

    class OperatorSelectedLiveSmokePreflightRequest(BaseModel):
        run_id: str | None = None
        sink: str | None = None
        write: bool = True

    class OperatorLivePilotReadinessPacketRequest(BaseModel):
        run_id: str
        sink: str | None = None
        write: bool = True

    class WatchBacklogPreflightRequest(BaseModel):
        write: bool = True

    class WatchDryRunSelectionHandoffRequest(BaseModel):
        write: bool = True

    class WatchDryRunOperatorResponseRequest(BaseModel):
        response: str
        acknowledgement: str = ""

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

    @app.get("/operator/dashboard")
    def operator_dashboard(run_id: str | None = None) -> dict[str, object]:
        return service().operator_dashboard(run_id=run_id)

    @app.get("/runtime/readiness")
    def runtime_readiness() -> dict[str, object]:
        return service().runtime_readiness()

    @app.get("/service/recovery")
    def service_recovery(run_id: str | None = None) -> dict[str, object]:
        return service().service_recovery_report(run_id=run_id)

    @app.get("/live-target-candidates")
    def live_target_candidates(run_id: str | None = None, sink: str | None = None) -> dict[str, object]:
        return service().live_target_candidates(run_id=run_id, sink=sink)

    @app.post("/live-readiness-audit")
    def live_readiness_audit(request: LiveReadinessAuditRequest = Body(...)) -> dict[str, object]:
        return service().live_readiness_audit(
            run_id=request.run_id,
            sink=request.sink,
            write=request.write,
        )

    @app.post("/live-selection-requirements")
    def live_selection_requirements(request: LiveSelectionRequirementsRequest = Body(...)) -> dict[str, object]:
        return service().live_selection_requirements(
            run_id=request.run_id,
            sink=request.sink,
            write=request.write,
        )

    @app.post("/operator-selected-live-smoke-preflight")
    def operator_selected_live_smoke_preflight(
        request: OperatorSelectedLiveSmokePreflightRequest = Body(...),
    ) -> dict[str, object]:
        return service().operator_selected_live_smoke_preflight(
            run_id=request.run_id,
            sink=request.sink,
            write=request.write,
        )

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

    @app.get(PILOT_READINESS_API_PATH)
    def get_run_pilot_readiness(run_id: str) -> dict[str, object]:
        return service().pilot_readiness_report(run_id)

    @app.get("/runs/{run_id}/dry-run-closeout")
    def get_run_dry_run_closeout(run_id: str, write: bool = True) -> dict[str, object]:
        return service().dry_run_closeout(run_id, write=write)

    @app.get("/runs/{run_id}/dry-run-review-handoff")
    def get_run_dry_run_review_handoff(run_id: str, write: bool = True) -> dict[str, object]:
        return service().dry_run_review_handoff(run_id, write=write)

    @app.get("/runs/{run_id}/dry-run-safe-loop")
    def get_run_dry_run_safe_loop(run_id: str, limit: int = 5, write: bool = True) -> dict[str, object]:
        return service().dry_run_safe_loop(run_id, limit=limit, write=write)

    @app.get(REVIEW_ROUTE_READINESS_API_PATH)
    def get_run_review_route_readiness(run_id: str, write: bool = True) -> dict[str, object]:
        return service().review_route_readiness(run_id, write=write)

    @app.post(LOOKUP_SELECTION_PACKET_API_PATH)
    def create_run_lookup_selection_packet(
        run_id: str,
        request: LookupSelectionPacketRequest = Body(...),
    ) -> dict[str, object]:
        return service().lookup_selection_packet(
            run_id,
            operator=request.operator,
            sink=request.sink,
            write=request.write,
        )

    @app.post("/runs/{run_id}/close-lookup-prerequisites")
    def create_run_close_lookup_prerequisites(
        run_id: str,
        request: CloseLookupPrerequisitesRequest = Body(...),
    ) -> dict[str, object]:
        return service().close_lookup_prerequisites(
            run_id,
            operator=request.operator,
            sink=request.sink,
            limit=request.limit,
            write=request.write,
        )

    @app.get("/runs/{run_id}/live-pilot-status")
    def get_run_live_pilot_status(run_id: str, write: bool = True) -> dict[str, object]:
        return service().live_pilot_status(run_id=run_id, write=write)

    @app.get("/runs/{run_id}/live-pilot-handoff")
    def get_run_live_pilot_handoff(run_id: str, write: bool = True) -> dict[str, object]:
        return service().live_pilot_handoff(run_id=run_id, write=write)

    @app.get("/runs/{run_id}/live-pilot-approval-packet")
    def get_run_live_pilot_approval_packet(run_id: str, job_id: str | None = None) -> dict[str, object]:
        return service().live_pilot_approval_packet(run_id=run_id, job_id=job_id)

    @app.post(SELECTED_TARGET_APPROVAL_BOUNDARY_API_PATH)
    def create_run_selected_target_approval_boundary(
        run_id: str,
        request: SelectedTargetApprovalBoundaryRequest,
    ) -> dict[str, object]:
        return service().selected_target_approval_boundary(
            run_id,
            operator=request.operator,
            sink=request.sink,
            job_id=request.job_id,
            response=request.response,
            write=request.write,
        )

    @app.post(SELECTED_TARGET_COMMAND_COPY_PACKET_API_PATH)
    def create_run_selected_target_command_copy_packet(
        run_id: str,
        request: SelectedTargetCommandCopyPacketRequest,
    ) -> dict[str, object]:
        return service().selected_target_command_copy_packet(
            run_id,
            operator=request.operator,
            response=request.response,
            acknowledgement=request.acknowledgement,
            sink=request.sink,
            job_id=request.job_id,
        )

    @app.post("/runs/{run_id}/live-pilot-operator-response-validation")
    def validate_run_live_pilot_operator_response(
        run_id: str,
        request: LivePilotOperatorResponseValidationRequest,
    ) -> dict[str, object]:
        return service().validate_live_pilot_operator_response(run_id=run_id, response=request.response)

    @app.post("/runs/{run_id}/selected-live-target-preflight")
    def preflight_run_selected_live_target(
        run_id: str,
        request: SelectedLiveTargetPreflightRequest,
    ) -> dict[str, object]:
        return service().selected_live_target_preflight(run_id=run_id, response=request.response)

    @app.post("/runs/{run_id}/selected-live-target-preview")
    def preview_run_selected_live_target(
        run_id: str,
        request: SelectedLiveTargetPreflightRequest,
    ) -> dict[str, object]:
        return service().selected_live_target_artifact_preview(run_id=run_id, response=request.response)

    @app.post("/runs/{run_id}/selected-live-target-from-response")
    def create_run_selected_live_target_from_response(
        run_id: str,
        request: SelectedLiveTargetFromResponseRequest,
    ) -> dict[str, object]:
        return service().selected_live_target_from_response(
            run_id=run_id,
            response=request.response,
            write_selected_target=request.write_selected_target,
            reason=request.reason,
        )

    @app.post("/runs/{run_id}/selected-live-target-handoff-from-response")
    def create_run_selected_live_target_handoff_from_response(
        run_id: str,
        request: SelectedLiveTargetHandoffFromResponseRequest,
    ) -> dict[str, object]:
        return service().selected_live_target_handoff_from_response(
            run_id=run_id,
            response=request.response,
            write_audit=request.write_audit,
        )

    @app.post("/runs/{run_id}/lookup-smoke-handoff-from-response")
    def create_run_lookup_smoke_handoff_from_response(
        run_id: str,
        request: LookupSmokeHandoffFromResponseRequest,
    ) -> dict[str, object]:
        return service().lookup_smoke_handoff_from_response(
            run_id=run_id,
            response=request.response,
            write_handoff=request.write_handoff,
        )

    @app.post("/runs/{run_id}/selected-lookup-smoke-execution-packet-from-response")
    def create_run_selected_lookup_smoke_execution_packet_from_response(
        run_id: str,
        request: SelectedLookupSmokeExecutionPacketFromResponseRequest,
    ) -> dict[str, object]:
        return service().selected_lookup_smoke_execution_packet_from_response(
            run_id=run_id,
            response=request.response,
            execute_selected_lookup_smoke=request.execute_selected_lookup_smoke,
        )

    @app.post("/runs/{run_id}/selected-write-pilot-execution-packet-from-response")
    def create_run_selected_write_pilot_execution_packet_from_response(
        run_id: str,
        request: SelectedWritePilotExecutionPacketFromResponseRequest,
    ) -> dict[str, object]:
        return service().selected_write_pilot_execution_packet_from_response(
            run_id=run_id,
            response=request.response,
            execute_write_pilot=request.execute_write_pilot,
        )

    @app.post("/runs/{run_id}/selected-readback-pilot-execution-packet-from-response")
    def create_run_selected_readback_pilot_execution_packet_from_response(
        run_id: str,
        request: SelectedReadbackPilotExecutionPacketFromResponseRequest,
    ) -> dict[str, object]:
        return service().selected_readback_pilot_execution_packet_from_response(
            run_id=run_id,
            response=request.response,
            execute_readback_pilot=request.execute_readback_pilot,
        )

    @app.post("/runs/{run_id}/live-pilot-closeout-packet-from-response")
    def create_run_live_pilot_closeout_packet_from_response(
        run_id: str,
        request: LivePilotCloseoutPacketFromResponseRequest,
    ) -> dict[str, object]:
        return service().live_pilot_closeout_packet_from_response(
            run_id=run_id,
            response=request.response,
            write_closeout=request.write_closeout,
        )

    @app.post("/runs/{run_id}/live-pilot-operator-workflow-packet-from-response")
    def create_run_live_pilot_operator_workflow_packet_from_response(
        run_id: str,
        request: LivePilotOperatorWorkflowPacketFromResponseRequest,
    ) -> dict[str, object]:
        return service().live_pilot_operator_workflow_packet_from_response(
            run_id=run_id,
            response=request.response,
        )

    @app.post("/runs/{run_id}/live-pilot-operator-rehearsal-from-response")
    def create_run_live_pilot_operator_rehearsal_from_response(
        run_id: str,
        request: LivePilotOperatorRehearsalFromResponseRequest,
    ) -> dict[str, object]:
        return service().live_pilot_operator_rehearsal_from_response(
            run_id=run_id,
            response=request.response,
        )

    @app.post("/runs/{run_id}/live-pilot-readiness-export-from-response")
    def create_run_live_pilot_readiness_export_from_response(
        run_id: str,
        request: LivePilotReadinessExportFromResponseRequest,
    ) -> dict[str, object]:
        return service().live_pilot_readiness_export_from_response(
            run_id=run_id,
            response=request.response,
            write=request.write,
        )

    @app.post("/runs/{run_id}/live-pilot-execution-checklist-from-response")
    def create_run_live_pilot_execution_checklist_from_response(
        run_id: str,
        request: LivePilotExecutionChecklistFromResponseRequest,
    ) -> dict[str, object]:
        return service().live_pilot_execution_checklist_from_response(
            run_id=run_id,
            response=request.response,
        )

    @app.post("/runs/{run_id}/live-pilot-command-copy-packet-from-response")
    def create_run_live_pilot_command_copy_packet_from_response(
        run_id: str,
        request: LivePilotCommandCopyPacketFromResponseRequest,
    ) -> dict[str, object]:
        return service().live_pilot_command_copy_packet_from_response(
            run_id=run_id,
            response=request.response,
            acknowledgement=request.acknowledgement,
        )

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

    @app.get("/reviews/children")
    def list_child_reviews(
        run_id: str | None = None,
        state: str = "needs_review",
    ) -> list[dict[str, object]]:
        return service().child_review_queue(run_id=run_id, state=state)

    @app.post("/reviews/children/{candidate_id}")
    def submit_child_review(candidate_id: str, request: ChildReviewRequest = Body(...)) -> dict[str, object]:
        return service().submit_child_review(
            run_id=request.run_id,
            candidate_id=candidate_id,
            reviewer=request.reviewer,
            action=request.action,
            field_corrections=dict(request.field_corrections),
            notes=request.notes,
        )

    @app.get("/reviews/children/route-prep")
    def list_child_route_prep(
        run_id: str | None = None,
        state: str = "approved_for_dedupe",
    ) -> list[dict[str, object]]:
        return service().child_route_prep_queue(run_id=run_id, state=state)

    @app.post("/reviews/children/{candidate_id}/route-prep")
    def prepare_child_route(candidate_id: str, request: ChildRoutePrepRequest = Body(...)) -> dict[str, object]:
        return service().prepare_child_route(
            run_id=request.run_id,
            candidate_id=candidate_id,
            dry_run=request.dry_run,
        )

    @app.post("/reviews/children/{candidate_id}/sink-lookup-result")
    def create_child_sink_lookup_result(
        candidate_id: str,
        request: ChildLookupResultRequest = Body(...),
    ) -> dict[str, object]:
        return service().record_child_sink_lookup_result(
            run_id=request.run_id,
            candidate_id=candidate_id,
            matches_by_sink={sink: [dict(match) for match in matches] for sink, matches in request.matches_by_sink.items()},
        )

    @app.post("/reviews/children/{candidate_id}/downstream-duplicate-assessment")
    def create_child_downstream_duplicate_assessment(
        candidate_id: str,
        request: ChildRoutePrepRequest = Body(...),
    ) -> dict[str, object]:
        return service().assess_child_downstream_duplicates(
            run_id=request.run_id,
            candidate_id=candidate_id,
        )

    @app.post("/reviews/children/{candidate_id}/duplicate-resolution")
    def create_child_duplicate_resolution(
        candidate_id: str,
        request: ChildDuplicateResolutionRequest = Body(...),
    ) -> dict[str, object]:
        return service().resolve_child_duplicate(
            run_id=request.run_id,
            candidate_id=candidate_id,
            reviewer=request.reviewer,
            decision=request.decision,
            target_identity=request.target_identity,
            reason=request.reason,
        )

    @app.post("/reviews/children/{candidate_id}/sink-plan-gate")
    def create_child_sink_plan_gate(
        candidate_id: str,
        request: ChildRoutePrepRequest = Body(...),
    ) -> dict[str, object]:
        return service().child_sink_plan_gate(
            run_id=request.run_id,
            candidate_id=candidate_id,
        )

    @app.post("/reviews/children/{candidate_id}/sink-apply-preflight")
    def create_child_sink_apply_preflight(
        candidate_id: str,
        request: ChildSinkApplyPreflightRequest = Body(...),
    ) -> dict[str, object]:
        return service().child_sink_apply_preflight(
            run_id=request.run_id,
            candidate_id=candidate_id,
            apply=request.apply,
        )

    @app.post("/reviews/children/{candidate_id}/selected-target-handoff")
    def create_child_selected_target_handoff(
        candidate_id: str,
        request: ChildSelectedTargetHandoffRequest = Body(...),
    ) -> dict[str, object]:
        return service().child_selected_target_handoff(
            run_id=request.run_id,
            candidate_id=candidate_id,
            sink=request.sink,
            operator=request.operator,
            scope=request.scope,
            reason=request.reason,
        )

    @app.post("/reviews/children/{candidate_id}/selected-target-response-validation")
    def create_child_selected_target_response_validation(
        candidate_id: str,
        request: ChildSelectedTargetResponseRequest = Body(...),
    ) -> dict[str, object]:
        return service().validate_child_selected_target_response(
            run_id=request.run_id,
            candidate_id=candidate_id,
            response=request.response,
        )

    @app.post("/reviews/children/{candidate_id}/selected-target-execution-checklist")
    def create_child_selected_target_execution_checklist(
        candidate_id: str,
        request: ChildSelectedTargetResponseRequest = Body(...),
    ) -> dict[str, object]:
        return service().child_selected_target_execution_checklist(
            run_id=request.run_id,
            candidate_id=candidate_id,
            response=request.response,
        )

    @app.post("/reviews/children/{candidate_id}/selected-target-command-copy-packet")
    def create_child_selected_target_command_copy_packet(
        candidate_id: str,
        request: ChildSelectedTargetCommandCopyRequest = Body(...),
    ) -> dict[str, object]:
        return service().child_selected_target_command_copy_packet(
            run_id=request.run_id,
            candidate_id=candidate_id,
            response=request.response,
            acknowledgement=request.acknowledgement,
        )

    @app.post("/reviews/children/{candidate_id}/selected-target-audit")
    def create_child_selected_target_audit(
        candidate_id: str,
        request: ChildSelectedTargetAuditRequest = Body(...),
    ) -> dict[str, object]:
        return service().child_selected_target_audit(
            run_id=request.run_id,
            candidate_id=candidate_id,
            sink=request.sink,
            operator=request.operator,
            scope=request.scope,
            write=request.write,
        )

    @app.post("/reviews/children/{candidate_id}/selected-target-abandonment")
    def create_child_selected_target_abandonment(
        candidate_id: str,
        request: ChildSelectedTargetAbandonmentRequest = Body(...),
    ) -> dict[str, object]:
        return service().abandon_child_selected_target(
            run_id=request.run_id,
            candidate_id=candidate_id,
            operator=request.operator,
            reason=request.reason,
        )

    @app.post("/reviews/children/{candidate_id}/selected-target-replacement-reset")
    def create_child_selected_target_replacement_reset(
        candidate_id: str,
        request: ChildSelectedTargetReplacementResetRequest = Body(...),
    ) -> dict[str, object]:
        return service().child_selected_target_replacement_reset(
            run_id=request.run_id,
            candidate_id=candidate_id,
            sink=request.sink,
            operator=request.operator,
            scope=request.scope,
            reset_by=request.reset_by,
            reason=request.reason,
        )

    @app.post("/reviews/children/{candidate_id}/replacement-handoff-refresh")
    def create_child_replacement_handoff_refresh(
        candidate_id: str,
        request: ChildReplacementHandoffRefreshRequest = Body(...),
    ) -> dict[str, object]:
        return service().refresh_child_replacement_handoff(
            run_id=request.run_id,
            candidate_id=candidate_id,
            sink=request.sink,
            operator=request.operator,
            scope=request.scope,
            reason=request.reason,
        )

    @app.post("/reviews/children/{candidate_id}/replacement-response-validation")
    def create_child_replacement_response_validation(
        candidate_id: str,
        request: ChildSelectedTargetResponseRequest = Body(...),
    ) -> dict[str, object]:
        return service().validate_child_replacement_response(
            run_id=request.run_id,
            candidate_id=candidate_id,
            response=request.response,
        )

    @app.post("/reviews/children/{candidate_id}/replacement-execution-checklist")
    def create_child_replacement_execution_checklist(
        candidate_id: str,
        request: ChildSelectedTargetResponseRequest = Body(...),
    ) -> dict[str, object]:
        return service().child_replacement_execution_checklist(
            run_id=request.run_id,
            candidate_id=candidate_id,
            response=request.response,
        )

    @app.post("/reviews/children/{candidate_id}/replacement-command-copy-packet")
    def create_child_replacement_command_copy_packet(
        candidate_id: str,
        request: ChildSelectedTargetCommandCopyRequest = Body(...),
    ) -> dict[str, object]:
        return service().child_replacement_command_copy_packet(
            run_id=request.run_id,
            candidate_id=candidate_id,
            response=request.response,
            acknowledgement=request.acknowledgement,
        )

    @app.post("/reviews/children/{candidate_id}/replacement-closeout-status")
    def create_child_replacement_closeout_status(
        candidate_id: str,
        request: ChildRoutePrepRequest = Body(...),
    ) -> dict[str, object]:
        return service().child_replacement_closeout_status(
            run_id=request.run_id,
            candidate_id=candidate_id,
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

    @app.get("/actions/next")
    def get_next_actions(run_id: str | None = None, limit: int = 20) -> dict[str, object]:
        return service().next_actions(run_id=run_id, limit=limit)

    @app.post("/actions/next")
    def post_next_actions(request: NextActionsRequest = Body(default=NextActionsRequest())) -> dict[str, object]:
        return service().next_actions(run_id=request.run_id, limit=request.limit)

    @app.post("/contacts/{contact_id}/review-recommendations")
    def create_contact_review_recommendation(
        contact_id: str,
        request: ContactReviewRecommendationRequest = Body(...),
    ) -> dict[str, object]:
        return service().record_contact_review_recommendation(
            contact_id=contact_id,
            source=request.source,
            category=request.category,
            recommendation=request.recommendation,
            rationale=request.rationale,
            confidence=request.confidence,
            evidence=dict(request.evidence),
        )

    @app.get("/contacts/review-states")
    def list_contact_review_states(
        contact_id: str | None = None,
        state: str = "all",
        limit: int = 100,
    ) -> dict[str, object]:
        return service().list_contact_review_states(contact_id=contact_id, state=state, limit=limit)

    @app.post("/contacts/review-states/{review_state_id}/decision")
    def decide_contact_review_state(
        review_state_id: str,
        request: ContactReviewDecisionRequest = Body(...),
    ) -> dict[str, object]:
        return service().decide_contact_review_state(
            review_state_id=review_state_id,
            reviewer=request.reviewer,
            decision=request.decision,
            notes=request.notes,
        )

    @app.post("/contacts/review-safe-loop")
    def run_contact_review_safe_loop(
        request: ContactReviewSafeLoopRequest = Body(default=ContactReviewSafeLoopRequest()),
    ) -> dict[str, object]:
        return service().run_contact_review_safe_loop(
            limit=request.limit,
            reviewer=request.reviewer,
            apply=request.apply,
        )

    @app.post("/contacts/{contact_id}/route-selection-approval-boundary")
    def create_contact_route_selection_approval_boundary(
        contact_id: str,
        request: ContactRouteSelectionApprovalBoundaryRequest = Body(...),
    ) -> dict[str, object]:
        return service().contact_route_selection_approval_boundary(
            contact_id,
            operator=request.operator,
            sink=request.sink,
            response=request.response,
            write=request.write,
        )

    @app.post("/contacts/{contact_id}/route-selection-command-copy-packet")
    def create_contact_route_selection_command_copy_packet(
        contact_id: str,
        request: ContactRouteSelectionCommandCopyRequest = Body(...),
    ) -> dict[str, object]:
        return service().contact_route_selection_command_copy_packet(
            contact_id,
            operator=request.operator,
            response=request.response,
            acknowledgement=request.acknowledgement,
            sink=request.sink,
        )

    @app.get("/offline-pilot-gap-audit")
    def offline_pilot_gap_audit(write: bool = True) -> dict[str, object]:
        return service().offline_pilot_gap_audit(write=write)

    @app.post("/drills/multi-card-preclassification")
    def multi_card_preclassification_drill() -> dict[str, object]:
        return service().multi_card_preclassification_drill()

    @app.post("/drills/watch-dry-run-selection")
    def watch_dry_run_selection_drill() -> dict[str, object]:
        return service().watch_dry_run_selection_drill()

    @app.post("/drills/watch-dry-run-execution")
    def watch_dry_run_execution_drill() -> dict[str, object]:
        return service().watch_dry_run_execution_drill()

    @app.post("/drills/review-routing")
    def review_routing_drill() -> dict[str, object]:
        return service().review_routing_drill()

    @app.post("/drills/live-pilot-rehearsal")
    def live_pilot_rehearsal_drill() -> dict[str, object]:
        return service().live_pilot_rehearsal_drill()

    @app.get(OPERATOR_LIVE_PILOT_READINESS_API_PATH)
    def get_operator_live_pilot_readiness_packet(
        run_id: str,
        sink: str | None = None,
        write: bool = True,
    ) -> dict[str, object]:
        return service().operator_live_pilot_readiness_packet(
            run_id=run_id,
            sink=sink,
            write=write,
        )

    @app.post(OPERATOR_LIVE_PILOT_READINESS_API_PATH)
    def post_operator_live_pilot_readiness_packet(
        request: OperatorLivePilotReadinessPacketRequest = Body(...),
    ) -> dict[str, object]:
        return service().operator_live_pilot_readiness_packet(
            run_id=request.run_id,
            sink=request.sink,
            write=request.write,
        )

    @app.post("/drills/child-replacement-readiness")
    def child_replacement_readiness_drill() -> dict[str, object]:
        return service().child_replacement_readiness_drill()

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
            provider=request.provider,
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

    @app.post("/jobs/{job_id}/sink-lookup-smoke-handoff")
    def create_sink_lookup_smoke_handoff(
        job_id: str,
        request: SinkLookupSmokeHandoffRequest = Body(...),
    ) -> dict[str, object]:
        return service().build_sink_lookup_smoke_handoff_for_job(
            job_id=job_id,
            run_id=request.run_id,
            sink=request.sink,
            approved_by=request.approved_by,
        )

    @app.post("/jobs/{job_id}/live-selection-packet")
    def create_live_selection_packet(
        job_id: str,
        request: LiveSelectionPacketRequest = Body(...),
    ) -> dict[str, object]:
        return service().live_selection_packet(
            job_id=job_id,
            run_id=request.run_id,
            sink=request.sink,
            operator=request.operator,
            scope=request.scope,
            reason=request.reason,
            write=request.write,
        )

    @app.post("/jobs/{job_id}/selected-live-target")
    def create_selected_live_target(
        job_id: str,
        request: SelectedLiveTargetRequest = Body(...),
    ) -> dict[str, object]:
        return service().select_live_target_for_job(
            job_id=job_id,
            run_id=request.run_id,
            sink=request.sink,
            operator=request.operator,
            scope=request.scope,
            reason=request.reason,
            safety_confirmation=request.safety_confirmation,
        )

    @app.post("/jobs/{job_id}/selected-live-target-audit")
    def create_selected_live_target_audit(
        job_id: str,
        request: SelectedLiveTargetAuditRequest = Body(...),
    ) -> dict[str, object]:
        return service().selected_live_target_audit(
            job_id=job_id,
            run_id=request.run_id,
            scope=request.scope,
            write=request.write,
        )

    @app.post("/jobs/{job_id}/live-pilot-abandonment")
    def create_live_pilot_abandonment(
        job_id: str,
        request: LivePilotAbandonRequest = Body(...),
    ) -> dict[str, object]:
        return service().live_pilot_abandon_for_job(
            job_id=job_id,
            run_id=request.run_id,
            operator=request.operator,
            reason=request.reason,
        )

    @app.post("/jobs/{job_id}/selected-lookup-smoke")
    def execute_selected_lookup_smoke(
        job_id: str,
        request: SelectedLookupSmokeRequest = Body(...),
    ) -> dict[str, object]:
        return service().execute_selected_lookup_smoke_for_job(
            job_id=job_id,
            run_id=request.run_id,
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

    @app.post("/jobs/{job_id}/live-pilot-closeout")
    def create_live_pilot_closeout(
        job_id: str,
        request: LivePilotCloseoutRequest = Body(...),
    ) -> dict[str, object]:
        return service().build_live_pilot_closeout_for_job(
            job_id=job_id,
            run_id=request.run_id,
            write=request.write,
        )

    @app.post("/jobs/{job_id}/downstream-duplicate-assessment")
    def create_downstream_duplicate_assessment(job_id: str, run_id: str) -> dict[str, object]:
        return service().assess_downstream_duplicates_for_job(job_id=job_id, run_id=run_id)

    @app.post("/enrichment/check")
    def enrichment_check(request: EnrichmentRequest = Body(default=EnrichmentRequest(run_id=""))) -> dict[str, object]:
        return service().enrichment_readiness(
            mode=request.mode,
            allow_paid_enrichment=request.allow_paid_enrichment,
            provider=request.provider,
        )

    @app.get("/watch/status")
    def watch_status() -> dict[str, object]:
        return service().watch_status()

    @app.post("/watch/backlog-preflight")
    def watch_backlog_preflight(
        request: WatchBacklogPreflightRequest = Body(default=WatchBacklogPreflightRequest()),
    ) -> dict[str, object]:
        return service().watch_backlog_preflight(write=request.write)

    @app.post("/watch/dry-run-selection-handoff")
    def watch_dry_run_selection_handoff(
        request: WatchDryRunSelectionHandoffRequest = Body(default=WatchDryRunSelectionHandoffRequest()),
    ) -> dict[str, object]:
        return service().watch_dry_run_selection_handoff(write=request.write)

    @app.post("/watch/dry-run-validate-response")
    def watch_dry_run_validate_response(
        request: WatchDryRunOperatorResponseRequest = Body(...),
    ) -> dict[str, object]:
        return service().validate_watch_dry_run_operator_response(response=request.response)

    @app.post("/watch/dry-run-command-copy-packet")
    def watch_dry_run_command_copy_packet(
        request: WatchDryRunOperatorResponseRequest = Body(...),
    ) -> dict[str, object]:
        return service().watch_dry_run_command_copy_packet(
            response=request.response,
            acknowledgement=request.acknowledgement,
        )

    @app.post("/watch/dry-run-readiness")
    def watch_dry_run_readiness(
        request: WatchBacklogPreflightRequest = Body(default=WatchBacklogPreflightRequest()),
    ) -> dict[str, object]:
        return service().watch_dry_run_readiness(write=request.write)

    @app.post("/watch/dry-run")
    def watch_dry_run() -> dict[str, object]:
        return service().watch_dry_run_harness()

    return app
