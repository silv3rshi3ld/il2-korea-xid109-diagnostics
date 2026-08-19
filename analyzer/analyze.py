#!/usr/bin/env python3
"""Compare controlled IL-2 Korea Xid 109 diagnostic runs."""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
RESULTS_ROOT = REPO_ROOT / "results"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from analyzer.parsers import (  # noqa: E402
    parse_descriptor_qa_faults,
    parse_kernel_log,
    parse_proton_log,
    parse_vkd3d_log,
)


CASES = (
    "baseline",
    "descriptor-qa",
    "descriptor-heap",
    "single-queue",
    "no-descriptor-buffer",
    "sync",
)
RUN_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{6}Z-(" + "|".join(CASES) + r")(?:-\d+)?$"
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SHADER_HASH_RE = re.compile(r"^[0-9a-f]{8,16}$")
STAGING_RE = re.compile(r"^\.culprit-candidate-building-\d+$")
CANDIDATE_MARKER = "generated; safe for analyzer-owned files only\n"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def read_json(path: pathlib.Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def validate_run_tree(path: pathlib.Path) -> None:
    if path.is_symlink() or not path.is_dir():
        raise RuntimeError(f"unsafe run path: {path}")
    for directory, directory_names, file_names in os.walk(path, followlinks=False):
        directory_path = pathlib.Path(directory)
        for name in [*directory_names, *file_names]:
            entry = directory_path / name
            if entry.is_symlink() or not (entry.is_dir() or entry.is_file()):
                raise RuntimeError(f"unsafe symlink or special file in run: {entry}")


def atomic_text(path: pathlib.Path, value: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)


def atomic_json(path: pathlib.Path, value: Any) -> None:
    atomic_text(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def negative_observation_threshold() -> int:
    policy = read_json(REPO_ROOT / "config/test-policy.json", {})
    if not isinstance(policy, dict):
        return 600
    try:
        threshold = int(policy.get("no_xid_observation_seconds", 600))
    except (TypeError, ValueError):
        return 600
    return threshold if threshold > 0 else 600


def region_summary(region: dict[str, Any]) -> dict[str, Any]:
    checkpoint = region.get("checkpoint") or {}
    return {
        "queue": region.get("queue"),
        "bottom_context": checkpoint.get("bottom_context"),
        "top_context": checkpoint.get("top_context"),
        "last_completed": checkpoint.get("bottom_marker"),
        "top_progress": checkpoint.get("top_marker"),
        "commands": region.get("commands", []),
        "shaders": [item["hash"] for item in region.get("shaders", [])],
        "events": region.get("events", []),
        "fingerprint": region.get("fingerprint"),
    }


def descriptor_fault_signature(fault: dict[str, Any]) -> str:
    payload = {
        key: value
        for key, value in fault.items()
        if key not in {"start_line", "end_line", "source", "shader_dump_files"}
    }
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def collect_descriptor_faults(
    descriptor_qa_text: str,
    vkd3d_faults: list[dict[str, Any]],
    shader_manifest: Any,
) -> list[dict[str, Any]]:
    faults: list[dict[str, Any]] = []
    seen: set[str] = set()
    sources = (
        ("descriptor-qa.log", parse_descriptor_qa_faults(descriptor_qa_text)),
        ("vkd3d.log", vkd3d_faults),
    )
    shader_entries = shader_manifest.get("shaders", []) if isinstance(shader_manifest, dict) else []
    for source, parsed in sources:
        for parsed_fault in parsed:
            signature = descriptor_fault_signature(parsed_fault)
            if signature in seen:
                continue
            fault = dict(parsed_fault)
            fault["source"] = source
            shader_hash = str(fault.get("shader_hash") or "").lower().zfill(16)
            fault["shader_dump_files"] = sorted(
                {
                    entry["file"]
                    for entry in shader_entries
                    if isinstance(entry, dict)
                    and isinstance(entry.get("file"), str)
                    and isinstance(entry.get("vkd3d_hash"), str)
                    and entry["vkd3d_hash"].lower().zfill(16) == shader_hash
                }
            )
            faults.append(fault)
            seen.add(signature)
    return faults


def summarize_run(run_dir: pathlib.Path) -> dict[str, Any]:
    analysis_warnings: list[str] = []
    metadata_path = run_dir / "metadata.json"
    try:
        metadata_value = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        metadata_value = {}
        analysis_warnings.append("metadata.json is missing or malformed")
    if isinstance(metadata_value, dict):
        metadata = metadata_value
    else:
        metadata = {}
        analysis_warnings.append("metadata.json is not a JSON object")
    name_match = RUN_RE.fullmatch(run_dir.name)
    path_case = name_match.group(1) if name_match else "unknown"
    if metadata.get("case") != path_case:
        analysis_warnings.append("metadata case disagrees with the run directory")

    kernel_text = read_text(run_dir / "kernel-full.log")
    events = parse_kernel_log(kernel_text)
    xid_cache_path = run_dir / "xid-events.json"
    xid_cache_consistent: bool | None = None
    if xid_cache_path.is_file():
        xid_data = read_json(xid_cache_path, None)
        cached_events = xid_data.get("events") if isinstance(xid_data, dict) else None
        if not isinstance(cached_events, list) or not all(
            isinstance(event, dict) for event in cached_events
        ):
            xid_cache_consistent = False
            analysis_warnings.append("xid-events.json is malformed; reparsed kernel-full.log")
        elif cached_events != events:
            xid_cache_consistent = False
            analysis_warnings.append(
                "xid-events.json disagrees with kernel-full.log; raw kernel log was authoritative"
            )
        else:
            xid_cache_consistent = True
    else:
        xid_cache_consistent = False
        analysis_warnings.append("xid-events.json is missing")
    all_xid109 = [event for event in events if event.get("xid") == 109]
    xid109 = [
        event
        for event in all_xid109
        if str(event.get("name") or "").casefold() == "il2series.exe"
    ]
    unattributed_xid109 = [event for event in all_xid109 if event not in xid109]
    other_xid_events = [event for event in events if event not in xid109]
    if other_xid_events:
        analysis_warnings.append(
            f"kernel-full.log contains {len(other_xid_events)} non-target NVIDIA Xid event(s)"
        )
    vkd3d_text = read_text(run_dir / "vkd3d.log")
    descriptor_qa_path = run_dir / "descriptor-qa.log"
    descriptor_qa_text = read_text(descriptor_qa_path)
    proton_text = read_text(run_dir / "proton.log")
    empty_raw_logs = [
        name
        for name, text in (
            ("vkd3d.log", vkd3d_text),
            ("proton.log", proton_text),
        )
        if not text.strip()
    ]
    if empty_raw_logs:
        analysis_warnings.append(
            "required raw evidence is missing or empty: " + ", ".join(empty_raw_logs)
        )
    kernel_capture_complete = metadata.get("kernel_capture_complete") is True
    if not (run_dir / "kernel-full.log").is_file() or not kernel_capture_complete:
        analysis_warnings.append("kernel journal collection was not verified as complete")
    vkd3d = parse_vkd3d_log(vkd3d_text)
    proton = parse_proton_log(proton_text)
    shader_manifest = read_json(run_dir / "shader-manifest.json", {})
    descriptor_faults = collect_descriptor_faults(
        descriptor_qa_text,
        vkd3d["descriptor_qa_faults"],
        shader_manifest,
    )
    descriptor_qa_log_present = descriptor_qa_path.is_file() and bool(descriptor_qa_text.strip())
    if path_case == "descriptor-qa" and not descriptor_qa_log_present:
        analysis_warnings.append("descriptor-qa.log is missing or empty for descriptor-qa case")
    regions = vkd3d["regions"]
    primary = regions[0] if regions else None
    device_lost = bool(vkd3d["device_lost"] or proton["device_lost"])
    first_lost = vkd3d["first_device_lost"] or proton["first"]
    duration = metadata.get("duration_seconds")
    observation_start = metadata.get("observation_start_utc")
    observation_duration = metadata.get("observation_duration_seconds")
    if not isinstance(duration, int) or isinstance(duration, bool) or duration < 0:
        analysis_warnings.append("metadata Proton runtime duration is malformed")
    exit_code = metadata.get("proton_exit_code")
    if not isinstance(exit_code, int) or isinstance(exit_code, bool):
        analysis_warnings.append("metadata Proton exit code is malformed")
    if not isinstance(metadata.get("kernel_capture_complete"), bool):
        analysis_warnings.append("metadata kernel capture status is malformed")
    ready_recorded = bool(
        (run_dir / ".observation-start-recorded").is_file()
        and isinstance(observation_start, str)
        and observation_start
        and isinstance(observation_duration, int)
        and not isinstance(observation_duration, bool)
        and observation_duration >= 0
    )
    if not ready_recorded:
        analysis_warnings.append("READY observation marker is missing or incomplete")
    capture_warnings_value = metadata.get("capture_warnings", [])
    if isinstance(capture_warnings_value, list) and all(
        isinstance(warning, str) for warning in capture_warnings_value
    ):
        capture_warnings = capture_warnings_value
    else:
        capture_warnings = []
        analysis_warnings.append("metadata capture_warnings is malformed")
    interrupted_value = metadata.get("capture_interrupted", False)
    recovered_value = metadata.get("recovered_after_interruption", False)
    if not isinstance(interrupted_value, bool) or not isinstance(recovered_value, bool):
        analysis_warnings.append("metadata interruption flags are malformed")
    capture_interrupted = bool(interrupted_value or recovered_value)
    capture_complete = bool(
        metadata.get("capture_complete") is True
        and (run_dir / ".capture-complete").is_file()
        and not (run_dir / ".capture-in-progress").exists()
        and metadata.get("case") == path_case
    )
    usable_regions = [
        region
        for region in regions
        if region.get("commands") or region.get("shaders")
    ]
    usable_failure = bool(
        capture_complete
        and xid109
        and vkd3d["device_lost"]
        and ready_recorded
        and vkd3d["breadcrumb_analysis_complete"]
        and usable_regions
        and not capture_warnings
        and not analysis_warnings
        and not capture_interrupted
    )
    valid_negative = bool(
        capture_complete
        and not events
        and not device_lost
        and kernel_capture_complete
        and ready_recorded
        and observation_duration >= negative_observation_threshold()
        and exit_code == 0
        and not capture_warnings
        and not analysis_warnings
        and not capture_interrupted
    )

    outcome_parts = []
    if xid109:
        outcome_parts.append("IL2Series.exe Xid 109")
    elif valid_negative:
        outcome_parts.append(
            f"No Xid 109 in valid {observation_duration}-second observation window"
        )
    elif capture_complete:
        outcome_parts.append("No Xid 109; inconclusive capture")
    else:
        outcome_parts.append("Incomplete capture")
    if device_lost:
        outcome_parts.append("device lost")
    if unattributed_xid109:
        outcome_parts.append("unattributed Xid 109 also present")
    if regions:
        outcome_parts.append(f"{len(regions)} crash region(s)")
    if descriptor_faults:
        outcome_parts.append(f"{len(descriptor_faults)} descriptor QA fault(s)")
    if analysis_warnings:
        outcome_parts.append(f"{len(analysis_warnings)} analysis warning(s)")

    clean_regions = []
    for region in regions:
        clean_regions.append({key: value for key, value in region.items() if key != "raw_lines"})
    return {
        "run": run_dir.name,
        "path": f"results/{run_dir.name}",
        "case": path_case,
        "start_utc": metadata.get("start_utc"),
        "duration_seconds": duration,
        "observation_start_utc": observation_start,
        "observation_duration_seconds": observation_duration,
        "ready_recorded": ready_recorded,
        "capture_complete": capture_complete,
        "capture_warnings": capture_warnings,
        "analysis_warnings": analysis_warnings,
        "capture_interrupted": capture_interrupted,
        "proton_exit_code": exit_code,
        "valid_no_xid_observation": valid_negative,
        "usable_failure": usable_failure,
        "xid109": bool(xid109),
        "xid109_events": xid109,
        "unattributed_xid109_events": unattributed_xid109,
        "other_xid_events": other_xid_events,
        "xid_cache_consistent": xid_cache_consistent,
        "kernel_capture_complete": kernel_capture_complete,
        "pci": sorted({event.get("pci") for event in xid109 if event.get("pci")}),
        "channels": sorted({event.get("channel") for event in xid109 if event.get("channel")}),
        "info": sorted({event.get("info") for event in xid109 if event.get("info")}),
        "device_lost": device_lost,
        "first_device_lost": first_lost,
        "breadcrumb_analysis": vkd3d["breadcrumb_analysis"],
        "breadcrumb_analysis_complete": vkd3d["breadcrumb_analysis_complete"],
        "descriptor_qa_log_present": descriptor_qa_log_present,
        "descriptor_qa_faults": descriptor_faults,
        "regions": clean_regions,
        "region_fingerprints": [
            region["fingerprint"] for region in clean_regions if region.get("fingerprint")
        ],
        "primary_region_fingerprint": primary.get("fingerprint") if primary else None,
        "crash_regions": [region_summary(region) for region in clean_regions],
        "crash_region": region_summary(primary) if primary else region_summary({}),
        "outcome": ", ".join(outcome_parts),
    }


def same_region(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return bool(set(left.get("region_fingerprints", [])) & set(right.get("region_fingerprints", [])))


def latest_case_runs(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the newest capture for each protocol case, preserving timestamp order."""
    latest: dict[str, dict[str, Any]] = {}
    for run in sorted(runs, key=lambda item: str(item.get("run", ""))):
        case_name = run.get("case")
        if case_name in CASES:
            latest[case_name] = run
    return sorted(latest.values(), key=lambda run: str(run.get("run", "")))


def build_evidence(runs: list[dict[str, Any]]) -> dict[str, list[str]]:
    observed: list[str] = []
    inferred: list[str] = []
    proven = ["No root cause is proven by this diagnostic matrix."]
    by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for run in runs:
        duration = run.get("duration_seconds")
        observation_duration = run.get("observation_duration_seconds")
        validity = (
            "valid no-Xid observation"
            if run["valid_no_xid_observation"]
            else (
                "usable direct failure observation"
                if run["usable_failure"]
                else "inconclusive capture"
            )
        )
        observed.append(
            f"{run['run']}: {'produced' if run['xid109'] else 'did not produce'} an "
            "IL2Series.exe-attributed Xid 109 "
            f"during the captured {duration if duration is not None else 'unknown'}-second run; "
            "the confirmed fully-rendered-hangar observation was "
            f"{observation_duration if observation_duration is not None else 'unknown'} seconds; "
            f"device lost was {'observed' if run['device_lost'] else 'not observed'}; "
            f"{len(run['regions'])} breadcrumb crash region(s) were parsed; {validity}."
        )
        for fault in run.get("descriptor_qa_faults", []):
            desired = fault.get("desired_descriptor_type") or {}
            found = fault.get("found_descriptor_type") or {}
            observed.append(
                f"{run['run']}: descriptor QA reported "
                f"{', '.join(fault.get('fault_types', [])) or 'an unspecified fault'}; "
                f"shader {fault.get('shader_hash', 'unknown')} instruction "
                f"{fault.get('instruction_id', 'unknown')}; descriptor heap cookie "
                f"{fault.get('descriptor_heap_cookie', 'unknown')}; resource/view cookie "
                f"{fault.get('resource_view_cookie', 'unknown')}; desired descriptor type "
                f"{desired.get('value', 'unknown')} ({desired.get('name', 'unknown')}), found "
                f"{found.get('value', 'unknown')} ({found.get('name', 'unknown')}); failed heap "
                f"index {fault.get('failed_heap_index', 'unknown')}."
            )

    for run in latest_case_runs(runs):
        by_case[run["case"]].append(run)

    baseline_failures = [run for run in by_case.get("baseline", []) if run["usable_failure"]]
    if baseline_failures:
        baseline = baseline_failures[-1]
        for case_name, stable_text, fail_text in (
            (
                "descriptor-qa",
                "Descriptor QA instrumentation did not reproduce the Xid in the observation window; instrumentation changes timing and is not proof that descriptor access is valid.",
                "The failure survives GPU-assisted descriptor QA instrumentation; inspect any reported descriptor faults directly.",
            ),
            (
                "descriptor-heap",
                "The known-stable descriptor-heap path did not reproduce the Xid; descriptor-path selection or its timing becomes a stronger lead.",
                "The failure also occurs on the descriptor-heap path, so the default descriptor-buffer path is less likely to be the sole trigger.",
            ),
            (
                "single-queue",
                "Queue topology or timing may influence reproduction; this does not prove an asynchronous-queue bug.",
                "Asynchronous compute/transfer queue use is less likely to be necessary for reproduction; it is not ruled out as a contributor.",
            ),
            (
                "no-descriptor-buffer",
                "Descriptor-buffer use or the timing it creates may influence reproduction; this does not prove a descriptor-buffer defect.",
                "VK_EXT_descriptor_buffer is less likely to be the sole trigger; descriptor handling is not ruled out.",
            ),
            (
                "sync",
                "Timing or synchronization sensitivity becomes more plausible; no synchronization defect is proven.",
                "The failure survives synchronized breadcrumb instrumentation; that does not identify the faulty synchronization primitive.",
            ),
        ):
            conclusive = [
                run for run in by_case.get(case_name, [])
                if run["usable_failure"] or run["valid_no_xid_observation"]
            ]
            if not conclusive:
                continue
            comparison = conclusive[-1]
            if not comparison["xid109"]:
                inferred.append(f"{case_name}: {stable_text}")
            else:
                qualifier = " At least one parsed crash-region fingerprint matches baseline." \
                    if same_region(baseline, comparison) else ""
                inferred.append(f"{case_name}: {fail_text}{qualifier}")

    groups: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for run in latest_case_runs(runs):
        if not run["usable_failure"]:
            continue
        for region in run["crash_regions"]:
            if region.get("fingerprint") and (region.get("commands") or region.get("shaders")):
                groups[region["fingerprint"]][run["run"]] = run
    for fingerprint, run_map in groups.items():
        group = list(run_map.values())
        if len(group) >= 2:
            observed.append(
                f"{len(group)} failing runs share normalized crash-region fingerprint "
                f"{fingerprint[:12]}: {', '.join(run['run'] for run in group)}."
            )
            inferred.append(
                "The repeated command/shader region is a candidate for focused analysis, not a demonstrated root cause."
            )
    if not inferred:
        inferred.append("The available completed cases do not yet support a cross-case inference.")
    return {"observed": observed, "inferred": inferred, "proven": proven}


def cell(value: Any) -> str:
    if value is None or value == []:
        return "—"
    if isinstance(value, list):
        value = ", ".join(str(item) for item in value)
    return str(value).replace("|", "\\|").replace("\n", " ")


def table_row(run: dict[str, Any]) -> str:
    regions = run["crash_regions"]
    contexts: list[str] = []
    shaders: list[str] = []
    completed: list[str] = []
    next_commands: list[str] = []
    for region in regions:
        queue = region.get("queue")
        queue_text = f"{queue['type']}[{queue['index']}]" if queue else "unknown queue"
        if region.get("bottom_context") is not None:
            contexts.append(f"{queue_text} ctx {region['bottom_context']}→{region['top_context']}")
        for shader in region.get("shaders", []):
            if shader not in shaders:
                shaders.append(shader)
        if region.get("last_completed") is not None:
            completed.append(f"{queue_text}:{region['last_completed']}")
        if region.get("commands"):
            next_commands.append(f"{queue_text}:{region['commands'][0]}")
    return "| " + " | ".join(
        [
            cell(run["case"]),
            cell(run["observation_duration_seconds"]),
            "yes" if run["xid109"] else "no",
            cell(run["pci"]),
            cell(run["channels"]),
            cell(run["info"]),
            "yes" if run["device_lost"] else "no",
            cell(contexts),
            cell(shaders[:4]),
            cell(completed),
            cell(next_commands),
            cell(run["outcome"]),
        ]
    ) + " |"


def context_around_first(text: str, pattern: re.Pattern[str], radius: int = 20) -> str:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if pattern.search(line):
            start = max(0, index - radius)
            end = min(len(lines), index + radius + 1)
            return "\n".join(lines[start:end]) + "\n"
    return ""


def file_sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_shader_hash(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    lowered = value.lower()
    if not SHADER_HASH_RE.fullmatch(lowered):
        return None
    return lowered.zfill(16)


def manifest_relative_path(value: Any, manifest_path: pathlib.Path) -> pathlib.PurePosixPath:
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"invalid shader path in {manifest_path}: {value!r}")
    relative = pathlib.PurePosixPath(value)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise RuntimeError(f"unsafe shader path in {manifest_path}: {value!r}")
    return relative


def shader_source(
    run_dir: pathlib.Path,
    relative: pathlib.PurePosixPath,
    manifest_path: pathlib.Path,
) -> pathlib.Path:
    run_root = run_dir.resolve(strict=True)
    source = run_dir.joinpath(*relative.parts)
    current = run_dir
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise RuntimeError(f"unsafe shader symlink in {manifest_path}: {relative}")
    try:
        resolved = source.resolve(strict=True)
    except OSError as exc:
        raise RuntimeError(f"missing shader declared by {manifest_path}: {relative}") from exc
    if not resolved.is_relative_to(run_root) or not resolved.is_file():
        raise RuntimeError(f"shader escapes run directory in {manifest_path}: {relative}")
    return resolved


def copy_candidate_shaders(
    candidate: pathlib.Path | None,
    runs: list[dict[str, Any]],
    hashes: set[str],
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    normalized_hashes = {
        normalized
        for shader_hash in hashes
        if (normalized := normalize_shader_hash(shader_hash)) is not None
    }
    seen: dict[tuple[str, str], str] = {}
    for run in runs:
        run_name = run.get("run")
        if not isinstance(run_name, str) or not RUN_RE.fullmatch(run_name):
            raise RuntimeError(f"invalid candidate source run name: {run_name!r}")
        run_dir = RESULTS_ROOT / run_name
        results_root = RESULTS_ROOT.resolve(strict=True)
        try:
            resolved_run = run_dir.resolve(strict=True)
        except OSError as exc:
            raise RuntimeError(f"candidate source run is missing: {run_name}") from exc
        if resolved_run.parent != results_root or not resolved_run.is_dir():
            raise RuntimeError(f"candidate source run escapes results directory: {run_name}")

        manifest_path = resolved_run / "shader-manifest.json"
        manifest = read_json(manifest_path, None)
        shader_values = manifest.get("shaders") if isinstance(manifest, dict) else None
        if not isinstance(shader_values, list):
            raise RuntimeError(f"invalid shader manifest: {manifest_path}")
        for index, entry in enumerate(shader_values):
            if not isinstance(entry, dict):
                raise RuntimeError(
                    f"invalid shader entry {index} in {manifest_path}: expected an object"
                )
            relative = manifest_relative_path(entry.get("file"), manifest_path)
            shader_hash = normalize_shader_hash(entry.get("vkd3d_hash"))
            suffix = pathlib.PurePosixPath(relative).suffix.lower()
            if shader_hash not in normalized_hashes or suffix not in {".dxil", ".spv"}:
                continue

            source = shader_source(resolved_run, relative, manifest_path)
            declared_digest = entry.get("sha256")
            if not isinstance(declared_digest, str) or not SHA256_RE.fullmatch(declared_digest):
                raise RuntimeError(
                    f"invalid SHA-256 for {relative} in {manifest_path}: {declared_digest!r}"
                )
            actual_digest = file_sha256(source)
            if actual_digest != declared_digest:
                raise RuntimeError(
                    f"shader SHA-256 mismatch for {relative} in {manifest_path}"
                )
            declared_size = entry.get("byte_size")
            if (
                not isinstance(declared_size, int)
                or isinstance(declared_size, bool)
                or source.stat().st_size != declared_size
            ):
                raise RuntimeError(f"shader size mismatch for {relative} in {manifest_path}")

            key = (shader_hash, suffix)
            if key in seen:
                if seen[key] != actual_digest:
                    raise RuntimeError(
                        f"conflicting shader bytes for {shader_hash}{suffix} across candidate runs"
                    )
                continue
            destination_name = source.name
            if candidate is not None:
                destination = candidate / destination_name
                if destination.exists() and file_sha256(destination) != actual_digest:
                    destination = candidate / f"{shader_hash}-{run_name}{suffix}"
                    destination_name = destination.name
                if destination.exists() and file_sha256(destination) != actual_digest:
                    raise RuntimeError(
                        f"candidate shader destination collision: {destination.name}"
                    )
                if not destination.exists():
                    shutil.copy2(source, destination)
            copied = dict(entry)
            copied["vkd3d_hash"] = shader_hash
            copied["file"] = destination_name
            copied["source_run"] = run_name
            entries.append(copied)
            seen[key] = actual_digest
    return entries


def candidate_trees_match(left: pathlib.Path, right: pathlib.Path) -> bool:
    def file_map(root: pathlib.Path) -> dict[str, str] | None:
        if root.is_symlink() or not root.is_dir():
            return None
        values: dict[str, str] = {}
        try:
            for child in root.iterdir():
                if child.is_symlink() or not child.is_file():
                    return None
                values[child.name] = file_sha256(child)
        except OSError:
            return None
        return values

    return file_map(left) == file_map(right)


def retire_candidate(candidate: pathlib.Path) -> None:
    if not candidate.exists():
        return
    marker = candidate / ".generated-by-il2-xid109-analyzer"
    if not candidate.is_dir() or not marker.is_file():
        raise RuntimeError(f"refusing to retire unrecognized candidate path: {candidate}")
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    previous = RESULTS_ROOT / f"culprit-candidate.previous-{timestamp}"
    suffix = 2
    while previous.exists():
        previous = RESULTS_ROOT / f"culprit-candidate.previous-{timestamp}-{suffix}"
        suffix += 1
    candidate.replace(previous)


def discard_candidate_staging(
    candidate: pathlib.Path, *, allow_incomplete_marker: bool = False
) -> None:
    if not candidate.exists() and not candidate.is_symlink():
        return
    try:
        expected_parent = RESULTS_ROOT.resolve(strict=True)
        actual_parent = candidate.parent.resolve(strict=True)
    except OSError as exc:
        raise RuntimeError(f"cannot validate candidate staging path: {candidate}") from exc
    if (
        actual_parent != expected_parent
        or not STAGING_RE.fullmatch(candidate.name)
        or candidate.is_symlink()
        or not candidate.is_dir()
    ):
        raise RuntimeError(f"refusing to remove unrecognized candidate staging path: {candidate}")
    marker = candidate / ".generated-by-il2-xid109-analyzer"
    recognized_marker = (
        not marker.is_symlink()
        and marker.is_file()
        and read_text(marker) == CANDIDATE_MARKER
    )
    incomplete_marker_only = allow_incomplete_marker and all(
        child.name == marker.name and not child.is_symlink() and child.is_file()
        for child in candidate.iterdir()
    )
    if not (recognized_marker or incomplete_marker_only):
        raise RuntimeError(f"refusing to remove unrecognized candidate staging path: {candidate}")
    shutil.rmtree(candidate)


def generate_candidate(runs: list[dict[str, Any]]) -> dict[str, Any] | None:
    final_candidate = RESULTS_ROOT / "culprit-candidate"
    groups: dict[str, dict[str, tuple[dict[str, Any], int]]] = defaultdict(dict)
    for run in latest_case_runs(runs):
        if not run["usable_failure"]:
            continue
        for index, region in enumerate(run["crash_regions"]):
            fingerprint = region.get("fingerprint")
            if fingerprint and (region.get("commands") or region.get("shaders")):
                groups[fingerprint].setdefault(run["run"], (run, index))
    converged = [
        (fingerprint, list(run_map.values()))
        for fingerprint, run_map in groups.items()
        if len(run_map) >= 2
    ]
    if not converged:
        retire_candidate(final_candidate)
        return None
    fingerprint, matches = max(converged, key=lambda item: len(item[1]))
    group = [run for run, _ in matches]
    hashes = {
        shader
        for run, region_index in matches
        for shader in run["crash_regions"][region_index]["shaders"]
    }
    source_regions = [
        {
            "run": run["run"],
            "region_index": region_index,
            "queue": run["crash_regions"][region_index].get("queue"),
            "bottom_context": run["crash_regions"][region_index].get("bottom_context"),
            "top_context": run["crash_regions"][region_index].get("top_context"),
        }
        for run, region_index in matches
    ]
    existing: dict[str, Any] | None = None
    generated_utc = utc_now()
    if final_candidate.is_dir() and (
        final_candidate / ".generated-by-il2-xid109-analyzer"
    ).is_file():
        existing_value = read_json(final_candidate / "metadata.json", {})
        if (
            isinstance(existing_value, dict)
            and existing_value.get("fingerprint") == fingerprint
            and existing_value.get("source_regions") == source_regions
            and isinstance(existing_value.get("generated_utc"), str)
        ):
            existing = existing_value
            generated_utc = existing_value["generated_utc"]
    candidate = RESULTS_ROOT / f".culprit-candidate-building-{os.getpid()}"
    if candidate.exists() or candidate.is_symlink():
        discard_candidate_staging(candidate)
    candidate.mkdir()
    marker = candidate / ".generated-by-il2-xid109-analyzer"
    try:
        marker.write_text(CANDIDATE_MARKER, encoding="utf-8")
        shader_entries = copy_candidate_shaders(candidate, group, hashes)
        region_sections: list[str] = []
        vkd3d_sections: list[str] = []
        proton_sections: list[str] = []
        xid_sections: list[str] = []
        device_pattern = re.compile(
            r"VK_ERROR_DEVICE_LOST|Device lost observed|DEVICE_LOST", re.IGNORECASE
        )
        xid_pattern = re.compile(
            r"NVRM|Xid|CTX SWITCH TIMEOUT|IL2Series\.exe", re.IGNORECASE
        )
        for run, region_index in matches:
            run_dir = RESULTS_ROOT / run["run"]
            vkd3d_text = read_text(run_dir / "vkd3d.log")
            parsed = parse_vkd3d_log(vkd3d_text)
            raw_region = (
                parsed["regions"][region_index].get("raw_lines", [])
                if region_index < len(parsed["regions"])
                else []
            )
            region_sections.append(
                f"===== {run['run']} =====\n" + "\n".join(raw_region) + "\n"
            )
            vkd3d_sections.append(
                f"===== {run['run']} =====\n"
                + context_around_first(vkd3d_text, device_pattern, 80)
            )
            proton_sections.append(
                f"===== {run['run']} =====\n"
                + context_around_first(read_text(run_dir / "proton.log"), device_pattern, 40)
            )
            xid_sections.append(
                f"===== {run['run']} =====\n"
                + context_around_first(read_text(run_dir / "kernel-full.log"), xid_pattern, 20)
            )

        atomic_text(candidate / "breadcrumb-region.txt", "\n".join(region_sections))
        atomic_text(candidate / "relevant-vkd3d-log.txt", "\n".join(vkd3d_sections))
        atomic_text(candidate / "relevant-proton-log.txt", "\n".join(proton_sections))
        atomic_text(candidate / "xid-context.txt", "\n".join(xid_sections))
        atomic_json(
            candidate / "shader-manifest.json",
            {
                "schema_version": 1,
                "candidate_fingerprint": fingerprint,
                "shaders": shader_entries,
            },
        )
        metadata = {
            "schema_version": 1,
            "label": "CANDIDATE CRASH REGION",
            "generated_utc": generated_utc,
            "fingerprint": fingerprint,
            "source_runs": [run["run"] for run in group],
            "source_regions": source_regions,
            "xid": 109,
            "shader_hashes": sorted(hashes),
            "claim": "Repeated observed region; root cause not proven",
        }
        atomic_json(candidate / "metadata.json", metadata)
        atomic_text(
            candidate / "README.md",
            "# CANDIDATE CRASH REGION\n\n"
            "This bundle was generated because multiple Xid 109/device-lost runs had at least one "
            "matching normalized queue/command/shader/event region fingerprint.\n\n"
            f"OBSERVED: the matching runs are {', '.join(run['run'] for run in group)}.\n\n"
            "INFERRED: this repeated region is a useful target for focused source, shader, and resource analysis.\n\n"
            "PROVEN: no command, shader, resource, VKD3D component, game behavior, or NVIDIA driver defect "
            "has been proven causal. Do not label this bundle a root cause.\n",
        )
        if existing is not None and candidate_trees_match(candidate, final_candidate):
            discard_candidate_staging(candidate)
            return existing
        if existing is not None:
            metadata["generated_utc"] = utc_now()
            atomic_json(candidate / "metadata.json", metadata)
        if final_candidate.exists():
            retire_candidate(final_candidate)
        candidate.replace(final_candidate)
        return metadata
    except Exception:
        if candidate.exists() or candidate.is_symlink():
            discard_candidate_staging(candidate, allow_incomplete_marker=True)
        raise


def markdown(runs: list[dict[str, Any]], evidence: dict[str, list[str]], candidate: dict[str, Any] | None) -> str:
    lines = [
        "# IL-2 Korea Xid 109 analysis summary",
        "",
        f"Generated: {utc_now()}",
        "",
        "| Case | Hangar Observation (s) | Xid109 | PCI | Channel | Info | Device Lost | Crash Region | Shader | Last Completed | Next Command | Outcome |",
        "|---|---:|---:|---|---|---|---:|---|---|---|---|---|",
    ]
    lines.extend(table_row(run) for run in runs)
    for heading in ("observed", "inferred", "proven"):
        lines.extend(["", f"## {heading.upper()}", ""])
        lines.extend(f"- {item}" for item in evidence[heading])
    lines.extend(["", "## Descriptor QA faults", ""])
    descriptor_fault_rows = []
    for run in runs:
        for fault in run.get("descriptor_qa_faults", []):
            desired = fault.get("desired_descriptor_type") or {}
            found = fault.get("found_descriptor_type") or {}
            descriptor_fault_rows.append(
                "| " + " | ".join(
                    [
                        cell(run["case"]),
                        cell(fault.get("fault_types")),
                        cell(fault.get("shader_hash")),
                        cell(fault.get("instruction_id")),
                        cell(fault.get("descriptor_heap_cookie")),
                        cell(fault.get("resource_view_cookie")),
                        cell(f"{desired.get('value', '—')} ({desired.get('name', '—')})"),
                        cell(f"{found.get('value', '—')} ({found.get('name', '—')})"),
                        cell(fault.get("failed_heap_index")),
                        cell(fault.get("shader_dump_files")),
                    ]
                ) + " |"
            )
    if descriptor_fault_rows:
        lines.extend(
            [
                "| Case | Fault type(s) | Shader hash | Instruction ID | Descriptor heap cookie | Resource/view cookie | Desired type | Found type | Failed heap index | Shader dumps |",
                "|---|---|---|---:|---:|---:|---|---|---:|---|",
                *descriptor_fault_rows,
            ]
        )
    else:
        lines.append("No descriptor QA faults were parsed from the captured logs.")
    lines.extend(["", "## Candidate bundle", ""])
    if candidate:
        lines.append(
            f"Generated `results/culprit-candidate/` for fingerprint `{candidate['fingerprint']}`. "
            "It is explicitly a candidate crash region, not a root cause."
        )
    else:
        lines.append("Not generated: at least two failing runs have not converged on the same parsed command/shader region.")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    if RESULTS_ROOT.is_symlink() or not RESULTS_ROOT.is_dir():
        raise SystemExit("error: results path is missing or unsafe")
    run_dirs = sorted(
        path for path in RESULTS_ROOT.iterdir()
        if RUN_RE.fullmatch(path.name)
    )
    for path in run_dirs:
        validate_run_tree(path)
    runs = [summarize_run(path) for path in run_dirs]
    evidence = build_evidence(runs)
    candidate = generate_candidate(runs)
    report = {
        "schema_version": 1,
        "generated_utc": utc_now(),
        "run_count": len(runs),
        "runs": runs,
        "evidence": evidence,
        "candidate": candidate,
    }
    atomic_json(RESULTS_ROOT / "analysis-summary.json", report)
    atomic_text(RESULTS_ROOT / "analysis-summary.md", markdown(runs, evidence, candidate))
    print(f"Analyzed {len(runs)} run(s).")
    print(RESULTS_ROOT / "analysis-summary.md")
    if candidate:
        print(RESULTS_ROOT / "culprit-candidate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
