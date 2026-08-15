#!/usr/bin/env python3
"""Verify every file declared by an extracted prepared tester bundle."""

from __future__ import annotations

import argparse
import hashlib
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
    if not checksum_file.is_file():
        raise SystemExit("not a prepared tester bundle: bundle-checksums.sha256 is missing")
    errors: list[str] = []
    count = 0
    for line in checksum_file.read_text(encoding="utf-8").splitlines():
        match = LINE_RE.match(line)
        if not match:
            errors.append(f"malformed checksum line: {line!r}")
            continue
        relative = pathlib.PurePosixPath(match.group("path"))
        if relative.is_absolute() or ".." in relative.parts:
            errors.append(f"unsafe checksum path: {relative}")
            continue
        path = root.joinpath(*relative.parts)
        if path.is_symlink():
            errors.append(f"unsafe symlink in bundle: {relative}")
        elif not path.is_file():
            errors.append(f"missing bundle file: {relative}")
        elif sha256(path) != match.group("digest"):
            errors.append(f"checksum mismatch: {relative}")
        count += 1
    if count == 0:
        errors.append("bundle checksum list is empty")
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"verified {count} prepared-bundle files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
