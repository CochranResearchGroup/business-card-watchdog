#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLAN_0056 = "docs/dev/plans/0056-2026-06-16-monolith-decomposition-drift-guard.md"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"drift guard failed: {message}")


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> int:
    roadmap = read("ROADMAP.md")
    runbook = read("RUNBOOK.md")
    plan = read(PLAN_0056)

    require((ROOT / PLAN_0056).exists(), f"{PLAN_0056} is missing")
    require(f"Latest completed refactor plan: `{PLAN_0056}`" in roadmap, "ROADMAP latest refactor plan is stale")
    require("State: CLOSED" in plan, "Plan 0056 is not closed")
    require("Pending." not in plan, "Plan 0056 validation is still pending")
    require("## Turn 262 | 2026-06-16" in runbook, "RUNBOOK Turn 262 closeout is missing")
    require("Executed Plan 0056" in runbook, "RUNBOOK does not record Plan 0056 execution")
    require("codegraph sync && codegraph status" in runbook, "RUNBOOK does not record CodeGraph validation")
    require("This was a behavior-preserving surface registry seed" in runbook, "RUNBOOK safety boundary is missing")
    print("plan drift guard passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
