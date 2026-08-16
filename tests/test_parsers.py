from __future__ import annotations

import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analyzer.parsers import (  # noqa: E402
    extract_breadcrumb_report,
    parse_kernel_log,
    parse_proton_log,
    parse_vkd3d_log,
)


FIXTURES = ROOT / "tests/fixtures"


class KernelParserTests(unittest.TestCase):
    def test_parses_and_normalizes_xid109(self) -> None:
        events = parse_kernel_log((FIXTURES / "kernel-xid109.log").read_text())
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event["xid"], 109)
        self.assertEqual(event["pci"], "0000:01:00")
        self.assertEqual(event["pid"], 4242)
        self.assertEqual(event["name"], "IL2Series.exe")
        self.assertEqual(event["channel"], "0x28")
        self.assertEqual(event["channel_raw"], "0x00000028")
        self.assertEqual(event["info"], "0x1c022")
        self.assertEqual(event["error_string"], "CTX SWITCH TIMEOUT")
        self.assertTrue(event["timestamp"].startswith("2026-08-15T14:32:10"))

    def test_ignores_non_xid_text(self) -> None:
        self.assertEqual(parse_kernel_log("NVRM initialized\nunrelated\n"), [])


class ProtonParserTests(unittest.TestCase):
    def test_finds_first_device_lost(self) -> None:
        result = parse_proton_log((FIXTURES / "proton-device-lost.log").read_text())
        self.assertTrue(result["device_lost"])
        self.assertEqual(result["first"]["line_number"], 2)
        self.assertIn("VK_ERROR_DEVICE_LOST", result["first"]["text"])


class Vkd3dParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = (FIXTURES / "vkd3d-breadcrumb.log").read_text()

    def test_parses_checkpoint_region(self) -> None:
        result = parse_vkd3d_log(self.text)
        self.assertTrue(result["device_lost"])
        self.assertTrue(result["breadcrumb_analysis"])
        self.assertTrue(result["breadcrumb_analysis_complete"])
        self.assertEqual(len(result["regions"]), 1)
        region = result["regions"][0]
        self.assertEqual(region["queue"], {"type": "direct", "index": 0})
        self.assertEqual(region["checkpoint"]["bottom_context"], 17)
        self.assertEqual(region["checkpoint"]["top_marker"], 43)
        self.assertEqual(region["checkpoint"]["bottom_marker"], 41)
        self.assertEqual(region["commands"], ["dispatch", "barrier"])
        self.assertEqual(
            region["shaders"],
            [{"hash": "0123456789abcdef", "stage": "20"}],
        )
        self.assertEqual(
            region["events"],
            [
                "shader:0123456789abcdef:20",
                "command:dispatch",
                "arg:80",
                "command:barrier",
            ],
        )
        self.assertRegex(region["fingerprint"], r"^[0-9a-f]{64}$")

    def test_extracts_only_breadcrumb_report(self) -> None:
        report = extract_breadcrumb_report(self.text)
        self.assertTrue(report.startswith("00e4:err:vkd3d_breadcrumb_tracer_report_device_lost"))
        self.assertTrue(report.rstrip().endswith("Done analyzing breadcrumbs ..."))
        self.assertNotIn("Device 0000000000000001 is lost", report)

    def test_retains_unclosed_region(self) -> None:
        result = parse_vkd3d_log(
            "Device lost observed, analyzing breadcrumbs ...\n"
            "===== Potential crash region BEGIN =====\n"
            "Command: draw_indexed\n"
        )
        self.assertEqual(result["regions"][0]["commands"], ["draw_indexed"])
        self.assertFalse(result["regions"][0]["complete_delimiters"])
        self.assertFalse(result["breadcrumb_analysis_complete"])

    def test_complete_report_can_retain_an_open_ended_region(self) -> None:
        result = parse_vkd3d_log(
            "Device lost observed, analyzing breadcrumbs ...\n"
            "===== Potential crash region BEGIN =====\n"
            "Command: draw_indexed\n"
            "Done analyzing breadcrumbs ...\n"
        )
        self.assertTrue(result["breadcrumb_analysis_complete"])
        self.assertFalse(result["regions"][0]["complete_delimiters"])

    def test_resource_cookie_values_do_not_prevent_region_matching(self) -> None:
        first = parse_vkd3d_log(
            "Reporting NVIDIA checkpoints for direct queue 0.\n"
            "===== Potential crash region BEGIN =====\n"
            "Cookie: 1 (#1)\nCommand: dispatch\n"
            "===== Potential crash region END =====\n"
        )["regions"][0]
        second = parse_vkd3d_log(
            "Reporting NVIDIA checkpoints for direct queue 0.\n"
            "===== Potential crash region BEGIN =====\n"
            "Cookie: 999 (#3e7)\nCommand: dispatch\n"
            "===== Potential crash region END =====\n"
        )["regions"][0]
        self.assertNotEqual(first["events"], second["events"])
        self.assertEqual(first["fingerprint"], second["fingerprint"])


if __name__ == "__main__":
    unittest.main()
