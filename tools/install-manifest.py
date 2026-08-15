#!/usr/bin/env python3
"""Create the custom compatibility-tool installation manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
from datetime import datetime, timezone


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--baseline", type=pathlib.Path, required=True)
    parser.add_argument("--baseline-version", required=True)
    parser.add_argument("--baseline-vkd3d-version", required=True)
    parser.add_argument("--original-core", type=pathlib.Path, required=True)
    parser.add_argument("--diagnostic-core", type=pathlib.Path, required=True)
    parser.add_argument("--build-manifest", type=pathlib.Path, required=True)
    parser.add_argument("--harness-commit", required=True)
    args = parser.parse_args()

    value = {
        "schema_version": 1,
        "installed_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "baseline": {
            "path": str(args.baseline),
            "version": args.baseline_version,
            "vkd3d_version": args.baseline_vkd3d_version,
            "d3d12core_x64_sha256": sha256(args.original_core),
        },
        "diagnostic": {
            "d3d12core_x64_sha256": sha256(args.diagnostic_core),
            "build_manifest_sha256": sha256(args.build_manifest),
        },
        "harness_git_commit": args.harness_commit,
        "installed_components": [
            "files/lib/wine/vkd3d-proton/x86_64-windows/d3d12core.dll",
            "proton wrapper",
            "diagnostic state and launch collector",
            "compatibilitytool.vdf",
        ],
    }
    temporary = args.output.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
