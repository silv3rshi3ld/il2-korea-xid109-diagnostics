#!/usr/bin/env python3
"""Write a complete, deterministic-shape build provenance manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import subprocess
from datetime import datetime, timezone


def output(command: list[str], cwd: pathlib.Path | None = None) -> str:
    try:
        return subprocess.check_output(
            command,
            cwd=cwd,
            stderr=subprocess.STDOUT,
            text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        return f"unavailable: {exc}"


def checked_bytes(command: list[str], cwd: pathlib.Path) -> bytes:
    """Return exact output for provenance-bearing Git commands or fail the build."""
    return subprocess.check_output(command, cwd=cwd, stderr=subprocess.STDOUT)


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def first_line(value: str) -> str:
    return value.splitlines()[0] if value else "unavailable"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=pathlib.Path, required=True)
    parser.add_argument("--prefix", type=pathlib.Path, required=True)
    parser.add_argument("--patch", type=pathlib.Path, required=True)
    parser.add_argument("--started", required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()

    source = args.source.resolve()
    prefix = args.prefix.resolve()
    patch = args.patch.resolve()
    artifacts: list[dict[str, object]] = []
    for relative in (
        "x64/d3d12.dll",
        "x64/d3d12core.dll",
        "x86/d3d12.dll",
        "x86/d3d12core.dll",
    ):
        path = prefix / relative
        if not path.is_file():
            raise SystemExit(f"missing expected build artifact: {path}")
        artifacts.append(
            {
                "path": relative,
                "size": path.stat().st_size,
                "sha256": sha256(path),
            }
        )

    submodules: dict[str, str] = {}
    for line in output(["git", "submodule", "status", "--recursive"], source).splitlines():
        fields = line.lstrip("-+ ").split()
        if len(fields) >= 2:
            submodules[fields[1]] = fields[0]

    commands = {
        "git": ["git", "--version"],
        "meson": ["meson", "--version"],
        "ninja": ["ninja", "--version"],
        "x86_64-w64-mingw32-gcc": ["x86_64-w64-mingw32-gcc", "--version"],
        "i686-w64-mingw32-gcc": ["i686-w64-mingw32-gcc", "--version"],
        "x86_64-w64-mingw32-ld": ["x86_64-w64-mingw32-ld", "--version"],
        "i686-w64-mingw32-ld": ["i686-w64-mingw32-ld", "--version"],
        "glslangValidator": ["glslangValidator", "--version"],
        "widl": ["widl", "--help"],
        "x86_64-w64-mingw32-widl": ["x86_64-w64-mingw32-widl", "--version"],
        "i686-w64-mingw32-widl": ["i686-w64-mingw32-widl", "--version"],
        "python": ["python3", "--version"],
    }
    toolchain = {name: first_line(output(command)) for name, command in commands.items()}

    status_lines = checked_bytes(
        ["git", "status", "--porcelain=v1"], source
    ).decode("utf-8", errors="strict").splitlines()
    commit_epoch = int(output(["git", "show", "-s", "--format=%ct", "HEAD"], source))
    commit_time_utc = datetime.fromtimestamp(commit_epoch, timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    manifest = {
        "schema_version": 1,
        "build_started_utc": args.started,
        "build_finished_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": {
            "repository": "https://github.com/HansKristian-Work/vkd3d-proton.git",
            "commit": output(["git", "rev-parse", "HEAD"], source),
            "describe": output(["git", "describe", "--always", "--tags", "--dirty=+"], source),
            "commit_time_utc": commit_time_utc,
            "dirty": bool(status_lines),
            "status_porcelain": status_lines,
            "submodules": submodules,
            "patch": {
                "path": os.path.relpath(patch, args.output.parent.resolve()),
                "sha256": sha256(patch),
                "diff_sha256": hashlib.sha256(
                    checked_bytes(["git", "diff", "--binary"], source)
                ).hexdigest(),
            },
        },
        "build": {
            "buildtype": "release",
            "enable_trace": True,
            "strip": True,
            "meson_arguments": [
                "--buildtype=release",
                "--strip",
                "-Denable_trace=true",
            ],
            "source_date_epoch": os.environ.get("SOURCE_DATE_EPOCH", "unavailable"),
            "locale": os.environ.get("LC_ALL", "unavailable"),
            "timezone": os.environ.get("TZ", "unavailable"),
        },
        "toolchain": toolchain,
        "artifacts": artifacts,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
