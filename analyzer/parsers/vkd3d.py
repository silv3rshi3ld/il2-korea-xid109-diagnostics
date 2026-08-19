"""Parse VKD3D-Proton breadcrumb reports from the pinned diagnostic build."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from .proton import parse_proton_log


QUEUE_RE = re.compile(
    r"Reporting NVIDIA checkpoints for (?P<type>direct|compute|copy) queue (?P<index>\d+)",
    re.IGNORECASE,
)
PENDING_RE = re.compile(
    r"Found pending command list context\s+"
    r"(?:\[(?P<bottom_context>\d+),\s*(?P<top_context>\d+)\]|(?P<context>\d+))\s+"
    r"in executable state, TOP_OF_PIPE marker (?P<top>\d+), "
    r"BOTTOM_OF_PIPE marker (?P<bottom>\d+)",
    re.IGNORECASE,
)
COMMAND_RE = re.compile(r"\bCommand:\s*(?P<value>[A-Za-z0-9_ -]+)\s*$")
SHADER_RE = re.compile(
    r"\bhash:\s*(?P<hash>[0-9A-Fa-f]{8,16}),\s*stage:\s*(?P<stage>[0-9A-Fa-f]+)",
    re.IGNORECASE,
)
ARG_RE = re.compile(r"\bSet arg:\s*(?P<decimal>\d+)\s*\(#(?P<hex>[0-9A-Fa-f]+)\)")
COOKIE_RE = re.compile(r"\bCookie:\s*(?P<decimal>\d+)\s*\(#(?P<hex>[0-9A-Fa-f]+)\)")
TAG_RE = re.compile(r"\bTag:\s*(?P<value>.+?)\s*$")
BEGIN = "Potential crash region BEGIN"
END = "Potential crash region END"
REPORT_BEGIN = "Device lost observed, analyzing breadcrumbs"
REPORT_END = "Done analyzing breadcrumbs"
DESCRIPTOR_FAULT_RE = re.compile(r"Fault type:\s*(?P<value>[A-Z][A-Z0-9_]+)")
DESCRIPTOR_HEAP_COOKIE_RE = re.compile(r"CBV_SRV_UAV heap cookie:\s*(?P<value>\d+)")
DESCRIPTOR_SHADER_RE = re.compile(
    r"Shader hash and instruction:\s*(?P<hash>[0-9A-Fa-f]{8,16})\s*\((?P<instruction>\d+)\)"
)
DESCRIPTOR_RESOURCE_COOKIE_RE = re.compile(
    r"Accessed resource/view cookie:\s*(?P<value>\d+)"
)
DESCRIPTOR_DESIRED_TYPE_RE = re.compile(
    r"Shader desired descriptor type:\s*(?P<value>\d+)\s*\((?P<name>.+)\)\s*$"
)
DESCRIPTOR_FOUND_TYPE_RE = re.compile(
    r"Found descriptor type in heap:\s*(?P<value>\d+)\s*\((?P<name>.+)\)\s*$"
)
DESCRIPTOR_FAILED_INDEX_RE = re.compile(r"Failed heap index:\s*(?P<value>\d+)")


def _fingerprint(region: dict[str, Any]) -> str:
    normalized_events = [
        "cookie:*" if event.startswith("cookie:") else event
        for event in region["events"]
    ]
    payload = {
        "queue": region.get("queue"),
        "events": normalized_events,
    }
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def parse_descriptor_qa_faults(text: str) -> list[dict[str, Any]]:
    """Parse complete GPU-assisted descriptor QA fault records.

    The pinned VKD3D revision emits the same field block to its regular error
    log and, when configured, to ``VKD3D_DESCRIPTOR_QA_LOG``. A fault can carry
    more than one fault type, so records are completed by the final heap-index
    field rather than by a second ``Fault type`` line.
    """
    faults: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line_number, line in enumerate(text.splitlines(), start=1):
        fault_match = DESCRIPTOR_FAULT_RE.search(line)
        if fault_match:
            if current is None:
                current = {"fault_types": [], "start_line": line_number}
            fault_type = fault_match.group("value")
            if fault_type not in current["fault_types"]:
                current["fault_types"].append(fault_type)
            continue
        if current is None:
            continue
        if match := DESCRIPTOR_HEAP_COOKIE_RE.search(line):
            current["descriptor_heap_cookie"] = int(match.group("value"))
        elif match := DESCRIPTOR_SHADER_RE.search(line):
            current["shader_hash"] = match.group("hash").lower().zfill(16)
            current["instruction_id"] = int(match.group("instruction"))
        elif match := DESCRIPTOR_RESOURCE_COOKIE_RE.search(line):
            current["resource_view_cookie"] = int(match.group("value"))
        elif match := DESCRIPTOR_DESIRED_TYPE_RE.search(line):
            current["desired_descriptor_type"] = {
                "value": int(match.group("value")),
                "name": match.group("name").strip(),
            }
        elif match := DESCRIPTOR_FOUND_TYPE_RE.search(line):
            current["found_descriptor_type"] = {
                "value": int(match.group("value")),
                "name": match.group("name").strip(),
            }
        elif match := DESCRIPTOR_FAILED_INDEX_RE.search(line):
            current["failed_heap_index"] = int(match.group("value"))
            current["end_line"] = line_number
            faults.append(current)
            current = None
    return faults


def parse_vkd3d_log(text: str) -> dict[str, Any]:
    device = parse_proton_log(text)
    regions: list[dict[str, Any]] = []
    current_queue: dict[str, Any] | None = None
    pending: dict[str, Any] | None = None
    region: dict[str, Any] | None = None
    report_started = False
    report_complete = False

    for line_number, line in enumerate(text.splitlines(), start=1):
        if REPORT_BEGIN.lower() in line.lower():
            report_started = True
        if report_started and REPORT_END.lower() in line.lower():
            report_complete = True

        queue = QUEUE_RE.search(line)
        if queue:
            current_queue = {
                "type": queue.group("type").lower(),
                "index": int(queue.group("index")),
            }

        pending_match = PENDING_RE.search(line)
        if pending_match:
            context = pending_match.group("context")
            pending = {
                "bottom_context": int(pending_match.group("bottom_context") or context),
                "top_context": int(pending_match.group("top_context") or context),
                "top_marker": int(pending_match.group("top")),
                "bottom_marker": int(pending_match.group("bottom")),
            }

        if BEGIN in line:
            if region is not None:
                region["end_line"] = line_number - 1
                region["complete_delimiters"] = False
                region["fingerprint"] = _fingerprint(region)
                regions.append(region)
            region = {
                "start_line": line_number,
                "end_line": None,
                "queue": dict(current_queue) if current_queue else None,
                "checkpoint": dict(pending) if pending else None,
                "commands": [],
                "shaders": [],
                "events": [],
                "raw_lines": [line],
                "complete_delimiters": False,
            }
            continue

        if region is None:
            continue

        region["raw_lines"].append(line)
        command = COMMAND_RE.search(line)
        if command:
            value = command.group("value").strip().lower().replace(" ", "_")
            if value not in {"top_marker", "bottom_marker", "set_shader_hash"}:
                region["commands"].append(value)
                region["events"].append(f"command:{value}")
        shader = SHADER_RE.search(line)
        if shader:
            item = {
                "hash": shader.group("hash").lower().zfill(16),
                "stage": shader.group("stage").lower(),
            }
            if item not in region["shaders"]:
                region["shaders"].append(item)
            region["events"].append(f"shader:{item['hash']}:{item['stage']}")
        argument = ARG_RE.search(line)
        if argument:
            region["events"].append(f"arg:{int(argument.group('hex'), 16):x}")
        cookie = COOKIE_RE.search(line)
        if cookie:
            region["events"].append(f"cookie:{int(cookie.group('hex'), 16):x}")
        tag = TAG_RE.search(line)
        if tag:
            region["events"].append(f"tag:{tag.group('value').strip()}")
        if END in line:
            region["end_line"] = line_number
            region["complete_delimiters"] = True
            region["fingerprint"] = _fingerprint(region)
            regions.append(region)
            region = None

    if region is not None:
        region["end_line"] = len(text.splitlines())
        region["fingerprint"] = _fingerprint(region)
        regions.append(region)

    return {
        "device_lost": device["device_lost"],
        "first_device_lost": device["first"],
        "breadcrumb_analysis": report_started,
        "breadcrumb_analysis_complete": report_complete,
        "regions": regions,
        "descriptor_qa_faults": parse_descriptor_qa_faults(text),
    }


def extract_breadcrumb_report(text: str) -> str:
    lines = text.splitlines()
    start: int | None = None
    end: int | None = None
    for index, line in enumerate(lines):
        if start is None and REPORT_BEGIN.lower() in line.lower():
            start = index
        if start is not None and REPORT_END.lower() in line.lower():
            end = index + 1
            break
    if start is None:
        return ""
    return "\n".join(lines[start:end]) + "\n"
