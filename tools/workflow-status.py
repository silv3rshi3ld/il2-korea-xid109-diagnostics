#!/usr/bin/env python3
"""Show novice-friendly progress and select the next scientifically usable case."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analyzer.parsers import parse_vkd3d_log  # noqa: E402
RUN_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{6}Z-(baseline|single-queue|no-descriptor-buffer|sync)(?:-\d+)?$"
)


def read_json(path: pathlib.Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def inspect_run(path: pathlib.Path, threshold: int) -> dict[str, Any]:
    metadata = read_json(path / "metadata.json", {})
    xid_data = read_json(path / "xid-events.json", {"events": []})
    xid109_events = [event for event in xid_data.get("events", []) if event.get("xid") == 109]
    xid109 = any(str(event.get("name") or "").casefold() == "il2series.exe" for event in xid109_events)
    unattributed_xid109 = bool(xid109_events) and not xid109
    vkd3d_path = path / "vkd3d.log"
    vkd3d = parse_vkd3d_log(
        vkd3d_path.read_text(encoding="utf-8", errors="replace") if vkd3d_path.is_file() else ""
    )
    duration = metadata.get("duration_seconds")
    warnings = metadata.get("capture_warnings") or []
    complete = bool(metadata.get("capture_complete")) and (path / ".capture-complete").is_file()
    interrupted = bool(
        metadata.get("capture_interrupted") or metadata.get("recovered_after_interruption")
    )
    exit_code = metadata.get("proton_exit_code")
    stable_valid = bool(
        complete
        and not xid109
        and isinstance(duration, int)
        and duration >= threshold
        and exit_code == 0
        and not interrupted
        and not warnings
    )
    usable_failure = bool(
        complete
        and xid109
        and vkd3d["device_lost"]
        and vkd3d["regions"]
        and not interrupted
        and not warnings
    )
    review_required = bool(
        complete and (unattributed_xid109 or (xid109 and not usable_failure))
    )
    if not complete:
        state = "INCOMPLETE — recover before continuing"
    elif usable_failure:
        state = "COMPLETE — IL2Series.exe Xid 109 and breadcrumb region observed"
    elif review_required:
        reasons = []
        if unattributed_xid109:
            reasons.append("Xid 109 was not attributed to IL2Series.exe")
        if interrupted:
            reasons.append("capture was interrupted/recovered")
        if warnings:
            reasons.append("capture has warnings")
        if xid109 and not vkd3d["device_lost"]:
            reasons.append("device-lost report is missing")
        if xid109 and not vkd3d["regions"]:
            reasons.append("breadcrumb crash region is missing")
        state = "REVIEW REQUIRED — " + "; ".join(reasons)
    elif stable_valid:
        state = f"COMPLETE — no Xid in {duration // 60} minute(s)"
    else:
        state = "INCONCLUSIVE — no Xid, but too short/interrupted/warned/failed"
    return {
        "name": path.name,
        "case": metadata.get("case", "unknown"),
        "duration": duration,
        "xid109": xid109,
        "unattributed_xid109": unattributed_xid109,
        "complete": complete,
        "stable_valid": stable_valid,
        "usable_failure": usable_failure,
        "review_required": review_required,
        "state": state,
    }


def all_runs() -> tuple[list[dict[str, Any]], int, list[str]]:
    policy = read_json(ROOT / "config/test-policy.json", {})
    threshold = int(policy.get("no_xid_observation_seconds", 600))
    order = policy.get(
        "recommended_case_order",
        ["baseline", "single-queue", "no-descriptor-buffer", "sync"],
    )
    runs = [
        inspect_run(path, threshold)
        for path in sorted(RESULTS.iterdir())
        if path.is_dir() and RUN_RE.match(path.name)
    ] if RESULTS.is_dir() else []
    return runs, threshold, order


def next_action(runs: list[dict[str, Any]], order: list[str]) -> str:
    if any(not run["complete"] for run in runs):
        return "RECOVER"
    by_case = {case: [run for run in runs if run["case"] == case] for case in order}
    baseline = by_case.get("baseline", [])
    if not any(run["usable_failure"] or run["stable_valid"] for run in baseline):
        if any(run["review_required"] for run in baseline):
            return "REVIEW"
        return "baseline"
    if any(run["stable_valid"] for run in baseline) and not any(
        run["usable_failure"] for run in baseline
    ):
        return "STOP_BASELINE_NO_XID"
    for case in order[1:]:
        case_runs = by_case.get(case, [])
        if not any(run["usable_failure"] or run["stable_valid"] for run in case_runs):
            if any(run["review_required"] for run in case_runs):
                return "REVIEW"
            return case
    return "COMPLETE"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--next", action="store_true", help="print only the next workflow token")
    args = parser.parse_args()
    runs, threshold, order = all_runs()
    action = next_action(runs, order)
    if args.next:
        print(action)
        return 0

    print("IL-2 Korea diagnostic progress")
    print(f"A no-Xid result counts only after {threshold // 60} minutes and a clean capture.\n")
    if not runs:
        print("No game runs have been captured yet.")
    for run in runs:
        duration = f"{run['duration']}s" if isinstance(run["duration"], int) else "unknown"
        print(f"- {run['name']}: {run['state']} (duration {duration})")
    print(f"\nNext workflow action: {action}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
