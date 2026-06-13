from __future__ import annotations

import argparse
import json
from pathlib import Path

from .api import create_app
from .config import load_config, write_default_config
from .mcp import manifest_json
from .service import BusinessCardService
from .service_ops import install_user_service, service_status, uninstall_user_service
from .watcher import PollingWatcher


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bcw")
    parser.add_argument("--config", type=Path, default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-config")

    status = sub.add_parser("status")
    status.add_argument("--json", action="store_true")

    doctor = sub.add_parser("doctor")
    doctor.add_argument("--json", action="store_true")

    process = sub.add_parser("process")
    process.add_argument("source")
    process.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True)
    process.add_argument("--workers", type=int, default=2)

    runs = sub.add_parser("runs")
    runs_sub = runs.add_subparsers(dest="runs_command", required=True)
    runs_list = runs_sub.add_parser("list")
    runs_list.add_argument("--json", action="store_true")
    runs_show = runs_sub.add_parser("show")
    runs_show.add_argument("run_id")
    runs_show.add_argument("--json", action="store_true")
    runs_summary = runs_sub.add_parser("summary")
    runs_summary.add_argument("run_id")
    runs_summary.add_argument("--json", action="store_true")

    jobs = sub.add_parser("jobs")
    jobs_sub = jobs.add_subparsers(dest="jobs_command", required=True)
    jobs_list = jobs_sub.add_parser("list")
    jobs_list.add_argument("--run-id", default=None)
    jobs_list.add_argument("--json", action="store_true")
    jobs_show = jobs_sub.add_parser("show")
    jobs_show.add_argument("job_id")
    jobs_show.add_argument("--run-id", default=None)
    jobs_show.add_argument("--json", action="store_true")
    jobs_review = jobs_sub.add_parser("review")
    jobs_review.add_argument("job_id")
    jobs_review.add_argument("--run-id", required=True)
    jobs_review.add_argument("--reviewer", default="operator")
    jobs_review.add_argument(
        "--action",
        choices=["approve_for_routing", "keep_needs_review"],
        default="keep_needs_review",
    )
    jobs_review.add_argument("--field-corrections-json", default="{}")
    jobs_review.add_argument("--crop-selection-json", default="{}")
    jobs_review.add_argument("--notes", default="")
    jobs_review.add_argument("--json", action="store_true")

    reviews = sub.add_parser("reviews")
    reviews_sub = reviews.add_subparsers(dest="reviews_command", required=True)
    reviews_list = reviews_sub.add_parser("list")
    reviews_list.add_argument("--run-id", default=None)
    reviews_list.add_argument("--state", default="needs_review")
    reviews_list.add_argument("--json", action="store_true")

    sinks = sub.add_parser("sinks")
    sinks_sub = sinks.add_subparsers(dest="sinks_command", required=True)
    sinks_check = sinks_sub.add_parser("check")
    sinks_check.add_argument("--json", action="store_true")
    sinks_plan = sinks_sub.add_parser("plan")
    sinks_plan.add_argument("job_id")
    sinks_plan.add_argument("--run-id", required=True)
    sinks_plan.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True)
    sinks_plan.add_argument("--json", action="store_true")

    enrichment = sub.add_parser("enrichment")
    enrichment_sub = enrichment.add_subparsers(dest="enrichment_command", required=True)
    enrichment_check = enrichment_sub.add_parser("check")
    enrichment_check.add_argument("--mode", choices=["none", "public_web", "api", "all"], default=None)
    enrichment_check.add_argument("--allow-paid-enrichment", action="store_true")
    enrichment_check.add_argument("--json", action="store_true")
    enrichment_request = enrichment_sub.add_parser("request")
    enrichment_request.add_argument("job_id")
    enrichment_request.add_argument("--run-id", required=True)
    enrichment_request.add_argument("--mode", choices=["public_web", "api", "all"], default="public_web")
    enrichment_request.add_argument("--requested-by", default="operator")
    enrichment_request.add_argument("--allow-paid-enrichment", action="store_true")
    enrichment_request.add_argument("--public-web-results-json", default="[]")
    enrichment_request.add_argument("--json", action="store_true")

    watch = sub.add_parser("watch")
    watch.add_argument("--once", action="store_true")
    watch.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True)
    watch.add_argument("--interval-seconds", type=float, default=10.0)
    watch.add_argument("--settle-seconds", type=float, default=None)

    watch_status = sub.add_parser("watch-status")
    watch_status.add_argument("--json", action="store_true")

    watch_reset = sub.add_parser("watch-reset")
    watch_reset.add_argument("--yes", action="store_true")

    api = sub.add_parser("api")
    api.add_argument("--host", default="127.0.0.1")
    api.add_argument("--port", type=int, default=8787)

    service = sub.add_parser("service")
    service_sub = service.add_subparsers(dest="service_command", required=True)
    service_status_parser = service_sub.add_parser("status")
    service_status_parser.add_argument("--json", action="store_true")
    service_install = service_sub.add_parser("install")
    service_install.add_argument("--json", action="store_true")
    service_uninstall = service_sub.add_parser("uninstall")
    service_uninstall.add_argument("--json", action="store_true")

    sub.add_parser("mcp-manifest")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "init-config":
        print(write_default_config(args.config))
        return 0

    config = load_config(args.config)
    service = BusinessCardService(config)

    if args.command == "status":
        payload = service.status()
        print(json.dumps(payload, indent=2) if args.json else payload)
        return 0 if payload["skill_ready"] else 2

    if args.command == "doctor":
        payload = service.doctor()
        print(json.dumps(payload, indent=2) if args.json else payload)
        return 0 if payload["ok"] else 2

    if args.command == "process":
        run = service.process_source(
            args.source,
            dry_run=args.dry_run,
            workers=args.workers,
        )
        print(json.dumps(run, indent=2))
        return 0

    if args.command == "runs":
        if args.runs_command == "list":
            payload = service.list_runs()
        elif args.runs_command == "summary":
            payload = service.run_summary(args.run_id)
        else:
            payload = service.get_run(args.run_id)
        print(json.dumps(payload, indent=2) if args.json else payload)
        return 0

    if args.command == "reviews":
        payload = service.review_queue(run_id=args.run_id, state=args.state)
        print(json.dumps(payload, indent=2) if args.json else payload)
        return 0

    if args.command == "jobs":
        if args.jobs_command == "list":
            payload = service.list_jobs(args.run_id)
        elif args.jobs_command == "show":
            payload = service.get_job(args.job_id, run_id=args.run_id)
        else:
            payload = service.submit_review(
                job_id=args.job_id,
                run_id=args.run_id,
                reviewer=args.reviewer,
                action=args.action,
                field_corrections=json.loads(args.field_corrections_json),
                crop_selection=json.loads(args.crop_selection_json),
                notes=args.notes,
            )
        print(json.dumps(payload, indent=2) if args.json else payload)
        return 0

    if args.command == "sinks":
        if args.sinks_command == "check":
            payload = service.sink_readiness()
        else:
            payload = service.plan_sinks_for_job(
                job_id=args.job_id,
                run_id=args.run_id,
                dry_run=args.dry_run,
            )
        print(json.dumps(payload, indent=2) if args.json else payload)
        return 0

    if args.command == "enrichment":
        if args.enrichment_command == "check":
            payload = service.enrichment_readiness(
                mode=args.mode,
                allow_paid_enrichment=args.allow_paid_enrichment,
            )
        else:
            payload = service.request_enrichment(
                job_id=args.job_id,
                run_id=args.run_id,
                mode=args.mode,
                requested_by=args.requested_by,
                allow_paid_enrichment=args.allow_paid_enrichment,
                public_web_results=json.loads(args.public_web_results_json),
            )
        print(json.dumps(payload, indent=2) if args.json else payload)
        checks = payload.get("checks") or payload.get("readiness", {}).get("checks", [])
        return 0 if all(check["status"] == "ready" for check in checks) else 2

    if args.command == "watch":
        PollingWatcher(
            config,
            interval_seconds=args.interval_seconds,
            settle_seconds=args.settle_seconds,
        ).run(
            dry_run=args.dry_run,
            once=args.once,
        )
        return 0

    if args.command == "watch-status":
        payload = service.watch_status()
        print(json.dumps(payload, indent=2) if args.json else payload)
        return 0 if payload["last_error"] is None else 2

    if args.command == "watch-reset":
        if not args.yes:
            raise SystemExit("Refusing to reset watcher state without --yes")
        print(json.dumps(service.watch_reset(), indent=2))
        return 0

    if args.command == "api":
        try:
            import uvicorn
        except ImportError as exc:
            raise SystemExit("Install with the api extra: pip install -e '.[api]'") from exc
        uvicorn.run(create_app(), host=args.host, port=args.port)
        return 0

    if args.command == "service":
        if args.service_command == "install":
            payload = install_user_service(config).to_dict()
        elif args.service_command == "uninstall":
            payload = uninstall_user_service().to_dict()
        else:
            payload = service_status().to_dict()
        print(json.dumps(payload, indent=2) if args.json else payload)
        return 0

    if args.command == "mcp-manifest":
        print(manifest_json(), end="")
        return 0

    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
