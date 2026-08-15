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

from analyzer.parsers import parse_kernel_log, parse_proton_log, parse_vkd3d_log  # noqa: E402


RUN_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{6}Z-(baseline|single-queue|no-descriptor-buffer|sync)(?:-\d+)?$"
)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def read_json(path: pathlib.Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def atomic_text(path: pathlib.Path, value: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)


def atomic_json(path: pathlib.Path, value: Any) -> None:
    atomic_text(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def summarize_run(run_dir: pathlib.Path) -> dict[str, Any]:
    metadata = read_json(run_dir / "metadata.json", {})
    kernel_text = read_text(run_dir / "kernel-full.log")
    xid_data = read_json(run_dir / "xid-events.json", {})
    events = xid_data.get("events") if isinstance(xid_data, dict) else None
    if not isinstance(events, list):
        events = parse_kernel_log(kernel_text)
    xid109 = [event for event in events if event.get("xid") == 109]
    vkd3d_text = read_text(run_dir / "vkd3d.log")
    proton_text = read_text(run_dir / "proton.log")
    vkd3d = parse_vkd3d_log(vkd3d_text)
    proton = parse_proton_log(proton_text)
    regions = vkd3d["regions"]
    primary = regions[0] if regions else None
    checkpoint = primary.get("checkpoint") if primary else None
    queue = primary.get("queue") if primary else None
    device_lost = bool(vkd3d["device_lost"] or proton["device_lost"])
    first_lost = vkd3d["first_device_lost"] or proton["first"]

    outcome_parts = []
    if xid109:
        outcome_parts.append("Xid 109")
    elif metadata.get("capture_complete"):
        outcome_parts.append("No Xid 109 observed")
    else:
        outcome_parts.append("Incomplete capture")
    if device_lost:
        outcome_parts.append("device lost")
    if regions:
        outcome_parts.append(f"{len(regions)} crash region(s)")

    clean_regions = []
    for region in regions:
        clean_regions.append({key: value for key, value in region.items() if key != "raw_lines"})
    return {
        "run": run_dir.name,
        "path": str(run_dir),
        "case": metadata.get("case", "unknown"),
        "start_utc": metadata.get("start_utc"),
        "duration_seconds": metadata.get("duration_seconds"),
        "capture_complete": bool(metadata.get("capture_complete")),
        "capture_warnings": metadata.get("capture_warnings", []),
        "xid109": bool(xid109),
        "xid109_events": xid109,
        "pci": sorted({event.get("pci") for event in xid109 if event.get("pci")}),
        "channels": sorted({event.get("channel") for event in xid109 if event.get("channel")}),
        "info": sorted({event.get("info") for event in xid109 if event.get("info")}),
        "device_lost": device_lost,
        "first_device_lost": first_lost,
        "breadcrumb_analysis": vkd3d["breadcrumb_analysis"],
        "regions": clean_regions,
        "primary_region_fingerprint": primary.get("fingerprint") if primary else None,
        "crash_region": {
            "queue": queue,
            "bottom_context": checkpoint.get("bottom_context") if checkpoint else None,
            "top_context": checkpoint.get("top_context") if checkpoint else None,
            "last_completed": checkpoint.get("bottom_marker") if checkpoint else None,
            "top_progress": checkpoint.get("top_marker") if checkpoint else None,
            "commands": primary.get("commands", []) if primary else [],
            "shaders": [item["hash"] for item in primary.get("shaders", [])] if primary else [],
        },
        "outcome": ", ".join(outcome_parts),
    }


def same_region(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_fp = left.get("primary_region_fingerprint")
    right_fp = right.get("primary_region_fingerprint")
    return bool(left_fp and right_fp and left_fp == right_fp)


def build_evidence(runs: list[dict[str, Any]]) -> dict[str, list[str]]:
    observed: list[str] = []
    inferred: list[str] = []
    proven = ["No root cause is proven by this diagnostic matrix."]
    by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for run in runs:
        by_case[run["case"]].append(run)
        duration = run.get("duration_seconds")
        observed.append(
            f"{run['run']}: {'produced' if run['xid109'] else 'did not produce'} Xid 109 "
            f"during the captured {duration if duration is not None else 'unknown'}-second run; "
            f"device lost was {'observed' if run['device_lost'] else 'not observed'}; "
            f"{len(run['regions'])} breadcrumb crash region(s) were parsed."
        )

    baseline_failures = [run for run in by_case.get("baseline", []) if run["xid109"]]
    if baseline_failures:
        baseline = baseline_failures[-1]
        for case_name, stable_text, fail_text in (
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
            completed = [run for run in by_case.get(case_name, []) if run["capture_complete"]]
            if not completed:
                continue
            comparison = completed[-1]
            if not comparison["xid109"]:
                inferred.append(f"{case_name}: {stable_text}")
            else:
                qualifier = " The parsed primary crash-region fingerprint matches baseline." \
                    if same_region(baseline, comparison) else ""
                inferred.append(f"{case_name}: {fail_text}{qualifier}")

    failing_with_regions = [
        run for run in runs
        if run["xid109"] and run["device_lost"] and run.get("primary_region_fingerprint")
    ]
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for run in failing_with_regions:
        groups[run["primary_region_fingerprint"]].append(run)
    for fingerprint, group in groups.items():
        if len(group) >= 2:
            observed.append(
                f"{len(group)} failing runs share normalized primary crash-region fingerprint "
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
    region = run["crash_region"]
    queue = region.get("queue")
    queue_text = f"{queue['type']}[{queue['index']}]" if queue else "—"
    contexts = "—"
    if region.get("bottom_context") is not None:
        contexts = f"{queue_text} ctx {region['bottom_context']}→{region['top_context']}"
    shaders = region.get("shaders", [])
    return "| " + " | ".join(
        [
            cell(run["case"]),
            "yes" if run["xid109"] else "no",
            cell(run["pci"]),
            cell(run["channels"]),
            cell(run["info"]),
            "yes" if run["device_lost"] else "no",
            cell(contexts),
            cell(shaders[:4]),
            cell(region.get("last_completed")),
            cell(region.get("commands", [None])[0] if region.get("commands") else None),
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


def copy_candidate_shaders(candidate: pathlib.Path, runs: list[dict[str, Any]], hashes: set[str]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for run in runs:
        run_dir = pathlib.Path(run["path"])
        manifest = read_json(run_dir / "shader-manifest.json", {"shaders": []})
        for entry in manifest.get("shaders", []):
            shader_hash = (entry.get("vkd3d_hash") or "").lower()
            suffix = pathlib.Path(entry.get("file", "")).suffix.lower()
            if shader_hash not in hashes or suffix not in {".dxil", ".spv"}:
                continue
            key = (shader_hash, suffix)
            if key in seen:
                continue
            source = run_dir / entry["file"]
            if not source.is_file():
                continue
            destination = candidate / source.name
            if destination.exists() and hashlib.sha256(destination.read_bytes()).hexdigest() != entry.get("sha256"):
                destination = candidate / f"{shader_hash}-{run['run']}{suffix}"
            if not destination.exists():
                shutil.copy2(source, destination)
            copied = dict(entry)
            copied["file"] = destination.name
            copied["source_run"] = run["run"]
            entries.append(copied)
            seen.add(key)
    return entries


def generate_candidate(runs: list[dict[str, Any]]) -> dict[str, Any] | None:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for run in runs:
        region = run["crash_region"]
        if run["xid109"] and run["device_lost"] and run.get("primary_region_fingerprint") and \
                (region.get("commands") or region.get("shaders")):
            groups[run["primary_region_fingerprint"]].append(run)
    converged = [(fingerprint, group) for fingerprint, group in groups.items() if len(group) >= 2]
    if not converged:
        return None
    fingerprint, group = max(converged, key=lambda item: len(item[1]))
    final_candidate = RESULTS_ROOT / "culprit-candidate"
    candidate = RESULTS_ROOT / f".culprit-candidate-building-{os.getpid()}"
    if candidate.exists():
        raise RuntimeError(f"candidate staging directory already exists: {candidate}")
    candidate.mkdir()
    marker = candidate / ".generated-by-il2-xid109-analyzer"
    marker.write_text("generated; safe for analyzer-owned files only\n", encoding="utf-8")

    hashes = {shader for run in group for shader in run["crash_region"]["shaders"]}
    shader_entries = copy_candidate_shaders(candidate, group, hashes)
    region_sections: list[str] = []
    vkd3d_sections: list[str] = []
    proton_sections: list[str] = []
    xid_sections: list[str] = []
    device_pattern = re.compile(r"VK_ERROR_DEVICE_LOST|Device lost observed|DEVICE_LOST", re.IGNORECASE)
    xid_pattern = re.compile(r"NVRM|Xid|CTX SWITCH TIMEOUT|IL2Series\.exe", re.IGNORECASE)
    for run in group:
        run_dir = pathlib.Path(run["path"])
        vkd3d_text = read_text(run_dir / "vkd3d.log")
        parsed = parse_vkd3d_log(vkd3d_text)
        raw_region = parsed["regions"][0].get("raw_lines", []) if parsed["regions"] else []
        region_sections.append(f"===== {run['run']} =====\n" + "\n".join(raw_region) + "\n")
        vkd3d_sections.append(
            f"===== {run['run']} =====\n" + context_around_first(vkd3d_text, device_pattern, 80)
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
        {"schema_version": 1, "candidate_fingerprint": fingerprint, "shaders": shader_entries},
    )
    metadata = {
        "schema_version": 1,
        "label": "CANDIDATE CRASH REGION",
        "generated_utc": utc_now(),
        "fingerprint": fingerprint,
        "source_runs": [run["run"] for run in group],
        "xid": 109,
        "shader_hashes": sorted(hashes),
        "claim": "Repeated observed region; root cause not proven",
    }
    atomic_json(candidate / "metadata.json", metadata)
    atomic_text(
        candidate / "README.md",
        "# CANDIDATE CRASH REGION\n\n"
        "This bundle was generated because multiple Xid 109/device-lost runs had the same "
        "normalized command/shader-region fingerprint.\n\n"
        f"OBSERVED: the matching runs are {', '.join(run['run'] for run in group)}.\n\n"
        "INFERRED: this repeated region is a useful target for focused source, shader, and resource analysis.\n\n"
        "PROVEN: no command, shader, resource, VKD3D component, game behavior, or NVIDIA driver defect "
        "has been proven causal. Do not label this bundle a root cause.\n",
    )
    if final_candidate.exists():
        final_marker = final_candidate / ".generated-by-il2-xid109-analyzer"
        if not final_marker.is_file():
            raise RuntimeError(f"refusing to replace unrecognized candidate directory: {final_candidate}")
        previous = RESULTS_ROOT / f"culprit-candidate.previous-{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H%M%SZ')}"
        if previous.exists():
            raise RuntimeError(f"candidate backup path already exists: {previous}")
        final_candidate.replace(previous)
    candidate.replace(final_candidate)
    return metadata


def markdown(runs: list[dict[str, Any]], evidence: dict[str, list[str]], candidate: dict[str, Any] | None) -> str:
    lines = [
        "# IL-2 Korea Xid 109 analysis summary",
        "",
        f"Generated: {utc_now()}",
        "",
        "| Case | Xid109 | PCI | Channel | Info | Device Lost | Crash Region | Shader | Last Completed | Next Command | Outcome |",
        "|---|---:|---|---|---|---:|---|---|---|---|---|",
    ]
    lines.extend(table_row(run) for run in runs)
    for heading in ("observed", "inferred", "proven"):
        lines.extend(["", f"## {heading.upper()}", ""])
        lines.extend(f"- {item}" for item in evidence[heading])
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
    run_dirs = sorted(
        path for path in RESULTS_ROOT.iterdir()
        if path.is_dir() and RUN_RE.match(path.name) and (path / "metadata.json").is_file()
    )
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
