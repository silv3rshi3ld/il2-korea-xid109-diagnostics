#!/usr/bin/env python3
"""Verify the diagnostic manifest and every declared artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re


EXPECTED_COMMIT = "238f157e1d64f90e0d90593557c092ab8af6e0a3"
EXPECTED_REPOSITORY = "https://github.com/HansKristian-Work/vkd3d-proton.git"
EXPECTED_ARTIFACTS = {
    "x64/d3d12.dll",
    "x64/d3d12core.dll",
    "x86/d3d12.dll",
    "x86/d3d12core.dll",
}
EXPECTED_PE_MACHINES = {
    "x64/d3d12.dll": 0x8664,
    "x64/d3d12core.dll": 0x8664,
    "x86/d3d12.dll": 0x014C,
    "x86/d3d12core.dll": 0x014C,
}
ROOT = pathlib.Path(__file__).resolve().parents[1]


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pe_machine(path: pathlib.Path) -> int | None:
    with path.open("rb") as stream:
        header = stream.read(64)
        if len(header) < 64 or header[:2] != b"MZ":
            return None
        pe_offset = int.from_bytes(header[0x3C:0x40], "little")
        if pe_offset < 64 or pe_offset > path.stat().st_size - 6:
            return None
        stream.seek(pe_offset)
        if stream.read(4) != b"PE\0\0":
            return None
        return int.from_bytes(stream.read(2), "little")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=pathlib.Path, required=True)
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    parser.add_argument("--source-lock", type=pathlib.Path, default=ROOT / "build/source-lock.json")
    args = parser.parse_args()

    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"invalid build manifest: {exc}")
    try:
        source_lock = json.loads(args.source_lock.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"invalid source lock: {exc}")
    errors: list[str] = []
    if manifest.get("schema_version") != 1:
        errors.append("unsupported manifest schema")
    source = manifest.get("source", {})
    locked_source = source_lock.get("vkd3d_proton", {})
    if locked_source.get("commit") != EXPECTED_COMMIT or source.get("commit") != EXPECTED_COMMIT:
        errors.append("source commit does not match the source lock")
    if source.get("repository") != EXPECTED_REPOSITORY or locked_source.get("repository") != EXPECTED_REPOSITORY:
        errors.append("source repository does not match the source lock")
    if source.get("dirty") is not True or source.get("status_porcelain") != [" M libs/vkd3d/breadcrumbs.c"]:
        errors.append("source state is not exactly the one report-only patch")
    patches = source_lock.get("patches", [])
    expected_patch_sha = patches[0].get("sha256") if len(patches) == 1 else None
    manifest_patch = source.get("patch", {})
    patch_path = ROOT / patches[0].get("path", "") if len(patches) == 1 else None
    if not expected_patch_sha or manifest_patch.get("sha256") != expected_patch_sha:
        errors.append("diagnostic patch hash does not match the source lock")
    elif not patch_path or not patch_path.is_file() or sha256(patch_path) != expected_patch_sha:
        errors.append("repository diagnostic patch does not match the source lock")
    if not re.fullmatch(r"[0-9a-f]{64}", str(manifest_patch.get("diff_sha256", ""))):
        errors.append("manifest does not contain an exact source diff hash")
    for submodule, commit in locked_source.get("submodules", {}).items():
        if source.get("submodules", {}).get(submodule) != commit:
            errors.append(f"submodule does not match source lock: {submodule}")
    build = manifest.get("build", {})
    if (
        build.get("buildtype") != "release"
        or build.get("enable_trace") is not True
        or build.get("strip") is not True
        or build.get("meson_arguments") != source_lock.get("build", {}).get("meson_arguments")
    ):
        errors.append("build is not release + enable_trace")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        errors.append("manifest has no artifacts")
        artifacts = []
    declared_paths = [artifact.get("path") for artifact in artifacts]
    if set(declared_paths) != EXPECTED_ARTIFACTS or len(declared_paths) != len(EXPECTED_ARTIFACTS):
        errors.append("manifest artifact set is not exactly the expected four DLLs")
    for artifact in artifacts:
        relative = artifact.get("path")
        if not isinstance(relative, str) or relative.startswith("/") or ".." in pathlib.PurePath(relative).parts:
            errors.append(f"unsafe artifact path: {relative!r}")
            continue
        path = args.artifact_root / relative
        if path.is_symlink():
            errors.append(f"artifact must not be a symlink: {relative}")
            continue
        if not path.is_file():
            errors.append(f"missing artifact: {relative}")
            continue
        if path.stat().st_size != artifact.get("size"):
            errors.append(f"size mismatch: {relative}")
        if sha256(path) != artifact.get("sha256"):
            errors.append(f"SHA256 mismatch: {relative}")
        machine = pe_machine(path)
        if machine != EXPECTED_PE_MACHINES.get(relative):
            errors.append(f"artifact has an invalid PE header/architecture: {relative}")
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"verified {len(artifacts)} diagnostic DLL artifacts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
