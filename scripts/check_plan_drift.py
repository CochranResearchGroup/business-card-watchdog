#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LATEST_REFACTOR_PLAN = "docs/dev/plans/0058-2026-06-19-goal-compatible-monolith-refactoring.md"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"drift guard failed: {message}")


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> int:
    roadmap = read("ROADMAP.md")
    runbook = read("RUNBOOK.md")
    plan = read(LATEST_REFACTOR_PLAN)

    require((ROOT / LATEST_REFACTOR_PLAN).exists(), f"{LATEST_REFACTOR_PLAN} is missing")
    require(
        f"Latest completed refactor plan: `{LATEST_REFACTOR_PLAN}`" in roadmap,
        "ROADMAP latest refactor plan is stale",
    )
    require("State: CLOSED" in plan, "Plan 0058 is not closed")
    require("Pending." not in plan, "Plan 0058 validation is still pending")
    require("## Turn 266 | 2026-06-19" in runbook, "RUNBOOK Turn 266 closeout is missing")
    require(
        "Executed Plan 0058 with Slices 0058-A through 0058-C" in runbook,
        "RUNBOOK Plan 0058 closeout is missing",
    )
    require("codegraph sync && codegraph status" in runbook, "RUNBOOK does not record CodeGraph validation")
    require(
        "This was a behavior-preserving pilot-readiness extraction" in runbook,
        "RUNBOOK safety boundary is missing",
    )
    print("plan drift guard passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
