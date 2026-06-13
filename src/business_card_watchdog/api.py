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
        notes: str = ""

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

    @app.get("/runs/{run_id}/jobs")
    def list_run_jobs(run_id: str) -> list[dict[str, object]]:
        return service().list_jobs(run_id)

    @app.get("/reviews")
    def list_reviews(run_id: str | None = None, state: str = "needs_review") -> list[dict[str, object]]:
        return service().review_queue(run_id=run_id, state=state)

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
            notes=request.notes,
        )

    @app.post("/sinks/check")
    def sink_check() -> dict[str, object]:
        return service().sink_readiness()

    @app.get("/watch/status")
    def watch_status() -> dict[str, object]:
        return service().watch_status()

    return app
