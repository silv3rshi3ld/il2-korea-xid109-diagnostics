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
                    "observation_start_utc": "2026-08-15T12:00:10Z",
                    "observation_duration_seconds": 90,
                    "proton_exit_code": 0,
                    "capture_complete": True,
                    "kernel_capture_complete": True,
                    "capture_warnings": [],
                }
            )
        )
        (run / ".capture-complete").touch()
        (run / ".observation-start-recorded").touch()
        for source_name, destination_name in (
            ("kernel-xid109.log", "kernel-full.log"),
            ("vkd3d-breadcrumb.log", "vkd3d.log"),
            ("proton-device-lost.log", "proton.log"),
        ):
            (run / destination_name).write_text((FIXTURES / source_name).read_text())
        kernel_events = analysis.parse_kernel_log((run / "kernel-full.log").read_text())
        (run / "xid-events.json").write_text(json.dumps({"events": kernel_events}))
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
                candidate_again = analysis.generate_candidate([first, second])
            self.assertIsNotNone(candidate)
            bundle = root / "culprit-candidate"
            self.assertTrue((bundle / "0123456789abcdef.dxil").is_file())
            self.assertTrue((bundle / "0123456789abcdef.spv").is_file())
            self.assertIn("CANDIDATE CRASH REGION", (bundle / "README.md").read_text())
            self.assertNotIn("ROOT CAUSE", (bundle / "README.md").read_text())
            self.assertEqual(candidate_again["fingerprint"], candidate["fingerprint"])
            self.assertFalse(any(root.glob("culprit-candidate.previous-*")))

    def test_one_failure_does_not_generate_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            only = analysis.summarize_run(self.make_run(root, "2026-08-15T120000Z", "baseline"))
            with mock.patch.object(analysis, "RESULTS_ROOT", root):
                self.assertIsNone(analysis.generate_candidate([only]))
            self.assertFalse((root / "culprit-candidate").exists())

    def test_failure_before_ready_is_not_analysis_eligible(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            run_path = self.make_run(root, "2026-08-15T120000Z", "baseline")
            (run_path / ".observation-start-recorded").unlink()
            metadata = json.loads((run_path / "metadata.json").read_text())
            metadata["observation_start_utc"] = None
            metadata["observation_duration_seconds"] = None
            (run_path / "metadata.json").write_text(json.dumps(metadata))
            run = analysis.summarize_run(run_path)
            self.assertFalse(run["usable_failure"])
            self.assertTrue(
                any("READY observation marker" in item for item in run["analysis_warnings"])
            )

    def test_latest_case_attempt_controls_candidate_generation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            old = analysis.summarize_run(
                self.make_run(root, "2026-08-15T120000Z", "baseline")
            )
            comparison = analysis.summarize_run(
                self.make_run(root, "2026-08-15T120100Z", "single-queue")
            )
            latest_path = self.make_run(root, "2026-08-15T120200Z", "baseline")
            metadata = json.loads((latest_path / "metadata.json").read_text())
            metadata["capture_warnings"] = ["synthetic warning"]
            (latest_path / "metadata.json").write_text(json.dumps(metadata))
            latest = analysis.summarize_run(latest_path)
            with mock.patch.object(analysis, "RESULTS_ROOT", root):
                self.assertIsNone(analysis.generate_candidate([old, comparison, latest]))

    def test_candidate_with_extra_file_is_rebuilt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            first = analysis.summarize_run(
                self.make_run(root, "2026-08-15T120000Z", "baseline")
            )
            second = analysis.summarize_run(
                self.make_run(root, "2026-08-15T120500Z", "no-descriptor-buffer")
            )
            with mock.patch.object(analysis, "RESULTS_ROOT", root):
                self.assertIsNotNone(analysis.generate_candidate([first, second]))
                secret = root / "culprit-candidate/unexpected-secret.txt"
                secret.write_text("must not be archived\n")
                relevant = root / "culprit-candidate/relevant-proton-log.txt"
                relevant.write_text("PRIVATE UNRELATED CONTENT\n")
                self.assertIsNotNone(analysis.generate_candidate([first, second]))
            self.assertFalse((root / "culprit-candidate/unexpected-secret.txt").exists())
            self.assertNotIn(
                "PRIVATE UNRELATED CONTENT",
                (root / "culprit-candidate/relevant-proton-log.txt").read_text(),
            )
            self.assertEqual(len(list(root.glob("culprit-candidate.previous-*"))), 1)

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
            metadata = json.loads((comparison_path / "metadata.json").read_text())
            metadata["duration_seconds"] = 900
            metadata["observation_duration_seconds"] = 599
            (comparison_path / "metadata.json").write_text(json.dumps(metadata))
            (comparison_path / "kernel-full.log").write_text("journal capture completed\n")
            (comparison_path / "xid-events.json").write_text(json.dumps({"events": []}))
            (comparison_path / "vkd3d.log").write_text("VKD3D capture completed\n")
            (comparison_path / "proton.log").write_text("Proton exited normally\n")
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
            metadata["observation_duration_seconds"] = 600
            (run_path / "metadata.json").write_text(json.dumps(metadata))
            (run_path / "kernel-full.log").write_text("journal capture completed\n")
            (run_path / "xid-events.json").write_text(json.dumps({"events": []}))
            (run_path / "vkd3d.log").write_text("VKD3D capture completed\n")
            (run_path / "proton.log").write_text("Proton exited normally\n")
            run = analysis.summarize_run(run_path)
            self.assertTrue(run["valid_no_xid_observation"])

    def test_verified_empty_kernel_log_can_be_a_valid_negative(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            run_path = self.make_run(root, "2026-08-15T120500Z", "single-queue")
            metadata = json.loads((run_path / "metadata.json").read_text())
            metadata["duration_seconds"] = 600
            metadata["observation_duration_seconds"] = 600
            (run_path / "metadata.json").write_text(json.dumps(metadata))
            (run_path / "kernel-full.log").write_text("")
            (run_path / "xid-events.json").write_text(json.dumps({"events": []}))
            (run_path / "vkd3d.log").write_text("VKD3D capture completed\n")
            (run_path / "proton.log").write_text("Proton exited normally\n")
            run = analysis.summarize_run(run_path)
            self.assertTrue(run["valid_no_xid_observation"])

    def test_unverified_empty_kernel_log_is_not_a_valid_negative(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            run_path = self.make_run(root, "2026-08-15T120500Z", "single-queue")
            metadata = json.loads((run_path / "metadata.json").read_text())
            metadata["duration_seconds"] = 600
            metadata["observation_duration_seconds"] = 600
            metadata["kernel_capture_complete"] = False
            (run_path / "metadata.json").write_text(json.dumps(metadata))
            (run_path / "kernel-full.log").write_text("")
            (run_path / "xid-events.json").write_text(json.dumps({"events": []}))
            (run_path / "vkd3d.log").write_text("VKD3D capture completed\n")
            (run_path / "proton.log").write_text("Proton exited normally\n")
            run = analysis.summarize_run(run_path)
            self.assertFalse(run["valid_no_xid_observation"])
            self.assertTrue(
                any("kernel journal collection" in warning for warning in run["analysis_warnings"])
            )

    def test_other_xid_is_not_a_valid_negative(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            run_path = self.make_run(root, "2026-08-15T120500Z", "single-queue")
            metadata = json.loads((run_path / "metadata.json").read_text())
            metadata["duration_seconds"] = 600
            metadata["observation_duration_seconds"] = 600
            (run_path / "metadata.json").write_text(json.dumps(metadata))
            kernel_text = (
                "2026-08-15T12:05:00Z NVRM: Xid (PCI:0000:01:00): 79, "
                "pid=42, name=IL2Series.exe\n"
            )
            events = analysis.parse_kernel_log(kernel_text)
            (run_path / "kernel-full.log").write_text(kernel_text)
            (run_path / "xid-events.json").write_text(json.dumps({"events": events}))
            (run_path / "vkd3d.log").write_text("VKD3D capture completed\n")
            (run_path / "proton.log").write_text("Proton exited normally\n")
            run = analysis.summarize_run(run_path)
            self.assertFalse(run["valid_no_xid_observation"])
            self.assertEqual(run["other_xid_events"][0]["xid"], 79)
            self.assertTrue(any("non-target" in item for item in run["analysis_warnings"]))

    def test_mixed_xid_codes_make_a_failure_unusable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            run_path = self.make_run(root, "2026-08-15T120000Z", "baseline")
            kernel_text = (run_path / "kernel-full.log").read_text() + (
                "\n2026-08-15T12:00:01Z NVRM: Xid (PCI:0000:01:00): 79, "
                "pid=42, name=IL2Series.exe\n"
            )
            events = analysis.parse_kernel_log(kernel_text)
            (run_path / "kernel-full.log").write_text(kernel_text)
            (run_path / "xid-events.json").write_text(json.dumps({"events": events}))
            run = analysis.summarize_run(run_path)
            self.assertTrue(run["xid109"])
            self.assertFalse(run["usable_failure"])
            self.assertTrue(any("non-target" in item for item in run["analysis_warnings"]))

    def test_device_lost_without_xid_is_not_a_valid_negative(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            run_path = self.make_run(root, "2026-08-15T120500Z", "baseline")
            metadata = json.loads((run_path / "metadata.json").read_text())
            metadata["duration_seconds"] = 600
            metadata["observation_duration_seconds"] = 600
            (run_path / "metadata.json").write_text(json.dumps(metadata))
            (run_path / "kernel-full.log").write_text("journal capture completed\n")
            (run_path / "xid-events.json").write_text(json.dumps({"events": []}))
            (run_path / "vkd3d.log").write_text("Device lost observed\n")
            run = analysis.summarize_run(run_path)
            self.assertTrue(run["device_lost"])
            self.assertFalse(run["valid_no_xid_observation"])

    def test_raw_kernel_log_is_authoritative_over_stale_xid_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            run_path = self.make_run(root, "2026-08-15T120000Z", "baseline")
            (run_path / "xid-events.json").write_text(json.dumps({"events": []}))
            run = analysis.summarize_run(run_path)
            self.assertTrue(run["xid109"])
            self.assertFalse(run["xid_cache_consistent"])
            self.assertFalse(run["usable_failure"])
            self.assertIn("disagrees with kernel-full.log", run["analysis_warnings"][0])

    def test_malformed_metadata_and_xid_cache_do_not_crash_analysis(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            run_path = self.make_run(root, "2026-08-15T120000Z", "baseline")
            (run_path / "metadata.json").write_text("[]\n")
            (run_path / "xid-events.json").write_text("{not-json\n")
            run = analysis.summarize_run(run_path)
            self.assertTrue(run["xid109"])
            self.assertFalse(run["capture_complete"])
            self.assertFalse(run["usable_failure"])
            self.assertGreaterEqual(len(run["analysis_warnings"]), 2)

    def test_missing_xid_cache_is_not_analysis_eligible(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            run_path = self.make_run(root, "2026-08-15T120000Z", "baseline")
            (run_path / "xid-events.json").unlink()
            run = analysis.summarize_run(run_path)
            self.assertIn("xid-events.json is missing", run["analysis_warnings"])
            self.assertFalse(run["usable_failure"])

    def test_incomplete_breadcrumb_report_is_not_a_usable_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            run_path = self.make_run(root, "2026-08-15T120000Z", "baseline")
            text = (run_path / "vkd3d.log").read_text()
            (run_path / "vkd3d.log").write_text(
                text.replace("Done analyzing breadcrumbs ...", "")
            )
            run = analysis.summarize_run(run_path)
            self.assertTrue(run["breadcrumb_analysis"])
            self.assertFalse(run["breadcrumb_analysis_complete"])
            self.assertFalse(run["usable_failure"])

    def test_complete_report_with_open_ended_region_is_a_usable_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            run_path = self.make_run(root, "2026-08-15T120000Z", "baseline")
            text = (run_path / "vkd3d.log").read_text()
            (run_path / "vkd3d.log").write_text(
                text.replace("===== Potential crash region END =====\n", "")
            )
            run = analysis.summarize_run(run_path)
            self.assertTrue(run["breadcrumb_analysis_complete"])
            self.assertFalse(run["regions"][0]["complete_delimiters"])
            self.assertTrue(run["usable_failure"])

    def test_candidate_shader_rejects_parent_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            run_path = self.make_run(root, "2026-08-15T120000Z", "baseline")
            manifest_path = run_path / "shader-manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["shaders"][0]["file"] = "../outside.dxil"
            manifest_path.write_text(json.dumps(manifest))
            candidate = root / "candidate"
            candidate.mkdir()
            with mock.patch.object(analysis, "RESULTS_ROOT", root):
                with self.assertRaisesRegex(RuntimeError, "unsafe shader path"):
                    analysis.copy_candidate_shaders(
                        candidate,
                        [{"run": run_path.name}],
                        {"0123456789abcdef"},
                    )

    def test_candidate_shader_verifies_declared_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            run_path = self.make_run(root, "2026-08-15T120000Z", "baseline")
            (run_path / "shaders/0123456789abcdef.dxil").write_bytes(b"changed")
            candidate = root / "candidate"
            candidate.mkdir()
            with mock.patch.object(analysis, "RESULTS_ROOT", root):
                with self.assertRaisesRegex(RuntimeError, "SHA-256 mismatch"):
                    analysis.copy_candidate_shaders(
                        candidate,
                        [{"run": run_path.name}],
                        {"0123456789abcdef"},
                    )

    def test_candidate_shader_normalizes_short_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            run_path = self.make_run(root, "2026-08-15T120000Z", "baseline")
            manifest_path = run_path / "shader-manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["shaders"][0]["vkd3d_hash"] = "89ABCDEF"
            manifest_path.write_text(json.dumps(manifest))
            candidate = root / "candidate"
            candidate.mkdir()
            with mock.patch.object(analysis, "RESULTS_ROOT", root):
                entries = analysis.copy_candidate_shaders(
                    candidate,
                    [{"run": run_path.name}],
                    {"0000000089abcdef"},
                )
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["vkd3d_hash"], "0000000089abcdef")

    def test_candidate_shader_rejects_conflicting_bytes_for_same_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            first_path = self.make_run(root, "2026-08-15T120000Z", "baseline")
            second_path = self.make_run(
                root, "2026-08-15T120500Z", "no-descriptor-buffer"
            )
            second_shader = second_path / "shaders/0123456789abcdef.dxil"
            second_shader.write_bytes(b"different synthetic dxil")
            manifest_path = second_path / "shader-manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["shaders"][0]["byte_size"] = second_shader.stat().st_size
            manifest["shaders"][0]["sha256"] = hashlib.sha256(
                second_shader.read_bytes()
            ).hexdigest()
            manifest_path.write_text(json.dumps(manifest))
            candidate = root / "candidate"
            candidate.mkdir()
            with mock.patch.object(analysis, "RESULTS_ROOT", root):
                with self.assertRaisesRegex(RuntimeError, "conflicting shader bytes"):
                    analysis.copy_candidate_shaders(
                        candidate,
                        [{"run": first_path.name}, {"run": second_path.name}],
                        {"0123456789abcdef"},
                    )

    def test_candidate_generation_error_removes_owned_staging_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            first_path = self.make_run(root, "2026-08-15T120000Z", "baseline")
            second_path = self.make_run(
                root, "2026-08-15T120500Z", "no-descriptor-buffer"
            )
            first = analysis.summarize_run(first_path)
            second = analysis.summarize_run(second_path)
            (second_path / "shaders/0123456789abcdef.dxil").write_bytes(b"tampered")
            with mock.patch.object(analysis, "RESULTS_ROOT", root):
                with self.assertRaisesRegex(RuntimeError, "SHA-256 mismatch"):
                    analysis.generate_candidate([first, second])
            self.assertFalse(any(root.glob(".culprit-candidate-building-*")))
            self.assertFalse((root / "culprit-candidate").exists())

    def test_no_convergence_retires_a_stale_generated_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            stale = root / "culprit-candidate"
            stale.mkdir()
            (stale / ".generated-by-il2-xid109-analyzer").write_text("generated\n")
            (stale / "metadata.json").write_text("{}\n")
            with mock.patch.object(analysis, "RESULTS_ROOT", root):
                self.assertIsNone(analysis.generate_candidate([]))
            self.assertFalse(stale.exists())
            backups = list(root.glob("culprit-candidate.previous-*"))
            self.assertEqual(len(backups), 1)
            self.assertTrue((backups[0] / "metadata.json").is_file())

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
            self.assertIn("fully-rendered-hangar observation was 90 seconds", report)
            self.assertIn("| baseline | 90 |", report)

    def test_descriptor_qa_faults_are_reported_with_shader_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            run_path = self.make_run(root, "2026-08-15T120000Z", "descriptor-qa")
            (run_path / "descriptor-qa.log").write_text(
                (FIXTURES / "vkd3d-descriptor-qa.log").read_text()
            )
            run = analysis.summarize_run(run_path)
            self.assertEqual(len(run["descriptor_qa_faults"]), 2)
            fault = run["descriptor_qa_faults"][1]
            self.assertEqual(fault["fault_types"], ["MISMATCH_DESCRIPTOR_TYPE"])
            self.assertEqual(fault["shader_hash"], "0123456789abcdef")
            self.assertEqual(fault["instruction_id"], 27)
            self.assertEqual(fault["descriptor_heap_cookie"], 1900)
            self.assertEqual(fault["resource_view_cookie"], 1902)
            self.assertEqual(fault["failed_heap_index"], 93)
            self.assertEqual(
                fault["shader_dump_files"],
                [
                    "shaders/0123456789abcdef.dxil",
                    "shaders/0123456789abcdef.spv",
                ],
            )
            evidence = analysis.build_evidence([run])
            report = analysis.markdown([run], evidence, None)
            self.assertIn("## Descriptor QA faults", report)
            self.assertIn("HEAP_OUT_OF_RANGE, MISMATCH_DESCRIPTOR_TYPE", report)
            self.assertIn("0123456789abcdef", report)
            self.assertIn("93", report)


if __name__ == "__main__":
    unittest.main()
