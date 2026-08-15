"""Find the first device-lost observation in Proton-family logs."""

from __future__ import annotations

import re
from typing import Any


DEVICE_LOST_RE = re.compile(
    r"VK_ERROR_DEVICE_LOST|Device lost observed|DEVICE_LOST received|"
    r"device\s+[^\n]*\sis lost|DXGI_ERROR_DEVICE_(?:REMOVED|HUNG)",
    re.IGNORECASE,
)
ISO_TIMESTAMP_RE = re.compile(
    r"(?P<value>\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?)"
)


def parse_proton_log(text: str) -> dict[str, Any]:
    for line_number, line in enumerate(text.splitlines(), start=1):
        if DEVICE_LOST_RE.search(line):
            timestamp = ISO_TIMESTAMP_RE.search(line)
            return {
                "device_lost": True,
                "first": {
                    "line_number": line_number,
                    "timestamp": timestamp.group("value") if timestamp else None,
                    "text": line,
                },
            }
    return {"device_lost": False, "first": None}
