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
EXPECTED_PATCH_SHA256 = "40933324b9e33079dd95197cc0fe34b857e21225aed427c6db8786afa4f51297"
EXPECTED_DIFF_SHA256 = "87ff08af931dcfd04acb3000333f716c71117069667da6b3b4c0ddf1d81325be"
EXPECTED_PATCH_PATH = "build/patches/0001-label-nvidia-checkpoint-queues.patch"
EXPECTED_SUBMODULES = {
    "khronos/SPIRV-Headers": "f88a2d766840fc825af1fc065977953ba1fa4a91",
    "khronos/Vulkan-Headers": "0e9de566b7d4051c5cc1b762e242c46565956bdf",
    "subprojects/dxil-spirv": "cc75a0c98d34d7bcc03560527c799b52e48b4d1f",
    "subprojects/dxil-spirv/subprojects/dxbc-spirv": "d5b06435fd84843d4c9ee7b3b42d2f3b7b8e3f1a",
    "subprojects/dxil-spirv/subprojects/dxbc-spirv/submodules/spirv_headers": "c8ad050fcb29e42a2f57d9f59e97488f465c436d",
    "subprojects/dxil-spirv/third_party/SPIRV-Cross": "4b7bcb7e5cf71015b3299088d22004bfe4e13a5e",
    "subprojects/dxil-spirv/third_party/SPIRV-Tools": "199cb207b911501ddd76dcddf100a6e21c15ef23",
    "subprojects/dxil-spirv/third_party/spirv-headers": "c63848ecf2200425511319fd8bf2c17b751e501e",
}
EXPECTED_TOOLCHAIN_KEYS = {
    "git",
    "glslangValidator",
    "i686-w64-mingw32-gcc",
    "i686-w64-mingw32-ld",
    "i686-w64-mingw32-widl",
    "meson",
    "ninja",
    "python",
    "widl",
    "x86_64-w64-mingw32-gcc",
    "x86_64-w64-mingw32-ld",
    "x86_64-w64-mingw32-widl",
}
REQUIRED_TOOLCHAINS = EXPECTED_TOOLCHAIN_KEYS - {
    "widl",
    "x86_64-w64-mingw32-widl",
    "i686-w64-mingw32-widl",
}
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


def available_tool(value: object) -> bool:
    return bool(
        isinstance(value, str)
        and value.strip()
        and not value.casefold().startswith("unavailable")
    )


