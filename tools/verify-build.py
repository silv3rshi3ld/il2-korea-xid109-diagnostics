#!/usr/bin/env python3
"""Verify the diagnostic manifest and every declared artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib


EXPECTED_COMMIT = "238f157e1d64f90e0d90593557c092ab8af6e0a3"


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=pathlib.Path, required=True)
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    args = parser.parse_args()

    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"invalid build manifest: {exc}")
    errors: list[str] = []
    if manifest.get("source", {}).get("commit") != EXPECTED_COMMIT:
        errors.append("source commit does not match the source lock")
    build = manifest.get("build", {})
    if build.get("buildtype") != "release" or build.get("enable_trace") is not True:
        errors.append("build is not release + enable_trace")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        errors.append("manifest has no artifacts")
        artifacts = []
    for artifact in artifacts:
        relative = artifact.get("path")
        if not isinstance(relative, str) or relative.startswith("/") or ".." in pathlib.PurePath(relative).parts:
            errors.append(f"unsafe artifact path: {relative!r}")
            continue
        path = args.artifact_root / relative
        if not path.is_file():
            errors.append(f"missing artifact: {relative}")
            continue
        if path.stat().st_size != artifact.get("size"):
            errors.append(f"size mismatch: {relative}")
        if sha256(path) != artifact.get("sha256"):
            errors.append(f"SHA256 mismatch: {relative}")
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"verified {len(artifacts)} diagnostic DLL artifacts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
