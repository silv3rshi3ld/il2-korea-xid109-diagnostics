#!/usr/bin/env python3
"""Verify every file declared by an extracted prepared tester bundle."""

from __future__ import annotations

import argparse
import hashlib
import os
import pathlib
import re


LINE_RE = re.compile(r"^(?P<digest>[0-9a-f]{64})  (?P<path>.+)$")


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    checksum_file = root / "bundle-checksums.sha256"
    if checksum_file.is_symlink() or not checksum_file.is_file():
        raise SystemExit("not a prepared tester bundle: bundle-checksums.sha256 is missing")
    errors: list[str] = []
    count = 0
    declared: set[pathlib.PurePosixPath] = set()
    for line in checksum_file.read_text(encoding="utf-8").splitlines():
        match = LINE_RE.match(line)
        if not match:
            errors.append(f"malformed checksum line: {line!r}")
            continue
        relative = pathlib.PurePosixPath(match.group("path"))
        if relative.is_absolute() or ".." in relative.parts:
            errors.append(f"unsafe checksum path: {relative}")
            continue
        if relative == pathlib.PurePosixPath(checksum_file.name):
            errors.append("bundle checksum file must not declare itself")
            continue
        if relative in declared:
            errors.append(f"duplicate checksum path: {relative}")
            continue
        declared.add(relative)
        path = root.joinpath(*relative.parts)
        if path.is_symlink():
            errors.append(f"unsafe symlink in bundle: {relative}")
        elif not path.is_file():
            errors.append(f"missing bundle file: {relative}")
        elif sha256(path) != match.group("digest"):
            errors.append(f"checksum mismatch: {relative}")
        count += 1
    actual: set[pathlib.PurePosixPath] = set()
    for directory, directory_names, file_names in os.walk(root, followlinks=False):
        directory_path = pathlib.Path(directory)
        for name in directory_names:
            path = directory_path / name
            if path.is_symlink():
                relative = pathlib.PurePosixPath(path.relative_to(root).as_posix())
                errors.append(f"unsafe symlink in bundle: {relative}")
        for name in file_names:
            path = directory_path / name
            relative = pathlib.PurePosixPath(path.relative_to(root).as_posix())
            if relative == pathlib.PurePosixPath(checksum_file.name):
                continue
            if path.is_symlink():
                errors.append(f"unsafe symlink in bundle: {relative}")
            elif not path.is_file():
                errors.append(f"unsafe non-regular file in bundle: {relative}")
            else:
                actual.add(relative)
    for relative in sorted(actual - declared, key=str):
        errors.append(f"unlisted bundle file: {relative}")
    if count == 0:
        errors.append("bundle checksum list is empty")
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"verified {count} prepared-bundle files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
