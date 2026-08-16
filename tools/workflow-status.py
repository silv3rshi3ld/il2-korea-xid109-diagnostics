#!/usr/bin/env python3
"""Show novice-friendly progress and select the next scientifically usable case."""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analyzer.parsers import parse_kernel_log, parse_proton_log, parse_vkd3d_log  # noqa: E402
RUN_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{6}Z-(baseline|single-queue|no-descriptor-buffer|sync)(?:-\d+)?$"
)


def read_json(path: pathlib.Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def unsafe_tree_entry(path: pathlib.Path) -> pathlib.Path | None:
    if path.is_symlink() or not path.is_dir():
        return path
    for directory, directory_names, file_names in os.walk(path, followlinks=False):
        directory_path = pathlib.Path(directory)
        for name in [*directory_names, *file_names]:
            entry = directory_path / name
            if entry.is_symlink() or not (entry.is_dir() or entry.is_file()):
                return entry
    return None


def unsafe_run(path: pathlib.Path, entry: pathlib.Path) -> dict[str, Any]:
    name_match = RUN_RE.fullmatch(path.name)
    path_case = name_match.group(1) if name_match else "unknown"
    try:
        detail = entry.relative_to(path).as_posix()
    except ValueError:
        detail = entry.name
    return {
        "name": path.name,
        "case": path_case,
        "duration": None,
        "observation_start": None,
        "observation_duration": None,
        "ready_recorded": False,
        "xid109": False,
        "unattributed_xid109": False,
        "other_xid": False,
        "device_lost": False,
        "xid_cache_consistent": False,
        "kernel_capture_complete": False,
        "complete": False,
        "recoverable": False,
        "broken": True,
        "stable_valid": False,
        "usable_failure": False,
        "review_required": True,
        "state": f"REVIEW REQUIRED — unsafe symlink or special file: {detail}",
    }


def inspect_run(path: pathlib.Path, threshold: int) -> dict[str, Any]:
    if (unsafe_entry := unsafe_tree_entry(path)) is not None:
        return unsafe_run(path, unsafe_entry)
    metadata_path = path / "metadata.json"
    metadata_malformed = False
    metadata_present = metadata_path.is_file()
    if metadata_present:
        try:
            metadata_value = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            metadata_value = {}
            metadata_malformed = True
    else:
        metadata_value = {}
    if isinstance(metadata_value, dict):
        metadata = metadata_value
    else:
        metadata = {}
        metadata_malformed = True
    name_match = RUN_RE.fullmatch(path.name)
    path_case = name_match.group(1) if name_match else "unknown"
    case_consistent = metadata.get("case") == path_case
    kernel_path = path / "kernel-full.log"
    kernel_text = (
        kernel_path.read_text(encoding="utf-8", errors="replace")
        if kernel_path.is_file()
        else ""
    )
    events = parse_kernel_log(kernel_text)
    xid_data = read_json(path / "xid-events.json", None)
    cached_events = xid_data.get("events") if isinstance(xid_data, dict) else None
    xid_cache_consistent = bool(
        isinstance(cached_events, list)
        and all(isinstance(event, dict) for event in cached_events)
        and cached_events == events
    )
    xid109_events = [event for event in events if isinstance(event, dict) and event.get("xid") == 109]
    attributed_xid109 = [
        event
        for event in xid109_events
        if str(event.get("name") or "").casefold() == "il2series.exe"
    ]
    unattributed_xid109_events = [event for event in xid109_events if event not in attributed_xid109]
    other_xid_events = [event for event in events if event.get("xid") != 109]
    xid109 = bool(attributed_xid109)
    unattributed_xid109 = bool(unattributed_xid109_events)
    unexpected_xid = bool(unattributed_xid109_events or other_xid_events)
    vkd3d_path = path / "vkd3d.log"
    vkd3d = parse_vkd3d_log(
        vkd3d_path.read_text(encoding="utf-8", errors="replace") if vkd3d_path.is_file() else ""
    )
    proton_path = path / "proton.log"
    proton = parse_proton_log(
        proton_path.read_text(encoding="utf-8", errors="replace") if proton_path.is_file() else ""
    )
    expected_logs_present = bool(
        kernel_path.is_file()
        and vkd3d_path.is_file()
        and vkd3d_path.stat().st_size
        and proton_path.is_file()
        and proton_path.stat().st_size
    )
    kernel_capture_complete = metadata.get("kernel_capture_complete") is True
    device_lost = bool(vkd3d["device_lost"] or proton["device_lost"])
    usable_regions = [
        region
        for region in vkd3d["regions"]
        if region.get("commands") or region.get("shaders")
    ]
    duration = metadata.get("duration_seconds")
    observation_start = metadata.get("observation_start_utc")
    observation_duration = metadata.get("observation_duration_seconds")
    ready_recorded = bool(
        (path / ".observation-start-recorded").is_file()
        and isinstance(observation_start, str)
        and observation_start
        and isinstance(observation_duration, int)
        and not isinstance(observation_duration, bool)
        and observation_duration >= 0
    )
    warnings_value = metadata.get("capture_warnings", [])
    warnings_valid = isinstance(warnings_value, list) and all(
        isinstance(warning, str) for warning in warnings_value
    )
    warnings = warnings_value if warnings_valid else ["metadata capture_warnings is malformed"]
    interrupted_value = metadata.get("capture_interrupted", False)
    recovered_value = metadata.get("recovered_after_interruption", False)
    metadata_fields_valid = bool(
        isinstance(metadata.get("capture_complete"), bool)
        and isinstance(metadata.get("kernel_capture_complete"), bool)
        and warnings_valid
        and isinstance(interrupted_value, bool)
        and isinstance(recovered_value, bool)
        and (
            duration is None
            or (isinstance(duration, int) and not isinstance(duration, bool) and duration >= 0)
        )
        and (
            observation_start is None
            or (isinstance(observation_start, str) and bool(observation_start))
        )
        and (
            observation_duration is None
            or (
                isinstance(observation_duration, int)
                and not isinstance(observation_duration, bool)
                and observation_duration >= 0
            )
        )
        and (
            metadata.get("proton_exit_code") is None
            or (
                isinstance(metadata.get("proton_exit_code"), int)
                and not isinstance(metadata.get("proton_exit_code"), bool)
            )
        )
    )
    complete_marker = (path / ".capture-complete").is_file()
    in_progress_marker = (path / ".capture-in-progress").is_file()
    complete = bool(
        metadata.get("capture_complete") is True
        and complete_marker
        and not in_progress_marker
        and not metadata_malformed
        and case_consistent
    )
    recoverable = bool(
        in_progress_marker
        and not complete_marker
        and not metadata_malformed
        and (not metadata_present or case_consistent)
    )
    broken = not complete and not recoverable
    interrupted = bool(interrupted_value or recovered_value)
    exit_code = metadata.get("proton_exit_code")
    completion_values_valid = bool(
        isinstance(duration, int)
        and not isinstance(duration, bool)
        and duration >= 0
        and isinstance(exit_code, int)
        and not isinstance(exit_code, bool)
    )
    stable_valid = bool(
        complete
        and not events
        and not device_lost
        and expected_logs_present
        and kernel_capture_complete
        and xid_cache_consistent
        and ready_recorded
        and metadata_fields_valid
        and completion_values_valid
        and observation_duration >= threshold
        and isinstance(exit_code, int)
        and not isinstance(exit_code, bool)
        and exit_code == 0
        and not interrupted
        and not warnings
    )
    usable_failure = bool(
        complete
        and xid109
        and vkd3d["device_lost"]
        and ready_recorded
        and vkd3d["breadcrumb_analysis_complete"]
        and usable_regions
        and not unexpected_xid
        and expected_logs_present
        and kernel_capture_complete
        and xid_cache_consistent
        and metadata_fields_valid
        and completion_values_valid
        and not interrupted
        and not warnings
    )
    review_required = bool(
        broken
        or (
            complete
            and (
                unexpected_xid
                or (xid109 and not usable_failure)
                or (device_lost and not xid109)
                or not xid_cache_consistent
                or not expected_logs_present
                or not kernel_capture_complete
                or not metadata_fields_valid
            )
        )
    )
    if recoverable:
        state = "INCOMPLETE — recover before continuing"
    elif broken:
        broken_reasons = []
        if metadata_malformed:
            broken_reasons.append("metadata is malformed")
        if metadata_present and not case_consistent:
            broken_reasons.append("metadata case disagrees with the run directory")
        if complete_marker == in_progress_marker:
            broken_reasons.append("capture marker state is inconsistent")
        state = "REVIEW REQUIRED — " + "; ".join(
            broken_reasons or ["capture markers or metadata are inconsistent"]
        )
    elif usable_failure:
        state = "COMPLETE — IL2Series.exe Xid 109 and breadcrumb region observed"
    elif review_required:
        reasons = []
        if unattributed_xid109:
            reasons.append("Xid 109 was not attributed to IL2Series.exe")
        if other_xid_events:
            reasons.append("a different NVIDIA Xid was observed")
        if interrupted:
            reasons.append("capture was interrupted/recovered")
        if warnings:
            reasons.append("capture has warnings")
        if xid109 and not vkd3d["device_lost"]:
            reasons.append("device-lost report is missing")
        if xid109 and not ready_recorded:
            reasons.append("READY was not recorded before the failure")
        if xid109 and not vkd3d["breadcrumb_analysis_complete"]:
            reasons.append("breadcrumb report did not finish")
        elif xid109 and not vkd3d["regions"]:
            reasons.append("breadcrumb crash region is missing")
        elif xid109 and not usable_regions:
            reasons.append("breadcrumb crash region has no parsed command or shader")
        if device_lost and not xid109:
            reasons.append("device loss was observed without an IL2Series.exe-attributed Xid 109")
        if not xid_cache_consistent:
            reasons.append("parsed Xid cache is missing, malformed, or inconsistent with the raw kernel log")
        if not expected_logs_present:
            reasons.append("one or more required raw logs are missing or empty")
        if not kernel_capture_complete:
            reasons.append("kernel journal collection was not verified as complete")
        if not metadata_fields_valid:
            reasons.append("metadata fields have invalid types or values")
        if xid109 and not completion_values_valid:
            reasons.append("completed-run duration or Proton exit status is missing")
        state = "REVIEW REQUIRED — " + "; ".join(reasons)
    elif stable_valid:
        state = f"COMPLETE — no Xid in {observation_duration // 60} minute(s) after READY"
    else:
        state = "INCONCLUSIVE — no Xid, but too short/interrupted/warned/failed"
    return {
        "name": path.name,
        "case": path_case,
        "duration": duration,
        "observation_start": observation_start,
        "observation_duration": observation_duration,
        "ready_recorded": ready_recorded,
        "xid109": xid109,
        "unattributed_xid109": unattributed_xid109,
        "other_xid": bool(other_xid_events),
        "device_lost": device_lost,
        "xid_cache_consistent": xid_cache_consistent,
        "kernel_capture_complete": kernel_capture_complete,
        "completion_values_valid": completion_values_valid,
        "complete": complete,
        "recoverable": recoverable,
        "broken": broken,
        "stable_valid": stable_valid,
        "usable_failure": usable_failure,
        "review_required": review_required,
        "state": state,
    }


def all_runs() -> tuple[list[dict[str, Any]], int, list[str]]:
    if RESULTS.is_symlink():
        raise SystemExit("error: results path must not be a symlink")
    policy = read_json(ROOT / "config/test-policy.json", {})
    if not isinstance(policy, dict):
        policy = {}
    try:
        threshold = int(policy.get("no_xid_observation_seconds", 600))
    except (TypeError, ValueError):
        threshold = 600
    if threshold <= 0:
        threshold = 600
    default_order = ["baseline", "single-queue", "no-descriptor-buffer", "sync"]
    order = policy.get("recommended_case_order", default_order)
    if order != default_order:
        order = default_order
    runs = [
        inspect_run(path, threshold)
        for path in sorted(RESULTS.iterdir())
        if RUN_RE.fullmatch(path.name)
    ] if RESULTS.is_dir() else []
    return runs, threshold, order


def next_action(runs: list[dict[str, Any]], order: list[str]) -> str:
    if any(run["recoverable"] for run in runs):
        return "RECOVER"
    if any(run["broken"] for run in runs):
        return "REVIEW"
    by_case = {case: [run for run in runs if run["case"] == case] for case in order}
    baseline = by_case.get("baseline", [])
    if not baseline:
        return "baseline"
    latest_baseline = baseline[-1]
    if latest_baseline["review_required"]:
        return "REVIEW"
    if latest_baseline["stable_valid"]:
        return "STOP_BASELINE_NO_XID"
    if not latest_baseline["usable_failure"]:
        return "baseline"
    for case in order[1:]:
        case_runs = by_case.get(case, [])
        if not case_runs:
            return case
        latest = case_runs[-1]
        if latest["review_required"]:
            return "REVIEW"
        if not (latest["usable_failure"] or latest["stable_valid"]):
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
        observation = (
            f"{run['observation_duration']}s"
            if isinstance(run["observation_duration"], int)
            else "not marked"
        )
        print(
            f"- {run['name']}: {run['state']} "
            f"(Proton runtime {duration}; READY observation {observation})"
        )
    print(f"\nNext workflow action: {action}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
