from __future__ import annotations

import hashlib
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import analyzer.analyze as analysis  # noqa: E402


FIXTURES = ROOT / "tests/fixtures"


class AnalyzerIntegrationTests(unittest.TestCase):
    def make_run(self, root: pathlib.Path, timestamp: str, case: str) -> pathlib.Path:
        run = root / f"{timestamp}-{case}"
        shaders = run / "shaders"
        shaders.mkdir(parents=True)
        (run / "metadata.json").write_text(
            json.dumps(
                {
                    "case": case,
                    "start_utc": "2026-08-15T12:00:00Z",
                    "duration_seconds": 90,
                    "proton_exit_code": 0,
                    "capture_complete": True,
                    "capture_warnings": [],
                }
            )
        )
        for source_name, destination_name in (
            ("kernel-xid109.log", "kernel-full.log"),
            ("vkd3d-breadcrumb.log", "vkd3d.log"),
            ("proton-device-lost.log", "proton.log"),
        ):
            (run / destination_name).write_text((FIXTURES / source_name).read_text())
        dxil = shaders / "0123456789abcdef.dxil"
        spv = shaders / "0123456789abcdef.spv"
        dxil.write_bytes(b"synthetic dxil")
        spv.write_bytes(b"synthetic spv")
        entries = []
        for path, shader_type in ((dxil, "DXIL"), (spv, "SPIR-V")):
            entries.append(
                {
                    "vkd3d_hash": "0123456789abcdef",
                    "file": path.relative_to(run).as_posix(),
                    "type": shader_type,
                    "byte_size": path.stat().st_size,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "deduplicated": False,
                }
            )
        (run / "shader-manifest.json").write_text(json.dumps({"shaders": entries}))
        return run

    def test_two_matching_failures_generate_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            first = analysis.summarize_run(self.make_run(root, "2026-08-15T120000Z", "baseline"))
            second = analysis.summarize_run(
                self.make_run(root, "2026-08-15T120500Z", "no-descriptor-buffer")
            )
            self.assertTrue(first["xid109"])
            self.assertTrue(first["device_lost"])
            self.assertEqual(first["primary_region_fingerprint"], second["primary_region_fingerprint"])
            with mock.patch.object(analysis, "RESULTS_ROOT", root):
                candidate = analysis.generate_candidate([first, second])
            self.assertIsNotNone(candidate)
            bundle = root / "culprit-candidate"
            self.assertTrue((bundle / "0123456789abcdef.dxil").is_file())
            self.assertTrue((bundle / "0123456789abcdef.spv").is_file())
            self.assertIn("CANDIDATE CRASH REGION", (bundle / "README.md").read_text())
            self.assertNotIn("ROOT CAUSE", (bundle / "README.md").read_text())
            candidate_again = analysis.generate_candidate([first, second])
            self.assertEqual(candidate_again["fingerprint"], candidate["fingerprint"])
            self.assertFalse(any(root.glob("culprit-candidate.previous-*")))

    def test_one_failure_does_not_generate_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            only = analysis.summarize_run(self.make_run(root, "2026-08-15T120000Z", "baseline"))
            with mock.patch.object(analysis, "RESULTS_ROOT", root):
                self.assertIsNone(analysis.generate_candidate([only]))
            self.assertFalse((root / "culprit-candidate").exists())

    def test_matching_nonfirst_region_can_generate_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            first_path = self.make_run(root, "2026-08-15T120000Z", "baseline")
            second_path = self.make_run(root, "2026-08-15T120500Z", "single-queue")
            original = (FIXTURES / "vkd3d-breadcrumb.log").read_text()
            different = (
                original.replace("direct queue 0", "compute queue 0")
                .replace("0123456789abcdef", "fedcba9876543210")
                .replace("Command: dispatch", "Command: draw")
                .replace("Done analyzing breadcrumbs ...", "")
            )
            (second_path / "vkd3d.log").write_text(different + original)
            first = analysis.summarize_run(first_path)
            second = analysis.summarize_run(second_path)
            self.assertNotEqual(
                first["primary_region_fingerprint"], second["primary_region_fingerprint"]
            )
            with mock.patch.object(analysis, "RESULTS_ROOT", root):
                candidate = analysis.generate_candidate([first, second])
            self.assertIsNotNone(candidate)
            self.assertEqual(candidate["source_regions"][1]["region_index"], 1)

    def test_short_no_xid_run_is_not_used_as_stability_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            baseline = analysis.summarize_run(
                self.make_run(root, "2026-08-15T120000Z", "baseline")
            )
            comparison_path = self.make_run(
                root, "2026-08-15T120500Z", "single-queue"
            )
            (comparison_path / "kernel-full.log").write_text("")
            (comparison_path / "xid-events.json").write_text(json.dumps({"events": []}))
            (comparison_path / "vkd3d.log").write_text("")
            (comparison_path / "proton.log").write_text("")
            comparison = analysis.summarize_run(comparison_path)
            self.assertFalse(comparison["valid_no_xid_observation"])
            evidence = analysis.build_evidence([baseline, comparison])
            self.assertFalse(any("Queue topology" in item for item in evidence["inferred"]))

    def test_clean_ten_minute_no_xid_run_is_valid(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            run_path = self.make_run(root, "2026-08-15T120500Z", "single-queue")
            metadata = json.loads((run_path / "metadata.json").read_text())
            metadata["duration_seconds"] = 600
            (run_path / "metadata.json").write_text(json.dumps(metadata))
            (run_path / "kernel-full.log").write_text("")
            (run_path / "xid-events.json").write_text(json.dumps({"events": []}))
            (run_path / "vkd3d.log").write_text("")
            (run_path / "proton.log").write_text("")
            run = analysis.summarize_run(run_path)
            self.assertTrue(run["valid_no_xid_observation"])

    def test_report_uses_evidence_levels(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            run = analysis.summarize_run(self.make_run(root, "2026-08-15T120000Z", "baseline"))
            evidence = analysis.build_evidence([run])
            report = analysis.markdown([run], evidence, None)
            self.assertIn("## OBSERVED", report)
            self.assertIn("## INFERRED", report)
            self.assertIn("## PROVEN", report)
            self.assertIn("No root cause is proven", report)


if __name__ == "__main__":
    unittest.main()
