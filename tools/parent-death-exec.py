#!/usr/bin/env python3
"""Exec a child that receives SIGTERM if this launcher process disappears."""

from __future__ import annotations

import ctypes
import os
import signal
import sys


PR_SET_PDEATHSIG = 1


def arm_parent_death_signal() -> None:
    original_parent = os.getppid()
    if original_parent <= 1:
        raise RuntimeError("parent process is already unavailable")
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(PR_SET_PDEATHSIG, signal.SIGTERM, 0, 0, 0) != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))
    if os.getppid() != original_parent:
        os.kill(os.getpid(), signal.SIGTERM)


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1] == "--self-test":
        arm_parent_death_signal()
        print("parent-death signal support is available")
        return 0
    if len(sys.argv) < 2:
        raise SystemExit("usage: parent-death-exec.py COMMAND [ARGUMENT ...]")
    arm_parent_death_signal()
    os.execvp(sys.argv[1], sys.argv[1:])
    return 127


if __name__ == "__main__":
    raise SystemExit(main())
