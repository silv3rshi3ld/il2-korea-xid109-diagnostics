#!/usr/bin/env python3
"""Merge journal captures while preserving order and removing exact duplicate lines."""

from __future__ import annotations

import argparse
import pathlib


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("inputs", nargs="*", type=pathlib.Path)
    args = parser.parse_args()

    seen: set[str] = set()
    merged: list[str] = []
    for path in args.inputs:
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line not in seen:
                seen.add(line)
                merged.append(line)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text("\n".join(merged) + ("\n" if merged else ""), encoding="utf-8")
    temporary.replace(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
