"""Parse NVIDIA Xid events from journal or dmesg text."""

from __future__ import annotations

import re
from typing import Any


XID_RE = re.compile(
    r"Xid\s*\(PCI:(?P<pci>[0-9A-Fa-f:.]+)\):\s*(?P<xid>\d+)\b(?P<tail>.*)",
    re.IGNORECASE,
)
PID_RE = re.compile(r"\bpid[= ](?P<value>\d+)", re.IGNORECASE)
NAME_RE = re.compile(r"\bname[= ](?P<value>[^,\s]+)", re.IGNORECASE)
CHANNEL_RE = re.compile(r"\bchannel\s+(?P<value>0x[0-9A-Fa-f]+)", re.IGNORECASE)
INFO_RE = re.compile(r"\bInfo\s+(?P<value>0x[0-9A-Fa-f]+)", re.IGNORECASE)
ERROR_RE = re.compile(r"\berrorString\s+(?P<value>[^,]+)", re.IGNORECASE)
ISO_TIMESTAMP_RE = re.compile(
    r"^(?P<value>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?)"
)


def _hex_normalized(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return hex(int(value, 16))
    except ValueError:
        return value.lower()


def _search(regex: re.Pattern[str], text: str) -> str | None:
    match = regex.search(text)
    return match.group("value").strip() if match else None


def parse_kernel_log(text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        match = XID_RE.search(line)
        if not match:
            continue
        timestamp_match = ISO_TIMESTAMP_RE.match(line)
        raw_channel = _search(CHANNEL_RE, match.group("tail"))
        raw_info = _search(INFO_RE, match.group("tail"))
        events.append(
            {
                "timestamp": timestamp_match.group("value") if timestamp_match else None,
                "pci": match.group("pci").lower(),
                "xid": int(match.group("xid")),
                "pid": int(pid) if (pid := _search(PID_RE, match.group("tail"))) else None,
                "name": _search(NAME_RE, match.group("tail")),
                "channel": _hex_normalized(raw_channel),
                "channel_raw": raw_channel,
                "info": _hex_normalized(raw_info),
                "info_raw": raw_info,
                "error_string": _search(ERROR_RE, match.group("tail")),
                "line_number": line_number,
                "raw": line,
            }
        )
    return events
