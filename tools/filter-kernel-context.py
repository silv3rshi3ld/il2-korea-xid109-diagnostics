#!/usr/bin/env python3
"""Keep matching kernel lines plus nearby context without external dependencies."""

from __future__ import annotations

import argparse
import pathlib
import re


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--context", type=int, default=8)
    args = parser.parse_args()

    if not args.input.is_file():
        args.output.write_text("", encoding="utf-8")
        return 0
    lines = args.input.read_text(encoding="utf-8", errors="replace").splitlines()
    pattern = re.compile(r"NVRM|Xid|CTX SWITCH TIMEOUT|IL2Series\.exe", re.IGNORECASE)
    selected: set[int] = set()
    for index, line in enumerate(lines):
        if pattern.search(line):
            begin = max(0, index - args.context)
            end = min(len(lines), index + args.context + 1)
            selected.update(range(begin, end))
    args.output.write_text(
        "\n".join(line for index, line in enumerate(lines) if index in selected)
        + ("\n" if selected else ""),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