def safe_artifact_path(root: pathlib.Path, relative: str) -> pathlib.Path | None:
    if root.is_symlink() or not root.is_dir():
        return None
    current = root
    for part in pathlib.PurePosixPath(relative).parts:
        current /= part
        if current.is_symlink():
            return None
    try:
        resolved_root = root.resolve(strict=True)
        resolved = current.resolve(strict=True)
    except OSError:
        return None
    if not resolved.is_relative_to(resolved_root) or not resolved.is_file():
        return None
    return resolved


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
    if not isinstance(manifest, dict):
        raise SystemExit("build manifest must be a JSON object")
    if not isinstance(source_lock, dict):
        raise SystemExit("source lock must be a JSON object")
    if source_lock.get("schema_version") != 1:
        errors.append("unsupported source-lock schema")
    if manifest.get("schema_version") != 1:
        errors.append("unsupported manifest schema")
    timestamp_pattern = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
    for field in ("build_started_utc", "build_finished_utc"):
        if not timestamp_pattern.fullmatch(str(manifest.get(field, ""))):
            errors.append(f"manifest has an invalid or missing {field}")
    toolchain = manifest.get("toolchain")
    if not isinstance(toolchain, dict) or set(toolchain) != EXPECTED_TOOLCHAIN_KEYS:
        errors.append("manifest has no toolchain provenance")
    else:
        if any(not available_tool(toolchain.get(name)) for name in REQUIRED_TOOLCHAINS):
            errors.append("manifest has unavailable required build tools")
        widl_available = available_tool(toolchain.get("widl")) or (
            available_tool(toolchain.get("x86_64-w64-mingw32-widl"))
            and available_tool(toolchain.get("i686-w64-mingw32-widl"))
        )
        if not widl_available:
            errors.append("manifest has no usable WIDL toolchain provenance")
    source = manifest.get("source", {})
    locked_source = source_lock.get("vkd3d_proton", {})
    if not isinstance(source, dict) or not isinstance(locked_source, dict):
        raise SystemExit("manifest and source lock must contain source objects")
    if locked_source.get("commit") != EXPECTED_COMMIT or source.get("commit") != EXPECTED_COMMIT:
        errors.append("source commit does not match the source lock")
    if source.get("repository") != EXPECTED_REPOSITORY or locked_source.get("repository") != EXPECTED_REPOSITORY:
        errors.append("source repository does not match the source lock")
    if source.get("dirty") is not True or source.get("status_porcelain") != [" M libs/vkd3d/breadcrumbs.c"]:
        errors.append("source state is not exactly the one report-only patch")
    patches = source_lock.get("patches", [])
    locked_patch = patches[0] if (
        isinstance(patches, list) and len(patches) == 1 and isinstance(patches[0], dict)
    ) else {}
    expected_patch_sha = locked_patch.get("sha256")
    expected_diff_sha = locked_patch.get("diff_sha256")
    manifest_patch = source.get("patch", {})
    if not isinstance(manifest_patch, dict):
        manifest_patch = {}
    locked_patch_path = locked_patch.get("path")
    patch_path = ROOT / EXPECTED_PATCH_PATH
    if locked_patch_path != EXPECTED_PATCH_PATH or manifest_patch.get("path") != EXPECTED_PATCH_PATH:
        errors.append("diagnostic patch path does not match the source lock")
    if (
        expected_patch_sha != EXPECTED_PATCH_SHA256
        or manifest_patch.get("sha256") != EXPECTED_PATCH_SHA256
    ):
        errors.append("diagnostic patch hash does not match the source lock")
    elif not patch_path or not patch_path.is_file() or sha256(patch_path) != expected_patch_sha:
        errors.append("repository diagnostic patch does not match the source lock")
    if (
        expected_diff_sha != EXPECTED_DIFF_SHA256
        or manifest_patch.get("diff_sha256") != EXPECTED_DIFF_SHA256
    ):
        errors.append("exact source diff hash does not match the source lock")
    if locked_source.get("submodules") != EXPECTED_SUBMODULES:
        errors.append("source lock does not contain the exact recursive submodule set")
    if source.get("submodules") != EXPECTED_SUBMODULES:
        errors.append("manifest does not contain the exact recursive submodule set")
    build = manifest.get("build", {})
    locked_build = source_lock.get("build", {})
    if not isinstance(build, dict) or not isinstance(locked_build, dict):
        raise SystemExit("manifest and source lock must contain build objects")
    if (
        build.get("buildtype") != "release"
        or build.get("enable_trace") is not True
        or build.get("strip") is not True
        or build.get("meson_arguments") != locked_build.get("meson_arguments")
        or build.get("source_date_epoch") != locked_build.get("source_date_epoch")
        or build.get("locale") != "C"
        or locked_build.get("locale") != "C"
        or build.get("timezone") != "UTC"
        or locked_build.get("timezone") != "UTC"
    ):
        errors.append("build settings or reproducibility environment do not match the source lock")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        errors.append("manifest has no artifacts")
        artifacts = []
    if not all(isinstance(artifact, dict) for artifact in artifacts):
        errors.append("each manifest artifact must be an object")
        artifacts = [artifact for artifact in artifacts if isinstance(artifact, dict)]
    declared_paths = [artifact.get("path") for artifact in artifacts]
    if (
        not all(isinstance(path, str) for path in declared_paths)
        or set(declared_paths) != EXPECTED_ARTIFACTS
        or len(declared_paths) != len(EXPECTED_ARTIFACTS)
    ):
        errors.append("manifest artifact set is not exactly the expected four DLLs")
    for artifact in artifacts:
        relative = artifact.get("path")
        if not isinstance(relative, str) or relative.startswith("/") or ".." in pathlib.PurePath(relative).parts:
            errors.append(f"unsafe artifact path: {relative!r}")
            continue
        path = safe_artifact_path(args.artifact_root, relative)
        if path is None:
            errors.append(f"missing or unsafe artifact path: {relative}")
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
