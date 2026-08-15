#!/usr/bin/env python3
"""Create and finalize per-run machine-readable artifacts using the stdlib only."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import shutil
from datetime import datetime, timezone
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in os.sys.path:
    os.sys.path.insert(0, str(REPO_ROOT))

from analyzer.parsers import (  # noqa: E402
    extract_breadcrumb_report,
    parse_kernel_log,
    parse_proton_log,
    parse_vkd3d_log,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path: pathlib.Path, default: Any = None) -> Any:
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_json(path: pathlib.Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def file_sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def command_init(args: argparse.Namespace) -> int:
    build_manifest = load_json(args.build_manifest, {})
    source_lock = load_json(REPO_ROOT / "build/source-lock.json", {})
    policy = load_json(REPO_ROOT / "config/test-policy.json", {})
    metadata = {
        "schema_version": 1,
        "app_id": 247970,
        "case": args.case,
        "case_description": args.description,
        "diagnostic_environment": {
            "VKD3D_CONFIG": args.vkd3d_config,
            "VKD3D_DISABLE_EXTENSIONS": args.disabled_extensions or None,
            "VKD3D_DEBUG": "info",
            "VKD3D_SHADER_DEBUG": "err",
            "PROTON_LOG": "1",
        },
        "start_utc": args.start,
        "end_utc": None,
        "duration_seconds": None,
        "no_xid_observation_target_seconds": policy.get("no_xid_observation_seconds", 600),
        "proton_exit_code": None,
        "capture_complete": False,
        "capture_interrupted": False,
        "recovered_after_interruption": False,
        "harness_git_commit": args.harness_commit,
        "failing_build_lock": source_lock.get("failing_proton", {}),
        "diagnostic_build": build_manifest,
    }
    atomic_json(args.output, metadata)
    return 0


def command_finish(args: argparse.Namespace) -> int:
    metadata = load_json(args.metadata, {})
    metadata["end_utc"] = args.end
    metadata["duration_seconds"] = args.duration
    metadata["proton_exit_code"] = args.exit_code
    metadata["capture_complete"] = True
    metadata["capture_interrupted"] = args.interrupted
    metadata["recovered_after_interruption"] = args.recovered
    metadata["capture_warnings"] = args.warning
    atomic_json(args.metadata, metadata)
    return 0


def _shader_type(suffix: str) -> str:
    return {
        ".dxil": "DXIL",
        ".dxbc": "DXBC",
        ".spv": "SPIR-V",
    }.get(suffix.lower(), suffix.lstrip(".").upper() or "unknown")


def _deduplicate(path: pathlib.Path, store: pathlib.Path, digest: str) -> bool:
    store.mkdir(parents=True, exist_ok=True)
    canonical = store / digest
    if not canonical.exists():
        try:
            os.link(path, canonical)
        except OSError:
            shutil.copy2(path, canonical)
        return False
    if canonical.stat().st_size != path.stat().st_size or file_sha256(canonical) != digest:
        raise RuntimeError(f"content-addressed shader collision: {digest}")
    try:
        temporary = path.with_name(path.name + ".dedup.tmp")
        if temporary.exists():
            temporary.unlink()
        os.link(canonical, temporary)
        temporary.replace(path)
        return True
    except OSError:
        return False


def command_shaders(args: argparse.Namespace) -> int:
    entries: list[dict[str, Any]] = []
    store = args.results_root / ".shader-store"
    if args.directory.is_dir():
        for path in sorted(item for item in args.directory.rglob("*") if item.is_file()):
            digest = file_sha256(path)
            deduplicated = _deduplicate(path, store, digest)
            stem = path.stem.lower()
            entries.append(
                {
                    "vkd3d_hash": stem if all(c in "0123456789abcdef" for c in stem) else None,
                    "file": path.relative_to(args.run_dir).as_posix(),
                    "type": _shader_type(path.suffix),
                    "byte_size": path.stat().st_size,
                    "sha256": digest,
                    "deduplicated": deduplicated,
                }
            )
    atomic_json(
        args.output,
        {
            "schema_version": 1,
            "generated_utc": utc_now(),
            "shaders": entries,
        },
    )
    return 0


def command_xids(args: argparse.Namespace) -> int:
    text = args.input.read_text(encoding="utf-8", errors="replace") if args.input.is_file() else ""
    atomic_json(
        args.output,
        {
            "schema_version": 1,
            "generated_utc": utc_now(),
            "events": parse_kernel_log(text),
        },
    )
    return 0


def command_breadcrumbs(args: argparse.Namespace) -> int:
    text = args.input.read_text(encoding="utf-8", errors="replace") if args.input.is_file() else ""
    args.output.write_text(extract_breadcrumb_report(text), encoding="utf-8")
    return 0


def command_summary(args: argparse.Namespace) -> int:
    run_dir = args.run_dir
    metadata = load_json(run_dir / "metadata.json", {})
    xid_data = load_json(run_dir / "xid-events.json", {"events": []})
    events = xid_data.get("events", [])
    xid109 = [
        event
        for event in events
        if event.get("xid") == 109
        and str(event.get("name") or "").casefold() == "il2series.exe"
    ]
    vkd3d_text = (run_dir / "vkd3d.log").read_text(encoding="utf-8", errors="replace") \
        if (run_dir / "vkd3d.log").is_file() else ""
    proton_text = (run_dir / "proton.log").read_text(encoding="utf-8", errors="replace") \
        if (run_dir / "proton.log").is_file() else ""
    vkd3d = parse_vkd3d_log(vkd3d_text)
    proton = parse_proton_log(proton_text)
    regions = vkd3d["regions"]

    lines = [
        f"Run: {run_dir.name}",
        f"Case: {metadata.get('case', 'unknown')}",
        f"Duration: {metadata.get('duration_seconds', 'unknown')} seconds",
        "",
        "OBSERVED",
        f"- Xid 109: {'yes' if xid109 else 'no'}",
        f"- VK_ERROR_DEVICE_LOST/device removed: {'yes' if vkd3d['device_lost'] or proton['device_lost'] else 'no'}",
        f"- Breadcrumb crash regions: {len(regions)}",
        f"- Dumped shaders: {len(load_json(run_dir / 'shader-manifest.json', {'shaders': []}).get('shaders', []))}",
        f"- Capture interrupted/recovered: "
        f"{'yes' if metadata.get('capture_interrupted') or metadata.get('recovered_after_interruption') else 'no'}",
    ]
    if xid109:
        event = xid109[0]
        lines.append(
            f"- First Xid 109: PCI {event.get('pci')}, channel {event.get('channel')}, "
            f"Info {event.get('info')}, timestamp {event.get('timestamp')}"
        )
    if regions:
        region = regions[0]
        checkpoint = region.get("checkpoint") or {}
        lines.append(
            f"- First crash region: queue {region.get('queue')}, "
            f"last completed marker {checkpoint.get('bottom_marker')}, "
            f"top marker {checkpoint.get('top_marker')}, commands {', '.join(region['commands']) or 'none parsed'}"
        )
        lines.append(
            "- Region shader hashes: "
            + (", ".join(shader["hash"] for shader in region["shaders"]) or "none parsed")
        )
    lines.extend(
        [
            "",
            "INFERRED",
            "- No causal inference is made from one run. Compare completed cases with analyzer/analyze.py.",
            "",
            "PROVEN",
            "- No root cause is proven by this run summary.",
        ]
    )
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init")
    init.add_argument("--output", type=pathlib.Path, required=True)
    init.add_argument("--case", required=True)
    init.add_argument("--description", required=True)
    init.add_argument("--vkd3d-config", required=True)
    init.add_argument("--disabled-extensions", default="")
    init.add_argument("--start", required=True)
    init.add_argument("--build-manifest", type=pathlib.Path, required=True)
    init.add_argument("--harness-commit", required=True)
    init.set_defaults(func=command_init)

    finish = subparsers.add_parser("finish")
    finish.add_argument("--metadata", type=pathlib.Path, required=True)
    finish.add_argument("--end", required=True)
    finish.add_argument("--duration", type=int, required=True)
    finish.add_argument("--exit-code", type=int)
    finish.add_argument("--interrupted", action="store_true")
    finish.add_argument("--recovered", action="store_true")
    finish.add_argument("--warning", action="append", default=[])
    finish.set_defaults(func=command_finish)

    shaders = subparsers.add_parser("shaders")
    shaders.add_argument("--directory", type=pathlib.Path, required=True)
    shaders.add_argument("--run-dir", type=pathlib.Path, required=True)
    shaders.add_argument("--results-root", type=pathlib.Path, required=True)
    shaders.add_argument("--output", type=pathlib.Path, required=True)
    shaders.set_defaults(func=command_shaders)

    xids = subparsers.add_parser("xids")
    xids.add_argument("--input", type=pathlib.Path, required=True)
    xids.add_argument("--output", type=pathlib.Path, required=True)
    xids.set_defaults(func=command_xids)

    breadcrumbs = subparsers.add_parser("breadcrumbs")
    breadcrumbs.add_argument("--input", type=pathlib.Path, required=True)
    breadcrumbs.add_argument("--output", type=pathlib.Path, required=True)
    breadcrumbs.set_defaults(func=command_breadcrumbs)

    summary = subparsers.add_parser("summary")
    summary.add_argument("--run-dir", type=pathlib.Path, required=True)
    summary.add_argument("--output", type=pathlib.Path, required=True)
    summary.set_defaults(func=command_summary)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
